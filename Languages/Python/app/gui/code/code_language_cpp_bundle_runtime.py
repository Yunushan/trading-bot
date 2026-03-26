from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from . import code_language_release_runtime
from .code_language_catalog import (
    CPP_CACHE_META_FILE,
    CPP_PACKAGED_EXECUTABLE_BASENAME,
    CPP_RELEASE_CPP_ASSET,
    CPP_RELEASE_OWNER,
    CPP_RELEASE_REPO,
)

_CPP_PACKAGED_MANIFEST_CACHE: dict[str, tuple[dict[str, str], float]] = {}
_CPP_LATEST_RELEASE_INFO_CACHE: dict[str, tuple[str | None, str | None, float]] = {}


def reset_cpp_runtime_caches() -> None:
    _CPP_PACKAGED_MANIFEST_CACHE.clear()
    _CPP_LATEST_RELEASE_INFO_CACHE.clear()


def cpp_cache_root() -> Path | None:
    candidates: list[Path] = []
    for env_key in ("LOCALAPPDATA", "APPDATA"):
        raw_base = str(os.environ.get(env_key) or "").strip()
        if raw_base:
            candidates.append(Path(raw_base) / "TradingBot" / "cpp-runtime")
    try:
        candidates.append(Path.home() / ".trading-bot" / "cpp-runtime")
    except Exception:
        pass

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
        except Exception:
            continue
    return None


def path_is_within_directory(path_value: Path | None, directory: Path | None) -> bool:
    if path_value is None or directory is None:
        return False
    try:
        path_resolved = path_value.resolve()
    except Exception:
        path_resolved = path_value
    try:
        dir_resolved = directory.resolve()
    except Exception:
        dir_resolved = directory
    path_norm = os.path.normcase(os.path.normpath(str(path_resolved)))
    dir_norm = os.path.normcase(os.path.normpath(str(dir_resolved)))
    if path_norm == dir_norm:
        return True
    return path_norm.startswith(dir_norm + os.sep)


def cpp_runtime_is_cached_path(exe_path: Path | None) -> bool:
    cache_root = cpp_cache_root()
    if exe_path is None or cache_root is None:
        return False
    return path_is_within_directory(exe_path, cache_root)


def cpp_packaged_executable_names() -> set[str]:
    names = {CPP_PACKAGED_EXECUTABLE_BASENAME}
    if sys.platform == "win32":
        names.add(f"{CPP_PACKAGED_EXECUTABLE_BASENAME}.exe")
    return names


def find_cpp_packaged_exe_under(root: Path | None) -> Path | None:
    if root is None:
        return None
    try:
        resolved_root = root.resolve()
    except Exception:
        resolved_root = root
    if not resolved_root.exists():
        return None

    names = cpp_packaged_executable_names()
    found: list[Path] = []

    for name in names:
        candidate = resolved_root / name
        if candidate.is_file():
            found.append(candidate)

    if resolved_root.is_dir() and not found:
        try:
            for path in resolved_root.rglob("*"):
                if path.is_file() and path.name in names:
                    found.append(path)
        except Exception:
            return None

    if not found:
        return None
    found.sort(key=lambda item: float(item.stat().st_mtime) if item.exists() else 0.0, reverse=True)
    return found[0]


def cpp_packaged_runtime_exe(find_cpp_code_tab_executable) -> Path | None:
    if not code_language_release_runtime.is_frozen_python_app():
        return None
    exe_path = find_cpp_code_tab_executable()
    if exe_path is None or not exe_path.is_file():
        return None
    if sys.platform == "win32" and cpp_runtime_bundle_missing(exe_path):
        return None
    return exe_path


def cpp_packaged_manifest_installed_map(exe_path: Path | None) -> dict[str, str]:
    if exe_path is None:
        return {}
    cache_key = os.path.normcase(os.path.normpath(str(exe_path.parent)))
    now = time.time()
    entry = _CPP_PACKAGED_MANIFEST_CACHE.get(cache_key)
    if isinstance(entry, tuple) and len(entry) == 2:
        cached_map, cached_at = entry
        try:
            if now - float(cached_at or 0.0) < 30 and isinstance(cached_map, dict):
                return dict(cached_map)
        except Exception:
            pass

    manifest_paths = [
        exe_path.parent / "cpp-deps.json",
        exe_path.parent / "cpp-env-versions.json",
        exe_path.parent / "TB_CPP_ENV_VERSIONS.json",
        exe_path.parent / "versions.json",
    ]
    resolved: dict[str, str] = {}
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue

        if isinstance(payload, dict):
            deps = payload.get("dependencies")
            if isinstance(deps, list):
                for item in deps:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or item.get("label") or "").strip()
                    version = str(item.get("installed") or item.get("version") or "").strip()
                    if not name or not version:
                        continue
                    resolved[name.lower()] = version

            rows = payload.get("rows")
            if isinstance(rows, list):
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or item.get("label") or "").strip()
                    version = str(item.get("installed") or item.get("version") or "").strip()
                    if not name or not version:
                        continue
                    resolved[name.lower()] = version

            if not resolved:
                for key, value in payload.items():
                    if isinstance(value, (str, int, float)):
                        version = str(value).strip()
                        if version:
                            resolved[str(key).strip().lower()] = version
        if resolved:
            break

    _CPP_PACKAGED_MANIFEST_CACHE[cache_key] = (dict(resolved), now)
    return resolved


def cpp_packaged_installed_value(target: dict[str, str], find_cpp_code_tab_executable) -> str | None:
    exe_path = cpp_packaged_runtime_exe(find_cpp_code_tab_executable)
    if exe_path is None:
        return None

    custom = str(target.get("custom") or "").strip().lower()
    label = str(target.get("label") or "").strip().lower()
    manifest_map = cpp_packaged_manifest_installed_map(exe_path)

    aliases: list[str] = [label]
    alias_by_custom = {
        "cpp_qt": ["qt6 (c++)", "qt6"],
        "cpp_qt_network": ["qt6 network (rest)", "qt6 network"],
        "cpp_qt_webengine": ["qt6 webengine"],
        "cpp_qt_websockets": ["qt6 websockets"],
        "cpp_eigen": ["eigen"],
        "cpp_xtensor": ["xtensor"],
        "cpp_talib": ["ta-lib", "talib"],
        "cpp_libcurl": ["libcurl", "curl"],
        "cpp_cpr": ["cpr"],
        "cpp_file_version": ["binance rest client (native)", "binance websocket client (native)"],
    }
    for alias in alias_by_custom.get(custom, []):
        alias_norm = str(alias).strip().lower()
        if alias_norm and alias_norm not in aliases:
            aliases.append(alias_norm)
    for key in aliases:
        value = str(manifest_map.get(key) or "").strip()
        if value and value.strip().lower() not in {"bundled", "bundle"}:
            return value

    if custom == "cpp_file_version":
        release_tag = code_language_release_runtime.release_tag_from_metadata_dirs(
            [exe_path.parent, exe_path.parent.parent]
        )
        if release_tag:
            return release_tag
    return None


def cpp_cache_meta_path(cache_root: Path | None) -> Path | None:
    if cache_root is None:
        return None
    return cache_root / CPP_CACHE_META_FILE


def read_cache_meta(cache_root: Path | None) -> dict:
    meta_path = cpp_cache_meta_path(cache_root)
    if meta_path is None or not meta_path.is_file():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_cache_meta(cache_root: Path | None, payload: dict) -> None:
    meta_path = cpp_cache_meta_path(cache_root)
    if meta_path is None:
        return
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def cpp_latest_release_asset_info(timeout: float = 8.0) -> tuple[str | None, str | None]:
    explicit_url = str(os.environ.get("TB_CPP_ZIP_URL") or "").strip()
    if explicit_url:
        return None, explicit_url

    owner = str(os.environ.get("TB_RELEASE_OWNER") or CPP_RELEASE_OWNER).strip() or CPP_RELEASE_OWNER
    repo = str(os.environ.get("TB_RELEASE_REPO") or CPP_RELEASE_REPO).strip() or CPP_RELEASE_REPO
    asset_name = str(os.environ.get("TB_CPP_RELEASE_ASSET") or CPP_RELEASE_CPP_ASSET).strip() or CPP_RELEASE_CPP_ASSET

    cache_key = f"{owner}/{repo}/{asset_name}".lower()
    now = time.time()
    entry = _CPP_LATEST_RELEASE_INFO_CACHE.get(cache_key)
    if isinstance(entry, tuple) and len(entry) == 3:
        cached_tag, cached_url, cached_at = entry
        try:
            if now - float(cached_at or 0.0) < 300:
                return cached_tag, cached_url
        except Exception:
            pass

    tag_name: str | None = None
    browser_url: str | None = None
    payload = code_language_release_runtime.http_get_json(
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
        timeout=timeout,
    )
    if isinstance(payload, dict):
        tag_name = str(payload.get("tag_name") or "").strip() or None
        assets = payload.get("assets")
        if isinstance(assets, list):
            for row in assets:
                if not isinstance(row, dict):
                    continue
                if str(row.get("name") or "").strip() != asset_name:
                    continue
                candidate = str(row.get("browser_download_url") or "").strip()
                if candidate:
                    browser_url = candidate
                    break

    if not browser_url:
        browser_url = f"https://github.com/{owner}/{repo}/releases/latest/download/{asset_name}"

    _CPP_LATEST_RELEASE_INFO_CACHE[cache_key] = (tag_name, browser_url, now)
    return tag_name, browser_url


def cpp_release_is_newer(latest_tag: str | None, cached_tag: str | None) -> bool:
    latest_clean = str(latest_tag or "").strip()
    cached_clean = str(cached_tag or "").strip()
    if not latest_clean:
        return False
    if not cached_clean:
        return True

    latest_ver = code_language_release_runtime.extract_semver_from_text(latest_clean)
    cached_ver = code_language_release_runtime.extract_semver_from_text(cached_clean)
    if latest_ver and cached_ver:
        return code_language_release_runtime.version_sort_key(latest_ver) > code_language_release_runtime.version_sort_key(cached_ver)
    return latest_clean != cached_clean


def download_binary_file(url: str, target_path: Path, timeout: float = 45.0) -> None:
    timeout_val = max(8.0, float(timeout or 45.0))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_val) as response:
        with target_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def extract_zip_safely(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        destination_root = destination.resolve()
    except Exception:
        destination_root = destination
    destination_root_norm = os.path.normcase(str(destination_root))

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            name = str(member.filename or "").replace("\\", "/")
            if not name:
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in name:
                continue

            target = destination / Path(name)
            try:
                target_resolved = target.resolve()
            except Exception:
                target_resolved = target
            target_norm = os.path.normcase(str(target_resolved))
            if not (target_norm == destination_root_norm or target_norm.startswith(destination_root_norm + os.sep)):
                continue

            if member.is_dir():
                target_resolved.mkdir(parents=True, exist_ok=True)
                continue

            target_resolved.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target_resolved.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def cpp_local_zip_candidates(cache_root: Path | None) -> list[Path]:
    candidates: list[Path] = []

    explicit_zip = str(os.environ.get("TB_CPP_ZIP_PATH") or "").strip()
    if explicit_zip:
        candidates.append(Path(explicit_zip).expanduser())

    try:
        exe_dir = Path(sys.executable).resolve().parent
    except Exception:
        exe_dir = None
    if exe_dir is not None:
        candidates.extend(
            [
                exe_dir / CPP_RELEASE_CPP_ASSET,
                exe_dir / "release" / CPP_RELEASE_CPP_ASSET,
            ]
        )

    try:
        cwd = Path.cwd().resolve()
    except Exception:
        cwd = None
    if cwd is not None:
        candidates.extend(
            [
                cwd / CPP_RELEASE_CPP_ASSET,
                cwd / "release" / CPP_RELEASE_CPP_ASSET,
            ]
        )

    if cache_root is not None:
        candidates.append(cache_root / "_download" / CPP_RELEASE_CPP_ASSET)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = os.path.normcase(os.path.normpath(str(resolved)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def cpp_runtime_bundle_missing(exe_path: Path) -> bool:
    required_dlls = ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll")
    for dll_name in required_dlls:
        try:
            if not (exe_path.parent / dll_name).is_file():
                return True
        except Exception:
            return True
    if sys.platform == "win32":
        try:
            if not (exe_path.parent / "platforms" / "qwindows.dll").is_file():
                return True
        except Exception:
            return True
    return False


def populate_cpp_bundle_from_zip(
    zip_path: Path,
    *,
    cache_root: Path,
    bundle_dir: Path,
) -> tuple[Path | None, str | None]:
    if not zip_path.is_file():
        return None, f"Zip not found: {zip_path}"

    staging_dir = cache_root / "_staging"
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        pass
    staging_dir.mkdir(parents=True, exist_ok=True)

    extracted_dir = staging_dir / "extract"
    try:
        extract_zip_safely(zip_path, extracted_dir)
    except Exception as exc:
        return None, f"Could not extract C++ bundle '{zip_path}': {exc}"

    staged_exe = find_cpp_packaged_exe_under(extracted_dir)
    if staged_exe is None or not staged_exe.is_file():
        return None, f"Archive '{zip_path.name}' does not contain Trading-Bot-C++.exe."

    staged_bundle_dir = staged_exe.parent
    try:
        shutil.rmtree(bundle_dir, ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.copytree(staged_bundle_dir, bundle_dir, dirs_exist_ok=True)
    except Exception as exc:
        return None, f"Could not cache C++ runtime files: {exc}"

    final_exe = find_cpp_packaged_exe_under(bundle_dir)
    if final_exe is None or not final_exe.is_file():
        return None, "C++ cache populated but executable could not be located."
    if sys.platform == "win32" and cpp_runtime_bundle_missing(final_exe):
        return None, "C++ bundle is incomplete (Qt runtime files missing)."
    return final_exe, None


def ensure_cached_cpp_bundle(find_cpp_code_tab_executable, force_download: bool = False) -> tuple[Path | None, str | None]:
    cache_root = cpp_cache_root()
    if cache_root is None:
        return None, "Could not initialize local cache directory for C++ runtime."

    bundle_dir = cache_root / "Trading-Bot-C++"
    cached_exe = find_cpp_packaged_exe_under(bundle_dir)
    cached_valid = (
        cached_exe is not None
        and cached_exe.is_file()
        and (sys.platform != "win32" or not cpp_runtime_bundle_missing(cached_exe))
    )
    cache_meta = read_cache_meta(cache_root)
    latest_tag: str | None = None
    download_url: str | None = None
    allow_local_zip = True

    if cached_valid and not force_download:
        auto_update_raw = str(os.environ.get("TB_CPP_AUTO_UPDATE", "1") or "1").strip().lower()
        auto_update_enabled = auto_update_raw not in {"0", "false", "no", "off"}
        if not auto_update_enabled:
            return cached_exe, None

        latest_tag, download_url = cpp_latest_release_asset_info(timeout=8.0)
        if not latest_tag:
            return cached_exe, None

        cached_tag = str(cache_meta.get("release_tag") or "").strip() or None
        if cpp_release_is_newer(latest_tag, cached_tag):
            allow_local_zip = False
        else:
            return cached_exe, None

    local_zip_error = ""
    if allow_local_zip:
        for local_zip in cpp_local_zip_candidates(cache_root):
            if not local_zip.is_file():
                continue
            from_zip_exe, from_zip_err = populate_cpp_bundle_from_zip(
                local_zip,
                cache_root=cache_root,
                bundle_dir=bundle_dir,
            )
            if from_zip_exe is not None and from_zip_exe.is_file():
                meta_payload = dict(cache_meta)
                if latest_tag:
                    meta_payload["release_tag"] = latest_tag
                meta_payload["asset_name"] = CPP_RELEASE_CPP_ASSET
                meta_payload["updated_at"] = time.time()
                if download_url:
                    meta_payload["download_url"] = download_url
                write_cache_meta(cache_root, meta_payload)
                return from_zip_exe, None
            if from_zip_err:
                local_zip_error = str(from_zip_err)

    if not download_url:
        latest_tag, download_url = cpp_latest_release_asset_info(timeout=8.0)
    if not download_url:
        if cached_valid:
            return cached_exe, None
        if local_zip_error:
            return None, local_zip_error
        return None, "Could not resolve C++ release asset URL."

    timeout_raw = str(os.environ.get("TB_CPP_DOWNLOAD_TIMEOUT") or "").strip()
    try:
        timeout_val = max(8.0, float(timeout_raw)) if timeout_raw else 45.0
    except Exception:
        timeout_val = 45.0

    download_dir = cache_root / "_download"
    zip_target = download_dir / CPP_RELEASE_CPP_ASSET

    try:
        download_binary_file(download_url, zip_target, timeout=timeout_val)
    except Exception as exc:
        if cached_valid:
            return cached_exe, None
        if local_zip_error:
            return None, f"{local_zip_error}\nCould not download C++ bundle: {exc}"
        return None, f"Could not download C++ bundle: {exc}"

    downloaded_exe, downloaded_err = populate_cpp_bundle_from_zip(
        zip_target,
        cache_root=cache_root,
        bundle_dir=bundle_dir,
    )
    if downloaded_exe is None or not downloaded_exe.is_file():
        if cached_valid:
            return cached_exe, None
        return downloaded_exe, downloaded_err

    meta_payload = dict(cache_meta)
    if latest_tag:
        meta_payload["release_tag"] = latest_tag
    meta_payload["asset_name"] = CPP_RELEASE_CPP_ASSET
    meta_payload["updated_at"] = time.time()
    meta_payload["download_url"] = download_url
    write_cache_meta(cache_root, meta_payload)
    return downloaded_exe, None
