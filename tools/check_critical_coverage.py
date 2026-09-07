"""Enforce minimum line coverage for production-sensitive Python package subtrees."""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


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


def _package_line_counts(root: ET.Element) -> dict[str, tuple[int, int]]:
    if root.tag != "coverage":
        raise ValueError("expected a coverage.py coverage document")
    counts: dict[str, tuple[int, int]] = {}
    filenames: set[str] = set()
    for package in root.findall("./packages/package"):
        name = str(package.get("name") or "")
        if not name or name in counts:
            raise ValueError(f"missing or duplicate package name: {name!r}")
        classes = package.findall("./classes/class")
        if not classes:
            raise ValueError(f"package {name!r} has no per-file line evidence")
        covered = total = 0
        for source in classes:
            filename = str(source.get("filename") or "").replace("\\", "/")
            path = PurePosixPath(filename)
            if not filename or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"invalid source filename: {filename!r}")
            filename = path.as_posix()
            if filename in filenames:
                raise ValueError(f"duplicate source filename: {filename!r}")
            filenames.add(filename)
            lines = source.find("lines")
            if lines is None:
                raise ValueError(f"source {filename!r} has no line evidence")
            numbers: set[int] = set()
            for line in lines.findall("line"):
                number = int(line.get("number", ""))
                hits = int(line.get("hits", ""))
                if number <= 0 or hits < 0 or number in numbers:
                    raise ValueError(
                        f"invalid or duplicate line evidence in {filename!r}"
                    )
                numbers.add(number)
                total += 1
                covered += int(hits > 0)
        counts[name] = (covered, total)
    return counts


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
        for package in root.findall("./packages/package"):
            name = str(package.get("name") or "")
            rate = float(package.get("line-rate") or 0.0)
            if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
                raise ValueError(
                    f"line-rate for {name or '<unnamed package>'!r} must be finite and between 0 and 1"
                )
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "coverage_file": str(coverage_file),
            "error": f"invalid package line-rate: {exc}",
            "packages": {},
        }
    try:
        counts = _package_line_counts(root)
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "coverage_file": str(coverage_file),
            "error": f"invalid coverage line evidence: {exc}",
            "packages": {},
        }
    packages: dict[str, dict[str, object]] = {}
    for name, minimum in CRITICAL_PACKAGE_MINIMUMS.items():
        # Package rates are rounded and exclude descendants in coverage.py XML.
        included = sorted(
            key for key in counts if key == name or key.startswith(name + ".")
        )
        covered = sum(counts[key][0] for key in included)
        total = sum(counts[key][1] for key in included)
        actual = covered / total if total else None
        packages[name] = {
            "actual": actual,
            "minimum": minimum,
            "ok": actual is not None and actual >= minimum,
            "covered_lines": covered,
            "total_lines": total,
            "included_packages": included,
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
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    args = parser.parse_args(argv)
    report = build_coverage_report(args.coverage_file)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, item in report["packages"].items():
            actual = item["actual"]
            actual_label = "missing" if actual is None else f"{float(actual):.2%}"
            print(
                f"{name} (including descendants): {actual_label} "
                f"[{item['covered_lines']}/{item['total_lines']} lines] "
                f"(minimum {float(item['minimum']):.2%})"
            )
        if report.get("error"):
            print(f"error: {report['error']}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
