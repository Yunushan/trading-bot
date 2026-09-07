#!/usr/bin/env python3
"""Exercise forced process exit, config backup/restore and read-only service recovery."""

from __future__ import annotations

import argparse
import hashlib
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
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


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
SYNTHETIC_SECRETS = {
    "api_key": "recovery-drill-exchange-key",
    "api_secret": "recovery-drill-exchange-secret",
    "llm_api_key": "recovery-drill-llm-secret",
}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


_NO_REDIRECT_OPENER = build_opener(ProxyHandler({}), _NoRedirectHandler)


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


def _read_only_json(url: str, *, api_token: str, deadline: float) -> tuple[int, dict[str, Any]]:
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return 0, {}
    request = Request(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_token}"},
        method="GET",
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=min(1.0, remaining)) as response:  # noqa: S310 - fixed loopback origin
            status = int(response.status)
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return status, {}
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                return status, {}
            return status, payload if isinstance(payload, dict) else {}
    except HTTPError as exc:
        try:
            return int(exc.code), {}
        finally:
            exc.close()
    except (OSError, TimeoutError, URLError):
        return 0, {}


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


def _child_environment(config_path: Path, api_token: str) -> dict[str, str]:
    # Carry only OS launch necessities, never caller credentials or trading/TLS/proxy flags.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "TEMP", "TMP", "LANG", "LC_ALL"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    environment.update({
        "HOME": str(config_path.parent),
        "USERPROFILE": str(config_path.parent),
        "APPDATA": str(config_path.parent),
        "LOCALAPPDATA": str(config_path.parent),
        "XDG_CONFIG_HOME": str(config_path.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "BOT_SERVICE_API_TOKEN": api_token,
        "BOT_SERVICE_API_READ_ONLY": "1",
        "BOT_ENABLE_LIVE_TRADING": "0",
    })
    return environment


def _launch_child(config_path: Path, port: int, api_token: str, output) -> subprocess.Popen[bytes]:  # noqa: ANN001
    return subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "apps" / "service-api" / "main.py"),
         "--serve", "--host", "127.0.0.1", "--port", str(port),
         "--config-path", str(config_path), "--load-config"],
        cwd=REPO_ROOT,
        env=_child_environment(config_path, api_token),
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _persisted_config_view(payload: dict[str, Any]) -> dict[str, Any]:
    view = json.loads(json.dumps(payload))
    llm = view.get("llm")
    if isinstance(llm, dict):
        # These describe the host's catalog, not settings restored from the backup.
        llm.pop("catalog_path", None)
        llm.pop("model_suggestions", None)
    return view


def _wait_for_service(process, base_url: str, api_token: str, expected_config: dict[str, Any], deadline: float) -> dict[str, Any]:  # noqa: ANN001
    expected_config = _persisted_config_view(expected_config)
    observation: dict[str, Any] = {"ready": False}
    while process.poll() is None and time.perf_counter() < deadline:
        responses = [
            _read_only_json(f"{base_url}{path}", api_token=api_token, deadline=deadline)
            for path in ("/livez", "/readyz", "/api/v1/runtime", "/api/v1/config")
        ]
        codes = [status for status, _ in responses]
        live, ready, runtime, config = [body for _, body in responses]
        config = _persisted_config_view(config)
        unauthenticated_status, _ = _read_only_json(f"{base_url}/api/v1/config", api_token="", deadline=deadline)
        control = runtime.get("control_plane")
        read_only = ready.get("read_only") is True and isinstance(control, dict) and control.get("trading_execution_supported") is False
        observation = {
            "status_codes": codes,
            "config_matches": config == expected_config,
            "config_mismatch_fields": sorted(key for key in config.keys() | expected_config.keys() if config.get(key) != expected_config.get(key)),
            "read_only_verified": read_only,
            "auth_verified": unauthenticated_status == 401,
        }
        observation["ready"] = bool(
            codes == [200] * 4 and live.get("status") == "ok" and ready.get("status") == "ready"
            and runtime.get("service_name") == "trading-bot-service" and observation["config_matches"]
            and read_only and observation["auth_verified"] and process.poll() is None
            and time.perf_counter() < deadline
        )
        if observation["ready"]:
            return observation
        time.sleep(min(0.1, max(0.0, deadline - time.perf_counter())))
    return {**observation, "ready": False}


def _restore_config_backup(config_path: Path, backup_path: Path) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=config_path.parent, prefix=".restore-", delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(backup_path.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, config_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _run_canonical_service_restart(
    *, config_path: Path, backup_path: Path, expected_config: dict[str, Any],
    backup_created_at: float, timeout_seconds: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    timeline: dict[str, float] = {}
    result: dict[str, Any] = {
        "name": "canonical-service-process-restart", "status": "fail",
        "process_boundary": "child-process", "timeline_seconds": timeline,
        "original_ready": False, "original_exit_observed": False,
        "endpoint_down_observed": False, "config_corruption_observed": False,
        "restored_config_matches": False, "read_only_verified": False, "auth_verified": False,
        "replacement_ready": False, "same_endpoint": False,
        "recovery_time_seconds": 0.0, "config_recovery_time_seconds": 0.0,
        "service_recovery_time_seconds": 0.0, "recovery_point_seconds": 0.0,
    }
    children = []
    tokens = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    port = _reserve_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as output:
        try:
            if config_path.is_symlink() or backup_path.is_symlink():
                raise ValueError("Recovery fixture files must not be symlinks")
            backup_digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            original = _launch_child(config_path, port, tokens[0], output)
            children.append(original)
            result.update(original_pid=original.pid, original_endpoint=base_url, backup_sha256=backup_digest)
            observation = _wait_for_service(original, base_url, tokens[0], expected_config, started + timeout_seconds)
            result["original_ready"] = observation["ready"]
            result["original_status_codes"] = observation.get("status_codes", [])
            result["original_verification"] = observation
            if not observation["ready"]:
                raise ValueError("Original service did not prove authenticated read-only configuration readiness")
            timeline["original_ready"] = time.perf_counter() - started
            outage_started = time.perf_counter()
            deadline = outage_started + timeout_seconds
            timeline["forced_exit_requested"] = outage_started - started
            result["recovery_point_seconds"] = max(0.0, outage_started - backup_created_at)
            original.kill()
            result["failure_mode"] = "forced-process-exit"
            result["original_exit_code"] = original.wait(timeout=max(0.01, deadline - time.perf_counter()))
            if result["original_exit_code"] == 0:
                raise ValueError("Original service exited normally instead of demonstrating a forced exit")
            result["original_exit_observed"] = True
            timeline["original_exit_observed"] = time.perf_counter() - started
            down_status, _ = _read_only_json(f"{base_url}/livez", api_token=tokens[0], deadline=deadline)
            if down_status != 0 or time.perf_counter() >= deadline:
                raise ValueError("The original endpoint did not become unavailable after forced process exit")
            result["endpoint_down_observed"] = True
            timeline["endpoint_down_observed"] = time.perf_counter() - started
            config_path.write_text('{"config":', encoding="utf-8")
            result["config_corruption_observed"] = hashlib.sha256(config_path.read_bytes()).hexdigest() != backup_digest
            timeline["config_corruption_observed"] = time.perf_counter() - started
            _restore_config_backup(config_path, backup_path)
            result["restored_backup_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
            if result["restored_backup_sha256"] != backup_digest:
                raise ValueError("Restored configuration does not match the backup bytes")
            timeline["config_restored"] = time.perf_counter() - started
            if time.perf_counter() >= deadline:
                raise ValueError("Recovery deadline expired before replacement startup")
            replacement = _launch_child(config_path, port, tokens[1], output)
            children.append(replacement)
            result.update(replacement_pid=replacement.pid, replacement_endpoint=base_url)
            result["same_endpoint"] = result["original_endpoint"] == result["replacement_endpoint"]
            timeline["replacement_started"] = time.perf_counter() - started
            recovered = _wait_for_service(replacement, base_url, tokens[1], expected_config, deadline)
            result["replacement_verification"] = recovered
            result.update(
                replacement_ready=recovered["ready"], status_codes=recovered.get("status_codes", []),
                restored_config_matches=recovered.get("config_matches", False),
                read_only_verified=observation["read_only_verified"] and recovered.get("read_only_verified", False),
                auth_verified=observation["auth_verified"] and recovered.get("auth_verified", False),
            )
            if not recovered["ready"] or original.pid == replacement.pid:
                raise ValueError("Distinct replacement did not prove authenticated read-only configuration readiness")
            timeline["replacement_ready"] = time.perf_counter() - started
            result["recovery_time_seconds"] = timeline["replacement_ready"] - timeline["forced_exit_requested"]
            result["config_recovery_time_seconds"] = timeline["config_restored"] - timeline["config_corruption_observed"]
            result["service_recovery_time_seconds"] = timeline["replacement_ready"] - timeline["config_restored"]
            result["status"] = "pass"
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result["diagnostic"] = redact_text(str(exc))
            diagnostic = _redacted_process_diagnostic(output, api_token=tokens[0])
            result["process_diagnostic"] = diagnostic.replace(tokens[1], "[REDACTED]")
        finally:
            for child in reversed(children):
                try:
                    _stop_child(child)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    result["status"] = "fail"
                    result["cleanup_error"] = type(exc).__name__
            result["children_stopped"] = all(child.poll() is not None for child in children)
            if not result["children_stopped"]:
                result["status"] = "fail"
    return result


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
                "mode": "Demo/Testnet",
                "live_trading_enabled": False,
                "llm_enabled": False,
                **SYNTHETIC_SECRETS,
            }
        )
        try:
            service.save_config(source="operational-recovery-drill")
            shutil.copy2(config_path, backup_path)
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

            # Remove synthetic credentials before either child starts or the recovery backup is taken.
            service.update_config({field: "" for field in SYNTHETIC_SECRETS})
            service.save_config(source="operational-recovery-drill-secret-cleanup")
            persisted_after_cleanup = config_path.read_text(encoding="utf-8")
            cleanup_payload = json.loads(persisted_after_cleanup)
            cleanup_pass = not cleanup_payload.get("credential_store_fields") and all(
                secret not in persisted_after_cleanup
                for secret in SYNTHETIC_SECRETS.values()
            )
            suite_results.append(
                {
                    "name": "synthetic-credential-cleanup",
                    "status": "pass" if cleanup_pass else "fail",
                }
            )

            if not safe_backup or not cleanup_pass:
                raise ValueError("Recovery fixture must have a redacted backup and cleared synthetic credentials")
            shutil.copy2(config_path, backup_path)
            backup_created_at = time.perf_counter()
            expected_config = service.get_config_payload().to_dict()
            expected_config["llm"]["api_key_present"] = False
            process_result = _run_canonical_service_restart(
                config_path=config_path, backup_path=backup_path,
                expected_config=expected_config,
                backup_created_at=backup_created_at,
                timeout_seconds=min(30.0, rto_seconds),
            )
            suite_results.append(process_result)
            suite_results.append({
                "name": "config-restore-round-trip",
                "status": "pass" if process_result["restored_config_matches"] else "fail",
            })
            config_recovery_time = process_result["config_recovery_time_seconds"]
            service_recovery_time = process_result["service_recovery_time_seconds"]
            recovery_time = process_result["recovery_time_seconds"]
            recovery_point = process_result["recovery_point_seconds"]
        finally:
            try:
                service.update_config(
                    {field: "" for field in SYNTHETIC_SECRETS}
                )
                service.save_config(
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
