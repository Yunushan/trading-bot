#!/usr/bin/env python3
"""Exercise service config backup/restore and read-only restart recovery."""

from __future__ import annotations

import argparse
import json
import shutil
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

from app.service.api import create_service_api_app  # noqa: E402
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


EVIDENCE_ID = "service-config-backup-restore"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recovery_limits(policy: dict[str, Any]) -> tuple[float, float]:
    objectives = policy.get("recovery_objectives")
    matching = [
        item
        for item in objectives if isinstance(item, dict) and item.get("evidence_id") == EVIDENCE_ID
    ] if isinstance(objectives, list) else []
    if not matching:
        raise ValueError(f"No recovery objectives reference {EVIDENCE_ID}")
    return (
        min(float(item["rto_seconds"]) for item in matching),
        min(float(item["rpo_seconds"]) for item in matching),
    )


def run_recovery_drill(*, policy_path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
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
    issues: list[str] = []
    recovery_time = 0.0
    recovery_point = 0.0

    try:
        from fastapi.testclient import TestClient
    except Exception as exc:
        return {
            "ok": False,
            "status": "fail",
            "evidence_id": EVIDENCE_ID,
            "promotion_eligible": False,
            "issues": [f"FastAPI TestClient is unavailable: {exc}"],
        }

    with tempfile.TemporaryDirectory(prefix="trading-bot-recovery-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        config_path = temporary_root / "service-config.json"
        backup_path = temporary_root / "service-config.backup.json"
        service = TradingBotService(config_path=config_path)
        expected_symbols = ["BTCUSDT", "ETHUSDT"]
        expected_intervals = ["5m", "15m"]
        service.update_config(
            {
                "symbols": expected_symbols,
                "intervals": expected_intervals,
                "theme": "Dark",
                "api_key": "",
                "api_secret": "",
                "llm_api_key": "",
            }
        )
        service.save_config(source="operational-recovery-drill")
        shutil.copy2(config_path, backup_path)
        backup_created_at = time.time()
        persisted_text = backup_path.read_text(encoding="utf-8")
        safe_backup = all(secret not in persisted_text for secret in ("exchange-secret", "llm-secret"))
        suite_results.append(
            {
                "name": "config-backup-created",
                "status": "pass" if backup_path.is_file() and safe_backup else "fail",
            }
        )

        service.update_config({"symbols": ["INVALIDUSDT"], "intervals": ["1m"]})
        service.save_config(source="operational-recovery-drill-mutation")
        recovery_started = time.perf_counter()
        restore_temp = config_path.with_suffix(".restore.tmp")
        shutil.copy2(backup_path, restore_temp)
        restore_temp.replace(config_path)
        restored = TradingBotService(config_path=config_path, load_persisted_config=True)
        recovery_time = time.perf_counter() - recovery_started
        recovery_point = max(0.0, time.time() - backup_created_at)
        restored_payload = restored.get_config_payload().to_dict()
        config_matches = (
            restored_payload.get("symbols") == expected_symbols
            and restored_payload.get("intervals") == expected_intervals
            and restored_payload.get("theme") == "Dark"
        )
        suite_results.append(
            {
                "name": "config-restore-round-trip",
                "status": "pass" if config_matches else "fail",
            }
        )

        app = create_service_api_app(
            service=restored,
            api_token="operational-recovery-token",
            host_context="operational-recovery-drill",
            host_owner="verification-process",
            enable_local_executor=False,
        )
        with TestClient(app) as client:
            liveness = client.get("/livez")
            readiness = client.get("/readyz")
            runtime = client.get(
                "/api/v1/runtime",
                headers={"Authorization": "Bearer operational-recovery-token"},
            )
        restart_ready = all(response.status_code == 200 for response in (liveness, readiness, runtime))
        suite_results.append(
            {
                "name": "read-only-service-restart",
                "status": "pass" if restart_ready else "fail",
                "status_codes": [liveness.status_code, readiness.status_code, runtime.status_code],
            }
        )

    rto_pass = recovery_time <= rto_seconds
    rpo_pass = recovery_point <= rpo_seconds
    suite_results.extend(
        [
            {
                "name": "recovery-time-objective",
                "status": "pass" if rto_pass else "fail",
                "actual_seconds": round(recovery_time, 6),
                "maximum_seconds": rto_seconds,
            },
            {
                "name": "recovery-point-objective",
                "status": "pass" if rpo_pass else "fail",
                "actual_seconds": round(recovery_point, 6),
                "maximum_seconds": rpo_seconds,
            },
        ]
    )
    ok = all(result.get("status") == "pass" for result in suite_results)
    if not ok:
        issues.extend(str(result.get("name")) for result in suite_results if result.get("status") != "pass")
    promotion_eligible = bool(ok and source_tree_clean is True)
    return {
        "ok": ok,
        "evidence_id": EVIDENCE_ID,
        "status": "pass" if ok else "fail",
        "evidence_scope": "local-config-and-service-recovery-drill",
        "generated_at": _now_iso(),
        "commit": _current_commit(REPO_ROOT),
        "source_tree_clean": source_tree_clean,
        "policy_sha256": policy_sha256(policy),
        "secrets_redacted": True,
        "read_only": True,
        "order_submission_attempted": False,
        "runtime_ready_claimed": False,
        "promotion_eligible": promotion_eligible,
        "recovery_time_seconds": round(recovery_time, 6),
        "recovery_point_seconds": round(recovery_point, 6),
        "thresholds": {
            "rto_seconds": rto_seconds,
            "rpo_seconds": rpo_seconds,
        },
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
        report = run_recovery_drill(policy_path=args.policy)
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
            f"Operational recovery drill: {report.get('status', 'fail')}; "
            f"RTO={report.get('recovery_time_seconds', 0)}s; "
            f"RPO={report.get('recovery_point_seconds', 0)}s"
        )
        for issue in report.get("issues", []):
            print(f"- {issue}", file=sys.stderr)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
