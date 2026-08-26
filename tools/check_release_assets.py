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

WINDOWS_ASSET_TAGS = (
    "windows-x64",
    "windows-arm64",
)
LINUX_ARCHES = (
    ("x86_64", "amd64", "x86_64"),
    ("aarch64", "arm64", "aarch64"),
)
MACOS_ASSET_TAGS = (
    "macos-14-arm64",
    "macos-15-intel",
    "macos-15-arm64",
    "macos-26-arm64",
)
RELEASE_METADATA_IDS = (
    "windows-x64",
    "windows-arm64",
    "linux-x64",
    "linux-arm64",
    "macos-14-arm64",
    "macos-15-intel",
    "macos-15-arm64",
    "macos-26-arm64",
)
REQUIRED_RUST_PREFIXES = (
    "Trading-Bot-Rust-tauri",
)
NATIVE_SIGNING_REQUIRED_SINCE = (1, 0, 41)
RELEASE_ASSET_INTEGRITY_REQUIRED_SINCE = (1, 0, 41)
SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
HTTP_STATUS_PATTERN = re.compile(r"\bHTTP\s+(?P<status>[1-5][0-9]{2})\b", re.IGNORECASE)


class GitHubApiError(RuntimeError):
    """GitHub API failure with an optional HTTP status for fail-closed callers."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _http_status_from_error_text(value: str) -> int | None:
    match = HTTP_STATUS_PATTERN.search(str(value or ""))
    return int(match.group("status")) if match else None


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


def _native_signing_required(tag: str) -> bool:
    match = VERSION_PATTERN.search(str(tag or "").strip())
    if not match:
        return False
    numeric_parts = [int(part) for part in re.findall(r"\d+", match.group(1))[:3]]
    numeric_parts.extend([0] * (3 - len(numeric_parts)))
    return tuple(numeric_parts) >= NATIVE_SIGNING_REQUIRED_SINCE


def _asset_integrity_metadata_required(tag: str) -> bool:
    match = VERSION_PATTERN.search(str(tag or "").strip())
    if not match:
        return False
    numeric_parts = [int(part) for part in re.findall(r"\d+", match.group(1))[:3]]
    numeric_parts.extend([0] * (3 - len(numeric_parts)))
    return tuple(numeric_parts) >= RELEASE_ASSET_INTEGRITY_REQUIRED_SINCE


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
        for rust_prefix in REQUIRED_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-{asset_tag}-{version}.exe", True, group))

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
        for rust_prefix in REQUIRED_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-linux-{arch}-{version}.tar.gz", True, group))

    for asset_tag in MACOS_ASSET_TAGS:
        group = f"macOS {asset_tag.removeprefix('macos-')}"
        assets.extend(
            [
                ExpectedAsset(f"Trading-Bot-Python-{asset_tag}-{version}.zip", True, group),
                ExpectedAsset(f"Trading-Bot-Rust-{asset_tag}-{version}.zip", True, group),
                ExpectedAsset(f"Trading-Bot-C++-{asset_tag}-{version}.zip", True, group),
            ]
        )
        for rust_prefix in REQUIRED_RUST_PREFIXES:
            assets.append(ExpectedAsset(f"{rust_prefix}-{asset_tag}-{version}.zip", True, group))

    for release_id in RELEASE_METADATA_IDS:
        group = f"Release integrity {release_id}"
        assets.extend(
            [
                ExpectedAsset(f"release-manifest-{release_id}.json", True, group),
                ExpectedAsset(f"release-sbom-{release_id}.spdx.json", True, group),
            ]
        )

    signing_required = _native_signing_required(tag)
    for release_id in (*WINDOWS_ASSET_TAGS, *MACOS_ASSET_TAGS):
        group = f"Native signing {release_id}"
        assets.append(
            ExpectedAsset(
                f"release-signing-{release_id}.json",
                signing_required,
                group,
            )
        )

    return version, assets


def _missing_required_assets(
    expected_assets: list[ExpectedAsset], release_asset_names: set[str]
) -> list[str]:
    """Return required release files absent from the published asset names."""

    return sorted(
        asset.name
        for asset in expected_assets
        if asset.required and asset.name not in release_asset_names
    )


def _release_payload_issues(
    payload: dict,
    *,
    tag: str,
    expected_assets: list[ExpectedAsset],
    require_prerelease_candidate: bool = False,
) -> list[str]:
    """Return release-state and required-asset metadata defects."""

    issues: list[str] = []
    if str(payload.get("tag_name") or "").strip() != tag:
        issues.append("release payload tag_name does not match the requested tag")
    if require_prerelease_candidate:
        if payload.get("draft") is not False:
            issues.append("release candidate must be published, not draft")
        if payload.get("prerelease") is not True:
            issues.append("release candidate must still be marked prerelease")

    rows = payload.get("assets")
    if not isinstance(rows, list):
        issues.append("release payload does not contain an asset list")
        return issues

    rows_by_name: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            rows_by_name.setdefault(name, []).append(row)

    require_digest = _asset_integrity_metadata_required(tag)
    for expected in expected_assets:
        if not expected.required or expected.name not in rows_by_name:
            continue
        matching_rows = rows_by_name[expected.name]
        if len(matching_rows) != 1:
            issues.append(
                f"required release asset {expected.name!r} must appear exactly once"
            )
            continue
        row = matching_rows[0]
        if str(row.get("state") or "").strip().lower() != "uploaded":
            issues.append(
                f"required release asset {expected.name!r} is not fully uploaded"
            )
        size = row.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            issues.append(
                f"required release asset {expected.name!r} must have a positive byte size"
            )
        if require_digest and not SHA256_DIGEST_PATTERN.fullmatch(
            str(row.get("digest") or "").strip()
        ):
            issues.append(
                f"required release asset {expected.name!r} must expose a GitHub SHA-256 digest"
            )
    return issues


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
        raise GitHubApiError(
            message,
            status=_http_status_from_error_text(detail),
        )

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows certificate-store fallback returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Windows certificate-store fallback returned an unexpected response type.")
    return result


def _github_json_from_gh_cli(
    url: str,
    *,
    timeout: float,
    token: str | None,
) -> dict:
    """Fetch a GitHub API object through the authenticated GitHub CLI."""

    gh = shutil.which("gh")
    if not gh:
        raise RuntimeError("GitHub CLI fallback is unavailable.")

    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or not parsed.path:
        raise RuntimeError("GitHub CLI fallback only supports api.github.com URLs.")

    endpoint = parsed.path.lstrip("/")
    if parsed.query:
        endpoint = f"{endpoint}?{parsed.query}"

    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token

    try:
        completed = subprocess.run(
            [
                gh,
                "api",
                endpoint,
                "--header",
                "Accept: application/vnd.github+json",
                "--header",
                f"User-Agent: {USER_AGENT}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(10.0, float(timeout or 10.0) + 5.0),
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"GitHub CLI fallback failed to run: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        message = "GitHub API request failed through GitHub CLI fallback."
        if detail:
            message = f"{message} {detail}"
        raise GitHubApiError(
            message,
            status=_http_status_from_error_text(detail),
        )

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI fallback returned invalid JSON.") from exc
    if not isinstance(result, dict):
        raise RuntimeError("GitHub CLI fallback returned an unexpected response type.")
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
        raise GitHubApiError(message, status=exc.code) from exc
    except urllib.error.URLError as exc:
        if _is_ssl_certificate_error(exc):
            fallback_error: RuntimeError | None = None
            try:
                return _github_json_from_windows_certificate_store(
                    url,
                    timeout=timeout,
                    token=token,
                )
            except GitHubApiError as fallback_exc:
                if fallback_exc.status is not None:
                    raise
                fallback_error = fallback_exc
            except RuntimeError as fallback_exc:
                fallback_error = fallback_exc
            try:
                return _github_json_from_gh_cli(
                    url,
                    timeout=timeout,
                    token=token,
                )
            except GitHubApiError as cli_exc:
                if cli_exc.status is not None:
                    raise
                raise RuntimeError(
                    "Could not reach GitHub API with Python TLS validation; the "
                    f"Windows certificate-store fallback failed: {fallback_error}; "
                    f"the GitHub CLI fallback also failed: {cli_exc}"
                ) from exc
            except RuntimeError as cli_exc:
                raise RuntimeError(
                    "Could not reach GitHub API with Python TLS validation; the "
                    f"Windows certificate-store fallback failed: {fallback_error}; "
                    f"the GitHub CLI fallback also failed: {cli_exc}"
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
    parser.add_argument(
        "--require-prerelease-candidate",
        action="store_true",
        help=(
            "Require a published prerelease candidate with complete, non-empty, "
            "digest-bearing required assets before stable promotion."
        ),
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
    payload_issues = _release_payload_issues(
        payload,
        tag=args.tag,
        expected_assets=expected_assets,
        require_prerelease_candidate=args.require_prerelease_candidate,
    )

    present_required = sorted(asset.name for asset in required_assets if asset.name in release_asset_names)
    missing_required = _missing_required_assets(expected_assets, release_asset_names)
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
    print()
    _print_asset_list("Release payload issues", payload_issues)

    if missing_required or payload_issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
