#!/usr/bin/env python3
"""Audit Rust native runtime promotion readiness without weakening evidence gates."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from audit_native_source_sync import audit_native_source_sync
    from app.native_parity import native_python_source_contract_summary
    from check_generated_evidence_source_control import generated_evidence_write_guard
    from check_rust_native_local_recovery_evidence import local_recovery_generation_guard
    from check_rust_native_runtime_evidence import DEFAULT_MANIFEST_PATH, validate
    from write_rust_native_release_evidence import preflight_release_evidence_inputs
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.audit_native_source_sync import audit_native_source_sync
    from app.native_parity import native_python_source_contract_summary
    from tools.check_generated_evidence_source_control import generated_evidence_write_guard
    from tools.check_rust_native_local_recovery_evidence import local_recovery_generation_guard
    from tools.check_rust_native_runtime_evidence import DEFAULT_MANIFEST_PATH, validate
    from tools.write_rust_native_release_evidence import preflight_release_evidence_inputs


RUNTIME_READY_FUNCTION = "rust_native_trading_runtime_ready"
LIVE_SMOKE_EVIDENCE_IDS = {
    "rust-native-live-market-data-smoke",
    "rust-native-live-account-read-smoke",
}
LIVE_MARKET_EVIDENCE_ID = "rust-native-live-market-data-smoke"
LIVE_ACCOUNT_EVIDENCE_ID = "rust-native-live-account-read-smoke"
LIVE_SMOKE_WORKFLOW = "rust-native-live-smoke.yml"
LIVE_SMOKE_EVIDENCE_ARTIFACT = "rust-native-live-smoke-evidence"
LIVE_SMOKE_EVIDENCE_PLAN_ARTIFACT = "rust-native-live-smoke-evidence-plan"
LOCAL_RECOVERY_EVIDENCE_IDS = {
    "rust-native-live-stream-recovery",
    "rust-native-order-guard-recovery",
}
RELEASE_EVIDENCE_ID = "rust-native-release-platform-evidence"
EVIDENCE_IMPORT_COMMAND = (
    "python tools/import_rust_native_evidence_artifacts.py <artifact.zip-or-dir> "
    "artifacts/native-source-sync --apply --require-current-commit --require-clean-source "
    "--require-native-source-sync-audit"
)


def _runtime_evidence_import_command(required_runtime_ids: list[str] | tuple[str, ...]) -> str:
    suffix = " ".join(f"--require-runtime-id {evidence_id}" for evidence_id in required_runtime_ids)
    return f"{EVIDENCE_IMPORT_COMMAND} {suffix}".strip()


def _runtime_evidence_validation_command(required_runtime_ids: list[str] | tuple[str, ...]) -> str:
    only_flags = " ".join(f"--only {evidence_id}" for evidence_id in required_runtime_ids)
    return (
        "python tools/check_rust_native_runtime_evidence.py --require-evidence "
        "--require-current-commit --require-clean-source "
        "--evidence-dir artifacts/rust-native-runtime-evidence "
        f"{only_flags}"
    ).strip()


PROMOTION_EVIDENCE_IMPORT_COMMAND = _runtime_evidence_import_command(
    (
        LIVE_MARKET_EVIDENCE_ID,
        LIVE_ACCOUNT_EVIDENCE_ID,
        RELEASE_EVIDENCE_ID,
    )
)
GITHUB_PROMOTION_AUDIT_WORKFLOW = "rust-native-promotion-audit.yml"
GITHUB_PROMOTION_AUDIT_WORKFLOW_PLAN_ARTIFACT = "rust-native-promotion-evidence-plan"
GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND = (
    f"gh workflow run {GITHUB_PROMOTION_AUDIT_WORKFLOW} "
    "-f live_smoke_run_id=<live-smoke-actions-run-id> "
    "-f release_evidence_run_id=<release-evidence-actions-run-id>"
)
SOURCE_SYNC_AUDIT_STEP = "Audit native source sync"
SOURCE_SYNC_AUDIT_OUTPUT_PATH = "artifacts/native-source-sync/native-source-sync-audit.json"
SOURCE_SYNC_AUDIT_ARTIFACT = "native-source-sync-audit"
SOURCE_SYNC_AUDIT_COMMAND = (
    "python tools/audit_native_source_sync.py --json "
    f"--output {SOURCE_SYNC_AUDIT_OUTPUT_PATH}"
)
EVIDENCE_COLLECTION_ORDER = (
    LIVE_MARKET_EVIDENCE_ID,
    LIVE_ACCOUNT_EVIDENCE_ID,
    "rust-native-live-stream-recovery",
    "rust-native-order-guard-recovery",
    RELEASE_EVIDENCE_ID,
)


def _promotion_audit_workflow_inputs() -> dict[str, str]:
    return {
        "live_smoke_run_id": "<live-smoke-actions-run-id>",
        "release_evidence_run_id": "<release-evidence-actions-run-id>",
    }


def _promotion_required_runtime_ids() -> list[str]:
    return [
        LIVE_MARKET_EVIDENCE_ID,
        LIVE_ACCOUNT_EVIDENCE_ID,
        RELEASE_EVIDENCE_ID,
    ]


def _workflow_source_sync_audit() -> dict[str, Any]:
    return {
        "step": SOURCE_SYNC_AUDIT_STEP,
        "command": SOURCE_SYNC_AUDIT_COMMAND,
        "output_path": SOURCE_SYNC_AUDIT_OUTPUT_PATH,
        "github_workflow_artifact": SOURCE_SYNC_AUDIT_ARTIFACT,
        "required_before_evidence_collection": True,
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _runtime_ready_source_state(core_source: str) -> bool | None:
    pattern = re.compile(
        rf"pub\s+fn\s+{re.escape(RUNTIME_READY_FUNCTION)}\s*\(\s*\)\s*->\s*bool\s*"
        r"\{\s*(true|false)\s*\}",
        re.MULTILINE,
    )
    match = pattern.search(core_source)
    if not match:
        return None
    return match.group(1) == "true"


def _contains_all(source: str, needles: tuple[str, ...]) -> list[str]:
    return [needle for needle in needles if needle not in source]


def _env_present(name: str) -> bool:
    return bool(str(os.environ.get(name) or "").strip())


def _missing_named_prerequisites(checks: list[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in checks if not ok]


def _live_smoke_workflow_inputs(
    *,
    binance_testnet: str,
    symbol: str,
    interval: str,
) -> dict[str, str]:
    return {
        "binance_testnet": binance_testnet,
        "symbol": symbol,
        "interval": interval,
    }


def _live_smoke_prerequisites(evidence_dir: Path, *, source_tree_clean: bool = True) -> dict[str, Any]:
    api_key_present = _env_present("BINANCE_API_KEY")
    api_secret_present = _env_present("BINANCE_API_SECRET")
    confirmed = str(os.environ.get("TRADING_BOT_RUST_LIVE_SMOKE") or "").strip() == "1"
    market_confirmed = str(os.environ.get("TRADING_BOT_RUST_MARKET_SMOKE") or "").strip() == "1"
    binance_testnet = str(os.environ.get("BINANCE_TESTNET") or "true").strip() or "true"
    live_smoke_symbol = str(os.environ.get("BINANCE_LIVE_SMOKE_SYMBOL") or "BTCUSDT").strip() or "BTCUSDT"
    live_smoke_interval = str(os.environ.get("BINANCE_LIVE_SMOKE_INTERVAL") or "1m").strip() or "1m"
    workflow_inputs = _live_smoke_workflow_inputs(
        binance_testnet=binance_testnet,
        symbol=live_smoke_symbol,
        interval=live_smoke_interval,
    )
    market_expected_artifacts = [f"{LIVE_MARKET_EVIDENCE_ID}.json"]
    live_expected_artifacts = [
        f"{LIVE_MARKET_EVIDENCE_ID}.json",
        f"{LIVE_ACCOUNT_EVIDENCE_ID}.json",
    ]
    market_source_control_write_guard = generated_evidence_write_guard(
        [evidence_dir / "rust-native-live-market-data-smoke.json"],
        root=_repo_root(),
        require_generated_destinations=True,
    )
    account_source_control_write_guard = generated_evidence_write_guard(
        [
            evidence_dir / "rust-native-live-market-data-smoke.json",
            evidence_dir / "rust-native-live-account-read-smoke.json",
        ],
        root=_repo_root(),
        require_generated_destinations=True,
    )
    market_write_guard_ok = bool(market_source_control_write_guard.get("ok"))
    account_write_guard_ok = bool(account_source_control_write_guard.get("ok"))
    market_missing_prerequisites = _missing_named_prerequisites(
        [
            ("clean source tree", source_tree_clean),
            ("TRADING_BOT_RUST_MARKET_SMOKE=1", market_confirmed),
            ("generated evidence write guard", market_write_guard_ok),
        ]
    )
    account_missing_prerequisites = _missing_named_prerequisites(
        [
            ("clean source tree", source_tree_clean),
            ("BINANCE_API_KEY", api_key_present),
            ("BINANCE_API_SECRET", api_secret_present),
            ("TRADING_BOT_RUST_LIVE_SMOKE=1", confirmed),
            ("generated evidence write guard", account_write_guard_ok),
        ]
    )
    return {
        "binance_api_key_present": api_key_present,
        "binance_api_secret_present": api_secret_present,
        "live_smoke_confirmation_present": confirmed,
        "market_smoke_confirmation_present": market_confirmed,
        "binance_testnet": binance_testnet,
        "live_smoke_symbol": live_smoke_symbol,
        "live_smoke_interval": live_smoke_interval,
        "source_tree_clean": source_tree_clean,
        "market_missing_prerequisites": market_missing_prerequisites,
        "account_missing_prerequisites": account_missing_prerequisites,
        "can_run_live_smoke": (
            source_tree_clean and api_key_present and api_secret_present and confirmed and account_write_guard_ok
        ),
        "can_run_market_smoke": source_tree_clean and market_confirmed and market_write_guard_ok,
        "market_source_control_write_guard": market_source_control_write_guard,
        "account_source_control_write_guard": account_source_control_write_guard,
        "market_smoke_expected_artifacts": market_expected_artifacts,
        "live_smoke_expected_artifacts": live_expected_artifacts,
        "github_workflow_inputs": workflow_inputs,
        "github_workflow_artifact": LIVE_SMOKE_EVIDENCE_ARTIFACT,
        "github_workflow_plan_artifact": LIVE_SMOKE_EVIDENCE_PLAN_ARTIFACT,
        "github_workflow_requires_secrets": ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
        "workflow_source_sync_audit": _workflow_source_sync_audit(),
        "market_command": (
            "TRADING_BOT_RUST_MARKET_SMOKE=1 "
            f"BINANCE_TESTNET={binance_testnet} "
            f"BINANCE_LIVE_SMOKE_SYMBOL={live_smoke_symbol} "
            f"BINANCE_LIVE_SMOKE_INTERVAL={live_smoke_interval} "
            "cargo run -p trading-bot-rust -- --native-live-market-smoke"
        ),
        "market_preflight_command": "cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight",
        "command": (
            "TRADING_BOT_RUST_LIVE_SMOKE=1 BINANCE_API_KEY=... BINANCE_API_SECRET=... "
            f"BINANCE_TESTNET={binance_testnet} "
            f"BINANCE_LIVE_SMOKE_SYMBOL={live_smoke_symbol} "
            f"BINANCE_LIVE_SMOKE_INTERVAL={live_smoke_interval} "
            "cargo run -p trading-bot-rust -- --native-live-smoke"
        ),
        "preflight_command": "cargo run -p trading-bot-rust -- --native-live-smoke-preflight",
        "github_workflow": (
            f"gh workflow run {LIVE_SMOKE_WORKFLOW} "
            f"-f binance_testnet={binance_testnet} "
            f"-f symbol={live_smoke_symbol} "
            f"-f interval={live_smoke_interval}"
        ),
    }


def _release_evidence_prerequisites(root: Path, *, missing_limit: int = 10) -> dict[str, Any]:
    platform_evidence_dir = root / "release-platform-evidence"
    platform_evidence_count = (
        len(list(platform_evidence_dir.glob("*.json")))
        if platform_evidence_dir.is_dir()
        else 0
    )
    release_tag = str(os.environ.get("TRADING_BOT_RELEASE_TAG") or "v0.0.0").strip() or "v0.0.0"
    result: dict[str, Any] = {
        "release_tag": release_tag,
        "release_tag_configured": _env_present("TRADING_BOT_RELEASE_TAG"),
        "github_token_present": _env_present("GITHUB_TOKEN") or _env_present("GH_TOKEN"),
        "platform_evidence_dir": str(platform_evidence_dir),
        "platform_evidence_dir_exists": platform_evidence_dir.is_dir(),
        "platform_evidence_json_count": platform_evidence_count,
        "preflight_command": (
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence --preflight --json"
        ),
        "command": (
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence"
        ),
        "github_workflow": (
            "gh workflow run rust-native-release-evidence.yml -f tag=<tag> "
            "-f platform_evidence_run_id=<actions-run-id>"
        ),
        "workflow_source_sync_audit": _workflow_source_sync_audit(),
    }
    try:
        preflight = preflight_release_evidence_inputs(
            tag=release_tag,
            owner="Yunushan",
            repo="trading-bot",
            matrix_path=root / "docs" / "release-platform-test-matrix.json",
            platform_evidence_dir=platform_evidence_dir,
            output_dir=root / "artifacts" / "rust-native-runtime-evidence",
            missing_limit=missing_limit,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result.update(
            {
                "release_platform_preflight_ok": False,
                "release_platform_preflight_issues": [f"release evidence preflight failed: {exc}"],
            }
        )
        return result

    result.update(
        {
            "release_platform_preflight_ok": bool(preflight.get("ok")),
            "source_tree_clean": bool(preflight.get("source_tree_clean")),
            "release_asset_presence_verified": bool(preflight.get("release_asset_presence_verified")),
            "release_asset_presence_requires_network": bool(preflight.get("release_asset_presence_requires_network")),
            "release_evidence_target_count": int(preflight.get("release_evidence_target_count") or 0),
            "platform_target_count": int(preflight.get("platform_target_count") or 0),
            "browser_target_count": int(preflight.get("browser_target_count") or 0),
            "present_platform_evidence_count": int(preflight.get("present_platform_evidence_count") or 0),
            "passed_platform_evidence_count": int(preflight.get("passed_platform_evidence_count") or 0),
            "invalid_platform_evidence_count": int(preflight.get("invalid_platform_evidence_count") or 0),
            "unknown_platform_evidence_count": int(preflight.get("unknown_platform_evidence_count") or 0),
            "missing_platform_evidence_count": int(preflight.get("missing_platform_evidence_count") or 0),
            "missing_platform_evidence_limit": int(preflight.get("missing_platform_evidence_limit") or 0),
            "missing_platform_evidence_truncated": bool(preflight.get("missing_platform_evidence_truncated")),
            "missing_platform_evidence_all": list(preflight.get("missing_platform_evidence_all") or []),
            "missing_platform_evidence": list(preflight.get("missing_platform_evidence") or []),
            "missing_platform_evidence_plan": list(preflight.get("missing_platform_evidence_plan") or []),
            "workflow_dispatch_batch_plan": dict(preflight.get("workflow_dispatch_batch_plan") or {}),
            "local_browser_batch_plan": dict(preflight.get("local_browser_batch_plan") or {}),
            "source_control_write_guard": preflight.get("source_control_write_guard") or {},
            "release_platform_preflight_issues": list(preflight.get("issues") or []),
        }
    )
    return result


def _artifact_status_by_id(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = evidence.get("artifact_status")
    if not isinstance(rows, list):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            evidence_id = str(row.get("id") or "").strip()
            if evidence_id:
                parsed[evidence_id] = row
    return parsed


def _collection_row(
    *,
    evidence_id: str,
    status: dict[str, Any],
    collection_kind: str,
    prerequisites_ok: bool,
    expected_artifact: str,
    local_command: str,
    local_preflight_command: str = "",
    github_workflow: str = "",
    required_environment: list[str] | None = None,
    required_inputs: list[str] | None = None,
    required_runtime_ids: list[str] | None = None,
    safety: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok = bool(status.get("ok"))
    required_runtime_ids = list(required_runtime_ids or [evidence_id])
    return {
        "id": evidence_id,
        "category": str(status.get("category") or ""),
        "collection_kind": collection_kind,
        "status": "passed" if ok else "missing_or_failing",
        "ready_to_collect": bool(not ok and prerequisites_ok),
        "prerequisites_ok": bool(prerequisites_ok),
        "expected_artifact": expected_artifact,
        "canonical_path": str(status.get("path") or f"artifacts/rust-native-runtime-evidence/{expected_artifact}"),
        "local_preflight_command": local_preflight_command,
        "local_command": local_command,
        "github_workflow": github_workflow,
        "validation_command": _runtime_evidence_validation_command(required_runtime_ids),
        "import_command": _runtime_evidence_import_command(required_runtime_ids),
        "required_runtime_ids": required_runtime_ids,
        "required_environment": list(required_environment or []),
        "required_inputs": list(required_inputs or []),
        "safety": dict(safety or {}),
        "details": dict(details or {}),
        "issues": [str(issue) for issue in status.get("issues", [])],
    }


def _evidence_collection_plan(
    *,
    artifact_status_by_id: dict[str, dict[str, Any]],
    live_smoke_prerequisites: dict[str, Any],
    local_recovery_prerequisites: dict[str, Any],
    release_evidence_prerequisites: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evidence_id in EVIDENCE_COLLECTION_ORDER:
        status = artifact_status_by_id.get(evidence_id, {"id": evidence_id, "ok": False, "issues": ["not validated"]})
        expected_artifact = f"{evidence_id}.json"
        if evidence_id == LIVE_MARKET_EVIDENCE_ID:
            market_guard = dict(live_smoke_prerequisites.get("market_source_control_write_guard") or {})
            source_tree_clean = bool(live_smoke_prerequisites.get("source_tree_clean"))
            rows.append(
                _collection_row(
                    evidence_id=evidence_id,
                    status=status,
                    collection_kind="live_market_data_smoke",
                    prerequisites_ok=bool(live_smoke_prerequisites.get("can_run_market_smoke")),
                    expected_artifact=expected_artifact,
                    local_preflight_command=str(live_smoke_prerequisites.get("market_preflight_command") or ""),
                    local_command=str(live_smoke_prerequisites.get("market_command") or ""),
                    github_workflow=str(live_smoke_prerequisites.get("github_workflow") or ""),
                    required_environment=[
                        "TRADING_BOT_RUST_MARKET_SMOKE=1",
                        f"BINANCE_TESTNET={live_smoke_prerequisites.get('binance_testnet') or 'true'}",
                    ],
                    required_runtime_ids=[LIVE_MARKET_EVIDENCE_ID],
                    safety={
                        "read_only": True,
                        "requires_credentials": False,
                        "order_submission_attempted": False,
                    },
                    details={
                        "source_tree_clean": source_tree_clean,
                        "missing_prerequisites": list(
                            live_smoke_prerequisites.get("market_missing_prerequisites") or []
                        ),
                        "source_control_write_guard": market_guard,
                        "binance_testnet": str(live_smoke_prerequisites.get("binance_testnet") or "true"),
                        "live_smoke_symbol": str(live_smoke_prerequisites.get("live_smoke_symbol") or "BTCUSDT"),
                        "live_smoke_interval": str(live_smoke_prerequisites.get("live_smoke_interval") or "1m"),
                        "expected_artifacts": list(
                            live_smoke_prerequisites.get("market_smoke_expected_artifacts") or [expected_artifact]
                        ),
                        "github_workflow_inputs": dict(
                            live_smoke_prerequisites.get("github_workflow_inputs") or {}
                        ),
                        "github_workflow_artifact": str(
                            live_smoke_prerequisites.get("github_workflow_artifact") or ""
                        ),
                        "github_workflow_plan_artifact": str(
                            live_smoke_prerequisites.get("github_workflow_plan_artifact") or ""
                        ),
                        "workflow_source_sync_audit": dict(
                            live_smoke_prerequisites.get("workflow_source_sync_audit")
                            or _workflow_source_sync_audit()
                        ),
                    },
                )
            )
            rows[-1]["issues"].extend(str(issue) for issue in market_guard.get("issues", []))
            if not source_tree_clean:
                rows[-1]["issues"].append(
                    "source tree must be clean before collecting Rust native live market-data evidence"
                )
        elif evidence_id == LIVE_ACCOUNT_EVIDENCE_ID:
            account_guard = dict(live_smoke_prerequisites.get("account_source_control_write_guard") or {})
            source_tree_clean = bool(live_smoke_prerequisites.get("source_tree_clean"))
            rows.append(
                _collection_row(
                    evidence_id=evidence_id,
                    status=status,
                    collection_kind="live_signed_account_read_smoke",
                    prerequisites_ok=bool(live_smoke_prerequisites.get("can_run_live_smoke")),
                    expected_artifact=expected_artifact,
                    local_preflight_command=str(live_smoke_prerequisites.get("preflight_command") or ""),
                    local_command=str(live_smoke_prerequisites.get("command") or ""),
                    github_workflow=str(live_smoke_prerequisites.get("github_workflow") or ""),
                    required_environment=[
                        "TRADING_BOT_RUST_LIVE_SMOKE=1",
                        "BINANCE_API_KEY",
                        "BINANCE_API_SECRET",
                        f"BINANCE_TESTNET={live_smoke_prerequisites.get('binance_testnet') or 'true'}",
                    ],
                    required_runtime_ids=[LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID],
                    safety={
                        "read_only": True,
                        "requires_credentials": True,
                        "order_submission_attempted": False,
                    },
                    details={
                        "source_tree_clean": source_tree_clean,
                        "binance_api_key_present": bool(live_smoke_prerequisites.get("binance_api_key_present")),
                        "binance_api_secret_present": bool(live_smoke_prerequisites.get("binance_api_secret_present")),
                        "live_smoke_confirmation_present": bool(
                            live_smoke_prerequisites.get("live_smoke_confirmation_present")
                        ),
                        "missing_prerequisites": list(
                            live_smoke_prerequisites.get("account_missing_prerequisites") or []
                        ),
                        "source_control_write_guard": account_guard,
                        "binance_testnet": str(live_smoke_prerequisites.get("binance_testnet") or "true"),
                        "live_smoke_symbol": str(live_smoke_prerequisites.get("live_smoke_symbol") or "BTCUSDT"),
                        "live_smoke_interval": str(live_smoke_prerequisites.get("live_smoke_interval") or "1m"),
                        "expected_artifacts": list(
                            live_smoke_prerequisites.get("live_smoke_expected_artifacts") or [expected_artifact]
                        ),
                        "github_workflow_inputs": dict(
                            live_smoke_prerequisites.get("github_workflow_inputs") or {}
                        ),
                        "github_workflow_artifact": str(
                            live_smoke_prerequisites.get("github_workflow_artifact") or ""
                        ),
                        "github_workflow_plan_artifact": str(
                            live_smoke_prerequisites.get("github_workflow_plan_artifact") or ""
                        ),
                        "github_workflow_requires_secrets": list(
                            live_smoke_prerequisites.get("github_workflow_requires_secrets") or []
                        ),
                        "workflow_source_sync_audit": dict(
                            live_smoke_prerequisites.get("workflow_source_sync_audit")
                            or _workflow_source_sync_audit()
                        ),
                    },
                )
            )
            rows[-1]["issues"].extend(str(issue) for issue in account_guard.get("issues", []))
            if not source_tree_clean:
                rows[-1]["issues"].append(
                    "source tree must be clean before collecting Rust native signed account-read evidence"
                )
        elif evidence_id in LOCAL_RECOVERY_EVIDENCE_IDS:
            local_recovery_guard_ok = bool(local_recovery_prerequisites.get("ok"))
            local_recovery_issues = [str(issue) for issue in local_recovery_prerequisites.get("issues", [])]
            rows.append(
                _collection_row(
                    evidence_id=evidence_id,
                    status=status,
                    collection_kind="deterministic_local_recovery",
                    prerequisites_ok=local_recovery_guard_ok,
                    expected_artifact=expected_artifact,
                    local_preflight_command="",
                    local_command=(
                        "cargo run -p trading-bot-rust -- --write-local-recovery-evidence && "
                        "python tools/check_rust_native_local_recovery_evidence.py "
                        "--evidence-dir artifacts/rust-native-runtime-evidence --json"
                    ),
                    required_environment=[],
                    required_runtime_ids=[evidence_id],
                    safety={
                        "read_only": True,
                        "requires_credentials": False,
                        "order_submission_attempted": False,
                    },
                    details={
                        "source_control_guard": dict(local_recovery_prerequisites),
                        "source_control_guard_ok": local_recovery_guard_ok,
                        "generated_evidence_write_targets": list(
                            local_recovery_prerequisites.get("generated_evidence_write_targets") or []
                        ),
                        "non_generated_in_repo_write_targets": list(
                            local_recovery_prerequisites.get("non_generated_in_repo_write_targets") or []
                        ),
                        "tracked_generated_evidence_targets": list(
                            local_recovery_prerequisites.get("tracked_generated_evidence_targets") or []
                        ),
                    },
                )
            )
            if local_recovery_issues:
                rows[-1]["issues"].extend(local_recovery_issues)
        elif evidence_id == RELEASE_EVIDENCE_ID:
            release_preflight_issues = [
                str(issue) for issue in release_evidence_prerequisites.get("release_platform_preflight_issues", [])
            ]
            rows.append(
                _collection_row(
                    evidence_id=evidence_id,
                    status=status,
                    collection_kind="release_platform_evidence",
                    prerequisites_ok=bool(release_evidence_prerequisites.get("release_platform_preflight_ok")),
                    expected_artifact=expected_artifact,
                    local_preflight_command=str(release_evidence_prerequisites.get("preflight_command") or ""),
                    local_command=str(release_evidence_prerequisites.get("command") or ""),
                    github_workflow=str(release_evidence_prerequisites.get("github_workflow") or ""),
                    required_environment=["TRADING_BOT_RELEASE_TAG", "GITHUB_TOKEN or GH_TOKEN"],
                    required_inputs=["Rust release assets", "passed release-platform-evidence JSON for every target"],
                    required_runtime_ids=[RELEASE_EVIDENCE_ID],
                    safety={
                        "read_only": True,
                        "requires_credentials": False,
                        "order_submission_attempted": False,
                    },
                    details={
                        "release_tag_configured": bool(
                            release_evidence_prerequisites.get("release_tag_configured")
                        ),
                        "release_platform_preflight_ok": bool(
                            release_evidence_prerequisites.get("release_platform_preflight_ok")
                        ),
                        "source_tree_clean": bool(release_evidence_prerequisites.get("source_tree_clean")),
                        "missing_platform_evidence_count": int(
                            release_evidence_prerequisites.get("missing_platform_evidence_count") or 0
                        ),
                        "release_evidence_target_count": int(
                            release_evidence_prerequisites.get("release_evidence_target_count") or 0
                        ),
                        "platform_target_count": int(
                            release_evidence_prerequisites.get("platform_target_count") or 0
                        ),
                        "browser_target_count": int(
                            release_evidence_prerequisites.get("browser_target_count") or 0
                        ),
                        "missing_platform_evidence_limit": int(
                            release_evidence_prerequisites.get("missing_platform_evidence_limit") or 0
                        ),
                        "missing_platform_evidence_truncated": bool(
                            release_evidence_prerequisites.get("missing_platform_evidence_truncated")
                        ),
                        "missing_platform_evidence_all": list(
                            release_evidence_prerequisites.get("missing_platform_evidence_all") or []
                        ),
                        "missing_platform_evidence_plan": list(
                            release_evidence_prerequisites.get("missing_platform_evidence_plan") or []
                        ),
                        "workflow_dispatch_batch_plan": dict(
                            release_evidence_prerequisites.get("workflow_dispatch_batch_plan") or {}
                        ),
                        "workflow_source_sync_audit": dict(
                            release_evidence_prerequisites.get("workflow_source_sync_audit")
                            or _workflow_source_sync_audit()
                        ),
                        "local_browser_batch_plan": dict(
                            release_evidence_prerequisites.get("local_browser_batch_plan") or {}
                        ),
                        "release_asset_presence_verified": bool(
                            release_evidence_prerequisites.get("release_asset_presence_verified")
                        ),
                        "source_control_write_guard": dict(
                            release_evidence_prerequisites.get("source_control_write_guard") or {}
                        ),
                    },
                )
            )
            if release_preflight_issues:
                rows[-1]["issues"].extend(release_preflight_issues)
    return rows


def _failed_requirement_ids(promotion_model: dict[str, Any]) -> set[str]:
    rows = promotion_model.get("failed_requirement_ids")
    if not isinstance(rows, list):
        return set()
    return {str(row) for row in rows}


def _evidence_collection_rows_by_id(
    evidence_collection_plan: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(evidence_collection_plan, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in evidence_collection_plan:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("id") or "")
        if evidence_id:
            rows[evidence_id] = row
    return rows


def _evidence_collection_blockers(
    evidence_ids: list[str],
    evidence_rows_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    for evidence_id in evidence_ids:
        row = evidence_rows_by_id.get(evidence_id)
        if not row:
            continue
        if str(row.get("status") or "") == "passed":
            continue
        if bool(row.get("ready_to_collect")):
            continue
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        missing = [str(item) for item in details.get("missing_prerequisites") or []]
        if not missing:
            missing = [str(issue) for issue in row.get("issues") or []]
        if missing:
            blockers.extend(f"{evidence_id}: {item}" for item in missing)
        else:
            blockers.append(f"{evidence_id}: collection prerequisites are not satisfied")
    return blockers


def _evidence_action_details(
    evidence_ids: list[str],
    evidence_rows_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for evidence_id in evidence_ids:
        row = evidence_rows_by_id.get(evidence_id)
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "id": evidence_id,
                "status": str(row.get("status") or ""),
                "ready_to_collect": bool(row.get("ready_to_collect")),
                "collection_kind": str(row.get("collection_kind") or ""),
                "expected_artifact": str(row.get("expected_artifact") or ""),
                "local_preflight_command": str(row.get("local_preflight_command") or ""),
                "local_command": str(row.get("local_command") or ""),
                "github_workflow": str(row.get("github_workflow") or ""),
                "import_command": str(row.get("import_command") or ""),
                "validation_command": str(row.get("validation_command") or ""),
                "required_environment": [str(item) for item in row.get("required_environment") or []],
                "required_inputs": [str(item) for item in row.get("required_inputs") or []],
                "required_runtime_ids": [str(item) for item in row.get("required_runtime_ids") or []],
                "safety": dict(row.get("safety") or {}),
                "details": dict(row.get("details") or {}),
                "issues": [str(item) for item in row.get("issues") or []],
            }
        )
    return {
        "evidence_row_count": len(rows),
        "evidence_rows": rows,
    }


def _next_action_plan(
    remaining_ids: list[str],
    promotion_model: dict[str, Any] | None = None,
    evidence_collection_plan: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    failed_requirement_ids = _failed_requirement_ids(promotion_model or {})
    evidence_rows_by_id = _evidence_collection_rows_by_id(evidence_collection_plan)
    clean_source_scope = {}
    if isinstance(promotion_model, dict) and isinstance(promotion_model.get("clean_source_scope"), dict):
        clean_source_scope = dict(promotion_model["clean_source_scope"])
    clean_source_action_id = "create_clean_candidate_source_revision"
    clean_source_action_needed = bool(
        clean_source_scope.get("dirty_paths") or clean_source_scope.get("untracked_paths")
    )
    clean_source_dependency = [clean_source_action_id] if clean_source_action_needed else []

    def add_action(
        *,
        action_id: str,
        title: str,
        summary: str,
        requirement_ids: list[str],
        evidence_ids: list[str] | None = None,
        commands: list[str] | None = None,
        github_workflow: str = "",
        details: dict[str, Any] | None = None,
        depends_on_action_ids: list[str] | None = None,
        blocked_by: list[str] | None = None,
        ready_to_run: bool | None = None,
    ) -> None:
        blockers = [str(blocker) for blocker in blocked_by or [] if str(blocker)]
        action_ready = not blockers if ready_to_run is None else bool(ready_to_run)
        actions.append(
            {
                "id": action_id,
                "title": title,
                "summary": summary,
                "requirement_ids": requirement_ids,
                "evidence_ids": list(evidence_ids or []),
                "commands": list(commands or []),
                "github_workflow": github_workflow,
                "details": dict(details or {}),
                "depends_on_action_ids": list(depends_on_action_ids or []),
                "blocked_by": blockers,
                "ready_to_run": action_ready,
            }
        )

    if "native_source_sync" in failed_requirement_ids:
        add_action(
            action_id="regenerate_python_owned_native_contracts",
            title="Regenerate Python-owned native contracts",
            summary=(
                "Regenerate Python-owned native parity contracts with "
                "python Languages/Python/tools/generate_native_parity_contracts.py, then rerun "
                "python tools/audit_native_source_sync.py --json before collecting promotion evidence."
            ),
            requirement_ids=["native_source_sync"],
            commands=[
                "python Languages/Python/tools/generate_native_parity_contracts.py",
                "python tools/audit_native_source_sync.py --json",
            ],
        )
    if "python_runtime_readiness_source" in failed_requirement_ids:
        add_action(
            action_id="align_python_runtime_readiness_source",
            title="Align Python runtime readiness source",
            summary=(
                "Align Languages/Python/app/native_parity.py rust_standalone_runtime_ready with "
                "rust_native_trading_runtime_ready() before collecting or importing promotion evidence."
            ),
            requirement_ids=["python_runtime_readiness_source"],
            commands=["python tools/audit_rust_native_runtime_readiness.py --json"],
        )
    if "evidence_declaration" in failed_requirement_ids:
        add_action(
            action_id="align_runtime_evidence_manifest_policy",
            title="Align runtime evidence manifest policy",
            summary=(
                "Align docs/rust-native-runtime-evidence.json policy.runtime_ready_flag with the Rust "
                "runtime-ready source guard before using runtime evidence for promotion."
            ),
            requirement_ids=["evidence_declaration"],
            commands=["python tools/check_rust_native_runtime_evidence.py --schema-only"],
        )
    if "current_commit_clean_source_evidence" in failed_requirement_ids:
        add_action(
            action_id=clean_source_action_id,
            title="Create clean candidate source revision",
            summary=(
                "Create a clean candidate source revision before collecting or importing promotion evidence: "
                "the tracked source tree must be clean, untracked source/tool files must be absent, and only "
                "canonical evidence directories may be ignored by the current-commit evidence validators."
            ),
            requirement_ids=["current_commit_clean_source_evidence"],
            commands=[
                "git status --short",
                (
                    "python tools/check_rust_native_runtime_evidence.py --require-evidence "
                    "--require-current-commit --require-clean-source --evidence-dir artifacts/rust-native-runtime-evidence"
                ),
            ],
            details={"clean_source_scope": clean_source_scope},
        )
    if LIVE_MARKET_EVIDENCE_ID in remaining_ids:
        market_blockers = _evidence_collection_blockers([LIVE_MARKET_EVIDENCE_ID], evidence_rows_by_id)
        market_row = evidence_rows_by_id.get(LIVE_MARKET_EVIDENCE_ID, {})
        market_details = _evidence_action_details([LIVE_MARKET_EVIDENCE_ID], evidence_rows_by_id)
        market_preflight_command = str(market_row.get("local_preflight_command") or "")
        market_collection_command = str(market_row.get("local_command") or "")
        market_commands = [
            command for command in [market_preflight_command, market_collection_command] if command
        ]
        add_action(
            action_id="collect_rust_native_live_market_smoke",
            title="Collect Rust native live market-data smoke evidence",
            summary=(
                "Run cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight, then run "
                "TRADING_BOT_RUST_MARKET_SMOKE=1 BINANCE_TESTNET=true cargo run -p trading-bot-rust "
                "-- --native-live-market-smoke; it writes rust-native-live-market-data-smoke.json "
                "without credentials or order submission."
            ),
            requirement_ids=["required_runtime_evidence"],
            evidence_ids=[LIVE_MARKET_EVIDENCE_ID],
            commands=market_commands,
            github_workflow=str(market_row.get("github_workflow") or ""),
            details=market_details,
            depends_on_action_ids=clean_source_dependency,
            blocked_by=market_blockers,
        )
    if LIVE_ACCOUNT_EVIDENCE_ID in remaining_ids:
        account_blockers = _evidence_collection_blockers([LIVE_ACCOUNT_EVIDENCE_ID], evidence_rows_by_id)
        account_dependencies = list(clean_source_dependency)
        if LIVE_MARKET_EVIDENCE_ID in remaining_ids:
            account_dependencies.append("collect_rust_native_live_market_smoke")
        account_row = evidence_rows_by_id.get(LIVE_ACCOUNT_EVIDENCE_ID, {})
        account_github_workflow = str(account_row.get("github_workflow") or "")
        account_row_details = account_row.get("details") if isinstance(account_row.get("details"), dict) else {}
        account_preflight_command = str(account_row.get("local_preflight_command") or "")
        account_collection_command = str(account_row.get("local_command") or "")
        account_details = _evidence_action_details(
            [LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID],
            evidence_rows_by_id,
        )
        account_details.update(
            {
                "requires_credentials": True,
                "order_submission_attempted": False,
                "github_workflow_inputs": dict(account_row_details.get("github_workflow_inputs") or {}),
                "expected_artifacts": list(account_row_details.get("expected_artifacts") or []),
                "github_workflow_artifact": str(account_row_details.get("github_workflow_artifact") or ""),
                "github_workflow_plan_artifact": str(
                    account_row_details.get("github_workflow_plan_artifact") or ""
                ),
                "github_workflow_requires_secrets": list(
                    account_row_details.get("github_workflow_requires_secrets") or []
                ),
                "workflow_source_sync_audit": dict(
                    account_row_details.get("workflow_source_sync_audit")
                    or _workflow_source_sync_audit()
                ),
            }
        )
        add_action(
            action_id="collect_rust_native_live_account_smoke",
            title="Collect Rust native signed account-read smoke evidence",
            summary=(
                "Run cargo run -p trading-bot-rust -- --native-live-smoke-preflight, then run "
                "the guarded Rust live smoke with Binance credentials on testnet or production; "
                "it writes rust-native-live-account-read-smoke.json without submitting orders. "
                "On GitHub, use the manual rust-native-live-smoke.yml workflow with "
                "BINANCE_API_KEY and BINANCE_API_SECRET repository secrets. After downloading "
                "the workflow artifact ZIP or folder, run "
                f"{_runtime_evidence_import_command([LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID])} "
                "to validate and import it."
            ),
            requirement_ids=["required_runtime_evidence"],
            evidence_ids=[LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID],
            commands=[
                command
                for command in [
                    account_preflight_command,
                    account_collection_command,
                    _runtime_evidence_import_command([LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID]),
                ]
                if command
            ],
            github_workflow=account_github_workflow,
            details=account_details,
            depends_on_action_ids=account_dependencies,
            blocked_by=account_blockers,
        )
    if any(evidence_id in LOCAL_RECOVERY_EVIDENCE_IDS for evidence_id in remaining_ids):
        recovery_ids = [evidence_id for evidence_id in LOCAL_RECOVERY_EVIDENCE_IDS if evidence_id in remaining_ids]
        recovery_blockers = _evidence_collection_blockers(recovery_ids, evidence_rows_by_id)
        recovery_details = _evidence_action_details(recovery_ids, evidence_rows_by_id)
        add_action(
            action_id="collect_rust_native_local_recovery_evidence",
            title="Collect deterministic Rust native local recovery evidence",
            summary=(
                "Run python tools/check_rust_native_local_recovery_evidence.py "
                "--evidence-dir artifacts/rust-native-runtime-evidence --json."
            ),
            requirement_ids=["required_runtime_evidence"],
            evidence_ids=recovery_ids,
            commands=[
                "python tools/check_rust_native_local_recovery_evidence.py --evidence-dir artifacts/rust-native-runtime-evidence --json"
            ],
            details=recovery_details,
            depends_on_action_ids=clean_source_dependency,
            blocked_by=recovery_blockers,
        )
    if RELEASE_EVIDENCE_ID in remaining_ids:
        release_blockers = _evidence_collection_blockers([RELEASE_EVIDENCE_ID], evidence_rows_by_id)
        release_details = _evidence_action_details([RELEASE_EVIDENCE_ID], evidence_rows_by_id)
        release_rows = release_details.get("evidence_rows")
        release_row = release_rows[0] if isinstance(release_rows, list) and release_rows else {}
        release_row_details = release_row.get("details") if isinstance(release_row, dict) else {}
        if isinstance(release_row_details, dict):
            release_details.update(
                {
                    "release_evidence_target_count": release_row_details.get("release_evidence_target_count"),
                    "platform_target_count": release_row_details.get("platform_target_count"),
                    "browser_target_count": release_row_details.get("browser_target_count"),
                    "missing_platform_evidence_count": release_row_details.get("missing_platform_evidence_count"),
                    "missing_platform_evidence_truncated": release_row_details.get(
                        "missing_platform_evidence_truncated"
                    ),
                    "local_browser_batch_plan": dict(release_row_details.get("local_browser_batch_plan") or {}),
                    "missing_platform_evidence_plan": list(
                        release_row_details.get("missing_platform_evidence_plan") or []
                    ),
                    "workflow_dispatch_batch_plan": dict(
                        release_row_details.get("workflow_dispatch_batch_plan") or {}
                    ),
                    "workflow_source_sync_audit": dict(
                        release_row_details.get("workflow_source_sync_audit")
                        or _workflow_source_sync_audit()
                    ),
                }
            )
            workflow_dispatch_batch = (
                release_row_details.get("workflow_dispatch_batch_plan")
                if isinstance(release_row_details.get("workflow_dispatch_batch_plan"), dict)
                else {}
            )
            release_details.update(
                {
                    "workflow_dispatch_batch_command_target_ids": list(
                        workflow_dispatch_batch.get("command_target_ids") or []
                    ),
                    "workflow_dispatch_batch_command_limit": int(
                        workflow_dispatch_batch.get("command_limit") or 0
                    ),
                    "workflow_dispatch_batch_manual_input_target_count": int(
                        workflow_dispatch_batch.get("manual_input_target_count") or 0
                    ),
                    "workflow_dispatch_batch_commands_truncated": bool(
                        workflow_dispatch_batch.get("commands_truncated")
                    ),
                    "workflow_dispatch_batch_manual_input_targets_truncated": bool(
                        workflow_dispatch_batch.get("manual_input_targets_truncated")
                    ),
                }
            )
        add_action(
            action_id="collect_rust_native_release_platform_evidence",
            title="Collect Rust native release-platform evidence",
            summary=(
                "Run python tools/write_rust_native_release_evidence.py --tag <tag> "
                "--platform-evidence-dir release-platform-evidence --preflight --json; after Rust "
                "release assets and release-platform evidence exist, run "
                "python tools/write_rust_native_release_evidence.py --tag <tag> "
                "--platform-evidence-dir release-platform-evidence. On GitHub, use the manual "
                "rust-native-release-evidence.yml workflow with a release tag and the run id "
                f"that contains release-platform-evidence-* artifacts. After downloading "
                "the workflow artifact ZIP or folder, run "
                f"{_runtime_evidence_import_command([RELEASE_EVIDENCE_ID])} to validate and import it."
            ),
            requirement_ids=["required_runtime_evidence"],
            evidence_ids=[RELEASE_EVIDENCE_ID],
            commands=[
                "python tools/write_rust_native_release_evidence.py --tag <tag> --platform-evidence-dir release-platform-evidence --preflight --json",
                "python tools/write_rust_native_release_evidence.py --tag <tag> --platform-evidence-dir release-platform-evidence",
                _runtime_evidence_import_command([RELEASE_EVIDENCE_ID]),
            ],
            github_workflow=(
                "gh workflow run rust-native-release-evidence.yml -f tag=<tag> "
                "-f platform_evidence_run_id=<actions-run-id>"
            ),
            details=release_details,
            depends_on_action_ids=clean_source_dependency,
            blocked_by=release_blockers,
        )
    if remaining_ids:
        audit_blockers = [
            f"missing runtime evidence: {evidence_id}"
            for evidence_id in remaining_ids
        ]
        if "current_commit_clean_source_evidence" in failed_requirement_ids:
            audit_blockers.append("current-commit clean-source evidence is not passing")
        prerequisite_action_ids: list[str] = []
        if "current_commit_clean_source_evidence" in failed_requirement_ids:
            prerequisite_action_ids.append(clean_source_action_id)
        if LIVE_MARKET_EVIDENCE_ID in remaining_ids:
            prerequisite_action_ids.append("collect_rust_native_live_market_smoke")
        if LIVE_ACCOUNT_EVIDENCE_ID in remaining_ids:
            prerequisite_action_ids.append("collect_rust_native_live_account_smoke")
        if any(evidence_id in LOCAL_RECOVERY_EVIDENCE_IDS for evidence_id in remaining_ids):
            prerequisite_action_ids.append("collect_rust_native_local_recovery_evidence")
        if RELEASE_EVIDENCE_ID in remaining_ids:
            prerequisite_action_ids.append("collect_rust_native_release_platform_evidence")
        add_action(
            action_id="run_rust_native_promotion_audit_workflow",
            title="Run Rust native promotion audit workflow",
            summary=(
                "After the live-smoke and release-evidence workflow artifacts exist for the same candidate "
                f"source commit, run {GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND}; it downloads, imports, "
                "regenerates deterministic local recovery evidence, validates the full evidence set, and "
                "runs python tools/audit_rust_native_runtime_readiness.py --require-ready --json."
            ),
            requirement_ids=["required_runtime_evidence", "current_commit_clean_source_evidence"],
            evidence_ids=list(remaining_ids),
            commands=["python tools/audit_rust_native_runtime_readiness.py --require-ready --json"],
            github_workflow=GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND,
            details={
                "github_workflow": GITHUB_PROMOTION_AUDIT_WORKFLOW,
                "github_workflow_inputs": _promotion_audit_workflow_inputs(),
                "github_workflow_plan_artifact": GITHUB_PROMOTION_AUDIT_WORKFLOW_PLAN_ARTIFACT,
                "workflow_source_sync_audit": _workflow_source_sync_audit(),
                "required_runtime_ids": _promotion_required_runtime_ids(),
                "evidence_import_command": PROMOTION_EVIDENCE_IMPORT_COMMAND,
            },
            depends_on_action_ids=prerequisite_action_ids,
            blocked_by=audit_blockers,
        )
    if "runtime_ready_source_guard" in failed_requirement_ids:
        guard_blockers = [
            f"failed promotion requirement: {requirement_id}"
            for requirement_id in sorted(failed_requirement_ids - {"runtime_ready_source_guard"})
        ]
        guard_blockers.extend(f"missing runtime evidence: {evidence_id}" for evidence_id in remaining_ids)
        add_action(
            action_id="promote_runtime_ready_source_guard",
            title="Promote Rust runtime-ready source guard",
            summary=(
                "Keep rust_native_trading_runtime_ready() false until required runtime evidence, clean-source "
                "current-commit validation, Python native parity source, manifest policy, and Tauri runtime-ready "
                "text all agree; after those gates pass, promote the source guard and rerun the strict readiness audit."
            ),
            requirement_ids=["runtime_ready_source_guard"],
            commands=[
                "python tools/audit_rust_native_runtime_readiness.py --require-ready --json",
                "python Languages/Python/tools/generate_native_parity_contracts.py",
                "python tools/audit_native_source_sync.py --json",
            ],
            depends_on_action_ids=(
                ["run_rust_native_promotion_audit_workflow"] if remaining_ids else []
            ),
            blocked_by=guard_blockers,
        )
    return actions


def _next_actions(
    remaining_ids: list[str],
    promotion_model: dict[str, Any] | None = None,
    evidence_collection_plan: list[dict[str, Any]] | None = None,
) -> list[str]:
    return [
        str(row.get("summary") or "")
        for row in _next_action_plan(remaining_ids, promotion_model, evidence_collection_plan)
    ]


def _source_contract_audit(root: Path) -> dict[str, Any]:
    rust_root = root / "experiments" / "rust-shells"
    core = _read(rust_root / "crates" / "core" / "src" / "lib.rs")
    generated = _read(rust_root / "crates" / "core" / "src" / "generated_python_parity.rs")
    tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")
    rust_main = _read(rust_root / "src" / "main.rs")
    readme = _read(rust_root / "README.md")
    runtime_ready = _runtime_ready_source_state(core)
    runtime_ready_label = str(runtime_ready).lower() if runtime_ready is not None else "<unknown>"

    missing: list[str] = []
    missing.extend(
        f"core missing {needle}"
        for needle in _contains_all(
            core,
            (
                "pub fn native_python_app_contract_parity_ready",
                "pub fn cpp_entire_python_app_contract_parity_ready",
                "pub fn rust_entire_python_app_contract_parity_ready",
                "pub fn native_full_python_app_parity_ready",
                "pub fn cpp_entire_python_app_parity_ready",
                "pub fn rust_entire_python_app_parity_ready",
                "pub fn supported_frameworks()",
                '&["Tauri"]',
                "rust_native_runtime_capabilities",
            ),
        )
    )
    missing.extend(
        f"generated parity missing {needle}"
        for needle in _contains_all(
            generated,
            (
                "PYTHON_SOURCE_CONTRACT_HASH",
                "PYTHON_PARITY_DOMAINS",
                'rust_status: "Complete"',
                'required_before_full_parity: "C++: Complete | Rust: Complete"',
            ),
        )
    )
    missing.extend(
        f"Tauri shell missing {needle}"
        for needle in _contains_all(
            tauri_html,
            (
                f"Native Rust trading runtime ready: {runtime_ready_label}",
                "Python app contract/catalog parity ready: true",
                "C++ contract/catalog parity ready: true",
                "Rust contract/catalog parity ready: true",
            ),
        )
    )
    missing.extend(
        f"Rust CLI missing {needle}"
        for needle in _contains_all(
            rust_main,
            (
                "--native-live-smoke",
                "--native-live-market-smoke",
                "--write-local-recovery-evidence",
                "standalone native trading execution remains disabled",
            ),
        )
    )
    missing.extend(
        f"Rust README missing {needle}"
        for needle in _contains_all(
            readme,
            (
                "native_python_app_contract_parity_ready() == true",
                "native_full_python_app_parity_ready() == false",
                "--native-live-smoke-preflight",
                "--native-live-market-smoke",
                "--preflight",
                "rust-native-release-evidence.yml",
                "rust-native-promotion-audit.yml",
                "tools/check_rust_native_runtime_evidence.py --require-evidence",
                "--require-current-commit",
                "--require-clean-source",
                "tools/write_rust_native_release_evidence.py",
            ),
        )
    )

    if runtime_ready is None:
        missing.append(f"core missing parsable {RUNTIME_READY_FUNCTION}() source guard")

    return {
        "ok": not missing,
        "runtime_ready_source_state": runtime_ready,
        "issues": missing,
    }


def _python_runtime_readiness_contract() -> dict[str, Any]:
    summary = native_python_source_contract_summary()
    required_keys = ("cpp_standalone_runtime_ready", "rust_standalone_runtime_ready", "rust_full_parity")
    issues = [f"Python native parity summary missing {key}" for key in required_keys if key not in summary]
    return {
        "ok": not issues,
        "source": "Languages/Python/app/native_parity.py",
        "cpp_contract_parity": summary.get("cpp_contract_parity"),
        "rust_contract_parity": summary.get("rust_contract_parity"),
        "cpp_standalone_runtime_ready": summary.get("cpp_standalone_runtime_ready"),
        "rust_standalone_runtime_ready": summary.get("rust_standalone_runtime_ready"),
        "rust_full_parity": summary.get("rust_full_parity"),
        "issues": issues,
    }


def _source_sync_claim(
    *,
    source: dict[str, Any],
    native_source_sync: dict[str, Any],
    python_runtime_readiness: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    if not bool(source.get("ok")):
        issues.extend(str(issue) for issue in source.get("issues", []))
    if not bool(native_source_sync.get("ok")):
        issues.extend(f"native source sync: {issue}" for issue in native_source_sync.get("issues", []))
    if python_runtime_readiness.get("cpp_contract_parity") is not True:
        issues.append("Python native parity summary does not approve C++ contract parity.")
    if python_runtime_readiness.get("rust_contract_parity") is not True:
        issues.append("Python native parity summary does not approve Rust contract parity.")

    can_claim = not issues
    status = "approved" if can_claim else "denied"
    reason = (
        "C++ and Rust generated contract surfaces are synchronized with Python as source of truth."
        if can_claim
        else "C++/Rust source synchronization cannot be claimed until the Python contract markers, "
        "generated native artifacts, and Python contract-parity summary all pass."
    )
    return {
        "status": status,
        "can_claim": can_claim,
        "reason": reason,
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "cpp_contract_parity": python_runtime_readiness.get("cpp_contract_parity"),
        "rust_contract_parity": python_runtime_readiness.get("rust_contract_parity"),
        "source_contract_markers_ok": bool(source.get("ok")),
        "native_source_sync_ok": bool(native_source_sync.get("ok")),
        "native_source_sync_contract_hash": native_source_sync.get("contract_hash"),
        "generated_artifact_count": len(native_source_sync.get("generated", []) or []),
        "consumer_surface_count": len(native_source_sync.get("consumers", []) or []),
        "consumer_surface_names": [
            str(consumer.get("name"))
            for consumer in native_source_sync.get("consumers", []) or []
            if isinstance(consumer, dict) and str(consumer.get("name") or "").strip()
        ],
        "issues": issues,
        "audit_command": "python tools/audit_native_source_sync.py --json",
        "regenerate_command": "python Languages/Python/tools/generate_native_parity_contracts.py",
    }


def _promotion_requirement(
    *,
    requirement_id: str,
    title: str,
    ok: bool,
    summary: str,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "title": title,
        "required": True,
        "ok": ok,
        "status": "passed" if ok else "failed",
        "summary": summary,
        "issues": list(issues or []),
    }


def _actionable_current_commit_issues(current_commit_evidence: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for raw_issue in current_commit_evidence.get("issues", []):
        issue = str(raw_issue)
        if issue.startswith("missing evidence artifact:"):
            continue
        if issue not in issues:
            issues.append(issue)
    return issues


def _promotion_requirements(
    *,
    source: dict[str, Any],
    native_source_sync: dict[str, Any],
    declaration: dict[str, Any],
    evidence: dict[str, Any],
    evidence_complete: bool,
    promotion_evidence_ok: bool,
    current_commit_evidence: dict[str, Any],
    remaining_evidence_ids: list[str],
    runtime_ready: bool | None,
    python_runtime_readiness: dict[str, Any],
    python_source_match_issues: list[str],
    declaration_source_match_issues: list[str],
) -> list[dict[str, Any]]:
    source_ok = bool(source["ok"])
    native_source_sync_ok = bool(native_source_sync["ok"])
    python_runtime_readiness_ok = bool(python_runtime_readiness.get("ok")) and not python_source_match_issues
    declaration_ok = bool(declaration["ok"]) and not declaration_source_match_issues
    runtime_ready_ok = runtime_ready is True
    current_commit_evidence_ok = bool(evidence_complete and promotion_evidence_ok)

    if runtime_ready is True:
        runtime_summary = f"{RUNTIME_READY_FUNCTION}() returns true."
    elif runtime_ready is False:
        runtime_summary = (
            f"{RUNTIME_READY_FUNCTION}() still returns false; standalone Rust runtime "
            "promotion remains blocked."
        )
    else:
        runtime_summary = f"{RUNTIME_READY_FUNCTION}() is missing or not parsable."

    current_commit_issues = _actionable_current_commit_issues(current_commit_evidence)
    if not evidence_complete:
        current_commit_issues = [
            "required runtime evidence must pass before current-commit and clean-source promotion can pass"
        ] + current_commit_issues

    contract_hash = native_source_sync.get("contract_hash") or "unknown"
    return [
        _promotion_requirement(
            requirement_id="source_contract_markers",
            title="Rust source contract markers",
            ok=source_ok,
            summary=(
                "Rust source declares Python-owned C++/Rust contract parity boundaries."
                if source_ok
                else "Rust source is missing required Python parity boundary markers."
            ),
            issues=[str(issue) for issue in source.get("issues", [])],
        ),
        _promotion_requirement(
            requirement_id="native_source_sync",
            title="Generated native source sync",
            ok=native_source_sync_ok,
            summary=(
                f"Generated C++/Rust/Tauri contracts match Python source hash {contract_hash}."
                if native_source_sync_ok
                else "Generated native contracts are stale or incomplete compared with Python."
            ),
            issues=[str(issue) for issue in native_source_sync.get("issues", [])],
        ),
        _promotion_requirement(
            requirement_id="python_runtime_readiness_source",
            title="Python runtime-readiness source",
            ok=python_runtime_readiness_ok,
            summary=(
                "Python native parity source agrees with the Rust runtime-ready source guard."
                if python_runtime_readiness_ok
                else "Python native parity source does not agree with the Rust runtime-ready source guard."
            ),
            issues=[str(issue) for issue in python_runtime_readiness.get("issues", [])] + python_source_match_issues,
        ),
        _promotion_requirement(
            requirement_id="evidence_declaration",
            title="Runtime evidence manifest",
            ok=declaration_ok,
            summary=(
                "Rust runtime evidence manifest schema matches the Rust runtime-ready source guard."
                if declaration_ok
                else "Rust runtime evidence manifest declaration is invalid or inconsistent with source."
            ),
            issues=[str(issue) for issue in declaration.get("issues", [])] + declaration_source_match_issues,
        ),
        _promotion_requirement(
            requirement_id="required_runtime_evidence",
            title="Required runtime evidence artifacts",
            ok=evidence_complete,
            summary=(
                "All required live-smoke, recovery, and release-platform artifacts passed."
                if evidence_complete
                else f"{len(remaining_evidence_ids)} required runtime evidence artifact(s) remain missing or failing."
            ),
            issues=[str(issue) for issue in evidence.get("issues", [])],
        ),
        _promotion_requirement(
            requirement_id="current_commit_clean_source_evidence",
            title="Current commit clean-source evidence",
            ok=current_commit_evidence_ok,
            summary=(
                "Promotion evidence matches the current commit and was generated from a clean source tree."
                if current_commit_evidence_ok
                else "Promotion evidence must match the current commit and clean tracked source tree."
            ),
            issues=current_commit_issues,
        ),
        _promotion_requirement(
            requirement_id="runtime_ready_source_guard",
            title="Rust runtime ready source guard",
            ok=runtime_ready_ok,
            summary=runtime_summary,
            issues=[] if runtime_ready is not None else [f"missing {RUNTIME_READY_FUNCTION}() source guard"],
        ),
    ]


def _promotion_model(
    *,
    promotion_ready: bool,
    promotion_requirements: list[dict[str, Any]],
    native_source_sync: dict[str, Any],
    evidence_complete: bool,
    current_commit_evidence: dict[str, Any],
    runtime_ready: bool | None,
    python_source_match_issues: list[str],
    declaration_source_match_issues: list[str],
) -> dict[str, Any]:
    failed_requirement_ids = [str(row["id"]) for row in promotion_requirements if not bool(row["ok"])]
    if promotion_ready:
        phase = "runtime_complete"
    elif not bool(native_source_sync.get("ok")):
        phase = "regenerate_python_owned_native_contracts"
    elif python_source_match_issues:
        phase = "align_rust_runtime_guard_with_python_source_of_truth"
    elif declaration_source_match_issues:
        phase = "align_manifest_policy_with_runtime_ready_source_guard"
    elif not evidence_complete:
        phase = "collect_required_runtime_evidence"
    elif not bool(current_commit_evidence.get("ok")):
        phase = "regenerate_evidence_for_current_clean_source_commit"
    elif runtime_ready is not True:
        phase = "promote_runtime_ready_source_guard"
    else:
        phase = "resolve_failed_promotion_requirements"

    return {
        "phase": phase,
        "can_claim_runtime_complete": bool(promotion_ready),
        "failed_requirement_ids": failed_requirement_ids,
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "native_contract_sync_command": "python Languages/Python/tools/generate_native_parity_contracts.py",
        "promotion_audit_command": "python tools/audit_rust_native_runtime_readiness.py --require-ready --json",
        "github_promotion_audit_workflow": GITHUB_PROMOTION_AUDIT_WORKFLOW,
        "github_promotion_audit_workflow_command": GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND,
        "github_promotion_audit_workflow_inputs": _promotion_audit_workflow_inputs(),
        "github_promotion_audit_workflow_plan_artifact": GITHUB_PROMOTION_AUDIT_WORKFLOW_PLAN_ARTIFACT,
        "github_promotion_audit_source_sync_audit": _workflow_source_sync_audit(),
        "promotion_required_runtime_ids": _promotion_required_runtime_ids(),
        "evidence_import_command": PROMOTION_EVIDENCE_IMPORT_COMMAND,
        "evidence_commit_binding": "each runtime evidence artifact commit must match current git rev-parse HEAD",
        "clean_source_scope": {
            "requires_clean_tracked_source": True,
            "requires_no_untracked_promotion_scope_files": True,
            "ignored_paths": list(current_commit_evidence.get("current_source_tree_ignored_paths", [])),
            "dirty_paths": list(current_commit_evidence.get("current_source_tree_dirty_paths", [])),
            "untracked_paths": list(current_commit_evidence.get("current_source_tree_untracked_paths", [])),
        },
        "promotion_sequence": [
            "Regenerate and audit Python-owned C++/Rust/Tauri native contracts.",
            "Create a candidate source commit where rust_native_trading_runtime_ready(), "
            "Languages/Python/app/native_parity.py rust_standalone_runtime_ready, "
            "docs/rust-native-runtime-evidence.json policy, and Tauri runtime-ready text agree.",
            "Run live-smoke, recovery, and release evidence workflows from that candidate source commit.",
            "Import downloaded evidence artifacts with current-commit and clean-source validation; "
            "only canonical evidence directories are ignored for source cleanliness.",
            "Or run the rust-native-promotion-audit.yml workflow with live-smoke and "
            "release-evidence Actions run ids to download, import, regenerate local recovery, "
            "and run the strict promotion audit remotely.",
            "Run the readiness audit with --require-ready before claiming native Rust runtime completion.",
        ],
    }


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _completion_missing_inputs(
    *,
    remaining_evidence_ids: list[str],
    evidence_collection_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    rows_by_id = _evidence_collection_rows_by_id(evidence_collection_plan)
    missing_prerequisites: list[Any] = []
    required_environment: list[Any] = []
    required_inputs: list[Any] = []
    evidence_rows: list[dict[str, Any]] = []

    for evidence_id in remaining_evidence_ids:
        row = rows_by_id.get(evidence_id, {})
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        row_missing_prerequisites = _unique_strings(list(details.get("missing_prerequisites") or []))
        row_required_environment = _unique_strings(list(row.get("required_environment") or []))
        row_required_inputs = _unique_strings(list(row.get("required_inputs") or []))
        missing_prerequisites.extend(row_missing_prerequisites)
        required_environment.extend(row_required_environment)
        required_inputs.extend(row_required_inputs)

        summary: dict[str, Any] = {
            "evidence_id": evidence_id,
            "status": row.get("status", "unknown"),
            "ready_to_collect": bool(row.get("ready_to_collect")),
            "missing_prerequisites": row_missing_prerequisites,
            "required_environment": row_required_environment,
            "required_inputs": row_required_inputs,
        }
        workflow_source_sync = details.get("workflow_source_sync_audit")
        if isinstance(workflow_source_sync, dict) and workflow_source_sync:
            summary["workflow_source_sync_audit"] = dict(workflow_source_sync)
        if evidence_id in LIVE_SMOKE_EVIDENCE_IDS:
            workflow_inputs = details.get("github_workflow_inputs")
            if isinstance(workflow_inputs, dict) and workflow_inputs:
                summary["github_workflow_inputs"] = dict(workflow_inputs)
            expected_artifacts = details.get("expected_artifacts")
            if isinstance(expected_artifacts, list) and expected_artifacts:
                summary["expected_artifacts"] = [str(item) for item in expected_artifacts]
            required_secrets = details.get("github_workflow_requires_secrets")
            if isinstance(required_secrets, list) and required_secrets:
                summary["github_workflow_requires_secrets"] = [str(item) for item in required_secrets]
            workflow_artifact = str(details.get("github_workflow_artifact") or "").strip()
            if workflow_artifact:
                summary["github_workflow_artifact"] = workflow_artifact
            workflow_plan_artifact = str(details.get("github_workflow_plan_artifact") or "").strip()
            if workflow_plan_artifact:
                summary["github_workflow_plan_artifact"] = workflow_plan_artifact
        if evidence_id == RELEASE_EVIDENCE_ID:
            summary.update(
                {
                    "missing_platform_evidence_count": int(
                        details.get("missing_platform_evidence_count") or 0
                    ),
                    "release_evidence_target_count": int(
                        details.get("release_evidence_target_count") or 0
                    ),
                    "platform_target_count": int(details.get("platform_target_count") or 0),
                    "browser_target_count": int(details.get("browser_target_count") or 0),
                    "missing_platform_evidence_truncated": bool(
                        details.get("missing_platform_evidence_truncated")
                    ),
                }
            )
            local_browser_batch = (
                details.get("local_browser_batch_plan")
                if isinstance(details.get("local_browser_batch_plan"), dict)
                else {}
            )
            summary["local_browser_batch_target_count"] = int(local_browser_batch.get("target_count") or 0)
            workflow_dispatch_batch = (
                details.get("workflow_dispatch_batch_plan")
                if isinstance(details.get("workflow_dispatch_batch_plan"), dict)
                else {}
            )
            summary["workflow_dispatch_batch_target_count"] = int(
                workflow_dispatch_batch.get("target_count") or 0
            )
            summary["workflow_dispatch_batch_command_count"] = int(
                workflow_dispatch_batch.get("command_count") or 0
            )
            summary["workflow_dispatch_batch_command_target_ids"] = [
                str(target_id) for target_id in workflow_dispatch_batch.get("command_target_ids") or []
            ]
            summary["workflow_dispatch_batch_command_limit"] = int(
                workflow_dispatch_batch.get("command_limit") or 0
            )
            summary["workflow_dispatch_batch_commands_truncated"] = bool(
                workflow_dispatch_batch.get("commands_truncated")
            )
            summary["workflow_dispatch_batch_manual_input_target_count"] = int(
                workflow_dispatch_batch.get("manual_input_target_count") or 0
            )
            summary["workflow_dispatch_batch_manual_input_targets_truncated"] = bool(
                workflow_dispatch_batch.get("manual_input_targets_truncated")
            )
            summary["workflow_dispatch_batch_artifact_name_pattern"] = str(
                workflow_dispatch_batch.get("artifact_name_pattern") or ""
            )
        evidence_rows.append(summary)

    return {
        "missing_prerequisites": _unique_strings(missing_prerequisites),
        "required_environment": _unique_strings(required_environment),
        "required_inputs": _unique_strings(required_inputs),
        "evidence": evidence_rows,
    }


def _completion_claim(
    *,
    promotion_ready: bool,
    promotion_model: dict[str, Any],
    promotion_requirements: list[dict[str, Any]],
    remaining_evidence_ids: list[str],
    evidence_collection_plan: list[dict[str, Any]],
    current_commit: Any,
    native_source_sync_contract_hash: Any,
) -> dict[str, Any]:
    failed_rows = [row for row in promotion_requirements if not bool(row.get("ok"))]
    failed_requirement_ids = [str(row.get("id")) for row in failed_rows]
    denied_reasons = [
        str(row.get("summary") or row.get("title") or row.get("id") or "").strip()
        for row in failed_rows
        if str(row.get("summary") or row.get("title") or row.get("id") or "").strip()
    ]
    status = "approved" if promotion_ready else "denied"
    if promotion_ready:
        reason = "Native Rust runtime completion is verified for the current source commit."
    else:
        reason = "Native Rust runtime completion cannot be claimed until every promotion requirement passes."
    return {
        "status": status,
        "can_claim": bool(promotion_ready),
        "reason": reason,
        "phase": promotion_model.get("phase"),
        "failed_requirement_ids": failed_requirement_ids,
        "denied_reasons": denied_reasons,
        "remaining_evidence_ids": list(remaining_evidence_ids),
        "missing_inputs": _completion_missing_inputs(
            remaining_evidence_ids=remaining_evidence_ids,
            evidence_collection_plan=evidence_collection_plan,
        ),
        "current_commit": current_commit,
        "native_source_sync_contract_hash": native_source_sync_contract_hash,
        "promotion_audit_command": promotion_model.get("promotion_audit_command"),
        "github_promotion_audit_workflow": promotion_model.get("github_promotion_audit_workflow"),
        "github_promotion_audit_workflow_command": promotion_model.get("github_promotion_audit_workflow_command"),
        "github_promotion_audit_workflow_inputs": dict(
            promotion_model.get("github_promotion_audit_workflow_inputs") or {}
        ),
        "github_promotion_audit_workflow_plan_artifact": promotion_model.get(
            "github_promotion_audit_workflow_plan_artifact"
        ),
        "github_promotion_audit_source_sync_audit": dict(
            promotion_model.get("github_promotion_audit_source_sync_audit") or {}
        ),
        "promotion_required_runtime_ids": list(promotion_model.get("promotion_required_runtime_ids") or []),
    }


def _format_markdown_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text or "none"


def _format_command(command: Any) -> str:
    text = str(command or "").strip()
    return f"`{text}`" if text else "not available"


def _format_markdown_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "none"
    return ", ".join(f"`{str(value)}`" for value in values)


def _format_markdown_mapping(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return "none"
    return ", ".join(
        f"`{str(key)}={str(values[key])}`"
        for key in sorted(values)
    )


def _render_evidence_collection_markdown(result: dict[str, Any]) -> str:
    model = result.get("promotion_model") if isinstance(result.get("promotion_model"), dict) else {}
    source_sync_claim = result.get("source_sync_claim") if isinstance(result.get("source_sync_claim"), dict) else {}
    completion_claim = result.get("completion_claim") if isinstance(result.get("completion_claim"), dict) else {}
    missing_inputs = (
        completion_claim.get("missing_inputs")
        if isinstance(completion_claim.get("missing_inputs"), dict)
        else {}
    )
    clean_scope = model.get("clean_source_scope") if isinstance(model.get("clean_source_scope"), dict) else {}
    promotion_source_sync = (
        model.get("github_promotion_audit_source_sync_audit")
        if isinstance(model.get("github_promotion_audit_source_sync_audit"), dict)
        else {}
    )
    lines = [
        "# Rust Native Runtime Evidence Collection Plan",
        "",
        f"- Source sync claim: {_format_markdown_value(source_sync_claim.get('status'))}",
        f"- Source sync can be claimed: {_format_markdown_value(source_sync_claim.get('can_claim'))}",
        f"- Source sync claim reason: {_format_markdown_value(source_sync_claim.get('reason'))}",
        f"- Promotion ready: {_format_markdown_value(result.get('promotion_ready'))}",
        f"- Runtime completion claim: {_format_markdown_value(completion_claim.get('status'))}",
        f"- Runtime completion can be claimed: {_format_markdown_value(completion_claim.get('can_claim'))}",
        f"- Runtime completion claim reason: {_format_markdown_value(completion_claim.get('reason'))}",
        f"- Runtime missing prerequisites: {_format_markdown_list(missing_inputs.get('missing_prerequisites'))}",
        f"- Runtime required environment: {_format_markdown_list(missing_inputs.get('required_environment'))}",
        f"- Runtime required inputs: {_format_markdown_list(missing_inputs.get('required_inputs'))}",
        f"- Current commit: `{_format_markdown_value(result.get('current_commit'))}`",
        f"- Runtime ready source guard: {_format_markdown_value(result.get('runtime_ready_source_state'))}",
        f"- Python rust standalone runtime ready: {_format_markdown_value(result.get('python_rust_standalone_runtime_ready'))}",
        f"- Runtime ready policy state: {_format_markdown_value(result.get('runtime_ready_policy_state'))}",
        f"- Remaining evidence ids: {_format_markdown_list(result.get('remaining_evidence_ids'))}",
        f"- Evidence import command: {_format_command(model.get('evidence_import_command'))}",
        f"- GitHub promotion audit workflow: {_format_command(model.get('github_promotion_audit_workflow_command'))}",
        f"- GitHub promotion audit workflow inputs: {_format_markdown_mapping(model.get('github_promotion_audit_workflow_inputs'))}",
        f"- GitHub promotion audit plan artifact: `{_format_markdown_value(model.get('github_promotion_audit_workflow_plan_artifact'))}`",
        f"- GitHub promotion audit source-sync gate: {_format_command(promotion_source_sync.get('command'))}",
        f"- GitHub promotion audit source-sync JSON: `{_format_markdown_value(promotion_source_sync.get('output_path'))}`",
        f"- GitHub promotion audit source-sync artifact: `{_format_markdown_value(promotion_source_sync.get('github_workflow_artifact'))}`",
        f"- Promotion required runtime evidence ids: {_format_markdown_list(model.get('promotion_required_runtime_ids'))}",
        "",
        "## Promotion Requirements",
    ]

    for row in result.get("promotion_requirements", []):
        if not isinstance(row, dict):
            continue
        check = "x" if row.get("ok") else " "
        lines.append(
            f"- [{check}] {row.get('title', row.get('id', 'unknown'))}: {row.get('summary', '')}"
        )
        for issue in row.get("issues", []):
            lines.append(f"  - issue: {issue}")

    lines.extend(
        [
            "",
            "## Clean Source Scope",
            f"- Ignored evidence directories: {_format_markdown_list(clean_scope.get('ignored_paths'))}",
            f"- Dirty paths: {_format_markdown_list(clean_scope.get('dirty_paths'))}",
            f"- Untracked paths: {_format_markdown_list(clean_scope.get('untracked_paths'))}",
            "",
            "## Evidence Artifacts",
        ]
    )

    for row in result.get("evidence_collection_plan", []):
        if not isinstance(row, dict):
            continue
        lines.extend(
            [
                "",
                f"### {row.get('id', 'unknown')}",
                f"- Status: {_format_markdown_value(row.get('status'))}",
                f"- Collection kind: {_format_markdown_value(row.get('collection_kind'))}",
                f"- Ready to collect now: {_format_markdown_value(row.get('ready_to_collect'))}",
                f"- Expected artifact: `{_format_markdown_value(row.get('expected_artifact'))}`",
                f"- Canonical path: `{_format_markdown_value(row.get('canonical_path'))}`",
                f"- Local preflight command: {_format_command(row.get('local_preflight_command'))}",
                f"- Local collection command: {_format_command(row.get('local_command'))}",
                f"- GitHub workflow command: {_format_command(row.get('github_workflow'))}",
                f"- Validation command: {_format_command(row.get('validation_command'))}",
                f"- Required environment: {_format_markdown_list(row.get('required_environment'))}",
                f"- Required inputs: {_format_markdown_list(row.get('required_inputs'))}",
                f"- Required runtime evidence ids: {_format_markdown_list(row.get('required_runtime_ids'))}",
                f"- Import command: {_format_command(row.get('import_command'))}",
            ]
        )
        safety = row.get("safety") if isinstance(row.get("safety"), dict) else {}
        if safety:
            safety_text = ", ".join(
                f"{key}={_format_markdown_value(value)}"
                for key, value in sorted(safety.items())
            )
            lines.append(f"- Safety: {safety_text}")
        for issue in row.get("issues", []):
            lines.append(f"  - issue: {issue}")
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        if "source_tree_clean" in details:
            lines.append(f"- Source tree clean: {_format_markdown_value(details.get('source_tree_clean'))}")
        expected_artifacts = details.get("expected_artifacts")
        if isinstance(expected_artifacts, list) and expected_artifacts:
            lines.append(f"- Expected artifacts: {_format_markdown_list(expected_artifacts)}")
        workflow_inputs = details.get("github_workflow_inputs")
        if isinstance(workflow_inputs, dict) and workflow_inputs:
            lines.append(f"- GitHub workflow inputs: {_format_markdown_mapping(workflow_inputs)}")
        workflow_artifact = str(details.get("github_workflow_artifact") or "").strip()
        if workflow_artifact:
            lines.append(f"- GitHub workflow evidence artifact: `{workflow_artifact}`")
        workflow_plan_artifact = str(details.get("github_workflow_plan_artifact") or "").strip()
        if workflow_plan_artifact:
            lines.append(f"- GitHub workflow plan artifact: `{workflow_plan_artifact}`")
        workflow_source_sync = (
            details.get("workflow_source_sync_audit")
            if isinstance(details.get("workflow_source_sync_audit"), dict)
            else {}
        )
        if workflow_source_sync:
            lines.append(
                "- GitHub workflow source-sync gate: "
                f"{_format_command(workflow_source_sync.get('command'))}"
            )
            output_path = str(workflow_source_sync.get("output_path") or "").strip()
            if output_path:
                lines.append(f"- GitHub workflow source-sync JSON: `{output_path}`")
            source_sync_artifact = str(workflow_source_sync.get("github_workflow_artifact") or "").strip()
            if source_sync_artifact:
                lines.append(f"- GitHub workflow source-sync artifact: `{source_sync_artifact}`")
        workflow_secrets = details.get("github_workflow_requires_secrets")
        if isinstance(workflow_secrets, list) and workflow_secrets:
            lines.append(f"- GitHub workflow required secrets: {_format_markdown_list(workflow_secrets)}")
        if "release_evidence_target_count" in details:
            lines.append(
                "- Release evidence target count: "
                f"{_format_markdown_value(details.get('release_evidence_target_count'))} "
                f"(platform={_format_markdown_value(details.get('platform_target_count'))}, "
                f"browser={_format_markdown_value(details.get('browser_target_count'))})"
            )
        missing_prerequisites = details.get("missing_prerequisites")
        if isinstance(missing_prerequisites, list) and missing_prerequisites:
            lines.append(f"- Missing prerequisites: {_format_markdown_list(missing_prerequisites)}")
        missing_plan = details.get("missing_platform_evidence_plan")
        if isinstance(missing_plan, list) and missing_plan:
            lines.append("- Missing platform evidence plan:")
            for target in missing_plan:
                if not isinstance(target, dict):
                    continue
                lines.append(f"  - target: `{_format_markdown_value(target.get('target_id'))}`")
                lines.append(
                    f"    - validation: {_format_command(target.get('target_validation_command'))}"
                )
                lines.append(
                    f"    - workflow: {_format_command(target.get('workflow_dispatch_example'))}"
                )
            if details.get("missing_platform_evidence_truncated"):
                lines.append("  - note: missing target plan is truncated; rerun preflight with `--missing-limit 0` for all targets")
        workflow_dispatch_batch = details.get("workflow_dispatch_batch_plan")
        if isinstance(workflow_dispatch_batch, dict) and workflow_dispatch_batch.get("target_ids"):
            lines.append("- Missing target workflow dispatch batch:")
            lines.append(f"  - workflow: `{_format_markdown_value(workflow_dispatch_batch.get('workflow'))}`")
            lines.append(
                "  - targets with dispatch commands: "
                f"{_format_markdown_list(workflow_dispatch_batch.get('command_target_ids'))}"
            )
            lines.append(
                "  - commands shown: "
                f"{_format_markdown_value(workflow_dispatch_batch.get('command_count'))} of "
                f"{_format_markdown_value(workflow_dispatch_batch.get('target_count'))}"
            )
            workflow_dispatch_inputs = workflow_dispatch_batch.get("workflow_dispatch_inputs")
            if isinstance(workflow_dispatch_inputs, list) and workflow_dispatch_inputs:
                lines.append("  - structured dispatch inputs:")
                for inputs in workflow_dispatch_inputs:
                    if not isinstance(inputs, dict):
                        continue
                    target_id = _format_markdown_value(inputs.get("target_id"))
                    input_names = [
                        str(key)
                        for key in sorted(inputs)
                        if key not in {"target_id", "runner_labels_json"}
                    ]
                    input_summary = _format_markdown_list(input_names)
                    lines.append(f"    - `{target_id}`: inputs={input_summary}")
            for command in workflow_dispatch_batch.get("commands", []):
                lines.append(f"  - dispatch: {_format_command(command)}")
            manual_input_targets = workflow_dispatch_batch.get("manual_input_targets")
            if isinstance(manual_input_targets, list) and manual_input_targets:
                lines.append("  - targets requiring manual workflow inputs:")
                for target in manual_input_targets:
                    if not isinstance(target, dict):
                        continue
                    lines.append(
                        f"    - `{_format_markdown_value(target.get('target_id'))}`: "
                        f"{_format_markdown_list(target.get('required_workflow_inputs'))}"
                    )
            if workflow_dispatch_batch.get("commands_truncated"):
                lines.append("  - note: dispatch commands are truncated; rerun preflight with `--missing-limit 0` for all targets")
            lines.append(
                f"  - validate all: {_format_command(workflow_dispatch_batch.get('validation_command'))}"
            )
            lines.append(
                "  - aggregate release evidence: "
                f"{_format_command(workflow_dispatch_batch.get('aggregate_write_command'))}"
            )
        local_browser_batch = details.get("local_browser_batch_plan")
        if isinstance(local_browser_batch, dict) and local_browser_batch.get("target_ids"):
            lines.append("- Local browser batch:")
            lines.append(f"  - host: `{_format_markdown_value(local_browser_batch.get('host'))}`")
            lines.append(f"  - targets: {_format_markdown_list(local_browser_batch.get('target_ids'))}")
            lines.append(f"  - list: {_format_command(local_browser_batch.get('list_command'))}")
            lines.append(f"  - run: {_format_command(local_browser_batch.get('batch_command'))}")
            for command in local_browser_batch.get("validation_commands", []):
                lines.append(f"  - validation: {_format_command(command)}")
            if local_browser_batch.get("partial_evidence_only"):
                lines.append("  - note: local browser batch is partial evidence; remaining matrix targets still require their declared runners")

    lines.append("")
    lines.append("## Next Actions")
    action_plan = result.get("promotion_next_action_plan")
    if isinstance(action_plan, list) and action_plan:
        for index, row in enumerate(action_plan, start=1):
            if not isinstance(row, dict):
                continue
            lines.append(f"{index}. {row.get('summary')}")
            lines.append(f"   - Ready to run now: {_format_markdown_value(row.get('ready_to_run'))}")
            dependencies = row.get("depends_on_action_ids")
            if isinstance(dependencies, list) and dependencies:
                lines.append(f"   - Depends on: {', '.join(f'`{item}`' for item in dependencies)}")
            blockers = row.get("blocked_by")
            if isinstance(blockers, list) and blockers:
                lines.append("   - Blocked by:")
                for blocker in blockers:
                    lines.append(f"     - {blocker}")
    else:
        lines.append("No remaining evidence actions.")

    lines.append("")
    return "\n".join(lines)


def audit(
    *,
    manifest_path: Path,
    evidence_dir_override: Path | None,
    require_ready: bool,
    release_missing_limit: int = 10,
) -> dict[str, Any]:
    root = _repo_root()
    source = _source_contract_audit(root)
    native_source_sync = audit_native_source_sync()
    python_runtime_readiness = _python_runtime_readiness_contract()
    declaration = validate(manifest_path, require_evidence=False)
    evidence = validate(
        manifest_path,
        require_evidence=True,
        evidence_dir_override=evidence_dir_override,
    )
    current_commit_evidence = validate(
        manifest_path,
        require_evidence=True,
        require_current_commit=True,
        require_clean_source=True,
        evidence_dir_override=evidence_dir_override,
    )

    issues: list[str] = []
    blockers: list[str] = []
    if not source["ok"]:
        issues.extend(str(issue) for issue in source["issues"])
    if not native_source_sync["ok"]:
        issues.extend(f"native source sync: {issue}" for issue in native_source_sync["issues"])
    if not declaration["ok"]:
        issues.extend(str(issue) for issue in declaration["issues"])
    if not evidence["ok"]:
        blockers.extend(str(issue) for issue in evidence["issues"])

    artifact_status_by_id = _artifact_status_by_id(evidence)
    remaining_evidence_ids = sorted(
        evidence_id
        for evidence_id, status in artifact_status_by_id.items()
        if not bool(status.get("ok"))
    )
    runtime_ready = source.get("runtime_ready_source_state")
    python_rust_runtime_ready = python_runtime_readiness.get("rust_standalone_runtime_ready")
    python_source_match_issues: list[str] = []
    if runtime_ready is not None and python_rust_runtime_ready is not None and runtime_ready != python_rust_runtime_ready:
        python_source_match_issues.append(
            "Languages/Python/app/native_parity.py rust_standalone_runtime_ready does not match "
            "rust_native_trading_runtime_ready() source state"
        )
    runtime_ready_policy_state = declaration.get("runtime_ready_policy_state")
    declaration_source_match_issues: list[str] = []
    if runtime_ready is not None and runtime_ready_policy_state is not None and runtime_ready != runtime_ready_policy_state:
        declaration_source_match_issues.append(
            "policy.runtime_ready_flag does not match rust_native_trading_runtime_ready() source state"
        )
    evidence_complete = bool(evidence["ok"])
    if runtime_ready is True and not evidence_complete:
        issues.append(f"{RUNTIME_READY_FUNCTION}() is true before required evidence is complete")
    if runtime_ready is False and evidence_complete:
        blockers.append(f"{RUNTIME_READY_FUNCTION}() still returns false after required evidence is complete")
    issues.extend(python_source_match_issues)
    issues.extend(declaration_source_match_issues)

    promotion_evidence_ok = bool(current_commit_evidence["ok"])
    promotion_evidence_issues = _actionable_current_commit_issues(current_commit_evidence)
    if evidence_complete and not promotion_evidence_ok:
        blockers.extend(promotion_evidence_issues)

    promotion_requirements = _promotion_requirements(
        source=source,
        native_source_sync=native_source_sync,
        declaration=declaration,
        evidence=evidence,
        evidence_complete=evidence_complete,
        promotion_evidence_ok=promotion_evidence_ok,
        current_commit_evidence=current_commit_evidence,
        remaining_evidence_ids=remaining_evidence_ids,
        runtime_ready=runtime_ready,
        python_runtime_readiness=python_runtime_readiness,
        python_source_match_issues=python_source_match_issues,
        declaration_source_match_issues=declaration_source_match_issues,
    )
    promotion_ready = all(bool(row["ok"]) for row in promotion_requirements)
    promotion_model = _promotion_model(
        promotion_ready=promotion_ready,
        promotion_requirements=promotion_requirements,
        native_source_sync=native_source_sync,
        evidence_complete=evidence_complete,
        current_commit_evidence=current_commit_evidence,
        runtime_ready=runtime_ready,
        python_source_match_issues=python_source_match_issues,
        declaration_source_match_issues=declaration_source_match_issues,
    )
    ok = not issues and (promotion_ready if require_ready else True)
    if require_ready and blockers:
        ok = False
    evidence_dir_for_collection = Path(evidence_dir_override or (root / "artifacts" / "rust-native-runtime-evidence"))
    live_smoke_prerequisites = _live_smoke_prerequisites(
        evidence_dir_for_collection,
        source_tree_clean=bool(current_commit_evidence.get("current_source_tree_clean")),
    )
    local_recovery_prerequisites = local_recovery_generation_guard(evidence_dir_for_collection)
    release_evidence_prerequisites = _release_evidence_prerequisites(root, missing_limit=release_missing_limit)
    evidence_collection_plan = _evidence_collection_plan(
        artifact_status_by_id=artifact_status_by_id,
        live_smoke_prerequisites=live_smoke_prerequisites,
        local_recovery_prerequisites=local_recovery_prerequisites,
        release_evidence_prerequisites=release_evidence_prerequisites,
    )
    source_sync_claim = _source_sync_claim(
        source=source,
        native_source_sync=native_source_sync,
        python_runtime_readiness=python_runtime_readiness,
    )
    completion_claim = _completion_claim(
        promotion_ready=promotion_ready,
        promotion_model=promotion_model,
        promotion_requirements=promotion_requirements,
        remaining_evidence_ids=remaining_evidence_ids,
        evidence_collection_plan=evidence_collection_plan,
        current_commit=current_commit_evidence.get("current_commit"),
        native_source_sync_contract_hash=native_source_sync.get("contract_hash"),
    )

    return {
        "ok": ok,
        "promotion_ready": promotion_ready,
        "source_sync_claim": source_sync_claim,
        "completion_claim": completion_claim,
        "require_ready": require_ready,
        "runtime_ready_source_state": runtime_ready,
        "python_runtime_readiness_source": python_runtime_readiness,
        "python_cpp_standalone_runtime_ready": python_runtime_readiness.get("cpp_standalone_runtime_ready"),
        "python_rust_standalone_runtime_ready": python_rust_runtime_ready,
        "runtime_ready_python_source_matches_rust_guard": not python_source_match_issues,
        "runtime_ready_python_source_issues": python_source_match_issues,
        "runtime_ready_policy_state": runtime_ready_policy_state,
        "runtime_ready_policy_matches_source": not declaration_source_match_issues,
        "source_contract_ok": bool(source["ok"]),
        "native_source_sync_ok": bool(native_source_sync["ok"]),
        "native_source_sync_contract_hash": native_source_sync.get("contract_hash"),
        "native_source_sync_issues": list(native_source_sync.get("issues", [])),
        "evidence_declaration_ok": bool(declaration["ok"]),
        "evidence_complete": evidence_complete,
        "current_commit": current_commit_evidence.get("current_commit"),
        "current_source_tree_clean": current_commit_evidence.get("current_source_tree_clean"),
        "current_source_tree_dirty_paths": current_commit_evidence.get("current_source_tree_dirty_paths", []),
        "current_source_tree_untracked_paths": current_commit_evidence.get(
            "current_source_tree_untracked_paths",
            [],
        ),
        "current_source_tree_ignored_paths": current_commit_evidence.get("current_source_tree_ignored_paths", []),
        "promotion_evidence_ok": promotion_evidence_ok,
        "promotion_evidence_issues": promotion_evidence_issues,
        "promotion_model": promotion_model,
        "promotion_requirements": promotion_requirements,
        "promotion_requirement_count": len(promotion_requirements),
        "promotion_requirements_passed": sum(1 for row in promotion_requirements if bool(row["ok"])),
        "evidence_dir": evidence.get("evidence_dir"),
        "artifact_status": list(artifact_status_by_id.values()),
        "remaining_evidence_ids": remaining_evidence_ids,
        "evidence_collection_plan": evidence_collection_plan,
        "live_smoke_prerequisites": live_smoke_prerequisites,
        "local_recovery_prerequisites": local_recovery_prerequisites,
        "release_evidence_prerequisites": release_evidence_prerequisites,
        "promotion_next_action_plan": _next_action_plan(
            remaining_evidence_ids,
            promotion_model,
            evidence_collection_plan,
        ),
        "next_actions": _next_actions(
            remaining_evidence_ids,
            promotion_model,
            evidence_collection_plan,
        ),
        "issues": issues,
        "blockers": blockers,
        "missing_evidence_count": len(blockers),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Rust runtime evidence manifest path.")
    parser.add_argument("--evidence-dir", help="Override artifact directory for evidence validation.")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless Rust native runtime is promotion-ready.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--write-evidence-plan",
        help="Write a Markdown operator plan for collecting and importing Rust native runtime evidence.",
    )
    parser.add_argument(
        "--release-missing-limit",
        type=int,
        default=10,
        help=(
            "Maximum missing release-platform targets to include with commands in the readiness plan. "
            "Use 0 for every missing target."
        ),
    )
    args = parser.parse_args(argv)

    result = audit(
        manifest_path=Path(args.manifest),
        evidence_dir_override=Path(args.evidence_dir) if args.evidence_dir else None,
        require_ready=bool(args.require_ready),
        release_missing_limit=int(args.release_missing_limit),
    )
    if args.write_evidence_plan:
        plan_path = Path(args.write_evidence_plan)
        plan_guard = generated_evidence_write_guard(
            [plan_path],
            root=_repo_root(),
            require_generated_destinations=True,
        )
        if not plan_guard["ok"]:
            result["ok"] = False
            result["issues"].extend(str(issue) for issue in plan_guard["issues"])
            result["evidence_plan_write_guard"] = plan_guard
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print("Rust native runtime promotion audit: evidence plan write blocked")
                for issue in plan_guard["issues"]:
                    print(f"- issue: {issue}")
            return 1
        result["evidence_plan_write_guard"] = plan_guard
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(_render_evidence_collection_markdown(result), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        state = "ready" if result["promotion_ready"] else "not ready"
        print(f"Rust native runtime promotion audit: {state}")
        for issue in result["issues"]:
            print(f"- issue: {issue}")
        for blocker in result["blockers"]:
            print(f"- blocker: {blocker}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
