from __future__ import annotations

import threading
from pathlib import Path

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
