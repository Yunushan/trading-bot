#!/usr/bin/env python3
"""Check whether a complete, installable PyQt6 future family is published."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen


PYQT6_PACKAGE_NAMES = (
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-WebEngine",
    "PyQt6-WebEngine-Qt6",
)
PLATFORM_WHEEL_MARKERS = {
    "ubuntu-24.04": ("manylinux_", "linux_"),
    "windows-2025": ("win_amd64",),
    "macos-15": ("macosx_",),
}
_STABLE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def stable_version(value: object) -> tuple[int, int, int] | None:
    match = _STABLE_VERSION_RE.fullmatch(str(value or ""))
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def stable_series(value: object) -> tuple[int, int] | None:
    parsed = stable_version(value)
    return parsed[:2] if parsed is not None else None


def has_installable_wheel(files: object, wheel_markers: tuple[str, ...]) -> bool:
    """Return whether PyPI metadata has a non-yanked wheel for this runner."""

    if not isinstance(files, list):
        return False
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        filename = str(file_info.get("filename") or "").lower()
        if file_info.get("packagetype") != "bdist_wheel":
            continue
        if not filename.endswith(".whl") or file_info.get("yanked", False):
            continue
        platform_part = filename[:-4].rsplit("-", 1)[-1]
        if any(
            platform_tag.startswith(marker)
            for platform_tag in platform_part.split(".")
            for marker in wheel_markers
        ):
            return True
    return False


def package_has_installable_release(
    package_name: str,
    releases: object,
    target: str,
    target_series: tuple[int, int],
    wheel_markers: tuple[str, ...],
) -> bool:
    if not isinstance(releases, dict):
        return False
    if package_name == "PyQt6":
        return has_installable_wheel(releases.get(target, []), wheel_markers)
    return any(
        stable_series(version) == target_series
        and has_installable_wheel(files, wheel_markers)
        for version, files in releases.items()
    )


def _fetch_package_json(package_name: str) -> dict[str, Any]:
    request = Request(
        f"https://pypi.org/pypi/{package_name}/json",
        headers={"User-Agent": "trading-bot-pyqt6-future-compatibility"},
    )
    with urlopen(  # noqa: S310 - fixed HTTPS PyPI endpoint
        request,
        timeout=20,
        context=_pypi_ssl_context(),
    ) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"PyPI returned an invalid metadata document for {package_name}")
    return payload


def _pypi_ssl_context() -> ssl.SSLContext:
    """Use the host trust store, falling back to the bundled public CA set."""

    try:
        import truststore
    except ImportError:
        try:
            import certifi
        except ImportError:
            return ssl.create_default_context()
        return ssl.create_default_context(cafile=certifi.where())
    else:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def check_family(
    target: str,
    platform_name: str,
    metadata_loader: Callable[[str], dict[str, Any]] = _fetch_package_json,
) -> tuple[dict[str, bool], tuple[int, int]]:
    target_release = stable_version(target)
    if target_release is None:
        raise ValueError(f"Invalid PyQt6 target version {target!r}; use MAJOR.MINOR.PATCH")
    wheel_markers = PLATFORM_WHEEL_MARKERS.get(platform_name)
    if wheel_markers is None:
        raise ValueError(f"Unsupported PyQt6 compatibility runner {platform_name!r}")

    target_series = target_release[:2]
    package_status: dict[str, bool] = {}
    for package_name in PYQT6_PACKAGE_NAMES:
        payload = metadata_loader(package_name)
        package_status[package_name] = package_has_installable_release(
            package_name,
            payload.get("releases"),
            target,
            target_series,
            wheel_markers,
        )
    return package_status, target_series


def _write_github_output(path: str, available: bool) -> None:
    with open(path, "a", encoding="utf-8") as output:
        output.write(f"available={'true' if available else 'false'}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="stable PyQt6 release to check")
    parser.add_argument("--platform", required=True, help="GitHub Actions runner identifier")
    parser.add_argument("--github-output", help="GITHUB_OUTPUT path to receive available=true|false")
    args = parser.parse_args(argv)

    target = args.target.strip()
    platform_name = args.platform.strip()
    try:
        package_status, target_series = check_family(target, platform_name)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    available = all(package_status.values())
    if args.github_output:
        _write_github_output(args.github_output, available)
    status_text = ", ".join(
        f"{package_name}={'published' if is_available else 'not yet published'}"
        for package_name, is_available in package_status.items()
    )
    print(f"PyQt6 {target_series[0]}.{target_series[1]} family status for {platform_name}: {status_text}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
