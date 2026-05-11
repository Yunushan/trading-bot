from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path
    required: bool = True


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


def _checks(root: Path, *, skip_slow: bool) -> list[Check]:
    python = _python()
    npm = _command_path("npm")
    checks = [
        Check("tool versions", (python, "tools/check_local_tool_versions.py", "--json"), root, required=False),
        Check("worktree summary", (python, "tools/summarize_worktree_changes.py", "--json"), root, required=False),
        Check("workspace hygiene", (python, "tools/audit_workspace_hygiene.py", "--json"), root, required=False),
        Check("risky pattern audit", (python, "tools/audit_risky_patterns.py", "--json"), root, required=False),
        Check("service API contracts", (python, "Languages/Python/tools/check_service_api_contracts.py"), root),
        Check("service tests", (python, "Languages/Python/tools/run_service_tests.py"), root),
        Check("web dashboard tests", (npm, "test"), root / "apps" / "web-dashboard"),
        Check("mobile client tests", (npm, "test"), root / "apps" / "mobile-client"),
        Check("diff whitespace", ("git", "diff", "--check"), root),
    ]
    if not skip_slow:
        checks.insert(3, Check("python tests", (python, "-m", "unittest", "discover", "Languages/Python/tests"), root))
        checks.append(
            Check(
                "compileall",
                (
                    python,
                    "-m",
                    "compileall",
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
    checks.append(Check("ruff availability", (python, "-m", "ruff", "--version"), root, required=False))
    return checks


def _run_check(check: Check, *, verbose: bool) -> dict[str, object]:
    try:
        result = subprocess.run(
            list(check.command),
            cwd=check.cwd,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": check.name,
            "required": check.required,
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    ok = result.returncode == 0 or not check.required
    payload = {
        "name": check.name,
        "required": check.required,
        "ok": ok,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if not verbose:
        payload["stdout"] = "\n".join(payload["stdout"].splitlines()[-8:])
        payload["stderr"] = "\n".join(payload["stderr"].splitlines()[-8:])
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the repository verification suite from one command.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--skip-slow", action="store_true", help="Skip the full Python test suite and compileall.")
    parser.add_argument("--verbose", action="store_true", help="Keep full stdout/stderr in JSON output.")
    args = parser.parse_args(argv)
    root = _repo_root()
    results = [_run_check(check, verbose=args.verbose) for check in _checks(root, skip_slow=args.skip_slow)]
    ok = all(item["ok"] for item in results if item["required"])
    report = {"ok": ok, "results": results}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in results:
            status = "ok" if item["ok"] else "failed"
            required = "required" if item["required"] else "advisory"
            print(f"{item['name']}: {status} ({required})")
            if item["stdout"]:
                print(item["stdout"])
            if item["stderr"]:
                print(item["stderr"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
