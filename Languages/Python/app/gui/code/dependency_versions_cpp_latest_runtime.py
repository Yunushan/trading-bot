from __future__ import annotations

import re
import time

from . import dependency_versions_cpp_probe_runtime as probe
from . import dependency_versions_cpp_shared_runtime as shared


def _cpp_latest_qt_version_from_download() -> str | None:
    base_url = "https://download.qt.io/official_releases/qt/"
    listing = shared._http_get_text(base_url, timeout=8.0)
    if not listing:
        return None
    minor_versions = re.findall(r'href="(6\.\d+)/"', listing)
    selected_minor = shared._pick_highest_version(minor_versions)
    if not selected_minor:
        return None
    minor_listing = shared._http_get_text(f"{base_url}{selected_minor}/", timeout=8.0)
    if not minor_listing:
        return selected_minor
    patch_versions = re.findall(rf'href="({re.escape(selected_minor)}\.\d+)/"', minor_listing)
    return shared._pick_highest_version(patch_versions) or selected_minor


def _cpp_latest_local_qt_version() -> str | None:
    return shared._pick_highest_version(probe._cpp_qt_local_versions())


def _cpp_latest_qt_version() -> str | None:
    online_version = _cpp_latest_qt_version_from_download()
    if online_version:
        return online_version
    return _cpp_latest_local_qt_version()


def _cpp_latest_from_github_release(owner: str, repo: str) -> str | None:
    if not owner or not repo:
        return None
    payload = shared._http_get_json(
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
        timeout=8.0,
    )
    if not isinstance(payload, dict):
        return None
    candidates = [
        shared._extract_semver_from_text(payload.get("tag_name")),
        shared._extract_semver_from_text(payload.get("name")),
    ]
    return shared._pick_highest_version([candidate for candidate in candidates if candidate])


def _cpp_latest_from_github_tags(owner: str, repo: str) -> str | None:
    if not owner or not repo:
        return None
    payload = shared._http_get_json(
        f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=20",
        timeout=8.0,
    )
    if not isinstance(payload, list):
        return None
    versions: list[str] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        detected = shared._extract_semver_from_text(row.get("name"))
        if detected:
            versions.append(detected)
    return shared._pick_highest_version(versions)


def _cpp_latest_eigen_version() -> str | None:
    payload = shared._http_get_json(
        "https://gitlab.com/api/v4/projects/libeigen%2Feigen/repository/tags?per_page=20",
        timeout=8.0,
    )
    if not isinstance(payload, list):
        return None
    versions: list[str] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        detected = shared._extract_semver_from_text(row.get("name"))
        if detected:
            versions.append(detected)
    return shared._pick_highest_version(versions)


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
    cached_entry = shared._LATEST_CPP_VERSION_CACHE.get(cache_key)
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
        shared._LATEST_CPP_VERSION_CACHE[cache_key] = (value, now)
    return value
