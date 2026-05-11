from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


REVIEW_ROOTS = (
    "Languages/Python/app",
    "Languages/Python/tools",
    "Languages/Python/trading_core",
    "apps",
    "tools",
)
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "dist_enduser",
    "node_modules",
    "target",
}
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pyc", ".pyd", ".exe", ".dll"}


@dataclass(frozen=True, slots=True)
class RiskPattern:
    key: str
    severity: str
    regex: re.Pattern[str]
    note: str


PATTERNS = (
    RiskPattern(
        "broad_exception",
        "medium",
        re.compile(r"\bexcept\s+Exception\b"),
        "Broad exception handlers should either narrow the exception type or record a precise recovery reason.",
    ),
    RiskPattern(
        "bare_except",
        "high",
        re.compile(r"\bexcept\s*:"),
        "Bare except catches system-exiting exceptions and should be replaced with targeted handling.",
    ),
    RiskPattern(
        "ssl_verification_disabled",
        "high",
        re.compile(r"\bverify\s*=\s*False\b"),
        "Disabled TLS verification is unsafe outside explicit local test doubles.",
    ),
    RiskPattern(
        "silent_pass",
        "medium",
        re.compile(r"^\s*pass\s*(#.*)?$"),
        "Silent pass blocks in control paths deserve a comment, log, or narrower branch.",
    ),
    RiskPattern(
        "todo_marker",
        "low",
        re.compile(r"\bTODO\b|\bFIXME\b", re.IGNORECASE),
        "Open TODO/FIXME markers should become tracked work or be removed.",
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _should_scan(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in SKIP_DIRS for part in relative.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def audit_risky_patterns() -> dict[str, object]:
    root = _repo_root()
    findings: list[dict[str, object]] = []
    for scan_root in REVIEW_ROOTS:
        base = root / scan_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not _should_scan(path, root):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                for pattern in PATTERNS:
                    if not pattern.regex.search(line):
                        continue
                    findings.append(
                        {
                            "key": pattern.key,
                            "severity": pattern.severity,
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "line": line_number,
                            "text": line.strip()[:160],
                            "note": pattern.note,
                        }
                    )
    counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    for finding in findings:
        key = str(finding["key"])
        counts[key] = counts.get(key, 0) + 1
        severity = str(finding["severity"])
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        path = str(finding["path"])
        path_counts[path] = path_counts.get(path, 0) + 1
    top_paths = [
        {"path": path, "count": count}
        for path, count in sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    ]
    return {
        "finding_count": len(findings),
        "counts": counts,
        "severity_counts": severity_counts,
        "top_paths": top_paths,
        "findings": findings,
    }


def _summary_report(report: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in report.items() if key != "findings"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report broad exception and unsafe-pattern hotspots.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--summary", action="store_true", help="Omit per-line findings from JSON output.")
    parser.add_argument("--fail-on-high", action="store_true", help="Exit non-zero if high-severity findings exist.")
    args = parser.parse_args(argv)

    report = audit_risky_patterns()
    if args.json:
        payload = _summary_report(report) if args.summary else report
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Risky pattern findings: {report['finding_count']}")
        for key, count in sorted(report["counts"].items()):
            print(f"  - {key}: {count}")
        if report["top_paths"]:
            print("Top risky-pattern paths:")
            for item in report["top_paths"][:10]:
                print(f"  - {item['path']}: {item['count']}")
        for finding in report["findings"][:30]:
            print(f"{finding['severity']} {finding['path']}:{finding['line']} {finding['key']}")
    has_high = any(item["severity"] == "high" for item in report["findings"])
    return 1 if args.fail_on_high and has_high else 0


if __name__ == "__main__":
    raise SystemExit(main())
