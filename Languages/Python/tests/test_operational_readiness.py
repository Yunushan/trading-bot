from __future__ import annotations

import json
import copy
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_operational_readiness as readiness  # noqa: E402
from tools import import_production_slo_evidence as slo_import  # noqa: E402
from tools import run_incident_audit_continuity_drill as audit_continuity  # noqa: E402
from tools import run_operational_recovery_drill as recovery  # noqa: E402
from tools import run_service_sustained_probe as service_probe  # noqa: E402


POLICY_PATH = REPO_ROOT / "docs" / "operational-readiness-policy.json"


def _valid_process_recovery_fixture() -> dict[str, object]:
    return {
        "name": "canonical-service-process-restart", "status": "pass",
        "process_boundary": "child-process", "failure_mode": "forced-process-exit",
        **dict.fromkeys(readiness.RECOVERY_VERIFIED_FLAGS, True),
        "original_pid": 1001, "replacement_pid": 1002, "original_exit_code": -9,
        "original_endpoint": "http://127.0.0.1:43210", "replacement_endpoint": "http://127.0.0.1:43210",
        "original_status_codes": [200] * 4, "status_codes": [200] * 4,
        "backup_sha256": "a" * 64, "restored_backup_sha256": "a" * 64,
        "timeline_seconds": {event: float(index) for index, event in enumerate(readiness.RECOVERY_TIMELINE_EVENTS)},
        "recovery_time_seconds": 6.0, "config_recovery_time_seconds": 1.0,
        "service_recovery_time_seconds": 2.0, "recovery_point_seconds": 1.0,
    }


def _valid_slo_telemetry(*, window_end: datetime | None = None) -> dict[str, object]:
    end = window_end or datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return {
        "schema_version": 1,
        "telemetry_source": "prometheus:trading-bot-production",
        "deployed_commit": "a" * 40,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "eligible_request_count": 1_000_000,
        "successful_request_count": 999_500,
        "failed_request_count": 500,
        "read_latency_p95_ms": 125.0,
        "operational_snapshot_age_seconds": 30.0,
    }


class OperationalReadinessTests(unittest.TestCase):
    def test_checked_in_policy_is_valid_and_has_no_assumed_passes(self):
        policy = readiness.load_policy(POLICY_PATH)

        self.assertEqual([], readiness.validate_policy(policy))
        self.assertTrue(policy["policy"]["no_assumed_passes"])
        self.assertTrue(policy["policy"]["production_promotion_requires_all_evidence"])
        self.assertFalse(policy["probe_profiles"]["quick"]["promotion_eligible"])
        self.assertTrue(policy["probe_profiles"]["sustained"]["promotion_eligible"])

    def test_schema_audit_passes_without_claiming_promotion_readiness(self):
        report = readiness.audit_operational_readiness(REPO_ROOT)

        self.assertTrue(report["ok"])
        self.assertTrue(report["schema_ok"])
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(4, report["service_level_objective_count"])
        self.assertEqual(3, report["recovery_objective_count"])
        self.assertEqual(4, report["required_evidence_count"])

    def test_invalid_policy_is_rejected(self):
        policy = readiness.load_policy(POLICY_PATH)
        policy["policy"]["no_assumed_passes"] = False
        policy["probe_profiles"]["quick"]["promotion_eligible"] = True

        issues = readiness.validate_policy(policy)

        self.assertIn("policy.no_assumed_passes must be true", issues)
        self.assertIn("probe_profiles.quick.promotion_eligible must be false", issues)

    def test_missing_promotion_evidence_is_reported_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = readiness.audit_operational_readiness(
                REPO_ROOT,
                evidence_dir=Path(temporary_directory),
                require_evidence=True,
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(4, len(report["evidence"]))
        self.assertTrue(all(not item["ok"] for item in report["evidence"]))
        self.assertTrue(all("missing evidence artifact" in item["issues"][0] for item in report["evidence"]))

    def test_complete_current_policy_evidence_can_be_validated_without_assumptions(self):
        policy = readiness.load_policy(POLICY_PATH)
        policy_hash = readiness.policy_sha256(policy)
        generated_at = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence_dir = Path(temporary_directory)
            for requirement in policy["required_evidence"]:
                payload: dict[str, object] = {
                    "evidence_id": requirement["id"],
                    "status": "pass",
                    "generated_at": generated_at,
                    "commit": "a" * 40,
                    "source_tree_clean": True,
                    "policy_sha256": policy_hash,
                    "secrets_redacted": True,
                    "read_only": True,
                    "order_submission_attempted": False,
                    "promotion_eligible": True,
                    "suite_results": [{"name": "test", "status": "pass"}],
                }
                for field in requirement["required_fields"]:
                    payload.setdefault(field, 0)
                if requirement["id"] == "service-api-sustained-runtime":
                    sustained = policy["probe_profiles"]["sustained"]
                    payload.update(
                        {
                            "duration_seconds": sustained["minimum_duration_seconds"],
                            "request_count": sustained["minimum_requests"],
                            "error_rate": 0.0,
                            "latency_ms": {"p95": 1.0},
                            "operational_snapshot_sample_count": 1,
                            "operational_snapshot_expected_count": 1,
                            "operational_snapshot_max_age_seconds": 1.0,
                            "deployed_commit": "a" * 40,
                            "evidence_scope": "deployed-sustained-service-api-probe",
                            "environment": {"transport": "external-https"},
                        }
                    )
                elif requirement["id"] == "production-service-slo-window":
                    telemetry = _valid_slo_telemetry(window_end=datetime.now(timezone.utc) - timedelta(minutes=1))
                    payload.update(
                        {
                            **telemetry,
                            "telemetry_input_sha256": "a" * 64,
                            "successful_request_ratio": 0.9995,
                            "failed_request_ratio": 0.0005,
                        }
                    )
                else:
                    payload.update(
                        {
                            "recovery_time_seconds": 0.0,
                            "recovery_point_seconds": 0.0,
                        }
                    )
                    if requirement["id"] == "service-config-backup-restore":
                        payload.update(
                            {
                                "config_recovery_time_seconds": 1.0,
                                "service_recovery_time_seconds": 2.0,
                                "recovery_time_seconds": 6.0,
                                "recovery_point_seconds": 1.0,
                                "suite_results": [
                                    {"name": "config-backup-secret-redaction", "status": "pass"},
                                    {"name": "config-restore-round-trip", "status": "pass"},
                                    {"name": "synthetic-credential-cleanup", "status": "pass"},
                                    _valid_process_recovery_fixture(),
                                ],
                            }
                        )
                (evidence_dir / requirement["filename"]).write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            report = readiness.audit_operational_readiness(
                REPO_ROOT,
                evidence_dir=evidence_dir,
                require_evidence=True,
            )

        self.assertTrue(report["ok"])
        self.assertTrue(report["promotion_ready"])

    def test_quick_service_probe_is_read_only_and_not_promotion_evidence(self):
        policy = readiness.load_policy(POLICY_PATH)
        endpoint_count = len(policy["probe_profiles"]["quick"]["endpoints"])

        report = service_probe.run_probe(
            profile_name="quick",
            cycles=1,
            minimum_requests=endpoint_count,
        )

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(endpoint_count, report["request_count"])
        self.assertEqual(0, report["error_count"])
        self.assertEqual(4, report["operational_snapshot_sample_count"])
        self.assertEqual(4, report["operational_snapshot_expected_count"])
        self.assertEqual(0, report["operational_snapshot_issue_count"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["production_slo_proven"])

    def test_unseeded_standalone_read_only_service_has_no_trading_freshness_claim(self):
        from fastapi.testclient import TestClient
        from app.service.api import create_service_api_app

        with patch.dict(os.environ, {"BOT_SERVICE_API_READ_ONLY": "1"}):
            app = create_service_api_app(
                api_token="synthetic-probe-token",
                host_context="standalone-service",
            )
            with TestClient(app) as client:
                readiness_response = client.get("/readyz")
                response = client.get(
                    "/api/v1/runtime/operational-preflight",
                    headers={"Authorization": "Bearer synthetic-probe-token"},
                )

        self.assertEqual(200, response.status_code)
        self.assertEqual(200, readiness_response.status_code)
        self.assertIs(readiness_response.json()["trading_execution_supported"], False)
        self.assertTrue(app.state.service_api_read_only)
        ages, issues = service_probe._operational_snapshot_freshness_samples(response.json())
        self.assertEqual(1, len(ages))
        self.assertEqual(3, len(issues))
        for component in ("execution", "account", "portfolio"):
            self.assertTrue(any(component in issue for issue in issues), issues)

    def test_unseeded_observer_smoke_passes_service_health_without_trading_promotion(self):
        from fastapi.testclient import TestClient

        from app.service.api import create_service_api_app

        commit = "a" * 40
        token = "synthetic-observer-probe-token"
        with patch.dict(os.environ, {
            "BOT_SERVICE_API_READ_ONLY": "1",
            "BOT_SERVICE_API_TOKEN": token,
            "TRADING_BOT_BUILD_COMMIT": commit,
        }):
            app = create_service_api_app(api_token=token)
            with TestClient(app) as client:
                readiness_response = client.get("/readyz")

                class _InProcessRemote:
                    def __init__(self, *_args, **_kwargs):
                        pass

                    def __enter__(self):
                        return self

                    def __exit__(self, *_args):
                        return None

                    def get(self, endpoint, *, headers):
                        return client.get(endpoint, headers=headers)

                with patch.object(service_probe, "_RemoteReadOnlyClient", _InProcessRemote), patch.object(
                    service_probe, "_source_tree_clean", return_value=True,
                ):
                    observer = service_probe.run_probe(
                        profile_name="observer-smoke",
                        cycles=1,
                        minimum_requests=6,
                        base_url="https://observer.example",
                        expected_commit=commit,
                    )
                    strict_quick = service_probe.run_probe(
                        profile_name="quick",
                        cycles=1,
                        minimum_requests=6,
                        base_url="https://observer.example",
                        expected_commit=commit,
                        require_server_read_only=True,
                    )

        self.assertEqual(service_probe.OBSERVER_SMOKE_CONTRACT_VERSION,
                         readiness_response.json()["observation_contract_version"])
        self.assertIs(readiness_response.json()["trading_observation_supported"], False)
        self.assertTrue(observer["ok"], observer["issues"])
        self.assertTrue(observer["source_tree_clean"])
        self.assertEqual(service_probe.OBSERVER_SMOKE_EVIDENCE_ID, observer["evidence_id"])
        self.assertEqual("unavailable", observer["trading_observations"]["status"])
        self.assertIsNone(observer["trading_observations"]["freshness_age_seconds"])
        self.assertEqual(0, observer["operational_snapshot_sample_count"])
        self.assertEqual(0, observer["operational_snapshot_expected_count"])
        self.assertFalse(observer["promotion_eligible"])
        self.assertFalse(observer["runtime_ready_claimed"])
        self.assertFalse(observer["production_slo_proven"])
        self.assertNotIn("operational-snapshot-freshness", {
            item["name"] for item in observer["suite_results"] if "name" in item
        })
        self.assertFalse(strict_quick["ok"])
        self.assertEqual(1, strict_quick["operational_snapshot_sample_count"])
        self.assertEqual(4, strict_quick["operational_snapshot_expected_count"])

        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(item for item in policy["required_evidence"]
                           if item["id"] == "service-api-sustained-runtime")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / requirement["filename"]
            path.write_text(json.dumps(observer), encoding="utf-8")
            issues = readiness._validate_evidence(
                requirement,
                policy=policy,
                path=path,
                expected_policy_hash=readiness.policy_sha256(policy),
                expected_commit=observer["commit"],
                require_current_commit=True,
                require_clean_source=True,
            )
        self.assertTrue(any("evidence_id must be" in issue for issue in issues))
        self.assertTrue(any("promotion_eligible must be true" in issue for issue in issues))

    def test_read_only_injected_service_does_not_inherit_standalone_observer_contract(self):
        from fastapi.testclient import TestClient

        from app.service.api import create_service_api_app
        from app.service.runtime import TradingBotService

        with patch.dict(os.environ, {"BOT_SERVICE_API_READ_ONLY": "1"}):
            app = create_service_api_app(service=TradingBotService(), api_token="synthetic-token")
            with TestClient(app) as client:
                response = client.get("/readyz")
        self.assertEqual(200, response.status_code)
        self.assertIs(response.json()["read_only"], True)
        self.assertNotIn("observation_contract_version", response.json())
        self.assertNotIn("trading_observation_supported", response.json())

    def test_standalone_server_launcher_declares_no_observation_provider(self):
        from fastapi.testclient import TestClient

        from app.service.api import run_service_api_server

        with patch.dict(os.environ, {"BOT_SERVICE_API_READ_ONLY": "1"}), patch(
            "uvicorn.run"
        ) as serve:
            run_service_api_server(api_token="synthetic-token")
            app = serve.call_args.args[0]
            with TestClient(app) as client:
                response = client.get("/readyz")
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            service_probe.OBSERVER_SMOKE_CONTRACT_VERSION,
            response.json()["observation_contract_version"],
        )
        self.assertIs(response.json()["trading_observation_supported"], False)

    def test_observer_smoke_rejects_false_or_mixed_scope_claims(self):
        from fastapi.testclient import TestClient

        from app.service.api import create_service_api_app

        commit = "a" * 40
        token = "synthetic-observer-probe-token"
        cases = {
            "writable": lambda payload: payload.__setitem__("read_only", False),
            "trading executor": lambda payload: payload.__setitem__("trading_execution_supported", True),
            "missing execution flag": lambda payload: payload.pop("trading_execution_supported"),
            "trading observation": lambda payload: payload.__setitem__("trading_observation_supported", True),
            "missing observation flag": lambda payload: payload.pop("trading_observation_supported"),
            "malformed observation flag": lambda payload: payload.__setitem__("trading_observation_supported", "false"),
            "wrong contract": lambda payload: payload.__setitem__("observation_contract_version", "unknown/v1"),
            "wrong source": lambda payload: payload.__setitem__("trading_observation_source", "exchange"),
            "wrong host topology": lambda payload: payload.__setitem__("host_context", "desktop-hosted"),
            "wrong commit": lambda payload: payload.__setitem__("build_commit", "b" * 40),
        }
        with patch.dict(os.environ, {
            "BOT_SERVICE_API_READ_ONLY": "1",
            "BOT_SERVICE_API_TOKEN": token,
            "TRADING_BOT_BUILD_COMMIT": commit,
        }):
            app = create_service_api_app(api_token=token)
            with TestClient(app) as client:
                for name, mutate in cases.items():
                    with self.subTest(name=name):
                        class _MutatedRemote:
                            def __init__(self, *_args, **_kwargs):
                                pass

                            def __enter__(self):
                                return self

                            def __exit__(self, *_args):
                                return None

                            def get(self, endpoint, *, headers):
                                response = client.get(endpoint, headers=headers)
                                if endpoint == "/readyz":
                                    payload = response.json()
                                    mutate(payload)
                                    return SimpleNamespace(status_code=200, json=lambda: payload)
                                return response

                        with patch.object(service_probe, "_RemoteReadOnlyClient", _MutatedRemote):
                            report = service_probe.run_probe(
                                profile_name="observer-smoke",
                                cycles=1,
                                minimum_requests=6,
                                base_url="https://observer.example",
                                expected_commit=commit,
                            )
                        self.assertFalse(report["ok"])
                        self.assertFalse(report["promotion_eligible"])
                        self.assertNotEqual("unavailable", report["trading_observations"]["status"])

                class _MixedOrSeededRemote:
                    def __init__(self, *_args, **_kwargs):
                        self.ready_count = 0

                    def __enter__(self):
                        return self

                    def __exit__(self, *_args):
                        return None

                    def get(self, endpoint, *, headers):
                        response = client.get(endpoint, headers=headers)
                        if endpoint == "/readyz":
                            self.ready_count += 1
                            payload = response.json()
                            if self.ready_count == 2:
                                payload["trading_observation_supported"] = True
                            return SimpleNamespace(status_code=200, json=lambda: payload)
                        return response

                with patch.object(service_probe, "_RemoteReadOnlyClient", _MixedOrSeededRemote):
                    mixed = service_probe.run_probe(
                        profile_name="observer-smoke", cycles=2, minimum_requests=12,
                        base_url="https://observer.example", expected_commit=commit,
                    )
                self.assertFalse(mixed["ok"])

                class _MalformedPreflightRemote(_MixedOrSeededRemote):
                    def get(self, endpoint, *, headers):
                        if endpoint.endswith("/operational-preflight"):
                            return SimpleNamespace(status_code=200, json=lambda: {})
                        return client.get(endpoint, headers=headers)

                with patch.object(service_probe, "_RemoteReadOnlyClient", _MalformedPreflightRemote):
                    malformed = service_probe.run_probe(
                        profile_name="observer-smoke", cycles=1, minimum_requests=6,
                        base_url="https://observer.example", expected_commit=commit,
                    )
                self.assertFalse(malformed["ok"])
                self.assertTrue(any("preflight" in issue for issue in malformed["issues"]))

                class _SeededPreflightRemote(_MixedOrSeededRemote):
                    def get(self, endpoint, *, headers):
                        if endpoint.endswith("/operational-preflight"):
                            payload = client.get(endpoint, headers=headers).json()
                            timestamp = datetime.now(timezone.utc).isoformat()
                            for component, timestamp_field in service_probe.OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS.items():
                                payload["freshness"][component].update({
                                    timestamp_field: timestamp,
                                    "age_seconds": 0.0,
                                    "source": "synthetic-probe",
                                })
                            return SimpleNamespace(status_code=200, json=lambda: payload)
                        return client.get(endpoint, headers=headers)

                with patch.object(service_probe, "_RemoteReadOnlyClient", _SeededPreflightRemote):
                    seeded = service_probe.run_probe(
                        profile_name="observer-smoke", cycles=1, minimum_requests=6,
                        base_url="https://observer.example", expected_commit=commit,
                    )
                self.assertFalse(seeded["ok"])
                self.assertFalse(seeded["promotion_eligible"])
                self.assertEqual("unverified", seeded["trading_observations"]["status"])

        for kwargs in (
            {"base_url": "http://observer.example", "expected_commit": commit},
            {"base_url": "https://observer.example"},
            {"expected_commit": commit},
        ):
            with self.subTest(kwargs=kwargs):
                report = service_probe.run_probe(profile_name="observer-smoke", **kwargs)
                self.assertFalse(report["ok"])
                self.assertFalse(report["promotion_eligible"])

    def test_sustained_probe_requires_a_deployed_service_origin(self):
        report = service_probe.run_probe(
            profile_name="sustained",
            cycles=1,
            minimum_duration_seconds=0,
            minimum_requests=1,
        )

        self.assertFalse(report["ok"])
        self.assertFalse(report["promotion_eligible"])
        self.assertIn("requires --base-url", report["issues"][0])

    def test_deployment_probe_can_require_server_commit_and_read_only_state(self):
        now = datetime.now(timezone.utc).isoformat()
        expected_commit = "a" * 40
        preflight = {
            "freshness": {
                component: {
                    timestamp_field: now,
                    "age_seconds": 0.0,
                    "stale": False,
                }
                for component, timestamp_field in service_probe.OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS.items()
            }
        }

        class _RemoteClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def get(self, endpoint, *, headers):  # noqa: ARG002
                if endpoint.endswith("/readyz"):
                    payload = {
                        "status": "ready",
                        "build_commit": expected_commit,
                        "read_only": True,
                        "trading_execution_supported": False,
                    }
                elif endpoint.endswith("/operational-preflight"):
                    payload = preflight
                else:
                    payload = {"status": "ok"}
                return SimpleNamespace(status_code=200, json=lambda: payload)

        with patch.object(service_probe, "_RemoteReadOnlyClient", _RemoteClient), patch.dict(
            os.environ, {"PROBE_TEST_TOKEN": "synthetic-token"}, clear=False
        ):
            report = service_probe.run_probe(
                profile_name="quick",
                cycles=1,
                minimum_requests=6,
                base_url="https://service.example",
                api_token_env="PROBE_TEST_TOKEN",
                expected_commit=expected_commit,
                require_server_read_only=True,
            )

        self.assertTrue(report["ok"], report["issues"])
        self.assertTrue(report["server_identity_verified"])
        self.assertTrue(report["server_read_only_verified"])
        self.assertEqual(expected_commit, report["expected_commit"])
        identity_result = next(
            item
            for item in report["suite_results"]
            if item.get("name") == "server-read-only-and-commit-identity"
        )
        self.assertEqual("pass", identity_result["status"])

    def test_deployment_probe_rejects_wrong_commit_or_writable_server(self):
        now = datetime.now(timezone.utc).isoformat()
        preflight = {
            "freshness": {
                component: {
                    timestamp_field: now,
                    "age_seconds": 0.0,
                    "stale": False,
                }
                for component, timestamp_field in service_probe.OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS.items()
            }
        }

        class _RemoteClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def get(self, endpoint, *, headers):  # noqa: ARG002
                if endpoint.endswith("/readyz"):
                    payload = {
                        "status": "ready",
                        "build_commit": "f" * 40,
                        "read_only": False,
                        "trading_execution_supported": False,
                    }
                elif endpoint.endswith("/operational-preflight"):
                    payload = preflight
                else:
                    payload = {"status": "ok"}
                return SimpleNamespace(status_code=200, json=lambda: payload)

        with patch.object(service_probe, "_RemoteReadOnlyClient", _RemoteClient), patch.dict(
            os.environ, {"PROBE_TEST_TOKEN": "synthetic-token"}, clear=False
        ):
            report = service_probe.run_probe(
                profile_name="quick",
                cycles=1,
                minimum_requests=6,
                base_url="https://service.example",
                api_token_env="PROBE_TEST_TOKEN",
                expected_commit="a" * 40,
                require_server_read_only=True,
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["server_identity_verified"])
        self.assertFalse(report["server_read_only_verified"])
        self.assertTrue(any("expected_commit" in issue for issue in report["issues"]))
        self.assertTrue(any("read_only=true" in issue for issue in report["issues"]))

    def test_read_only_deployment_probe_rejects_trading_capable_runtime(self):
        now = datetime.now(timezone.utc).isoformat()
        expected_commit = "a" * 40
        preflight = {
            "freshness": {
                component: {
                    timestamp_field: now,
                    "age_seconds": 0.0,
                    "stale": False,
                }
                for component, timestamp_field in service_probe.OPERATIONAL_FRESHNESS_TIMESTAMP_FIELDS.items()
            }
        }

        class _RemoteClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def get(self, endpoint, *, headers):  # noqa: ARG002
                if endpoint.endswith("/readyz"):
                    payload = {
                        "status": "ready",
                        "build_commit": expected_commit,
                        "read_only": True,
                        "trading_execution_supported": True,
                    }
                elif endpoint.endswith("/operational-preflight"):
                    payload = preflight
                else:
                    payload = {"status": "ok"}
                return SimpleNamespace(status_code=200, json=lambda: payload)

        for profile_name, explicit_read_only in (("quick", True), ("sustained", False)):
            with self.subTest(profile_name=profile_name), patch.object(
                service_probe, "_RemoteReadOnlyClient", _RemoteClient
            ):
                report = service_probe.run_probe(
                    profile_name=profile_name,
                    cycles=1,
                    minimum_duration_seconds=0,
                    minimum_requests=6,
                    base_url="https://service.example",
                    expected_commit=expected_commit,
                    require_server_read_only=explicit_read_only,
                )

            self.assertFalse(report["ok"])
            self.assertFalse(report["server_observer_scope_verified"])
            self.assertTrue(
                any("trading_execution_supported=false" in issue for issue in report["issues"])
            )

    def test_sustained_evidence_rejects_missing_operational_snapshot_samples(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item for item in policy["required_evidence"] if item["id"] == "service-api-sustained-runtime"
        )
        payload = {
            "duration_seconds": policy["probe_profiles"]["sustained"]["minimum_duration_seconds"],
            "request_count": policy["probe_profiles"]["sustained"]["minimum_requests"],
            "error_rate": 0.0,
            "latency_ms": {"p95": 1.0},
            "operational_snapshot_sample_count": 0,
            "operational_snapshot_expected_count": 1,
            "operational_snapshot_max_age_seconds": 0.0,
            "deployed_commit": "test-commit",
            "commit": "test-commit",
            "evidence_scope": "deployed-sustained-service-api-probe",
            "environment": {"transport": "external-https"},
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("service-api-sustained-runtime.json"),
        )

        self.assertTrue(any("sample_count must be a positive integer" in issue for issue in issues))
        self.assertTrue(any("must equal the expected count" in issue for issue in issues))

    def test_probe_base_url_rejects_credentials_and_non_origin_paths(self):
        for value in (
            "https://user:secret@example.test",
            "https://example.test/api/v1",
            "file:///tmp/service.sock",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    service_probe._normalize_base_url(value)

    def test_probe_rejects_wrapper_timestamp_without_component_freshness(self):
        payload = {"generated_at": datetime.now(timezone.utc).isoformat()}

        ages, issues = service_probe._operational_snapshot_freshness_samples(payload)

        self.assertEqual([], ages)
        self.assertIn("freshness must be an object", issues[0])

    def test_probe_rejects_stale_non_finite_and_future_component_freshness(self):
        now = datetime.now(timezone.utc)
        valid_timestamp = now.isoformat()
        payload = {
            "freshness": {
                "exchange_connector": {
                    "generated_at": valid_timestamp,
                    "age_seconds": 1.0,
                    "stale": True,
                },
                "execution": {
                    "heartbeat_at": valid_timestamp,
                    "age_seconds": float("nan"),
                    "stale": False,
                },
                "account": {
                    "generated_at": (now + timedelta(minutes=1)).isoformat(),
                    "age_seconds": 0.0,
                    "stale": False,
                },
                "portfolio": {
                    "generated_at": valid_timestamp,
                    "age_seconds": 1.0,
                    "stale": False,
                },
            }
        }

        ages, issues = service_probe._operational_snapshot_freshness_samples(
            payload,
            observed_at=now,
        )

        self.assertEqual(2, len(ages))
        self.assertTrue(any("exchange_connector" in issue and "stale" in issue for issue in issues))
        self.assertTrue(any("execution" in issue and "invalid" in issue for issue in issues))
        self.assertTrue(any("account" in issue and "future" in issue for issue in issues))

    def test_config_backup_restore_and_service_restart_drill_passes(self):
        report = recovery.run_recovery_drill()

        self.assertTrue(report["ok"], report["issues"])
        self.assertTrue(report["secrets_redacted"])
        self.assertTrue(report["read_only"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertLessEqual(report["recovery_time_seconds"], report["thresholds"]["rto_seconds"])
        self.assertLessEqual(report["recovery_point_seconds"], report["thresholds"]["rpo_seconds"])
        process_restart = next(
            item for item in report["suite_results"] if item["name"] == "canonical-service-process-restart"
        )
        self.assertEqual("pass", process_restart["status"])
        self.assertEqual("child-process", process_restart["process_boundary"])
        self.assertEqual("forced-process-exit", process_restart.get("failure_mode"))
        self.assertTrue(process_restart.get("original_ready"))
        self.assertTrue(process_restart.get("original_exit_observed"))
        self.assertTrue(process_restart.get("restored_config_matches"))
        self.assertTrue(process_restart.get("read_only_verified"))
        self.assertTrue(process_restart.get("same_endpoint"))
        self.assertNotEqual(process_restart.get("original_pid"), process_restart.get("replacement_pid"))
        self.assertTrue(process_restart["children_stopped"])
        self.assertTrue(process_restart["auth_verified"])
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(item for item in policy["required_evidence"] if item["id"] == recovery.EVIDENCE_ID)
        self.assertEqual([], readiness._validate_evidence_metrics(requirement, report, policy=policy, path=Path("recovery.json")))
        self.assertGreaterEqual(report["recovery_time_seconds"] + 0.00001, report["config_recovery_time_seconds"] + report["service_recovery_time_seconds"])
        serialized = json.dumps(report)
        for secret in recovery.SYNTHETIC_SECRETS.values():
            self.assertNotIn(secret, serialized)

    def test_config_recovery_evidence_requires_real_process_boundary(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item for item in policy["required_evidence"] if item["id"] == "service-config-backup-restore"
        )
        payload = {
            "recovery_time_seconds": 0.0,
            "recovery_point_seconds": 0.0,
            "config_recovery_time_seconds": 0.0,
            "service_recovery_time_seconds": 0.0,
            "suite_results": [
                {"name": "config-backup-secret-redaction", "status": "pass"},
                {"name": "config-restore-round-trip", "status": "pass"},
                {"name": "synthetic-credential-cleanup", "status": "pass"},
                {
                    "name": "canonical-service-process-restart",
                    "status": "pass",
                    "process_boundary": "in-process",
                },
            ],
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("service-config-backup-restore.json"),
        )

        self.assertTrue(any("child-process boundary" in issue for issue in issues))

    def test_cold_start_alone_is_not_process_recovery_evidence(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(item for item in policy["required_evidence"] if item["id"] == "service-config-backup-restore")
        payload = {
            "recovery_time_seconds": 0.1,
            "recovery_point_seconds": 0.1,
            "config_recovery_time_seconds": 0.01,
            "service_recovery_time_seconds": 0.1,
            "suite_results": [
                {"name": "config-backup-secret-redaction", "status": "pass"},
                {"name": "config-restore-round-trip", "status": "pass"},
                {"name": "synthetic-credential-cleanup", "status": "pass"},
                {"name": "canonical-service-process-restart", "status": "pass", "process_boundary": "child-process"},
            ],
        }
        issues = readiness._validate_evidence_metrics(requirement, payload, policy=policy, path=Path("recovery.json"))
        self.assertTrue(any("forced process exit" in issue for issue in issues), issues)

    def test_process_recovery_validator_rejects_missing_and_inconsistent_facts(self):
        result = _valid_process_recovery_fixture()
        payload = {key: result[key] for key in ("recovery_time_seconds", "config_recovery_time_seconds", "service_recovery_time_seconds", "recovery_point_seconds")}
        self.assertEqual([], readiness._validate_process_recovery(payload, result, path=Path("fixture.json")))
        mutations = [(field, value) for field in readiness.RECOVERY_VERIFIED_FLAGS for value in (None, False, 1, "true")]
        mutations += [
            ("original_pid", True), ("original_pid", 0), ("replacement_pid", 1001),
            ("replacement_pid", "1002"), ("original_exit_code", 0), ("original_exit_code", True),
            ("failure_mode", "cold-start"), ("replacement_endpoint", "http://127.0.0.1:43211"),
            ("original_endpoint", "https://public.invalid:43210"),
            ("backup_sha256", "invalid"), ("restored_backup_sha256", "b" * 64),
            ("status_codes", [200] * 3), ("original_status_codes", [200, 200, 401, 200]),
            ("timeline_seconds", {}), ("recovery_point_seconds", float("nan")),
            ("recovery_time_seconds", 0.0), ("config_recovery_time_seconds", 0.0),
            ("service_recovery_time_seconds", 0.0),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                changed = {**result, field: value}
                self.assertTrue(readiness._validate_process_recovery(payload, changed, path=Path("fixture.json")))
        for event in readiness.RECOVERY_TIMELINE_EVENTS:
            for value in (None, -1, True, float("nan"), float("inf")):
                with self.subTest(event=event, value=value):
                    changed = copy.deepcopy(result)
                    changed["timeline_seconds"][event] = value
                    self.assertTrue(readiness._validate_process_recovery(payload, changed, path=Path("fixture.json")))
        changed = copy.deepcopy(result)
        changed["timeline_seconds"]["config_restored"] = 0.5
        self.assertTrue(readiness._validate_process_recovery(payload, changed, path=Path("fixture.json")))
        for field in payload:
            with self.subTest(top_level_metric=field):
                self.assertTrue(readiness._validate_process_recovery({**payload, field: 0.0}, result, path=Path("fixture.json")))

    def test_process_recovery_validator_rejects_duplicate_results(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(item for item in policy["required_evidence"] if item["id"] == recovery.EVIDENCE_ID)
        result = _valid_process_recovery_fixture()
        payload = {key: result[key] for key in ("recovery_time_seconds", "config_recovery_time_seconds", "service_recovery_time_seconds", "recovery_point_seconds")}
        payload["suite_results"] = [result, result]
        issues = readiness._validate_evidence_metrics(requirement, payload, policy=policy, path=Path("fixture.json"))
        self.assertTrue(any("exactly one canonical-service-process-restart" in issue for issue in issues))

    def test_incident_audit_continuity_drill_recovers_rotated_redacted_logs(self):
        report = audit_continuity.run_continuity_drill()

        self.assertTrue(report["ok"], report.get("issues"))
        self.assertEqual("incident-audit-continuity", report["evidence_id"])
        self.assertTrue(report["read_only"])
        self.assertTrue(report["secrets_redacted"])
        self.assertFalse(report["order_submission_attempted"])
        self.assertGreaterEqual(len(report["suite_results"]), 9)

    def test_evidence_output_cannot_escape_configured_directory(self):
        policy = readiness.load_policy(POLICY_PATH)

        with self.assertRaisesRegex(ValueError, "must stay inside"):
            service_probe._resolve_output_path(policy, Path("..") / "outside.json")
        with self.assertRaisesRegex(ValueError, "must stay inside"):
            slo_import._resolve_output_path(policy, Path("..") / "outside.json")

    def test_evidence_output_accepts_repo_relative_configured_directory(self):
        policy = readiness.load_policy(POLICY_PATH)
        expected = (REPO_ROOT / "artifacts" / "operational-readiness" / "evidence.json").resolve()

        self.assertEqual(
            expected,
            service_probe._resolve_output_path(
                policy,
                Path("artifacts") / "operational-readiness" / "evidence.json",
            ),
        )
        self.assertEqual(
            expected,
            slo_import._resolve_output_path(
                policy,
                Path("artifacts") / "operational-readiness" / "evidence.json",
            ),
        )
        self.assertEqual(
            expected,
            service_probe._resolve_output_path(policy, Path("evidence.json")),
        )

    def test_production_slo_import_derives_ratios_and_binds_raw_export(self):
        policy = readiness.load_policy(POLICY_PATH)
        telemetry = _valid_slo_telemetry()

        report = slo_import.build_evidence(
            telemetry,
            policy=policy,
            current_commit="a" * 40,
            source_tree_clean=True,
            telemetry_input_sha256="b" * 64,
        )

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(0.9995, report["successful_request_ratio"])
        self.assertEqual(0.0005, report["failed_request_ratio"])
        self.assertEqual("b" * 64, report["telemetry_input_sha256"])
        self.assertEqual("a" * 40, report["deployed_commit"])
        self.assertTrue(all(item["status"] == "pass" for item in report["suite_results"]))

    def test_production_slo_import_rejects_telemetry_from_another_deployment(self):
        policy = readiness.load_policy(POLICY_PATH)
        telemetry = _valid_slo_telemetry()
        telemetry["deployed_commit"] = "b" * 40

        report = slo_import.build_evidence(
            telemetry,
            policy=policy,
            current_commit="a" * 40,
            source_tree_clean=True,
            telemetry_input_sha256="b" * 64,
        )

        self.assertFalse(report["ok"])
        self.assertIn("must match current git commit", " ".join(report["issues"]))

    def test_production_slo_validator_requires_deployed_commit_binding(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item for item in policy["required_evidence"] if item["id"] == "production-service-slo-window"
        )
        telemetry = _valid_slo_telemetry()
        telemetry.pop("deployed_commit")
        payload = {
            **telemetry,
            "commit": "a" * 40,
            "telemetry_input_sha256": "a" * 64,
            "successful_request_ratio": 0.9995,
            "failed_request_ratio": 0.0005,
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("production-service-slo-window.json"),
        )

        self.assertTrue(any("deployed_commit must be a full 40-character SHA" in issue for issue in issues))

    def test_production_slo_import_rejects_untrustworthy_evidence(self):
        policy = readiness.load_policy(POLICY_PATH)
        now = datetime.now(timezone.utc)
        cases: list[tuple[str, dict[str, object], bool, str]] = []

        mismatched = _valid_slo_telemetry(window_end=now)
        mismatched["failed_request_count"] = 499
        cases.append(("mismatched counts", mismatched, True, "must equal eligible_request_count"))

        stale = _valid_slo_telemetry(window_end=now - timedelta(days=3))
        cases.append(("stale window", stale, True, "window is stale"))

        future = _valid_slo_telemetry(window_end=now + timedelta(days=1))
        cases.append(("future window", future, True, "cannot end in the future"))

        unsafe_source = _valid_slo_telemetry(window_end=now)
        unsafe_source["telemetry_source"] = "https://user:secret@example.test?token=secret"
        cases.append(("unsafe source", unsafe_source, True, "credential-free identifier"))

        cases.append(("dirty source", _valid_slo_telemetry(window_end=now), False, "must be clean"))

        non_finite_latency = _valid_slo_telemetry(window_end=now)
        non_finite_latency["read_latency_p95_ms"] = float("inf")
        cases.append(("infinite latency", non_finite_latency, True, "non-negative number"))

        non_finite_snapshot = _valid_slo_telemetry(window_end=now)
        non_finite_snapshot["operational_snapshot_age_seconds"] = float("nan")
        cases.append(("NaN snapshot age", non_finite_snapshot, True, "non-negative number"))

        for name, telemetry, source_tree_clean, expected_issue in cases:
            with self.subTest(name=name):
                report = slo_import.build_evidence(
                    telemetry,
                    policy=policy,
                    current_commit="a" * 40,
                    source_tree_clean=source_tree_clean,
                    telemetry_input_sha256="b" * 64,
                    generated_at=now,
                )
                self.assertFalse(report["ok"])
                self.assertTrue(
                    any(expected_issue in issue for issue in report["issues"]),
                    report["issues"],
                )

    def test_policy_and_telemetry_json_reject_non_finite_constants(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            policy_path = temporary_root / "policy.json"
            policy_path.write_text(
                '{"schema_version": 1, "target": NaN}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                readiness.load_policy(policy_path)

            telemetry_path = temporary_root / "telemetry.json"
            telemetry_path.write_text(
                '{"read_latency_p95_ms": Infinity}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                slo_import.import_evidence(telemetry_path)

    def test_short_production_window_cannot_satisfy_rolling_slo(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item for item in policy["required_evidence"] if item["id"] == "production-service-slo-window"
        )
        payload = {
            "window_start": "2026-07-01T00:00:00+00:00",
            "window_end": "2026-07-02T00:00:00+00:00",
            "successful_request_ratio": 1.0,
            "failed_request_ratio": 0.0,
            "read_latency_p95_ms": 1.0,
            "operational_snapshot_age_seconds": 1.0,
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("production-service-slo-window.json"),
        )

        self.assertTrue(any("at least 30 days" in issue for issue in issues))

    def test_production_slo_validator_rejects_stale_and_impossible_ratios(self):
        policy = readiness.load_policy(POLICY_PATH)
        requirement = next(
            item for item in policy["required_evidence"] if item["id"] == "production-service-slo-window"
        )
        telemetry = _valid_slo_telemetry(window_end=datetime.now(timezone.utc) - timedelta(days=3))
        payload = {
            **telemetry,
            "telemetry_input_sha256": "a" * 64,
            "successful_request_ratio": 0.9,
            "failed_request_ratio": 0.2,
        }

        issues = readiness._validate_evidence_metrics(
            requirement,
            payload,
            policy=policy,
            path=Path("production-service-slo-window.json"),
        )

        self.assertTrue(any("window is stale" in issue for issue in issues))
        self.assertTrue(any("ratios must sum to 1" in issue for issue in issues))
        self.assertTrue(any("does not match request counts" in issue for issue in issues))

    def test_authoritative_verifiers_run_operational_readiness_gates(self):
        verify_all = (REPO_ROOT / "tools" / "verify_all.py").read_text(encoding="utf-8")
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        for script in (
            "tools/check_operational_readiness.py",
            "tools/run_service_sustained_probe.py",
            "tools/run_operational_recovery_drill.py",
        ):
            self.assertIn(script, verify_all)
            self.assertIn(script, ci_workflow)


if __name__ == "__main__":
    unittest.main()
