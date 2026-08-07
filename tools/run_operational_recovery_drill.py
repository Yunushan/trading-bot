#!/usr/bin/env python3
"""Exercise service config backup/restore and read-only restart recovery."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.security.redaction import redact_text  # noqa: E402
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
SERVICE_START_ATTEMPTS = 3
SYNTHETIC_SECRETS = {
    "api_key": "recovery-drill-exchange-key",
    "api_secret": "recovery-drill-exchange-secret",
    "llm_api_key": "recovery-drill-llm-secret",
}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


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


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_only_status(url: str, *, api_token: str) -> int:
    request = Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_token}"},
        method="GET",
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=1.0) as response:  # noqa: S310 - fixed loopback origin
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except (OSError, TimeoutError, URLError):
        return 0


def _stop_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _redacted_process_diagnostic(handle, *, api_token: str) -> str:  # noqa: ANN001
    try:
        handle.flush()
        handle.seek(0)
        raw = handle.read()
    except (OSError, ValueError):
        return ""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    text = text.replace(api_token, "[REDACTED]")
    for secret in SYNTHETIC_SECRETS.values():
        text = text.replace(secret, "[REDACTED]")
    return redact_text(text[-4000:]).strip()


def _run_canonical_service_restart(
    *,
    config_path: Path,
    timeout_seconds: float,
) -> tuple[bool, float, list[int], int | None, str, int]:
    started = time.perf_counter()
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    status_codes = [0, 0, 0]
    exit_code: int | None = None
    diagnostic = ""
    attempts = 0
    while attempts < SERVICE_START_ATTEMPTS and time.monotonic() < deadline:
        attempts += 1
        port = _reserve_loopback_port()
        base_url = f"http://127.0.0.1:{port}"
        api_token = secrets.token_urlsafe(32)
        command = [
            sys.executable,
            str(REPO_ROOT / "apps" / "service-api" / "main.py"),
            "--serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--config-path",
            str(config_path),
            "--load-config",
        ]
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["BOT_SERVICE_API_TOKEN"] = api_token
        with tempfile.TemporaryFile() as child_output:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=child_output,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                diagnostic = redact_text(f"{type(exc).__name__}: {exc}")
                continue
            try:
                while time.monotonic() < deadline:
                    exit_code = process.poll()
                    if exit_code is not None:
                        diagnostic = _redacted_process_diagnostic(child_output, api_token=api_token)
                        break
                    status_codes = [
                        _read_only_status(f"{base_url}/livez", api_token=api_token),
                        _read_only_status(f"{base_url}/readyz", api_token=api_token),
                        _read_only_status(
                            f"{base_url}/api/v1/runtime",
                            api_token=api_token,
                        ),
                    ]
                    if all(status_code == 200 for status_code in status_codes):
                        return (
                            True,
                            time.perf_counter() - started,
                            status_codes,
                            process.poll(),
                            "",
                            attempts,
                        )
                    time.sleep(0.1)
                else:
                    diagnostic = _redacted_process_diagnostic(child_output, api_token=api_token)
            finally:
                _stop_child(process)
        if exit_code is None:
            break
    return False, time.perf_counter() - started, status_codes, exit_code, diagnostic, attempts


def run_recovery_drill(*, policy_path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    resolved_policy_path = (
        policy_path if policy_path.is_absolute() else REPO_ROOT / policy_path
    )
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
    config_recovery_time = 0.0
    service_recovery_time = 0.0
    recovery_time = 0.0
    recovery_point = 0.0

    with tempfile.TemporaryDirectory(
        prefix="trading-bot-recovery-"
    ) as temporary_directory:
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
                **SYNTHETIC_SECRETS,
            }
        )
        cleanup_service = service
        try:
            service.save_config(source="operational-recovery-drill")
            shutil.copy2(config_path, backup_path)
            backup_created_at = time.time()
            persisted_text = backup_path.read_text(encoding="utf-8")
            backup_payload = json.loads(persisted_text)
            persisted_config = (
                backup_payload.get("config")
                if isinstance(backup_payload, dict)
                else None
            )
            safe_backup = bool(
                backup_path.is_file()
                and isinstance(persisted_config, dict)
                and backup_payload.get("inline_secrets_persisted") is False
                and all(
                    secret not in persisted_text
                    for secret in SYNTHETIC_SECRETS.values()
                )
                and all(
                    persisted_config.get(field) in (None, "")
                    for field in SYNTHETIC_SECRETS
                )
            )
            suite_results.append(
                {
                    "name": "config-backup-secret-redaction",
                    "status": "pass" if safe_backup else "fail",
                    "synthetic_secret_count": len(SYNTHETIC_SECRETS),
                }
            )

            service.update_config({"symbols": ["INVALIDUSDT"], "intervals": ["1m"]})
            service.save_config(source="operational-recovery-drill-mutation")
            recovery_started = time.perf_counter()
            restore_temp = config_path.with_suffix(".restore.tmp")
            shutil.copy2(backup_path, restore_temp)
            restore_temp.replace(config_path)
            restored = TradingBotService(
                config_path=config_path, load_persisted_config=True
            )
            cleanup_service = restored
            config_recovery_time = time.perf_counter() - recovery_started
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

            restored.update_config({field: "" for field in SYNTHETIC_SECRETS})
            restored.save_config(source="operational-recovery-drill-secret-cleanup")
            persisted_after_cleanup = config_path.read_text(encoding="utf-8")
            cleanup_pass = all(
                secret not in persisted_after_cleanup
                for secret in SYNTHETIC_SECRETS.values()
            )
            suite_results.append(
                {
                    "name": "synthetic-credential-cleanup",
                    "status": "pass" if cleanup_pass else "fail",
                }
            )

            restart_ready, service_recovery_time, status_codes, exit_code, diagnostic, attempts = (
                _run_canonical_service_restart(
                    config_path=config_path,
                    timeout_seconds=min(30.0, rto_seconds),
                )
            )
            suite_results.append(
                {
                    "name": "canonical-service-process-restart",
                    "status": "pass" if restart_ready else "fail",
                    "process_boundary": "child-process",
                    "status_codes": status_codes,
                    "premature_exit_code": exit_code,
                    "startup_attempts": attempts,
                    "diagnostic": diagnostic,
                    "actual_seconds": round(service_recovery_time, 6),
                }
            )
        finally:
            try:
                cleanup_service.update_config(
                    {field: "" for field in SYNTHETIC_SECRETS}
                )
                cleanup_service.save_config(
                    source="operational-recovery-drill-final-cleanup"
                )
            except Exception as exc:
                suite_results.append(
                    {
                        "name": "synthetic-credential-final-cleanup",
                        "status": "fail",
                        "error_type": type(exc).__name__,
                    }
                )

    recovery_time = max(config_recovery_time, service_recovery_time)

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
        issues.extend(
            str(result.get("name"))
            for result in suite_results
            if result.get("status") != "pass"
        )
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
        "config_recovery_time_seconds": round(config_recovery_time, 6),
        "service_recovery_time_seconds": round(service_recovery_time, 6),
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
            policy_path = (
                args.policy if args.policy.is_absolute() else REPO_ROOT / args.policy
            )
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
