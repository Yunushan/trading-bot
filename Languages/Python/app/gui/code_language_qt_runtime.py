from __future__ import annotations

import os
import re
from pathlib import Path

from app.gui.code_language_catalog import CPP_BUILD_ROOT


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


def _cpp_qt_version_from_path(path_value: str | None) -> str | None:
    text = str(path_value or "")
    for match in re.findall(r"(?<!\d)(6\.\d+(?:\.\d+)?)(?!\d)", text):
        if match:
            return match
    return None


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
