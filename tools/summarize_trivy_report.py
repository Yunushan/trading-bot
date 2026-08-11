#!/usr/bin/env python3
"""Print a concise, remediation-oriented summary of a Trivy JSON report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
_MISSING = object()


class TrivyReportFormatError(ValueError):
    """Raised when a Trivy report cannot be summarized without data loss."""


def _field(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return _MISSING


def _results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        results = payload
    elif isinstance(payload, dict):
        results = _field(payload, "Results", "results")
        if results is _MISSING:
            raise TrivyReportFormatError("report is missing Results/results")
    else:
        raise TrivyReportFormatError("report root must be a JSON object or array")

    if not isinstance(results, list):
        raise TrivyReportFormatError("Results/results must be an array")
    invalid_indexes = [index for index, item in enumerate(results) if not isinstance(item, dict)]
    if invalid_indexes:
        indexes = ", ".join(str(index) for index in invalid_indexes[:3])
        suffix = "..." if len(invalid_indexes) > 3 else ""
        raise TrivyReportFormatError(f"results contains non-object entries at index {indexes}{suffix}")
    return results


def _vulnerabilities(result: dict[str, Any], result_index: int) -> list[dict[str, Any]]:
    raw = _field(result, "Vulnerabilities", "vulnerabilities")
    if raw is _MISSING:
        # Trivy omits the field for clean image targets; absence has the same
        # meaning as its documented null value, not a malformed finding list.
        return []
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TrivyReportFormatError(f"result {result_index} Vulnerabilities/vulnerabilities must be an array or null")
    invalid_indexes = [index for index, item in enumerate(raw) if not isinstance(item, dict)]
    if invalid_indexes:
        indexes = ", ".join(str(index) for index in invalid_indexes[:3])
        suffix = "..." if len(invalid_indexes) > 3 else ""
        raise TrivyReportFormatError(
            f"result {result_index} contains non-object vulnerabilities at index {indexes}{suffix}"
        )
    return raw


def summarize_report(path: Path) -> tuple[Counter[str], list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    findings: list[dict[str, str]] = []
    for result_index, result in enumerate(_results(payload)):
        target = str(result.get("Target") or result.get("target") or "unknown target")
        for vulnerability_index, vulnerability in enumerate(_vulnerabilities(result, result_index)):
            raw_severity = _field(vulnerability, "Severity", "severity")
            if not isinstance(raw_severity, str) or not raw_severity.strip():
                raise TrivyReportFormatError(
                    f"result {result_index} vulnerability {vulnerability_index} has no valid severity"
                )
            severity = raw_severity.strip().upper()
            if severity not in SEVERITIES:
                raise TrivyReportFormatError(
                    f"result {result_index} vulnerability {vulnerability_index} has unknown severity {raw_severity!r}"
                )

            raw_id = _field(vulnerability, "VulnerabilityID", "vulnerability_id")
            if not isinstance(raw_id, str) or not raw_id.strip():
                raise TrivyReportFormatError(
                    f"result {result_index} vulnerability {vulnerability_index} is missing VulnerabilityID"
                )
            raw_package = _field(vulnerability, "PkgName", "pkg_name")
            if not isinstance(raw_package, str) or not raw_package.strip():
                raise TrivyReportFormatError(
                    f"result {result_index} vulnerability {vulnerability_index} is missing PkgName"
                )

            counts[severity] += 1
            findings.append(
                {
                    "severity": severity,
                    "id": raw_id.strip(),
                    "package": raw_package.strip(),
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
    except TrivyReportFormatError as exc:
        print(f"Invalid Trivy report {args.report}: {exc}")
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
