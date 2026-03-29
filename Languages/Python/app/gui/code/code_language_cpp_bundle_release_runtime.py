from __future__ import annotations

import os
import time
import urllib.request
from pathlib import Path

from . import code_language_release_runtime
from .code_language_catalog import (
    CPP_RELEASE_CPP_ASSET,
    CPP_RELEASE_OWNER,
    CPP_RELEASE_REPO,
)
from .code_language_cpp_bundle_cache_runtime import _CPP_LATEST_RELEASE_INFO_CACHE


def cpp_latest_release_asset_info(timeout: float = 8.0) -> tuple[str | None, str | None]:
    explicit_url = str(os.environ.get("TB_CPP_ZIP_URL") or "").strip()
    if explicit_url:
        return None, explicit_url

    owner = str(os.environ.get("TB_RELEASE_OWNER") or CPP_RELEASE_OWNER).strip() or CPP_RELEASE_OWNER
    repo = str(os.environ.get("TB_RELEASE_REPO") or CPP_RELEASE_REPO).strip() or CPP_RELEASE_REPO
    asset_name = str(os.environ.get("TB_CPP_RELEASE_ASSET") or CPP_RELEASE_CPP_ASSET).strip() or CPP_RELEASE_CPP_ASSET

    cache_key = f"{owner}/{repo}/{asset_name}".lower()
    now = time.time()
    entry = _CPP_LATEST_RELEASE_INFO_CACHE.get(cache_key)
    if isinstance(entry, tuple) and len(entry) == 3:
        cached_tag, cached_url, cached_at = entry
        try:
            if now - float(cached_at or 0.0) < 300:
                return cached_tag, cached_url
        except Exception:
            pass

    tag_name: str | None = None
    browser_url: str | None = None
    payload = code_language_release_runtime.http_get_json(
        f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
        timeout=timeout,
    )
    if isinstance(payload, dict):
        tag_name = str(payload.get("tag_name") or "").strip() or None
        assets = payload.get("assets")
        if isinstance(assets, list):
            for row in assets:
                if not isinstance(row, dict):
                    continue
                if str(row.get("name") or "").strip() != asset_name:
                    continue
                candidate = str(row.get("browser_download_url") or "").strip()
                if candidate:
                    browser_url = candidate
                    break

    if not browser_url:
        browser_url = f"https://github.com/{owner}/{repo}/releases/latest/download/{asset_name}"

    _CPP_LATEST_RELEASE_INFO_CACHE[cache_key] = (tag_name, browser_url, now)
    return tag_name, browser_url


def cpp_release_is_newer(latest_tag: str | None, cached_tag: str | None) -> bool:
    latest_clean = str(latest_tag or "").strip()
    cached_clean = str(cached_tag or "").strip()
    if not latest_clean:
        return False
    if not cached_clean:
        return True

    latest_ver = code_language_release_runtime.extract_semver_from_text(latest_clean)
    cached_ver = code_language_release_runtime.extract_semver_from_text(cached_clean)
    if latest_ver and cached_ver:
        return code_language_release_runtime.version_sort_key(latest_ver) > code_language_release_runtime.version_sort_key(cached_ver)
    return latest_clean != cached_clean


def download_binary_file(url: str, target_path: Path, timeout: float = 45.0) -> None:
    timeout_val = max(8.0, float(timeout or 45.0))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_val) as response:
        with target_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


__all__ = [
    "cpp_latest_release_asset_info",
    "cpp_release_is_newer",
    "download_binary_file",
]
