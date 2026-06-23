"""Browser contract command helpers for release-platform evidence targets."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Mapping


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


def browser_contract_command_args(
    target: dict[str, Any],
    *,
    npm_executable: str | Path | None = None,
    node_executable: str | Path | None = None,
) -> list[str] | None:
    browser = browser_name_from_target(target)
    if browser not in SUPPORTED_BROWSER_CONTRACT_COMMANDS:
        return None
    if npm_executable:
        return [
            str(npm_executable),
            "--prefix",
            "apps/web-dashboard",
            "run",
            "test:browser",
            "--",
            f"--browser={browser}",
        ]
    if node_executable:
        return [
            str(node_executable),
            "apps/web-dashboard/tests/browser-contract.test.mjs",
            f"--browser={browser}",
        ]
    return None


def browser_contract_tool(
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] | None = None,
    platform_name: str | None = None,
    path_is_file: Callable[[Path], bool] | None = None,
    path_is_executable: Callable[[Path], bool] | None = None,
) -> dict[str, Any]:
    platform_name = platform_name or sys.platform
    environ = environ or os.environ
    which = which or shutil.which
    path_is_file = path_is_file or (lambda path: path.is_file())
    path_is_executable = path_is_executable or (
        lambda path: True if platform_name == "win32" else os.access(path, os.X_OK)
    )
    npm_name = "npm.cmd" if platform_name == "win32" else "npm"
    node_name = "node.exe" if platform_name == "win32" else "node"

    npm = which(npm_name)
    if npm:
        return {
            "kind": "npm",
            "required_tool": npm_name,
            "executable": npm,
            "npm_available": True,
            "tool_available": True,
            "unavailable_reason": "",
        }

    node_env = str(environ.get("TB_BROWSER_NODE_EXECUTABLE") or "").strip()
    if node_env:
        node_path = Path(node_env).expanduser()
        if path_is_file(node_path) and path_is_executable(node_path):
            return {
                "kind": "node",
                "required_tool": "TB_BROWSER_NODE_EXECUTABLE",
                "executable": str(node_path),
                "npm_available": False,
                "tool_available": True,
                "unavailable_reason": "",
            }
        return {
            "kind": "",
            "required_tool": "TB_BROWSER_NODE_EXECUTABLE",
            "executable": node_env,
            "npm_available": False,
            "tool_available": False,
            "unavailable_reason": (
                "TB_BROWSER_NODE_EXECUTABLE must point to an existing executable Node.js file"
            ),
        }

    node = which(node_name)
    if node:
        return {
            "kind": "node",
            "required_tool": node_name,
            "executable": node,
            "npm_available": False,
            "tool_available": True,
            "unavailable_reason": "",
        }
    return {
        "kind": "",
        "required_tool": f"{npm_name} or {node_name}",
        "executable": "",
        "npm_available": False,
        "tool_available": False,
        "unavailable_reason": (
            f"{npm_name} or {node_name} is not on PATH; "
            "set TB_BROWSER_NODE_EXECUTABLE to a Node.js executable"
        ),
    }


def browser_contract_missing_command_message(target: dict[str, Any]) -> str:
    browser = browser_name_from_target(target)
    if browser in SUPPORTED_BROWSER_CONTRACT_COMMANDS:
        return (
            f"npm or node is not on PATH; cannot run {browser} browser contract command. "
            "Set TB_BROWSER_NODE_EXECUTABLE to a Node.js executable for the direct Node harness."
        )
    if browser:
        return f"Set TB_BROWSER_TEST_COMMAND to the real {browser} browser contract command for this target."
    return "Set TB_BROWSER_TEST_COMMAND to the real browser contract command for this target."
