from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

from . import code_language_launch, code_language_runtime
from . import dependency_versions_cpp_latest_runtime as latest
from . import dependency_versions_cpp_probe_runtime as probe
from . import dependency_versions_cpp_shared_runtime as shared


def _cpp_cached_installed_value(cache_key: str, resolver, ttl_sec: float = 20.0) -> str | None:
    now = time.time()
    entry = shared._CPP_INSTALLED_VALUE_CACHE.get(cache_key)
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
    shared._CPP_INSTALLED_VALUE_CACHE[cache_key] = (resolved_value, now)
    return resolved_value


def _cpp_custom_installed_value(target: dict[str, str]) -> str | None:
    custom = str(target.get("custom") or "").strip().lower()
    cache_key = f"{custom}:{str(target.get('path') or '').strip()}"

    def _resolve():
        packaged_value = code_language_runtime.cpp_packaged_installed_value(target)
        if custom == "cpp_file_version":
            packaged_semver = shared._extract_semver_from_text(str(packaged_value or ""))
            if packaged_semver:
                return packaged_semver
            cpp_release_tag, _ = code_language_runtime.cpp_runtime_release_snapshot()
            if cpp_release_tag:
                return cpp_release_tag
            py_release_tag = code_language_runtime.python_runtime_release_tag()
            if py_release_tag:
                return py_release_tag
            if packaged_value:
                normalized_packaged = (
                    shared._normalize_installed_version_text(packaged_value)
                    or str(packaged_value).strip()
                )
                lowered = normalized_packaged.lower()
                if (
                    normalized_packaged
                    and lowered not in {"installed", "active"}
                    and not lowered.startswith("src-")
                ):
                    return normalized_packaged
        elif packaged_value:
            return packaged_value

        if custom == "cpp_qt":
            return probe._cpp_qt_version_display()
        if custom == "cpp_qt_network":
            qt_version = probe._cpp_qt_version_display()
            return qt_version if probe._cpp_qt_network_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_qt_webengine":
            qt_version = probe._cpp_qt_version_display()
            return qt_version if probe._cpp_qt_webengine_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_qt_websockets":
            qt_version = probe._cpp_qt_version_display()
            return qt_version if probe._cpp_qt_websockets_available() and qt_version != "Not detected" else "Not installed"
        if custom == "cpp_file_version":
            fingerprint = probe._cpp_source_fingerprint(target.get("path"))
            return "Unknown" if str(fingerprint).strip().lower() == "missing" else fingerprint
        if custom == "cpp_eigen":
            return probe._cpp_detect_eigen_version() or "Not installed"
        if custom == "cpp_xtensor":
            return probe._cpp_detect_xtensor_version() or "Not installed"
        if custom == "cpp_talib":
            return probe._cpp_detect_talib_version() or "Not installed"
        if custom == "cpp_libcurl":
            return probe._cpp_detect_libcurl_version() or "Not installed"
        if custom == "cpp_cpr":
            return probe._cpp_detect_cpr_version() or "Not installed"
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
        latest_resolved = latest._cpp_latest_version_for_key(latest_key)
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
        return "Active" if probe._cpp_dependency_file_exists(target.get("path")) else "Passive"
    installed_value = _cpp_custom_installed_value(target)
    return "Active" if _cpp_version_is_installed_marker(installed_value) else "Passive"


def _cpp_pinned_qt_version() -> str:
    cached_value = str(shared._CPP_PINNED_QT_VERSION_CACHE.get("value") or "").strip()
    if cached_value:
        return cached_value

    default_value = "6.10.2"
    cmake_path = shared.CPP_PROJECT_PATH / "CMakeLists.txt"
    try:
        text = cmake_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        shared._CPP_PINNED_QT_VERSION_CACHE["value"] = default_value
        return default_value

    match = re.search(r'set\s*\(\s*TB_QT_VERSION\s+"([^"]+)"', text, flags=re.IGNORECASE)
    if not match:
        shared._CPP_PINNED_QT_VERSION_CACHE["value"] = default_value
        return default_value

    detected = shared._extract_semver_from_text(match.group(1))
    value = detected or default_value
    shared._CPP_PINNED_QT_VERSION_CACHE["value"] = value
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
        pinned_qt = shared._extract_semver_from_text(_cpp_pinned_qt_version())
        installed_qt = shared._extract_semver_from_text(installed)
        if not pinned_qt or not installed_qt:
            return False
        return installed_qt == pinned_qt
    return _cpp_version_is_installed_marker(installed)


def _cpp_env_dependency_targets(targets: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    source = targets if targets is not None else shared._CPP_DEPENDENCY_VERSION_TARGETS
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
            if probe._cpp_dependency_file_exists(target.get("path")) and installed.lower() != "unknown":
                continue
            missing.append(label)
            continue
        if not _cpp_target_meets_requirement(target, installed):
            missing.append(label)
    return missing


def _cpp_dependency_installer_command() -> tuple[list[str], Path] | tuple[None, None]:
    tools_dir = shared.CPP_PROJECT_PATH / "tools"
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
        return command, shared._BASE_PROJECT_PATH

    script_path = tools_dir / "install_cpp_dependencies.sh"
    bash_exe = shutil.which("bash")
    if not script_path.is_file() or not bash_exe:
        return None, None
    return [bash_exe, str(script_path)], shared._BASE_PROJECT_PATH


def _cpp_run_dependency_installer() -> tuple[bool, str]:
    command, cwd = _cpp_dependency_installer_command()
    if not command or cwd is None:
        if sys.platform == "win32":
            return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.ps1"
        return False, "Missing installer command or script: Languages/C++/tools/install_cpp_dependencies.sh"
    with shared._CPP_AUTO_SETUP_LOCK:
        return code_language_launch.run_command_capture_hidden(command, cwd=cwd)


def _reset_cpp_dependency_caches() -> None:
    shared._CPP_INSTALLED_VALUE_CACHE.clear()
    shared._CPP_INCLUDE_DIR_CACHE = ([], 0.0)
    shared._CPP_VCPKG_STATUS_CACHE = ({}, 0.0)
    shared._CPP_PINNED_QT_VERSION_CACHE.clear()
    code_language_runtime.reset_cpp_runtime_caches()
