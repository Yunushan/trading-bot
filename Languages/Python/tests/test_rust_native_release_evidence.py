import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_rust_native_local_recovery_evidence as local_recovery  # noqa: E402
from tools import check_rust_native_live_smoke_preflight as live_smoke_preflight  # noqa: E402
from tools import check_rust_native_runtime_evidence as runtime_evidence  # noqa: E402
from tools import check_rust_native_evidence_workflows as evidence_workflows  # noqa: E402
from tools import check_generated_evidence_source_control as evidence_source_control  # noqa: E402
from tools import check_native_cpp as native_cpp  # noqa: E402
from tools import check_release_platform_matrix as release_platform_matrix  # noqa: E402
from tools import check_release_assets as release_assets  # noqa: E402
from tools import import_rust_native_evidence_artifacts as evidence_importer  # noqa: E402
from tools import run_release_platform_probe as release_platform_probe  # noqa: E402
from tools import audit_rust_native_runtime_readiness as runtime_readiness  # noqa: E402
from tools import write_rust_native_release_evidence as release_evidence  # noqa: E402


BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
PYTHON_SOURCE_CONTRACT_HASH = runtime_evidence.native_python_source_contract_hash()


def _native_source_sync_binding(contract_hash: str = PYTHON_SOURCE_CONTRACT_HASH) -> dict[str, object]:
    return {
        "required": True,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": contract_hash,
        "surface_contract_required": True,
    }


def _market_smoke_endpoints(base_url: str = BINANCE_FUTURES_TESTNET_BASE_URL) -> list[dict[str, str]]:
    return [
        {"name": "exchangeInfo", "status": "passed", "url": f"{base_url}/fapi/v1/exchangeInfo"},
        {"name": "klines", "status": "passed", "url": f"{base_url}/fapi/v1/klines"},
        {"name": "tickerPrice", "status": "passed", "url": f"{base_url}/fapi/v1/ticker/price"},
    ]


def _account_smoke_endpoints(base_url: str = BINANCE_FUTURES_TESTNET_BASE_URL) -> list[dict[str, str]]:
    return [
        {"name": "positionSideDual", "status": "passed", "url": f"{base_url}/fapi/v1/positionSide/dual"},
        {"name": "multiAssetsMargin", "status": "passed", "url": f"{base_url}/fapi/v1/multiAssetsMargin"},
        {"name": "balance", "status": "passed", "url": f"{base_url}/fapi/v2/balance"},
        {"name": "positionRisk", "status": "passed", "url": f"{base_url}/fapi/v2/positionRisk"},
    ]


def _market_smoke_suite_results(symbol: str = "BTCUSDT") -> list[dict[str, object]]:
    return [
        {"name": "fetch_usdt_symbols", "status": "passed", "observed_count": 5},
        {"name": "fetch_klines", "status": "passed", "observed_count": 10},
        {"name": "fetch_ticker_price", "status": "passed", "symbol": symbol},
        {
            "name": "native_runtime_read_only_market_cycle",
            "status": "passed",
            "stream_connected": True,
            "rest_stream_connected": True,
            "websocket_connected": True,
            "websocket_url": "wss://stream.binancefuture.com/ws/btcusdt@kline_1m",
            "websocket_timeout_ms": 20000,
            "websocket_poll_status": "event",
            "websocket_event_kind": "kline",
            "strategy_evaluated": True,
            "trading_execution_supported": False,
            "computed_indicator_keys": ["rsi"],
            "unsupported_indicator_keys": [],
            "status_message": "Read-only native market cycle evaluated strategy; signal=none.",
        },
    ]


def _account_smoke_suite_results() -> list[dict[str, object]]:
    return [
        {
            "name": "fetch_futures_position_mode",
            "status": "passed",
            "position_mode": "Hedge",
            "dual_side_position": True,
        },
        {
            "name": "fetch_futures_multi_assets_mode",
            "status": "passed",
            "multi_assets_margin": False,
        },
        {
            "name": "fetch_usdt_balance",
            "status": "passed",
            "asset": "USDT",
            "balances_redacted": True,
        },
        {"name": "fetch_open_futures_positions", "status": "passed", "observed_count": 0},
        {
            "name": "native_runtime_read_only_account_bootstrap",
            "status": "passed",
            "signal_evaluation_allowed": False,
            "trading_execution_supported": False,
            "preflight_message": "Native account preflight blocked: Futures settings unknown.",
            "status_message": "Read-only native account bootstrap is safe but not signal-ready.",
        },
    ]


def _release_platform_suite_results(target: dict[str, object]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for suite_name in target.get("test_suites", []):
        row: dict[str, object] = {"name": str(suite_name), "status": "passed"}
        if suite_name == "platform-probe":
            row["target_match"] = {"matched": True, "issues": []}
        results.append(row)
    return results


def _target_evidence_payload(target: dict[str, object]) -> dict[str, object]:
    return {
        "target_id": str(target["id"]),
        "status": "passed",
        "suite_results": _release_platform_suite_results(target),
    }


def _json_sha256(payload: dict[str, object]) -> str:
    data = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _valid_source_sync_consumer_rows() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "ok": True,
            "missing_text": [],
            "unknown_service_routes": [],
            "unknown_route_extractors": [],
        }
        for name in evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES
    ]


def _valid_source_sync_audit_payload(contract_hash: str = PYTHON_SOURCE_CONTRACT_HASH) -> dict[str, object]:
    return {
        "ok": True,
        "source": "Languages/Python/app/native_parity.py",
        "contract_hash": contract_hash,
        "surface_contract": {
            "ok": True,
            "required_generated_artifact_names": list(evidence_importer.SOURCE_SYNC_REQUIRED_GENERATED_ARTIFACTS),
            "actual_generated_artifact_names": list(evidence_importer.SOURCE_SYNC_REQUIRED_GENERATED_ARTIFACTS),
            "required_consumer_surface_names": list(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            "actual_consumer_surface_names": list(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            "issues": [],
        },
        "generated": [
            {
                "name": name,
                "ok": True,
                "embeds_contract_hash": True,
                "expected_contract_hash": contract_hash,
                "actual_sha256": f"{index:064x}",
                "expected_sha256": f"{index:064x}",
                "actual_bytes": index,
                "expected_bytes": index,
                "issues": [],
            }
            for index, name in enumerate(
                evidence_importer.SOURCE_SYNC_REQUIRED_GENERATED_ARTIFACTS,
                start=1,
            )
        ],
        "consumers": _valid_source_sync_consumer_rows(),
        "issues": [],
    }


class RustNativeReleaseEvidenceTests(unittest.TestCase):
    def test_evidence_workflow_checker_covers_ci_gate(self):
        result = evidence_workflows.check_workflows(REPO_ROOT)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(5, result["workflow_count"])
        workflows = {workflow["name"]: workflow for workflow in result["workflows"]}
        self.assertIn("ci_rust_native_gate", workflows)
        self.assertEqual(".github/workflows/ci.yml", workflows["ci_rust_native_gate"]["path"])
        ci_workflow_text = (REPO_ROOT / workflows["ci_rust_native_gate"]["path"]).read_text(encoding="utf-8")
        ci_importer_section = ci_workflow_text[
            ci_workflow_text.find("Audit Rust native evidence importer") : ci_workflow_text.find(
                "Audit Rust native runtime promotion readiness"
            )
        ]
        self.assertIn("artifacts/native-source-sync", ci_importer_section)
        self.assertIn("--require-native-source-sync-audit", ci_importer_section)
        self.assertIn("live_smoke", workflows)
        self.assertIn("release_platform_real_tests", workflows)
        self.assertIn("release_evidence", workflows)
        self.assertIn("promotion_audit", workflows)
        release_platform_workflow_text = (REPO_ROOT / workflows["release_platform_real_tests"]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("--require-native-source-sync", release_platform_workflow_text)
        for workflow_name in (
            "ci_rust_native_gate",
            "live_smoke",
            "release_platform_real_tests",
            "release_evidence",
            "promotion_audit",
        ):
            with self.subTest(workflow=workflow_name):
                workflow = workflows[workflow_name]
                self.assertTrue(workflow["ok"], workflow["issues"])
                workflow_text = (REPO_ROOT / workflow["path"]).read_text(encoding="utf-8")
                self.assertIn("Audit native source sync", workflow_text)
                self.assertIn("python tools/audit_native_source_sync.py --json", workflow_text)
                self.assertIn("--output artifacts/native-source-sync/native-source-sync-audit.json", workflow_text)
                self.assertIn("Upload native source sync audit", workflow_text)
                self.assertIn("name: native-source-sync-audit", workflow_text)
                self.assertIn("path: artifacts/native-source-sync/native-source-sync-audit.json", workflow_text)
        promotion_workflow_text = (REPO_ROOT / workflows["promotion_audit"]["path"]).read_text(encoding="utf-8")
        self.assertIn("--require-native-source-sync", promotion_workflow_text)
        live_smoke_workflow_text = (REPO_ROOT / workflows["live_smoke"]["path"]).read_text(encoding="utf-8")
        self.assertIn("Validate Rust native live-smoke preflight", live_smoke_workflow_text)
        self.assertIn(
            "python tools/check_rust_native_live_smoke_preflight.py --json --timeout 180",
            live_smoke_workflow_text,
        )

    def test_source_sync_importer_uses_audit_surface_contract_names(self):
        self.assertIs(
            evidence_importer.SOURCE_SYNC_REQUIRED_GENERATED_ARTIFACTS,
            evidence_importer.REQUIRED_GENERATED_ARTIFACT_NAMES,
        )
        self.assertIs(
            evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES,
            evidence_importer.REQUIRED_CONSUMER_SURFACE_NAMES,
        )

    def test_live_smoke_preflight_payload_requires_current_python_source_contract_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            payload = {
                "ok": True,
                "mode": "native_live_market_smoke_preflight",
                "network_access_attempted": False,
                "order_submission_attempted": False,
                "runtime_ready_claimed": False,
                "commit": "current-commit",
                "read_only": True,
                "secrets_redacted": True,
                "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                "native_source_sync": _native_source_sync_binding(),
                "source_tree_clean": True,
                "evidence_dir": str(evidence_dir),
                "expected_artifacts": ["rust-native-live-market-data-smoke.json"],
                "missing": [],
                "source_control_write_guard": {"ok": True, "issues": []},
                "prerequisites": {
                    "market_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -- --native-live-market-smoke",
            }

            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                matching = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=True,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing=set(),
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

            payload["python_source_contract_hash"] = "0" * 64
            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                stale = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=True,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing=set(),
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

        self.assertEqual([], matching)
        self.assertTrue(
            any("python_source_contract_hash must match current Python source contract" in issue for issue in stale)
        )

    def test_live_smoke_preflight_payload_requires_native_source_sync_binding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            payload = {
                "ok": True,
                "mode": "native_live_market_smoke_preflight",
                "network_access_attempted": False,
                "order_submission_attempted": False,
                "runtime_ready_claimed": False,
                "commit": "current-commit",
                "read_only": True,
                "secrets_redacted": True,
                "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                "native_source_sync": _native_source_sync_binding(),
                "source_tree_clean": True,
                "evidence_dir": str(evidence_dir),
                "expected_artifacts": ["rust-native-live-market-data-smoke.json"],
                "missing": [],
                "source_control_write_guard": {"ok": True, "issues": []},
                "prerequisites": {
                    "market_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -- --native-live-market-smoke",
            }

            def validate(payload_under_test: dict[str, object]) -> list[str]:
                with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                    return live_smoke_preflight._validate_payload(
                        payload_under_test,
                        expected_ok=True,
                        expected_mode="native_live_market_smoke_preflight",
                        expected_artifacts={"rust-native-live-market-data-smoke.json"},
                        expected_missing=set(),
                        expected_prerequisites={
                            "market_smoke_confirmation_present": True,
                            "binance_testnet": True,
                            "symbol": "BTCUSDT",
                            "interval": "1m",
                        },
                        evidence_dir=evidence_dir,
                        expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                    )

            matching = validate(payload)
            missing_binding_payload = json.loads(json.dumps(payload))
            del missing_binding_payload["native_source_sync"]
            missing_binding = validate(missing_binding_payload)
            stale_binding_payload = json.loads(json.dumps(payload))
            stale_binding_payload["native_source_sync"]["contract_hash"] = "0" * 64
            stale_binding = validate(stale_binding_payload)

        self.assertEqual([], matching)
        self.assertTrue(
            any("payload native_source_sync must be a non-empty object" in issue for issue in missing_binding)
        )
        self.assertTrue(
            any(
                "payload native_source_sync.contract_hash must match current Python source contract" in issue
                for issue in stale_binding
            )
        )

    def test_live_smoke_preflight_payload_requires_current_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            payload = {
                "ok": True,
                "mode": "native_live_market_smoke_preflight",
                "network_access_attempted": False,
                "order_submission_attempted": False,
                "runtime_ready_claimed": False,
                "commit": "current-commit",
                "read_only": True,
                "secrets_redacted": True,
                "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                "native_source_sync": _native_source_sync_binding(),
                "source_tree_clean": True,
                "evidence_dir": str(evidence_dir),
                "expected_artifacts": ["rust-native-live-market-data-smoke.json"],
                "missing": [],
                "source_control_write_guard": {"ok": True, "issues": []},
                "prerequisites": {
                    "market_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -- --native-live-market-smoke",
            }

            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                matching = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=True,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing=set(),
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

            payload["commit"] = "stale-commit"
            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                stale = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=True,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing=set(),
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

        self.assertEqual([], matching)
        self.assertTrue(any("payload commit must match current git commit current-commit" in issue for issue in stale))

    def test_live_smoke_preflight_payload_models_dirty_source_as_missing_prerequisite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            payload = {
                "ok": False,
                "mode": "native_live_market_smoke_preflight",
                "network_access_attempted": False,
                "order_submission_attempted": False,
                "runtime_ready_claimed": False,
                "commit": "current-commit",
                "read_only": True,
                "secrets_redacted": True,
                "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                "native_source_sync": _native_source_sync_binding(),
                "source_tree_clean": False,
                "evidence_dir": str(evidence_dir),
                "expected_artifacts": ["rust-native-live-market-data-smoke.json"],
                "missing": ["clean source tree"],
                "source_control_write_guard": {"ok": True, "issues": []},
                "prerequisites": {
                    "market_smoke_confirmation_present": True,
                    "binance_testnet": True,
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                },
                "operator_command": "TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -- --native-live-market-smoke",
            }

            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                matching = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=False,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing={"clean source tree"},
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

            payload["missing"] = []
            with patch.object(live_smoke_preflight, "_current_git_commit", return_value="current-commit"):
                stale = live_smoke_preflight._validate_payload(
                    payload,
                    expected_ok=False,
                    expected_mode="native_live_market_smoke_preflight",
                    expected_artifacts={"rust-native-live-market-data-smoke.json"},
                    expected_missing={"clean source tree"},
                    expected_prerequisites={
                        "market_smoke_confirmation_present": True,
                        "binance_testnet": True,
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                    },
                    evidence_dir=evidence_dir,
                    expected_operator_fragments=("TRADING_BOT_RUST_MARKET_SMOKE=1", "--native-live-market-smoke"),
                )

        self.assertEqual([], matching)
        self.assertTrue(any("payload missing must be ['clean source tree']" in issue for issue in stale))

    def test_generated_evidence_source_control_guard_rejects_existing_tracked_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tracked_runtime_artifact = Path("artifacts/rust-native-runtime-evidence/stale.json")
            tracked_workflow_plan_artifact = Path(
                "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md"
            )
            tracked_plan_artifact = Path("artifacts/rust-native-runtime-evidence-plan.md")
            tracked_source_sync_artifact = Path("artifacts/native-source-sync/native-source-sync-audit.json")
            pending_removal_artifact = Path("release-platform-evidence/windows-11-x64.json")
            (root / tracked_runtime_artifact).parent.mkdir(parents=True)
            (root / tracked_source_sync_artifact).parent.mkdir(parents=True)
            (root / tracked_runtime_artifact).write_text("{}", encoding="utf-8")
            (root / tracked_workflow_plan_artifact).write_text("# generated workflow plan\n", encoding="utf-8")
            (root / tracked_plan_artifact).write_text("# generated plan\n", encoding="utf-8")
            (root / tracked_source_sync_artifact).write_text("{}", encoding="utf-8")

            result = evidence_source_control.check_generated_evidence_source_control(
                root=root,
                tracked_files=[
                    tracked_runtime_artifact.as_posix(),
                    tracked_workflow_plan_artifact.as_posix(),
                    tracked_plan_artifact.as_posix(),
                    tracked_source_sync_artifact.as_posix(),
                    pending_removal_artifact.as_posix(),
                    "docs/rust-native-runtime-evidence.json",
                ],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            [
                tracked_source_sync_artifact.as_posix(),
                tracked_plan_artifact.as_posix(),
                tracked_workflow_plan_artifact.as_posix(),
                tracked_runtime_artifact.as_posix(),
            ],
            result["tracked_existing_generated_evidence"],
        )
        self.assertEqual([pending_removal_artifact.as_posix()], result["tracked_pending_removal_generated_evidence"])
        self.assertTrue(any("generated evidence artifact is tracked as source" in issue for issue in result["issues"]))

    def test_generated_evidence_write_guard_rejects_tracked_pending_removal_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pending_output = Path("artifacts/rust-native-runtime-evidence/rust-native-live-account-read-smoke.json")
            result = evidence_source_control.generated_evidence_write_guard(
                [root / pending_output],
                root=root,
                tracked_files=[pending_output.as_posix()],
            )

        self.assertFalse(result["ok"])
        self.assertEqual([pending_output.as_posix()], result["tracked_generated_evidence_write_targets"])
        self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in result["issues"]))

    def test_generated_evidence_write_guard_rejects_in_repo_nongenerated_destinations(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as external_dir:
            root = Path(temp_dir)
            in_repo_output = Path("docs") / "rust-native-live-account-read-smoke.json"
            external_output = Path(external_dir) / "rust-native-live-account-read-smoke.json"
            result = evidence_source_control.generated_evidence_write_guard(
                [root / in_repo_output, external_output],
                root=root,
                tracked_files=[],
                require_generated_destinations=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual([in_repo_output.as_posix()], result["non_generated_in_repo_write_targets"])
        self.assertTrue(
            any("outside generated evidence directories inside the repository" in issue for issue in result["issues"])
        )

    def test_local_recovery_generation_refuses_tracked_generated_evidence_targets(self):
        tracked_targets = [
            "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
            "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
        ]
        guard = {
            "ok": False,
            "generated_evidence_write_targets": tracked_targets,
            "non_generated_in_repo_write_targets": [],
            "tracked_generated_evidence_write_targets": tracked_targets,
            "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
        }

        with (
            patch.object(local_recovery, "generated_evidence_write_guard", return_value=guard),
            patch.object(
                local_recovery,
                "_run_recovery_evidence_command",
                side_effect=AssertionError("cargo should not run when evidence targets are tracked"),
            ),
            patch.object(
                local_recovery,
                "validate",
                side_effect=AssertionError("validation should not run after source-control guard failure"),
            ),
        ):
            result = local_recovery.check_local_recovery_evidence(
                manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                evidence_dir=Path("artifacts/rust-native-runtime-evidence"),
                validate_only=False,
                timeout=1,
            )

        self.assertFalse(result["ok"])
        self.assertEqual("blocked-before-run", result["command"]["command"])
        self.assertEqual(tracked_targets, result["source_control_guard"]["generated_evidence_write_targets"])
        self.assertEqual(tracked_targets, result["source_control_guard"]["tracked_generated_evidence_targets"])
        self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in result["issues"]))

    def test_local_recovery_generation_refuses_in_repo_nongenerated_evidence_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "docs" / "recovery-evidence"
            expected_targets = [
                "docs/recovery-evidence/rust-native-live-stream-recovery.json",
                "docs/recovery-evidence/rust-native-order-guard-recovery.json",
            ]
            with (
                patch.object(local_recovery, "_repo_root", return_value=root),
                patch.object(
                    local_recovery,
                    "_run_recovery_evidence_command",
                    side_effect=AssertionError("cargo should not run for non-generated in-repo evidence paths"),
                ),
                patch.object(
                    local_recovery,
                    "validate",
                    side_effect=AssertionError("validation should not run after source-control guard failure"),
                ),
            ):
                result = local_recovery.check_local_recovery_evidence(
                    manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                    evidence_dir=evidence_dir,
                    validate_only=False,
                    timeout=1,
                )

        self.assertFalse(result["ok"])
        self.assertEqual("blocked-before-run", result["command"]["command"])
        self.assertEqual(expected_targets, result["source_control_guard"]["non_generated_in_repo_write_targets"])
        self.assertTrue(
            any("outside generated evidence directories inside the repository" in issue for issue in result["issues"])
        )

    def test_local_recovery_promotion_mode_requires_clean_source_before_running_cargo(self):
        with (
            patch.object(local_recovery, "_current_source_tree_clean", return_value=False),
            patch.object(
                local_recovery,
                "_current_source_tree_dirty_paths",
                return_value=["tools/check_rust_native_local_recovery_evidence.py"],
            ),
            patch.object(local_recovery, "_current_source_tree_untracked_paths", return_value=[]),
            patch.object(
                local_recovery,
                "_run_recovery_evidence_command",
                side_effect=AssertionError("cargo should not run from a dirty promotion source tree"),
            ),
            patch.object(
                local_recovery,
                "validate",
                side_effect=AssertionError("validation should not run after clean-source guard failure"),
            ),
        ):
            result = local_recovery.check_local_recovery_evidence(
                manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                evidence_dir=Path("artifacts/rust-native-runtime-evidence"),
                validate_only=False,
                timeout=1,
                require_clean_source=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["require_clean_source"])
        self.assertEqual("blocked-before-run", result["command"]["command"])
        self.assertFalse(result["promotion_source_guard"]["ok"])
        self.assertFalse(result["promotion_source_guard"]["source_tree_clean"])
        self.assertEqual(
            ["tools/check_rust_native_local_recovery_evidence.py"],
            result["promotion_source_guard"]["dirty_paths"],
        )
        self.assertTrue(any("source tree must be clean" in issue for issue in result["issues"]))

    def test_local_recovery_promotion_mode_requires_native_source_sync_before_running_cargo(self):
        failed_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        failed_source_sync["ok"] = False
        failed_source_sync["issues"] = ["generated contract drift"]

        with (
            patch.object(local_recovery, "_current_source_tree_clean", return_value=True),
            patch.object(local_recovery, "_current_source_tree_dirty_paths", return_value=[]),
            patch.object(local_recovery, "_current_source_tree_untracked_paths", return_value=[]),
            patch.object(local_recovery, "audit_native_source_sync", return_value=failed_source_sync),
            patch.object(
                local_recovery,
                "_run_recovery_evidence_command",
                side_effect=AssertionError("cargo should not run when native source-sync fails"),
            ),
            patch.object(
                local_recovery,
                "validate",
                side_effect=AssertionError("validation should not run after native source-sync guard failure"),
            ),
        ):
            result = local_recovery.check_local_recovery_evidence(
                manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                evidence_dir=Path("artifacts/rust-native-runtime-evidence"),
                validate_only=False,
                timeout=1,
                require_clean_source=True,
                require_native_source_sync=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["require_native_source_sync"])
        self.assertEqual("blocked-before-run", result["command"]["command"])
        self.assertFalse(result["native_source_sync_guard"]["ok"])
        self.assertEqual("fresh-hash", result["native_source_sync_guard"]["contract_hash"])
        self.assertTrue(any("generated contract drift" in issue for issue in result["issues"]))

    def test_local_recovery_validate_only_records_native_source_sync_guard(self):
        validation_result = {"ok": True, "issues": [], "artifact_status": []}
        with (
            patch.object(local_recovery, "_current_source_tree_clean", return_value=True),
            patch.object(local_recovery, "_current_source_tree_dirty_paths", return_value=[]),
            patch.object(local_recovery, "_current_source_tree_untracked_paths", return_value=[]),
            patch.object(
                local_recovery,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(local_recovery, "validate", return_value=validation_result) as validate_mock,
        ):
            result = local_recovery.check_local_recovery_evidence(
                manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                evidence_dir=Path("artifacts/rust-native-runtime-evidence"),
                validate_only=True,
                timeout=1,
                require_clean_source=True,
                require_native_source_sync=True,
            )

        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["native_source_sync_guard"]["ok"])
        self.assertEqual("fresh-hash", result["native_source_sync_guard"]["contract_hash"])
        self.assertTrue(result["native_source_sync_guard"]["surface_contract_ok"])
        validate_kwargs = validate_mock.call_args.kwargs
        self.assertTrue(validate_kwargs["require_current_commit"])
        self.assertTrue(validate_kwargs["require_clean_source"])

    def test_local_recovery_promotion_mode_validates_current_clean_evidence(self):
        source_control_guard = {
            "ok": True,
            "generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
            ],
            "non_generated_in_repo_write_targets": [],
            "tracked_generated_evidence_targets": [],
            "issues": [],
        }
        command_result = {
            "ok": True,
            "returncode": 0,
            "command": "cargo run -p trading-bot-rust -- --write-local-recovery-evidence",
            "stdout_tail": "",
            "stderr_tail": "",
        }
        validation_result = {"ok": True, "issues": [], "artifact_status": []}
        with (
            patch.object(local_recovery, "_current_source_tree_clean", return_value=True),
            patch.object(local_recovery, "_current_source_tree_dirty_paths", return_value=[]),
            patch.object(local_recovery, "_current_source_tree_untracked_paths", return_value=[]),
            patch.object(local_recovery, "local_recovery_generation_guard", return_value=source_control_guard),
            patch.object(local_recovery, "_run_recovery_evidence_command", return_value=command_result),
            patch.object(local_recovery, "validate", return_value=validation_result) as validate_mock,
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            result = local_recovery.check_local_recovery_evidence(
                manifest_path=Path("docs/rust-native-runtime-evidence.json"),
                evidence_dir=Path(temp_dir),
                validate_only=False,
                timeout=1,
                require_clean_source=True,
            )

        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["promotion_source_guard"]["ok"])
        self.assertTrue(result["promotion_source_guard"]["source_tree_clean"])
        validate_kwargs = validate_mock.call_args.kwargs
        self.assertTrue(validate_kwargs["require_current_commit"])
        self.assertTrue(validate_kwargs["require_clean_source"])
        self.assertEqual(local_recovery.RECOVERY_EVIDENCE_IDS, validate_kwargs["requirement_ids"])

    def test_importer_refuses_apply_to_tracked_generated_evidence_write_targets(self):
        candidate = evidence_importer.JsonCandidate(
            source="downloaded-artifact.zip!rust-native-live-market-data-smoke.json",
            name="rust-native-live-market-data-smoke.json",
            payload={"evidence_id": "rust-native-live-market-data-smoke"},
        )
        destination = REPO_ROOT / "artifacts" / "rust-native-runtime-evidence" / candidate.name
        guard = {
            "ok": False,
            "generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json"
            ],
            "tracked_generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json"
            ],
            "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
        }

        with (
            patch.object(evidence_importer, "_iter_json_candidates", return_value=([candidate], [])),
            patch.object(evidence_importer, "_load_release_targets", return_value=({}, [])),
            patch.object(evidence_importer, "_candidate_destination", return_value=("runtime", destination, [])),
            patch.object(evidence_importer, "generated_evidence_write_guard", return_value=guard),
        ):
            result = evidence_importer.import_evidence_artifacts(
                [Path("downloaded-artifact.zip")],
                apply=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(0, result["copied_count"])
        self.assertEqual(guard, result["source_control_write_guard"])
        self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in result["issues"]))

    def test_importer_refuses_apply_to_in_repo_nongenerated_evidence_destinations(self):
        candidate = evidence_importer.JsonCandidate(
            source="downloaded-artifact.zip!rust-native-live-market-data-smoke.json",
            name="rust-native-live-market-data-smoke.json",
            payload={"evidence_id": "rust-native-live-market-data-smoke"},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "docs" / candidate.name
            with (
                patch.object(evidence_importer, "_repo_root", return_value=root),
                patch.object(evidence_importer, "_iter_json_candidates", return_value=([candidate], [])),
                patch.object(evidence_importer, "_load_release_targets", return_value=({}, [])),
                patch.object(evidence_importer, "_candidate_destination", return_value=("runtime", destination, [])),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [Path("downloaded-artifact.zip")],
                    apply=True,
                )
            output_exists = destination.exists()

        self.assertFalse(result["ok"])
        self.assertEqual(0, result["copied_count"])
        self.assertFalse(output_exists)
        self.assertEqual(
            ["docs/rust-native-live-market-data-smoke.json"],
            result["source_control_write_guard"]["non_generated_in_repo_write_targets"],
        )
        self.assertTrue(
            any("outside generated evidence directories inside the repository" in issue for issue in result["issues"])
        )

    def test_release_evidence_writer_refuses_tracked_generated_output_target(self):
        artifact = {
            "evidence_id": "rust-native-release-platform-evidence",
            "status": "passed",
        }
        guard = {
            "ok": False,
            "generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-release-platform-evidence.json"
            ],
            "tracked_generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-release-platform-evidence.json"
            ],
            "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(release_evidence, "build_release_evidence", return_value=(artifact, [])),
            patch.object(release_evidence, "generated_evidence_write_guard", return_value=guard),
        ):
            output = io.StringIO()
            output_dir = Path(temp_dir) / "artifacts" / "rust-native-runtime-evidence"
            with contextlib.redirect_stdout(output):
                exit_code = release_evidence.main(
                    [
                        "--tag",
                        "v1.2.3",
                        "--output-dir",
                        str(output_dir),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            output_exists = (output_dir / "rust-native-release-platform-evidence.json").exists()

        self.assertEqual(1, exit_code)
        self.assertFalse(output_exists)
        self.assertFalse(payload["ok"])
        self.assertEqual(guard, payload["source_control_write_guard"])
        self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in payload["issues"]))

    def test_release_evidence_writer_refuses_in_repo_nongenerated_output_target(self):
        artifact = {
            "evidence_id": "rust-native-release-platform-evidence",
            "status": "passed",
        }
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(release_evidence, "_repo_root", return_value=Path(temp_dir)),
            patch.object(release_evidence, "build_release_evidence", return_value=(artifact, [])),
        ):
            output = io.StringIO()
            output_path = Path(temp_dir) / "docs" / "rust-native-release-platform-evidence.json"
            with contextlib.redirect_stdout(output):
                exit_code = release_evidence.main(
                    [
                        "--tag",
                        "v1.2.3",
                        "--output-dir",
                        "docs",
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            output_exists = output_path.exists()

        self.assertEqual(1, exit_code)
        self.assertFalse(output_exists)
        self.assertFalse(payload["ok"])
        self.assertEqual(
            ["docs/rust-native-release-platform-evidence.json"],
            payload["source_control_write_guard"]["non_generated_in_repo_write_targets"],
        )
        self.assertTrue(
            any("outside generated evidence directories inside the repository" in issue for issue in payload["issues"])
        )

    def test_readiness_audit_refuses_tracked_generated_plan_output(self):
        guard = {
            "ok": False,
            "generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md"
            ],
            "tracked_generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md"
            ],
            "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
        }
        audit_result = {
            "ok": True,
            "issues": [],
            "blockers": [],
            "promotion_ready": False,
            "promotion_requirements": [],
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(runtime_readiness, "audit", return_value=audit_result),
            patch.object(runtime_readiness, "generated_evidence_write_guard", return_value=guard),
        ):
            output = io.StringIO()
            plan_path = (
                Path(temp_dir) / "artifacts" / "rust-native-runtime-evidence" / "rust-native-runtime-evidence-plan.md"
            )
            with contextlib.redirect_stdout(output):
                exit_code = runtime_readiness.main(
                    [
                        "--write-evidence-plan",
                        str(plan_path),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(1, exit_code)
        self.assertFalse(plan_path.exists())
        self.assertFalse(payload["ok"])
        self.assertEqual(guard, payload["evidence_plan_write_guard"])
        self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in payload["issues"]))

    def test_readiness_live_smoke_prerequisites_require_canonical_write_guard(self):
        guard = {
            "ok": False,
            "generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json"
            ],
            "tracked_generated_evidence_write_targets": [
                "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json"
            ],
            "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
        }

        with (
            patch.dict(
                runtime_readiness.os.environ,
                {
                    "TRADING_BOT_RUST_MARKET_SMOKE": "1",
                    "TRADING_BOT_RUST_LIVE_SMOKE": "1",
                    "BINANCE_API_KEY": "test-key",
                    "BINANCE_API_SECRET": "test-secret",
                },
                clear=True,
            ),
            patch.object(runtime_readiness, "generated_evidence_write_guard", return_value=guard),
        ):
            result = runtime_readiness._live_smoke_prerequisites(
                REPO_ROOT / "artifacts" / "rust-native-runtime-evidence"
            )

        self.assertFalse(result["can_run_market_smoke"])
        self.assertFalse(result["can_run_live_smoke"])
        self.assertEqual(guard, result["market_source_control_write_guard"])
        self.assertEqual(guard, result["account_source_control_write_guard"])
        self.assertEqual(["generated evidence write guard"], result["market_missing_prerequisites"])
        self.assertEqual(["generated evidence write guard"], result["account_missing_prerequisites"])
        self.assertEqual(
            {"binance_testnet": "true", "symbol": "BTCUSDT", "interval": "1m"},
            result["github_workflow_inputs"],
        )
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json"],
            result["market_smoke_expected_artifacts"],
        )
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json", "rust-native-live-account-read-smoke.json"],
            result["live_smoke_expected_artifacts"],
        )
        self.assertEqual("rust-native-live-smoke-evidence", result["github_workflow_artifact"])
        self.assertEqual("rust-native-live-smoke-evidence-plan", result["github_workflow_plan_artifact"])
        self.assertEqual(["BINANCE_API_KEY", "BINANCE_API_SECRET"], result["github_workflow_requires_secrets"])
        self.assertIn("-f symbol=BTCUSDT", result["github_workflow"])

    def test_readiness_live_smoke_prerequisites_expose_configured_workflow_inputs(self):
        guard = {
            "ok": True,
            "generated_evidence_write_targets": [],
            "tracked_generated_evidence_write_targets": [],
            "issues": [],
        }

        with (
            patch.dict(
                runtime_readiness.os.environ,
                {
                    "TRADING_BOT_RUST_MARKET_SMOKE": "1",
                    "TRADING_BOT_RUST_LIVE_SMOKE": "1",
                    "BINANCE_API_KEY": "test-key",
                    "BINANCE_API_SECRET": "test-secret",
                    "BINANCE_TESTNET": "false",
                    "BINANCE_LIVE_SMOKE_SYMBOL": "ETHUSDT",
                    "BINANCE_LIVE_SMOKE_INTERVAL": "5m",
                },
                clear=True,
            ),
            patch.object(runtime_readiness, "generated_evidence_write_guard", return_value=guard),
        ):
            result = runtime_readiness._live_smoke_prerequisites(
                REPO_ROOT / "artifacts" / "rust-native-runtime-evidence"
            )

        self.assertTrue(result["can_run_market_smoke"])
        self.assertTrue(result["can_run_live_smoke"])
        self.assertEqual("false", result["binance_testnet"])
        self.assertEqual("ETHUSDT", result["live_smoke_symbol"])
        self.assertEqual("5m", result["live_smoke_interval"])
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            result["github_workflow_inputs"],
        )
        self.assertIn("BINANCE_TESTNET=false", result["market_command"])
        self.assertIn("BINANCE_LIVE_SMOKE_SYMBOL=ETHUSDT", result["command"])
        self.assertIn("-f binance_testnet=false", result["github_workflow"])
        self.assertIn("-f symbol=ETHUSDT", result["github_workflow"])
        self.assertIn("-f interval=5m", result["github_workflow"])

    def test_readiness_live_smoke_prerequisites_require_clean_source(self):
        guard = {
            "ok": True,
            "generated_evidence_write_targets": [],
            "tracked_generated_evidence_write_targets": [],
            "issues": [],
        }

        with (
            patch.dict(
                runtime_readiness.os.environ,
                {
                    "TRADING_BOT_RUST_MARKET_SMOKE": "1",
                    "TRADING_BOT_RUST_LIVE_SMOKE": "1",
                    "BINANCE_API_KEY": "test-key",
                    "BINANCE_API_SECRET": "test-secret",
                },
                clear=True,
            ),
            patch.object(runtime_readiness, "generated_evidence_write_guard", return_value=guard),
        ):
            result = runtime_readiness._live_smoke_prerequisites(
                REPO_ROOT / "artifacts" / "rust-native-runtime-evidence",
                source_tree_clean=False,
            )

        self.assertFalse(result["source_tree_clean"])
        self.assertFalse(result["can_run_market_smoke"])
        self.assertFalse(result["can_run_live_smoke"])
        self.assertEqual(["clean source tree"], result["market_missing_prerequisites"])
        self.assertEqual(["clean source tree"], result["account_missing_prerequisites"])

    def test_release_asset_fetch_uses_windows_cert_store_fallback_for_ssl_errors(self):
        fallback_payload = {
            "html_url": "https://github.com/Yunushan/trading-bot/releases/tag/v1.0.33",
            "assets": [{"name": "Trading-Bot-Rust-windows-x64-1.0.33.exe"}],
        }
        ssl_error = urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

        with (
            patch.object(release_assets.urllib.request, "urlopen", side_effect=ssl_error),
            patch.object(
                release_assets,
                "_github_json_from_windows_certificate_store",
                return_value=fallback_payload,
            ) as fallback,
        ):
            payload = release_assets._github_json(
                "https://api.github.com/repos/Yunushan/trading-bot/releases/tags/v1.0.33",
                timeout=1.0,
                token="token-not-rendered",
            )

        self.assertEqual(fallback_payload, payload)
        fallback.assert_called_once()

    def test_release_asset_fetch_does_not_use_windows_fallback_for_non_ssl_url_errors(self):
        network_error = urllib.error.URLError("temporary DNS failure")

        with (
            patch.object(release_assets.urllib.request, "urlopen", side_effect=network_error),
            patch.object(
                release_assets,
                "_github_json_from_windows_certificate_store",
                side_effect=AssertionError("fallback should not run"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Could not reach GitHub API"):
                release_assets._github_json(
                    "https://api.github.com/repos/Yunushan/trading-bot/releases/tags/v1.0.33",
                    timeout=1.0,
                    token=None,
                )

    def test_required_rust_release_assets_match_tier_one_desktop_targets(self):
        version, assets = release_assets._build_expected_assets("v1.2.3")
        required_rust_assets = {
            asset.name for asset in assets if asset.required and asset.name.startswith("Trading-Bot-Rust-")
        }
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, _browser_targets, issues = release_platform_matrix._validate_matrix(matrix)

        self.assertEqual("1.2.3", version)
        self.assertEqual([], issues)
        self.assertEqual(
            {"windows-11-x64", "macos-15-arm64", "ubuntu-24_04-x64"},
            {str(target["id"]) for target in platform_targets},
        )
        self.assertEqual(
            {
                "Trading-Bot-Rust-windows-x64-1.2.3.exe",
                "Trading-Bot-Rust-linux-x86_64-1.2.3.tar.gz",
                "Trading-Bot-Rust-macos-15-arm64-1.2.3.zip",
            },
            required_rust_assets,
        )

    def test_build_release_evidence_requires_rust_assets_and_platform_results(self):
        tag = "v1.2.3"
        _, expected_assets = release_evidence._build_expected_assets(tag)
        rust_required_names = {
            asset.name for asset in expected_assets if asset.required and asset.name.startswith("Trading-Bot-Rust-")
        }
        release_payload = {"assets": [{"name": name} for name in sorted(rust_required_names)]}
        platform_targets = [
            {
                "id": "windows-11-x64",
                "kind": "platform",
                "runner_kind": "github-hosted-or-self-hosted",
                "runner_labels": ["self-hosted", "tb-release-platform", "windows-11-x64"],
                "test_suites": ["platform-probe", "desktop-release-smoke", "native-build-smoke"],
            }
        ]
        browser_targets = [
            {
                "id": "browser-chrome-windows-11-x64",
                "kind": "browser",
                "runner_kind": "real-browser-or-browser-lab",
                "runner_labels": ["self-hosted", "tb-browser", "chrome-windows-11-x64"],
                "test_suites": ["browser-contract"],
            }
        ]
        targets_by_id = {target["id"]: target for target in platform_targets + browser_targets}

        def _read_platform_evidence(path: Path) -> dict[str, object]:
            target = targets_by_id[path.stem]
            payload = _target_evidence_payload(target)
            payload.update(
                {
                    "commit": "abc123",
                    "source_tree_clean": True,
                    "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                    "native_source_sync": _native_source_sync_binding(),
                    "runtime_ready_claimed": False,
                    "secrets_redacted": True,
                }
            )
            return payload

        with tempfile.TemporaryDirectory() as temp_dir:
            platform_evidence_dir = Path(temp_dir) / "release-platform-evidence"
            platform_evidence_dir.mkdir()
            for target in platform_targets + browser_targets:
                (platform_evidence_dir / f"{target['id']}.json").write_text("{}", encoding="utf-8")

            with (
                patch.object(release_evidence, "_fetch_release", return_value=release_payload),
                patch.object(release_evidence, "_load_json", return_value={"schema_version": 1}),
                patch.object(
                    release_evidence, "_validate_matrix", return_value=(platform_targets, browser_targets, [])
                ),
                patch.object(release_evidence, "_evidence_issues", return_value=[]),
                patch.object(release_evidence, "_read_evidence", side_effect=_read_platform_evidence),
                patch.object(release_evidence, "_sha256_file", return_value="a" * 64),
                patch.object(release_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(release_evidence, "_source_tree_clean", return_value=True),
            ):
                artifact, issues = release_evidence.build_release_evidence(
                    tag=tag,
                    owner="Yunushan",
                    repo="trading-bot",
                    timeout=1.0,
                    matrix_path=Path("docs/release-platform-test-matrix.json"),
                    platform_evidence_dir=platform_evidence_dir,
                )

        self.assertEqual([], issues)
        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual("rust-native-release-platform-evidence", artifact["evidence_id"])
        self.assertEqual("release_platform", artifact["evidence_scope"])
        self.assertFalse(artifact["runtime_ready_claimed"])
        self.assertTrue(artifact["source_tree_clean"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, artifact["python_source_contract_hash"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, artifact["native_source_sync"]["contract_hash"])
        self.assertTrue(artifact["native_source_sync"]["surface_contract_required"])
        self.assertTrue(artifact["secrets_redacted"])
        self.assertGreaterEqual(len(artifact["release_artifacts"]), len(rust_required_names))
        self.assertEqual(2, len(artifact["platform_results"]))
        self.assertTrue(all(row["suite_results"] for row in artifact["platform_results"]))
        self.assertTrue(all(row["evidence_file"].endswith(".json") for row in artifact["platform_results"]))
        self.assertTrue(all(row["evidence_sha256"] == "a" * 64 for row in artifact["platform_results"]))
        self.assertTrue(all(row["status"] == "passed" for row in artifact["suite_results"]))

    def test_build_release_evidence_fails_when_required_rust_assets_are_missing(self):
        tag = "v1.2.3"
        release_payload = {"assets": []}

        with (
            patch.object(release_evidence, "_source_tree_clean", return_value=True),
            patch.object(release_evidence, "_fetch_release", return_value=release_payload),
        ):
            artifact, issues = release_evidence.build_release_evidence(
                tag=tag,
                owner="Yunushan",
                repo="trading-bot",
                timeout=1.0,
                matrix_path=Path("docs/release-platform-test-matrix.json"),
                platform_evidence_dir=Path("release-platform-evidence"),
            )

        self.assertIsNone(artifact)
        self.assertTrue(any("missing required Rust release assets" in issue for issue in issues))

    def test_build_release_evidence_blocks_dirty_source_before_network(self):
        with (
            patch.object(release_evidence, "_source_tree_clean", return_value=False),
            patch.object(release_evidence, "_fetch_release", side_effect=AssertionError("network forbidden")),
        ):
            artifact, issues = release_evidence.build_release_evidence(
                tag="v1.2.3",
                owner="Yunushan",
                repo="trading-bot",
                timeout=1.0,
                matrix_path=Path("docs/release-platform-test-matrix.json"),
                platform_evidence_dir=Path("release-platform-evidence"),
            )

        self.assertIsNone(artifact)
        self.assertEqual([release_evidence.DIRTY_SOURCE_RELEASE_EVIDENCE_ISSUE], issues)

    def test_build_release_evidence_blocks_failed_native_source_sync_before_network(self):
        failed_source_sync = _valid_source_sync_audit_payload("stale-hash")
        failed_source_sync["ok"] = False
        failed_source_sync["issues"] = ["generated Rust contract is stale"]
        with (
            patch.object(release_evidence, "_source_tree_clean", return_value=True),
            patch.object(release_evidence, "audit_native_source_sync", return_value=failed_source_sync),
            patch.object(release_evidence, "_fetch_release", side_effect=AssertionError("network forbidden")),
        ):
            artifact, issues = release_evidence.build_release_evidence(
                tag="v1.2.3",
                owner="Yunushan",
                repo="trading-bot",
                timeout=1.0,
                matrix_path=Path("docs/release-platform-test-matrix.json"),
                platform_evidence_dir=Path("release-platform-evidence"),
            )

        self.assertIsNone(artifact)
        self.assertIn(release_evidence.FAILED_SOURCE_SYNC_RELEASE_EVIDENCE_ISSUE, issues)
        self.assertIn("generated Rust contract is stale", issues)

    def test_runtime_release_evidence_requires_required_rust_assets_and_full_platform_matrix(self):
        tag = "v1.2.3"
        _, expected_assets = release_evidence._build_expected_assets(tag)
        rust_release_artifacts = [
            {
                "name": asset.name,
                "group": asset.group,
                "required": asset.required,
                "status": "passed",
            }
            for asset in expected_assets
            if asset.required and asset.name.startswith("Trading-Bot-Rust-")
        ]
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, browser_targets, matrix_issues = release_platform_matrix._validate_matrix(matrix)
        self.assertEqual([], matrix_issues)
        platform_results = [
            {
                "target_id": target["id"],
                "kind": target["kind"],
                "runner_kind": target["runner_kind"],
                "status": "passed",
                "evidence_file": f"{target['id']}.json",
                "evidence_sha256": _json_sha256(_target_evidence_payload(target)),
                "expected_suite_count": len(target["test_suites"]),
                "test_suites": [str(item) for item in target["test_suites"]],
                "suite_count": len(target["test_suites"]),
                "suite_results": _release_platform_suite_results(target),
            }
            for target in platform_targets + browser_targets
        ]
        payload = {
            "evidence_id": "rust-native-release-platform-evidence",
            "status": "passed",
            "evidence_scope": "release_platform",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "python tools/write_rust_native_release_evidence.py --tag v1.2.3",
            "environment": {
                "tag": tag,
                "owner": "Yunushan",
                "repo": "trading-bot",
                "matrix": "docs/release-platform-test-matrix.json",
                "platform_evidence_dir": "release-platform-evidence",
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "release_artifacts": rust_release_artifacts,
            "platform_results": platform_results,
            "suite_results": [{"name": "release-platform", "status": "passed"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "rust-native-release-platform-evidence.json"
            platform_evidence_dir = evidence_dir / "release-platform-evidence"
            platform_evidence_dir.mkdir()
            for target in platform_targets + browser_targets:
                (platform_evidence_dir / f"{target['id']}.json").write_text(
                    json.dumps(_target_evidence_payload(target), sort_keys=True),
                    encoding="utf-8",
                )
            payload["environment"]["platform_evidence_dir"] = str(platform_evidence_dir)
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            valid = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            missing_asset_payload = json.loads(json.dumps(payload))
            missing_asset_payload["release_artifacts"] = missing_asset_payload["release_artifacts"][1:]
            evidence_path.write_text(json.dumps(missing_asset_payload), encoding="utf-8")
            missing_asset = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            missing_platform_payload = json.loads(json.dumps(payload))
            missing_platform_payload["platform_results"] = missing_platform_payload["platform_results"][1:]
            evidence_path.write_text(json.dumps(missing_platform_payload), encoding="utf-8")
            missing_platform = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            wrong_kind_payload = json.loads(json.dumps(payload))
            wrong_kind_payload["platform_results"][0]["kind"] = "browser"
            evidence_path.write_text(json.dumps(wrong_kind_payload), encoding="utf-8")
            wrong_kind = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            forged_asset_payload = json.loads(json.dumps(payload))
            forged_asset_payload["release_artifacts"].append(
                {
                    "name": "Trading-Bot-Rust-forged-platform-1.2.3.zip",
                    "group": "Forged",
                    "required": False,
                    "status": "passed",
                }
            )
            evidence_path.write_text(json.dumps(forged_asset_payload), encoding="utf-8")
            forged_asset = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            short_suite_payload = json.loads(json.dumps(payload))
            short_suite_payload["platform_results"][0]["suite_count"] = 1
            evidence_path.write_text(json.dumps(short_suite_payload), encoding="utf-8")
            short_suite = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            missing_embedded_suites_payload = json.loads(json.dumps(payload))
            del missing_embedded_suites_payload["platform_results"][0]["suite_results"]
            evidence_path.write_text(json.dumps(missing_embedded_suites_payload), encoding="utf-8")
            missing_embedded_suites = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            failed_embedded_suite_payload = json.loads(json.dumps(payload))
            failed_embedded_suite_payload["platform_results"][0]["suite_results"][0]["status"] = "failed"
            evidence_path.write_text(json.dumps(failed_embedded_suite_payload), encoding="utf-8")
            failed_embedded_suite = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            target_mismatch_payload = json.loads(json.dumps(payload))
            target_mismatch_payload["platform_results"][0]["suite_results"][0]["target_match"] = {
                "matched": False,
                "issues": ["system mismatch"],
            }
            evidence_path.write_text(json.dumps(target_mismatch_payload), encoding="utf-8")
            target_mismatch = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            missing_hash_payload = json.loads(json.dumps(payload))
            del missing_hash_payload["platform_results"][0]["evidence_sha256"]
            evidence_path.write_text(json.dumps(missing_hash_payload), encoding="utf-8")
            missing_hash = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

            wrong_hash_payload = json.loads(json.dumps(payload))
            wrong_hash_payload["platform_results"][0]["evidence_sha256"] = "0" * 64
            evidence_path.write_text(json.dumps(wrong_hash_payload), encoding="utf-8")
            wrong_hash = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-release-platform-evidence"},
            )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(missing_asset["ok"])
        self.assertTrue(any("missing required Rust release assets" in issue for issue in missing_asset["issues"]))
        self.assertFalse(missing_platform["ok"])
        self.assertTrue(any("missing release platform results" in issue for issue in missing_platform["issues"]))
        self.assertFalse(wrong_kind["ok"])
        self.assertTrue(any("platform_results[0].kind must be platform" in issue for issue in wrong_kind["issues"]))
        self.assertFalse(forged_asset["ok"])
        self.assertTrue(any("must be an expected Rust release asset" in issue for issue in forged_asset["issues"]))
        self.assertFalse(short_suite["ok"])
        self.assertTrue(
            any("platform_results[0].suite_count must be at least" in issue for issue in short_suite["issues"])
        )
        self.assertFalse(missing_embedded_suites["ok"])
        self.assertTrue(
            any(
                "platform_results[0].suite_results must be a non-empty list" in issue
                for issue in missing_embedded_suites["issues"]
            )
        )
        self.assertFalse(failed_embedded_suite["ok"])
        self.assertTrue(
            any(
                "platform_results[0].suite_results[0].status must be passed" in issue
                for issue in failed_embedded_suite["issues"]
            )
        )
        self.assertFalse(target_mismatch["ok"])
        self.assertTrue(
            any(
                "suite_results[platform-probe].target_match.matched must be true" in issue
                for issue in target_mismatch["issues"]
            )
        )
        self.assertFalse(missing_hash["ok"])
        self.assertTrue(
            any("evidence_sha256 must be a SHA-256 hex digest" in issue for issue in missing_hash["issues"])
        )
        self.assertFalse(wrong_hash["ok"])
        self.assertTrue(any("evidence_sha256 does not match" in issue for issue in wrong_hash["issues"]))

    def test_runtime_evidence_requires_native_source_sync_binding(self):
        payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "rust-native-live-account-read-smoke.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            valid = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-live-account-read-smoke"},
            )

            missing_binding_payload = json.loads(json.dumps(payload))
            del missing_binding_payload["native_source_sync"]
            evidence_path.write_text(json.dumps(missing_binding_payload), encoding="utf-8")
            missing_binding = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-live-account-read-smoke"},
            )

            stale_binding_payload = json.loads(json.dumps(payload))
            stale_binding_payload["native_source_sync"]["contract_hash"] = "0" * 64
            evidence_path.write_text(json.dumps(stale_binding_payload), encoding="utf-8")
            stale_binding = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={"rust-native-live-account-read-smoke"},
            )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(missing_binding["ok"])
        self.assertTrue(
            any("native_source_sync must be a non-empty object" in issue for issue in missing_binding["issues"])
        )
        self.assertFalse(stale_binding["ok"])
        self.assertTrue(
            any(
                "native_source_sync.contract_hash must match current Python source contract" in issue
                for issue in stale_binding["issues"]
            )
        )

    def test_release_evidence_preflight_reports_local_inputs_without_network(self):
        tag = "v1.2.3"
        platform_targets = [
            {
                "id": "windows-11-x64",
                "kind": "platform",
                "runner_kind": "github-hosted-or-self-hosted",
            }
        ]
        browser_targets = [
            {
                "id": "browser-chrome-windows-11-x64",
                "kind": "browser",
                "browser": "chrome",
                "host": "windows-11-x64",
                "runner_kind": "real-browser-or-browser-lab",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir) / "release-platform-evidence"
            output_dir = Path(temp_dir) / "runtime-evidence"
            evidence_dir.mkdir()
            (evidence_dir / "windows-11-x64.json").write_text("{}", encoding="utf-8")
            with (
                patch.object(release_evidence, "_fetch_release", side_effect=AssertionError("network forbidden")),
                patch.object(release_evidence, "_load_json", return_value={"schema_version": 1}),
                patch.object(
                    release_evidence, "_validate_matrix", return_value=(platform_targets, browser_targets, [])
                ),
                patch.object(release_evidence, "_source_tree_clean", return_value=True),
                patch.object(
                    release_evidence,
                    "_observed_platform",
                    return_value={
                        "system": "Windows",
                        "release": "11",
                        "normalized_architecture": "x64",
                    },
                ),
            ):
                result = release_evidence.preflight_release_evidence_inputs(
                    tag=tag,
                    owner="Yunushan",
                    repo="trading-bot",
                    matrix_path=Path("docs/release-platform-test-matrix.json"),
                    platform_evidence_dir=evidence_dir,
                    output_dir=output_dir,
                )

        self.assertFalse(result["ok"])
        self.assertFalse(result["network_access_attempted"])
        self.assertFalse(result["artifact_write_attempted"])
        self.assertFalse(result["release_asset_presence_verified"])
        self.assertTrue(result["release_asset_presence_requires_network"])
        self.assertTrue(result["secrets_redacted"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, result["native_source_sync"]["contract_hash"])
        self.assertTrue(result["native_source_sync"]["surface_contract_required"])
        self.assertTrue(result["native_source_sync_guard"]["ok"], result["native_source_sync_guard"]["issues"])
        self.assertTrue(result["native_source_sync_guard"]["surface_contract_ok"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, result["native_source_sync_guard"]["contract_hash"])
        self.assertGreaterEqual(len(result["required_rust_release_assets"]), 1)
        self.assertEqual(2, result["release_evidence_target_count"])
        self.assertEqual(1, result["platform_target_count"])
        self.assertEqual(1, result["browser_target_count"])
        self.assertEqual(1, result["present_platform_evidence_count"])
        self.assertEqual(0, result["passed_platform_evidence_count"])
        self.assertEqual(1, result["invalid_platform_evidence_count"])
        self.assertEqual("windows-11-x64", result["invalid_platform_evidence"][0]["target_id"])
        self.assertEqual(1, result["missing_platform_evidence_count"])
        self.assertEqual(["browser-chrome-windows-11-x64"], result["missing_platform_evidence_all"])
        self.assertEqual(["browser-chrome-windows-11-x64"], result["missing_platform_evidence"])
        self.assertEqual(1, len(result["missing_platform_evidence_plan"]))
        self.assertEqual("browser-chrome-windows-11-x64", result["missing_platform_evidence_plan"][0]["target_id"])
        self.assertNotIn(
            "browser_test_command", result["missing_platform_evidence_plan"][0]["required_workflow_inputs"]
        )
        self.assertTrue(result["missing_platform_evidence_plan"][0]["browser_contract_command_builtin"])
        self.assertEqual(
            "npm --prefix apps/web-dashboard run test:browser -- --browser=chrome",
            result["missing_platform_evidence_plan"][0]["browser_contract_command"],
        )
        self.assertIn(
            "tools/check_release_platform_matrix.py",
            result["missing_platform_evidence_plan"][0]["target_validation_command"],
        )
        self.assertIn(
            "--require-native-source-sync",
            result["missing_platform_evidence_plan"][0]["probe_command"],
        )
        self.assertIn(
            "--require-current-commit",
            result["missing_platform_evidence_plan"][0]["target_validation_command"],
        )
        self.assertIn(
            "--require-clean-source",
            result["missing_platform_evidence_plan"][0]["target_validation_command"],
        )
        self.assertIn(
            "--target-filter browser-chrome-windows-11-x64",
            result["missing_platform_evidence_plan"][0]["target_validation_command"],
        )
        workflow_example = result["missing_platform_evidence_plan"][0]["workflow_dispatch_example"]
        self.assertIn("gh workflow run release-platform-real-tests.yml", workflow_example)
        self.assertNotIn("browser_test_command", workflow_example)
        workflow_batch = result["workflow_dispatch_batch_plan"]
        self.assertEqual("release-platform-real-tests.yml", workflow_batch["workflow"])
        self.assertEqual(1, workflow_batch["target_count"])
        self.assertEqual(["browser-chrome-windows-11-x64"], workflow_batch["target_ids"])
        self.assertEqual(1, workflow_batch["command_count"])
        self.assertEqual(["browser-chrome-windows-11-x64"], workflow_batch["command_target_ids"])
        self.assertIn("gh workflow run release-platform-real-tests.yml", workflow_batch["commands"][0])
        self.assertEqual("browser-chrome-windows-11-x64", workflow_batch["workflow_dispatch_inputs"][0]["target_id"])
        self.assertEqual("[]", workflow_batch["workflow_dispatch_inputs"][0]["runner_labels_json"])
        self.assertNotIn("browser_test_command", workflow_batch["workflow_dispatch_inputs"][0])
        self.assertFalse(workflow_batch["commands_truncated"])
        self.assertEqual(0, workflow_batch["manual_input_target_count"])
        self.assertEqual(
            {
                "target_id": "all",
                "runner_labels_json": "",
                "require_all_evidence": True,
            },
            workflow_batch["complete_matrix_dispatch"]["workflow_dispatch_inputs"],
        )
        self.assertIn(
            "-f target_id=all -f require_all_evidence=true",
            workflow_batch["complete_matrix_dispatch"]["command"],
        )
        self.assertIn("--require-current-commit", workflow_batch["validation_command"])
        self.assertIn("write_rust_native_release_evidence.py", workflow_batch["aggregate_write_command"])
        self.assertEqual("windows-11-x64", result["local_browser_batch_plan"]["host"])
        self.assertEqual(["browser-chrome-windows-11-x64"], result["local_browser_batch_plan"]["target_ids"])
        self.assertEqual(1, result["local_browser_batch_plan"]["target_count"])
        self.assertIn("--list-local-browser-targets", result["local_browser_batch_plan"]["list_command"])
        self.assertIn("--local-browser-targets", result["local_browser_batch_plan"]["batch_command"])
        self.assertIn("--require-clean-source", result["local_browser_batch_plan"]["batch_command"])
        self.assertIn("--require-native-source-sync", result["local_browser_batch_plan"]["batch_command"])
        self.assertIn(
            "--target-filter browser-chrome-windows-11-x64",
            result["local_browser_batch_plan"]["validation_commands"][0],
        )
        self.assertTrue(result["local_browser_batch_plan"]["partial_evidence_only"])
        self.assertTrue(result["local_browser_batch_plan"]["remaining_matrix_targets_still_required"])
        self.assertIn("--preflight", result["preflight_command"])

    def test_release_evidence_preflight_requires_native_source_sync_before_network(self):
        tag = "v1.2.3"
        failed_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        failed_source_sync["surface_contract"] = {
            **failed_source_sync["surface_contract"],
            "ok": False,
            "issues": ["missing generated Rust parity artifact"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir) / "release-platform-evidence"
            output_dir = Path(temp_dir) / "runtime-evidence"
            evidence_dir.mkdir()
            with (
                patch.object(release_evidence, "_fetch_release", side_effect=AssertionError("network forbidden")),
                patch.object(release_evidence, "_load_json", return_value={"schema_version": 1}),
                patch.object(release_evidence, "_validate_matrix", return_value=([], [], [])),
                patch.object(release_evidence, "_source_tree_clean", return_value=True),
                patch.object(release_evidence, "audit_native_source_sync", return_value=failed_source_sync),
            ):
                result = release_evidence.preflight_release_evidence_inputs(
                    tag=tag,
                    owner="Yunushan",
                    repo="trading-bot",
                    matrix_path=Path("docs/release-platform-test-matrix.json"),
                    platform_evidence_dir=evidence_dir,
                    output_dir=output_dir,
                )

        self.assertFalse(result["ok"])
        self.assertFalse(result["network_access_attempted"])
        self.assertFalse(result["artifact_write_attempted"])
        self.assertFalse(result["native_source_sync_guard"]["ok"])
        self.assertFalse(result["native_source_sync_guard"]["surface_contract_ok"])
        self.assertIn(release_evidence.FAILED_SOURCE_SYNC_RELEASE_EVIDENCE_ISSUE, result["issues"])
        self.assertIn("missing generated Rust parity artifact", result["issues"])

    def test_release_evidence_preflight_blocks_dirty_source_without_network(self):
        tag = "v1.2.3"

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir) / "release-platform-evidence"
            output_dir = Path(temp_dir) / "runtime-evidence"
            evidence_dir.mkdir()
            with (
                patch.object(release_evidence, "_fetch_release", side_effect=AssertionError("network forbidden")),
                patch.object(release_evidence, "_load_json", return_value={"schema_version": 1}),
                patch.object(release_evidence, "_validate_matrix", return_value=([], [], [])),
                patch.object(release_evidence, "_source_tree_clean", return_value=False),
            ):
                result = release_evidence.preflight_release_evidence_inputs(
                    tag=tag,
                    owner="Yunushan",
                    repo="trading-bot",
                    matrix_path=Path("docs/release-platform-test-matrix.json"),
                    platform_evidence_dir=evidence_dir,
                    output_dir=output_dir,
                )

        self.assertFalse(result["ok"])
        self.assertFalse(result["network_access_attempted"])
        self.assertFalse(result["artifact_write_attempted"])
        self.assertFalse(result["source_tree_clean"])
        self.assertIn(
            release_evidence.DIRTY_SOURCE_RELEASE_EVIDENCE_ISSUE,
            result["issues"],
        )

    def test_release_evidence_browser_workflow_examples_use_supported_browser_commands(self):
        edge_target = {
            "id": "browser-edge-windows-11-x64",
            "kind": "browser",
            "browser": "edge",
            "runner_labels": ["self-hosted", "tb-browser", "edge-windows-11-x64"],
            "test_suites": ["browser-contract"],
        }
        firefox_target = {
            "id": "browser-firefox-windows-11-x64",
            "kind": "browser",
            "browser": "firefox",
            "runner_labels": ["self-hosted", "tb-browser", "firefox-windows-11-x64"],
            "test_suites": ["browser-contract"],
        }

        edge_plan = release_evidence._target_plan(edge_target)
        firefox_plan = release_evidence._target_plan(firefox_target)

        self.assertTrue(edge_plan["browser_contract_command_builtin"])
        self.assertEqual(
            "npm --prefix apps/web-dashboard run test:browser -- --browser=edge",
            edge_plan["browser_contract_command"],
        )
        self.assertNotIn("browser_test_command", edge_plan["required_workflow_inputs"])
        self.assertNotIn("browser_test_command", edge_plan["workflow_dispatch_example"])

        self.assertTrue(firefox_plan["browser_contract_command_builtin"])
        self.assertEqual(
            "npm --prefix apps/web-dashboard run test:browser -- --browser=firefox",
            firefox_plan["browser_contract_command"],
        )
        self.assertNotIn("browser_test_command", firefox_plan["required_workflow_inputs"])
        self.assertNotIn("browser_test_command", firefox_plan["workflow_dispatch_example"])

        batch_plan = release_evidence._workflow_dispatch_batch_plan([edge_target, firefox_target], limit=1)
        self.assertEqual(2, batch_plan["target_count"])
        self.assertEqual(["browser-edge-windows-11-x64", "browser-firefox-windows-11-x64"], batch_plan["target_ids"])
        self.assertEqual(1, batch_plan["command_count"])
        self.assertEqual(["browser-edge-windows-11-x64"], batch_plan["command_target_ids"])
        self.assertTrue(batch_plan["commands_truncated"])
        self.assertEqual(0, batch_plan["manual_input_target_count"])
        self.assertEqual([], batch_plan["manual_input_targets"])
        self.assertEqual("browser-edge-windows-11-x64", batch_plan["workflow_dispatch_inputs"][0]["target_id"])
        self.assertNotIn("browser_test_command", batch_plan["workflow_dispatch_inputs"][0])

    def test_readiness_audit_release_prerequisites_include_preflight_coverage(self):
        preflight_result = {
            "ok": False,
            "source_tree_clean": True,
            "release_asset_presence_verified": False,
            "release_asset_presence_requires_network": True,
            "release_evidence_target_count": 99,
            "platform_target_count": 70,
            "browser_target_count": 29,
            "present_platform_evidence_count": 1,
            "passed_platform_evidence_count": 0,
            "invalid_platform_evidence_count": 1,
            "unknown_platform_evidence_count": 1,
            "missing_platform_evidence_count": 98,
            "missing_platform_evidence_limit": 10,
            "missing_platform_evidence_truncated": True,
            "missing_platform_evidence_all": [
                "browser-chrome-windows-11-x64",
                "browser-edge-windows-11-x64",
            ],
            "missing_platform_evidence": ["browser-chrome-windows-11-x64"],
            "missing_platform_evidence_plan": [
                {
                    "target_id": "browser-chrome-windows-11-x64",
                    "probe_command": (
                        "python tools/run_release_platform_probe.py "
                        "--target-id browser-chrome-windows-11-x64 --require-clean-source "
                        "--require-native-source-sync "
                        "--output release-platform-evidence/browser-chrome-windows-11-x64.json"
                    ),
                    "target_validation_command": (
                        "python tools/check_release_platform_matrix.py --require-evidence "
                        "--require-current-commit --require-clean-source "
                        "--evidence-dir release-platform-evidence --target-filter browser-chrome-windows-11-x64"
                    ),
                    "workflow_dispatch_example": "gh workflow run release-platform-real-tests.yml",
                }
            ],
            "workflow_dispatch_batch_plan": {
                "workflow": "release-platform-real-tests.yml",
                "target_count": 98,
                "target_ids": [
                    "browser-chrome-windows-11-x64",
                    "browser-edge-windows-11-x64",
                ],
                "command_limit": 10,
                "command_count": 1,
                "command_target_ids": ["browser-chrome-windows-11-x64"],
                "commands": ["gh workflow run release-platform-real-tests.yml"],
                "workflow_dispatch_inputs": [
                    {
                        "target_id": "browser-chrome-windows-11-x64",
                        "runner_labels_json": "[]",
                    }
                ],
                "commands_truncated": True,
                "manual_input_target_count": 0,
                "manual_input_targets": [],
                "manual_input_targets_truncated": False,
                "validation_command": (
                    "python tools/check_release_platform_matrix.py --require-evidence "
                    "--require-current-commit --require-clean-source --evidence-dir release-platform-evidence"
                ),
                "aggregate_write_command": (
                    "python tools/write_rust_native_release_evidence.py --tag <tag> "
                    "--platform-evidence-dir release-platform-evidence"
                ),
            },
            "issues": ["missing release platform evidence for 98 of 99 target(s)"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "release-platform-evidence").mkdir()
            with (
                patch.dict(runtime_readiness.os.environ, {"TRADING_BOT_RELEASE_TAG": "v9.9.9"}, clear=True),
                patch.object(
                    runtime_readiness,
                    "preflight_release_evidence_inputs",
                    return_value=preflight_result,
                ) as preflight,
            ):
                result = runtime_readiness._release_evidence_prerequisites(root)

        self.assertEqual("v9.9.9", result["release_tag"])
        self.assertTrue(result["release_tag_configured"])
        self.assertFalse(result["release_platform_preflight_ok"])
        self.assertTrue(result["source_tree_clean"])
        self.assertFalse(result["release_asset_presence_verified"])
        self.assertTrue(result["release_asset_presence_requires_network"])
        self.assertEqual(99, result["release_evidence_target_count"])
        self.assertEqual(70, result["platform_target_count"])
        self.assertEqual(29, result["browser_target_count"])
        self.assertEqual(1, result["present_platform_evidence_count"])
        self.assertEqual(0, result["passed_platform_evidence_count"])
        self.assertEqual(1, result["invalid_platform_evidence_count"])
        self.assertEqual(1, result["unknown_platform_evidence_count"])
        self.assertEqual(98, result["missing_platform_evidence_count"])
        self.assertEqual(10, result["missing_platform_evidence_limit"])
        self.assertTrue(result["missing_platform_evidence_truncated"])
        self.assertEqual(
            ["browser-chrome-windows-11-x64", "browser-edge-windows-11-x64"],
            result["missing_platform_evidence_all"],
        )
        self.assertEqual(["browser-chrome-windows-11-x64"], result["missing_platform_evidence"])
        self.assertEqual("browser-chrome-windows-11-x64", result["missing_platform_evidence_plan"][0]["target_id"])
        self.assertIn("--require-clean-source", result["missing_platform_evidence_plan"][0]["probe_command"])
        self.assertIn("--require-native-source-sync", result["missing_platform_evidence_plan"][0]["probe_command"])
        self.assertIn(
            "--require-current-commit", result["missing_platform_evidence_plan"][0]["target_validation_command"]
        )
        self.assertIn(
            "--require-clean-source", result["missing_platform_evidence_plan"][0]["target_validation_command"]
        )
        self.assertEqual(98, result["workflow_dispatch_batch_plan"]["target_count"])
        self.assertEqual(
            ["browser-chrome-windows-11-x64"], result["workflow_dispatch_batch_plan"]["command_target_ids"]
        )
        self.assertTrue(result["workflow_dispatch_batch_plan"]["commands_truncated"])
        self.assertIn("--require-clean-source", result["workflow_dispatch_batch_plan"]["validation_command"])
        self.assertIn("98 of 99", result["release_platform_preflight_issues"][0])
        self.assertEqual("v9.9.9", preflight.call_args.kwargs["tag"])
        self.assertEqual(10, preflight.call_args.kwargs["missing_limit"])

    def test_readiness_audit_release_prerequisites_accept_full_missing_plan_limit(self):
        preflight_result = {
            "ok": False,
            "source_tree_clean": True,
            "release_asset_presence_verified": False,
            "release_asset_presence_requires_network": True,
            "release_evidence_target_count": 2,
            "platform_target_count": 2,
            "browser_target_count": 0,
            "present_platform_evidence_count": 0,
            "passed_platform_evidence_count": 0,
            "invalid_platform_evidence_count": 0,
            "unknown_platform_evidence_count": 0,
            "missing_platform_evidence_count": 2,
            "missing_platform_evidence_limit": 0,
            "missing_platform_evidence_truncated": False,
            "missing_platform_evidence_all": ["ubuntu-24_04-x64", "windows-11-x64"],
            "missing_platform_evidence": ["ubuntu-24_04-x64", "windows-11-x64"],
            "missing_platform_evidence_plan": [
                {"target_id": "ubuntu-24_04-x64"},
                {"target_id": "windows-11-x64"},
            ],
            "issues": ["missing release platform evidence for 2 of 2 target(s)"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(
                runtime_readiness,
                "preflight_release_evidence_inputs",
                return_value=preflight_result,
            ) as preflight:
                result = runtime_readiness._release_evidence_prerequisites(root, missing_limit=0)

        self.assertEqual(0, preflight.call_args.kwargs["missing_limit"])
        self.assertEqual(0, result["missing_platform_evidence_limit"])
        self.assertFalse(result["missing_platform_evidence_truncated"])
        self.assertEqual(["ubuntu-24_04-x64", "windows-11-x64"], result["missing_platform_evidence"])
        self.assertEqual(["ubuntu-24_04-x64", "windows-11-x64"], result["missing_platform_evidence_all"])
        self.assertEqual(
            ["ubuntu-24_04-x64", "windows-11-x64"],
            [row["target_id"] for row in result["missing_platform_evidence_plan"]],
        )

    def test_readiness_audit_passes_release_missing_limit_to_prerequisites(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": True,
                    "issues": [],
                    "artifact_status": [],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(runtime_readiness, "_live_smoke_prerequisites", return_value={}),
            patch.object(runtime_readiness, "local_recovery_generation_guard", return_value={"ok": True, "issues": []}),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": True, "issues": []},
            ) as release_prerequisites,
        ):
            runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
                release_missing_limit=0,
            )

        self.assertEqual(0, release_prerequisites.call_args.kwargs["missing_limit"])

    def test_readiness_audit_requires_native_source_sync(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": [],
                    "artifact_status": [],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": []}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value={"ok": False, "contract_hash": "stale-hash", "issues": ["generated contract is stale"]},
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["promotion_ready"])
        self.assertFalse(result["native_source_sync_ok"])
        self.assertEqual("stale-hash", result["native_source_sync_contract_hash"])
        self.assertEqual(
            [
                "generated contract is stale",
                "native source sync surface_contract is missing.",
            ],
            result["native_source_sync_issues"],
        )
        self.assertIn("native source sync: generated contract is stale", result["issues"])
        requirements = {row["id"]: row for row in result["promotion_requirements"]}
        self.assertEqual(result["promotion_requirement_count"], len(result["promotion_requirements"]))
        self.assertEqual(
            result["promotion_requirements_passed"],
            sum(1 for row in result["promotion_requirements"] if row["ok"]),
        )
        self.assertEqual("failed", requirements["native_source_sync"]["status"])
        self.assertEqual(
            [
                "generated contract is stale",
                "native source sync surface_contract is missing.",
            ],
            requirements["native_source_sync"]["issues"],
        )
        self.assertEqual("failed", requirements["required_runtime_evidence"]["status"])
        self.assertEqual("failed", requirements["runtime_ready_source_guard"]["status"])
        self.assertEqual("regenerate_python_owned_native_contracts", result["promotion_model"]["phase"])
        self.assertFalse(result["promotion_model"]["can_claim_runtime_complete"])
        self.assertIn("native_source_sync", result["promotion_model"]["failed_requirement_ids"])
        self.assertEqual("denied", result["source_sync_claim"]["status"])
        self.assertFalse(result["source_sync_claim"]["can_claim"])
        self.assertIn("native source sync: generated contract is stale", result["source_sync_claim"]["issues"])
        self.assertEqual("denied", result["native_source_sync"]["status"])
        self.assertFalse(result["native_source_sync"]["ok"])
        self.assertEqual("stale-hash", result["native_source_sync"]["contract_hash"])
        self.assertEqual(
            "artifacts/native-source-sync/native-source-sync-audit.json",
            result["native_source_sync"]["audit_output_path"],
        )
        self.assertEqual("native-source-sync-audit", result["native_source_sync"]["audit_artifact"])

    def test_readiness_audit_phase_requires_source_sync_surface_contract(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": [],
                    "artifact_status": [],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        native_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        native_source_sync.pop("surface_contract")

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(runtime_readiness, "audit_native_source_sync", return_value=native_source_sync),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        self.assertFalse(result["native_source_sync_ok"])
        self.assertEqual("regenerate_python_owned_native_contracts", result["promotion_model"]["phase"])
        self.assertIn("native_source_sync", result["promotion_model"]["failed_requirement_ids"])
        self.assertEqual("denied", result["native_source_sync"]["status"])
        self.assertFalse(result["native_source_sync"]["surface_contract_ok"])
        self.assertTrue(
            any(
                "native source sync surface_contract is missing." in issue
                for issue in result["native_source_sync"]["issues"]
            )
        )

    def test_source_sync_claim_requires_surface_contract(self):
        native_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        native_source_sync.pop("surface_contract")

        claim = runtime_readiness._source_sync_claim(
            source={"ok": True, "issues": []},
            native_source_sync=native_source_sync,
            python_runtime_readiness={
                "cpp_contract_parity": True,
                "rust_contract_parity": True,
            },
        )

        self.assertEqual("denied", claim["status"])
        self.assertFalse(claim["can_claim"])
        self.assertFalse(claim["surface_contract_ok"])
        self.assertIn(
            "native source sync: native source sync surface_contract is missing.",
            claim["issues"],
        )

    def test_promotion_requirement_requires_source_sync_surface_contract(self):
        native_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        native_source_sync.pop("surface_contract")

        requirements = runtime_readiness._promotion_requirements(
            source={"ok": True, "issues": []},
            native_source_sync=native_source_sync,
            declaration={"ok": True, "issues": []},
            evidence={"ok": True, "issues": []},
            evidence_complete=True,
            promotion_evidence_ok=True,
            current_commit_evidence={"issues": []},
            remaining_evidence_ids=[],
            runtime_ready=True,
            python_runtime_readiness={"ok": True, "issues": []},
            python_source_match_issues=[],
            declaration_source_match_issues=[],
        )

        rows = {row["id"]: row for row in requirements}
        self.assertEqual("failed", rows["native_source_sync"]["status"])
        self.assertIn(
            "native source sync surface_contract is missing.",
            rows["native_source_sync"]["issues"],
        )

    def test_runtime_evidence_policy_can_represent_promoted_state(self):
        manifest = json.loads((REPO_ROOT / "docs" / "rust-native-runtime-evidence.json").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "rust-native-runtime-evidence.json"

            manifest["policy"]["runtime_ready_flag"] = "rust_native_trading_runtime_ready() == true"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            promoted = runtime_evidence.validate(manifest_path, require_evidence=False)

            manifest["policy"]["runtime_ready_flag"] = "rust_native_trading_runtime_ready() == maybe"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            invalid = runtime_evidence.validate(manifest_path, require_evidence=False)

        self.assertTrue(promoted["ok"], promoted["issues"])
        self.assertTrue(promoted["runtime_ready_policy_state"])
        self.assertFalse(invalid["ok"])
        self.assertTrue(any("policy.runtime_ready_flag must be" in issue for issue in invalid["issues"]))

    def test_readiness_audit_required_runtime_ids_follow_manifest_contract(self):
        self.assertEqual(
            set(runtime_evidence.REQUIRED_REQUIREMENTS),
            set(runtime_readiness._promotion_required_runtime_ids()),
        )
        self.assertEqual([], runtime_readiness._runtime_evidence_id_contract_issues())

    def test_readiness_audit_reports_required_runtime_id_contract_drift(self):
        with patch.object(
            runtime_readiness,
            "EVIDENCE_COLLECTION_ORDER",
            (
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
            ),
        ):
            issues = runtime_readiness._runtime_evidence_id_contract_issues()
            requirements = runtime_readiness._promotion_requirements(
                source={"ok": True, "issues": []},
                native_source_sync=_valid_source_sync_audit_payload("fresh-hash"),
                declaration={"ok": True, "issues": []},
                evidence={"ok": False, "issues": []},
                evidence_complete=False,
                promotion_evidence_ok=False,
                current_commit_evidence={"issues": []},
                remaining_evidence_ids=["rust-native-release-platform-evidence"],
                runtime_ready=False,
                python_runtime_readiness={"ok": True, "issues": []},
                python_source_match_issues=[],
                declaration_source_match_issues=[],
            )

        rows = {row["id"]: row for row in requirements}
        self.assertTrue(
            any("rust-native-release-platform-evidence" in issue for issue in issues),
            issues,
        )
        self.assertEqual("failed", rows["runtime_evidence_id_contract"]["status"])
        self.assertTrue(
            any(
                "rust-native-release-platform-evidence" in issue
                for issue in rows["runtime_evidence_id_contract"]["issues"]
            )
        )

    def test_readiness_audit_fails_when_manifest_policy_disagrees_with_source_guard(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": [],
                    "artifact_status": [],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": True}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["runtime_ready_policy_matches_source"])
        self.assertTrue(result["runtime_ready_policy_state"])
        self.assertIn(
            "policy.runtime_ready_flag does not match rust_native_trading_runtime_ready() source state",
            result["issues"],
        )
        requirements = {row["id"]: row for row in result["promotion_requirements"]}
        self.assertEqual("failed", requirements["evidence_declaration"]["status"])
        self.assertTrue(any("does not match" in issue for issue in requirements["evidence_declaration"]["issues"]))
        self.assertEqual(
            "align_manifest_policy_with_runtime_ready_source_guard",
            result["promotion_model"]["phase"],
        )

    def test_readiness_audit_fails_when_python_runtime_source_disagrees_with_rust_guard(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": True,
                    "issues": [],
                    "artifact_status": [
                        {"id": "rust-native-live-market-data-smoke", "ok": True},
                        {"id": "rust-native-live-account-read-smoke", "ok": True},
                        {"id": "rust-native-live-stream-recovery", "ok": True},
                        {"id": "rust-native-order-guard-recovery", "ok": True},
                        {"id": "rust-native-release-platform-evidence", "ok": True},
                    ],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": True}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": True, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(
                runtime_readiness,
                "native_python_source_contract_summary",
                return_value={
                    "cpp_contract_parity": True,
                    "rust_contract_parity": True,
                    "cpp_standalone_runtime_ready": False,
                    "rust_standalone_runtime_ready": False,
                    "rust_full_parity": False,
                },
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": True},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=True,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["promotion_ready"])
        self.assertFalse(result["runtime_ready_python_source_matches_rust_guard"])
        self.assertFalse(result["python_rust_standalone_runtime_ready"])
        self.assertIn(
            "Languages/Python/app/native_parity.py rust_standalone_runtime_ready does not match "
            "rust_native_trading_runtime_ready() source state",
            result["issues"],
        )
        requirements = {row["id"]: row for row in result["promotion_requirements"]}
        self.assertEqual("failed", requirements["python_runtime_readiness_source"]["status"])
        self.assertEqual(
            "align_rust_runtime_guard_with_python_source_of_truth",
            result["promotion_model"]["phase"],
        )
        self.assertIn(
            "python_runtime_readiness_source",
            result["promotion_model"]["failed_requirement_ids"],
        )

    def test_readiness_audit_promotion_checklist_passes_only_when_all_gates_pass(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": True,
                    "issues": [],
                    "artifact_status": [
                        {"id": "rust-native-live-market-data-smoke", "ok": True},
                        {"id": "rust-native-live-account-read-smoke", "ok": True},
                        {"id": "rust-native-live-stream-recovery", "ok": True},
                        {"id": "rust-native-order-guard-recovery", "ok": True},
                        {"id": "rust-native-release-platform-evidence", "ok": True},
                    ],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": True}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": True, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(
                runtime_readiness,
                "native_python_source_contract_summary",
                return_value={
                    "cpp_contract_parity": True,
                    "rust_contract_parity": True,
                    "cpp_standalone_runtime_ready": False,
                    "rust_standalone_runtime_ready": True,
                    "rust_full_parity": True,
                },
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": True},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=True,
            )

        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["promotion_ready"])
        self.assertEqual(result["promotion_requirement_count"], result["promotion_requirements_passed"])
        self.assertTrue(all(row["required"] for row in result["promotion_requirements"]))
        self.assertTrue(all(row["ok"] for row in result["promotion_requirements"]))
        self.assertTrue(all(row["status"] == "passed" for row in result["promotion_requirements"]))
        self.assertEqual([], result["remaining_evidence_ids"])
        self.assertEqual("runtime_complete", result["promotion_model"]["phase"])
        self.assertTrue(result["promotion_model"]["can_claim_runtime_complete"])
        self.assertEqual([], result["promotion_model"]["failed_requirement_ids"])
        self.assertEqual("approved", result["completion_claim"]["status"])
        self.assertTrue(result["completion_claim"]["can_claim"])
        self.assertEqual([], result["completion_claim"]["failed_requirement_ids"])
        self.assertEqual([], result["completion_claim"]["remaining_evidence_ids"])
        self.assertEqual([], result["completion_claim"]["missing_inputs"]["missing_prerequisites"])
        self.assertEqual([], result["completion_claim"]["missing_inputs"]["required_environment"])
        self.assertEqual([], result["completion_claim"]["missing_inputs"]["required_inputs"])
        self.assertEqual([], result["completion_claim"]["missing_inputs"]["evidence"])
        self.assertEqual([], result["promotion_next_action_plan"])
        self.assertEqual([], result["next_actions"])
        self.assertEqual("fresh-hash", result["completion_claim"]["native_source_sync_contract_hash"])
        self.assertEqual("approved", result["source_sync_claim"]["status"])
        self.assertTrue(result["source_sync_claim"]["can_claim"])
        self.assertEqual("fresh-hash", result["source_sync_claim"]["native_source_sync_contract_hash"])
        self.assertTrue(result["source_sync_claim"]["surface_contract_ok"])
        self.assertEqual("approved", result["native_source_sync"]["status"])
        self.assertTrue(result["native_source_sync"]["ok"])
        self.assertEqual("fresh-hash", result["native_source_sync"]["contract_hash"])
        self.assertTrue(result["native_source_sync"]["surface_contract_ok"])
        self.assertEqual("native-source-sync-audit", result["native_source_sync"]["audit_artifact"])
        self.assertEqual(
            list(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            result["source_sync_claim"]["actual_consumer_surface_names"],
        )
        self.assertEqual(
            len(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            result["source_sync_claim"]["consumer_surface_count"],
        )
        self.assertIn(
            "cpp_chart_uses_python_source_surface",
            result["source_sync_claim"]["consumer_surface_names"],
        )
        self.assertEqual(0, len(result["source_sync_claim"]["issues"]))
        self.assertTrue(result["runtime_ready_python_source_matches_rust_guard"])
        self.assertTrue(result["python_rust_standalone_runtime_ready"])
        self.assertIn("candidate source commit", " ".join(result["promotion_model"]["promotion_sequence"]))

    def test_readiness_audit_exposes_reachable_promotion_model_before_evidence_is_complete(self):
        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": ["missing evidence artifact: rust-native-live-account-read-smoke.json"],
                    "artifact_status": [
                        {"id": "rust-native-live-market-data-smoke", "ok": True},
                        {"id": "rust-native-live-account-read-smoke", "ok": False},
                        {"id": "rust-native-release-platform-evidence", "ok": False},
                    ],
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "current_source_tree_dirty_paths": [],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        model = result["promotion_model"]
        claim = result["completion_claim"]
        source_claim = result["source_sync_claim"]
        expected_workflow_source_sync_audit = {
            "step": "Audit native source sync",
            "command": (
                "python tools/audit_native_source_sync.py --json "
                "--output artifacts/native-source-sync/native-source-sync-audit.json"
            ),
            "output_path": "artifacts/native-source-sync/native-source-sync-audit.json",
            "github_workflow_artifact": "native-source-sync-audit",
            "required_before_evidence_collection": True,
            "python_source_of_truth": "Languages/Python/app/native_parity.py",
        }
        self.assertEqual("approved", source_claim["status"])
        self.assertTrue(source_claim["can_claim"])
        self.assertEqual("fresh-hash", source_claim["native_source_sync_contract_hash"])
        self.assertTrue(source_claim["surface_contract_ok"])
        self.assertEqual(
            list(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            source_claim["actual_consumer_surface_names"],
        )
        self.assertEqual(
            len(evidence_importer.SOURCE_SYNC_REQUIRED_CONSUMER_SURFACES),
            source_claim["consumer_surface_count"],
        )
        self.assertIn("cpp_dashboard_uses_python_source_surface", source_claim["consumer_surface_names"])
        self.assertEqual("collect_required_runtime_evidence", model["phase"])
        self.assertFalse(model["can_claim_runtime_complete"])
        self.assertEqual("denied", claim["status"])
        self.assertFalse(claim["can_claim"])
        self.assertEqual("collect_required_runtime_evidence", claim["phase"])
        self.assertEqual(
            [
                "required_runtime_evidence",
                "current_commit_clean_source_evidence",
                "runtime_ready_source_guard",
            ],
            model["failed_requirement_ids"],
        )
        self.assertEqual(model["failed_requirement_ids"], claim["failed_requirement_ids"])
        self.assertEqual(
            ["rust-native-live-account-read-smoke", "rust-native-release-platform-evidence"],
            claim["remaining_evidence_ids"],
        )
        self.assertTrue(any("required runtime evidence artifact" in reason for reason in claim["denied_reasons"]))
        self.assertIn("current git rev-parse HEAD", model["evidence_commit_binding"])
        self.assertEqual(
            [
                "artifacts/rust-native-runtime-evidence",
                "artifacts/native-source-sync",
                "release-platform-evidence",
            ],
            model["clean_source_scope"]["ignored_paths"],
        )
        self.assertEqual([], model["clean_source_scope"]["dirty_paths"])
        self.assertEqual([], model["clean_source_scope"]["untracked_paths"])
        self.assertTrue(model["clean_source_scope"]["requires_no_untracked_promotion_scope_files"])
        self.assertIn(
            "gh workflow run rust-native-promotion-audit.yml",
            model["github_promotion_audit_workflow_command"],
        )
        self.assertEqual("rust-native-promotion-audit.yml", model["github_promotion_audit_workflow"])
        self.assertEqual(
            {
                "live_smoke_run_id": "<live-smoke-actions-run-id>",
                "release_evidence_run_id": "<release-evidence-actions-run-id>",
            },
            model["github_promotion_audit_workflow_inputs"],
        )
        self.assertEqual(
            "rust-native-promotion-evidence-plan",
            model["github_promotion_audit_workflow_plan_artifact"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            model["github_promotion_audit_source_sync_audit"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
                "rust-native-release-platform-evidence",
            ],
            model["promotion_required_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-release-platform-evidence",
            ],
            model["promotion_external_import_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
            ],
            model["promotion_local_recovery_runtime_ids"],
        )
        self.assertEqual(
            model["github_promotion_audit_workflow_inputs"],
            claim["github_promotion_audit_workflow_inputs"],
        )
        self.assertEqual(
            model["github_promotion_audit_workflow_plan_artifact"],
            claim["github_promotion_audit_workflow_plan_artifact"],
        )
        self.assertEqual(
            model["github_promotion_audit_source_sync_audit"],
            claim["github_promotion_audit_source_sync_audit"],
        )
        self.assertEqual(
            model["promotion_required_runtime_ids"],
            claim["promotion_required_runtime_ids"],
        )
        self.assertEqual(
            model["promotion_external_import_runtime_ids"],
            claim["promotion_external_import_runtime_ids"],
        )
        self.assertEqual(
            model["promotion_local_recovery_runtime_ids"],
            claim["promotion_local_recovery_runtime_ids"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-live-market-data-smoke",
            model["evidence_import_command"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-live-account-read-smoke",
            model["evidence_import_command"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-release-platform-evidence",
            model["evidence_import_command"],
        )
        self.assertIn("artifacts/native-source-sync", model["evidence_import_command"])
        self.assertIn("--require-native-source-sync-audit", model["evidence_import_command"])
        self.assertTrue(any("rust-native-promotion-audit.yml" in action for action in result["next_actions"]))
        action_plan = {row["id"]: row for row in result["promotion_next_action_plan"]}
        self.assertIn("create_clean_candidate_source_revision", action_plan)
        self.assertEqual(
            ["current_commit_clean_source_evidence"],
            action_plan["create_clean_candidate_source_revision"]["requirement_ids"],
        )
        self.assertIn("clean_source_scope", action_plan["create_clean_candidate_source_revision"]["details"])
        self.assertIn("collect_rust_native_live_account_smoke", action_plan)
        self.assertEqual(
            ["rust-native-live-market-data-smoke", "rust-native-live-account-read-smoke"],
            action_plan["collect_rust_native_live_account_smoke"]["evidence_ids"],
        )
        self.assertIn(
            "required_runtime_evidence",
            action_plan["collect_rust_native_live_account_smoke"]["requirement_ids"],
        )
        account_details = action_plan["collect_rust_native_live_account_smoke"]["details"]
        self.assertTrue(account_details["requires_credentials"])
        self.assertFalse(account_details["order_submission_attempted"])
        self.assertEqual(2, account_details["evidence_row_count"])
        self.assertEqual(
            ["rust-native-live-market-data-smoke", "rust-native-live-account-read-smoke"],
            [row["id"] for row in account_details["evidence_rows"]],
        )
        self.assertIn(
            "--require-runtime-id rust-native-live-account-read-smoke",
            account_details["evidence_rows"][1]["import_command"],
        )
        self.assertIn(
            "--require-current-commit",
            account_details["evidence_rows"][1]["validation_command"],
        )
        self.assertEqual(expected_workflow_source_sync_audit, account_details["workflow_source_sync_audit"])
        self.assertEqual(
            expected_workflow_source_sync_audit,
            account_details["evidence_rows"][1]["details"]["workflow_source_sync_audit"],
        )
        self.assertIn("collect_rust_native_release_platform_evidence", action_plan)
        self.assertEqual(
            ["rust-native-release-platform-evidence"],
            action_plan["collect_rust_native_release_platform_evidence"]["evidence_ids"],
        )
        release_details = action_plan["collect_rust_native_release_platform_evidence"]["details"]
        self.assertEqual(1, release_details["evidence_row_count"])
        self.assertEqual(
            "rust-native-release-platform-evidence",
            release_details["evidence_rows"][0]["id"],
        )
        self.assertIn("Rust release assets", release_details["evidence_rows"][0]["required_inputs"])
        self.assertIn(
            "--require-runtime-id rust-native-release-platform-evidence",
            release_details["evidence_rows"][0]["import_command"],
        )
        self.assertEqual(expected_workflow_source_sync_audit, release_details["workflow_source_sync_audit"])
        self.assertEqual(
            expected_workflow_source_sync_audit,
            release_details["evidence_rows"][0]["details"]["workflow_source_sync_audit"],
        )
        self.assertIn("run_rust_native_promotion_audit_workflow", action_plan)
        self.assertIn(
            "current_commit_clean_source_evidence",
            action_plan["run_rust_native_promotion_audit_workflow"]["requirement_ids"],
        )
        promotion_details = action_plan["run_rust_native_promotion_audit_workflow"]["details"]
        self.assertEqual("rust-native-promotion-audit.yml", promotion_details["github_workflow"])
        self.assertEqual(
            {
                "live_smoke_run_id": "<live-smoke-actions-run-id>",
                "release_evidence_run_id": "<release-evidence-actions-run-id>",
            },
            promotion_details["github_workflow_inputs"],
        )
        self.assertEqual(
            "rust-native-promotion-evidence-plan",
            promotion_details["github_workflow_plan_artifact"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            promotion_details["workflow_source_sync_audit"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
                "rust-native-release-platform-evidence",
            ],
            promotion_details["required_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-release-platform-evidence",
            ],
            promotion_details["external_import_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
            ],
            promotion_details["local_recovery_runtime_ids"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-release-platform-evidence",
            promotion_details["evidence_import_command"],
        )
        self.assertIn("--require-native-source-sync-audit", promotion_details["evidence_import_command"])
        self.assertIn("promote_runtime_ready_source_guard", action_plan)
        self.assertEqual(
            ["runtime_ready_source_guard"],
            action_plan["promote_runtime_ready_source_guard"]["requirement_ids"],
        )
        self.assertTrue(any("clean candidate source revision" in action for action in result["next_actions"]))
        self.assertTrue(
            any("Keep rust_native_trading_runtime_ready() false" in action for action in result["next_actions"])
        )
        self.assertTrue(
            any(
                "--require-runtime-id rust-native-live-account-read-smoke" in action
                for action in result["next_actions"]
            )
        )
        self.assertTrue(
            any(
                "--require-runtime-id rust-native-release-platform-evidence" in action
                for action in result["next_actions"]
            )
        )
        self.assertIn("--require-current-commit", model["evidence_import_command"])

    def test_completion_missing_inputs_summarizes_remaining_evidence_inputs(self):
        summary = runtime_readiness._completion_missing_inputs(
            remaining_evidence_ids=[
                "rust-native-live-account-read-smoke",
                "rust-native-release-platform-evidence",
            ],
            evidence_collection_plan=[
                {
                    "id": "rust-native-live-account-read-smoke",
                    "status": "missing_or_failing",
                    "ready_to_collect": False,
                    "required_environment": [
                        "TRADING_BOT_RUST_LIVE_SMOKE=1",
                        "BINANCE_API_KEY",
                        "BINANCE_API_SECRET",
                    ],
                    "required_inputs": [],
                    "details": {
                        "missing_prerequisites": [
                            "clean source tree",
                            "BINANCE_API_KEY",
                            "BINANCE_API_SECRET",
                        ],
                        "github_workflow_inputs": {
                            "binance_testnet": "true",
                            "symbol": "BTCUSDT",
                            "interval": "1m",
                        },
                        "expected_artifacts": [
                            "rust-native-live-market-data-smoke.json",
                            "rust-native-live-account-read-smoke.json",
                        ],
                        "github_workflow_artifact": "rust-native-live-smoke-evidence",
                        "github_workflow_plan_artifact": "rust-native-live-smoke-evidence-plan",
                        "github_workflow_requires_secrets": ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
                    },
                },
                {
                    "id": "rust-native-release-platform-evidence",
                    "status": "missing_or_failing",
                    "ready_to_collect": False,
                    "required_environment": ["TRADING_BOT_RELEASE_TAG", "GITHUB_TOKEN or GH_TOKEN"],
                    "required_inputs": [
                        "Rust release assets",
                        "passed release-platform-evidence JSON for every target",
                    ],
                    "details": {
                        "missing_platform_evidence_count": 97,
                        "release_evidence_target_count": 99,
                        "platform_target_count": 70,
                        "browser_target_count": 29,
                        "missing_platform_evidence_truncated": True,
                        "local_browser_batch_plan": {"target_count": 2},
                        "workflow_dispatch_batch_plan": {
                            "target_count": 97,
                            "command_count": 10,
                            "command_limit": 10,
                            "command_target_ids": [
                                "windows-11-x64",
                                "browser-chrome-windows-11-x64",
                            ],
                            "commands_truncated": True,
                            "manual_input_target_count": 4,
                            "manual_input_targets_truncated": True,
                            "artifact_name_pattern": "release-platform-evidence-<target_id>",
                        },
                    },
                },
            ],
        )

        self.assertEqual(
            ["clean source tree", "BINANCE_API_KEY", "BINANCE_API_SECRET"],
            summary["missing_prerequisites"],
        )
        self.assertEqual(
            [
                "TRADING_BOT_RUST_LIVE_SMOKE=1",
                "BINANCE_API_KEY",
                "BINANCE_API_SECRET",
                "TRADING_BOT_RELEASE_TAG",
                "GITHUB_TOKEN or GH_TOKEN",
            ],
            summary["required_environment"],
        )
        self.assertEqual(
            ["Rust release assets", "passed release-platform-evidence JSON for every target"],
            summary["required_inputs"],
        )
        account_summary = summary["evidence"][0]
        self.assertEqual("rust-native-live-account-read-smoke", account_summary["evidence_id"])
        self.assertEqual(
            {"binance_testnet": "true", "symbol": "BTCUSDT", "interval": "1m"},
            account_summary["github_workflow_inputs"],
        )
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json", "rust-native-live-account-read-smoke.json"],
            account_summary["expected_artifacts"],
        )
        self.assertEqual("rust-native-live-smoke-evidence", account_summary["github_workflow_artifact"])
        self.assertEqual("rust-native-live-smoke-evidence-plan", account_summary["github_workflow_plan_artifact"])
        self.assertEqual(
            ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
            account_summary["github_workflow_requires_secrets"],
        )
        release_summary = summary["evidence"][1]
        self.assertEqual("rust-native-release-platform-evidence", release_summary["evidence_id"])
        self.assertEqual(97, release_summary["missing_platform_evidence_count"])
        self.assertEqual(99, release_summary["release_evidence_target_count"])
        self.assertEqual(70, release_summary["platform_target_count"])
        self.assertEqual(29, release_summary["browser_target_count"])
        self.assertEqual(2, release_summary["local_browser_batch_target_count"])
        self.assertEqual(97, release_summary["workflow_dispatch_batch_target_count"])
        self.assertEqual(10, release_summary["workflow_dispatch_batch_command_count"])
        self.assertEqual(10, release_summary["workflow_dispatch_batch_command_limit"])
        self.assertEqual(
            ["windows-11-x64", "browser-chrome-windows-11-x64"],
            release_summary["workflow_dispatch_batch_command_target_ids"],
        )
        self.assertTrue(release_summary["workflow_dispatch_batch_commands_truncated"])
        self.assertEqual(4, release_summary["workflow_dispatch_batch_manual_input_target_count"])
        self.assertTrue(release_summary["workflow_dispatch_batch_manual_input_targets_truncated"])
        self.assertEqual(
            "release-platform-evidence-<target_id>",
            release_summary["workflow_dispatch_batch_artifact_name_pattern"],
        )

    def test_promotion_action_plan_links_dirty_source_dependency_to_evidence_actions(self):
        promotion_model = {
            "failed_requirement_ids": [
                "required_runtime_evidence",
                "current_commit_clean_source_evidence",
                "runtime_ready_source_guard",
            ],
            "clean_source_scope": {
                "dirty_paths": ["tools/audit_rust_native_runtime_readiness.py"],
                "untracked_paths": [],
            },
        }
        evidence_collection_plan = [
            {
                "id": "rust-native-live-account-read-smoke",
                "status": "missing_or_failing",
                "ready_to_collect": False,
                "details": {"missing_prerequisites": ["clean source tree", "BINANCE_API_KEY"]},
                "issues": ["missing evidence artifact: rust-native-live-account-read-smoke.json"],
            },
            {
                "id": "rust-native-release-platform-evidence",
                "status": "missing_or_failing",
                "ready_to_collect": False,
                "details": {"missing_prerequisites": ["clean source tree"]},
                "issues": ["missing evidence artifact: rust-native-release-platform-evidence.json"],
            },
        ]

        plan = runtime_readiness._next_action_plan(
            ["rust-native-live-account-read-smoke", "rust-native-release-platform-evidence"],
            promotion_model,
            evidence_collection_plan,
        )

        action_plan = {row["id"]: row for row in plan}
        self.assertEqual([], action_plan["create_clean_candidate_source_revision"]["depends_on_action_ids"])
        self.assertIn(
            "create_clean_candidate_source_revision",
            action_plan["collect_rust_native_live_account_smoke"]["depends_on_action_ids"],
        )
        self.assertIn(
            "create_clean_candidate_source_revision",
            action_plan["collect_rust_native_release_platform_evidence"]["depends_on_action_ids"],
        )
        self.assertIn(
            "create_clean_candidate_source_revision",
            action_plan["run_rust_native_promotion_audit_workflow"]["depends_on_action_ids"],
        )
        self.assertIn(
            "rust-native-live-account-read-smoke: clean source tree",
            action_plan["collect_rust_native_live_account_smoke"]["blocked_by"],
        )
        self.assertFalse(action_plan["collect_rust_native_live_account_smoke"]["ready_to_run"])

    def test_promotion_action_plan_uses_collection_row_live_smoke_commands(self):
        plan = runtime_readiness._next_action_plan(
            ["rust-native-live-market-data-smoke", "rust-native-live-account-read-smoke"],
            {"failed_requirement_ids": ["required_runtime_evidence"], "clean_source_scope": {}},
            [
                {
                    "id": "rust-native-live-market-data-smoke",
                    "status": "missing_or_failing",
                    "ready_to_collect": True,
                    "local_preflight_command": "configured market preflight",
                    "local_command": "configured market command",
                    "github_workflow": "configured market workflow",
                    "details": {},
                    "issues": [],
                },
                {
                    "id": "rust-native-live-account-read-smoke",
                    "status": "missing_or_failing",
                    "ready_to_collect": True,
                    "local_preflight_command": "configured account preflight",
                    "local_command": "configured account command",
                    "github_workflow": "configured account workflow",
                    "details": {
                        "github_workflow_inputs": {
                            "binance_testnet": "false",
                            "symbol": "ETHUSDT",
                            "interval": "5m",
                        },
                        "expected_artifacts": [
                            "rust-native-live-market-data-smoke.json",
                            "rust-native-live-account-read-smoke.json",
                        ],
                    },
                    "issues": [],
                },
            ],
        )

        action_plan = {row["id"]: row for row in plan}
        market_action = action_plan["collect_rust_native_live_market_smoke"]
        account_action = action_plan["collect_rust_native_live_account_smoke"]
        self.assertEqual(
            ["configured market preflight", "configured market command"],
            market_action["commands"],
        )
        self.assertEqual("configured market workflow", market_action["github_workflow"])
        self.assertEqual(
            [
                "configured account preflight",
                "configured account command",
                (
                    "python tools/import_rust_native_evidence_artifacts.py <artifact.zip-or-dir> "
                    "artifacts/native-source-sync --apply --require-current-commit --require-clean-source "
                    "--require-native-source-sync-audit "
                    "--require-runtime-id rust-native-live-market-data-smoke "
                    "--require-runtime-id rust-native-live-account-read-smoke"
                ),
            ],
            account_action["commands"],
        )
        self.assertEqual("configured account workflow", account_action["github_workflow"])
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            account_action["details"]["github_workflow_inputs"],
        )

    def test_promotion_clean_source_check_ignores_only_canonical_evidence_dirs(self):
        captured_commands: list[list[str]] = []

        def _run_stub(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch.object(runtime_evidence.subprocess, "run", side_effect=_run_stub):
            clean = runtime_evidence._current_source_tree_clean()

        self.assertTrue(clean)
        self.assertEqual(2, len(captured_commands))
        self.assertIn("--untracked-files=no", captured_commands[0])
        self.assertIn("--untracked-files=all", captured_commands[1])
        for command in captured_commands:
            self.assertIn(":(exclude)artifacts/rust-native-runtime-evidence", command)
            self.assertIn(":(exclude)artifacts/native-source-sync", command)
            self.assertIn(":(exclude)release-platform-evidence", command)
            self.assertIn(".", command)

    def test_release_platform_clean_source_check_ignores_canonical_evidence_dirs(self):
        captured_commands: list[list[str]] = []

        def _run_stub(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with patch.object(release_platform_matrix.subprocess, "run", side_effect=_run_stub):
            clean = release_platform_matrix._current_source_tree_clean()

        self.assertTrue(clean)
        self.assertEqual(2, len(captured_commands))
        self.assertIn("--untracked-files=no", captured_commands[0])
        self.assertIn("--untracked-files=all", captured_commands[1])
        for command in captured_commands:
            self.assertIn(":(exclude)artifacts/rust-native-runtime-evidence", command)
            self.assertIn(":(exclude)artifacts/native-source-sync", command)
            self.assertIn(":(exclude)release-platform-evidence", command)
            self.assertIn(".", command)

    def test_release_evidence_writers_stamp_source_clean_with_promotion_scope(self):
        for module in (release_platform_probe, release_evidence):
            with self.subTest(module=module.__name__):
                captured_commands: list[list[str]] = []

                def _run_stub(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                    captured_commands.append(command)
                    stdout = "" if len(captured_commands) == 1 else "?? tools/new-release-probe.py\n"
                    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

                with patch.object(module.subprocess, "run", side_effect=_run_stub):
                    clean = module._source_tree_clean()

                self.assertFalse(clean)
                self.assertEqual(2, len(captured_commands))
                self.assertIn("--untracked-files=no", captured_commands[0])
                self.assertIn("--untracked-files=all", captured_commands[1])
                for command in captured_commands:
                    self.assertIn(":(exclude)artifacts/rust-native-runtime-evidence", command)
                    self.assertIn(":(exclude)artifacts/native-source-sync", command)
                    self.assertIn(":(exclude)release-platform-evidence", command)
                    self.assertIn(".", command)

    def test_promotion_clean_source_reports_dirty_tracked_paths(self):
        dirty_output = (
            " M tools/audit_rust_native_runtime_readiness.py\n"
            "R  old/name.py -> Languages/Python/tests/test_rust_native_release_evidence.py\n"
        )
        parsed_paths = runtime_evidence._dirty_paths_from_porcelain(dirty_output)
        self.assertEqual(
            [
                "tools/audit_rust_native_runtime_readiness.py",
                "Languages/Python/tests/test_rust_native_release_evidence.py",
            ],
            parsed_paths,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=False),
                patch.object(runtime_evidence, "_current_source_tree_dirty_paths", return_value=parsed_paths),
                patch.object(runtime_evidence, "_current_source_tree_untracked_paths", return_value=[]),
            ):
                result = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_clean_source=True,
                    evidence_dir_override=Path(temp_dir),
                    requirement_ids={"rust-native-live-market-data-smoke"},
                )

        self.assertFalse(result["ok"])
        self.assertEqual(parsed_paths, result["current_source_tree_dirty_paths"])
        self.assertTrue(
            any("dirty paths: tools/audit_rust_native_runtime_readiness.py" in issue for issue in result["issues"])
        )

    def test_promotion_clean_source_reports_untracked_source_paths(self):
        untracked_output = (
            "?? tools/import_rust_native_evidence_artifacts.py\n?? Languages/Python/app/native_new_surface.py\n"
        )
        parsed_paths = runtime_evidence._untracked_paths_from_porcelain(untracked_output)
        self.assertEqual(
            [
                "tools/import_rust_native_evidence_artifacts.py",
                "Languages/Python/app/native_new_surface.py",
            ],
            parsed_paths,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=False),
                patch.object(runtime_evidence, "_current_source_tree_dirty_paths", return_value=[]),
                patch.object(runtime_evidence, "_current_source_tree_untracked_paths", return_value=parsed_paths),
            ):
                result = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_clean_source=True,
                    evidence_dir_override=Path(temp_dir),
                    requirement_ids={"rust-native-live-market-data-smoke"},
                )

        self.assertFalse(result["ok"])
        self.assertEqual(parsed_paths, result["current_source_tree_untracked_paths"])
        self.assertTrue(
            any(
                "untracked paths: tools/import_rust_native_evidence_artifacts.py" in issue for issue in result["issues"]
            )
        )

    def test_readiness_audit_surfaces_dirty_paths_in_promotion_model(self):
        dirty_paths = ["tools/audit_rust_native_runtime_readiness.py"]

        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": [
                        "current tracked source tree must be clean for promotion evidence validation",
                        "current promotion source tree must not contain untracked source/tool files; "
                        "untracked paths: tools/import_rust_native_evidence_artifacts.py",
                    ],
                    "artifact_status": [],
                    "current_commit": "abc123",
                    "current_source_tree_clean": False,
                    "current_source_tree_dirty_paths": dirty_paths,
                    "current_source_tree_untracked_paths": ["tools/import_rust_native_evidence_artifacts.py"],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        self.assertEqual(dirty_paths, result["current_source_tree_dirty_paths"])
        self.assertEqual(
            ["tools/import_rust_native_evidence_artifacts.py"],
            result["current_source_tree_untracked_paths"],
        )
        self.assertEqual(dirty_paths, result["promotion_model"]["clean_source_scope"]["dirty_paths"])
        self.assertEqual(
            ["tools/import_rust_native_evidence_artifacts.py"],
            result["promotion_model"]["clean_source_scope"]["untracked_paths"],
        )
        requirements = {row["id"]: row for row in result["promotion_requirements"]}
        clean_source_issues = requirements["current_commit_clean_source_evidence"]["issues"]
        self.assertTrue(
            any("required runtime evidence must pass before current-commit" in issue for issue in clean_source_issues)
        )
        self.assertTrue(any("current tracked source tree must be clean" in issue for issue in clean_source_issues))
        self.assertTrue(
            any(
                "untracked paths: tools/import_rust_native_evidence_artifacts.py" in issue
                for issue in clean_source_issues
            )
        )
        self.assertEqual(
            [
                "current tracked source tree must be clean for promotion evidence validation",
                "current promotion source tree must not contain untracked source/tool files; "
                "untracked paths: tools/import_rust_native_evidence_artifacts.py",
            ],
            result["promotion_evidence_issues"],
        )

    def test_readiness_audit_emits_structured_evidence_collection_plan(self):
        artifact_status = [
            {
                "id": "rust-native-live-market-data-smoke",
                "category": "live_smoke",
                "ok": True,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json",
                "issues": [],
            },
            {
                "id": "rust-native-live-account-read-smoke",
                "category": "live_smoke",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-account-read-smoke.json",
                "issues": ["missing evidence artifact: rust-native-live-account-read-smoke.json"],
            },
            {
                "id": "rust-native-live-stream-recovery",
                "category": "local_recovery",
                "ok": True,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                "issues": [],
            },
            {
                "id": "rust-native-order-guard-recovery",
                "category": "local_recovery",
                "ok": True,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                "issues": [],
            },
            {
                "id": "rust-native-release-platform-evidence",
                "category": "release_platform",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-release-platform-evidence.json",
                "issues": ["missing evidence artifact: rust-native-release-platform-evidence.json"],
            },
        ]

        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": [
                        "missing evidence artifact: rust-native-live-account-read-smoke.json",
                        "missing evidence artifact: rust-native-release-platform-evidence.json",
                    ],
                    "artifact_status": artifact_status,
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "current_source_tree_dirty_paths": [],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        live_prerequisites = {
            "source_tree_clean": True,
            "can_run_market_smoke": False,
            "can_run_live_smoke": True,
            "market_missing_prerequisites": ["TRADING_BOT_RUST_MARKET_SMOKE=1"],
            "account_missing_prerequisites": [],
            "market_preflight_command": "market preflight",
            "market_command": "market command",
            "preflight_command": "account preflight",
            "command": "account command",
            "github_workflow": (
                "gh workflow run rust-native-live-smoke.yml -f binance_testnet=false -f symbol=ETHUSDT -f interval=5m"
            ),
            "binance_api_key_present": True,
            "binance_api_secret_present": True,
            "live_smoke_confirmation_present": True,
            "binance_testnet": "false",
            "live_smoke_symbol": "ETHUSDT",
            "live_smoke_interval": "5m",
            "market_smoke_expected_artifacts": ["rust-native-live-market-data-smoke.json"],
            "live_smoke_expected_artifacts": [
                "rust-native-live-market-data-smoke.json",
                "rust-native-live-account-read-smoke.json",
            ],
            "github_workflow_inputs": {
                "binance_testnet": "false",
                "symbol": "ETHUSDT",
                "interval": "5m",
            },
            "github_workflow_artifact": "rust-native-live-smoke-evidence",
            "github_workflow_plan_artifact": "rust-native-live-smoke-evidence-plan",
            "github_workflow_requires_secrets": ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
        }
        release_prerequisites = {
            "release_platform_preflight_ok": False,
            "source_tree_clean": True,
            "preflight_command": "release preflight",
            "command": "release command",
            "github_workflow": "gh workflow run rust-native-release-evidence.yml",
            "release_tag_configured": False,
            "release_evidence_target_count": 99,
            "platform_target_count": 70,
            "browser_target_count": 29,
            "missing_platform_evidence_count": 98,
            "missing_platform_evidence_limit": 10,
            "missing_platform_evidence_truncated": True,
            "missing_platform_evidence_all": [
                "browser-chrome-windows-11-x64",
                "browser-edge-windows-11-x64",
            ],
            "missing_platform_evidence_plan": [
                {
                    "target_id": "browser-chrome-windows-11-x64",
                    "target_validation_command": (
                        "python tools/check_release_platform_matrix.py --require-evidence "
                        "--require-current-commit --require-clean-source "
                        "--evidence-dir release-platform-evidence --target-filter browser-chrome-windows-11-x64"
                    ),
                    "workflow_dispatch_example": "gh workflow run release-platform-real-tests.yml",
                }
            ],
            "workflow_dispatch_batch_plan": {
                "workflow": "release-platform-real-tests.yml",
                "target_count": 98,
                "target_ids": [
                    "browser-chrome-windows-11-x64",
                    "browser-edge-windows-11-x64",
                ],
                "command_limit": 10,
                "command_count": 1,
                "command_target_ids": ["browser-chrome-windows-11-x64"],
                "commands": ["gh workflow run release-platform-real-tests.yml"],
                "workflow_dispatch_inputs": [
                    {
                        "target_id": "browser-chrome-windows-11-x64",
                        "runner_labels_json": "[]",
                    }
                ],
                "commands_truncated": True,
                "manual_input_target_count": 0,
                "manual_input_targets": [],
                "manual_input_targets_truncated": False,
                "validation_command": (
                    "python tools/check_release_platform_matrix.py --require-evidence "
                    "--require-current-commit --require-clean-source --evidence-dir release-platform-evidence"
                ),
                "aggregate_write_command": (
                    "python tools/write_rust_native_release_evidence.py --tag <tag> "
                    "--platform-evidence-dir release-platform-evidence"
                ),
            },
            "local_browser_batch_plan": {
                "host": "windows-11-x64",
                "target_count": 2,
                "target_ids": ["browser-chrome-windows-11-x64", "browser-edge-windows-11-x64"],
                "list_command": "python tools/run_release_platform_probe.py --list-local-browser-targets",
                "batch_command": (
                    "python tools/run_release_platform_probe.py "
                    "--local-browser-targets --require-clean-source --require-native-source-sync "
                    "--output-dir release-platform-evidence"
                ),
                "validation_commands": [
                    (
                        "python tools/check_release_platform_matrix.py --require-evidence "
                        "--require-current-commit --require-clean-source "
                        "--evidence-dir release-platform-evidence --target-filter browser-chrome-windows-11-x64"
                    )
                ],
                "partial_evidence_only": True,
                "remaining_matrix_targets_still_required": True,
            },
            "release_asset_presence_verified": False,
        }

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(runtime_readiness, "_live_smoke_prerequisites", return_value=live_prerequisites),
            patch.object(runtime_readiness, "_release_evidence_prerequisites", return_value=release_prerequisites),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        plan = result["evidence_collection_plan"]
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
                "rust-native-release-platform-evidence",
            ],
            [row["id"] for row in plan],
        )
        plan_by_id = {row["id"]: row for row in plan}
        market_row = plan_by_id["rust-native-live-market-data-smoke"]
        account_row = plan_by_id["rust-native-live-account-read-smoke"]
        release_row = plan_by_id["rust-native-release-platform-evidence"]

        self.assertEqual("passed", market_row["status"])
        self.assertFalse(market_row["ready_to_collect"])
        self.assertEqual(
            ["TRADING_BOT_RUST_MARKET_SMOKE=1"],
            market_row["details"]["missing_prerequisites"],
        )
        self.assertEqual("false", market_row["details"]["binance_testnet"])
        self.assertEqual("ETHUSDT", market_row["details"]["live_smoke_symbol"])
        self.assertEqual("5m", market_row["details"]["live_smoke_interval"])
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json"],
            market_row["details"]["expected_artifacts"],
        )
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            market_row["details"]["github_workflow_inputs"],
        )
        self.assertEqual("live_signed_account_read_smoke", account_row["collection_kind"])
        self.assertTrue(account_row["ready_to_collect"])
        self.assertEqual("account preflight", account_row["local_preflight_command"])
        self.assertEqual("account command", account_row["local_command"])
        self.assertIn("-f symbol=ETHUSDT", account_row["github_workflow"])
        self.assertIn("BINANCE_API_KEY", account_row["required_environment"])
        self.assertTrue(account_row["safety"]["read_only"])
        self.assertTrue(account_row["safety"]["requires_credentials"])
        self.assertFalse(account_row["safety"]["order_submission_attempted"])
        self.assertTrue(account_row["details"]["binance_api_key_present"])
        self.assertEqual([], account_row["details"]["missing_prerequisites"])
        self.assertEqual("false", account_row["details"]["binance_testnet"])
        self.assertEqual("ETHUSDT", account_row["details"]["live_smoke_symbol"])
        self.assertEqual("5m", account_row["details"]["live_smoke_interval"])
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json", "rust-native-live-account-read-smoke.json"],
            account_row["details"]["expected_artifacts"],
        )
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            account_row["details"]["github_workflow_inputs"],
        )
        self.assertEqual("rust-native-live-smoke-evidence", account_row["details"]["github_workflow_artifact"])
        self.assertEqual(
            "rust-native-live-smoke-evidence-plan", account_row["details"]["github_workflow_plan_artifact"]
        )
        self.assertEqual(
            ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
            account_row["details"]["github_workflow_requires_secrets"],
        )
        self.assertIn("--require-evidence", account_row["validation_command"])
        self.assertIn("--require-current-commit", account_row["validation_command"])
        self.assertIn("--require-clean-source", account_row["validation_command"])
        self.assertIn("--only rust-native-live-market-data-smoke", account_row["validation_command"])
        self.assertIn("--only rust-native-live-account-read-smoke", account_row["validation_command"])
        self.assertIn("--require-current-commit", account_row["import_command"])
        self.assertIn("--require-clean-source", account_row["import_command"])
        self.assertEqual(
            ["rust-native-live-market-data-smoke", "rust-native-live-account-read-smoke"],
            account_row["required_runtime_ids"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-live-market-data-smoke",
            account_row["import_command"],
        )
        self.assertIn(
            "--require-runtime-id rust-native-live-account-read-smoke",
            account_row["import_command"],
        )
        self.assertIn("missing evidence artifact", account_row["issues"][0])

        self.assertEqual("release_platform_evidence", release_row["collection_kind"])
        self.assertFalse(release_row["ready_to_collect"])
        self.assertEqual("release preflight", release_row["local_preflight_command"])
        self.assertIn("Rust release assets", release_row["required_inputs"])
        self.assertIn("passed release-platform-evidence JSON for every target", release_row["required_inputs"])
        self.assertEqual(["rust-native-release-platform-evidence"], release_row["required_runtime_ids"])
        self.assertIn("--only rust-native-release-platform-evidence", release_row["validation_command"])
        self.assertIn(
            "--require-runtime-id rust-native-release-platform-evidence",
            release_row["import_command"],
        )
        self.assertEqual(98, release_row["details"]["missing_platform_evidence_count"])
        self.assertEqual(10, release_row["details"]["missing_platform_evidence_limit"])
        self.assertTrue(release_row["details"]["missing_platform_evidence_truncated"])
        self.assertEqual(
            ["browser-chrome-windows-11-x64", "browser-edge-windows-11-x64"],
            release_row["details"]["missing_platform_evidence_all"],
        )
        self.assertTrue(release_row["details"]["source_tree_clean"])
        self.assertEqual(
            "browser-chrome-windows-11-x64",
            release_row["details"]["missing_platform_evidence_plan"][0]["target_id"],
        )
        self.assertEqual(
            ["browser-chrome-windows-11-x64", "browser-edge-windows-11-x64"],
            release_row["details"]["local_browser_batch_plan"]["target_ids"],
        )
        self.assertEqual(
            ["browser-chrome-windows-11-x64"],
            release_row["details"]["workflow_dispatch_batch_plan"]["command_target_ids"],
        )
        self.assertTrue(release_row["details"]["workflow_dispatch_batch_plan"]["commands_truncated"])
        self.assertIn(
            "--require-current-commit",
            release_row["details"]["missing_platform_evidence_plan"][0]["target_validation_command"],
        )
        self.assertFalse(release_row["details"]["release_asset_presence_verified"])
        self.assertEqual(99, release_row["details"]["release_evidence_target_count"])
        self.assertEqual(70, release_row["details"]["platform_target_count"])
        self.assertEqual(29, release_row["details"]["browser_target_count"])

        action_plan = {row["id"]: row for row in result["promotion_next_action_plan"]}
        expected_workflow_source_sync_audit = {
            "step": "Audit native source sync",
            "command": (
                "python tools/audit_native_source_sync.py --json "
                "--output artifacts/native-source-sync/native-source-sync-audit.json"
            ),
            "output_path": "artifacts/native-source-sync/native-source-sync-audit.json",
            "github_workflow_artifact": "native-source-sync-audit",
            "required_before_evidence_collection": True,
            "python_source_of_truth": "Languages/Python/app/native_parity.py",
        }
        account_action = action_plan["collect_rust_native_live_account_smoke"]
        release_action = action_plan["collect_rust_native_release_platform_evidence"]
        promotion_action = action_plan["run_rust_native_promotion_audit_workflow"]
        guard_action = action_plan["promote_runtime_ready_source_guard"]

        self.assertTrue(account_action["ready_to_run"])
        self.assertEqual([], account_action["blocked_by"])
        self.assertEqual([], account_action["depends_on_action_ids"])
        self.assertEqual(2, account_action["details"]["evidence_row_count"])
        self.assertEqual(
            "rust-native-live-account-read-smoke",
            account_action["details"]["evidence_rows"][1]["id"],
        )
        self.assertEqual(
            "account preflight",
            account_action["details"]["evidence_rows"][1]["local_preflight_command"],
        )
        self.assertIn("-f symbol=ETHUSDT", account_action["github_workflow"])
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            account_action["details"]["github_workflow_inputs"],
        )
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json", "rust-native-live-account-read-smoke.json"],
            account_action["details"]["expected_artifacts"],
        )
        self.assertEqual("rust-native-live-smoke-evidence", account_action["details"]["github_workflow_artifact"])
        self.assertEqual(
            "rust-native-live-smoke-evidence-plan",
            account_action["details"]["github_workflow_plan_artifact"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            account_action["details"]["workflow_source_sync_audit"],
        )
        self.assertEqual(
            ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
            account_action["details"]["github_workflow_requires_secrets"],
        )
        self.assertEqual(
            {"binance_testnet": "false", "symbol": "ETHUSDT", "interval": "5m"},
            account_action["details"]["evidence_rows"][1]["details"]["github_workflow_inputs"],
        )
        self.assertEqual(
            ["rust-native-live-market-data-smoke.json", "rust-native-live-account-read-smoke.json"],
            account_action["details"]["evidence_rows"][1]["details"]["expected_artifacts"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            account_action["details"]["evidence_rows"][1]["details"]["workflow_source_sync_audit"],
        )
        self.assertFalse(account_action["details"]["evidence_rows"][1]["safety"]["order_submission_attempted"])
        self.assertFalse(release_action["ready_to_run"])
        self.assertTrue(
            any("rust-native-release-platform-evidence" in blocker for blocker in release_action["blocked_by"])
        )
        self.assertEqual(1, release_action["details"]["evidence_row_count"])
        self.assertEqual(99, release_action["details"]["release_evidence_target_count"])
        self.assertEqual(98, release_action["details"]["missing_platform_evidence_count"])
        self.assertIn(
            "browser-chrome-windows-11-x64",
            release_action["details"]["local_browser_batch_plan"]["target_ids"],
        )
        self.assertEqual(98, release_action["details"]["workflow_dispatch_batch_plan"]["target_count"])
        self.assertEqual(1, release_action["details"]["workflow_dispatch_batch_plan"]["command_count"])
        self.assertEqual(
            ["browser-chrome-windows-11-x64"],
            release_action["details"]["workflow_dispatch_batch_command_target_ids"],
        )
        self.assertEqual(10, release_action["details"]["workflow_dispatch_batch_command_limit"])
        self.assertTrue(release_action["details"]["workflow_dispatch_batch_commands_truncated"])
        self.assertEqual(0, release_action["details"]["workflow_dispatch_batch_manual_input_target_count"])
        self.assertFalse(release_action["details"]["workflow_dispatch_batch_manual_input_targets_truncated"])
        self.assertEqual(
            expected_workflow_source_sync_audit,
            release_action["details"]["workflow_source_sync_audit"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            release_action["details"]["evidence_rows"][0]["details"]["workflow_source_sync_audit"],
        )
        self.assertFalse(promotion_action["ready_to_run"])
        self.assertIn(
            "missing runtime evidence: rust-native-live-account-read-smoke",
            promotion_action["blocked_by"],
        )
        self.assertIn(
            "collect_rust_native_live_account_smoke",
            promotion_action["depends_on_action_ids"],
        )
        self.assertIn(
            "collect_rust_native_release_platform_evidence",
            promotion_action["depends_on_action_ids"],
        )
        self.assertEqual("rust-native-promotion-audit.yml", promotion_action["details"]["github_workflow"])
        self.assertEqual(
            {
                "live_smoke_run_id": "<live-smoke-actions-run-id>",
                "release_evidence_run_id": "<release-evidence-actions-run-id>",
            },
            promotion_action["details"]["github_workflow_inputs"],
        )
        self.assertEqual(
            "rust-native-promotion-evidence-plan",
            promotion_action["details"]["github_workflow_plan_artifact"],
        )
        self.assertEqual(
            expected_workflow_source_sync_audit,
            promotion_action["details"]["workflow_source_sync_audit"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
                "rust-native-release-platform-evidence",
            ],
            promotion_action["details"]["required_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-market-data-smoke",
                "rust-native-live-account-read-smoke",
                "rust-native-release-platform-evidence",
            ],
            promotion_action["details"]["external_import_runtime_ids"],
        )
        self.assertEqual(
            [
                "rust-native-live-stream-recovery",
                "rust-native-order-guard-recovery",
            ],
            promotion_action["details"]["local_recovery_runtime_ids"],
        )
        self.assertFalse(guard_action["ready_to_run"])
        self.assertIn(
            "failed promotion requirement: required_runtime_evidence",
            guard_action["blocked_by"],
        )
        self.assertIn(
            "run_rust_native_promotion_audit_workflow",
            guard_action["depends_on_action_ids"],
        )

        markdown = runtime_readiness._render_evidence_collection_markdown(result)
        self.assertIn("# Rust Native Runtime Evidence Collection Plan", markdown)
        self.assertIn("Runtime completion claim: denied", markdown)
        self.assertIn("Runtime completion can be claimed: false", markdown)
        self.assertIn("Runtime required environment:", markdown)
        self.assertIn("TRADING_BOT_RUST_LIVE_SMOKE=1", markdown)
        self.assertIn("Runtime required inputs:", markdown)
        self.assertIn("Rust release assets", markdown)
        self.assertIn("## Promotion Requirements", markdown)
        self.assertIn("## Clean Source Scope", markdown)
        self.assertIn("## Evidence Artifacts", markdown)
        self.assertIn("rust-native-live-account-read-smoke", markdown)
        self.assertIn("account preflight", markdown)
        self.assertIn("account command", markdown)
        self.assertIn("read_only=true", markdown)
        self.assertIn("requires_credentials=true", markdown)
        self.assertIn(
            "Expected artifacts: `rust-native-live-market-data-smoke.json`, `rust-native-live-account-read-smoke.json`",
            markdown,
        )
        self.assertIn("GitHub workflow inputs:", markdown)
        self.assertIn("GitHub workflow source-sync gate:", markdown)
        self.assertIn("python tools/audit_native_source_sync.py --json", markdown)
        self.assertIn("`symbol=ETHUSDT`", markdown)
        self.assertIn("`interval=5m`", markdown)
        self.assertIn("rust-native-live-smoke-evidence", markdown)
        self.assertIn("rust-native-live-smoke-evidence-plan", markdown)
        self.assertIn("GitHub workflow required secrets: `BINANCE_API_KEY`, `BINANCE_API_SECRET`", markdown)
        self.assertIn("release preflight", markdown)
        self.assertIn("Source tree clean: true", markdown)
        self.assertIn("Missing prerequisites: `TRADING_BOT_RUST_MARKET_SMOKE=1`", markdown)
        self.assertIn("Validation command", markdown)
        self.assertIn("--require-current-commit", markdown)
        self.assertIn("browser-chrome-windows-11-x64", markdown)
        self.assertIn("gh workflow run release-platform-real-tests.yml", markdown)
        self.assertIn("Local browser batch", markdown)
        self.assertIn("Missing target workflow dispatch batch", markdown)
        self.assertIn("targets with dispatch commands", markdown)
        self.assertIn("structured dispatch inputs", markdown)
        self.assertIn("commands shown: 1 of 98", markdown)
        self.assertIn("--local-browser-targets", markdown)
        self.assertIn("browser-edge-windows-11-x64", markdown)
        self.assertIn("missing target plan is truncated", markdown)
        self.assertIn("Release evidence target count: 99 (platform=70, browser=29)", markdown)
        self.assertIn("Required runtime evidence ids", markdown)
        self.assertIn("--require-runtime-id rust-native-live-account-read-smoke", markdown)
        self.assertIn("--require-runtime-id rust-native-release-platform-evidence", markdown)
        self.assertIn("## Next Actions", markdown)
        self.assertIn("Ready to run now: true", markdown)
        self.assertIn("Ready to run now: false", markdown)
        self.assertIn("Blocked by:", markdown)
        self.assertIn("gh workflow run rust-native-promotion-audit.yml", markdown)
        self.assertIn("GitHub promotion audit workflow inputs:", markdown)
        self.assertIn("`live_smoke_run_id=<live-smoke-actions-run-id>`", markdown)
        self.assertIn("`release_evidence_run_id=<release-evidence-actions-run-id>`", markdown)
        self.assertIn("rust-native-promotion-evidence-plan", markdown)
        self.assertIn("Promotion required runtime evidence ids", markdown)
        self.assertIn("clean candidate source revision", markdown)
        self.assertIn("Keep rust_native_trading_runtime_ready() false", markdown)

    def test_readiness_audit_blocks_local_recovery_collection_when_targets_are_tracked(self):
        tracked_targets = [
            "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
            "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
        ]
        artifact_status = [
            {
                "id": "rust-native-live-stream-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                "issues": ["missing evidence artifact: rust-native-live-stream-recovery.json"],
            },
            {
                "id": "rust-native-order-guard-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                "issues": ["missing evidence artifact: rust-native-order-guard-recovery.json"],
            },
        ]

        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": ["missing local recovery evidence"],
                    "artifact_status": artifact_status,
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "current_source_tree_dirty_paths": [],
                    "current_source_tree_untracked_paths": [],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(runtime_readiness, "_live_smoke_prerequisites", return_value={}),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
            patch.object(
                runtime_readiness,
                "local_recovery_generation_guard",
                return_value={
                    "ok": False,
                    "generated_evidence_write_targets": tracked_targets,
                    "non_generated_in_repo_write_targets": [],
                    "tracked_generated_evidence_targets": tracked_targets,
                    "issues": ["refusing to write generated evidence artifact over tracked source path(s)"],
                },
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        self.assertFalse(result["local_recovery_prerequisites"]["ok"])
        plan_by_id = {row["id"]: row for row in result["evidence_collection_plan"]}
        stream_row = plan_by_id["rust-native-live-stream-recovery"]
        order_row = plan_by_id["rust-native-order-guard-recovery"]
        for row in (stream_row, order_row):
            self.assertEqual("deterministic_local_recovery", row["collection_kind"])
            self.assertFalse(row["ready_to_collect"])
            self.assertFalse(row["prerequisites_ok"])
            self.assertFalse(row["details"]["source_control_guard_ok"])
            self.assertTrue(row["details"]["native_source_sync_ok"])
            self.assertIn("--require-native-source-sync", row["local_command"])
            self.assertEqual(tracked_targets, row["details"]["generated_evidence_write_targets"])
            self.assertEqual([], row["details"]["non_generated_in_repo_write_targets"])
            self.assertEqual(tracked_targets, row["details"]["tracked_generated_evidence_targets"])
            self.assertEqual(
                tracked_targets, row["details"]["source_control_guard"]["generated_evidence_write_targets"]
            )
            self.assertTrue(any("refusing to write generated evidence artifact" in issue for issue in row["issues"]))

    def test_readiness_audit_blocks_local_recovery_collection_when_source_is_dirty(self):
        artifact_status = [
            {
                "id": "rust-native-live-stream-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                "issues": ["missing evidence artifact: rust-native-live-stream-recovery.json"],
            },
            {
                "id": "rust-native-order-guard-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                "issues": ["missing evidence artifact: rust-native-order-guard-recovery.json"],
            },
        ]

        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": ["missing local recovery evidence"],
                    "artifact_status": artifact_status,
                    "current_commit": "abc123",
                    "current_source_tree_clean": False,
                    "current_source_tree_dirty_paths": ["tools/audit_rust_native_runtime_readiness.py"],
                    "current_source_tree_untracked_paths": [],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(
                runtime_readiness,
                "audit_native_source_sync",
                return_value=_valid_source_sync_audit_payload("fresh-hash"),
            ),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(runtime_readiness, "_live_smoke_prerequisites", return_value={}),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
            patch.object(
                runtime_readiness,
                "local_recovery_generation_guard",
                return_value={
                    "ok": True,
                    "generated_evidence_write_targets": [
                        "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                        "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                    ],
                    "non_generated_in_repo_write_targets": [],
                    "tracked_generated_evidence_targets": [],
                    "issues": [],
                },
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        plan_by_id = {row["id"]: row for row in result["evidence_collection_plan"]}
        for evidence_id in (
            "rust-native-live-stream-recovery",
            "rust-native-order-guard-recovery",
        ):
            row = plan_by_id[evidence_id]
            self.assertEqual("deterministic_local_recovery", row["collection_kind"])
            self.assertFalse(row["ready_to_collect"])
            self.assertFalse(row["prerequisites_ok"])
            self.assertTrue(row["details"]["source_control_guard_ok"])
            self.assertTrue(row["details"]["native_source_sync_ok"])
            self.assertIn("--require-native-source-sync", row["local_command"])
            self.assertFalse(row["details"]["source_tree_clean"])
            self.assertEqual(["clean source tree"], row["details"]["missing_prerequisites"])
            self.assertTrue(any("source tree must be clean" in issue for issue in row["issues"]))

        missing_rows = {row["evidence_id"]: row for row in result["completion_claim"]["missing_inputs"]["evidence"]}
        self.assertEqual(
            ["clean source tree"],
            missing_rows["rust-native-live-stream-recovery"]["missing_prerequisites"],
        )
        self.assertEqual(
            ["clean source tree"],
            missing_rows["rust-native-order-guard-recovery"]["missing_prerequisites"],
        )

    def test_readiness_audit_blocks_local_recovery_collection_when_native_source_sync_fails(self):
        artifact_status = [
            {
                "id": "rust-native-live-stream-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                "issues": ["missing evidence artifact: rust-native-live-stream-recovery.json"],
            },
            {
                "id": "rust-native-order-guard-recovery",
                "category": "live_recovery",
                "ok": False,
                "path": "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                "issues": ["missing evidence artifact: rust-native-order-guard-recovery.json"],
            },
        ]
        failed_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        failed_source_sync["ok"] = False
        failed_source_sync["issues"] = ["generated contract drift"]

        def _validate_stub(*_args: object, **kwargs: object) -> dict[str, object]:
            if kwargs.get("require_evidence"):
                return {
                    "ok": False,
                    "issues": ["missing local recovery evidence"],
                    "artifact_status": artifact_status,
                    "current_commit": "abc123",
                    "current_source_tree_clean": True,
                    "current_source_tree_dirty_paths": [],
                    "current_source_tree_untracked_paths": [],
                    "current_source_tree_ignored_paths": [
                        "artifacts/rust-native-runtime-evidence",
                        "artifacts/native-source-sync",
                        "release-platform-evidence",
                    ],
                    "evidence_dir": "artifacts/rust-native-runtime-evidence",
                }
            return {"ok": True, "issues": [], "runtime_ready_policy_state": False}

        with (
            patch.object(
                runtime_readiness,
                "_source_contract_audit",
                return_value={"ok": True, "runtime_ready_source_state": False, "issues": []},
            ),
            patch.object(runtime_readiness, "audit_native_source_sync", return_value=failed_source_sync),
            patch.object(runtime_readiness, "validate", side_effect=_validate_stub),
            patch.object(runtime_readiness, "_live_smoke_prerequisites", return_value={}),
            patch.object(
                runtime_readiness,
                "_release_evidence_prerequisites",
                return_value={"release_platform_preflight_ok": False},
            ),
            patch.object(
                runtime_readiness,
                "local_recovery_generation_guard",
                return_value={
                    "ok": True,
                    "generated_evidence_write_targets": [
                        "artifacts/rust-native-runtime-evidence/rust-native-live-stream-recovery.json",
                        "artifacts/rust-native-runtime-evidence/rust-native-order-guard-recovery.json",
                    ],
                    "non_generated_in_repo_write_targets": [],
                    "tracked_generated_evidence_targets": [],
                    "issues": [],
                },
            ),
        ):
            result = runtime_readiness.audit(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir_override=None,
                require_ready=False,
            )

        plan_by_id = {row["id"]: row for row in result["evidence_collection_plan"]}
        for evidence_id in (
            "rust-native-live-stream-recovery",
            "rust-native-order-guard-recovery",
        ):
            row = plan_by_id[evidence_id]
            self.assertFalse(row["ready_to_collect"])
            self.assertFalse(row["prerequisites_ok"])
            self.assertTrue(row["details"]["source_control_guard_ok"])
            self.assertFalse(row["details"]["native_source_sync_ok"])
            self.assertEqual(["native source sync audit"], row["details"]["missing_prerequisites"])
            self.assertTrue(any("native source sync audit must pass" in issue for issue in row["issues"]))

        missing_rows = {row["evidence_id"]: row for row in result["completion_claim"]["missing_inputs"]["evidence"]}
        self.assertEqual(
            ["native source sync audit"],
            missing_rows["rust-native-live-stream-recovery"]["missing_prerequisites"],
        )
        self.assertEqual(
            ["native source sync audit"],
            missing_rows["rust-native-order-guard-recovery"]["missing_prerequisites"],
        )

    def test_importer_validates_actions_zip_into_runtime_and_platform_dirs(self):
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, browser_targets, matrix_issues = release_platform_matrix._validate_matrix(matrix)
        self.assertEqual([], matrix_issues)
        targets = platform_targets + browser_targets
        windows_target = next(target for target in targets if target["id"] == "windows-11-x64")
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }
        market_payload = {
            "evidence_id": "rust-native-live-market-data-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }
        platform_payload = {
            **_target_evidence_payload(windows_target),
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "runtime_ready_claimed": False,
            "secrets_redacted": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "github-actions-artifacts.zip"
            runtime_dir = root / "runtime-evidence"
            platform_dir = root / "release-platform-evidence"
            runtime_dir.mkdir()
            (runtime_dir / "rust-native-live-market-data-smoke.json").write_text(
                json.dumps(market_payload, sort_keys=True),
                encoding="utf-8",
            )
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "rust-native-live-smoke-evidence/rust-native-live-market-data-smoke.json",
                    json.dumps(market_payload),
                )
                archive.writestr(
                    "rust-native-live-smoke-evidence/rust-native-live-account-read-smoke.json",
                    json.dumps(account_payload),
                )
                archive.writestr(
                    "release-platform-evidence-windows-11-x64/windows-11-x64.json",
                    json.dumps(platform_payload),
                )
                archive.writestr("release-platform-evidence-windows-11-x64/notes.txt", "ignored")

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                preview = evidence_importer.import_evidence_artifacts(
                    [archive_path],
                    runtime_evidence_dir=runtime_dir,
                    platform_evidence_dir=platform_dir,
                    apply=False,
                    require_current_commit=True,
                    require_clean_source=True,
                    required_runtime_ids={
                        "rust-native-live-market-data-smoke",
                        "rust-native-live-account-read-smoke",
                    },
                )
                imported = evidence_importer.import_evidence_artifacts(
                    [archive_path],
                    runtime_evidence_dir=runtime_dir,
                    platform_evidence_dir=platform_dir,
                    apply=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    required_runtime_ids={
                        "rust-native-live-market-data-smoke",
                        "rust-native-live-account-read-smoke",
                    },
                )
            runtime_evidence_imported = (runtime_dir / "rust-native-live-account-read-smoke.json").is_file()
            platform_evidence_imported = (platform_dir / "windows-11-x64.json").is_file()

        self.assertTrue(preview["ok"], preview["issues"])
        self.assertTrue(preview["require_current_commit"])
        self.assertTrue(preview["require_clean_source"])
        self.assertEqual(
            ["rust-native-live-account-read-smoke", "rust-native-live-market-data-smoke"],
            preview["required_runtime_ids"],
        )
        self.assertEqual(
            ["rust-native-live-account-read-smoke", "rust-native-live-market-data-smoke"],
            preview["valid_runtime_ids"],
        )
        self.assertEqual(2, preview["planned_count"])
        self.assertEqual(0, preview["copied_count"])
        self.assertEqual(0, preview["overwrite_count"])
        self.assertEqual(1, preview["skipped_existing_count"])
        self.assertTrue(all(row["action"] == "copy" for row in preview["planned"]))
        self.assertEqual("skip_existing_identical", preview["skipped_existing"][0]["action"])
        self.assertTrue(imported["ok"], imported["issues"])
        self.assertEqual(2, imported["copied_count"])
        self.assertEqual(0, imported["overwrite_count"])
        self.assertEqual(1, imported["skipped_existing_count"])
        self.assertTrue(all(row["action"] == "copy" for row in imported["copied"]))
        self.assertTrue(runtime_evidence_imported)
        self.assertTrue(platform_evidence_imported)

    def test_importer_rejects_stale_release_platform_evidence_with_promotion_flags(self):
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, browser_targets, matrix_issues = release_platform_matrix._validate_matrix(matrix)
        self.assertEqual([], matrix_issues)
        targets = platform_targets + browser_targets
        windows_target = next(target for target in targets if target["id"] == "windows-11-x64")
        payload = {
            **_target_evidence_payload(windows_target),
            "commit": "old-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "runtime_ready_claimed": False,
            "secrets_redacted": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "windows-11-x64.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                stale_commit = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    platform_evidence_dir=root / "release-platform-evidence",
                    apply=False,
                    require_current_commit=True,
                    require_clean_source=True,
                )

            payload["commit"] = "current-commit"
            payload["source_tree_clean"] = False
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                dirty_artifact = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    platform_evidence_dir=root / "release-platform-evidence",
                    apply=False,
                    require_current_commit=True,
                    require_clean_source=True,
                )

            payload["source_tree_clean"] = True
            payload["python_source_contract_hash"] = "0" * 64
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                stale_contract = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    platform_evidence_dir=root / "release-platform-evidence",
                    apply=False,
                    require_current_commit=True,
                    require_clean_source=True,
                )

        self.assertFalse(stale_commit["ok"])
        self.assertEqual(0, stale_commit["planned_count"])
        self.assertTrue(any("commit must match current git commit" in issue for issue in stale_commit["issues"]))
        self.assertFalse(dirty_artifact["ok"])
        self.assertEqual(0, dirty_artifact["planned_count"])
        self.assertTrue(any("source_tree_clean must be true" in issue for issue in dirty_artifact["issues"]))
        self.assertFalse(stale_contract["ok"])
        self.assertEqual(0, stale_contract["planned_count"])
        self.assertTrue(
            any(
                "python_source_contract_hash must match current Python source contract" in issue
                for issue in stale_contract["issues"]
            )
        )

    def test_importer_reports_overwrite_actions_and_hashes(self):
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:2",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }
        existing_payload = {
            **account_payload,
            "generated_at": "unix:1",
            "command": "previous live account smoke",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "github-actions-artifacts.zip"
            runtime_dir = root / "runtime-evidence"
            runtime_dir.mkdir()
            destination = runtime_dir / "rust-native-live-account-read-smoke.json"
            destination.write_text(json.dumps(existing_payload, sort_keys=True), encoding="utf-8")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "rust-native-live-smoke-evidence/rust-native-live-account-read-smoke.json",
                    json.dumps(account_payload),
                )

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [archive_path],
                    runtime_evidence_dir=runtime_dir,
                    apply=True,
                    overwrite=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    required_runtime_ids={"rust-native-live-account-read-smoke"},
                )
            imported_payload = json.loads(destination.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(1, result["planned_count"])
        self.assertEqual(1, result["copied_count"])
        self.assertEqual(1, result["overwrite_count"])
        self.assertEqual(1, len(result["overwritten"]))
        overwrite_row = result["overwritten"][0]
        self.assertEqual("overwrite", overwrite_row["action"])
        self.assertEqual(str(destination), overwrite_row["destination"])
        self.assertFalse(overwrite_row["replaces_identical_json"])
        self.assertRegex(overwrite_row["existing_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(overwrite_row["incoming_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(overwrite_row["existing_sha256"], overwrite_row["incoming_sha256"])
        self.assertEqual(account_payload, imported_payload)

    def test_importer_requires_named_runtime_artifacts_for_promotion_import(self):
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "rust-native-live-account-read-smoke.json"
            evidence_path.write_text(json.dumps(account_payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    runtime_evidence_dir=root / "runtime-evidence",
                    require_current_commit=True,
                    require_clean_source=True,
                    required_runtime_ids={
                        "rust-native-live-market-data-smoke",
                        "rust-native-live-account-read-smoke",
                        "rust-native-release-platform-evidence",
                    },
                )

        self.assertFalse(result["ok"])
        self.assertEqual(["rust-native-live-account-read-smoke"], result["valid_runtime_ids"])
        self.assertTrue(
            any(
                "missing required runtime evidence artifact in scanned inputs: rust-native-live-market-data-smoke"
                in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "missing required runtime evidence artifact in scanned inputs: rust-native-release-platform-evidence"
                in issue
                for issue in result["issues"]
            )
        )

    def test_importer_requires_native_source_sync_audit_for_promotion_import(self):
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "rust-native-live-account-read-smoke.json"
            evidence_path.write_text(json.dumps(account_payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    runtime_evidence_dir=root / "runtime-evidence",
                    require_current_commit=True,
                    require_clean_source=True,
                    require_native_source_sync_audit=True,
                    required_runtime_ids={"rust-native-live-account-read-smoke"},
                )

        self.assertFalse(result["ok"])
        self.assertEqual(["rust-native-live-account-read-smoke"], result["valid_runtime_ids"])
        self.assertEqual(0, result["native_source_sync_audit_count"])
        self.assertEqual([], result["valid_native_source_sync_audit_sources"])
        self.assertEqual([], result["valid_current_checkout_native_source_sync_audit_sources"])
        self.assertTrue(
            any(
                "missing required native source sync audit artifact in scanned inputs: native-source-sync-audit.json"
                in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "missing required current-checkout native source sync audit artifact: "
                "artifacts/native-source-sync/native-source-sync-audit.json" in issue
                for issue in result["issues"]
            )
        )

    def test_importer_rejects_downloaded_native_source_sync_audit_for_promotion_import(self):
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "github-actions-artifacts.zip"
            runtime_dir = root / "runtime-evidence"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "rust-native-live-smoke-evidence/rust-native-live-account-read-smoke.json",
                    json.dumps(account_payload),
                )
                archive.writestr(
                    "native-source-sync-audit/native-source-sync-audit.json",
                    json.dumps(_valid_source_sync_audit_payload()),
                )
            with (
                patch.object(evidence_importer, "_repo_root", return_value=root),
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [archive_path],
                    runtime_evidence_dir=runtime_dir,
                    manifest_path=REPO_ROOT / "docs" / "rust-native-runtime-evidence.json",
                    matrix_path=REPO_ROOT / "docs" / "release-platform-test-matrix.json",
                    require_current_commit=True,
                    require_clean_source=True,
                    require_native_source_sync_audit=True,
                    required_runtime_ids={"rust-native-live-account-read-smoke"},
                )

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["native_source_sync_audit_count"])
        self.assertEqual(
            [f"{archive_path}!native-source-sync-audit/native-source-sync-audit.json"],
            result["valid_native_source_sync_audit_sources"],
        )
        self.assertEqual([], result["valid_current_checkout_native_source_sync_audit_sources"])
        self.assertEqual(["rust-native-live-account-read-smoke"], result["valid_runtime_ids"])
        self.assertTrue(
            any(
                "missing required current-checkout native source sync audit artifact: "
                "artifacts/native-source-sync/native-source-sync-audit.json" in issue
                for issue in result["issues"]
            )
        )

    def test_importer_accepts_current_native_source_sync_audit_for_promotion_import(self):
        account_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }
        source_sync_payload = _valid_source_sync_audit_payload()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "github-actions-artifacts.zip"
            runtime_dir = root / "runtime-evidence"
            canonical_audit_path = root / "artifacts" / "native-source-sync" / "native-source-sync-audit.json"
            canonical_audit_path.parent.mkdir(parents=True)
            canonical_audit_path.write_text(json.dumps(source_sync_payload), encoding="utf-8")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "rust-native-live-smoke-evidence/rust-native-live-account-read-smoke.json",
                    json.dumps(account_payload),
                )
            with (
                patch.object(evidence_importer, "_repo_root", return_value=root),
                patch.object(runtime_evidence, "_current_git_commit", return_value="abc123"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [archive_path, canonical_audit_path],
                    runtime_evidence_dir=runtime_dir,
                    manifest_path=REPO_ROOT / "docs" / "rust-native-runtime-evidence.json",
                    matrix_path=REPO_ROOT / "docs" / "release-platform-test-matrix.json",
                    require_current_commit=True,
                    require_clean_source=True,
                    require_native_source_sync_audit=True,
                    required_runtime_ids={"rust-native-live-account-read-smoke"},
                )

        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["require_native_source_sync_audit"])
        self.assertEqual(2, result["candidate_count"])
        self.assertEqual(1, result["native_source_sync_audit_count"])
        self.assertEqual(
            [str(canonical_audit_path)],
            result["valid_native_source_sync_audit_sources"],
        )
        self.assertEqual(
            [str(canonical_audit_path)],
            result["valid_current_checkout_native_source_sync_audit_sources"],
        )
        self.assertEqual(1, result["planned_count"])

    def test_importer_rejects_legacy_native_source_sync_audit_without_surface_contract(self):
        source_sync_payload = _valid_source_sync_audit_payload()
        source_sync_payload.pop("surface_contract")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "native-source-sync-audit.json"
            audit_path.write_text(json.dumps(source_sync_payload), encoding="utf-8")
            result = evidence_importer.import_evidence_artifacts(
                [audit_path],
                runtime_evidence_dir=root / "runtime-evidence",
                require_native_source_sync_audit=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["native_source_sync_audit_count"])
        self.assertEqual([], result["valid_native_source_sync_audit_sources"])
        self.assertTrue(any("must include native source sync surface_contract" in issue for issue in result["issues"]))

    def test_importer_rejects_native_source_sync_audit_surface_contract_drift(self):
        source_sync_payload = _valid_source_sync_audit_payload()
        surface_contract = dict(source_sync_payload["surface_contract"])
        surface_contract["actual_consumer_surface_names"] = surface_contract["actual_consumer_surface_names"][:-1]
        source_sync_payload["surface_contract"] = surface_contract

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "native-source-sync-audit.json"
            audit_path.write_text(json.dumps(source_sync_payload), encoding="utf-8")
            result = evidence_importer.import_evidence_artifacts(
                [audit_path],
                runtime_evidence_dir=root / "runtime-evidence",
                require_native_source_sync_audit=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["native_source_sync_audit_count"])
        self.assertEqual([], result["valid_native_source_sync_audit_sources"])
        self.assertTrue(
            any("surface_contract actual_consumer_surface_names mismatch" in issue for issue in result["issues"])
        )

    def test_importer_rejects_partial_or_failed_native_source_sync_audit(self):
        source_sync_payload = {
            "ok": True,
            "source": "Languages/Python/app/native_parity.py",
            "contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "generated": [
                {
                    "name": "rust_core_generated_contract",
                    "ok": True,
                    "embeds_contract_hash": True,
                    "expected_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                    "actual_sha256": "1" * 64,
                    "expected_sha256": "1" * 64,
                    "actual_bytes": 1,
                    "expected_bytes": 1,
                    "issues": [],
                },
                {
                    "name": "cpp_generated_contract",
                    "ok": False,
                    "embeds_contract_hash": False,
                    "expected_contract_hash": "0" * 64,
                    "actual_sha256": "1" * 64,
                    "expected_sha256": "2" * 64,
                    "actual_bytes": 10,
                    "expected_bytes": 11,
                    "issues": ["stale generated artifact"],
                },
            ],
            "consumers": [
                {
                    "name": "cpp_dashboard_uses_python_source_surface",
                    "ok": False,
                    "missing_text": ["pythonSourceIndicatorDisplayNames"],
                    "unknown_service_routes": ["unknown_route"],
                    "unknown_route_extractors": ["bad_extractor"],
                }
            ],
            "issues": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "native-source-sync-audit.json"
            audit_path.write_text(json.dumps(source_sync_payload), encoding="utf-8")
            result = evidence_importer.import_evidence_artifacts(
                [audit_path],
                runtime_evidence_dir=root / "runtime-evidence",
                require_native_source_sync_audit=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["native_source_sync_audit_count"])
        self.assertEqual([], result["valid_native_source_sync_audit_sources"])
        self.assertTrue(
            any(
                "missing generated artifact check: tauri_browser_generated_contract" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any("generated artifact check failed: cpp_generated_contract" in issue for issue in result["issues"])
        )
        self.assertTrue(
            any(
                "generated artifact issues must be empty: cpp_generated_contract" in issue for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "generated artifact must embed current contract hash: cpp_generated_contract" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "generated artifact expected_contract_hash is stale: cpp_generated_contract" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any("generated artifact SHA-256 mismatch: cpp_generated_contract" in issue for issue in result["issues"])
        )
        self.assertTrue(
            any("generated artifact byte count mismatch: cpp_generated_contract" in issue for issue in result["issues"])
        )
        self.assertTrue(
            any(
                "missing consumer surface check: rust_core_consumes_generated_contract" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "missing consumer surface check: tauri_browser_service_api_uses_python_source_routes" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "consumer surface check failed: cpp_dashboard_uses_python_source_surface" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "consumer surface missing_text must be empty: cpp_dashboard_uses_python_source_surface" in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "consumer surface unknown_service_routes must be empty: cpp_dashboard_uses_python_source_surface"
                in issue
                for issue in result["issues"]
            )
        )
        self.assertTrue(
            any(
                "consumer surface unknown_route_extractors must be empty: cpp_dashboard_uses_python_source_surface"
                in issue
                for issue in result["issues"]
            )
        )

    def test_importer_treats_missing_canonical_evidence_dirs_as_empty_audit_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(evidence_importer, "_repo_root", return_value=root):
                result = evidence_importer.import_evidence_artifacts(
                    [
                        Path("artifacts/rust-native-runtime-evidence"),
                        Path("release-platform-evidence"),
                    ],
                    matrix_path=REPO_ROOT / "docs" / "release-platform-test-matrix.json",
                    manifest_path=REPO_ROOT / "docs" / "rust-native-runtime-evidence.json",
                )

        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(0, result["candidate_count"])
        self.assertEqual([], result["valid_runtime_ids"])

    def test_importer_can_reject_stale_runtime_evidence_in_promotion_mode(self):
        stale_payload = {
            "evidence_id": "rust-native-live-account-read-smoke",
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "old-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "rust-native-live-account-read-smoke.json"
            evidence_path.write_text(json.dumps(stale_payload), encoding="utf-8")
            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                result = evidence_importer.import_evidence_artifacts(
                    [evidence_path],
                    runtime_evidence_dir=root / "runtime-evidence",
                    require_current_commit=True,
                    require_clean_source=True,
                )

        self.assertFalse(result["ok"])
        self.assertEqual(0, result["planned_count"])
        self.assertTrue(any("commit must match current git commit" in issue for issue in result["issues"]))

    def test_release_platform_evidence_requires_platform_probe_target_match(self):
        target = {
            "id": "windows-11-x64",
            "kind": "platform",
            "test_suites": ["platform-probe", "desktop-release-smoke"],
        }
        payload = {
            "target_id": "windows-11-x64",
            "status": "passed",
            "suite_results": [
                {
                    "name": "platform-probe",
                    "status": "passed",
                    "target_match": {
                        "matched": False,
                        "issues": ["system mismatch: expected Windows, observed Linux"],
                    },
                },
                {"name": "desktop-release-smoke", "status": "passed"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "windows-11-x64.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            issues = release_platform_matrix._evidence_issues([target], evidence_dir)
            payload["suite_results"][0]["target_match"] = {"matched": True, "issues": []}
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            fixed_issues = release_platform_matrix._evidence_issues([target], evidence_dir)
            payload["suite_results"] = payload["suite_results"][:1]
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            missing_suite_issues = release_platform_matrix._evidence_issues([target], evidence_dir)

        self.assertTrue(any("target_match.matched must be true" in issue for issue in issues))
        self.assertEqual([], fixed_issues)
        self.assertTrue(
            any("missing required suite result for desktop-release-smoke" in issue for issue in missing_suite_issues)
        )

    def test_release_platform_evidence_requires_every_matrix_suite_result(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke", "python-service-contract"],
        }
        payload = {
            "target_id": "ubuntu-24_04-x64",
            "status": "passed",
            "suite_results": [{"name": "native-build-smoke", "status": "passed"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "ubuntu-24_04-x64.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            missing_suite_issues = release_platform_matrix._evidence_issues([target], evidence_dir)
            payload["suite_results"].append({"name": "python-service-contract", "status": "passed"})
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            fixed_issues = release_platform_matrix._evidence_issues([target], evidence_dir)
            payload["suite_results"][0]["name"] = "rust-workspace-check"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            legacy_alias_issues = release_platform_matrix._evidence_issues([target], evidence_dir)

        self.assertTrue(
            any("missing required suite result for python-service-contract" in issue for issue in missing_suite_issues)
        )
        self.assertEqual([], fixed_issues)
        self.assertEqual([], legacy_alias_issues)

    def test_release_platform_source_binding_rejects_stale_or_dirty_target_artifacts(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke"],
        }
        payload = {
            **_target_evidence_payload(target),
            "commit": "current-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "runtime_ready_claimed": False,
            "secrets_redacted": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "ubuntu-24_04-x64.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                valid = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

            payload["commit"] = "old-commit"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                stale_commit = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

            payload["commit"] = "current-commit"
            payload["source_tree_clean"] = False
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                dirty_source = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

            payload["source_tree_clean"] = True
            payload["python_source_contract_hash"] = "0" * 64
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                stale_contract = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

            payload["python_source_contract_hash"] = PYTHON_SOURCE_CONTRACT_HASH
            del payload["native_source_sync"]
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                missing_native_source_sync = release_evidence._release_platform_source_binding_issues(
                    [target], evidence_dir
                )

            payload["native_source_sync"] = _native_source_sync_binding("0" * 64)
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                stale_native_source_sync = release_evidence._release_platform_source_binding_issues(
                    [target], evidence_dir
                )

            payload["native_source_sync"] = _native_source_sync_binding()
            del payload["native_source_sync"]["surface_contract_required"]
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                partial_native_source_sync = release_evidence._release_platform_source_binding_issues(
                    [target], evidence_dir
                )

            payload["native_source_sync"] = _native_source_sync_binding()
            payload["runtime_ready_claimed"] = True
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                runtime_claim = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

            payload["runtime_ready_claimed"] = False
            payload["secrets_redacted"] = False
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(release_evidence, "_current_git_commit", return_value="current-commit"):
                unredacted = release_evidence._release_platform_source_binding_issues([target], evidence_dir)

        self.assertEqual([], valid)
        self.assertTrue(any("commit must match current git commit" in issue for issue in stale_commit))
        self.assertTrue(any("source_tree_clean must be true" in issue for issue in dirty_source))
        self.assertTrue(any("python_source_contract_hash must match" in issue for issue in stale_contract))
        self.assertTrue(
            any("native_source_sync must be a non-empty object" in issue for issue in missing_native_source_sync)
        )
        self.assertTrue(
            any(
                "native_source_sync.contract_hash must match current Python source contract" in issue
                for issue in stale_native_source_sync
            )
        )
        self.assertTrue(
            any(
                "native_source_sync.surface_contract_required must be true" in issue
                for issue in partial_native_source_sync
            )
        )
        self.assertTrue(any("runtime_ready_claimed must be false" in issue for issue in runtime_claim))
        self.assertTrue(any("secrets_redacted must be true" in issue for issue in unredacted))

    def test_importer_platform_source_binding_requires_native_source_sync(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke"],
        }
        payload = {
            **_target_evidence_payload(target),
            "commit": "current-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "runtime_ready_claimed": False,
            "secrets_redacted": True,
        }

        def validate_candidate(candidate_payload: dict[str, object]) -> list[str]:
            candidate = evidence_importer.JsonCandidate(
                source="release-platform-evidence/ubuntu-24_04-x64.json",
                name="ubuntu-24_04-x64.json",
                payload=candidate_payload,
            )
            with (
                patch.object(evidence_importer.runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(evidence_importer.runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                return evidence_importer._validate_platform_source_binding(
                    candidate,
                    require_current_commit=True,
                    require_clean_source=True,
                )

        valid = validate_candidate(payload)
        missing_binding_payload = json.loads(json.dumps(payload))
        del missing_binding_payload["native_source_sync"]
        missing_binding = validate_candidate(missing_binding_payload)
        stale_binding_payload = json.loads(json.dumps(payload))
        stale_binding_payload["native_source_sync"]["contract_hash"] = "0" * 64
        stale_binding = validate_candidate(stale_binding_payload)
        partial_binding_payload = json.loads(json.dumps(payload))
        del partial_binding_payload["native_source_sync"]["audit_path"]
        partial_binding = validate_candidate(partial_binding_payload)

        self.assertEqual([], valid)
        self.assertTrue(any("native_source_sync must be a non-empty object" in issue for issue in missing_binding))
        self.assertTrue(
            any(
                "native_source_sync.contract_hash must match current Python source contract" in issue
                for issue in stale_binding
            )
        )
        self.assertTrue(any("native_source_sync.audit_path must be" in issue for issue in partial_binding))

    def test_release_platform_probe_writes_source_binding_fields(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke"],
        }
        suite_results = [{"name": "native-build-smoke", "status": "passed"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ubuntu-24_04-x64.json"
            stdout = io.StringIO()
            with (
                patch.object(release_platform_probe, "_find_target", return_value=target),
                patch.object(release_platform_probe, "_suite_results", return_value=suite_results),
                patch.object(release_platform_probe, "_current_git_commit", return_value="abc123"),
                patch.object(release_platform_probe, "_source_tree_clean", return_value=True),
                patch.object(
                    release_platform_probe,
                    "native_python_source_contract_hash",
                    return_value=PYTHON_SOURCE_CONTRACT_HASH,
                ),
                contextlib.redirect_stdout(stdout),
            ):
                returncode = release_platform_probe.main(
                    [
                        "--target-id",
                        "ubuntu-24_04-x64",
                        "--output",
                        str(output_path),
                    ]
                )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(0, returncode)
        self.assertEqual("abc123", payload["commit"])
        self.assertTrue(payload["source_tree_clean"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, payload["python_source_contract_hash"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, payload["native_source_sync"]["contract_hash"])
        self.assertFalse(payload["runtime_ready_claimed"])
        self.assertTrue(payload["secrets_redacted"])

    def test_release_platform_probe_requires_native_source_sync_before_writing(self):
        failed_source_sync = _valid_source_sync_audit_payload("fresh-hash")
        failed_source_sync["ok"] = False
        failed_source_sync["issues"] = ["generated platform parity artifact is stale"]
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "release-platform-evidence" / "windows-11-x64.json"
            with (
                patch.object(release_platform_probe, "_source_tree_clean", return_value=True),
                patch.object(release_platform_probe, "audit_native_source_sync", return_value=failed_source_sync),
                patch.object(release_platform_probe, "_run_probe", side_effect=AssertionError("probe should not run")),
                contextlib.redirect_stdout(stdout),
            ):
                returncode = release_platform_probe.main(
                    [
                        "--target-id",
                        "windows-11-x64",
                        "--matrix",
                        str(REPO_ROOT / "docs" / "release-platform-test-matrix.json"),
                        "--require-clean-source",
                        "--require-native-source-sync",
                        "--output",
                        str(output_path),
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(1, returncode)
        self.assertFalse(payload["ok"])
        self.assertFalse(output_path.exists())
        self.assertFalse(payload["native_source_sync_guard"]["ok"])
        self.assertIn("generated platform parity artifact is stale", payload["issues"])

    def test_release_platform_probe_writes_relative_outputs_under_repo_root(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke"],
        }
        suite_results = [{"name": "native-build-smoke", "status": "passed"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected_path = root / "release-platform-evidence" / "ubuntu-24_04-x64.json"
            with (
                patch.object(release_platform_probe, "_suite_results", return_value=suite_results),
                patch.object(release_platform_probe, "_current_git_commit", return_value="abc123"),
                patch.object(release_platform_probe, "_source_tree_clean", return_value=True),
                patch.object(
                    release_platform_probe,
                    "native_python_source_contract_hash",
                    return_value=PYTHON_SOURCE_CONTRACT_HASH,
                ),
            ):
                result = release_platform_probe._run_probe(
                    target,
                    output=Path("release-platform-evidence") / "ubuntu-24_04-x64.json",
                    root=root,
                )
            payload = json.loads(expected_path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual(str(expected_path), result["output"])
        self.assertEqual("abc123", payload["commit"])
        self.assertEqual([], result["source_control_write_guard"]["non_generated_in_repo_write_targets"])

    def test_release_platform_probe_refuses_in_repo_nongenerated_output_before_running_suites(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "test_suites": ["native-build-smoke"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_path = root / "docs" / "ubuntu-24_04-x64.json"
            stdout = io.StringIO()
            with (
                patch.object(release_platform_probe, "_repo_root", return_value=root),
                patch.object(release_platform_probe, "_find_target", return_value=target),
                patch.object(
                    release_platform_probe,
                    "_suite_results",
                    side_effect=AssertionError("suite should not run after source-control guard failure"),
                ),
                contextlib.redirect_stdout(stdout),
            ):
                returncode = release_platform_probe.main(
                    [
                        "--target-id",
                        "ubuntu-24_04-x64",
                        "--output",
                        "docs/ubuntu-24_04-x64.json",
                    ]
                )
            result = json.loads(stdout.getvalue())
            output_exists = output_path.exists()

        self.assertEqual(1, returncode)
        self.assertFalse(output_exists)
        self.assertFalse(result["ok"])
        self.assertEqual(
            ["docs/ubuntu-24_04-x64.json"],
            result["source_control_write_guard"]["non_generated_in_repo_write_targets"],
        )
        self.assertTrue(
            any("outside generated evidence directories inside the repository" in issue for issue in result["issues"])
        )

    def test_release_platform_probe_uses_checked_in_chrome_browser_harness_by_default(self):
        target = {
            "id": "browser-chrome-windows-11-x64",
            "kind": "browser",
            "browser": "chrome",
            "test_suites": ["browser-contract"],
        }
        expected_command = [
            "npm.cmd",
            "--prefix",
            "apps/web-dashboard",
            "run",
            "test:browser",
            "--",
            "--browser=chrome",
        ]

        with (
            patch.dict(release_platform_probe.os.environ, {}, clear=True),
            patch.object(release_platform_probe.shutil, "which", return_value="npm.cmd"),
            patch.object(
                release_platform_probe,
                "_run_command",
                return_value={"name": "browser-contract", "status": "passed", "command": expected_command},
            ) as run_command,
        ):
            results = release_platform_probe._suite_results(target, root=REPO_ROOT)

        self.assertEqual("passed", results[0]["status"])
        run_command.assert_called_once()
        self.assertEqual("browser-contract", run_command.call_args.args[0])
        self.assertEqual(expected_command, run_command.call_args.args[1])

    def test_release_platform_probe_detects_current_browser_host(self):
        self.assertEqual(
            "windows-11-x64",
            release_platform_probe._current_browser_host(
                {
                    "system": "Windows",
                    "release": "11",
                    "normalized_architecture": "x64",
                }
            ),
        )
        self.assertEqual(
            "ubuntu-24_04-arm64",
            release_platform_probe._current_browser_host(
                {
                    "system": "Linux",
                    "os_release_id": "ubuntu",
                    "os_release_version_id": "24.04",
                    "normalized_architecture": "arm64",
                }
            ),
        )
        self.assertEqual(
            "macos-15-arm64",
            release_platform_probe._current_browser_host(
                {
                    "system": "Darwin",
                    "macos_version": "15.6.1",
                    "normalized_architecture": "arm64",
                }
            ),
        )

    def test_release_platform_probe_selects_only_current_host_builtin_browser_targets(self):
        with (
            patch.object(release_platform_probe, "_current_browser_host", return_value="windows-11-x64"),
            patch.object(release_platform_probe.shutil, "which", return_value="npm.cmd"),
        ):
            targets = release_platform_probe._local_browser_targets(
                REPO_ROOT / "docs" / "release-platform-test-matrix.json"
            )

        self.assertEqual(
            [
                "browser-chrome-windows_11_x64",
                "browser-edge-windows_11_x64",
                "browser-firefox-windows_11_x64",
            ],
            sorted(str(target["id"]) for target in targets),
        )
        self.assertTrue(all(str(target["host"]) == "windows-11-x64" for target in targets))
        self.assertIn("firefox", {str(target.get("browser")) for target in targets})
        self.assertNotIn("internet-explorer", {str(target.get("browser")) for target in targets})

    def test_release_matrix_maps_browser_targets_to_matching_declared_runners(self):
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, browser_targets, issues = release_platform_matrix._validate_matrix(matrix)

        self.assertEqual([], issues)
        windows_platform = next(target for target in platform_targets if target["id"] == "windows-11-x64")
        self.assertEqual("self-hosted-windows-11", windows_platform["runner_kind"])
        self.assertEqual(
            ["self-hosted", "windows", "x64", "tb-release-platform", "windows-11-x64"],
            windows_platform["runner_labels"],
        )
        expected_labels = {
            "windows-11-x64": ["self-hosted", "windows", "x64", "tb-release-platform", "windows-11-x64"],
            "ubuntu-24_04-x64": ["ubuntu-24.04"],
            "macos-15-arm64": ["macos-15"],
        }
        expected_kinds = {
            "windows-11-x64": "self-hosted-windows-11",
            "ubuntu-24_04-x64": "github-hosted",
            "macos-15-arm64": "github-hosted",
        }
        for target in browser_targets:
            self.assertEqual(expected_kinds[target["host"]], target["runner_kind"])
            self.assertEqual(expected_labels[target["host"]], target["runner_labels"])

    def test_release_platform_probe_local_browser_batch_writes_per_target_outputs(self):
        targets = [
            {"id": "browser-chrome-windows_11_x64", "kind": "browser", "browser": "chrome"},
            {"id": "browser-edge-windows_11_x64", "kind": "browser", "browser": "edge"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()

            def _run_probe_stub(target: dict[str, object], *, output: Path, root: Path) -> dict[str, object]:
                return {"ok": True, "target_id": target["id"], "output": str(output)}

            with (
                contextlib.redirect_stdout(output),
                patch.object(release_platform_probe, "_current_browser_host", return_value="windows-11-x64"),
                patch.object(release_platform_probe, "_local_browser_targets", return_value=targets),
                patch.object(release_platform_probe, "_run_probe", side_effect=_run_probe_stub) as run_probe,
            ):
                exit_code = release_platform_probe.main(
                    [
                        "--local-browser-targets",
                        "--output-dir",
                        temp_dir,
                    ]
                )

            payload = json.loads(output.getvalue())

        self.assertEqual(0, exit_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("windows-11-x64", payload["host"])
        self.assertEqual(2, payload["count"])
        self.assertEqual(2, run_probe.call_count)
        self.assertEqual(
            [
                str(Path(temp_dir) / "browser-chrome-windows_11_x64.json"),
                str(Path(temp_dir) / "browser-edge-windows_11_x64.json"),
            ],
            [row["output"] for row in payload["outputs"]],
        )

    def test_release_platform_probe_local_browser_batch_can_require_clean_source(self):
        targets = [
            {"id": "browser-chrome-windows_11_x64", "kind": "browser", "browser": "chrome"},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output = io.StringIO()

            with (
                contextlib.redirect_stdout(output),
                patch.object(release_platform_probe, "_source_tree_clean", return_value=False),
                patch.object(release_platform_probe, "_current_browser_host", return_value="windows-11-x64"),
                patch.object(release_platform_probe, "_local_browser_targets", return_value=targets),
                patch.object(release_platform_probe, "_run_probe") as run_probe,
            ):
                exit_code = release_platform_probe.main(
                    [
                        "--local-browser-targets",
                        "--require-clean-source",
                        "--output-dir",
                        temp_dir,
                    ]
                )

            payload = json.loads(output.getvalue())

        self.assertEqual(1, exit_code)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["source_tree_clean"])
        self.assertEqual("windows-11-x64", payload["host"])
        self.assertTrue(any("source tree must be clean" in issue for issue in payload["issues"]))
        run_probe.assert_not_called()

    def test_release_platform_probe_keeps_browser_env_override_for_external_labs(self):
        target = {
            "id": "browser-firefox-windows-11-x64",
            "kind": "browser",
            "browser": "firefox",
            "test_suites": ["browser-contract"],
        }
        override = "external-firefox-lab --prove-real-browser"
        expected_command = ["cmd", "/c", override] if sys.platform == "win32" else ["sh", "-lc", override]

        with (
            patch.dict(release_platform_probe.os.environ, {"TB_BROWSER_TEST_COMMAND": override}, clear=True),
            patch.object(
                release_platform_probe,
                "_run_command",
                return_value={"name": "browser-contract", "status": "passed", "command": expected_command},
            ) as run_command,
        ):
            results = release_platform_probe._suite_results(target, root=REPO_ROOT)

        self.assertEqual("passed", results[0]["status"])
        run_command.assert_called_once()
        self.assertEqual(expected_command, run_command.call_args.args[1])

    def test_release_platform_probe_uses_builtin_firefox_command(self):
        target = {
            "id": "browser-firefox-windows-11-x64",
            "kind": "browser",
            "browser": "firefox",
            "test_suites": ["browser-contract"],
        }

        with (
            patch.dict(release_platform_probe.os.environ, {}, clear=True),
            patch.object(release_platform_probe.shutil, "which", return_value="npm.cmd"),
            patch.object(
                release_platform_probe,
                "_run_command",
                return_value={"name": "browser-contract", "status": "passed"},
            ) as run_command,
        ):
            results = release_platform_probe._suite_results(target, root=REPO_ROOT)

        self.assertEqual("passed", results[0]["status"])
        self.assertEqual(
            ["npm.cmd", "--prefix", "apps/web-dashboard", "run", "test:browser", "--", "--browser=firefox"],
            run_command.call_args.args[1],
        )

    def test_release_platform_probe_uses_builtin_native_desktop_smoke(self):
        target = {
            "id": "windows-11-x64",
            "kind": "platform",
            "test_suites": ["desktop-release-smoke"],
        }

        with (
            patch.dict(release_platform_probe.os.environ, {}, clear=True),
            patch.object(
                release_platform_probe,
                "_run_command",
                return_value={"name": "desktop-release-smoke", "status": "passed"},
            ) as run_command,
        ):
            results = release_platform_probe._suite_results(target, root=REPO_ROOT)

        self.assertEqual("passed", results[0]["status"])
        self.assertEqual(
            [
                sys.executable,
                "tools/check_native_cpp.py",
                "--config",
                "Release",
                "--timeout",
                "600",
            ],
            run_command.call_args.args[1],
        )
        self.assertEqual(900, run_command.call_args.kwargs["timeout"])

    def test_release_platform_probe_builds_and_smokes_both_required_rust_binaries(self):
        target = {
            "id": "ubuntu-24_04-x64",
            "kind": "platform",
            "family": "ubuntu",
            "architecture": "x64",
            "test_suites": ["native-build-smoke"],
        }

        with (
            patch.object(release_platform_probe.shutil, "which", return_value="cargo"),
            patch.object(release_platform_probe, "_current_git_commit", return_value="a" * 40),
            patch.object(
                release_platform_probe,
                "_run_command",
                side_effect=[
                    {"name": "rust-workspace-check", "status": "passed"},
                    {"name": "rust-workspace-tests", "status": "passed"},
                    {"name": "rust-release-build", "status": "passed"},
                    {"name": "rust-package-smoke", "status": "passed"},
                ],
            ) as run_command,
        ):
            results = release_platform_probe._suite_results(target, root=REPO_ROOT)

        self.assertEqual(["rust-workspace-check", "native-build-smoke"], [row["name"] for row in results])
        self.assertEqual(
            [
                "cargo",
                "check",
                "--manifest-path",
                "experiments/rust-shells/Cargo.toml",
                "--locked",
                "--workspace",
            ],
            run_command.call_args_list[0].args[1],
        )
        self.assertEqual(
            [
                "cargo",
                "test",
                "--manifest-path",
                "experiments/rust-shells/Cargo.toml",
                "--locked",
                "--workspace",
            ],
            run_command.call_args_list[1].args[1],
        )
        self.assertEqual(
            [
                "cargo",
                "build",
                "--manifest-path",
                "experiments/rust-shells/Cargo.toml",
                "--locked",
                "--release",
                "--package",
                "trading-bot-rust",
                "--package",
                "trading-bot-tauri-desktop",
            ],
            run_command.call_args_list[2].args[1],
        )
        package_command = run_command.call_args_list[3].args[1]
        self.assertIn("tools/write_rust_package_smoke_evidence.py", package_command)
        self.assertIn("trading-bot-rust", " ".join(package_command))
        self.assertIn("trading-bot-tauri-desktop", " ".join(package_command))
        self.assertIn("--require-clean-source", package_command)

    def test_release_platform_probe_stops_native_build_after_workspace_test_failure(self):
        target = {
            "id": "macos-15-arm64",
            "kind": "platform",
            "family": "macos",
            "architecture": "arm64",
            "test_suites": ["native-build-smoke"],
        }
        with patch.object(
            release_platform_probe,
            "_run_command",
            return_value={"name": "rust-workspace-tests", "status": "failed"},
        ) as run_command:
            result = release_platform_probe._rust_native_build_smoke(
                "cargo",
                target,
                root=REPO_ROOT,
            )

        self.assertEqual("failed", result["status"])
        self.assertEqual("rust-workspace-tests failed", result["stderr"])
        run_command.assert_called_once()

    def test_native_cpp_desktop_smoke_uses_offscreen_qt_on_non_windows_hosts(self):
        with patch.dict(native_cpp.os.environ, {}, clear=True), patch.object(native_cpp.sys, "platform", "linux"):
            environment = native_cpp._desktop_smoke_env(REPO_ROOT / "missing-build", "Release")
        self.assertEqual("offscreen", environment["QT_QPA_PLATFORM"])

        with patch.dict(native_cpp.os.environ, {}, clear=True), patch.object(native_cpp.sys, "platform", "win32"):
            environment = native_cpp._desktop_smoke_env(REPO_ROOT / "missing-build", "Release")
        self.assertNotIn("QT_QPA_PLATFORM", environment)

    def test_native_cpp_uses_requested_release_build_type_with_single_config_generators(self):
        with (
            patch.object(native_cpp.sys, "platform", "linux"),
            patch.object(native_cpp.shutil, "which", side_effect=["cmake", "ctest"]),
            patch.object(native_cpp, "_run_step", return_value={"ok": True}) as run_step,
        ):
            report = native_cpp.check_native_cpp(
                build_dir=REPO_ROOT / "build" / "test-native-release",
                config="Release",
                require_webengine=True,
                enable_qt_deploy_script=None,
                smoke_targets_only=True,
                qt_version=None,
                timeout=30,
            )

        self.assertTrue(report["ok"])
        configure_command = run_step.call_args_list[0].args[1]
        self.assertIn("-DCMAKE_BUILD_TYPE=Release", configure_command)

    def test_native_cpp_serializes_windows_builds_to_avoid_pdb_contention(self):
        with (
            patch.object(native_cpp.sys, "platform", "win32"),
            patch.object(native_cpp.shutil, "which", side_effect=["cmake", "ctest"]),
            patch.object(native_cpp, "_run_step", return_value={"ok": True}) as run_step,
        ):
            report = native_cpp.check_native_cpp(
                build_dir=REPO_ROOT / "build" / "test-native-windows",
                config="Debug",
                require_webengine=True,
                enable_qt_deploy_script=None,
                smoke_targets_only=True,
                qt_version=None,
                timeout=30,
            )

        self.assertTrue(report["ok"])
        for call in run_step.call_args_list[1:3]:
            self.assertEqual(["--parallel", "1"], call.args[1][-2:])

    def test_release_platform_cli_target_filter_limits_evidence_validation(self):
        payload = {
            "target_id": "windows-11-x64",
            "status": "passed",
            "suite_results": [
                {
                    "name": "platform-probe",
                    "status": "passed",
                    "target_match": {"matched": True, "issues": []},
                },
                {"name": "python-service-contract", "status": "passed"},
                {"name": "desktop-release-smoke", "status": "passed"},
                {"name": "native-build-smoke", "status": "passed"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            (evidence_dir / "windows-11-x64.json").write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                returncode = release_platform_matrix.main(
                    [
                        "--matrix",
                        str(REPO_ROOT / "docs" / "release-platform-test-matrix.json"),
                        "--require-evidence",
                        "--evidence-dir",
                        str(evidence_dir),
                        "--target-filter",
                        "windows-11-x64",
                        "--json",
                    ]
                )
            report = json.loads(stdout.getvalue())

        self.assertEqual(0, returncode)
        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(1, report["target_count"])
        self.assertGreater(report["total_target_count"], report["target_count"])
        self.assertEqual("windows-11-x64", report["target_filter"])

    def test_release_platform_cli_emits_all_targets_and_scopes_runner_overrides(self):
        matrix_path = str(REPO_ROOT / "docs" / "release-platform-test-matrix.json")

        all_stdout = io.StringIO()
        with contextlib.redirect_stdout(all_stdout):
            all_code = release_platform_matrix.main(["--matrix", matrix_path, "--emit-github-matrix"])
        all_matrix = json.loads(all_stdout.getvalue())

        focused_stdout = io.StringIO()
        with contextlib.redirect_stdout(focused_stdout):
            focused_code = release_platform_matrix.main(
                [
                    "--matrix",
                    matrix_path,
                    "--emit-github-matrix",
                    "--target-filter",
                    "browser-edge-windows_11_x64",
                    "--runner-labels-json",
                    '["self-hosted","tb-release-platform","windows-11-x64"]',
                ]
            )
        focused_matrix = json.loads(focused_stdout.getvalue())

        invalid_stdout = io.StringIO()
        with contextlib.redirect_stdout(invalid_stdout):
            invalid_code = release_platform_matrix.main(
                [
                    "--matrix",
                    matrix_path,
                    "--emit-github-matrix",
                    "--runner-labels-json",
                    '["self-hosted"]',
                ]
            )
        invalid_matrix = json.loads(invalid_stdout.getvalue())

        self.assertEqual(0, all_code)
        self.assertEqual(12, len(all_matrix["include"]))
        self.assertIn(
            "browser-edge-windows_11_x64",
            {item["target_id"] for item in all_matrix["include"]},
        )
        self.assertEqual(0, focused_code)
        self.assertEqual(
            [
                {
                    "target_id": "browser-edge-windows_11_x64",
                    "kind": "browser",
                    "runner_kind": "self-hosted-windows-11",
                    "runner_labels_json": '["self-hosted","tb-release-platform","windows-11-x64"]',
                    "test_suites": "browser-contract",
                }
            ],
            focused_matrix["include"],
        )
        self.assertEqual(1, invalid_code)
        self.assertEqual([], invalid_matrix["include"])

    def test_release_platform_cli_promotion_flags_require_source_bound_target_evidence(self):
        matrix = release_platform_matrix._load_json(REPO_ROOT / "docs" / "release-platform-test-matrix.json")
        platform_targets, browser_targets, matrix_issues = release_platform_matrix._validate_matrix(matrix)
        self.assertEqual([], matrix_issues)
        targets = platform_targets + browser_targets
        windows_target = next(target for target in targets if target["id"] == "windows-11-x64")
        payload = {
            **_target_evidence_payload(windows_target),
            "commit": "current-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "runtime_ready_claimed": False,
            "secrets_redacted": True,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / "windows-11-x64.json"

            def run_check() -> tuple[int, dict[str, object]]:
                evidence_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = io.StringIO()
                with (
                    patch.object(release_platform_matrix, "_current_git_commit", return_value="current-commit"),
                    patch.object(release_platform_matrix, "_current_source_tree_clean", return_value=True),
                    contextlib.redirect_stdout(stdout),
                ):
                    returncode = release_platform_matrix.main(
                        [
                            "--matrix",
                            str(REPO_ROOT / "docs" / "release-platform-test-matrix.json"),
                            "--require-evidence",
                            "--require-current-commit",
                            "--require-clean-source",
                            "--evidence-dir",
                            str(evidence_dir),
                            "--target-filter",
                            "windows-11-x64",
                            "--json",
                        ]
                    )
                return returncode, json.loads(stdout.getvalue())

            valid_code, valid = run_check()
            payload["commit"] = "old-commit"
            stale_code, stale = run_check()
            payload["commit"] = "current-commit"
            payload["source_tree_clean"] = False
            dirty_code, dirty = run_check()
            payload["source_tree_clean"] = True
            payload["python_source_contract_hash"] = "0" * 64
            stale_contract_code, stale_contract = run_check()
            payload["python_source_contract_hash"] = PYTHON_SOURCE_CONTRACT_HASH
            del payload["native_source_sync"]
            missing_source_sync_code, missing_source_sync = run_check()
            payload["native_source_sync"] = _native_source_sync_binding("0" * 64)
            stale_source_sync_code, stale_source_sync = run_check()
            payload["native_source_sync"] = _native_source_sync_binding()
            payload["commit"] = ["current-commit"]
            wrong_commit_type_code, wrong_commit_type = run_check()
            payload["commit"] = "current-commit"
            payload["secrets_redacted"] = "true"
            wrong_bool_type_code, wrong_bool_type = run_check()

        self.assertEqual(0, valid_code, valid["issues"])
        self.assertTrue(valid["ok"], valid["issues"])
        self.assertTrue(valid["require_current_commit"])
        self.assertTrue(valid["require_clean_source"])
        self.assertEqual("current-commit", valid["current_commit"])
        self.assertEqual(PYTHON_SOURCE_CONTRACT_HASH, valid["current_python_source_contract_hash"])
        self.assertTrue(valid["current_source_tree_clean"])
        self.assertEqual(1, stale_code)
        self.assertFalse(stale["ok"])
        self.assertTrue(any("commit must match current git commit" in issue for issue in stale["issues"]))
        self.assertEqual(1, dirty_code)
        self.assertFalse(dirty["ok"])
        self.assertTrue(any("source_tree_clean must be true" in issue for issue in dirty["issues"]))
        self.assertEqual(1, stale_contract_code)
        self.assertFalse(stale_contract["ok"])
        self.assertTrue(
            any(
                "python_source_contract_hash must match current Python source contract" in issue
                for issue in stale_contract["issues"]
            )
        )
        self.assertEqual(1, missing_source_sync_code)
        self.assertFalse(missing_source_sync["ok"])
        self.assertTrue(
            any("native_source_sync must be a non-empty object" in issue for issue in missing_source_sync["issues"])
        )
        self.assertEqual(1, stale_source_sync_code)
        self.assertFalse(stale_source_sync["ok"])
        self.assertTrue(
            any(
                "native_source_sync.contract_hash must match current Python source contract" in issue
                for issue in stale_source_sync["issues"]
            )
        )
        self.assertEqual(1, wrong_commit_type_code)
        self.assertFalse(wrong_commit_type["ok"])
        self.assertTrue(any("commit must be a string" in issue for issue in wrong_commit_type["issues"]))
        self.assertEqual(1, wrong_bool_type_code)
        self.assertFalse(wrong_bool_type["ok"])
        self.assertTrue(any("secrets_redacted must be boolean" in issue for issue in wrong_bool_type["issues"]))

    def test_release_platform_probe_rejects_wrong_observed_platform(self):
        target = {
            "family": "windows",
            "version": "11",
            "architecture": "x64",
        }
        observed = {
            "system": "Linux",
            "release": "6.8",
            "normalized_architecture": "x64",
            "os_release_id": "ubuntu",
            "os_release_version_id": "24.04",
        }

        issues = release_platform_probe._platform_match_issues(target, observed)

        self.assertTrue(any("system mismatch" in issue for issue in issues))

    def test_recovery_evidence_filter_validates_only_deterministic_local_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            for evidence_id in sorted(local_recovery.RECOVERY_EVIDENCE_IDS):
                payload = {
                    "evidence_id": evidence_id,
                    "status": "passed",
                    "evidence_scope": "deterministic_local",
                    "generated_at": "unix:1",
                    "commit": "abc123",
                    "source_tree_clean": True,
                    "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
                    "native_source_sync": _native_source_sync_binding(),
                    "command": "cargo run -p trading-bot-rust -- --write-local-recovery-evidence",
                    "environment": {"scope": "deterministic_local"},
                    "secrets_redacted": True,
                    "runtime_ready_claimed": False,
                    "recovery_scenarios": [{"name": "scenario", "status": "passed"}],
                    "suite_results": [{"name": "suite", "status": "passed"}],
                }
                (evidence_dir / f"{evidence_id}.json").write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            filtered = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids=set(local_recovery.RECOVERY_EVIDENCE_IDS),
            )
            unfiltered = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
            )
            local_check = local_recovery.check_local_recovery_evidence(
                manifest_path=runtime_evidence.DEFAULT_MANIFEST_PATH,
                evidence_dir=evidence_dir,
                validate_only=True,
                timeout=1,
            )

        self.assertTrue(filtered["ok"], filtered["issues"])
        self.assertEqual(sorted(local_recovery.RECOVERY_EVIDENCE_IDS), filtered["validated_evidence_ids"])
        self.assertEqual(2, len(filtered["artifact_status"]))
        self.assertTrue(all(row["ok"] for row in filtered["artifact_status"]))
        self.assertFalse(unfiltered["ok"])
        self.assertTrue(any("rust-native-live-market-data-smoke" in issue for issue in unfiltered["issues"]))
        remaining = [row["id"] for row in unfiltered["artifact_status"] if not row["ok"]]
        self.assertIn("rust-native-live-market-data-smoke", remaining)
        self.assertIn("rust-native-release-platform-evidence", remaining)
        self.assertTrue(local_check["ok"], local_check["issues"])

    def test_runtime_evidence_can_require_current_git_commit(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "current-commit",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / f"{evidence_id}.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                fresh = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    evidence_dir_override=evidence_dir,
                    requirement_ids={evidence_id},
                )

            payload["commit"] = "stale-commit"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                stale = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    evidence_dir_override=evidence_dir,
                    requirement_ids={evidence_id},
                )

            payload["commit"] = "current-commit"
            payload["source_tree_clean"] = False
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                dirty_artifact = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    evidence_dir_override=evidence_dir,
                    requirement_ids={evidence_id},
                )

            payload["source_tree_clean"] = True
            payload["python_source_contract_hash"] = "0" * 64
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(runtime_evidence, "_current_git_commit", return_value="current-commit"),
                patch.object(runtime_evidence, "_current_source_tree_clean", return_value=True),
            ):
                stale_python_contract = runtime_evidence.validate(
                    runtime_evidence.DEFAULT_MANIFEST_PATH,
                    require_evidence=True,
                    require_current_commit=True,
                    require_clean_source=True,
                    evidence_dir_override=evidence_dir,
                    requirement_ids={evidence_id},
                )

        self.assertTrue(fresh["ok"], fresh["issues"])
        self.assertFalse(stale["ok"])
        self.assertTrue(any("commit must match current git commit" in issue for issue in stale["issues"]))
        self.assertFalse(dirty_artifact["ok"])
        self.assertTrue(any("source_tree_clean must be true" in issue for issue in dirty_artifact["issues"]))
        self.assertFalse(stale_python_contract["ok"])
        self.assertTrue(
            any(
                "python_source_contract_hash must match current Python source contract" in issue
                for issue in stale_python_contract["issues"]
            )
        )

    def test_runtime_evidence_enforces_manifest_declared_artifact_fields(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / f"{evidence_id}.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            valid = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            del payload["command"]
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            missing_field = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["command"] = "cargo run -p trading-bot-rust -- --native-live-market-smoke"
            payload["source_tree_clean"] = "true"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            wrong_type = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["source_tree_clean"] = True
            payload["command"] = ["cargo", "run", "-p", "trading-bot-rust"]
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            wrong_string_type = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(missing_field["ok"])
        self.assertTrue(any("missing required artifact field: command" in issue for issue in missing_field["issues"]))
        self.assertFalse(wrong_type["ok"])
        self.assertTrue(any("source_tree_clean must be boolean" in issue for issue in wrong_type["issues"]))
        self.assertFalse(wrong_string_type["ok"])
        self.assertTrue(any("command must be a string" in issue for issue in wrong_string_type["issues"]))

    def test_runtime_evidence_requires_machine_readable_generated_at(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / f"{evidence_id}.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            valid = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["generated_at"] = "2026-06-20T00:00:00Z"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            bad_format = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["generated_at"] = "unix:0"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            bad_seconds = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(bad_format["ok"])
        self.assertTrue(any("generated_at must use unix:<seconds> format" in issue for issue in bad_format["issues"]))
        self.assertFalse(bad_seconds["ok"])
        self.assertTrue(
            any("generated_at must contain positive unix seconds" in issue for issue in bad_seconds["issues"])
        )

    def test_runtime_evidence_enforces_live_smoke_endpoint_contracts(self):
        market_id = "rust-native-live-market-data-smoke"
        account_id = "rust-native-live-account-read-smoke"
        market_payload = {
            "evidence_id": market_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }
        account_payload = {
            "evidence_id": account_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "account_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
                "api_key_present": True,
                "api_secret_present": True,
                "signed_account_read": True,
                "secrets_in_artifact": False,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _account_smoke_endpoints(),
            "suite_results": _account_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            market_path = evidence_dir / f"{market_id}.json"
            account_path = evidence_dir / f"{account_id}.json"
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            valid_market = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            market_payload["endpoints"] = [
                endpoint for endpoint in _market_smoke_endpoints() if endpoint["name"] != "klines"
            ]
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            missing_market_endpoint = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            market_payload["endpoints"] = _market_smoke_endpoints("https://fapi.binance.com")
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            wrong_market_scope = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            valid_account = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

            account_payload["endpoints"] = [
                endpoint for endpoint in _account_smoke_endpoints() if endpoint["name"] != "positionRisk"
            ]
            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            missing_account_endpoint = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

            market_payload["endpoints"] = _market_smoke_endpoints()
            market_payload["suite_results"] = [
                row for row in _market_smoke_suite_results() if row["name"] != "fetch_klines"
            ]
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            missing_market_suite = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            market_payload["suite_results"] = _market_smoke_suite_results()
            market_payload["suite_results"][-1]["computed_indicator_keys"] = []
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            missing_native_rsi = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            market_payload["suite_results"] = _market_smoke_suite_results()
            market_payload["suite_results"][-1]["unsupported_indicator_keys"] = ["supertrend"]
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            unsupported_native_indicator = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            market_payload["suite_results"] = _market_smoke_suite_results()
            market_payload["suite_results"][-1]["websocket_connected"] = False
            market_payload["suite_results"][-1]["websocket_url"] = ""
            market_payload["suite_results"][-1]["websocket_timeout_ms"] = 0
            market_payload["suite_results"][-1]["websocket_poll_status"] = "rest"
            market_payload["suite_results"][-1]["websocket_event_kind"] = ""
            market_path.write_text(json.dumps(market_payload), encoding="utf-8")
            missing_websocket_observation = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={market_id},
            )

            account_payload["endpoints"] = _account_smoke_endpoints()
            account_payload["suite_results"] = _account_smoke_suite_results()
            account_payload["suite_results"][2]["balances_redacted"] = False
            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            unredacted_balance = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

            account_payload["suite_results"] = [
                row for row in _account_smoke_suite_results() if row["name"] != "fetch_usdt_balance"
            ]
            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            missing_account_suite = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

            account_payload["suite_results"] = _account_smoke_suite_results()
            del account_payload["environment"]["api_key_present"]
            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            missing_credential_metadata = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

            account_payload["environment"]["api_key_present"] = True
            account_payload["environment"]["secrets_in_artifact"] = True
            account_path.write_text(json.dumps(account_payload), encoding="utf-8")
            secret_artifact_metadata = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={account_id},
            )

        self.assertTrue(valid_market["ok"], valid_market["issues"])
        self.assertFalse(missing_market_endpoint["ok"])
        self.assertTrue(
            any("missing live-smoke endpoints: klines" in issue for issue in missing_market_endpoint["issues"])
        )
        self.assertFalse(wrong_market_scope["ok"])
        self.assertTrue(
            any(
                "url must start with https://testnet.binancefuture.com/" in issue
                for issue in wrong_market_scope["issues"]
            )
        )
        self.assertTrue(valid_account["ok"], valid_account["issues"])
        self.assertFalse(missing_account_endpoint["ok"])
        self.assertTrue(
            any("missing live-smoke endpoints: positionRisk" in issue for issue in missing_account_endpoint["issues"])
        )
        self.assertFalse(missing_market_suite["ok"])
        self.assertTrue(
            any("missing live-smoke suite results: fetch_klines" in issue for issue in missing_market_suite["issues"])
        )
        self.assertFalse(missing_native_rsi["ok"])
        self.assertTrue(
            any("computed_indicator_keys must include rsi" in issue for issue in missing_native_rsi["issues"])
        )
        self.assertFalse(unsupported_native_indicator["ok"])
        self.assertTrue(
            any(
                "unsupported_indicator_keys must be an empty list" in issue
                for issue in unsupported_native_indicator["issues"]
            )
        )
        self.assertFalse(missing_websocket_observation["ok"])
        self.assertTrue(
            any("websocket_connected must be true" in issue for issue in missing_websocket_observation["issues"])
        )
        self.assertTrue(
            any("websocket_url must be a wss URL" in issue for issue in missing_websocket_observation["issues"])
        )
        self.assertTrue(
            any(
                "websocket_timeout_ms must be a positive integer" in issue
                for issue in missing_websocket_observation["issues"]
            )
        )
        self.assertTrue(
            any(
                "websocket_poll_status must be event" in issue
                for issue in missing_websocket_observation["issues"]
            )
        )
        self.assertTrue(
            any(
                "websocket_event_kind must be kline" in issue
                for issue in missing_websocket_observation["issues"]
            )
        )
        self.assertFalse(unredacted_balance["ok"])
        self.assertTrue(
            any(
                "suite_results[fetch_usdt_balance].balances_redacted must be true" in issue
                for issue in unredacted_balance["issues"]
            )
        )
        self.assertFalse(missing_account_suite["ok"])
        self.assertTrue(
            any(
                "missing live-smoke suite results: fetch_usdt_balance" in issue
                for issue in missing_account_suite["issues"]
            )
        )
        self.assertFalse(missing_credential_metadata["ok"])
        self.assertTrue(
            any("environment.api_key_present must be true" in issue for issue in missing_credential_metadata["issues"])
        )
        self.assertFalse(secret_artifact_metadata["ok"])
        self.assertTrue(
            any(
                "environment.secrets_in_artifact must be false" in issue for issue in secret_artifact_metadata["issues"]
            )
        )

    def test_runtime_evidence_rejects_secret_leaks_even_when_redaction_flag_is_true(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
            "source_tree_clean": True,
            "python_source_contract_hash": PYTHON_SOURCE_CONTRACT_HASH,
            "native_source_sync": _native_source_sync_binding(),
            "command": "cargo run -p trading-bot-rust -- --native-live-market-smoke",
            "environment": {
                "scope": "live_testnet",
                "market_base_url": BINANCE_FUTURES_TESTNET_BASE_URL,
            },
            "secrets_redacted": True,
            "runtime_ready_claimed": False,
            "read_only": True,
            "order_submission_attempted": False,
            "endpoints": _market_smoke_endpoints(),
            "suite_results": _market_smoke_suite_results(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            evidence_path = evidence_dir / f"{evidence_id}.json"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            valid = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["environment"]["api_secret"] = "exchange-secret"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            secret_field = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            del payload["environment"]["api_secret"]
            payload["suite_results"][0]["stderr_tail"] = "Authorization: Bearer leaked-token"
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            bearer_text = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

            payload["suite_results"][0]["stderr_tail"] = "api_secret=<redacted> signature=..."
            evidence_path.write_text(json.dumps(payload), encoding="utf-8")
            redacted_text = runtime_evidence.validate(
                runtime_evidence.DEFAULT_MANIFEST_PATH,
                require_evidence=True,
                evidence_dir_override=evidence_dir,
                requirement_ids={evidence_id},
            )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(secret_field["ok"])
        self.assertTrue(any("unredacted secret field: api_secret" in issue for issue in secret_field["issues"]))
        self.assertFalse(bearer_text["ok"])
        self.assertTrue(any("unredacted bearer token text" in issue for issue in bearer_text["issues"]))
        self.assertTrue(redacted_text["ok"], redacted_text["issues"])


if __name__ == "__main__":
    unittest.main()
