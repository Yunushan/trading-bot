from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from . import code_language_launch, code_language_runtime
from .code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    CPP_BUILD_ROOT,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    CPP_PROJECT_PATH,
)

_CPP_AUTO_SETUP_LOCK = threading.Lock()
_LATEST_CPP_VERSION_CACHE: dict[str, tuple[str, float]] = {}
_CPP_INCLUDE_DIR_CACHE: tuple[list[Path], float] = ([], 0.0)
_CPP_INSTALLED_VALUE_CACHE: dict[str, tuple[str | None, float]] = {}
_CPP_VCPKG_STATUS_CACHE: tuple[dict[str, str], float] = ({}, 0.0)
_CPP_PINNED_QT_VERSION_CACHE: dict[str, str] = {}


def _runtime():
    from . import dependency_versions_runtime as runtime

    return runtime


def _normalize_installed_version_text(value) -> str | None:
    return _runtime()._normalize_installed_version_text(value)


def _version_sort_key(version_text: str | None) -> tuple[int, ...]:
    return _runtime()._version_sort_key(version_text)


def _pick_highest_version(candidates: list[str]) -> str | None:
    return _runtime()._pick_highest_version(candidates)


def _extract_semver_from_text(value: str | None) -> str | None:
    return _runtime()._extract_semver_from_text(value)


def _http_get_text(url: str, timeout: float = 8.0) -> str | None:
    return _runtime()._http_get_text(url, timeout=timeout)


def _http_get_json(url: str, timeout: float = 8.0):
    return _runtime()._http_get_json(url, timeout=timeout)


def _cpp_dependency_file_exists(path_value: str | None) -> bool:
    relative_path = str(path_value or "").strip()
    if not relative_path:
        return False
    try:
        resolved = (_BASE_PROJECT_PATH / relative_path).resolve()
    except Exception:
        return False
    return resolved.is_file()


def _cpp_source_fingerprint(path_value: str | None) -> str:
    relative_path = str(path_value or "").strip()
    if not relative_path:
        return "Missing"
    try:
        resolved = (_BASE_PROJECT_PATH / relative_path).resolve()
    except Exception:
        return "Missing"
    if not resolved.is_file():
        return "Missing"
    try:
        digest = hashlib.sha1(resolved.read_bytes()).hexdigest()[:8]
    except Exception:
        return "Source"
    return f"src-{digest}"


def _cpp_qt_prefix_tokens() -> list[Path]:
    raw_prefix = str(code_language_runtime.resolve_cpp_qt_prefix_for_code_tab() or "").strip()
    if not raw_prefix:
        return []
    tokens = [token.strip() for token in raw_prefix.split(os.pathsep) if token.strip()]
    paths: list[Path] = []
    for token in tokens:
        try:
            paths.append(Path(token).resolve())
        except Exception:
            continue
    return paths


def _cpp_qt_version_from_path(path_value: str | None) -> str | None:
    text = str(path_value or "")
    for match in re.findall(r"(?<!\d)(6\.\d+(?:\.\d+)?)(?!\d)", text):
        if match:
            return match
    return None


def _cpp_qt_version_from_qmake() -> str | None:
    qmake_names = ["qmake"]
    if sys.platform == "win32":
        qmake_names.insert(0, "qmake.exe")
    for bin_dir in code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab():
        for executable in qmake_names:
            qmake_path = bin_dir / executable
            if not qmake_path.is_file():
                continue
            ok, output = code_language_launch.run_command_capture_hidden([str(qmake_path), "-query", "QT_VERSION"])
            if not ok:
                continue
            value = str(output or "").strip().splitlines()
            if not value:
                continue
            detected = _extract_semver_from_text(value[-1].strip())
            if detected:
                return detected
    return None


def _cpp_qt_version_display() -> str:
    qmake_version = _cpp_qt_version_from_qmake()
    if qmake_version:
        return qmake_version
    for prefix in _cpp_qt_prefix_tokens():
        detected = _cpp_qt_version_from_path(str(prefix))
        if detected:
            return detected
    return "Not detected"


def _cpp_qt_local_versions() -> list[str]:
    versions: list[str] = []
    roots = [Path("C:/Qt"), Path.home() / "Qt"]
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                detected = _cpp_qt_version_from_path(entry.name)
                if detected:
                    versions.append(detected)
        except Exception:
            continue
    return sorted({value for value in versions}, key=_version_sort_key)


def _cpp_latest_qt_version_from_download() -> str | None:
    base_url = "https://download.qt.io/official_releases/qt/"
    listing = _http_get_text(base_url, timeout=8.0)
    if not listing:
        return None
    minor_versions = re.findall(r'href="(6\.\d+)/"', listing)
    selected_minor = _pick_highest_version(minor_versions)
    if not selected_minor:
        return None
    minor_listing = _http_get_text(f"{base_url}{selected_minor}/", timeout=8.0)
    if not minor_listing:
        return selected_minor
    patch_versions = re.findall(rf'href="({re.escape(selected_minor)}\.\d+)/"', minor_listing)
    return _pick_highest_version(patch_versions) or selected_minor


def _cpp_latest_local_qt_version() -> str | None:
    return _pick_highest_version(_cpp_qt_local_versions())


def _cpp_latest_qt_version() -> str | None:
    online_version = _cpp_latest_qt_version_from_download()
    if online_version:
        return online_version
    return _cpp_latest_local_qt_version()


def _cpp_qt_kit_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None):
        if path is None:
            return
        try:
            resolved = path.resolve()
        except Exception:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    for prefix in _cpp_qt_prefix_tokens():
        current = prefix
        for _ in range(4):
            if (current / "include").is_dir() and (current / "bin").is_dir():
                _add(current)
                break
            if current.parent == current:
                break
            current = current.parent
    for bin_dir in code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab():
        _add(bin_dir.parent)
    return roots


def _cpp_qt_network_available() -> bool:
    cache_value = code_language_runtime.read_cmake_cache_value(CPP_BUILD_ROOT / "CMakeCache.txt", "Qt6Network_DIR")
    if cache_value:
        return True
    for bin_dir in code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab():
        for dll_name in ("Qt6Network.dll", "Qt6Networkd.dll"):
            try:
                if (bin_dir / dll_name).is_file():
                    return True
            except Exception:
                continue
    for root in _cpp_qt_kit_roots():
        try:
            if (root / "include" / "QtNetwork").is_dir():
                return True
        except Exception:
            continue
    return False


def _cpp_qt_webengine_available() -> bool:
    cache_value = code_language_runtime.read_cmake_cache_value(
        CPP_BUILD_ROOT / "CMakeCache.txt",
        "Qt6WebEngineWidgets_DIR",
    )
    if cache_value and str(cache_value).strip().upper() != "QT6WEBENGINEWIDGETS_DIR-NOTFOUND":
        try:
            cache_path = Path(str(cache_value)).resolve()
        except Exception:
            cache_path = Path(str(cache_value))
        try:
            if cache_path.is_file():
                return True
            if (cache_path / "Qt6WebEngineWidgetsConfig.cmake").is_file():
                return True
        except Exception:
            pass
    for bin_dir in code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab():
        for exe_name in ("QtWebEngineProcess.exe", "QtWebEngineProcess"):
            try:
                if (bin_dir / exe_name).is_file():
                    return True
            except Exception:
                continue
        for dll_name in ("Qt6WebEngineWidgets.dll", "Qt6WebEngineWidgetsd.dll"):
            try:
                if (bin_dir / dll_name).is_file():
                    return True
            except Exception:
                continue
    for root in _cpp_qt_kit_roots():
        try:
            if (root / "include" / "QtWebEngineWidgets").is_dir():
                return True
        except Exception:
            continue
        try:
            if (root / "lib" / "cmake" / "Qt6WebEngineWidgets" / "Qt6WebEngineWidgetsConfig.cmake").is_file():
                return True
        except Exception:
            continue
    return False


def _cpp_qt_websockets_available() -> bool:
    cache_value = code_language_runtime.read_cmake_cache_value(CPP_BUILD_ROOT / "CMakeCache.txt", "Qt6WebSockets_DIR")
    if cache_value:
        return True
    for bin_dir in code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab():
        for dll_name in ("Qt6WebSockets.dll", "Qt6WebSocketsd.dll"):
            try:
                if (bin_dir / dll_name).is_file():
                    return True
            except Exception:
                continue
    for root in _cpp_qt_kit_roots():
        try:
            if (root / "include" / "QtWebSockets").is_dir():
                return True
        except Exception:
            continue
    return False


def _cpp_candidate_vcpkg_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path_value: Path | str | None):
        if path_value is None:
            return
        try:
            resolved = Path(path_value).resolve()
        except Exception:
            return
        if resolved in seen or not resolved.is_dir():
            return
        seen.add(resolved)
        roots.append(resolved)

    env_root = str(os.environ.get("VCPKG_ROOT") or "").strip()
    if env_root:
        _add(env_root)
    _add(_BASE_PROJECT_PATH / ".vcpkg")
    _add(Path("C:/vcpkg"))
    _add(Path.home() / "vcpkg")
    return roots


def _cpp_load_vcpkg_status_versions() -> dict[str, str]:
    global _CPP_VCPKG_STATUS_CACHE
    now = time.time()
    if now - float(_CPP_VCPKG_STATUS_CACHE[1] or 0.0) < 120:
        return dict(_CPP_VCPKG_STATUS_CACHE[0])

    versions: dict[str, str] = {}
    for root in _cpp_candidate_vcpkg_roots():
        status_file = root / "installed" / "vcpkg" / "status"
        if not status_file.is_file():
            continue
        try:
            content = status_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for block in re.split(r"\r?\n\r?\n", content):
            if not block.strip():
                continue
            package = ""
            feature = ""
            version_value = ""
            status_value = ""
            for line in block.splitlines():
                if line.startswith("Package: "):
                    package = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Feature: "):
                    feature = line.split(":", 1)[1].strip().lower()
                elif line.startswith("Version: "):
                    version_value = line.split(":", 1)[1].strip()
                elif line.startswith("Status: "):
                    status_value = line.split(":", 1)[1].strip().lower()
            if not package or "install ok installed" not in status_value:
                continue
            if feature and feature not in {"core"}:
                continue
            if not version_value:
                continue
            existing = versions.get(package)
            if existing is None or _version_sort_key(version_value) >= _version_sort_key(existing):
                versions[package] = version_value
    _CPP_VCPKG_STATUS_CACHE = (dict(versions), now)
    return versions


def _cpp_vcpkg_installed_version(*package_names: str) -> str | None:
    versions = _cpp_load_vcpkg_status_versions()
    for name in package_names:
        key = str(name or "").strip().lower()
        if not key:
            continue
        value = versions.get(key)
        if value:
            return value
    return None


def _cpp_candidate_include_dirs() -> list[Path]:
    global _CPP_INCLUDE_DIR_CACHE
    now = time.time()
    if now - float(_CPP_INCLUDE_DIR_CACHE[1] or 0.0) < 120:
        return list(_CPP_INCLUDE_DIR_CACHE[0])

    include_dirs: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None):
        if path is None:
            return
        try:
            resolved = path.resolve()
        except Exception:
            return
        if resolved in seen or not resolved.is_dir():
            return
        seen.add(resolved)
        include_dirs.append(resolved)

    for base in (CPP_BUILD_ROOT, CPP_PROJECT_PATH, _BASE_PROJECT_PATH):
        try:
            for include_path in base.glob("vcpkg_installed/*/include"):
                _add(include_path)
        except Exception:
            continue

    try:
        build_parent = CPP_BUILD_ROOT.parent
    except Exception:
        build_parent = None
    if isinstance(build_parent, Path) and build_parent.is_dir():
        try:
            for build_dir in build_parent.glob("binance_cpp*"):
                for include_path in build_dir.glob("vcpkg_installed/*/include"):
                    _add(include_path)
        except Exception:
            pass

    for root_path in _cpp_candidate_vcpkg_roots():
        try:
            for include_path in root_path.glob("installed/*/include"):
                _add(include_path)
        except Exception:
            continue

    for qt_root in _cpp_qt_kit_roots():
        _add(qt_root / "include")
    _CPP_INCLUDE_DIR_CACHE = (list(include_dirs), now)
    return include_dirs


def _cpp_find_header(*relative_candidates: str) -> Path | None:
    for include_dir in _cpp_candidate_include_dirs():
        for relative in relative_candidates:
            rel = str(relative or "").strip().replace("\\", "/")
            if not rel:
                continue
            candidate = include_dir / rel
            if candidate.is_file():
                return candidate
    return None


def _cpp_read_text_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _cpp_extract_macro_str(text: str, macro_name: str) -> str | None:
    if not text or not macro_name:
        return None
    pattern = rf'^\s*#\s*define\s+{re.escape(macro_name)}\s+"([^"]+)"'
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    return str(match.group(1) or "").strip() or None


def _cpp_extract_macro_int(text: str, macro_name: str) -> int | None:
    if not text or not macro_name:
        return None
    pattern = rf"^\s*#\s*define\s+{re.escape(macro_name)}\s+(\d+)"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _cpp_detect_eigen_version() -> str | None:
    vcpkg_version = _cpp_vcpkg_installed_version("eigen3")
    if vcpkg_version:
        return vcpkg_version
    header = _cpp_find_header("eigen3/Eigen/src/Core/util/Macros.h", "Eigen/src/Core/util/Macros.h")
    text = _cpp_read_text_file(header)
    world = _cpp_extract_macro_int(text, "EIGEN_WORLD_VERSION")
    major = _cpp_extract_macro_int(text, "EIGEN_MAJOR_VERSION")
    minor = _cpp_extract_macro_int(text, "EIGEN_MINOR_VERSION")
    if world is None or major is None or minor is None:
        return None
    return f"{world}.{major}.{minor}"


def _cpp_detect_xtensor_version() -> str | None:
    vcpkg_version = _cpp_vcpkg_installed_version("xtensor")
    if vcpkg_version:
        return vcpkg_version
    header = _cpp_find_header("xtensor/core/xtensor_config.hpp", "xtensor/xtensor_config.hpp")
    text = _cpp_read_text_file(header)
    major = _cpp_extract_macro_int(text, "XTENSOR_VERSION_MAJOR")
    minor = _cpp_extract_macro_int(text, "XTENSOR_VERSION_MINOR")
    patch = _cpp_extract_macro_int(text, "XTENSOR_VERSION_PATCH")
    if major is not None and minor is not None and patch is not None:
        return f"{major}.{minor}.{patch}"
    return _cpp_extract_macro_str(text, "XTENSOR_VERSION")


def _cpp_detect_talib_version() -> str | None:
    vcpkg_version = _cpp_vcpkg_installed_version("talib")
    if vcpkg_version:
        return vcpkg_version
    header = _cpp_find_header("ta-lib/ta_defs.h", "ta_defs.h")
    text = _cpp_read_text_file(header)
    version = _cpp_extract_macro_str(text, "TA_LIB_VERSION_STR")
    if version:
        return version
    major = _cpp_extract_macro_int(text, "TA_LIB_VERSION_MAJOR")
    minor = _cpp_extract_macro_int(text, "TA_LIB_VERSION_MINOR")
    patch = _cpp_extract_macro_int(text, "TA_LIB_VERSION_PATCH")
    if major is not None and minor is not None and patch is not None:
        return f"{major}.{minor}.{patch}"
    return None


def _cpp_detect_cpr_version() -> str | None:
    vcpkg_version = _cpp_vcpkg_installed_version("cpr")
    if vcpkg_version:
        return vcpkg_version
    header = _cpp_find_header("cpr/cprver.h")
    text = _cpp_read_text_file(header)
    version = _cpp_extract_macro_str(text, "CPR_VERSION")
    if version:
        return version
    major = _cpp_extract_macro_int(text, "CPR_VERSION_MAJOR")
    minor = _cpp_extract_macro_int(text, "CPR_VERSION_MINOR")
    patch = _cpp_extract_macro_int(text, "CPR_VERSION_PATCH")
    if major is not None and minor is not None and patch is not None:
        return f"{major}.{minor}.{patch}"
    return None


def _cpp_detect_libcurl_version() -> str | None:
    vcpkg_version = _cpp_vcpkg_installed_version("curl")
    if vcpkg_version:
        return vcpkg_version
    header = _cpp_find_header("curl/curlver.h")
    text = _cpp_read_text_file(header)
    header_version = _cpp_extract_macro_str(text, "LIBCURL_VERSION")
    if header_version:
        return header_version
    ok, output = code_language_launch.run_command_capture_hidden(["curl", "--version"])
    if not ok:
        return None
    text_output = str(output or "")
    for pattern in (r"libcurl/([0-9]+(?:\.[0-9]+){1,3})", r"curl\s+([0-9]+(?:\.[0-9]+){1,3})"):
        match = re.search(pattern, text_output)
        if match:
            return str(match.group(1))
    return None


def _cpp_latest_from_github_release(owner: str, repo: str) -> str | None:
    if not owner or not repo:
        return None
    payload = _http_get_json(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", timeout=8.0)
    if not isinstance(payload, dict):
        return None
    candidates = [
        _extract_semver_from_text(payload.get("tag_name")),
        _extract_semver_from_text(payload.get("name")),
    ]
    return _pick_highest_version([candidate for candidate in candidates if candidate])


def _cpp_latest_from_github_tags(owner: str, repo: str) -> str | None:
    if not owner or not repo:
        return None
    payload = _http_get_json(f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=20", timeout=8.0)
    if not isinstance(payload, list):
        return None
    versions: list[str] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        detected = _extract_semver_from_text(row.get("name"))
        if detected:
            versions.append(detected)
    return _pick_highest_version(versions)


def _cpp_latest_eigen_version() -> str | None:
    payload = _http_get_json(
        "https://gitlab.com/api/v4/projects/libeigen%2Feigen/repository/tags?per_page=20",
        timeout=8.0,
    )
    if not isinstance(payload, list):
        return None
    versions: list[str] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        detected = _extract_semver_from_text(row.get("name"))
        if detected:
            versions.append(detected)
    return _pick_highest_version(versions)


def _cpp_latest_xtensor_version() -> str | None:
    return _cpp_latest_from_github_release("xtensor-stack", "xtensor") or _cpp_latest_from_github_tags(
        "xtensor-stack",
        "xtensor",
    )


def _cpp_latest_talib_version() -> str | None:
    return _cpp_latest_from_github_release("TA-Lib", "ta-lib")


def _cpp_latest_cpr_version() -> str | None:
    return _cpp_latest_from_github_release("libcpr", "cpr")


def _cpp_latest_libcurl_version() -> str | None:
    return _cpp_latest_from_github_release("curl", "curl")


def _cpp_latest_version_for_key(key: str | None) -> str | None:
    cache_key = str(key or "").strip().lower()
    if not cache_key:
        return None
    now = time.time()
    cached_entry = _LATEST_CPP_VERSION_CACHE.get(cache_key)
    if isinstance(cached_entry, tuple) and len(cached_entry) == 2:
        cached_value, cached_at = cached_entry
        try:
            if now - float(cached_at) < 1800:
                return str(cached_value or "").strip() or None
        except Exception:
            pass

    loaders = {
        "qt6": _cpp_latest_qt_version,
        "eigen": _cpp_latest_eigen_version,
        "xtensor": _cpp_latest_xtensor_version,
        "ta-lib": _cpp_latest_talib_version,
        "libcurl": _cpp_latest_libcurl_version,
        "cpr": _cpp_latest_cpr_version,
    }
    loader = loaders.get(cache_key)
    if loader is None:
        return None
    value = loader()
    if value:
        _LATEST_CPP_VERSION_CACHE[cache_key] = (value, now)
    return value


def _cpp_cached_installed_value(cache_key: str, resolver, ttl_sec: float = 20.0) -> str | None:
    now = time.time()
    entry = _CPP_INSTALLED_VALUE_CACHE.get(cache_key)
    if isinstance(entry, tuple) and len(entry) == 2:
        cached_value, cached_at = entry
        try:
            if now - float(cached_at) < max(1.0, float(ttl_sec)):
                return cached_value
        except Exception:
            pass
    try:
        resolved_value = resolver()
    except Exception:
        resolved_value = None
    _CPP_INSTALLED_VALUE_CACHE[cache_key] = (resolved_value, now)
    return resolved_value


def _cpp_custom_installed_value(target: dict[str, str]) -> str | None:
    custom = str(target.get("custom") or "").strip().lower()
    cache_key = f"{custom}:{str(target.get('path') or '').strip()}"

    def _resolve():
        packaged_value = code_language_runtime.cpp_packaged_installed_value(target)
        if custom == "cpp_file_version":
            packaged_semver = _extract_semver_from_text(str(packaged_value or ""))
            if packaged_semver:
                return packaged_semver
            cpp_release_tag, _ = code_language_runtime.cpp_runtime_release_snapshot()
            if cpp_release_tag:
                return cpp_release_tag
            py_release_tag = code_language_runtime.python_runtime_release_tag()
            if py_release_tag:
                return py_release_tag
            if packaged_value:
                normalized_packaged = _normalize_installed_version_text(packaged_value) or str(packaged_value).strip()
                lowered = normalized_packaged.lower()
                if normalized_packaged and lowered not in {"installed", "active"} and not lowered.startswith("src-"):
                    return normalized_packaged
        elif packaged_value:
            return packaged_value

        if custom == "cpp_qt":
            return _cpp_qt_version_display()
        if custom == "cpp_qt_network":
            qt_version = _cpp_qt_version_display()
            return qt_version if _cpp_qt_network_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_qt_webengine":
            qt_version = _cpp_qt_version_display()
            return qt_version if _cpp_qt_webengine_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_qt_websockets":
            qt_version = _cpp_qt_version_display()
            return qt_version if _cpp_qt_websockets_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_file_version":
            fingerprint = _cpp_source_fingerprint(target.get("path"))
            return "Unknown" if str(fingerprint).strip().lower() == "missing" else fingerprint
        if custom == "cpp_eigen":
            return _cpp_detect_eigen_version() or "Not installed"
        if custom == "cpp_xtensor":
            return _cpp_detect_xtensor_version() or "Not installed"
        if custom == "cpp_talib":
            return _cpp_detect_talib_version() or "Not installed"
        if custom == "cpp_libcurl":
            return _cpp_detect_libcurl_version() or "Not installed"
        if custom == "cpp_cpr":
            return _cpp_detect_cpr_version() or "Not installed"
        return None

    return _cpp_cached_installed_value(cache_key, _resolve, ttl_sec=20.0)


def _cpp_version_is_installed_marker(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    return normalized not in {"not installed", "not detected", "missing", "unknown", "disabled"}


def _cpp_custom_latest_value(target: dict[str, str], installed_value: str) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    latest_key = str(target.get("latest_key") or "").strip().lower()
    if custom == "cpp_file_version":
        return installed_value or "Unknown"
    if latest_key:
        latest_resolved = _cpp_latest_version_for_key(latest_key)
        if latest_resolved:
            return latest_resolved
    latest_text = str(target.get("latest") or "").strip()
    if latest_text:
        return latest_text
    return installed_value or "Unknown"


def _cpp_custom_usage_value(target: dict[str, str]) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    if code_language_runtime.cpp_packaged_runtime_exe() is not None:
        return "Active"
    if custom == "cpp_file_version":
        return "Active" if _cpp_dependency_file_exists(target.get("path")) else "Passive"
    installed_value = _cpp_custom_installed_value(target)
    return "Active" if _cpp_version_is_installed_marker(installed_value) else "Passive"


def _cpp_pinned_qt_version() -> str:
    cached_value = str(_CPP_PINNED_QT_VERSION_CACHE.get("value") or "").strip()
    if cached_value:
        return cached_value

    default_value = "6.10.2"
    cmake_path = CPP_PROJECT_PATH / "CMakeLists.txt"
    try:
        text = cmake_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        _CPP_PINNED_QT_VERSION_CACHE["value"] = default_value
        return default_value

    match = re.search(r'set\s*\(\s*TB_QT_VERSION\s+"([^"]+)"', text, flags=re.IGNORECASE)
    if not match:
        _CPP_PINNED_QT_VERSION_CACHE["value"] = default_value
        return default_value

    detected = _extract_semver_from_text(match.group(1))
    value = detected or default_value
    _CPP_PINNED_QT_VERSION_CACHE["value"] = value
    return value


def _cpp_target_requires_pinned_qt(target: dict[str, str]) -> bool:
    custom = str(target.get("custom") or "").strip().lower()
    return custom in {
        "cpp_qt",
        "cpp_qt_network",
        "cpp_qt_webengine",
        "cpp_qt_websockets",
    }


def _cpp_target_meets_requirement(target: dict[str, str], installed_value: str | None) -> bool:
    installed = str(installed_value or "").strip()
    if _cpp_target_requires_pinned_qt(target):
        pinned_qt = _extract_semver_from_text(_cpp_pinned_qt_version())
        installed_qt = _extract_semver_from_text(installed)
        if not pinned_qt or not installed_qt:
            return False
        return installed_qt == pinned_qt
    return _cpp_version_is_installed_marker(installed)


def _cpp_env_dependency_targets(targets: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    source = targets if targets is not None else _CPP_DEPENDENCY_VERSION_TARGETS
    resolved: list[dict[str, str]] = []
    for target in source or []:
        if not isinstance(target, dict):
            continue
        custom = str(target.get("custom") or "").strip().lower()
        if custom.startswith("cpp_"):
            resolved.append(target)
    return resolved


def _cpp_missing_dependency_labels(targets: list[dict[str, str]] | None = None) -> list[str]:
    missing: list[str] = []
    _reset_cpp_dependency_caches()
    for target in _cpp_env_dependency_targets(targets):
        label = str(target.get("label") or "").strip()
        custom = str(target.get("custom") or "").strip().lower()
        if not label:
            continue
        installed = str(_cpp_custom_installed_value(target) or "").strip()
        if custom == "cpp_file_version":
            if _cpp_dependency_file_exists(target.get("path")) and installed.lower() != "unknown":
                continue
            missing.append(label)
            continue
        if not _cpp_target_meets_requirement(target, installed):
            missing.append(label)
    return missing


def _cpp_dependency_installer_command() -> tuple[list[str], Path] | tuple[None, None]:
    tools_dir = CPP_PROJECT_PATH / "tools"
    if sys.platform == "win32":
        script_path = tools_dir / "install_cpp_dependencies.ps1"
        shell_exe = shutil.which("pwsh") or shutil.which("powershell")
        if not script_path.is_file() or not shell_exe:
            return None, None
        command = [
            shell_exe,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
        return command, _BASE_PROJECT_PATH

    script_path = tools_dir / "install_cpp_dependencies.sh"
    bash_exe = shutil.which("bash")
    if not script_path.is_file() or not bash_exe:
        return None, None
    return [bash_exe, str(script_path)], _BASE_PROJECT_PATH


def _cpp_run_dependency_installer() -> tuple[bool, str]:
    command, cwd = _cpp_dependency_installer_command()
    if not command or cwd is None:
        if sys.platform == "win32":
            return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.ps1"
        return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.sh"
    with _CPP_AUTO_SETUP_LOCK:
        return code_language_launch.run_command_capture_hidden(command, cwd=cwd)


def _reset_cpp_dependency_caches() -> None:
    _CPP_INSTALLED_VALUE_CACHE.clear()
    global _CPP_INCLUDE_DIR_CACHE
    _CPP_INCLUDE_DIR_CACHE = ([], 0.0)
    global _CPP_VCPKG_STATUS_CACHE
    _CPP_VCPKG_STATUS_CACHE = ({}, 0.0)
    _CPP_PINNED_QT_VERSION_CACHE.clear()
    code_language_runtime.reset_cpp_runtime_caches()
