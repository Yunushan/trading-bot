#!/usr/bin/env python3
"""Print a concise, remediation-oriented summary of a Trivy JSON report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def _results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        results = payload.get("Results", payload.get("results", []))
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def summarize_report(path: Path) -> tuple[Counter[str], list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    findings: list[dict[str, str]] = []
    for result in _results(payload):
        target = str(result.get("Target") or result.get("target") or "unknown target")
        vulnerabilities = result.get("Vulnerabilities", result.get("vulnerabilities", []))
        if not isinstance(vulnerabilities, list):
            continue
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            severity = str(vulnerability.get("Severity") or vulnerability.get("severity") or "UNKNOWN").upper()
            counts[severity] += 1
            findings.append(
                {
                    "severity": severity,
                    "id": str(vulnerability.get("VulnerabilityID") or vulnerability.get("vulnerability_id") or "unknown"),
                    "package": str(vulnerability.get("PkgName") or vulnerability.get("pkg_name") or "unknown"),
                    "installed": str(vulnerability.get("InstalledVersion") or vulnerability.get("installed_version") or "unknown"),
                    "fixed": str(vulnerability.get("FixedVersion") or vulnerability.get("fixed_version") or "not available"),
                    "target": target,
                }
            )
    findings.sort(key=lambda item: (SEVERITIES.index(item["severity"]) if item["severity"] in SEVERITIES else len(SEVERITIES), item["id"]))
    return counts, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Trivy JSON report path.")
    args = parser.parse_args(argv)
    if not args.report.is_file():
        print(f"Trivy report was not produced: {args.report}")
        return 1
    try:
        counts, findings = summarize_report(args.report)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read Trivy report {args.report}: {exc}")
        return 1

    total = sum(counts.values())
    summary = ", ".join(f"{severity.lower()}={counts[severity]}" for severity in SEVERITIES if counts[severity])
    print(f"Trivy vulnerabilities: total={total}" + (f" ({summary})" if summary else ""))
    for finding in findings:
        print(
            "- {severity} {id}: {package} {installed} -> {fixed} ({target})".format(
                **finding,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
