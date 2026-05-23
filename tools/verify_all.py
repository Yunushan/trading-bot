from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path
    required: bool = True
    remediation: str = ""
    blocks_success: bool = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _python() -> str:
    return sys.executable


def _command_path(name: str) -> str:
    candidates = (name, f"{name}.cmd") if sys.platform == "win32" else (name,)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return name


def _read_version_file(name: str) -> str:
    path = _repo_root() / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _declared_python_command() -> str:
    expected = _read_version_file(".python-version") or "3.14"
    if sys.platform == "win32":
        return f"py -{expected}" if shutil.which("py") else "python"
    return f"python{expected}"


def _python_install_remediation(extra: str) -> str:
    selected_python = _declared_python_command()
    return (
        "Install Python dependencies through the declared-runtime bootstrap: "
        f'python tools/bootstrap_local_dev.py --python-command "{selected_python}" --skip-client-deps. '
        "For a direct install with the selected interpreter, run: "
        f'{selected_python} -m pip install -e "Languages/Python[{extra}]".'
    )


def _mypy_cache_dir() -> str:
    return str(Path(tempfile.gettempdir()) / "trading-bot-mypy-cache")


def _checks(root: Path, *, skip_slow: bool) -> list[Check]:
    python = _python()
    npm = _command_path("npm")
    checks = [
        Check(
            "tool versions",
            (python, "tools/check_local_tool_versions.py", "--json"),
            root,
            required=False,
            remediation="Use the runtime versions declared in .python-version and .node-version.",
            blocks_success=True,
        ),
        Check("worktree summary", (python, "tools/summarize_worktree_changes.py", "--json"), root, required=False),
        Check(
            "workspace hygiene",
            (python, "tools/audit_workspace_hygiene.py", "--json"),
            root,
            required=False,
            remediation="Preview cleanup with: python tools/clean_workspace_artifacts.py --json",
        ),
        Check(
            "client dependency locks",
            (python, "tools/check_client_dependency_locks.py", "--json", "--strict"),
            root,
            required=False,
            remediation="Refresh missing client lockfiles with: npm install --package-lock-only",
        ),
        Check("risky pattern audit", (python, "tools/audit_risky_patterns.py", "--json", "--summary"), root, required=False),
        Check(
            "python lint",
            (
                python,
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--config",
                "Languages/Python/pyproject.toml",
                "Languages/Python",
            ),
            root,
            remediation=_python_install_remediation("dev"),
        ),
        Check(
            "python type check",
            (
                python,
                "-m",
                "mypy",
                "--no-incremental",
                "--cache-dir",
                _mypy_cache_dir(),
                "--config-file",
                "pyproject.toml",
            ),
            root / "Languages" / "Python",
            remediation=_python_install_remediation("dev"),
        ),
        Check(
            "service API contracts",
            (python, "Languages/Python/tools/check_service_api_contracts.py"),
            root,
            remediation=_python_install_remediation("service"),
        ),
        Check(
            "service tests",
            (python, "Languages/Python/tools/run_service_tests.py"),
            root,
            remediation=_python_install_remediation("service,dev"),
        ),
        Check(
            "web dashboard tests",
            (npm, "test"),
            root / "apps" / "web-dashboard",
            remediation="Install web dashboard dependencies with: npm install",
        ),
        Check(
            "mobile client tests",
            (npm, "test"),
            root / "apps" / "mobile-client",
            remediation="Install mobile client dependencies with: npm install",
        ),
        Check("diff whitespace", ("git", "diff", "--check"), root),
    ]
    if not skip_slow:
        checks.insert(
            3,
            Check(
                "python tests",
                (python, "Languages/Python/tools/run_python_tests.py"),
                root,
                remediation=_python_install_remediation("desktop,service,dev"),
            ),
        )
        checks.append(
            Check(
                "python source compile",
                (
                    python,
                    "tools/check_python_sources_compile.py",
                    "apps/desktop-pyqt/main.py",
                    "apps/service-api/main.py",
                    "Languages/Python/app",
                    "Languages/Python/trading_core",
                    "Languages/Python/main.py",
                    "Languages/Python/tools",
                    "tools",
                ),
                root,
            )
        )
    checks.append(
        Check(
            "ruff availability",
            (python, "-m", "ruff", "--version"),
            root,
            required=False,
            remediation=_python_install_remediation("dev"),
        )
    )
    return checks


def _load_json_object(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_remediation(stdout: str) -> str:
    payload = _load_json_object(stdout)
    remediations = payload.get("remediations")
    if isinstance(remediations, list):
        parsed = [str(item).strip() for item in remediations if str(item).strip()]
        if parsed:
            return " ".join(parsed)
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return ""
    mismatches: list[str] = []
    for name, item in checks.items():
        if not isinstance(item, dict) or item.get("ok"):
            continue
        expected = str(item.get("expected") or "").strip() or "declared"
        actual = str(item.get("actual") or "").strip() or "missing"
        mismatches.append(f"{name} expected {expected}, actual {actual}")
    if not mismatches:
        return ""
    return "Use repo runtime versions before verifying: " + "; ".join(mismatches)


def _client_lock_remediation(stdout: str) -> str:
    payload = _load_json_object(stdout)
    clients = payload.get("clients")
    if not isinstance(clients, list):
        return ""
    missing_paths = []
    for item in clients:
        if not isinstance(item, dict) or item.get("lockfile_exists", True):
            continue
        path = str(item.get("path") or "").strip()
        if path:
            missing_paths.append(path)
    if not missing_paths:
        return ""
    commands = [f"cd {path} && npm install --package-lock-only" for path in missing_paths]
    return "Create missing client lockfiles: " + "; ".join(commands)


def _workspace_hygiene_remediation(stdout: str) -> str:
    payload = _load_json_object(stdout)
    noisy_count = payload.get("noisy_artifact_count")
    if isinstance(noisy_count, int) and noisy_count > 0:
        return "Remove generated workspace noise with: python tools/clean_workspace_artifacts.py --apply"
    return ""


def _check_ok_from_output(*, check: Check, returncode: int, stdout: str) -> bool:
    if returncode != 0:
        return False
    payload = _load_json_object(stdout)
    payload_ok = payload.get("ok")
    if isinstance(payload_ok, bool):
        return payload_ok
    return True


def _missing_python_dependency_remediation(output: str, *, extra: str = "service,dev") -> str:
    missing_modules = ("No module named", "ModuleNotFoundError")
    dependency_names = ("PyQt6", "httpx", "requests", "fastapi", "uvicorn", "pydantic")
    if any(marker in output for marker in missing_modules) or "pip install httpx" in output:
        if any(name in output for name in dependency_names):
            return _python_install_remediation(extra)
    return ""


def _remediation_for(check: Check, *, returncode: int | None, stdout: str, stderr: str) -> str:
    output = f"{stdout}\n{stderr}"
    if check.name == "tool versions":
        return _runtime_remediation(stdout) or (check.remediation if returncode not in (0, None) else "")
    if check.name == "client dependency locks":
        return _client_lock_remediation(stdout) or (check.remediation if returncode not in (0, None) else "")
    if check.name == "workspace hygiene":
        return _workspace_hygiene_remediation(stdout) or (check.remediation if returncode not in (0, None) else "")
    if returncode == 0:
        return ""
    python_extra = "desktop,service,dev" if check.name == "python tests" else "service,dev"
    return _missing_python_dependency_remediation(output, extra=python_extra) or check.remediation


def _run_check(check: Check, *, verbose: bool) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run(
            list(check.command),
            cwd=check.cwd,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": check.name,
            "required": check.required,
            "blocks_success": check.blocks_success,
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "remediation": check.remediation,
        }
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    ok = _check_ok_from_output(check=check, returncode=result.returncode, stdout=stdout)
    payload = {
        "name": check.name,
        "required": check.required,
        "blocks_success": check.blocks_success,
        "ok": ok,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    remediation = _remediation_for(check, returncode=result.returncode, stdout=stdout, stderr=stderr)
    if remediation:
        payload["remediation"] = remediation
    if not verbose:
        payload["stdout"] = "\n".join(payload["stdout"].splitlines()[-8:])
        payload["stderr"] = "\n".join(payload["stderr"].splitlines()[-8:])
    return payload


def _collect_remediations(results: list[dict[str, object]]) -> list[str]:
    remediations: list[str] = []
    for item in results:
        remediation = item.get("remediation")
        if not isinstance(remediation, str) or not remediation:
            continue
        if remediation not in remediations:
            remediations.append(remediation)
    return remediations


def _report_ok(results: list[dict[str, object]]) -> bool:
    blocking_results = [
        item for item in results if bool(item.get("required")) or bool(item.get("blocks_success"))
    ]
    return all(bool(item.get("ok")) for item in blocking_results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the repository verification suite from one command.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--skip-slow", action="store_true", help="Skip the full Python test suite and source compile.")
    parser.add_argument("--verbose", action="store_true", help="Keep full stdout/stderr in JSON output.")
    args = parser.parse_args(argv)
    root = _repo_root()
    results = [_run_check(check, verbose=args.verbose) for check in _checks(root, skip_slow=args.skip_slow)]
    ok = _report_ok(results)
    report = {"ok": ok, "results": results, "remediations": _collect_remediations(results)}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in results:
            status = "ok" if item["ok"] else "failed"
            if item["required"]:
                weight = "required"
            elif item.get("blocks_success"):
                weight = "blocking advisory"
            else:
                weight = "advisory"
            print(f"{item['name']}: {status} ({weight})")
            if item["stdout"]:
                print(item["stdout"])
            if item["stderr"]:
                print(item["stderr"])
            if item.get("remediation"):
                print(f"remediation: {item['remediation']}")
        if report["remediations"]:
            print("Recommended fixes:")
            for remediation in report["remediations"]:
                print(f"- {remediation}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
