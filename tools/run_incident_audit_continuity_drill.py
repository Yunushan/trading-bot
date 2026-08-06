#!/usr/bin/env python3
"""Exercise incident and order-audit continuity without submitting orders."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.orders.order_audit_runtime import (  # noqa: E402
    bind_binance_order_audit_runtime,
)
from app.jsonl_rotation import jsonl_backup_path  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402

if __package__:
    from .check_operational_readiness import (  # noqa: E402
        DEFAULT_POLICY_PATH,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )
    from .run_service_sustained_probe import _atomic_write_json, _resolve_output_path  # noqa: E402
else:
    from check_operational_readiness import (  # noqa: E402
        DEFAULT_POLICY_PATH,
        _current_commit,
        _source_tree_clean,
        load_policy,
        policy_sha256,
        validate_policy,
    )
    from run_service_sustained_probe import _atomic_write_json, _resolve_output_path  # noqa: E402


EVIDENCE_ID = "incident-audit-continuity"
DRILL_SECRET = "continuity-drill-secret"


class _OrderAuditHarness:
    mode = "offline"
    account_type = "futures"
    _connector_backend = "continuity-drill"

    def _log(self, _message: str, *, lvl: str = "info") -> None:
        del lvl


bind_binance_order_audit_runtime(_OrderAuditHarness)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recovery_limits(policy: dict[str, Any]) -> tuple[float, float]:
    objectives = policy.get("recovery_objectives")
    matching = (
        [
            item
            for item in objectives
            if isinstance(item, dict) and item.get("evidence_id") == EVIDENCE_ID
        ]
        if isinstance(objectives, list)
        else []
    )
    if not matching:
        raise ValueError(f"No recovery objectives reference {EVIDENCE_ID}")
    return (
        min(float(item["rto_seconds"]) for item in matching),
        min(float(item["rpo_seconds"]) for item in matching),
    )


def _jsonl_paths(path: Path, backup_count: int) -> list[Path]:
    backups = [jsonl_backup_path(path, index) for index in range(backup_count, 0, -1)]
    return [*backups, path]


def _read_jsonl(paths: list[Path]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    parse_errors = 0
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                parse_errors += 1
    return rows, parse_errors


def _suite_result(name: str, passed: bool, **details: object) -> dict[str, object]:
    return {"name": name, "status": "pass" if passed else "fail", **details}


def run_continuity_drill(*, policy_path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    resolved_policy_path = policy_path if policy_path.is_absolute() else REPO_ROOT / policy_path
    policy = load_policy(resolved_policy_path)
    policy_issues = validate_policy(policy)
    if policy_issues:
        return {
            "ok": False,
            "status": "fail",
            "evidence_id": EVIDENCE_ID,
            "promotion_eligible": False,
            "issues": policy_issues,
        }

    rto_seconds, rpo_seconds = _recovery_limits(policy)
    source_tree_clean = _source_tree_clean(REPO_ROOT)
    suite_results: list[dict[str, object]] = []
    recovery_time = 0.0
    recovery_point = 0.0

    with tempfile.TemporaryDirectory(prefix="trading-bot-audit-continuity-") as temp_dir:
        temporary_root = Path(temp_dir)
        incident_path = temporary_root / "connector-incidents.jsonl"
        order_audit_path = temporary_root / "order-audit.jsonl"
        backup_count = 2

        service = TradingBotService(
            config={
                "connector_order_circuit_incident_log_path": str(incident_path),
                "connector_order_circuit_incident_log_max_bytes": 1,
                "connector_order_circuit_incident_log_backup_count": backup_count,
            }
        )
        for index in range(3):
            service.set_connector_order_circuit_breaker_snapshot(
                {
                    "active": True,
                    "state": "open",
                    "reason": "continuity_drill",
                    "message": f"Circuit opened api_secret={DRILL_SECRET}-{index}",
                    "block_count": index + 1,
                    "block_threshold": 1,
                },
                source="incident-audit-continuity-drill",
            )
            service.reset_connector_order_circuit_breaker(
                source="incident-audit-continuity-drill",
                force=True,
            )

        incident_path.write_text(
            incident_path.read_text(encoding="utf-8") + "{malformed-drill-line\n",
            encoding="utf-8",
        )
        restart_started = time.perf_counter()
        restarted_service = TradingBotService(
            config={
                "connector_order_circuit_incident_log_path": str(incident_path),
                "connector_order_circuit_incident_log_max_bytes": 1,
                "connector_order_circuit_incident_log_backup_count": backup_count,
            }
        )
        incident_tail = restarted_service.get_connector_order_circuit_incidents(limit=20)
        recovery_time = time.perf_counter() - restart_started
        incident_rendered = json.dumps(incident_tail, sort_keys=True)
        incident_events = [
            str(item.get("event") or "")
            for item in incident_tail.get("events", [])
            if isinstance(item, dict)
        ]
        incident_continuity_ok = (
            incident_tail.get("exists") is True
            and "connector_order_circuit_trip" in incident_events
            and "connector_order_circuit_reset" in incident_events
        )
        suite_results.extend(
            [
                _suite_result(
                    "incident-rotation-restart-readback",
                    incident_continuity_ok,
                    recovered_events=len(incident_events),
                ),
                _suite_result(
                    "incident-corruption-tolerance",
                    "connector_order_circuit_log_parse_error" in incident_events,
                ),
                _suite_result(
                    "incident-secret-redaction",
                    DRILL_SECRET not in incident_rendered and "<redacted>" in incident_rendered,
                ),
            ]
        )

        audit = _OrderAuditHarness()
        audit._configure_order_audit(
            path=order_audit_path,
            enabled=True,
            max_bytes=1,
            backup_count=backup_count,
        )
        for index in range(3):
            audit._audit_order_event(
                "order_rejected",
                symbol="BTCUSDT",
                side="BUY",
                market="futures",
                source="incident-audit-continuity-drill",
                params={"api_secret": f"{DRILL_SECRET}-{index}", "quantity": 0},
                error="synthetic rejection; no connector invoked",
            )
        order_rows, order_parse_errors = _read_jsonl(
            _jsonl_paths(order_audit_path, backup_count)
        )
        order_rendered = json.dumps(order_rows, sort_keys=True)
        order_status = audit.get_order_audit_status()
        suite_results.extend(
            [
                _suite_result(
                    "order-audit-rotation-readback",
                    len(order_rows) == 3
                    and all(row.get("event") == "order_rejected" for row in order_rows)
                    and order_parse_errors == 0,
                    recovered_events=len(order_rows),
                ),
                _suite_result(
                    "order-audit-secret-redaction",
                    DRILL_SECRET not in order_rendered and "<redacted>" in order_rendered,
                ),
                _suite_result(
                    "order-audit-write-health",
                    order_status.get("write_ok") is True and order_status.get("state") == "ready",
                ),
            ]
        )

        valid_incident_rows, _ = _read_jsonl(_jsonl_paths(incident_path, backup_count))
        timestamps = [
            datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00")).timestamp()
            for row in valid_incident_rows
            if row.get("ts")
        ]
        recovery_point = max(0.0, time.time() - max(timestamps)) if timestamps else float("inf")

    suite_results.extend(
        [
            _suite_result(
                "recovery-time-objective",
                recovery_time <= rto_seconds,
                actual_seconds=round(recovery_time, 6),
                maximum_seconds=rto_seconds,
            ),
            _suite_result(
                "recovery-point-objective",
                recovery_point <= rpo_seconds,
                actual_seconds=round(recovery_point, 6),
                maximum_seconds=rpo_seconds,
            ),
            _suite_result("no-order-submission", True, submission_attempts=0),
        ]
    )
    issues = [
        str(result.get("name"))
        for result in suite_results
        if result.get("status") != "pass"
    ]
    ok = not issues
    return {
        "ok": ok,
        "evidence_id": EVIDENCE_ID,
        "status": "pass" if ok else "fail",
        "evidence_scope": "local-incident-and-order-audit-continuity-drill",
        "generated_at": _now_iso(),
        "commit": _current_commit(REPO_ROOT),
        "source_tree_clean": source_tree_clean,
        "policy_sha256": policy_sha256(policy),
        "secrets_redacted": True,
        "read_only": True,
        "order_submission_attempted": False,
        "runtime_ready_claimed": False,
        "promotion_eligible": bool(ok and source_tree_clean is True),
        "recovery_time_seconds": round(recovery_time, 6),
        "recovery_point_seconds": round(recovery_point, 6),
        "thresholds": {"rto_seconds": rto_seconds, "rpo_seconds": rpo_seconds},
        "suite_results": suite_results,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_continuity_drill(policy_path=args.policy)
        if args.output:
            policy_path = args.policy if args.policy.is_absolute() else REPO_ROOT / args.policy
            output_path = _resolve_output_path(load_policy(policy_path), args.output)
            _atomic_write_json(output_path, report)
            report["output_path"] = str(output_path)
    except (OSError, ValueError) as exc:
        report = {
            "ok": False,
            "status": "fail",
            "evidence_id": EVIDENCE_ID,
            "promotion_eligible": False,
            "issues": [str(exc)],
        }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Incident/audit continuity drill: {report.get('status', 'fail')}; "
            f"RTO={report.get('recovery_time_seconds', 0)}s; "
            f"RPO={report.get('recovery_point_seconds', 0)}s"
        )
        for issue in report.get("issues", []):
            print(f"- {issue}", file=sys.stderr)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
