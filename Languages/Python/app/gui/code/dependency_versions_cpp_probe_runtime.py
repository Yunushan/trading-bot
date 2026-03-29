from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from pathlib import Path

from . import code_language_launch, code_language_runtime, dependency_versions_cpp_shared_runtime as shared


def _cpp_dependency_file_exists(path_value: str | None) -> bool:
    relative_path = str(path_value or "").strip()
    if not relative_path:
        return False
    try:
        resolved = (shared._BASE_PROJECT_PATH / relative_path).resolve()
    except Exception:
        return False
    return resolved.is_file()


def _cpp_source_fingerprint(path_value: str | None) -> str:
    relative_path = str(path_value or "").strip()
    if not relative_path:
        return "Missing"
    try:
        resolved = (shared._BASE_PROJECT_PATH / relative_path).resolve()
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
            ok, output = code_language_launch.run_command_capture_hidden(
                [str(qmake_path), "-query", "QT_VERSION"]
            )
            if not ok:
                continue
            value = str(output or "").strip().splitlines()
            if not value:
                continue
            detected = shared._extract_semver_from_text(value[-1].strip())
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
    return sorted({value for value in versions}, key=shared._version_sort_key)


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
    cache_value = code_language_runtime.read_cmake_cache_value(
        shared.CPP_BUILD_ROOT / "CMakeCache.txt",
        "Qt6Network_DIR",
    )
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
        shared.CPP_BUILD_ROOT / "CMakeCache.txt",
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
            if (
                root
                / "lib"
                / "cmake"
                / "Qt6WebEngineWidgets"
                / "Qt6WebEngineWidgetsConfig.cmake"
            ).is_file():
                return True
        except Exception:
            continue
    return False


def _cpp_qt_websockets_available() -> bool:
    cache_value = code_language_runtime.read_cmake_cache_value(
        shared.CPP_BUILD_ROOT / "CMakeCache.txt",
        "Qt6WebSockets_DIR",
    )
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
    _add(shared._BASE_PROJECT_PATH / ".vcpkg")
    _add(Path("C:/vcpkg"))
    _add(Path.home() / "vcpkg")
    return roots


def _cpp_load_vcpkg_status_versions() -> dict[str, str]:
    now = time.time()
    if now - float(shared._CPP_VCPKG_STATUS_CACHE[1] or 0.0) < 120:
        return dict(shared._CPP_VCPKG_STATUS_CACHE[0])

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
            if existing is None or shared._version_sort_key(version_value) >= shared._version_sort_key(existing):
                versions[package] = version_value
    shared._CPP_VCPKG_STATUS_CACHE = (dict(versions), now)
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
    now = time.time()
    if now - float(shared._CPP_INCLUDE_DIR_CACHE[1] or 0.0) < 120:
        return list(shared._CPP_INCLUDE_DIR_CACHE[0])

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

    for base in (shared.CPP_BUILD_ROOT, shared.CPP_PROJECT_PATH, shared._BASE_PROJECT_PATH):
        try:
            for include_path in base.glob("vcpkg_installed/*/include"):
                _add(include_path)
        except Exception:
            continue

    try:
        build_parent = shared.CPP_BUILD_ROOT.parent
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
    shared._CPP_INCLUDE_DIR_CACHE = (list(include_dirs), now)
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
