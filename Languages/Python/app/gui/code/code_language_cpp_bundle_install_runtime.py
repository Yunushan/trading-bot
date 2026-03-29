from __future__ import annotations

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

from .code_language_catalog import CPP_RELEASE_CPP_ASSET
from .code_language_cpp_bundle_cache_runtime import (
    cpp_cache_root,
    cpp_local_zip_candidates,
    read_cache_meta,
    write_cache_meta,
)
from .code_language_cpp_bundle_packaged_runtime import (
    cpp_runtime_bundle_missing,
    find_cpp_packaged_exe_under,
)
from .code_language_cpp_bundle_release_runtime import (
    cpp_latest_release_asset_info,
    cpp_release_is_newer,
    download_binary_file,
)


def extract_zip_safely(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        destination_root = destination.resolve()
    except Exception:
        destination_root = destination
    destination_root_norm = os.path.normcase(str(destination_root))

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            name = str(member.filename or "").replace("\\", "/")
            if not name:
                continue
            if name.startswith("/") or name.startswith("../") or "/../" in name:
                continue

            target = destination / Path(name)
            try:
                target_resolved = target.resolve()
            except Exception:
                target_resolved = target
            target_norm = os.path.normcase(str(target_resolved))
            if not (target_norm == destination_root_norm or target_norm.startswith(destination_root_norm + os.sep)):
                continue

            if member.is_dir():
                target_resolved.mkdir(parents=True, exist_ok=True)
                continue

            target_resolved.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target_resolved.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def populate_cpp_bundle_from_zip(
    zip_path: Path,
    *,
    cache_root: Path,
    bundle_dir: Path,
) -> tuple[Path | None, str | None]:
    if not zip_path.is_file():
        return None, f"Zip not found: {zip_path}"

    staging_dir = cache_root / "_staging"
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        pass
    staging_dir.mkdir(parents=True, exist_ok=True)

    extracted_dir = staging_dir / "extract"
    try:
        extract_zip_safely(zip_path, extracted_dir)
    except Exception as exc:
        return None, f"Could not extract C++ bundle '{zip_path}': {exc}"

    staged_exe = find_cpp_packaged_exe_under(extracted_dir)
    if staged_exe is None or not staged_exe.is_file():
        return None, f"Archive '{zip_path.name}' does not contain Trading-Bot-C++.exe."

    staged_bundle_dir = staged_exe.parent
    try:
        shutil.rmtree(bundle_dir, ignore_errors=True)
    except Exception:
        pass
    try:
        shutil.copytree(staged_bundle_dir, bundle_dir, dirs_exist_ok=True)
    except Exception as exc:
        return None, f"Could not cache C++ runtime files: {exc}"

    final_exe = find_cpp_packaged_exe_under(bundle_dir)
    if final_exe is None or not final_exe.is_file():
        return None, "C++ cache populated but executable could not be located."
    if sys.platform == "win32" and cpp_runtime_bundle_missing(final_exe):
        return None, "C++ bundle is incomplete (Qt runtime files missing)."
    return final_exe, None


def ensure_cached_cpp_bundle(find_cpp_code_tab_executable, force_download: bool = False) -> tuple[Path | None, str | None]:
    cache_root = cpp_cache_root()
    if cache_root is None:
        return None, "Could not initialize local cache directory for C++ runtime."

    bundle_dir = cache_root / "Trading-Bot-C++"
    cached_exe = find_cpp_packaged_exe_under(bundle_dir)
    cached_valid = (
        cached_exe is not None
        and cached_exe.is_file()
        and (sys.platform != "win32" or not cpp_runtime_bundle_missing(cached_exe))
    )
    cache_meta = read_cache_meta(cache_root)
    latest_tag: str | None = None
    download_url: str | None = None
    allow_local_zip = True

    if cached_valid and not force_download:
        auto_update_raw = str(os.environ.get("TB_CPP_AUTO_UPDATE", "1") or "1").strip().lower()
        auto_update_enabled = auto_update_raw not in {"0", "false", "no", "off"}
        if not auto_update_enabled:
            return cached_exe, None

        latest_tag, download_url = cpp_latest_release_asset_info(timeout=8.0)
        if not latest_tag:
            return cached_exe, None

        cached_tag = str(cache_meta.get("release_tag") or "").strip() or None
        if cpp_release_is_newer(latest_tag, cached_tag):
            allow_local_zip = False
        else:
            return cached_exe, None

    local_zip_error = ""
    if allow_local_zip:
        for local_zip in cpp_local_zip_candidates(cache_root):
            if not local_zip.is_file():
                continue
            from_zip_exe, from_zip_err = populate_cpp_bundle_from_zip(
                local_zip,
                cache_root=cache_root,
                bundle_dir=bundle_dir,
            )
            if from_zip_exe is not None and from_zip_exe.is_file():
                meta_payload = dict(cache_meta)
                if latest_tag:
                    meta_payload["release_tag"] = latest_tag
                meta_payload["asset_name"] = CPP_RELEASE_CPP_ASSET
                meta_payload["updated_at"] = time.time()
                if download_url:
                    meta_payload["download_url"] = download_url
                write_cache_meta(cache_root, meta_payload)
                return from_zip_exe, None
            if from_zip_err:
                local_zip_error = str(from_zip_err)

    if not download_url:
        latest_tag, download_url = cpp_latest_release_asset_info(timeout=8.0)
    if not download_url:
        if cached_valid:
            return cached_exe, None
        if local_zip_error:
            return None, local_zip_error
        return None, "Could not resolve C++ release asset URL."

    timeout_raw = str(os.environ.get("TB_CPP_DOWNLOAD_TIMEOUT") or "").strip()
    try:
        timeout_val = max(8.0, float(timeout_raw)) if timeout_raw else 45.0
    except Exception:
        timeout_val = 45.0

    download_dir = cache_root / "_download"
    zip_target = download_dir / CPP_RELEASE_CPP_ASSET

    try:
        download_binary_file(download_url, zip_target, timeout=timeout_val)
    except Exception as exc:
        if cached_valid:
            return cached_exe, None
        if local_zip_error:
            return None, f"{local_zip_error}\nCould not download C++ bundle: {exc}"
        return None, f"Could not download C++ bundle: {exc}"

    downloaded_exe, downloaded_err = populate_cpp_bundle_from_zip(
        zip_target,
        cache_root=cache_root,
        bundle_dir=bundle_dir,
    )
    if downloaded_exe is None or not downloaded_exe.is_file():
        if cached_valid:
            return cached_exe, None
        return downloaded_exe, downloaded_err

    meta_payload = dict(cache_meta)
    if latest_tag:
        meta_payload["release_tag"] = latest_tag
    meta_payload["asset_name"] = CPP_RELEASE_CPP_ASSET
    meta_payload["updated_at"] = time.time()
    meta_payload["download_url"] = download_url
    write_cache_meta(cache_root, meta_payload)
    return downloaded_exe, None


__all__ = [
    "download_binary_file",
    "ensure_cached_cpp_bundle",
    "extract_zip_safely",
    "populate_cpp_bundle_from_zip",
]
