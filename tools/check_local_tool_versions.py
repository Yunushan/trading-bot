from __future__ import annotations

import argparse
import json
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


def _matches(expected: str, actual: str) -> bool:
    expected = str(expected or "").strip().lstrip("v")
    actual = str(actual or "").strip().lstrip("v")
    if not expected or not actual:
        return False
    return actual == expected or actual.startswith(f"{expected}.")


def build_tool_version_report(*, skip_python: bool = False, skip_node: bool = False) -> dict[str, object]:
    expected_python = _read_version_file(".python-version")
    expected_node = _read_version_file(".node-version")
    actual_python = ".".join(str(item) for item in sys.version_info[:3])
    actual_node = _node_version()
    checks: dict[str, dict[str, object]] = {}
    if not skip_python:
        checks["python"] = {
            "expected": expected_python,
            "actual": actual_python,
            "ok": _matches(expected_python, actual_python),
        }
    if not skip_node:
        checks["node"] = {
            "expected": expected_node,
            "actual": actual_node,
            "ok": _matches(expected_node, actual_node),
        }
    return {
        "ok": all(bool(item["ok"]) for item in checks.values()),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local Python/Node versions against repo version files.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable summary.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any runtime does not match.")
    parser.add_argument("--skip-python", action="store_true", help="Do not check the active Python version.")
    parser.add_argument("--skip-node", action="store_true", help="Do not check the active Node.js version.")
    args = parser.parse_args(argv)

    report = build_tool_version_report(skip_python=args.skip_python, skip_node=args.skip_node)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, item in report["checks"].items():
            status = "ok" if item["ok"] else "mismatch"
            print(f"{name}: {status} (expected {item['expected'] or '-'}, actual {item['actual'] or '-'})")
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
