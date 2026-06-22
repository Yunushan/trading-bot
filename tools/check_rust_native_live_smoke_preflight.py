#!/usr/bin/env python3
"""Verify Rust native live-smoke preflight stays read-only and redacted."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from app.native_parity import native_python_source_contract_hash
except ModuleNotFoundError:  # pragma: no cover - exercised when run from repo root
    import sys

    PYTHON_ROOT = Path(__file__).resolve().parents[1] / "Languages" / "Python"
    if str(PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(PYTHON_ROOT))
    from app.native_parity import native_python_source_contract_hash  # noqa: E402


SIGNED_EXPECTED_ARTIFACTS = {
    "rust-native-live-market-data-smoke.json",
    "rust-native-live-account-read-smoke.json",
}
MARKET_EXPECTED_ARTIFACTS = {"rust-native-live-market-data-smoke.json"}
SECRET_SENTINELS = ("dummy-rust-preflight-key", "dummy-rust-preflight-secret")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rust_workspace() -> Path:
    return _repo_root() / "experiments" / "rust-shells"


def _tail(text: str, max_chars: int = 4000) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _parse_stdout_json(stdout: str) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"stdout is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "stdout JSON must be an object"
    return payload, ""


def _preflight_env(evidence_dir: Path, *, with_dummy_credentials: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["RUST_NATIVE_RUNTIME_EVIDENCE_DIR"] = str(evidence_dir)
    env["BINANCE_TESTNET"] = "true"
    env.pop("BINANCE_API_KEY", None)
    env.pop("BINANCE_API_SECRET", None)
    env.pop("TRADING_BOT_RUST_LIVE_SMOKE", None)
    if with_dummy_credentials:
        env["BINANCE_API_KEY"] = SECRET_SENTINELS[0]
        env["BINANCE_API_SECRET"] = SECRET_SENTINELS[1]
        env["TRADING_BOT_RUST_LIVE_SMOKE"] = "1"
    return env


def _market_preflight_env(evidence_dir: Path, *, confirmed: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["RUST_NATIVE_RUNTIME_EVIDENCE_DIR"] = str(evidence_dir)
    env["BINANCE_TESTNET"] = "true"
    env.pop("BINANCE_API_KEY", None)
    env.pop("BINANCE_API_SECRET", None)
    env.pop("TRADING_BOT_RUST_LIVE_SMOKE", None)
    env.pop("TRADING_BOT_RUST_MARKET_SMOKE", None)
    if confirmed:
        env["TRADING_BOT_RUST_MARKET_SMOKE"] = "1"
    return env


def _run_preflight(
    evidence_dir: Path,
    *,
    with_dummy_credentials: bool,
    timeout: int,
) -> dict[str, Any]:
    cargo = shutil.which("cargo")
    if not cargo:
        return {
            "ok": False,
            "returncode": None,
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke-preflight",
            "stdout_tail": "",
            "stderr_tail": "cargo was not found on PATH",
            "payload": None,
            "issues": ["cargo was not found on PATH"],
        }

    command = [cargo, "run", "-p", "trading-bot-rust", "--", "--native-live-smoke-preflight"]
    try:
        result = subprocess.run(
            command,
            cwd=_rust_workspace(),
            env=_preflight_env(evidence_dir, with_dummy_credentials=with_dummy_credentials),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "command": " ".join(command),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail((exc.stderr or "") + f"\nTimed out after {timeout} seconds."),
            "payload": None,
            "issues": [f"timed out after {timeout} seconds"],
        }

    payload, parse_issue = _parse_stdout_json(result.stdout)
    return {
        "ok": not parse_issue,
        "returncode": result.returncode,
        "command": " ".join(command),
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
        "payload": payload,
        "issues": [parse_issue] if parse_issue else [],
    }


def _run_market_preflight(
    evidence_dir: Path,
    *,
    confirmed: bool,
    timeout: int,
) -> dict[str, Any]:
    cargo = shutil.which("cargo")
    if not cargo:
        return {
            "ok": False,
            "returncode": None,
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight",
            "stdout_tail": "",
            "stderr_tail": "cargo was not found on PATH",
            "payload": None,
            "issues": ["cargo was not found on PATH"],
        }

    command = [cargo, "run", "-p", "trading-bot-rust", "--", "--native-live-market-smoke-preflight"]
    try:
        result = subprocess.run(
            command,
            cwd=_rust_workspace(),
            env=_market_preflight_env(evidence_dir, confirmed=confirmed),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "command": " ".join(command),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail((exc.stderr or "") + f"\nTimed out after {timeout} seconds."),
            "payload": None,
            "issues": [f"timed out after {timeout} seconds"],
        }

    payload, parse_issue = _parse_stdout_json(result.stdout)
    return {
        "ok": not parse_issue,
        "returncode": result.returncode,
        "command": " ".join(command),
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
        "payload": payload,
        "issues": [parse_issue] if parse_issue else [],
    }


def _artifact_names(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return sorted(item.name for item in path.iterdir() if item.is_file())


def _validate_payload(
    payload: dict[str, Any] | None,
    *,
    expected_ok: bool,
    expected_mode: str,
    expected_artifacts: set[str],
    expected_missing: set[str],
    expected_prerequisites: dict[str, Any],
    evidence_dir: Path,
    expected_operator_fragments: tuple[str, ...],
) -> list[str]:
    if payload is None:
        return ["missing preflight JSON payload"]
    issues: list[str] = []
    if payload.get("ok") is not expected_ok:
        issues.append(f"payload ok must be {expected_ok}")
    if payload.get("mode") != expected_mode:
        issues.append(f"payload mode must be {expected_mode}")
    for field in (
        "network_access_attempted",
        "order_submission_attempted",
        "runtime_ready_claimed",
    ):
        if payload.get(field) is not False:
            issues.append(f"{field} must be false")
    for field in ("read_only", "secrets_redacted"):
        if payload.get(field) is not True:
            issues.append(f"{field} must be true")
    python_source_contract_hash = str(payload.get("python_source_contract_hash") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", python_source_contract_hash):
        issues.append("payload python_source_contract_hash must be a SHA-256 hex digest")
    elif python_source_contract_hash != native_python_source_contract_hash():
        issues.append(
            "payload python_source_contract_hash must match current Python source contract "
            f"{native_python_source_contract_hash()}"
        )
    if Path(str(payload.get("evidence_dir") or "")) != evidence_dir:
        issues.append("payload evidence_dir must match the isolated preflight directory")
    expected = sorted(expected_artifacts)
    if sorted(str(item) for item in payload.get("expected_artifacts", [])) != expected:
        issues.append(f"payload expected_artifacts must be {expected}")
    missing = {str(item) for item in payload.get("missing", [])}
    if missing != expected_missing:
        issues.append(f"payload missing must be {sorted(expected_missing)}")
    source_control_guard = payload.get("source_control_write_guard")
    if not isinstance(source_control_guard, dict):
        issues.append("payload source_control_write_guard must be an object")
    else:
        if source_control_guard.get("ok") is not True:
            issues.append("payload source_control_write_guard.ok must be true for isolated preflight directories")
        if source_control_guard.get("issues") not in ([], None):
            issues.append("payload source_control_write_guard.issues must be empty for isolated preflight directories")
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, dict):
        issues.append("payload prerequisites must be an object")
    else:
        for field, expected_value in expected_prerequisites.items():
            if prerequisites.get(field) != expected_value:
                issues.append(f"payload prerequisites.{field} must be {expected_value!r}")
    operator_command = str(payload.get("operator_command") or "")
    for fragment in expected_operator_fragments:
        if fragment not in operator_command:
            issues.append(f"payload operator_command must include {fragment}")
    return issues


def check_live_smoke_preflight(*, timeout: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="trading-bot-rust-preflight-") as temp_dir:
        root = Path(temp_dir)
        missing_dir = root / "missing-env"
        dummy_dir = root / "dummy-env"
        market_missing_dir = root / "market-missing-env"
        market_confirmed_dir = root / "market-confirmed-env"
        missing_dir.mkdir()
        dummy_dir.mkdir()
        market_missing_dir.mkdir()
        market_confirmed_dir.mkdir()

        missing_run = _run_preflight(missing_dir, with_dummy_credentials=False, timeout=timeout)
        dummy_run = _run_preflight(dummy_dir, with_dummy_credentials=True, timeout=timeout)
        market_missing_run = _run_market_preflight(market_missing_dir, confirmed=False, timeout=timeout)
        market_confirmed_run = _run_market_preflight(market_confirmed_dir, confirmed=True, timeout=timeout)

        issues: list[str] = []
        if missing_run["returncode"] != 1:
            issues.append("missing-env preflight must fail with exit code 1")
        if dummy_run["returncode"] != 0:
            issues.append("dummy-env preflight must pass with exit code 0")
        if market_missing_run["returncode"] != 1:
            issues.append("market-missing-env preflight must fail with exit code 1")
        if market_confirmed_run["returncode"] != 0:
            issues.append("market-confirmed-env preflight must pass with exit code 0")
        issues.extend(
            f"missing-env: {issue}"
            for issue in _validate_payload(
                missing_run.get("payload"),
                expected_ok=False,
                expected_mode="native_live_smoke_preflight",
                expected_artifacts=SIGNED_EXPECTED_ARTIFACTS,
                expected_missing={"BINANCE_API_KEY", "BINANCE_API_SECRET", "TRADING_BOT_RUST_LIVE_SMOKE=1"},
                expected_prerequisites={
                    "binance_api_key_present": False,
                    "binance_api_secret_present": False,
                    "live_smoke_confirmation_present": False,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                evidence_dir=missing_dir,
                expected_operator_fragments=("BINANCE_API_KEY=...", "BINANCE_API_SECRET=...", "--native-live-smoke"),
            )
        )
        issues.extend(
            f"dummy-env: {issue}"
            for issue in _validate_payload(
                dummy_run.get("payload"),
                expected_ok=True,
                expected_mode="native_live_smoke_preflight",
                expected_artifacts=SIGNED_EXPECTED_ARTIFACTS,
                expected_missing=set(),
                expected_prerequisites={
                    "binance_api_key_present": True,
                    "binance_api_secret_present": True,
                    "live_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                evidence_dir=dummy_dir,
                expected_operator_fragments=("BINANCE_API_KEY=...", "BINANCE_API_SECRET=...", "--native-live-smoke"),
            )
        )
        issues.extend(
            f"market-missing-env: {issue}"
            for issue in _validate_payload(
                market_missing_run.get("payload"),
                expected_ok=False,
                expected_mode="native_live_market_smoke_preflight",
                expected_artifacts=MARKET_EXPECTED_ARTIFACTS,
                expected_missing={"TRADING_BOT_RUST_MARKET_SMOKE=1"},
                expected_prerequisites={
                    "market_smoke_confirmation_present": False,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                evidence_dir=market_missing_dir,
                expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
            )
        )
        issues.extend(
            f"market-confirmed-env: {issue}"
            for issue in _validate_payload(
                market_confirmed_run.get("payload"),
                expected_ok=True,
                expected_mode="native_live_market_smoke_preflight",
                expected_artifacts=MARKET_EXPECTED_ARTIFACTS,
                expected_missing=set(),
                expected_prerequisites={
                    "market_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                evidence_dir=market_confirmed_dir,
                expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
            )
        )

        for label, run in (
            ("missing-env", missing_run),
            ("dummy-env", dummy_run),
            ("market-missing-env", market_missing_run),
            ("market-confirmed-env", market_confirmed_run),
        ):
            combined_output = f"{run.get('stdout_tail', '')}\n{run.get('stderr_tail', '')}"
            for secret in SECRET_SENTINELS:
                if secret in combined_output:
                    issues.append(f"{label} leaked a dummy secret sentinel")

        missing_artifacts = _artifact_names(missing_dir)
        dummy_artifacts = _artifact_names(dummy_dir)
        market_missing_artifacts = _artifact_names(market_missing_dir)
        market_confirmed_artifacts = _artifact_names(market_confirmed_dir)
        if missing_artifacts:
            issues.append(f"missing-env preflight wrote unexpected artifacts: {missing_artifacts}")
        if dummy_artifacts:
            issues.append(f"dummy-env preflight wrote unexpected artifacts: {dummy_artifacts}")
        if market_missing_artifacts:
            issues.append(f"market-missing-env preflight wrote unexpected artifacts: {market_missing_artifacts}")
        if market_confirmed_artifacts:
            issues.append(f"market-confirmed-env preflight wrote unexpected artifacts: {market_confirmed_artifacts}")

        return {
            "ok": not issues,
            "issues": issues,
            "preflight_modes": {
                "missing_env": missing_run,
                "dummy_env": dummy_run,
                "market_missing_env": market_missing_run,
                "market_confirmed_env": market_confirmed_run,
            },
            "artifact_writes": {
                "missing_env": missing_artifacts,
                "dummy_env": dummy_artifacts,
                "market_missing_env": market_missing_artifacts,
                "market_confirmed_env": market_confirmed_artifacts,
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=120, help="Maximum seconds per Rust preflight command.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_live_smoke_preflight(timeout=int(args.timeout))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print("Rust native live-smoke preflight ok")
    else:
        print("Rust native live-smoke preflight failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
