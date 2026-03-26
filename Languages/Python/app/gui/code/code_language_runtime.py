from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .code_language_catalog import (
    CPP_BUILD_ROOT,
    CPP_EXECUTABLE_BASENAME,
    CPP_EXECUTABLE_LEGACY_BASENAME,
    CPP_PACKAGED_EXECUTABLE_BASENAME,
    CPP_PROJECT_PATH,
)
from . import (
    code_language_cpp_bundle_runtime,
    code_language_qt_runtime,
    code_language_release_runtime,
)

read_cmake_cache_value = code_language_qt_runtime.read_cmake_cache_value
resolve_cpp_qt_prefix_for_code_tab = code_language_qt_runtime.resolve_cpp_qt_prefix_for_code_tab
discover_cpp_qt_bin_dirs_for_code_tab = code_language_qt_runtime.discover_cpp_qt_bin_dirs_for_code_tab
qt_prefix_has_webengine = code_language_qt_runtime.qt_prefix_has_webengine
qt_prefix_has_websockets = code_language_qt_runtime.qt_prefix_has_websockets
is_frozen_python_app = code_language_release_runtime.is_frozen_python_app
_normalize_release_tag_text = code_language_release_runtime.normalize_release_tag_text
_release_tag_from_metadata_dirs = code_language_release_runtime.release_tag_from_metadata_dirs
python_runtime_release_tag = code_language_release_runtime.python_runtime_release_tag
reset_cpp_runtime_caches = code_language_cpp_bundle_runtime.reset_cpp_runtime_caches
cpp_cache_root = code_language_cpp_bundle_runtime.cpp_cache_root
cpp_runtime_is_cached_path = code_language_cpp_bundle_runtime.cpp_runtime_is_cached_path
read_cache_meta = code_language_cpp_bundle_runtime.read_cache_meta


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


def cpp_packaged_runtime_exe() -> Path | None:
    return code_language_cpp_bundle_runtime.cpp_packaged_runtime_exe(find_cpp_code_tab_executable)


def cpp_packaged_installed_value(target: dict[str, str]) -> str | None:
    return code_language_cpp_bundle_runtime.cpp_packaged_installed_value(
        target,
        find_cpp_code_tab_executable,
    )


def ensure_cached_cpp_bundle(force_download: bool = False) -> tuple[Path | None, str | None]:
    return code_language_cpp_bundle_runtime.ensure_cached_cpp_bundle(
        find_cpp_code_tab_executable,
        force_download=force_download,
    )


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


def _allow_cpp_recursive_search(root: Path) -> bool:
    """Skip broad roots that are already covered by direct candidate checks."""
    try:
        root_resolved = root.resolve()
    except Exception:
        root_resolved = root
    root_key = os.path.normcase(os.path.normpath(str(root_resolved)))
    if not root_key:
        return False

    broad_roots: set[str] = set()
    try:
        broad_roots.add(os.path.normcase(os.path.normpath(str(Path.cwd().resolve()))))
    except Exception:
        pass
    try:
        broad_roots.add(os.path.normcase(os.path.normpath(str(Path(sys.executable).resolve().parent))))
    except Exception:
        pass
    return root_key not in broad_roots


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
            if not _allow_cpp_recursive_search(root):
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


