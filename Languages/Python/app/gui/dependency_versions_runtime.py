from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib
import importlib.metadata as importlib_metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.request
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.binance_wrapper import _normalize_connector_choice as _normalize_connector_backend
from app.gui import code_language_launch, code_language_runtime
from app.gui.code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    CPP_BUILD_ROOT,
    CPP_CODE_LANGUAGE_KEY,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    CPP_PROJECT_PATH,
    DEFAULT_DEPENDENCY_VERSION_TARGETS as _DEFAULT_DEPENDENCY_VERSION_TARGETS,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    REQUIREMENTS_PATHS as _REQUIREMENTS_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_PROJECT_PATH,
    _rust_dependency_targets_for_config,
)

_RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC = 180.0
_RUSTUP_WINDOWS_INSTALLER_URL_BASE = "https://win.rustup.rs"
_RUSTUP_UNIX_INSTALLER_URL = "https://sh.rustup.rs"
_RUST_AUTO_INSTALL_LOCK = threading.Lock()
_CPP_AUTO_SETUP_LOCK = threading.Lock()

_CONNECTOR_DEPENDENCY_KEYS = {
    "python-binance",
    "binance-connector",
    "ccxt",
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
}

_DEPENDENCY_MODULE_ALIASES = {
    "python-binance": ("binance",),
    "binance-connector": ("binance",),
    "ccxt": ("ccxt",),
    "pyqt6": ("PyQt6",),
    "pyqt6-qt6": ("PyQt6",),
    "pyqt6-webengine": ("PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore"),
    "numba": ("numba",),
    "llvmlite": ("llvmlite",),
    "numpy": ("numpy",),
    "pandas": ("pandas",),
    "pandas-ta": ("pandas_ta",),
    "requests": ("requests",),
    "binance-sdk-derivatives-trading-usds-futures": ("binance_sdk_derivatives_trading_usds_futures",),
    "binance-sdk-derivatives-trading-coin-futures": ("binance_sdk_derivatives_trading_coin_futures",),
    "binance-sdk-spot": ("binance_sdk_spot",),
}

_DEPENDENCY_USAGE_ACTIVE_COLOR = "#16a34a"
_DEPENDENCY_USAGE_PASSIVE_COLOR = "#dc2626"
_DEPENDENCY_USAGE_PENDING_COLOR = "#d97706"
_DEPENDENCY_USAGE_UNKNOWN_COLOR = "#64748b"
_DEPENDENCY_USAGE_POLL_INTERVAL_MS = 1500
_CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC = 300.0


def _normalize_dependency_key(value: str | None) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _normalize_dependency_usage_text(usage: str | None) -> str:
    text = str(usage or "").strip().lower()
    if text == "active":
        return "Active"
    if text == "passive":
        return "Passive"
    if text == "checking...":
        return "Checking..."
    if text == "unknown":
        return "Unknown"
    if not text:
        return "Passive"
    return str(usage).strip()


def _dependency_usage_color(usage_text: str) -> str:
    normalized = str(usage_text or "").strip().lower()
    if normalized == "active":
        return _DEPENDENCY_USAGE_ACTIVE_COLOR
    if normalized == "passive":
        return _DEPENDENCY_USAGE_PASSIVE_COLOR
    if normalized == "checking...":
        return _DEPENDENCY_USAGE_PENDING_COLOR
    return _DEPENDENCY_USAGE_UNKNOWN_COLOR


def _set_dependency_usage_widget(widget: QtWidgets.QLabel | None, usage: str | None) -> None:
    if widget is None:
        return
    usage_text = _normalize_dependency_usage_text(usage)
    usage_color = _dependency_usage_color(usage_text)
    widget.setText(usage_text)
    widget.setStyleSheet(f"font-size: 11px; padding: 2px; font-weight: 600; color: {usage_color};")


def _set_dependency_usage_counter_widget(widget: QtWidgets.QLabel | None, count: int | str | None) -> None:
    if widget is None:
        return
    try:
        count_value = max(0, int(count or 0))
    except Exception:
        count_value = 0
    widget.setText(str(count_value))
    widget.setStyleSheet("font-size: 11px; padding: 2px; font-weight: 600;")


def _make_dependency_cell_copyable(widget: QtWidgets.QLabel | None) -> None:
    if widget is None:
        return
    try:
        widget.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    except Exception:
        pass
    try:
        widget.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
    except Exception:
        pass


def _apply_dependency_usage_entry(
    self,
    label: str,
    usage: str | None,
    *,
    widgets: tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel] | None = None,
    track_change: bool = True,
) -> None:
    if not label:
        return
    labels = getattr(self, "_dep_version_labels", None)
    if widgets is None:
        if not isinstance(labels, dict):
            return
        widgets = labels.get(label)
    if not widgets:
        return
    try:
        _, _, usage_widget, counter_widget = widgets
    except Exception:
        return

    usage_text = _normalize_dependency_usage_text(usage)
    normalized_usage = usage_text.lower()

    state_map = getattr(self, "_dep_usage_last_state", None)
    if not isinstance(state_map, dict):
        state_map = {}
        self._dep_usage_last_state = state_map
    count_map = getattr(self, "_dep_usage_change_counts", None)
    if not isinstance(count_map, dict):
        count_map = {}
        self._dep_usage_change_counts = count_map

    previous_state = str(state_map.get(label) or "").strip().lower()
    if track_change and previous_state in {"active", "passive"} and normalized_usage in {"active", "passive"}:
        if previous_state != normalized_usage:
            try:
                count_map[label] = max(0, int(count_map.get(label, 0))) + 1
            except Exception:
                count_map[label] = 1
    if normalized_usage in {"active", "passive"}:
        state_map[label] = normalized_usage

    _set_dependency_usage_widget(usage_widget, usage_text)
    _set_dependency_usage_counter_widget(counter_widget, count_map.get(label, 0))


def _dependency_module_candidates(target: dict[str, str]) -> tuple[str, ...]:
    package = _normalize_dependency_key(target.get("package"))
    label = _normalize_dependency_key(target.get("label"))
    key = package or label
    alias_candidates = _DEPENDENCY_MODULE_ALIASES.get(key)
    if alias_candidates:
        return alias_candidates
    raw = str(target.get("package") or target.get("label") or "").strip()
    if not raw:
        return tuple()
    return (raw.replace("-", "_"),)


def _normalize_installed_version_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, types.ModuleType):
        for attr_name in ("__version__", "VERSION", "version", "version_info"):
            try:
                nested_value = getattr(value, attr_name, None)
            except Exception:
                nested_value = None
            if nested_value is None or nested_value is value:
                continue
            if callable(nested_value):
                try:
                    nested_value = nested_value()
                except Exception:
                    nested_value = None
            if isinstance(nested_value, types.ModuleType):
                for inner_attr_name in ("__version__", "VERSION", "version", "version_info"):
                    try:
                        inner_value = getattr(nested_value, inner_attr_name, None)
                    except Exception:
                        inner_value = None
                    if inner_value is None or inner_value is nested_value or inner_value is value:
                        continue
                    if callable(inner_value):
                        try:
                            inner_value = inner_value()
                        except Exception:
                            inner_value = None
                    normalized = _normalize_installed_version_text(inner_value)
                    if normalized:
                        return normalized
                continue
            normalized = _normalize_installed_version_text(nested_value)
            if normalized:
                return normalized
        return None
    if isinstance(value, dict):
        for key in ("__version__", "version", "VERSION"):
            try:
                nested_value = value.get(key)
            except Exception:
                nested_value = None
            normalized = _normalize_installed_version_text(nested_value)
            if normalized:
                return normalized
        return None
    if isinstance(value, (tuple, list)):
        try:
            parts = [str(part).strip() for part in value if str(part).strip()]
            if parts:
                return ".".join(parts)
        except Exception:
            return None
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = str(value).strip()
    else:
        text = str(value).strip()
    if not text:
        return None
    if text.startswith("<module "):
        return None
    if text.startswith("<") and text.endswith(">") and " at 0x" in text:
        return None
    semver = _extract_semver_from_text(text)
    return semver or text


def _module_version_from_runtime(module_name: str, dependency_key: str) -> str | None:
    name = str(module_name or "").strip()
    if not name:
        return None
    try:
        module = importlib.import_module(name)
    except Exception:
        return None

    if name.startswith("PyQt6"):
        try:
            from PyQt6 import QtCore as _QtCore

            if dependency_key == "pyqt6":
                return (
                    _normalize_installed_version_text(getattr(_QtCore, "PYQT_VERSION_STR", None))
                    or _normalize_installed_version_text(getattr(_QtCore, "QT_VERSION_STR", None))
                )
            if dependency_key in {"pyqt6-qt6", "pyqt6-webengine"}:
                return _normalize_installed_version_text(getattr(_QtCore, "QT_VERSION_STR", None))
        except Exception:
            pass

    for attr_name in ("__version__", "VERSION", "version", "version_info"):
        try:
            attr_value = getattr(module, attr_name, None)
        except Exception:
            attr_value = None
        if callable(attr_value):
            try:
                attr_value = attr_value()
            except Exception:
                attr_value = None
        normalized = _normalize_installed_version_text(attr_value)
        if normalized:
            return normalized
    return "Installed"


def _installed_version_for_dependency_target(target: dict[str, str]) -> str | None:
    custom = str(target.get("custom") or "").strip().lower()
    if custom == "qt":
        return getattr(QtCore, "QT_VERSION_STR", None)
    if custom.startswith("cpp_"):
        return _cpp_custom_installed_value(target)
    if custom.startswith("rust_"):
        return _rust_custom_installed_value(target)

    dependency_key = _normalize_dependency_key(target.get("package") or target.get("label"))
    metadata_candidates: list[str] = []
    for candidate in (target.get("package"), target.get("pypi"), target.get("label")):
        value = str(candidate or "").strip()
        if value and value not in metadata_candidates:
            metadata_candidates.append(value)

    for package_name in metadata_candidates:
        try:
            version_text = importlib_metadata.version(package_name)
        except Exception:
            continue
        normalized = _normalize_installed_version_text(version_text)
        if normalized:
            return normalized

    for module_name in _dependency_module_candidates(target):
        resolved = _module_version_from_runtime(module_name, dependency_key)
        if resolved:
            return resolved
    return None


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


def _pick_highest_version(candidates: list[str]) -> str | None:
    valid = [str(item).strip() for item in candidates if str(item).strip()]
    if not valid:
        return None
    valid.sort(key=_version_sort_key)
    return valid[-1]


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


def _rust_manifest_path(path_value: str | None = None) -> Path:
    relative_path = str(path_value or "").strip()
    if relative_path:
        return (_BASE_PROJECT_PATH / relative_path).resolve()
    return RUST_PROJECT_PATH / "Cargo.toml"


def _rust_package_metadata(path_value: str | None = None) -> dict[str, str]:
    manifest_path = _rust_manifest_path(path_value)
    cache_key = str(manifest_path)
    cached = _RUST_PACKAGE_METADATA_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    metadata: dict[str, str] = {}
    try:
        text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        _RUST_PACKAGE_METADATA_CACHE[cache_key] = metadata
        return metadata

    current_section = ""
    for raw_line in text.splitlines():
        stripped = str(raw_line or "").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped.strip("[]").strip().lower()
            continue
        if current_section != "package":
            continue
        match = re.match(r'(?i)(name|version)\s*=\s*"([^"]+)"', stripped)
        if not match:
            continue
        metadata[str(match.group(1)).strip().lower()] = str(match.group(2)).strip()

    _RUST_PACKAGE_METADATA_CACHE[cache_key] = dict(metadata)
    return metadata


def _rust_project_version(path_value: str | None = None) -> str | None:
    version_text = str(_rust_package_metadata(path_value).get("version") or "").strip()
    return version_text or None


def _rust_toolchain_bin_dir() -> Path:
    cargo_home = str(os.environ.get("CARGO_HOME") or "").strip()
    if cargo_home:
        try:
            return Path(cargo_home).expanduser().resolve() / "bin"
        except Exception:
            return Path(cargo_home).expanduser() / "bin"
    return Path.home() / ".cargo" / "bin"


def _rust_tool_path(executable: str) -> Path | None:
    base_name = str(executable or "").strip()
    if not base_name:
        return None

    candidates = [base_name]
    if sys.platform == "win32" and not base_name.lower().endswith(".exe"):
        candidates.insert(0, f"{base_name}.exe")

    for name in candidates:
        found = shutil.which(name)
        if found:
            try:
                return Path(found).resolve()
            except Exception:
                return Path(found)

    bin_dir = _rust_toolchain_bin_dir()
    for name in candidates:
        path = bin_dir / name
        try:
            if path.is_file():
                return path.resolve()
        except Exception:
            continue
    return None


def _rust_toolchain_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ.copy())
    cargo_bin = _rust_toolchain_bin_dir()
    try:
        cargo_bin_text = str(cargo_bin.resolve())
    except Exception:
        cargo_bin_text = str(cargo_bin)
    if cargo_bin_text and cargo_bin.is_dir():
        current_path = str(env.get("PATH") or "")
        parts = [part for part in current_path.split(os.pathsep) if str(part or "").strip()]
        normalized_parts = {os.path.normcase(os.path.normpath(part)) for part in parts}
        normalized_bin = os.path.normcase(os.path.normpath(cargo_bin_text))
        if normalized_bin not in normalized_parts:
            env["PATH"] = os.pathsep.join([cargo_bin_text, *parts]) if parts else cargo_bin_text
    return env


def _reset_rust_dependency_caches() -> None:
    _RUST_PACKAGE_METADATA_CACHE.clear()
    _RUST_TOOL_VERSION_CACHE.clear()


def _rust_tool_version(command: list[str], *, cache_key: str) -> str | None:
    now = time.time()
    cached = _RUST_TOOL_VERSION_CACHE.get(cache_key)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_value, cached_at = cached
        try:
            if now - float(cached_at) < 20.0:
                return str(cached_value or "").strip() or None
        except Exception:
            pass

    executable = str(command[0] if command else "").strip()
    tool_path = _rust_tool_path(executable)
    if not executable or tool_path is None:
        _RUST_TOOL_VERSION_CACHE[cache_key] = (None, now)
        return None

    version_text = None
    try:
        resolved_command = [str(tool_path), *command[1:]]
        result = subprocess.run(
            resolved_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=4.0,
            env=_rust_toolchain_env(),
        )
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        version_text = _extract_semver_from_text(output)
    except Exception:
        version_text = None

    _RUST_TOOL_VERSION_CACHE[cache_key] = (version_text, now)
    return version_text


def _rust_custom_installed_value(target: dict[str, str]) -> str | None:
    custom = str(target.get("custom") or "").strip().lower()
    if custom == "rust_rustc":
        return _rust_tool_version(["rustc", "--version"], cache_key="rustc")
    if custom == "rust_cargo":
        return _rust_tool_version(["cargo", "--version"], cache_key="cargo")
    if custom == "rust_file_version":
        manifest_path = _rust_manifest_path(target.get("path"))
        version_text = _rust_project_version(target.get("path"))
        if version_text:
            return version_text
        if manifest_path.is_file():
            return "Scaffolded"
    return None


def _rust_custom_latest_value(target: dict[str, str], installed_value: str) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    latest_text = str(target.get("latest") or "").strip()
    if custom == "rust_file_version":
        return installed_value or latest_text or "Unknown"
    if _cpp_version_is_installed_marker(installed_value):
        return installed_value
    return latest_text or "Unknown"


def _rust_custom_usage_value(target: dict[str, str]) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    if custom == "rust_file_version":
        return "Active" if _rust_manifest_path(target.get("path")).is_file() else "Passive"
    installed_value = _rust_custom_installed_value(target)
    return "Active" if _cpp_version_is_installed_marker(installed_value) else "Passive"


def _rust_auto_install_enabled() -> bool:
    raw_value = str(os.environ.get("TB_RUST_AUTO_INSTALL", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _rust_auto_install_cooldown_seconds() -> float:
    raw_value = str(os.environ.get("TB_RUST_AUTO_INSTALL_COOLDOWN_SEC", "") or "").strip()
    if not raw_value:
        return _RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC
    try:
        return max(0.0, float(raw_value))
    except Exception:
        return _RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC


def _rust_missing_tool_labels() -> list[str]:
    missing: list[str] = []
    if _rust_tool_path("rustc") is None:
        missing.append("rustc")
    if _rust_tool_path("cargo") is None:
        missing.append("cargo")
    return missing


def _rust_toolchain_is_ready() -> bool:
    return not _rust_missing_tool_labels()


def _rust_installer_cache_dir() -> Path:
    root = (
        str(os.environ.get("LOCALAPPDATA") or "").strip()
        or str(os.environ.get("TEMP") or "").strip()
        or tempfile.gettempdir()
    )
    return (Path(root).expanduser() / "trading-bot-rustup").resolve()


def _rustup_windows_install_url() -> str:
    machine = str(platform.machine() or "").strip().lower()
    arch = "x86_64"
    if machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    elif machine in {"x86", "i386", "i686"}:
        arch = "i686"
    return f"{_RUSTUP_WINDOWS_INSTALLER_URL_BASE}/{arch}"


def _download_to_path(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
    with urllib.request.urlopen(request, timeout=45.0) as response:
        with open(destination, "wb") as fh:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)


def _install_rust_toolchain() -> tuple[bool, str]:
    with _RUST_AUTO_INSTALL_LOCK:
        if _rust_toolchain_is_ready():
            return True, "Rust toolchain already installed."

        cache_dir = _rust_installer_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            installer_path = cache_dir / "rustup-init.exe"
            install_url = _rustup_windows_install_url()
            command = [
                str(installer_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
            ]
        else:
            installer_path = cache_dir / "rustup-init.sh"
            install_url = _RUSTUP_UNIX_INSTALLER_URL
            sh_path = shutil.which("sh") or "/bin/sh"
            command = [
                str(sh_path),
                str(installer_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
            ]

        try:
            _download_to_path(install_url, installer_path)
        except Exception as exc:
            return False, f"Failed to download rustup installer from {install_url}: {exc}"

        if sys.platform != "win32":
            try:
                installer_path.chmod(0o755)
            except Exception:
                pass

        ok, output = code_language_launch.run_command_capture_hidden(
            command,
            cwd=cache_dir,
            env=_rust_toolchain_env(),
        )
        env_with_cargo = _rust_toolchain_env()
        try:
            os.environ["PATH"] = env_with_cargo.get("PATH", os.environ.get("PATH", ""))
        except Exception:
            pass

        _reset_rust_dependency_caches()
        ready = _rust_toolchain_is_ready()
        if ok and ready:
            return True, output or "Rust toolchain installed."
        tail = _tail_text(output, max_lines=20, max_chars=4000)
        if ready:
            return True, tail or "Rust toolchain installed."
        return False, tail or "rustup installation did not make cargo/rustc available."


def _cpp_auto_setup_enabled() -> bool:
    raw_value = str(os.environ.get("TB_CPP_AUTO_SETUP", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _cpp_auto_setup_cooldown_seconds() -> float:
    raw_value = str(os.environ.get("TB_CPP_AUTO_SETUP_COOLDOWN_SEC", "") or "").strip()
    if not raw_value:
        return _CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC
    try:
        return max(0.0, float(raw_value))
    except Exception:
        return _CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC


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


def _tail_text(value: str | None, *, max_lines: int = 20, max_chars: int = 4000) -> str:
    text = str(value or "")
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        text = "\n".join(lines[-max_lines:])
    text = text.strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _cpp_run_dependency_installer() -> tuple[bool, str]:
    command, cwd = _cpp_dependency_installer_command()
    if not command or cwd is None:
        if sys.platform == "win32":
            return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.ps1"
        return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.sh"
    with _CPP_AUTO_SETUP_LOCK:
        return code_language_launch.run_command_capture_hidden(command, cwd=cwd)


def _cpp_auto_prepare_environment_result(
    *,
    reason: str,
    targets: list[dict[str, str]] | None = None,
    install_when_missing: bool = True,
) -> dict[str, object]:
    target_list = _cpp_env_dependency_targets(targets)
    missing_before = _cpp_missing_dependency_labels(target_list)
    attempted = False
    install_ok = True
    install_output = ""

    if missing_before and install_when_missing and _cpp_auto_setup_enabled():
        attempted = True
        install_ok, install_output = _cpp_run_dependency_installer()

    _reset_cpp_dependency_caches()
    missing_after = _cpp_missing_dependency_labels(target_list)

    return {
        "reason": str(reason or "").strip(),
        "attempted": attempted,
        "install_ok": bool(install_ok),
        "missing_before": list(missing_before),
        "missing_after": list(missing_after),
        "ready": not missing_after,
        "install_output": _tail_text(install_output),
    }


def _apply_cpp_auto_prepare_result(
    self,
    result: dict | None,
    *,
    refresh_versions: bool = True,
) -> None:
    payload = result if isinstance(result, dict) else {}
    attempted = bool(payload.get("attempted"))
    install_ok = bool(payload.get("install_ok", True))
    ready = bool(payload.get("ready"))
    reason = str(payload.get("reason") or "").strip() or "cpp-auto-setup"
    missing_before = payload.get("missing_before") if isinstance(payload.get("missing_before"), list) else []
    missing_after = payload.get("missing_after") if isinstance(payload.get("missing_after"), list) else []
    install_output = str(payload.get("install_output") or "").strip()

    if attempted and ready:
        missing_text = ", ".join(str(item) for item in missing_before) if missing_before else "dependencies"
        self.log(f"C++ dependency auto-setup ({reason}) completed: {missing_text}")
    elif attempted and not ready:
        missing_text = ", ".join(str(item) for item in missing_after) if missing_after else "unknown"
        self.log(f"C++ dependency auto-setup ({reason}) did not complete fully. Missing: {missing_text}")
        if install_output:
            self.log(_tail_text(install_output, max_lines=12, max_chars=1800))
    elif not ready and not _cpp_auto_setup_enabled():
        missing_text = ", ".join(str(item) for item in missing_after) if missing_after else "unknown"
        self.log(f"C++ auto-setup is disabled (TB_CPP_AUTO_SETUP=0). Missing: {missing_text}")
    elif not ready and not install_ok and install_output:
        self.log(_tail_text(install_output, max_lines=12, max_chars=1800))

    if refresh_versions:
        _reset_cpp_dependency_caches()
        try:
            QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
        except Exception:
            pass


def _maybe_auto_prepare_cpp_environment(
    self,
    *,
    resolved_targets: list[dict[str, str]] | None = None,
    reason: str = "code-tab",
    force: bool = False,
) -> bool:
    if code_language_runtime.is_frozen_python_app():
        return False
    if not _cpp_auto_setup_enabled():
        return False

    cpp_targets = _cpp_env_dependency_targets(resolved_targets)
    if not cpp_targets:
        return False

    if getattr(self, "_cpp_auto_setup_inflight", False):
        return False

    now = time.time()
    cooldown_sec = _cpp_auto_setup_cooldown_seconds()
    last_attempt = float(getattr(self, "_cpp_auto_setup_last_attempt_at", 0.0) or 0.0)
    if not force and cooldown_sec > 0.0 and now - last_attempt < cooldown_sec:
        return False

    missing_now = _cpp_missing_dependency_labels(cpp_targets)
    if not missing_now:
        return False

    self._cpp_auto_setup_inflight = True
    self._cpp_auto_setup_last_attempt_at = now
    self.log(f"C++ dependencies missing ({reason}): {', '.join(missing_now)}. Starting automatic setup...")

    def _worker():
        result = _cpp_auto_prepare_environment_result(
            reason=reason,
            targets=cpp_targets,
            install_when_missing=True,
        )
        try:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_on_cpp_auto_prepare_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(object, result),
            )
        except Exception:
            self._cpp_auto_setup_inflight = False

    threading.Thread(target=_worker, daemon=True).start()
    return True


def _dependency_usage_state(
    target: dict[str, str],
    *,
    config: dict | None = None,
    loaded_modules: set[str] | None = None,
) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    if custom.startswith("cpp_"):
        return _cpp_custom_usage_value(target)
    if custom.startswith("rust_"):
        return _rust_custom_usage_value(target)

    dependency_key = _normalize_dependency_key(target.get("package") or target.get("label"))
    if dependency_key in _CONNECTOR_DEPENDENCY_KEYS:
        backend_key = _normalize_connector_backend((config or {}).get("connector_backend"))
        return "Active" if dependency_key == backend_key else "Passive"

    modules = loaded_modules if loaded_modules is not None else set(sys.modules.keys())
    for module_name in _dependency_module_candidates(target):
        name = str(module_name or "").strip()
        if not name:
            continue
        if name in modules:
            return "Active"
        prefix = f"{name}."
        if any(loaded.startswith(prefix) for loaded in modules):
            return "Active"
    return "Passive"


def _refresh_dependency_usage_labels(
    self,
    targets: list[dict[str, str]] | None = None,
    *,
    config: dict | None = None,
) -> None:
    labels = getattr(self, "_dep_version_labels", None)
    if not labels:
        return
    target_list = targets or getattr(self, "_dep_version_targets", []) or []
    if not target_list:
        return
    try:
        config_snapshot = dict((config if config is not None else self.config) or {})
    except Exception:
        config_snapshot = {}
    loaded_modules = set(sys.modules.keys())
    usage_by_label: dict[str, str] = {}
    for target in target_list:
        label = str(target.get("label") or "").strip()
        if not label:
            continue
        usage_by_label[label] = _dependency_usage_state(
            target,
            config=config_snapshot,
            loaded_modules=loaded_modules,
        )
    for label, widgets in labels.items():
        _apply_dependency_usage_entry(
            self,
            label,
            usage_by_label.get(label, "Passive"),
            widgets=widgets,
            track_change=True,
        )


def _extract_requirement_name(line: str) -> str | None:
    stripped = (line or "").strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith(("-", "--")):
        return None
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
    if not stripped:
        return None
    separators = ("==", ">=", "<=", "~=", "!=", "===", "<", ">", "@")
    name_part = stripped
    for sep in separators:
        if sep in stripped:
            name_part = stripped.split(sep, 1)[0].strip()
            break
    if "[" in name_part:
        name_part = name_part.split("[", 1)[0].strip()
    return name_part or None


def _iter_candidate_requirement_paths(config: dict | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None):
        if path is None:
            return
        try:
            resolved = Path(path).resolve()
        except Exception:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    _add(_BASE_PROJECT_PATH / "requirements.txt")
    lang_rel = None
    exch_rel = None
    forex_rel = None
    try:
        if config:
            lang_rel = LANGUAGE_PATHS.get(config.get("code_language"))
            exch_rel = EXCHANGE_PATHS.get(config.get("selected_exchange"))
            forex_rel = FOREX_BROKER_PATHS.get(config.get("selected_forex_broker"))
    except Exception:
        lang_rel = exch_rel = forex_rel = None

    if lang_rel:
        _add(_BASE_PROJECT_PATH / lang_rel / "requirements.txt")
        if exch_rel:
            _add(_BASE_PROJECT_PATH / lang_rel / exch_rel / "requirements.txt")
        if forex_rel:
            _add(_BASE_PROJECT_PATH / lang_rel / forex_rel / "requirements.txt")
    if exch_rel:
        _add(_BASE_PROJECT_PATH / exch_rel / "requirements.txt")

    for legacy in _REQUIREMENTS_PATHS:
        _add(legacy)
    return candidates


def _dependency_targets_from_requirements(paths: list[Path] | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    paths_to_check = paths or _REQUIREMENTS_PATHS
    for path in paths_to_check:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    pkg_name = _extract_requirement_name(raw_line)
                    if not pkg_name or pkg_name in seen:
                        continue
                    entries.append({"label": pkg_name, "package": pkg_name})
                    seen.add(pkg_name)
        except Exception:
            continue
    if not entries:
        return copy.deepcopy(_DEFAULT_DEPENDENCY_VERSION_TARGETS)
    return entries


def _resolve_dependency_targets_for_config(config: dict | None = None) -> list[dict[str, str]]:
    language_key = ""
    try:
        language_key = str((config or {}).get("code_language") or "").strip()
    except Exception:
        language_key = ""
    if language_key == CPP_CODE_LANGUAGE_KEY:
        return copy.deepcopy(_CPP_DEPENDENCY_VERSION_TARGETS)
    if language_key == RUST_CODE_LANGUAGE_KEY:
        return _rust_dependency_targets_for_config(config)
    return _dependency_targets_from_requirements(_iter_candidate_requirement_paths(config))


def _latest_version_from_pypi(package: str, timeout: float = 8.0) -> str | None:
    if not package:
        return None
    cache_entry = _LATEST_VERSION_CACHE.get(package)
    now = time.time()
    if cache_entry and now - cache_entry[1] < 1800:
        return cache_entry[0]
    url = f"https://pypi.org/pypi/{package}/json"
    timeout_val = max(2.0, float(timeout or 8.0))
    latest = None

    try:
        import requests  # type: ignore

        resp = requests.get(url, timeout=timeout_val, headers={"User-Agent": "trading-bot-starter/1.0"})
        if resp.status_code == 200:
            payload = resp.json()
            latest = payload.get("info", {}).get("version")
    except Exception:
        pass

    if latest is None:
        try:
            import requests  # type: ignore

            resp = requests.get(
                url,
                timeout=timeout_val,
                headers={"User-Agent": "trading-bot-starter/1.0"},
                verify=False,  # noqa: S501
            )
            if resp.status_code == 200:
                payload = resp.json()
                latest = payload.get("info", {}).get("version")
        except Exception:
            pass

    if latest is None:
        try:
            import ssl

            req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
            ctx = ssl.create_default_context()
            try:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass
            with urllib.request.urlopen(req, timeout=timeout_val, context=ctx) as resp:
                payload = json.load(resp)
                latest = payload.get("info", {}).get("version")
        except Exception:
            latest = None

    if latest:
        _LATEST_VERSION_CACHE[package] = (latest, now)
        return latest
    return None


def _collect_dependency_versions(
    targets: list[dict[str, str]] | None = None,
    *,
    include_latest: bool = True,
    config: dict | None = None,
) -> list[tuple[str, str, str, str]]:
    versions: list[tuple[str, str, str, str]] = []
    target_list = targets or DEPENDENCY_VERSION_TARGETS
    loaded_modules = set(sys.modules.keys())

    installed_map: dict[str, str] = {}
    for target in target_list:
        label = target["label"]
        installed_version = _installed_version_for_dependency_target(target)
        if installed_version:
            installed_version = _normalize_installed_version_text(installed_version) or installed_version
        installed_map[label] = installed_version or "Not installed"

    latest_map: dict[str, str] = {}
    if include_latest:
        max_workers = min(6, max(1, len(target_list)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map: dict[str, concurrent.futures.Future] = {}
            for target in target_list:
                custom = str(target.get("custom") or "").strip().lower()
                if custom.startswith("cpp_"):
                    installed_display = installed_map.get(target["label"], "Unknown")
                    latest_map[target["label"]] = _cpp_custom_latest_value(target, installed_display)
                    continue
                if custom.startswith("rust_"):
                    installed_display = installed_map.get(target["label"], "Unknown")
                    latest_map[target["label"]] = _rust_custom_latest_value(target, installed_display)
                    continue
                if custom == "qt":
                    latest_map[target["label"]] = installed_map.get(target["label"], "Unknown")
                    continue
                pypi_name = target.get("pypi") or target.get("package")
                if not pypi_name:
                    continue
                future_map[target["label"]] = pool.submit(_latest_version_from_pypi, pypi_name)
            for label, fut in future_map.items():
                try:
                    latest_val = fut.result(timeout=10.0)
                except Exception:
                    latest_val = None
                latest_map[label] = latest_val or "Unknown"

    for target in target_list:
        label = target["label"]
        installed_display = installed_map.get(label, "Not installed")
        latest_display = latest_map.get(label, "Not checked" if not include_latest else "Unknown")
        usage_display = _dependency_usage_state(target, config=config, loaded_modules=loaded_modules)
        versions.append((label, installed_display, latest_display, usage_display))
    return versions


def _reset_cpp_dependency_caches() -> None:
    _CPP_INSTALLED_VALUE_CACHE.clear()
    global _CPP_INCLUDE_DIR_CACHE
    _CPP_INCLUDE_DIR_CACHE = ([], 0.0)
    global _CPP_VCPKG_STATUS_CACHE
    _CPP_VCPKG_STATUS_CACHE = ({}, 0.0)
    _CPP_PINNED_QT_VERSION_CACHE.clear()
    code_language_runtime.reset_cpp_runtime_caches()


DEPENDENCY_VERSION_TARGETS = _resolve_dependency_targets_for_config()

_LATEST_VERSION_CACHE: dict[str, tuple[str, float]] = {}
_LATEST_CPP_VERSION_CACHE: dict[str, tuple[str, float]] = {}
_CPP_INCLUDE_DIR_CACHE: tuple[list[Path], float] = ([], 0.0)
_CPP_INSTALLED_VALUE_CACHE: dict[str, tuple[str | None, float]] = {}
_CPP_VCPKG_STATUS_CACHE: tuple[dict[str, str], float] = ({}, 0.0)
_CPP_PINNED_QT_VERSION_CACHE: dict[str, str] = {}
_RUST_PACKAGE_METADATA_CACHE: dict[str, dict[str, str]] = {}
_RUST_TOOL_VERSION_CACHE: dict[str, tuple[str | None, float]] = {}
