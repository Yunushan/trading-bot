from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from . import code_language_release_runtime
from .code_language_catalog import CPP_PACKAGED_EXECUTABLE_BASENAME
from .code_language_cpp_bundle_cache_runtime import _CPP_PACKAGED_MANIFEST_CACHE


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


__all__ = [
    "cpp_packaged_executable_names",
    "cpp_packaged_installed_value",
    "cpp_packaged_manifest_installed_map",
    "cpp_packaged_runtime_exe",
    "cpp_runtime_bundle_missing",
    "find_cpp_packaged_exe_under",
]
