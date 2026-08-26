#!/usr/bin/env python3
"""Fail closed on RustSec vulnerabilities and informational-warning drift."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _warning_rows(report: dict[str, Any], errors: list[str]) -> list[dict[str, str]]:
    warnings = report.get("warnings")
    if not isinstance(warnings, dict):
        errors.append("cargo audit report is missing a warnings object")
        return []

    rows: list[dict[str, str]] = []
    for kind, findings in warnings.items():
        if not isinstance(findings, list):
            errors.append(f"cargo audit warning category {kind} is malformed")
            continue
        for finding in findings:
            advisory = finding.get("advisory") if isinstance(finding, dict) else None
            package = finding.get("package") if isinstance(finding, dict) else None
            if not isinstance(advisory, dict) or not isinstance(package, dict):
                errors.append(f"cargo audit warning in {kind} is malformed")
                continue
            row = {
                "kind": str(kind),
                "id": str(advisory.get("id") or ""),
                "package": str(package.get("name") or ""),
                "version": str(package.get("version") or ""),
            }
            if not all(row.values()):
                errors.append(f"cargo audit warning in {kind} lacks exact identity fields")
                continue
            if advisory.get("withdrawn") is not None:
                errors.append(f"cargo audit still reports withdrawn advisory {row['id']}")
                continue
            rows.append(row)
    return rows


def evaluate(
    report: dict[str, Any],
    policy: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    today = as_of or date.today()
    errors: list[str] = []
    allowed: list[dict[str, str]] = []

    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        errors.append("cargo audit report is missing a vulnerabilities object")
    else:
        vulnerability_list = vulnerabilities.get("list")
        vulnerability_count = vulnerabilities.get("count")
        if not isinstance(vulnerability_list, list) or not isinstance(vulnerability_count, int):
            errors.append("cargo audit vulnerability summary is malformed")
        elif vulnerability_count != len(vulnerability_list):
            errors.append("cargo audit vulnerability count does not match its finding list")
        elif vulnerability_count > 0:
            errors.append(f"cargo audit reported {vulnerability_count} vulnerability finding(s)")

    database = report.get("database")
    max_database_age_days = int(policy.get("max_database_age_days", 7))
    if not isinstance(database, dict):
        errors.append("cargo audit report is missing database provenance")
    else:
        updated_at = _parse_datetime(database.get("last-updated"))
        if updated_at is None:
            errors.append("cargo audit database last-updated is invalid")
        else:
            database_age_days = (today - updated_at.date()).days
            if database_age_days < -1:
                errors.append("cargo audit database last-updated is in the future")
            elif database_age_days > max_database_age_days:
                errors.append(
                    f"cargo audit database is {database_age_days} days old; maximum is {max_database_age_days}"
                )

    actual_rows = _warning_rows(report, errors)
    actual_by_identity = {
        (row["kind"], row["id"], row["package"], row["version"]): row for row in actual_rows
    }
    if len(actual_by_identity) != len(actual_rows):
        errors.append("cargo audit report contains duplicate warning identities")

    exceptions = policy.get("exceptions")
    if not isinstance(exceptions, list):
        errors.append("Rust audit policy is missing an exceptions array")
        exceptions = []
    max_exception_days = int(policy.get("max_exception_days", 45))
    expected_identities: set[tuple[str, str, str, str]] = set()
    for exception in exceptions:
        if not isinstance(exception, dict):
            errors.append("every Rust audit exception must be an object")
            continue
        identity = (
            str(exception.get("kind") or ""),
            str(exception.get("id") or ""),
            str(exception.get("package") or ""),
            str(exception.get("version") or ""),
        )
        reason = str(exception.get("reason") or "").strip()
        scope = str(exception.get("scope") or "").strip()
        reviewed = _parse_date(exception.get("reviewed"))
        expires = _parse_date(exception.get("expires"))
        if not all(identity) or not reason or not scope or reviewed is None or expires is None:
            errors.append("every Rust audit exception needs identity, scope, reviewed, expires, and reason")
            continue
        if identity in expected_identities:
            errors.append(f"duplicate Rust audit exception for {identity[1]} {identity[2]}@{identity[3]}")
            continue
        expected_identities.add(identity)
        if expires < reviewed or (expires - reviewed).days > max_exception_days:
            errors.append(f"Rust audit exception {identity[1]} has an invalid review window")
            continue
        if expires < today:
            errors.append(f"Rust audit exception {identity[1]} expired on {expires.isoformat()}")
            continue
        if identity not in actual_by_identity:
            errors.append(
                f"Rust audit exception {identity[1]} for {identity[2]}@{identity[3]} is stale or changed"
            )
            continue
        allowed.append(
            {
                "kind": identity[0],
                "id": identity[1],
                "package": identity[2],
                "version": identity[3],
                "expires": expires.isoformat(),
                "scope": scope,
                "reason": reason,
            }
        )

    unresolved = [
        row
        for identity, row in sorted(actual_by_identity.items())
        if identity not in expected_identities
    ]
    if unresolved:
        errors.append(f"{len(unresolved)} Rust audit warning(s) are not covered by exact policy")

    return {
        "ok": not errors,
        "as_of": today.isoformat(),
        "vulnerability_count": (
            vulnerabilities.get("count") if isinstance(vulnerabilities, dict) else None
        ),
        "warning_count": len(actual_rows),
        "allowed": allowed,
        "unresolved": unresolved,
        "errors": errors,
    }


def _self_test() -> None:
    report = {
        "database": {"last-updated": "2026-08-26T01:00:00Z"},
        "vulnerabilities": {"count": 0, "list": []},
        "warnings": {
            "unsound": [
                {
                    "package": {"name": "example", "version": "1.2.3"},
                    "advisory": {"id": "RUSTSEC-2099-0001", "withdrawn": None},
                }
            ]
        },
    }
    policy = {
        "max_database_age_days": 7,
        "max_exception_days": 45,
        "exceptions": [
            {
                "kind": "unsound",
                "id": "RUSTSEC-2099-0001",
                "package": "example",
                "version": "1.2.3",
                "reviewed": "2026-08-26",
                "expires": "2026-09-30",
                "scope": "test-only",
                "reason": "self-test",
            }
        ],
    }
    passed = evaluate(report, policy, as_of=date(2026, 8, 26))
    assert passed["ok"], passed

    new_warning = json.loads(json.dumps(report))
    new_warning["warnings"]["unmaintained"] = [
        {
            "package": {"name": "new-package", "version": "9.9.9"},
            "advisory": {"id": "RUSTSEC-2099-0002", "withdrawn": None},
        }
    ]
    assert not evaluate(new_warning, policy, as_of=date(2026, 8, 26))["ok"]

    vulnerable = json.loads(json.dumps(report))
    vulnerable["vulnerabilities"] = {"count": 1, "list": [{"advisory": {"id": "RUSTSEC-1"}}]}
    assert not evaluate(vulnerable, policy, as_of=date(2026, 8, 26))["ok"]

    assert not evaluate(report, policy, as_of=date(2026, 10, 1))["ok"]
    print("Rust audit policy self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report")
    parser.add_argument("--policy")
    parser.add_argument("--as-of")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if not args.report or not args.policy:
        parser.error("--report and --policy are required unless --self-test is used")
    as_of = _parse_date(args.as_of) if args.as_of else None
    if args.as_of and as_of is None:
        parser.error("--as-of must be YYYY-MM-DD")
    result = evaluate(_read_json(args.report), _read_json(args.policy), as_of=as_of)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
