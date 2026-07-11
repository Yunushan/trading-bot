#!/usr/bin/env python3
"""Validate release assets for a GitHub tag against this repository's release matrix."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass


DEFAULT_OWNER = "Yunushan"
DEFAULT_REPO = "trading-bot"
USER_AGENT = "trading-bot-starter/1.0"
VERSION_PATTERN = re.compile(
    r"(\d+(?:[._-]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)"
)

WINDOWS_ASSET_TAGS = ("windows-x64",)
LINUX_ARCHES = (
    ("x86_64", "amd64", "x86_64"),
)
MACOS_ASSET_TAGS = (
    "macos-15-arm64",
)
OPTIONAL_RUST_PREFIXES = (
    "Trading-Bot-Rust-tauri",
)


@dataclass(frozen=True)
class ExpectedAsset:
    name: str
    required: bool
    group: str


def _resolve_default_repo() -> tuple[str, str]:
    repo_env = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if "/" in repo_env:
        owner, repo = repo_env.split("/", 1)
        owner = owner.strip()
        repo = repo.strip()
        if owner and repo:
            return owner, repo
    return DEFAULT_OWNER, DEFAULT_REPO


def _extract_release_version(tag: str) -> str:
    text = str(tag or "").strip()
    match = VERSION_PATTERN.search(text)
    if not match:
        return "0.0.0"
    return match.group(1).replace("_", ".").replace("-", ".")


def _build_expected_assets(tag: str) -> tuple[str, list[ExpectedAsset]]:
    version = _extract_release_version(tag)
    assets: list[ExpectedAsset] = []

    for asset_tag in WINDOWS_ASSET_TAGS:
        group = f"Windows {asset_tag.removeprefix('windows-')}"
        assets.extend(
            [
                ExpectedAsset(f"Trading-Bot-Python-{asset_tag}-{version}.exe", True, group),
                ExpectedAsset(f"Trading-Bot-Rust-{asset_tag}-{version}.exe", True, group),
                ExpectedAsset(f"Trading-Bot-C++-{asset_tag}-{version}.zip", True, group),
            ]
        )
        for rust_prefix in OPTIONAL_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-{asset_tag}-{version}.exe", False, group))

    for arch, deb_arch, rpm_arch in LINUX_ARCHES:
        group = f"Linux {arch}"
        assets.extend(
            [
                ExpectedAsset(f"Trading-Bot-Python-linux-{arch}-{version}.tar.gz", True, group),
                ExpectedAsset(f"Trading-Bot-Rust-linux-{arch}-{version}.tar.gz", True, group),
                ExpectedAsset(f"Trading-Bot-C++-linux-{arch}-{version}.tar.gz", True, group),
                ExpectedAsset(f"trading-bot-python_{version}_{deb_arch}.deb", True, group),
                ExpectedAsset(f"trading-bot-python_{version}_{rpm_arch}.rpm", True, group),
            ]
        )
        for rust_prefix in OPTIONAL_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-linux-{arch}-{version}.tar.gz", False, group))

    for asset_tag in MACOS_ASSET_TAGS:
        group = f"macOS {asset_tag.removeprefix('macos-')}"
        assets.extend(
            [
                ExpectedAsset(f"Trading-Bot-Python-{asset_tag}-{version}.zip", True, group),
                ExpectedAsset(f"Trading-Bot-Rust-{asset_tag}-{version}.zip", True, group),
                ExpectedAsset(f"Trading-Bot-C++-{asset_tag}-{version}.zip", True, group),
            ]
        )
        for rust_prefix in OPTIONAL_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-{asset_tag}-{version}.zip", False, group))

    return version, assets


def _is_ssl_certificate_error(exc: urllib.error.URLError) -> bool:
    text = str(exc.reason if hasattr(exc, "reason") else exc)
    return "CERTIFICATE_VERIFY_FAILED" in text or "[SSL:" in text


def _powershell_executable() -> str | None:
    for name in ("pwsh", "powershell"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _github_json_from_windows_certificate_store(
    url: str,
    *,
    timeout: float,
    token: str | None,
) -> dict:
    powershell = _powershell_executable()
    if os.name != "nt" or not powershell:
        raise RuntimeError("Windows certificate-store fallback is unavailable.")

    script = r"""
$ErrorActionPreference = 'Stop'
$headers = @{
  'User-Agent' = $env:TB_RELEASE_USER_AGENT
  'Accept' = 'application/vnd.github+json'
}
if ($env:TB_RELEASE_GITHUB_TOKEN) {
  $headers['Authorization'] = "Bearer $env:TB_RELEASE_GITHUB_TOKEN"
}
$timeoutSec = [Math]::Max(5, [int]$env:TB_RELEASE_TIMEOUT)
Invoke-RestMethod -Uri $env:TB_RELEASE_URL -Headers $headers -TimeoutSec $timeoutSec |
  ConvertTo-Json -Depth 100 -Compress
""".strip()
    env = os.environ.copy()
    env.update(
        {
            "TB_RELEASE_URL": url,
            "TB_RELEASE_USER_AGENT": USER_AGENT,
            "TB_RELEASE_TIMEOUT": str(max(5, int(float(timeout or 10.0)))),
            "TB_RELEASE_GITHUB_TOKEN": token or "",
        }
    )
    try:
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(10.0, float(timeout or 10.0) + 5.0),
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Windows certificate-store fallback failed to run: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        message = "GitHub API request failed through Windows certificate-store fallback."
        if detail:
            message = f"{message} {detail}"
        raise RuntimeError(message)

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows certificate-store fallback returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Windows certificate-store fallback returned an unexpected response type.")
    return result


def _github_json(url: str, *, timeout: float, token: str | None) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout or 10.0))) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except (OSError, UnicodeError):
            detail = ""
        message = f"GitHub API request failed with HTTP {exc.code}."
        if detail:
            message = f"{message} {detail}"
        raise RuntimeError(message) from exc
    except urllib.error.URLError as exc:
        if _is_ssl_certificate_error(exc):
            try:
                return _github_json_from_windows_certificate_store(
                    url,
                    timeout=timeout,
                    token=token,
                )
            except RuntimeError as fallback_exc:
                raise RuntimeError(
                    "Could not reach GitHub API with Python TLS validation, and the "
                    f"Windows certificate-store fallback also failed: {fallback_exc}"
                ) from exc
        raise RuntimeError(f"Could not reach GitHub API: {exc}") from exc

    try:
        result = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub API returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("GitHub API returned an unexpected response type.")
    return result


def _fetch_release(tag: str, *, owner: str, repo: str, timeout: float, token: str | None) -> dict:
    encoded_tag = urllib.parse.quote(str(tag or "").strip(), safe="")
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{encoded_tag}"
    return _github_json(url, timeout=timeout, token=token)


def _print_group_summary(title: str, assets: list[ExpectedAsset], release_asset_names: set[str]) -> None:
    if not assets:
        print(f"{title}: 0 expected")
        return

    expected_counts = Counter(asset.group for asset in assets)
    found_counts = Counter(asset.group for asset in assets if asset.name in release_asset_names)
    print(title)
    for group in sorted(expected_counts):
        print(f"- {group}: {found_counts.get(group, 0)}/{expected_counts[group]}")


def _print_asset_list(title: str, names: list[str]) -> None:
    print(title)
    if not names:
        print("- none")
        return
    for name in names:
        print(f"- {name}")


def _list_expected_assets(tag: str) -> int:
    version, expected_assets = _build_expected_assets(tag)
    required_assets = [asset for asset in expected_assets if asset.required]
    optional_assets = [asset for asset in expected_assets if not asset.required]

    print(f"Expected release assets for tag: {tag}")
    print(f"Resolved asset version: {version}")
    print(f"Required assets: {len(required_assets)}")
    print(f"Optional framework assets: {len(optional_assets)}")
    print()
    _print_group_summary("Required asset groups", required_assets, {asset.name for asset in required_assets})
    print()
    _print_group_summary("Optional asset groups", optional_assets, {asset.name for asset in optional_assets})
    print()
    _print_asset_list("Required assets", [asset.name for asset in required_assets])
    print()
    _print_asset_list("Optional assets", [asset.name for asset in optional_assets])
    return 0


def main() -> int:
    default_owner, default_repo = _resolve_default_repo()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Git tag to validate, for example: v1.0.30")
    parser.add_argument("--owner", default=default_owner, help=f"GitHub owner (default: {default_owner})")
    parser.add_argument("--repo", default=default_repo, help=f"GitHub repo (default: {default_repo})")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="GitHub API timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--list-expected",
        action="store_true",
        help="Print the expected release matrix for the tag without contacting GitHub.",
    )
    parser.add_argument(
        "--show-present",
        action="store_true",
        help="Also print the expected assets that are present on the release.",
    )
    args = parser.parse_args()

    if args.list_expected:
        return _list_expected_assets(args.tag)

    token = (
        str(os.environ.get("GITHUB_TOKEN") or "").strip()
        or str(os.environ.get("GH_TOKEN") or "").strip()
        or None
    )

    version, expected_assets = _build_expected_assets(args.tag)
    expected_by_name = {asset.name: asset for asset in expected_assets}
    required_assets = [asset for asset in expected_assets if asset.required]
    optional_assets = [asset for asset in expected_assets if not asset.required]

    try:
        payload = _fetch_release(
            args.tag,
            owner=str(args.owner).strip(),
            repo=str(args.repo).strip(),
            timeout=args.timeout,
            token=token,
        )
    except RuntimeError as exc:
        print(f"Release check failed: {exc}", file=sys.stderr)
        return 1

    release_asset_rows = payload.get("assets")
    if not isinstance(release_asset_rows, list):
        print("Release check failed: GitHub release payload does not contain an asset list.", file=sys.stderr)
        return 1

    release_asset_names = {
        str(row.get("name") or "").strip()
        for row in release_asset_rows
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }

    present_required = sorted(asset.name for asset in required_assets if asset.name in release_asset_names)
    missing_required = sorted(asset.name for asset in required_assets if asset.name not in release_asset_names)
    present_optional = sorted(asset.name for asset in optional_assets if asset.name in release_asset_names)
    missing_optional = sorted(asset.name for asset in optional_assets if asset.name not in release_asset_names)
    additional_assets = sorted(name for name in release_asset_names if name not in expected_by_name)

    print(f"Release: {args.owner}/{args.repo}")
    print(f"Tag: {args.tag}")
    print(f"Resolved asset version: {version}")
    print(f"Release URL: {str(payload.get('html_url') or '').strip() or 'Unknown'}")
    print(f"Published at: {str(payload.get('published_at') or '').strip() or 'Unknown'}")
    print(f"Assets on release: {len(release_asset_names)}")
    print()
    print(f"Required assets: {len(present_required)}/{len(required_assets)} present")
    print(f"Optional framework assets: {len(present_optional)}/{len(optional_assets)} present")
    print()
    _print_group_summary("Required asset groups", required_assets, release_asset_names)
    print()
    _print_group_summary("Optional asset groups", optional_assets, release_asset_names)
    print()

    if args.show_present:
        _print_asset_list("Present required assets", present_required)
        print()
        _print_asset_list("Present optional assets", present_optional)
        print()

    _print_asset_list("Missing required assets", missing_required)
    print()
    _print_asset_list("Missing optional assets", missing_optional)
    print()
    _print_asset_list("Additional release assets", additional_assets)

    if missing_required:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
