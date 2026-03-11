from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from app.gui.code_language_catalog import (
    CPP_BUILD_ROOT,
    CPP_CACHE_META_FILE,
    CPP_EXECUTABLE_BASENAME,
    CPP_EXECUTABLE_LEGACY_BASENAME,
    CPP_PACKAGED_EXECUTABLE_BASENAME,
    CPP_PROJECT_PATH,
    CPP_RELEASE_CPP_ASSET,
    CPP_RELEASE_OWNER,
    CPP_RELEASE_REPO,
    RELEASE_INFO_JSON_NAME,
    RELEASE_TAG_TEXT_NAME,
)

_THIS_FILE = Path(__file__).resolve()

_CPP_PACKAGED_MANIFEST_CACHE: dict[str, tuple[dict[str, str], float]] = {}
_CPP_LATEST_RELEASE_INFO_CACHE: dict[str, tuple[str | None, str | None, float]] = {}


def reset_cpp_runtime_caches() -> None:
    _CPP_PACKAGED_MANIFEST_CACHE.clear()
    _CPP_LATEST_RELEASE_INFO_CACHE.clear()


def _version_sort_key(version_text: str | None) -> tuple[int, ...]:
    value = str(version_text or "").strip()
    if not value:
        return tuple()
    parts = re.findall(r"\d+", value)
    if not parts:
        return tuple()
    try:
        return tuple(int(part) for part in parts)
    except Exception:
        return tuple()


def _extract_semver_from_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(
        r"(\d+(?:[._]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).replace("_", ".")


def _http_get_text(url: str, timeout: float = 8.0) -> str | None:
    if not url:
        return None
    timeout_val = max(2.0, float(timeout or 8.0))
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
        with urllib.request.urlopen(request, timeout=timeout_val) as response:
            data = response.read()
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _http_get_json(url: str, timeout: float = 8.0):
    payload = _http_get_text(url, timeout=timeout)
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None


def _cpp_qt_version_from_path(path_value: str | None) -> str | None:
    text = str(path_value or "")
    for match in re.findall(r"(?<!\d)(6\.\d+(?:\.\d+)?)(?!\d)", text):
        if match:
            return match
    return None


def cpp_executable_names() -> set[str]:
    base_names = {
        CPP_EXECUTABLE_BASENAME,
        CPP_PACKAGED_EXECUTABLE_BASENAME,
        CPP_EXECUTABLE_LEGACY_BASENAME,
    }
    names = set(base_names)
    if sys.platform == "win32":
        names.update({f"{name}.exe" for name in base_names})
    return names


def is_frozen_python_app() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))


def _normalize_release_tag_text(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    lower_text = text.lower()
    for prefix in ("refs/tags/", "refs/heads/"):
        if lower_text.startswith(prefix):
            text = text[len(prefix):].strip()
            lower_text = text.lower()
            break
    if not text:
        return None
    if lower_text in {"none", "null", "unknown", "n/a", "na", "-"}:
        return None
    if len(text) > 96:
        text = text[:96].strip()
    semver = _extract_semver_from_text(text)
    if semver:
        return semver
    return text


def _release_tag_from_json_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    candidate_keys = (
        "release_tag",
        "tag_name",
        "tag",
        "python_release_tag",
        "app_release_tag",
        "version",
    )
    for key in candidate_keys:
        tag_value = _normalize_release_tag_text(payload.get(key))
        if tag_value:
            return tag_value

    nested_keys = ("python", "app", "release")
    for nested_key in nested_keys:
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key in candidate_keys:
            tag_value = _normalize_release_tag_text(nested.get(key))
            if tag_value:
                return tag_value
    return None


def _release_tag_from_text_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue
            return _normalize_release_tag_text(line)
    except Exception:
        return None
    return None


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = os.path.normcase(os.path.normpath(str(resolved)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _release_tag_from_metadata_dirs(directories: list[Path]) -> str | None:
    metadata_names = (
        RELEASE_INFO_JSON_NAME,
        "tb-release.json",
        RELEASE_TAG_TEXT_NAME,
        "tb-release.txt",
    )
    for directory in _dedupe_paths(directories):
        for name in metadata_names:
            file_path = directory / name
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() == ".json":
                tag_value = _release_tag_from_json_file(file_path)
            else:
                tag_value = _release_tag_from_text_file(file_path)
            if tag_value:
                return tag_value
    return None


def _python_release_metadata_dirs() -> list[Path]:
    directories: list[Path] = []
    try:
        app_dir = _THIS_FILE.parents[1]
        directories.extend([app_dir, app_dir.parent])
    except Exception:
        pass

    if is_frozen_python_app():
        meipass_raw = str(getattr(sys, "_MEIPASS", "") or "").strip()
        if meipass_raw:
            meipass_dir = Path(meipass_raw)
            directories.extend([meipass_dir, meipass_dir / "app"])
        try:
            exe_dir = Path(sys.executable).resolve().parent
            directories.extend([exe_dir, exe_dir / "app"])
        except Exception:
            pass
    return _dedupe_paths(directories)


def python_runtime_release_tag() -> str | None:
    env_keys = (
        "TB_PY_RELEASE_TAG",
        "TB_PYTHON_RELEASE_TAG",
        "TB_APP_RELEASE_TAG",
        "TB_RELEASE_TAG",
        "BOT_RELEASE_TAG",
    )
    for key in env_keys:
        value = _normalize_release_tag_text(os.environ.get(key))
        if value:
            return value
    return _release_tag_from_metadata_dirs(_python_release_metadata_dirs())


def cpp_runtime_release_snapshot() -> tuple[str | None, str]:
    exe_path = find_cpp_code_tab_executable()
    if exe_path is None or not exe_path.is_file():
        return None, "Not installed"

    tag_from_bundle = _release_tag_from_metadata_dirs([exe_path.parent, exe_path.parent.parent])
    if tag_from_bundle:
        return tag_from_bundle, "Ready"

    if cpp_runtime_is_cached_path(exe_path):
        cache_meta = read_cache_meta(cpp_cache_root())
        cached_tag = _normalize_release_tag_text(cache_meta.get("release_tag"))
        if cached_tag:
            return cached_tag, "Ready"
        return None, "Cached"

    if is_frozen_python_app():
        return None, "Bundled"
    return None, "Local build"


def python_runtime_release_line() -> str:
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    release_tag = python_runtime_release_tag()
    if release_tag:
        return f"Release: {release_tag} | Python {py_version}"
    if is_frozen_python_app():
        return f"Release: Unknown | Python {py_version}"
    return f"Release: Dev | Python {py_version}"


def cpp_runtime_release_line() -> str:
    release_tag, state_text = cpp_runtime_release_snapshot()
    if release_tag:
        return f"Release: {release_tag}"
    if is_frozen_python_app():
        python_release_tag = python_runtime_release_tag()
        if python_release_tag:
            return f"Release: {python_release_tag}"
    if state_text:
        return f"Release: {state_text}"
    return "Release: Unknown"


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


def _path_is_within_directory(path_value: Path | None, directory: Path | None) -> bool:
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
    return _path_is_within_directory(exe_path, cache_root)


def _cpp_packaged_executable_names() -> set[str]:
    names = {CPP_PACKAGED_EXECUTABLE_BASENAME}
    if sys.platform == "win32":
        names.add(f"{CPP_PACKAGED_EXECUTABLE_BASENAME}.exe")
    return names


def _find_cpp_packaged_exe_under(root: Path | None) -> Path | None:
    if root is None:
        return None
    try:
        resolved_root = root.resolve()
    except Exception:
        resolved_root = root
    if not resolved_root.exists():
        return None

    names = _cpp_packaged_executable_names()
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


def cpp_packaged_runtime_exe() -> Path | None:
    if not is_frozen_python_app():
        return None
    exe_path = find_cpp_code_tab_executable()
    if exe_path is None or not exe_path.is_file():
        return None
    if sys.platform == "win32" and _cpp_runtime_bundle_missing(exe_path):
        return None
    return exe_path


def _cpp_packaged_manifest_installed_map(exe_path: Path | None) -> dict[str, str]:
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


def cpp_packaged_installed_value(target: dict[str, str]) -> str | None:
    exe_path = cpp_packaged_runtime_exe()
    if exe_path is None:
        return None

    custom = str(target.get("custom") or "").strip().lower()
    label = str(target.get("label") or "").strip().lower()
    manifest_map = _cpp_packaged_manifest_installed_map(exe_path)

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
        release_tag = _release_tag_from_metadata_dirs([exe_path.parent, exe_path.parent.parent])
        if release_tag:
            return release_tag
    return None


def _cpp_cache_meta_path(cache_root: Path | None) -> Path | None:
    if cache_root is None:
        return None
    return cache_root / CPP_CACHE_META_FILE


def read_cache_meta(cache_root: Path | None) -> dict:
    meta_path = _cpp_cache_meta_path(cache_root)
    if meta_path is None or not meta_path.is_file():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_cache_meta(cache_root: Path | None, payload: dict) -> None:
    meta_path = _cpp_cache_meta_path(cache_root)
    if meta_path is None:
        return
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _cpp_latest_release_asset_info(timeout: float = 8.0) -> tuple[str | None, str | None]:
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
    payload = _http_get_json(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", timeout=timeout)
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


def _cpp_release_is_newer(latest_tag: str | None, cached_tag: str | None) -> bool:
    latest_clean = str(latest_tag or "").strip()
    cached_clean = str(cached_tag or "").strip()
    if not latest_clean:
        return False
    if not cached_clean:
        return True

    latest_ver = _extract_semver_from_text(latest_clean)
    cached_ver = _extract_semver_from_text(cached_clean)
    if latest_ver and cached_ver:
        return _version_sort_key(latest_ver) > _version_sort_key(cached_ver)
    return latest_clean != cached_clean


def _download_binary_file(url: str, target_path: Path, timeout: float = 45.0) -> None:
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


def _extract_zip_safely(zip_path: Path, destination: Path) -> None:
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


def _cpp_local_zip_candidates(cache_root: Path | None) -> list[Path]:
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


def _cpp_runtime_bundle_missing(exe_path: Path) -> bool:
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


def _populate_cpp_bundle_from_zip(
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
        _extract_zip_safely(zip_path, extracted_dir)
    except Exception as exc:
        return None, f"Could not extract C++ bundle '{zip_path}': {exc}"

    staged_exe = _find_cpp_packaged_exe_under(extracted_dir)
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

    final_exe = _find_cpp_packaged_exe_under(bundle_dir)
    if final_exe is None or not final_exe.is_file():
        return None, "C++ cache populated but executable could not be located."
    if sys.platform == "win32" and _cpp_runtime_bundle_missing(final_exe):
        return None, "C++ bundle is incomplete (Qt runtime files missing)."
    return final_exe, None


def ensure_cached_cpp_bundle(force_download: bool = False) -> tuple[Path | None, str | None]:
    cache_root = cpp_cache_root()
    if cache_root is None:
        return None, "Could not initialize local cache directory for C++ runtime."

    bundle_dir = cache_root / "Trading-Bot-C++"
    cached_exe = _find_cpp_packaged_exe_under(bundle_dir)
    cached_valid = (
        cached_exe is not None
        and cached_exe.is_file()
        and (sys.platform != "win32" or not _cpp_runtime_bundle_missing(cached_exe))
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

        latest_tag, download_url = _cpp_latest_release_asset_info(timeout=8.0)
        if not latest_tag:
            return cached_exe, None

        cached_tag = str(cache_meta.get("release_tag") or "").strip() or None
        if _cpp_release_is_newer(latest_tag, cached_tag):
            allow_local_zip = False
        else:
            return cached_exe, None

    local_zip_error = ""
    if allow_local_zip:
        for local_zip in _cpp_local_zip_candidates(cache_root):
            if not local_zip.is_file():
                continue
            from_zip_exe, from_zip_err = _populate_cpp_bundle_from_zip(
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
                _write_cache_meta(cache_root, meta_payload)
                return from_zip_exe, None
            if from_zip_err:
                local_zip_error = str(from_zip_err)

    if not download_url:
        latest_tag, download_url = _cpp_latest_release_asset_info(timeout=8.0)
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
        _download_binary_file(download_url, zip_target, timeout=timeout_val)
    except Exception as exc:
        if cached_valid:
            return cached_exe, None
        if local_zip_error:
            return None, f"{local_zip_error}\nCould not download C++ bundle: {exc}"
        return None, f"Could not download C++ bundle: {exc}"

    downloaded_exe, downloaded_err = _populate_cpp_bundle_from_zip(
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
    _write_cache_meta(cache_root, meta_payload)
    return downloaded_exe, None


def _cpp_runtime_search_roots() -> list[Path]:
    raw_roots: list[Path] = []
    frozen_mode = is_frozen_python_app()

    try:
        exe_dir = Path(sys.executable).resolve().parent
    except Exception:
        exe_dir = None
    if exe_dir is not None:
        raw_roots.extend(
            [
                exe_dir,
                exe_dir / "Trading-Bot-C++",
                exe_dir / "release",
                exe_dir / "release" / "Trading-Bot-C++",
            ]
        )

    try:
        cwd = Path.cwd().resolve()
    except Exception:
        cwd = None
    if cwd is not None and not frozen_mode:
        raw_roots.extend(
            [
                cwd,
                cwd / "Trading-Bot-C++",
                cwd / "release",
                cwd / "release" / "Trading-Bot-C++",
            ]
        )

    env_hint = str(os.environ.get("TB_CPP_EXE_DIR") or "").strip()
    if env_hint:
        raw_roots.append(Path(env_hint).expanduser())

    cache_root = cpp_cache_root()
    if cache_root is not None:
        raw_roots.extend([cache_root / "Trading-Bot-C++", cache_root])

    unique: list[Path] = []
    seen: set[str] = set()
    for root in raw_roots:
        try:
            resolved = root.resolve()
        except Exception:
            resolved = root
        key = os.path.normcase(os.path.normpath(str(resolved)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def find_cpp_code_tab_executable() -> Path | None:
    frozen_mode = is_frozen_python_app()
    if frozen_mode:
        candidate_names = {CPP_PACKAGED_EXECUTABLE_BASENAME}
        if sys.platform == "win32":
            candidate_names.add(f"{CPP_PACKAGED_EXECUTABLE_BASENAME}.exe")
    else:
        candidate_names = cpp_executable_names()
    candidate_stems = {Path(name).stem.lower() for name in candidate_names}
    packaged_stem = CPP_PACKAGED_EXECUTABLE_BASENAME.lower()
    default_stem = CPP_EXECUTABLE_BASENAME.lower()
    legacy_stem = CPP_EXECUTABLE_LEGACY_BASENAME.lower()
    suffixes = {""}
    if sys.platform == "win32":
        suffixes.add(".exe")

    roots: list[Path] = []
    if not is_frozen_python_app():
        roots.extend(
            [
                CPP_PROJECT_PATH,
                CPP_PROJECT_PATH / "build",
                CPP_PROJECT_PATH / "Release",
                CPP_PROJECT_PATH / "Debug",
                CPP_PROJECT_PATH / "bin",
                CPP_BUILD_ROOT,
                CPP_BUILD_ROOT / "Release",
                CPP_BUILD_ROOT / "Debug",
                CPP_BUILD_ROOT / "bin",
                CPP_BUILD_ROOT / "out",
            ]
        )

        try:
            build_parent = CPP_BUILD_ROOT.parent
        except Exception:
            build_parent = None
        if isinstance(build_parent, Path) and build_parent.is_dir():
            try:
                for extra in sorted(build_parent.glob("binance_cpp*"), reverse=True):
                    roots.extend(
                        [
                            extra,
                            extra / "Release",
                            extra / "Debug",
                            extra / "bin",
                            extra / "out",
                        ]
                    )
            except Exception:
                pass

    roots.extend(_cpp_runtime_search_roots())

    found: list[Path] = []
    seen: set[Path] = set()

    def _remember(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for root in roots:
        for name in candidate_names:
            candidate = root / name
            if candidate.is_file():
                _remember(candidate)

    if not frozen_mode:
        for root in roots:
            if not root.is_dir():
                continue
            try:
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.suffix.lower() not in suffixes:
                        continue
                    if path.name in candidate_names or path.stem.lower() in candidate_stems:
                        _remember(path)
            except (PermissionError, OSError):
                continue
    if not found:
        return None

    def _mtime(path: Path) -> float:
        try:
            return float(path.stat().st_mtime)
        except Exception:
            return 0.0

    def _name_priority(path: Path) -> int:
        stem = path.stem.lower()
        if frozen_mode:
            if stem == packaged_stem:
                return 2
            if stem == default_stem:
                return 1
            return 0
        if stem == default_stem:
            return 3
        if stem == packaged_stem:
            return 2
        if stem == legacy_stem:
            return 1
        return 0

    found.sort(key=lambda path: (_name_priority(path), _mtime(path)), reverse=True)
    return found[0]


def cpp_executable_is_stale(exe_path: Path | None) -> bool:
    if is_frozen_python_app():
        return False
    if exe_path is None or not exe_path.is_file():
        return True
    try:
        exe_mtime = float(exe_path.stat().st_mtime)
    except Exception:
        return True

    source_paths: list[Path] = [
        CPP_PROJECT_PATH / "CMakeLists.txt",
        CPP_PROJECT_PATH / "resources.qrc",
    ]
    src_dir = CPP_PROJECT_PATH / "src"
    if src_dir.is_dir():
        try:
            source_paths.extend(sorted(src_dir.glob("*.cpp")))
            source_paths.extend(sorted(src_dir.glob("*.h")))
        except Exception:
            pass

    latest_source_mtime = 0.0
    for path in source_paths:
        try:
            if not path.is_file():
                continue
            latest_source_mtime = max(latest_source_mtime, float(path.stat().st_mtime))
        except Exception:
            continue

    if latest_source_mtime <= 0.0:
        return False
    return exe_mtime + 0.001 < latest_source_mtime


def read_cmake_cache_value(cache_file: Path, key: str) -> str | None:
    if not cache_file.is_file():
        return None
    needle = f"{key}:"
    try:
        for line in cache_file.read_text(errors="ignore").splitlines():
            if line.startswith(needle):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    value = parts[1].strip()
                    return value or None
    except Exception:
        return None
    return None


def _detect_default_cpp_qt_prefix() -> Path | None:
    discovered: list[Path] = []
    candidates = [
        Path("C:/Qt"),
        Path.home() / "Qt",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        try:
            version_dirs = sorted(
                [entry for entry in base.glob("6.*") if entry.is_dir()],
                key=lambda path: _version_sort_key(path.name),
                reverse=True,
            )
            for version_dir in version_dirs:
                for kit_dir in sorted(version_dir.iterdir(), key=lambda path: path.name.lower(), reverse=True):
                    qt_cmake = kit_dir / "lib" / "cmake" / "Qt6"
                    if qt_cmake.is_dir():
                        try:
                            discovered.append(qt_cmake.resolve())
                        except Exception:
                            discovered.append(qt_cmake)
        except Exception:
            continue
    if not discovered:
        return None
    discovered.sort(key=_qt_prefix_preference_key, reverse=True)
    return discovered[0]


def _normalize_qt_prefix_token(token: str | None) -> str:
    value = str(token or "").strip().strip('"').strip("'")
    if not value:
        return ""
    if "=" in value:
        maybe_path = value.rsplit("=", 1)[-1].strip().strip('"').strip("'")
        if maybe_path:
            value = maybe_path
    return value


def _as_qt6_cmake_dir(path_value: str | Path | None) -> Path | None:
    if path_value is None:
        return None
    try:
        candidate = Path(path_value).resolve()
    except Exception:
        return None
    probes = [candidate, candidate / "lib" / "cmake" / "Qt6"]
    if candidate.name.lower() == "qt6":
        probes.insert(0, candidate)
    for probe in probes:
        try:
            if (probe / "Qt6Config.cmake").is_file():
                return probe.resolve()
        except Exception:
            continue
    return None


def _qt_bin_dirs_from_prefix(path_value: str | Path | None) -> list[Path]:
    qt_dir = _as_qt6_cmake_dir(path_value)
    if qt_dir is None:
        return []
    bin_dirs: list[Path] = []
    seen: set[Path] = set()
    for base in [qt_dir, *qt_dir.parents]:
        candidate = base / "bin"
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        try:
            is_dir = resolved.is_dir()
        except Exception:
            is_dir = False
        if not is_dir or resolved in seen:
            continue
        seen.add(resolved)
        bin_dirs.append(resolved)
    return bin_dirs


def qt_prefix_has_webengine(path_value: str | Path | None) -> bool:
    qt_dir = _as_qt6_cmake_dir(path_value)
    if qt_dir is None:
        return False
    probes = [
        qt_dir.parent / "Qt6WebEngineWidgets" / "Qt6WebEngineWidgetsConfig.cmake",
        qt_dir.parent / "Qt6WebEngineCore" / "Qt6WebEngineCoreConfig.cmake",
    ]
    has_config = False
    for probe in probes:
        try:
            if probe.is_file():
                has_config = True
                break
        except Exception:
            continue
    if not has_config:
        return False
    for bin_dir in _qt_bin_dirs_from_prefix(path_value):
        try:
            if (bin_dir / "QtWebEngineProcess.exe").is_file():
                return True
        except Exception:
            continue
        for dll_name in ("Qt6WebEngineCore.dll", "Qt6WebEngineWidgets.dll", "Qt6WebEngineWidgetsd.dll"):
            try:
                if (bin_dir / dll_name).is_file():
                    return True
            except Exception:
                continue
    return False


def qt_prefix_has_websockets(path_value: str | Path | None) -> bool:
    qt_dir = _as_qt6_cmake_dir(path_value)
    if qt_dir is None:
        return False
    try:
        config_ok = (qt_dir.parent / "Qt6WebSockets" / "Qt6WebSocketsConfig.cmake").is_file()
    except Exception:
        config_ok = False
    if not config_ok:
        return False
    for bin_dir in _qt_bin_dirs_from_prefix(path_value):
        for dll_name in ("Qt6WebSockets.dll", "Qt6WebSocketsd.dll"):
            try:
                if (bin_dir / dll_name).is_file():
                    return True
            except Exception:
                continue
    return False


def _qt_prefix_preference_key(path_value: str | Path | None) -> tuple[int, tuple[int, ...]]:
    has_webengine = 1 if qt_prefix_has_webengine(path_value) else 0
    detected = _cpp_qt_version_from_path(str(path_value or ""))
    return has_webengine, _version_sort_key(detected or "")


def _best_qt_prefix_from_env(env_value: str | None) -> Path | None:
    raw = str(env_value or "").strip()
    if not raw:
        return None
    candidates: list[Path] = []
    for token in raw.split(os.pathsep):
        normalized = _normalize_qt_prefix_token(token)
        if not normalized:
            continue
        qt_dir = _as_qt6_cmake_dir(normalized)
        if qt_dir is not None:
            candidates.append(qt_dir)
    if not candidates:
        return None
    candidates.sort(key=_qt_prefix_preference_key, reverse=True)
    return candidates[0]


def resolve_cpp_qt_prefix_for_code_tab() -> str | None:
    env_prefix_raw = os.environ.get("QT_CMAKE_PREFIX_PATH") or os.environ.get("CMAKE_PREFIX_PATH")
    env_qt_prefix = _best_qt_prefix_from_env(env_prefix_raw)
    detected = _detect_default_cpp_qt_prefix()
    if env_qt_prefix is not None and detected is not None:
        if _qt_prefix_preference_key(detected) > _qt_prefix_preference_key(env_qt_prefix):
            return str(detected)
        return str(env_qt_prefix)
    if env_qt_prefix is not None:
        return str(env_qt_prefix)
    if detected is not None:
        return str(detected)

    cached_qt_dir = read_cmake_cache_value(CPP_BUILD_ROOT / "CMakeCache.txt", "Qt6_DIR")
    if cached_qt_dir:
        cached_path = _as_qt6_cmake_dir(cached_qt_dir)
        if cached_path is not None:
            return str(cached_path)
    return None


def discover_cpp_qt_bin_dirs_for_code_tab() -> list[Path]:
    prefixes: list[Path] = []
    resolved_prefix = resolve_cpp_qt_prefix_for_code_tab()
    if resolved_prefix:
        qt_dir = _as_qt6_cmake_dir(resolved_prefix)
        if qt_dir is not None:
            prefixes.append(qt_dir)

    detected = _detect_default_cpp_qt_prefix()
    if detected is not None:
        prefixes.append(detected)

    cached_qt_dir = read_cmake_cache_value(CPP_BUILD_ROOT / "CMakeCache.txt", "Qt6_DIR")
    if cached_qt_dir:
        prefixes.append(Path(cached_qt_dir))

    bin_dirs: list[Path] = []
    for prefix in prefixes:
        try:
            prefix_resolved = prefix.resolve()
        except Exception:
            continue
        for base in [prefix_resolved] + list(prefix_resolved.parents):
            candidate = base / "bin"
            if not candidate.is_dir():
                continue
            if (candidate / "Qt6Core.dll").is_file() or (candidate / "Qt6Widgets.dll").is_file():
                try:
                    bin_dirs.append(candidate.resolve())
                except Exception:
                    bin_dirs.append(candidate)
                break

    build_bin = CPP_BUILD_ROOT / "bin"
    if build_bin.is_dir():
        bin_dirs.append(build_bin.resolve())

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in bin_dirs:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique
