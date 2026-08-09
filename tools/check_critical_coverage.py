"""Enforce minimum line coverage for production-sensitive Python packages."""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


CRITICAL_PACKAGE_MINIMUMS: dict[str, float] = {
    "core.strategy": 0.75,
    "core.positions": 0.60,
    "integrations.exchanges.binance.market": 0.65,
    "integrations.exchanges.binance.orders": 0.70,
    "service.runners": 0.80,
    "settings": 0.85,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_coverage_report(coverage_file: Path) -> dict[str, object]:
    try:
        root = ET.parse(coverage_file).getroot()
    except (ET.ParseError, OSError) as exc:
        if isinstance(exc, FileNotFoundError):
            error = (
                f"coverage report not found at {coverage_file}; run "
                "python tools/run_python_tests.py --runner pytest before "
                "checking critical coverage"
            )
        else:
            error = str(exc)
        return {
            "ok": False,
            "coverage_file": str(coverage_file),
            "error": error,
            "packages": {},
        }

    try:
        rates: dict[str, float] = {}
        for package in root.findall(".//package"):
            name = str(package.get("name") or "")
            rate = float(package.get("line-rate") or 0.0)
            if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
                raise ValueError(
                    f"line-rate for {name or '<unnamed package>'!r} must be finite and between 0 and 1"
                )
            rates[name] = rate
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "coverage_file": str(coverage_file),
            "error": f"invalid package line-rate: {exc}",
            "packages": {},
        }
    packages: dict[str, dict[str, object]] = {}
    for name, minimum in CRITICAL_PACKAGE_MINIMUMS.items():
        actual = rates.get(name)
        packages[name] = {
            "actual": actual,
            "minimum": minimum,
            "ok": actual is not None and actual >= minimum,
        }
    return {
        "ok": all(bool(item["ok"]) for item in packages.values()),
        "coverage_file": str(coverage_file),
        "packages": packages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-file",
        type=Path,
        default=_repo_root() / "Languages" / "Python" / "coverage.xml",
        help="Path to the coverage.py XML report.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    report = build_coverage_report(args.coverage_file)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, item in report["packages"].items():
            actual = item["actual"]
            actual_label = "missing" if actual is None else f"{float(actual):.2%}"
            print(f"{name}: {actual_label} (minimum {float(item['minimum']):.2%})")
        if report.get("error"):
            print(f"error: {report['error']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
