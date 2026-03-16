from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import json
import re
import types
import urllib.request

from PyQt6 import QtCore

from . import (
    dependency_versions_cpp_runtime,
    dependency_versions_cpp_setup_runtime,
    dependency_versions_rust_runtime,
    dependency_versions_usage_runtime,
)

_DEPENDENCY_USAGE_POLL_INTERVAL_MS = dependency_versions_usage_runtime._DEPENDENCY_USAGE_POLL_INTERVAL_MS

_normalize_dependency_key = dependency_versions_usage_runtime._normalize_dependency_key
_normalize_dependency_usage_text = dependency_versions_usage_runtime._normalize_dependency_usage_text
_set_dependency_usage_widget = dependency_versions_usage_runtime._set_dependency_usage_widget
_set_dependency_usage_counter_widget = dependency_versions_usage_runtime._set_dependency_usage_counter_widget
_make_dependency_cell_copyable = dependency_versions_usage_runtime._make_dependency_cell_copyable
_apply_dependency_usage_entry = dependency_versions_usage_runtime._apply_dependency_usage_entry
_dependency_module_candidates = dependency_versions_usage_runtime._dependency_module_candidates
_dependency_usage_state = dependency_versions_usage_runtime._dependency_usage_state
_refresh_dependency_usage_labels = dependency_versions_usage_runtime._refresh_dependency_usage_labels
_resolve_dependency_targets_for_config = dependency_versions_usage_runtime._resolve_dependency_targets_for_config
_collect_dependency_versions = dependency_versions_usage_runtime._collect_dependency_versions

_rust_manifest_path = dependency_versions_rust_runtime._rust_manifest_path
_rust_package_metadata = dependency_versions_rust_runtime._rust_package_metadata
_rust_project_version = dependency_versions_rust_runtime._rust_project_version
_rust_tool_path = dependency_versions_rust_runtime._rust_tool_path
_rust_toolchain_env = dependency_versions_rust_runtime._rust_toolchain_env
_reset_rust_dependency_caches = dependency_versions_rust_runtime._reset_rust_dependency_caches
_rust_tool_version = dependency_versions_rust_runtime._rust_tool_version
_rust_custom_installed_value = dependency_versions_rust_runtime._rust_custom_installed_value
_rust_custom_latest_value = dependency_versions_rust_runtime._rust_custom_latest_value
_rust_custom_usage_value = dependency_versions_rust_runtime._rust_custom_usage_value
_rust_auto_install_enabled = dependency_versions_rust_runtime._rust_auto_install_enabled
_rust_auto_install_cooldown_seconds = dependency_versions_rust_runtime._rust_auto_install_cooldown_seconds
_rust_missing_tool_labels = dependency_versions_rust_runtime._rust_missing_tool_labels
_install_rust_toolchain = dependency_versions_rust_runtime._install_rust_toolchain

_cpp_auto_setup_enabled = dependency_versions_cpp_setup_runtime._cpp_auto_setup_enabled
_cpp_auto_setup_cooldown_seconds = dependency_versions_cpp_setup_runtime._cpp_auto_setup_cooldown_seconds
_tail_text = dependency_versions_cpp_setup_runtime._tail_text
_cpp_auto_prepare_environment_result = dependency_versions_cpp_setup_runtime._cpp_auto_prepare_environment_result
_apply_cpp_auto_prepare_result = dependency_versions_cpp_setup_runtime._apply_cpp_auto_prepare_result
_maybe_auto_prepare_cpp_environment = dependency_versions_cpp_setup_runtime._maybe_auto_prepare_cpp_environment

_cpp_dependency_file_exists = dependency_versions_cpp_runtime._cpp_dependency_file_exists
_cpp_source_fingerprint = dependency_versions_cpp_runtime._cpp_source_fingerprint
_cpp_qt_prefix_tokens = dependency_versions_cpp_runtime._cpp_qt_prefix_tokens
_cpp_qt_version_from_path = dependency_versions_cpp_runtime._cpp_qt_version_from_path
_cpp_qt_version_from_qmake = dependency_versions_cpp_runtime._cpp_qt_version_from_qmake
_cpp_qt_version_display = dependency_versions_cpp_runtime._cpp_qt_version_display
_cpp_qt_local_versions = dependency_versions_cpp_runtime._cpp_qt_local_versions
_cpp_latest_qt_version_from_download = dependency_versions_cpp_runtime._cpp_latest_qt_version_from_download
_cpp_latest_local_qt_version = dependency_versions_cpp_runtime._cpp_latest_local_qt_version
_cpp_latest_qt_version = dependency_versions_cpp_runtime._cpp_latest_qt_version
_cpp_qt_kit_roots = dependency_versions_cpp_runtime._cpp_qt_kit_roots
_cpp_qt_network_available = dependency_versions_cpp_runtime._cpp_qt_network_available
_cpp_qt_webengine_available = dependency_versions_cpp_runtime._cpp_qt_webengine_available
_cpp_qt_websockets_available = dependency_versions_cpp_runtime._cpp_qt_websockets_available
_cpp_candidate_vcpkg_roots = dependency_versions_cpp_runtime._cpp_candidate_vcpkg_roots
_cpp_load_vcpkg_status_versions = dependency_versions_cpp_runtime._cpp_load_vcpkg_status_versions
_cpp_vcpkg_installed_version = dependency_versions_cpp_runtime._cpp_vcpkg_installed_version
_cpp_candidate_include_dirs = dependency_versions_cpp_runtime._cpp_candidate_include_dirs
_cpp_find_header = dependency_versions_cpp_runtime._cpp_find_header
_cpp_read_text_file = dependency_versions_cpp_runtime._cpp_read_text_file
_cpp_extract_macro_str = dependency_versions_cpp_runtime._cpp_extract_macro_str
_cpp_extract_macro_int = dependency_versions_cpp_runtime._cpp_extract_macro_int
_cpp_detect_eigen_version = dependency_versions_cpp_runtime._cpp_detect_eigen_version
_cpp_detect_xtensor_version = dependency_versions_cpp_runtime._cpp_detect_xtensor_version
_cpp_detect_talib_version = dependency_versions_cpp_runtime._cpp_detect_talib_version
_cpp_detect_cpr_version = dependency_versions_cpp_runtime._cpp_detect_cpr_version
_cpp_detect_libcurl_version = dependency_versions_cpp_runtime._cpp_detect_libcurl_version
_cpp_latest_from_github_release = dependency_versions_cpp_runtime._cpp_latest_from_github_release
_cpp_latest_from_github_tags = dependency_versions_cpp_runtime._cpp_latest_from_github_tags
_cpp_latest_eigen_version = dependency_versions_cpp_runtime._cpp_latest_eigen_version
_cpp_latest_xtensor_version = dependency_versions_cpp_runtime._cpp_latest_xtensor_version
_cpp_latest_talib_version = dependency_versions_cpp_runtime._cpp_latest_talib_version
_cpp_latest_cpr_version = dependency_versions_cpp_runtime._cpp_latest_cpr_version
_cpp_latest_libcurl_version = dependency_versions_cpp_runtime._cpp_latest_libcurl_version
_cpp_latest_version_for_key = dependency_versions_cpp_runtime._cpp_latest_version_for_key
_cpp_cached_installed_value = dependency_versions_cpp_runtime._cpp_cached_installed_value
_cpp_custom_installed_value = dependency_versions_cpp_runtime._cpp_custom_installed_value
_cpp_version_is_installed_marker = dependency_versions_cpp_runtime._cpp_version_is_installed_marker
_cpp_custom_latest_value = dependency_versions_cpp_runtime._cpp_custom_latest_value
_cpp_custom_usage_value = dependency_versions_cpp_runtime._cpp_custom_usage_value
_cpp_pinned_qt_version = dependency_versions_cpp_runtime._cpp_pinned_qt_version
_cpp_target_requires_pinned_qt = dependency_versions_cpp_runtime._cpp_target_requires_pinned_qt
_cpp_target_meets_requirement = dependency_versions_cpp_runtime._cpp_target_meets_requirement
_cpp_env_dependency_targets = dependency_versions_cpp_runtime._cpp_env_dependency_targets
_cpp_missing_dependency_labels = dependency_versions_cpp_runtime._cpp_missing_dependency_labels
_cpp_dependency_installer_command = dependency_versions_cpp_runtime._cpp_dependency_installer_command
_cpp_run_dependency_installer = dependency_versions_cpp_runtime._cpp_run_dependency_installer
_reset_cpp_dependency_caches = dependency_versions_cpp_runtime._reset_cpp_dependency_caches


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


DEPENDENCY_VERSION_TARGETS = _resolve_dependency_targets_for_config()
