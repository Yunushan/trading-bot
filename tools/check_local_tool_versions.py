from __future__ import annotations

import argparse
import json
import shutil
import shlex
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_version_file(name: str) -> str:
    path = _repo_root() / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _split_command(value: str) -> tuple[str, ...]:
    parts = tuple(part for part in shlex.split(value, posix=sys.platform != "win32") if part)
    if not parts:
        raise ValueError("command cannot be empty")
    return parts


def _display_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _node_version() -> str:
    try:
        result = subprocess.run(
            ["node", "--version"],
            cwd=_repo_root(),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip().lstrip("v") if result.returncode == 0 else ""


def _python_version(python_command: tuple[str, ...] | None = None) -> str:
    if python_command is None:
        return ".".join(str(item) for item in sys.version_info[:3])
    try:
        result = subprocess.run(
            [
                *python_command,
                "-c",
                "import sys; print('.'.join(str(item) for item in sys.version_info[:3]))",
            ],
            cwd=_repo_root(),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _matches(expected: str, actual: str) -> bool:
    expected = str(expected or "").strip().lstrip("v")
    actual = str(actual or "").strip().lstrip("v")
    if not expected or not actual:
        return False
    return actual == expected or actual.startswith(f"{expected}.")


def _default_python_command(expected: str) -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("py", f"-{expected}") if shutil.which("py") else ("python",)
    return (f"python{expected}",)


def _runtime_remediation(
    name: str,
    expected: str,
    actual: str,
    *,
    python_command: tuple[str, ...] | None = None,
) -> str:
    if _matches(expected, actual):
        return ""
    expected = str(expected or "").strip() or "the declared version"
    actual = str(actual or "").strip() or "not found"
    if name == "python":
        selected_python = _display_command(python_command or _default_python_command(expected))
        return (
            f"Install Python {expected}, then run the declared-runtime bootstrap: "
            f'python tools/bootstrap_local_dev.py --python-command "{selected_python}" --skip-client-deps. '
            "For a direct install with the selected interpreter, run: "
            f'{selected_python} -m pip install -e "Languages/Python[desktop,service,dev]" '
            f"(current Python is {actual})."
        )
    if name == "node":
        return (
            f"Install Node.js {expected} before running web/mobile client checks "
            f"(current Node.js is {actual})."
        )
    return f"Install {name} {expected} before running local verification (current {name} is {actual})."


def build_tool_version_report(
    *,
    skip_python: bool = False,
    skip_node: bool = False,
    python_command: tuple[str, ...] | None = None,
) -> dict[str, object]:
    expected_python = _read_version_file(".python-version")
    expected_node = _read_version_file(".node-version")
    actual_python = _python_version(python_command)
    actual_node = _node_version()
    checks: dict[str, dict[str, object]] = {}
    if not skip_python:
        python_ok = _matches(expected_python, actual_python)
        checks["python"] = {
            "expected": expected_python,
            "actual": actual_python,
            "ok": python_ok,
        }
        if not python_ok:
            checks["python"]["remediation"] = _runtime_remediation(
                "python",
                expected_python,
                actual_python,
                python_command=python_command,
            )
        if python_command is not None:
            checks["python"]["command"] = _display_command(python_command)
    if not skip_node:
        node_ok = _matches(expected_node, actual_node)
        checks["node"] = {
            "expected": expected_node,
            "actual": actual_node,
            "ok": node_ok,
        }
        if not node_ok:
            checks["node"]["remediation"] = _runtime_remediation("node", expected_node, actual_node)
    remediations = [
        str(item["remediation"])
        for item in checks.values()
        if isinstance(item.get("remediation"), str) and item["remediation"]
    ]
    return {
        "ok": all(bool(item["ok"]) for item in checks.values()),
        "checks": checks,
        "remediations": remediations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local Python/Node versions against repo version files.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable summary.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any runtime does not match.")
    parser.add_argument("--skip-python", action="store_true", help="Do not check the active Python version.")
    parser.add_argument("--skip-node", action="store_true", help="Do not check the active Node.js version.")
    parser.add_argument(
        "--python-command",
        default="",
        help='Python command to probe instead of the current interpreter, for example: "python" or python3.14.',
    )
    args = parser.parse_args(argv)

    try:
        python_command = _split_command(args.python_command) if args.python_command else None
    except ValueError as exc:
        print(f"Invalid --python-command: {exc}", file=sys.stderr)
        return 2

    report = build_tool_version_report(
        skip_python=args.skip_python,
        skip_node=args.skip_node,
        python_command=python_command,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, item in report["checks"].items():
            status = "ok" if item["ok"] else "mismatch"
            print(f"{name}: {status} (expected {item['expected'] or '-'}, actual {item['actual'] or '-'})")
            if item.get("remediation"):
                print(f"  fix: {item['remediation']}")
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
