import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_rust_native_local_recovery_evidence as local_recovery  # noqa: E402
from tools import check_rust_native_runtime_evidence as runtime_evidence  # noqa: E402
from tools import check_release_platform_matrix as release_platform_matrix  # noqa: E402
from tools import check_release_assets as release_assets  # noqa: E402
from tools import run_release_platform_probe as release_platform_probe  # noqa: E402
from tools import audit_rust_native_runtime_readiness as runtime_readiness  # noqa: E402
from tools import write_rust_native_release_evidence as release_evidence  # noqa: E402


BINANCE_FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"


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


class RustNativeReleaseEvidenceTests(unittest.TestCase):
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

    def test_build_release_evidence_requires_rust_assets_and_platform_results(self):
        tag = "v1.2.3"
        _, expected_assets = release_evidence._build_expected_assets(tag)
        rust_required_names = {
            asset.name
            for asset in expected_assets
            if asset.required and asset.name.startswith("Trading-Bot-Rust-")
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
            return _target_evidence_payload(target)

        with (
            patch.object(release_evidence, "_fetch_release", return_value=release_payload),
            patch.object(release_evidence, "_load_json", return_value={"schema_version": 1}),
            patch.object(release_evidence, "_validate_matrix", return_value=(platform_targets, browser_targets, [])),
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
                platform_evidence_dir=Path("release-platform-evidence"),
            )

        self.assertEqual([], issues)
        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual("rust-native-release-platform-evidence", artifact["evidence_id"])
        self.assertEqual("release_platform", artifact["evidence_scope"])
        self.assertFalse(artifact["runtime_ready_claimed"])
        self.assertTrue(artifact["source_tree_clean"])
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

        with patch.object(release_evidence, "_fetch_release", return_value=release_payload):
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
        self.assertTrue(any("platform_results[0].suite_count must be at least" in issue for issue in short_suite["issues"]))
        self.assertFalse(missing_embedded_suites["ok"])
        self.assertTrue(
            any("platform_results[0].suite_results must be a non-empty list" in issue for issue in missing_embedded_suites["issues"])
        )
        self.assertFalse(failed_embedded_suite["ok"])
        self.assertTrue(
            any("platform_results[0].suite_results[0].status must be passed" in issue for issue in failed_embedded_suite["issues"])
        )
        self.assertFalse(target_mismatch["ok"])
        self.assertTrue(
            any("suite_results[platform-probe].target_match.matched must be true" in issue for issue in target_mismatch["issues"])
        )
        self.assertFalse(missing_hash["ok"])
        self.assertTrue(any("evidence_sha256 must be a SHA-256 hex digest" in issue for issue in missing_hash["issues"]))
        self.assertFalse(wrong_hash["ok"])
        self.assertTrue(any("evidence_sha256 does not match" in issue for issue in wrong_hash["issues"]))

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
                patch.object(release_evidence, "_validate_matrix", return_value=(platform_targets, browser_targets, [])),
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
        self.assertGreaterEqual(len(result["required_rust_release_assets"]), 1)
        self.assertEqual(1, result["present_platform_evidence_count"])
        self.assertEqual(0, result["passed_platform_evidence_count"])
        self.assertEqual(1, result["invalid_platform_evidence_count"])
        self.assertEqual("windows-11-x64", result["invalid_platform_evidence"][0]["target_id"])
        self.assertEqual(1, result["missing_platform_evidence_count"])
        self.assertEqual(["browser-chrome-windows-11-x64"], result["missing_platform_evidence"])
        self.assertEqual(1, len(result["missing_platform_evidence_plan"]))
        self.assertEqual("browser-chrome-windows-11-x64", result["missing_platform_evidence_plan"][0]["target_id"])
        self.assertIn("browser_test_command", result["missing_platform_evidence_plan"][0]["required_workflow_inputs"])
        self.assertIn("gh workflow run release-platform-real-tests.yml", result["missing_platform_evidence_plan"][0]["workflow_dispatch_example"])
        self.assertIn("--preflight", result["preflight_command"])

    def test_readiness_audit_release_prerequisites_include_preflight_coverage(self):
        preflight_result = {
            "ok": False,
            "release_asset_presence_verified": False,
            "release_asset_presence_requires_network": True,
            "platform_target_count": 70,
            "browser_target_count": 29,
            "present_platform_evidence_count": 1,
            "passed_platform_evidence_count": 0,
            "invalid_platform_evidence_count": 1,
            "unknown_platform_evidence_count": 1,
            "missing_platform_evidence_count": 98,
            "missing_platform_evidence_limit": 10,
            "missing_platform_evidence_truncated": True,
            "missing_platform_evidence": ["browser-chrome-windows-11-x64"],
            "missing_platform_evidence_plan": [
                {
                    "target_id": "browser-chrome-windows-11-x64",
                    "workflow_dispatch_example": "gh workflow run release-platform-real-tests.yml",
                }
            ],
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
        self.assertFalse(result["release_asset_presence_verified"])
        self.assertTrue(result["release_asset_presence_requires_network"])
        self.assertEqual(70, result["platform_target_count"])
        self.assertEqual(29, result["browser_target_count"])
        self.assertEqual(1, result["present_platform_evidence_count"])
        self.assertEqual(0, result["passed_platform_evidence_count"])
        self.assertEqual(1, result["invalid_platform_evidence_count"])
        self.assertEqual(1, result["unknown_platform_evidence_count"])
        self.assertEqual(98, result["missing_platform_evidence_count"])
        self.assertEqual(10, result["missing_platform_evidence_limit"])
        self.assertTrue(result["missing_platform_evidence_truncated"])
        self.assertEqual(["browser-chrome-windows-11-x64"], result["missing_platform_evidence"])
        self.assertEqual("browser-chrome-windows-11-x64", result["missing_platform_evidence_plan"][0]["target_id"])
        self.assertIn("98 of 99", result["release_platform_preflight_issues"][0])
        self.assertEqual("v9.9.9", preflight.call_args.kwargs["tag"])
        self.assertEqual(10, preflight.call_args.kwargs["missing_limit"])

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

        self.assertTrue(fresh["ok"], fresh["issues"])
        self.assertFalse(stale["ok"])
        self.assertTrue(any("commit must match current git commit" in issue for issue in stale["issues"]))
        self.assertFalse(dirty_artifact["ok"])
        self.assertTrue(
            any("source_tree_clean must be true" in issue for issue in dirty_artifact["issues"])
        )

    def test_runtime_evidence_enforces_manifest_declared_artifact_fields(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
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

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertFalse(missing_field["ok"])
        self.assertTrue(
            any("missing required artifact field: command" in issue for issue in missing_field["issues"])
        )

    def test_runtime_evidence_requires_machine_readable_generated_at(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
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
        self.assertTrue(any("generated_at must contain positive unix seconds" in issue for issue in bad_seconds["issues"]))

    def test_runtime_evidence_enforces_live_smoke_endpoint_contracts(self):
        market_id = "rust-native-live-market-data-smoke"
        account_id = "rust-native-live-account-read-smoke"
        market_payload = {
            "evidence_id": market_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
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
        self.assertTrue(any("url must start with https://testnet.binancefuture.com/" in issue for issue in wrong_market_scope["issues"]))
        self.assertTrue(valid_account["ok"], valid_account["issues"])
        self.assertFalse(missing_account_endpoint["ok"])
        self.assertTrue(
            any("missing live-smoke endpoints: positionRisk" in issue for issue in missing_account_endpoint["issues"])
        )
        self.assertFalse(missing_market_suite["ok"])
        self.assertTrue(
            any("missing live-smoke suite results: fetch_klines" in issue for issue in missing_market_suite["issues"])
        )
        self.assertFalse(unredacted_balance["ok"])
        self.assertTrue(
            any("suite_results[fetch_usdt_balance].balances_redacted must be true" in issue for issue in unredacted_balance["issues"])
        )
        self.assertFalse(missing_account_suite["ok"])
        self.assertTrue(
            any("missing live-smoke suite results: fetch_usdt_balance" in issue for issue in missing_account_suite["issues"])
        )
        self.assertFalse(missing_credential_metadata["ok"])
        self.assertTrue(
            any("environment.api_key_present must be true" in issue for issue in missing_credential_metadata["issues"])
        )
        self.assertFalse(secret_artifact_metadata["ok"])
        self.assertTrue(
            any("environment.secrets_in_artifact must be false" in issue for issue in secret_artifact_metadata["issues"])
        )

    def test_runtime_evidence_rejects_secret_leaks_even_when_redaction_flag_is_true(self):
        evidence_id = "rust-native-live-market-data-smoke"
        payload = {
            "evidence_id": evidence_id,
            "status": "passed",
            "evidence_scope": "live_testnet",
            "generated_at": "unix:1",
            "commit": "abc123",
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
