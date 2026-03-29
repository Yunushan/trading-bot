from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .code_language_catalog import CPP_CACHE_META_FILE, CPP_RELEASE_CPP_ASSET

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


__all__ = [
    "_CPP_LATEST_RELEASE_INFO_CACHE",
    "_CPP_PACKAGED_MANIFEST_CACHE",
    "cpp_cache_meta_path",
    "cpp_cache_root",
    "cpp_local_zip_candidates",
    "cpp_runtime_is_cached_path",
    "path_is_within_directory",
    "read_cache_meta",
    "reset_cpp_runtime_caches",
    "write_cache_meta",
]
