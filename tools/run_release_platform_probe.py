#!/usr/bin/env python3
"""Run release-platform smoke probes and write a real evidence artifact."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from check_release_platform_matrix import DEFAULT_MATRIX_PATH, _load_json, _validate_matrix


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_target(target_id: str, matrix_path: Path) -> dict[str, Any]:
    matrix = _load_json(matrix_path)
    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    if issues:
        raise RuntimeError("matrix is invalid: " + "; ".join(issues))
    for target in platform_targets + browser_targets:
        if target["id"] == target_id:
            return target
    raise RuntimeError(f"unknown target id: {target_id}")


def _run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 240,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name,
            "status": "failed",
            "command": command,
            "duration_seconds": round(time.time() - started, 3),
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "command": command,
        "duration_seconds": round(time.time() - started, 3),
        "returncode": result.returncode,
        "stdout": "\n".join(result.stdout.strip().splitlines()[-40:]),
        "stderr": "\n".join(result.stderr.strip().splitlines()[-40:]),
    }


def _shell_command_from_env(name: str) -> list[str] | None:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return None
    if sys.platform == "win32":
        return ["cmd", "/c", raw]
    return ["sh", "-lc", raw]


def _suite_results(target: dict[str, Any], *, root: Path) -> list[dict[str, Any]]:
    suites = [str(item) for item in target.get("test_suites", [])]
    results: list[dict[str, Any]] = []

    if "platform-probe" in suites:
        results.append(
            {
                "name": "platform-probe",
                "status": "passed",
                "observed": {
                    "platform": platform.platform(),
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "python": sys.version.split()[0],
                    "executable": sys.executable,
                },
            }
        )

    if "python-service-contract" in suites:
        results.append(
            _run_command(
                "python-service-contract",
                [
                    sys.executable,
                    "tools/check_python_sources_compile.py",
                    "apps/service-api/main.py",
                    "Languages/Python/app/service",
                    "Languages/Python/app/settings",
                    "Languages/Python/trading_core",
                ],
                cwd=root,
            )
        )
        results.append(
            _run_command(
                "python-service-healthcheck",
                [sys.executable, "apps/service-api/main.py", "--healthcheck"],
                cwd=root,
            )
        )

    if "desktop-release-smoke" in suites:
        command = _shell_command_from_env("TB_RELEASE_DESKTOP_SMOKE_COMMAND")
        if command is None:
            results.append(
                {
                    "name": "desktop-release-smoke",
                    "status": "failed",
                    "stderr": "Set TB_RELEASE_DESKTOP_SMOKE_COMMAND to the real release binary smoke command for this runner.",
                }
            )
        else:
            results.append(_run_command("desktop-release-smoke", command, cwd=root, timeout=600))

    if "native-build-smoke" in suites:
        cargo = shutil.which("cargo")
        if cargo:
            results.append(
                _run_command(
                    "rust-workspace-check",
                    [cargo, "check", "--manifest-path", "experiments/rust-shells/Cargo.toml", "--workspace"],
                    cwd=root,
                    timeout=900,
                )
            )
        else:
            results.append({"name": "rust-workspace-check", "status": "failed", "stderr": "cargo is not on PATH"})

    if "mobile-client-contract" in suites:
        npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
        if npm:
            results.append(_run_command("mobile-client-contract", [npm, "test"], cwd=root / "apps" / "mobile-client"))
        else:
            results.append({"name": "mobile-client-contract", "status": "failed", "stderr": "npm is not on PATH"})

    if "browser-contract" in suites:
        command = _shell_command_from_env("TB_BROWSER_TEST_COMMAND")
        if command is None:
            results.append(
                {
                    "name": "browser-contract",
                    "status": "failed",
                    "stderr": "Set TB_BROWSER_TEST_COMMAND to the real browser test command for this target.",
                }
            )
        else:
            results.append(_run_command("browser-contract", command, cwd=root, timeout=900))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True, help="Target id from tools/check_release_platform_matrix.py.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH), help="Path to release platform matrix JSON.")
    parser.add_argument("--output", required=True, help="Evidence JSON path to write.")
    args = parser.parse_args(argv)

    root = _repo_root()
    target = _find_target(args.target_id, Path(args.matrix))
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    suite_results = _suite_results(target, root=root)
    ok = bool(suite_results) and all(item.get("status") == "passed" for item in suite_results)
    payload = {
        "target_id": args.target_id,
        "status": "passed" if ok else "failed",
        "started_at": started,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": target,
        "suite_results": suite_results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": ok, "target_id": args.target_id, "output": str(output)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
