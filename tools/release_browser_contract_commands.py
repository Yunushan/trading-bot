"""Browser contract command helpers for release-platform evidence targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_BROWSER_CONTRACT_COMMANDS = {
    "chrome": "npm --prefix apps/web-dashboard run test:browser -- --browser=chrome",
    "edge": "npm --prefix apps/web-dashboard run test:browser -- --browser=edge",
}


def browser_name_from_target(target: dict[str, Any]) -> str:
    browser = str(target.get("browser") or "").strip().lower()
    if browser:
        return browser
    target_id = str(target.get("id") or "").strip().lower()
    if target_id.startswith("browser-"):
        return target_id.split("-", 2)[1]
    return ""


def browser_contract_command_text(target: dict[str, Any]) -> str:
    browser = browser_name_from_target(target)
    command = SUPPORTED_BROWSER_CONTRACT_COMMANDS.get(browser)
    if command:
        return command
    label = browser or "target"
    return f"<real {label} browser contract command from external lab>"


def has_builtin_browser_contract_command(target: dict[str, Any]) -> bool:
    return browser_name_from_target(target) in SUPPORTED_BROWSER_CONTRACT_COMMANDS


def browser_host_from_observed_platform(observed: dict[str, Any]) -> str:
    system = str(observed.get("system") or "")
    arch = str(observed.get("normalized_architecture") or "")
    if not arch:
        return ""

    if system == "Windows":
        release = str(observed.get("release") or "").strip()
        if release:
            return f"windows-{release}-{arch}"
    if system == "Linux" and str(observed.get("os_release_id") or "").lower() == "ubuntu":
        version = str(observed.get("os_release_version_id") or "").strip().replace(".", "_")
        if version:
            return f"ubuntu-{version}-{arch}"
    if system == "Darwin":
        major = str(observed.get("macos_version") or "").split(".", 1)[0]
        if major:
            return f"macos-{major}-{arch}"
    return ""


def builtin_browser_contract_targets_for_host(targets: list[dict[str, Any]], host: str) -> list[dict[str, Any]]:
    if not host:
        return []
    return [
        target
        for target in targets
        if str(target.get("host") or "") == host
        and has_builtin_browser_contract_command(target)
    ]


def browser_contract_command_args(target: dict[str, Any], *, npm_executable: str | Path) -> list[str] | None:
    browser = browser_name_from_target(target)
    if browser not in SUPPORTED_BROWSER_CONTRACT_COMMANDS:
        return None
    return [
        str(npm_executable),
        "--prefix",
        "apps/web-dashboard",
        "run",
        "test:browser",
        "--",
        f"--browser={browser}",
    ]


def browser_contract_missing_command_message(target: dict[str, Any]) -> str:
    browser = browser_name_from_target(target)
    if browser in SUPPORTED_BROWSER_CONTRACT_COMMANDS:
        return f"npm is not on PATH; cannot run {browser} browser contract command."
    if browser:
        return f"Set TB_BROWSER_TEST_COMMAND to the real {browser} browser contract command for this target."
    return "Set TB_BROWSER_TEST_COMMAND to the real browser contract command for this target."
