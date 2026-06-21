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
LOCAL_RECOVERY_EVIDENCE_IDS = {
    "rust-native-live-stream-recovery",
    "rust-native-order-guard-recovery",
}
RELEASE_EVIDENCE_ID = "rust-native-release-platform-evidence"
EVIDENCE_IMPORT_COMMAND = (
    "python tools/import_rust_native_evidence_artifacts.py <artifact.zip-or-dir> "
    "--apply --require-current-commit --require-clean-source"
)


def _runtime_evidence_import_command(required_runtime_ids: list[str] | tuple[str, ...]) -> str:
    suffix = " ".join(f"--require-runtime-id {evidence_id}" for evidence_id in required_runtime_ids)
    return f"{EVIDENCE_IMPORT_COMMAND} {suffix}".strip()


PROMOTION_EVIDENCE_IMPORT_COMMAND = _runtime_evidence_import_command(
    (
        "rust-native-live-market-data-smoke",
        "rust-native-live-account-read-smoke",
        "rust-native-release-platform-evidence",
    )
)
GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND = (
    "gh workflow run rust-native-promotion-audit.yml "
    "-f live_smoke_run_id=<live-smoke-actions-run-id> "
    "-f release_evidence_run_id=<release-evidence-actions-run-id>"
)
EVIDENCE_COLLECTION_ORDER = (
    LIVE_MARKET_EVIDENCE_ID,
    LIVE_ACCOUNT_EVIDENCE_ID,
    "rust-native-live-stream-recovery",
    "rust-native-order-guard-recovery",
    RELEASE_EVIDENCE_ID,
)


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


def _live_smoke_prerequisites(evidence_dir: Path) -> dict[str, Any]:
    api_key_present = _env_present("BINANCE_API_KEY")
    api_secret_present = _env_present("BINANCE_API_SECRET")
    confirmed = str(os.environ.get("TRADING_BOT_RUST_LIVE_SMOKE") or "").strip() == "1"
    market_confirmed = str(os.environ.get("TRADING_BOT_RUST_MARKET_SMOKE") or "").strip() == "1"
    market_source_control_write_guard = generated_evidence_write_guard(
        [evidence_dir / "rust-native-live-market-data-smoke.json"],
        root=_repo_root(),
    )
    account_source_control_write_guard = generated_evidence_write_guard(
        [
            evidence_dir / "rust-native-live-market-data-smoke.json",
            evidence_dir / "rust-native-live-account-read-smoke.json",
        ],
        root=_repo_root(),
    )
    market_write_guard_ok = bool(market_source_control_write_guard.get("ok"))
    account_write_guard_ok = bool(account_source_control_write_guard.get("ok"))
    return {
        "binance_api_key_present": api_key_present,
        "binance_api_secret_present": api_secret_present,
        "live_smoke_confirmation_present": confirmed,
        "market_smoke_confirmation_present": market_confirmed,
        "binance_testnet": str(os.environ.get("BINANCE_TESTNET") or "true").strip() or "true",
        "can_run_live_smoke": api_key_present and api_secret_present and confirmed and account_write_guard_ok,
        "can_run_market_smoke": market_confirmed and market_write_guard_ok,
        "market_source_control_write_guard": market_source_control_write_guard,
        "account_source_control_write_guard": account_source_control_write_guard,
        "market_command": (
            "TRADING_BOT_RUST_MARKET_SMOKE=1 BINANCE_TESTNET=true "
            "cargo run -p trading-bot-rust -- --native-live-market-smoke"
        ),
        "market_preflight_command": "cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight",
        "command": (
            "TRADING_BOT_RUST_LIVE_SMOKE=1 BINANCE_API_KEY=... BINANCE_API_SECRET=... "
            "BINANCE_TESTNET=true cargo run -p trading-bot-rust -- --native-live-smoke"
        ),
        "preflight_command": "cargo run -p trading-bot-rust -- --native-live-smoke-preflight",
        "github_workflow": "gh workflow run rust-native-live-smoke.yml -f binance_testnet=true -f symbol=BTCUSDT -f interval=1m",
    }


def _release_evidence_prerequisites(root: Path) -> dict[str, Any]:
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
    }
    try:
        preflight = preflight_release_evidence_inputs(
            tag=release_tag,
            owner="Yunushan",
            repo="trading-bot",
            matrix_path=root / "docs" / "release-platform-test-matrix.json",
            platform_evidence_dir=platform_evidence_dir,
            output_dir=root / "artifacts" / "rust-native-runtime-evidence",
            missing_limit=10,
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
            "release_asset_presence_verified": bool(preflight.get("release_asset_presence_verified")),
            "release_asset_presence_requires_network": bool(preflight.get("release_asset_presence_requires_network")),
            "platform_target_count": int(preflight.get("platform_target_count") or 0),
            "browser_target_count": int(preflight.get("browser_target_count") or 0),
            "present_platform_evidence_count": int(preflight.get("present_platform_evidence_count") or 0),
            "passed_platform_evidence_count": int(preflight.get("passed_platform_evidence_count") or 0),
            "invalid_platform_evidence_count": int(preflight.get("invalid_platform_evidence_count") or 0),
            "unknown_platform_evidence_count": int(preflight.get("unknown_platform_evidence_count") or 0),
            "missing_platform_evidence_count": int(preflight.get("missing_platform_evidence_count") or 0),
            "missing_platform_evidence_limit": int(preflight.get("missing_platform_evidence_limit") or 0),
            "missing_platform_evidence_truncated": bool(preflight.get("missing_platform_evidence_truncated")),
            "missing_platform_evidence": list(preflight.get("missing_platform_evidence") or []),
            "missing_platform_evidence_plan": list(preflight.get("missing_platform_evidence_plan") or []),
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
                    required_environment=["TRADING_BOT_RUST_MARKET_SMOKE=1", "BINANCE_TESTNET=true"],
                    required_runtime_ids=[LIVE_MARKET_EVIDENCE_ID],
                    safety={
                        "read_only": True,
                        "requires_credentials": False,
                        "order_submission_attempted": False,
                    },
                    details={
                        "source_control_write_guard": market_guard,
                    },
                )
            )
            rows[-1]["issues"].extend(str(issue) for issue in market_guard.get("issues", []))
        elif evidence_id == LIVE_ACCOUNT_EVIDENCE_ID:
            account_guard = dict(live_smoke_prerequisites.get("account_source_control_write_guard") or {})
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
                        "BINANCE_TESTNET=true",
                    ],
                    required_runtime_ids=[LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID],
                    safety={
                        "read_only": True,
                        "requires_credentials": True,
                        "order_submission_attempted": False,
                    },
                    details={
                        "binance_api_key_present": bool(live_smoke_prerequisites.get("binance_api_key_present")),
                        "binance_api_secret_present": bool(live_smoke_prerequisites.get("binance_api_secret_present")),
                        "live_smoke_confirmation_present": bool(
                            live_smoke_prerequisites.get("live_smoke_confirmation_present")
                        ),
                        "source_control_write_guard": account_guard,
                    },
                )
            )
            rows[-1]["issues"].extend(str(issue) for issue in account_guard.get("issues", []))
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
                        "source_control_guard_ok": local_recovery_guard_ok,
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
                        "missing_platform_evidence_count": int(
                            release_evidence_prerequisites.get("missing_platform_evidence_count") or 0
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


def _next_actions(remaining_ids: list[str]) -> list[str]:
    actions: list[str] = []
    if LIVE_MARKET_EVIDENCE_ID in remaining_ids:
        actions.append(
            "Run cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight, then run "
            "TRADING_BOT_RUST_MARKET_SMOKE=1 BINANCE_TESTNET=true cargo run -p trading-bot-rust "
            "-- --native-live-market-smoke; it writes rust-native-live-market-data-smoke.json "
            "without credentials or order submission."
        )
    if LIVE_ACCOUNT_EVIDENCE_ID in remaining_ids:
        actions.append(
            "Run cargo run -p trading-bot-rust -- --native-live-smoke-preflight, then run "
            "the guarded Rust live smoke with Binance credentials on testnet or production; "
            "it writes rust-native-live-account-read-smoke.json without submitting orders. "
            "On GitHub, use the manual rust-native-live-smoke.yml workflow with "
            "BINANCE_API_KEY and BINANCE_API_SECRET repository secrets. After downloading "
            "the workflow artifact ZIP or folder, run "
            f"{_runtime_evidence_import_command([LIVE_MARKET_EVIDENCE_ID, LIVE_ACCOUNT_EVIDENCE_ID])} "
            "to validate and import it."
        )
    if any(evidence_id in LOCAL_RECOVERY_EVIDENCE_IDS for evidence_id in remaining_ids):
        actions.append(
            "Run python tools/check_rust_native_local_recovery_evidence.py "
            "--evidence-dir artifacts/rust-native-runtime-evidence --json."
        )
    if RELEASE_EVIDENCE_ID in remaining_ids:
        actions.append(
            "Run python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence --preflight --json; after Rust "
            "release assets and release-platform evidence exist, run "
            "python tools/write_rust_native_release_evidence.py --tag <tag> "
            "--platform-evidence-dir release-platform-evidence. On GitHub, use the manual "
            "rust-native-release-evidence.yml workflow with a release tag and the run id "
            f"that contains release-platform-evidence-* artifacts. After downloading "
            "the workflow artifact ZIP or folder, run "
            f"{_runtime_evidence_import_command([RELEASE_EVIDENCE_ID])} to validate and import it."
        )
    if remaining_ids:
        actions.append(
            "After the live-smoke and release-evidence workflow artifacts exist for the same candidate "
            f"source commit, run {GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND}; it downloads, imports, "
            "regenerates deterministic local recovery evidence, validates the full evidence set, and "
            "runs python tools/audit_rust_native_runtime_readiness.py --require-ready --json."
        )
    return actions


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
        "cpp_standalone_runtime_ready": summary.get("cpp_standalone_runtime_ready"),
        "rust_standalone_runtime_ready": summary.get("rust_standalone_runtime_ready"),
        "rust_full_parity": summary.get("rust_full_parity"),
        "issues": issues,
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
        "github_promotion_audit_workflow_command": GITHUB_PROMOTION_AUDIT_WORKFLOW_COMMAND,
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


def _render_evidence_collection_markdown(result: dict[str, Any]) -> str:
    model = result.get("promotion_model") if isinstance(result.get("promotion_model"), dict) else {}
    clean_scope = model.get("clean_source_scope") if isinstance(model.get("clean_source_scope"), dict) else {}
    lines = [
        "# Rust Native Runtime Evidence Collection Plan",
        "",
        f"- Promotion ready: {_format_markdown_value(result.get('promotion_ready'))}",
        f"- Current commit: `{_format_markdown_value(result.get('current_commit'))}`",
        f"- Runtime ready source guard: {_format_markdown_value(result.get('runtime_ready_source_state'))}",
        f"- Python rust standalone runtime ready: {_format_markdown_value(result.get('python_rust_standalone_runtime_ready'))}",
        f"- Runtime ready policy state: {_format_markdown_value(result.get('runtime_ready_policy_state'))}",
        f"- Remaining evidence ids: {_format_markdown_list(result.get('remaining_evidence_ids'))}",
        f"- Evidence import command: {_format_command(model.get('evidence_import_command'))}",
        f"- GitHub promotion audit workflow: {_format_command(model.get('github_promotion_audit_workflow_command'))}",
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

    lines.append("")
    lines.append("## Next Actions")
    next_actions = result.get("next_actions")
    if isinstance(next_actions, list) and next_actions:
        for index, action in enumerate(next_actions, start=1):
            lines.append(f"{index}. {action}")
    else:
        lines.append("No remaining evidence actions.")

    lines.append("")
    return "\n".join(lines)


def audit(
    *,
    manifest_path: Path,
    evidence_dir_override: Path | None,
    require_ready: bool,
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
    live_smoke_prerequisites = _live_smoke_prerequisites(evidence_dir_for_collection)
    local_recovery_prerequisites = local_recovery_generation_guard(evidence_dir_for_collection)
    release_evidence_prerequisites = _release_evidence_prerequisites(root)
    evidence_collection_plan = _evidence_collection_plan(
        artifact_status_by_id=artifact_status_by_id,
        live_smoke_prerequisites=live_smoke_prerequisites,
        local_recovery_prerequisites=local_recovery_prerequisites,
        release_evidence_prerequisites=release_evidence_prerequisites,
    )

    return {
        "ok": ok,
        "promotion_ready": promotion_ready,
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
        "next_actions": _next_actions(remaining_evidence_ids),
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
    args = parser.parse_args(argv)

    result = audit(
        manifest_path=Path(args.manifest),
        evidence_dir_override=Path(args.evidence_dir) if args.evidence_dir else None,
        require_ready=bool(args.require_ready),
    )
    if args.write_evidence_plan:
        plan_path = Path(args.write_evidence_plan)
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
