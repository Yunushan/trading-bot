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
    from check_rust_native_runtime_evidence import DEFAULT_MANIFEST_PATH, validate
    from write_rust_native_release_evidence import preflight_release_evidence_inputs
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
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


def _live_smoke_prerequisites() -> dict[str, Any]:
    api_key_present = _env_present("BINANCE_API_KEY")
    api_secret_present = _env_present("BINANCE_API_SECRET")
    confirmed = str(os.environ.get("TRADING_BOT_RUST_LIVE_SMOKE") or "").strip() == "1"
    market_confirmed = str(os.environ.get("TRADING_BOT_RUST_MARKET_SMOKE") or "").strip() == "1"
    return {
        "binance_api_key_present": api_key_present,
        "binance_api_secret_present": api_secret_present,
        "live_smoke_confirmation_present": confirmed,
        "market_smoke_confirmation_present": market_confirmed,
        "binance_testnet": str(os.environ.get("BINANCE_TESTNET") or "true").strip() or "true",
        "can_run_live_smoke": api_key_present and api_secret_present and confirmed,
        "can_run_market_smoke": market_confirmed,
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
            "BINANCE_API_KEY and BINANCE_API_SECRET repository secrets."
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
            "that contains release-platform-evidence-* artifacts."
        )
    return actions


def _source_contract_audit(root: Path) -> dict[str, Any]:
    rust_root = root / "experiments" / "rust-shells"
    core = _read(rust_root / "crates" / "core" / "src" / "lib.rs")
    generated = _read(rust_root / "crates" / "core" / "src" / "generated_python_parity.rs")
    tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")
    rust_main = _read(rust_root / "src" / "main.rs")
    readme = _read(rust_root / "README.md")

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
                "Native Rust trading runtime ready: false",
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
                "tools/check_rust_native_runtime_evidence.py --require-evidence",
                "--require-current-commit",
                "--require-clean-source",
                "tools/write_rust_native_release_evidence.py",
            ),
        )
    )

    runtime_ready = _runtime_ready_source_state(core)
    if runtime_ready is None:
        missing.append(f"core missing parsable {RUNTIME_READY_FUNCTION}() source guard")

    return {
        "ok": not missing,
        "runtime_ready_source_state": runtime_ready,
        "issues": missing,
    }


def audit(
    *,
    manifest_path: Path,
    evidence_dir_override: Path | None,
    require_ready: bool,
) -> dict[str, Any]:
    root = _repo_root()
    source = _source_contract_audit(root)
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
    evidence_complete = bool(evidence["ok"])
    if runtime_ready is True and not evidence_complete:
        issues.append(f"{RUNTIME_READY_FUNCTION}() is true before required evidence is complete")
    if runtime_ready is False and evidence_complete:
        blockers.append(f"{RUNTIME_READY_FUNCTION}() still returns false after required evidence is complete")

    promotion_evidence_ok = bool(current_commit_evidence["ok"])
    promotion_evidence_issues: list[str] = []
    if evidence_complete and not promotion_evidence_ok:
        promotion_evidence_issues = [str(issue) for issue in current_commit_evidence["issues"]]
        blockers.extend(promotion_evidence_issues)

    promotion_ready = bool(
        source["ok"]
        and declaration["ok"]
        and evidence_complete
        and promotion_evidence_ok
        and runtime_ready is True
    )
    ok = not issues and (promotion_ready if require_ready else True)
    if require_ready and blockers:
        ok = False

    return {
        "ok": ok,
        "promotion_ready": promotion_ready,
        "require_ready": require_ready,
        "runtime_ready_source_state": runtime_ready,
        "source_contract_ok": bool(source["ok"]),
        "evidence_declaration_ok": bool(declaration["ok"]),
        "evidence_complete": evidence_complete,
        "current_commit": current_commit_evidence.get("current_commit"),
        "current_source_tree_clean": current_commit_evidence.get("current_source_tree_clean"),
        "promotion_evidence_ok": promotion_evidence_ok,
        "promotion_evidence_issues": promotion_evidence_issues,
        "evidence_dir": evidence.get("evidence_dir"),
        "artifact_status": list(artifact_status_by_id.values()),
        "remaining_evidence_ids": remaining_evidence_ids,
        "live_smoke_prerequisites": _live_smoke_prerequisites(),
        "release_evidence_prerequisites": _release_evidence_prerequisites(root),
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
    args = parser.parse_args(argv)

    result = audit(
        manifest_path=Path(args.manifest),
        evidence_dir_override=Path(args.evidence_dir) if args.evidence_dir else None,
        require_ready=bool(args.require_ready),
    )
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
