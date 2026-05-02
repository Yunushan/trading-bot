import json
import math
import socket
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import EmbeddedDesktopServiceClient, RemoteDesktopServiceClient, create_desktop_service_client  # noqa: E402
from app.service.auth import (  # noqa: E402
    auth_required,
    host_requires_service_api_token,
    validate_bearer_token,
)
from app.service.api_contract import (  # noqa: E402
    SERVICE_API_BASE_PATH,
    SERVICE_API_LEGACY_BASE_PATH,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_LEGACY_ROUTE_PATHS,
    SERVICE_API_STREAM_DASHBOARD_PATH,
    SERVICE_API_VERSION,
)
from app.service.api import (  # noqa: E402
    FASTAPI_AVAILABLE,
    ServiceApiBackgroundHost,
    create_service_api_app,
    run_service_api_server,
)
from app.jsonl_rotation import jsonl_backup_path  # noqa: E402
from app.service.runners import bot_runtime_state as bot_runtime_state_module  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402
from app.settings import ConfigValidationError  # noqa: E402

REPO_ROOT = PYTHON_ROOT.parents[1]


class _FakeBacktestWrapper:
    def __init__(self, **kwargs):
        self.account_type = str(kwargs.get("account_type") or "FUTURES").upper()
        self.mode = str(kwargs.get("mode") or "Demo/Testnet")
        self.api_key = str(kwargs.get("api_key") or "")
        self.api_secret = str(kwargs.get("api_secret") or "")
        self.indicator_source = "Binance futures"

    @staticmethod
    def clamp_futures_leverage(_symbol, requested_leverage):
        return max(1, int(requested_leverage or 1))

    def get_klines_range(self, _symbol, _interval, start_time, end_time, limit=1500):
        if not PANDAS_AVAILABLE or pd is None:
            raise RuntimeError("pandas is required for the fake backtest wrapper")
        start_dt = pd.to_datetime(start_time)
        end_dt = pd.to_datetime(end_time)
        periods = max(200, min(int(limit or 200), 360))
        index = pd.date_range(start=start_dt, end=end_dt, periods=periods)
        closes = [100.0 + math.sin(step / 5.0) * 12.0 + math.cos(step / 17.0) * 3.0 for step in range(len(index))]
        opens = [value - 0.4 for value in closes]
        highs = [value + 1.2 for value in closes]
        lows = [value - 1.2 for value in closes]
        volumes = [500 + (step % 15) * 7 for step in range(len(index))]
        return pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            },
            index=index,
        )


def _mark_operational_inputs_stale(service: TradingBotService, *, seconds: int = 900) -> str:
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    service.set_exchange_connector_snapshot(
        {
            "health": "ok",
            "state": "ready",
            "generated_at": stale_at,
        },
        source="unit-test",
    )
    runtime = service._runtime
    with runtime._lock:
        runtime._account_snapshot = replace(
            runtime._account_snapshot,
            source="unit-test",
            generated_at=stale_at,
        )
        runtime._portfolio_snapshot = replace(
            runtime._portfolio_snapshot,
            source="unit-test",
            generated_at=stale_at,
        )
    return stale_at


def _mark_operational_inputs_fresh(service: TradingBotService) -> str:
    fresh_at = datetime.now(timezone.utc).isoformat()
    service.set_exchange_connector_snapshot(
        {
            "health": "ok",
            "state": "ready",
            "generated_at": fresh_at,
        },
        source="unit-test",
    )
    service.set_account_snapshot(
        total_balance=1000.0,
        available_balance=900.0,
        source="unit-test",
    )
    service.set_portfolio_snapshot(
        open_position_records={},
        closed_position_records=[],
        source="unit-test",
    )
    return fresh_at


def _mark_running_execution_heartbeat_stale(service: TradingBotService, *, seconds: int = 900) -> str:
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    service.set_runtime_state(active=True, active_engine_count=1, source="unit-test")
    service.set_execution_snapshot(
        executor_kind="local-service-executor",
        owner="service-process",
        state="running",
        workload_kind="service-runtime-session",
        session_id="stale-session",
        requested_job_count=1,
        active_engine_count=1,
        heartbeat_at=stale_at,
        last_action="heartbeat",
        last_message="Execution heartbeat is stale.",
        started_at=stale_at,
        source="unit-test",
    )
    return stale_at


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value)


class ServiceApiSmokeTests(unittest.TestCase):
    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_app_exposes_expected_routes(self):
        app = create_service_api_app()
        paths = {route.path for route in app.router.routes}
        schema_paths = set(app.openapi()["paths"])
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn("/ui", paths)
        self.assertEqual(SERVICE_API_BASE_PATH, "/api/v1")
        self.assertEqual(SERVICE_API_LEGACY_BASE_PATH, "/api")
        self.assertEqual(SERVICE_API_VERSION, "1.0.0")
        self.assertEqual(SERVICE_API_STREAM_DASHBOARD_PATH, "/api/v1/stream/dashboard")
        for route_name in (
            "dashboard",
            "runtime",
            "status",
            "config",
            "config_summary",
            "account",
            "portfolio",
            "exchange_connector",
            "connector_order_circuit_breaker",
            "connector_order_circuit_breaker_reset",
            "connector_order_circuit_incidents",
            "logs",
            "terminal_run",
            "llm_providers",
            "llm_config",
            "llm_prompt",
            "execution",
            "backtest",
            "runtime_state",
            "operational_preflight",
            "control_start",
            "control_stop",
            "control_start_failed",
            "backtest_run",
            "backtest_stop",
            "stream_dashboard",
        ):
            self.assertIn(SERVICE_API_ROUTE_PATHS[route_name], paths)
            self.assertIn(SERVICE_API_ROUTE_PATHS[route_name], schema_paths)
            self.assertIn(SERVICE_API_LEGACY_ROUTE_PATHS[route_name], paths)
            self.assertNotIn(SERVICE_API_LEGACY_ROUTE_PATHS[route_name], schema_paths)
        self.assertEqual(app.version, SERVICE_API_VERSION)
        self.assertEqual(app.state.service_api_base_path, SERVICE_API_BASE_PATH)
        self.assertEqual(app.state.service_api_legacy_base_path, SERVICE_API_LEGACY_BASE_PATH)
        self.assertEqual(app.state.service_api_stream_path, SERVICE_API_STREAM_DASHBOARD_PATH)
        self.assertEqual(Path(app.state.web_client_dir).name, "web-dashboard")
        self.assertEqual(app.state.service_api_host_context, "standalone-service")
        self.assertEqual(app.state.service_api_host_owner, "service-process")
        self.assertEqual(
            app.state.service.describe_runtime().to_dict()["control_plane"]["mode"],
            "local-service-executor",
        )

    def test_desktop_service_client_defaults_to_embedded_mode(self):
        client = create_desktop_service_client(config={"mode": "Paper"})
        self.assertIsInstance(client, EmbeddedDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "embedded")
        preflight = client.get_operational_preflight()
        self.assertIsInstance(preflight, dict)
        self.assertIn("start", preflight)
        self.assertIn("orders", preflight)

    def test_desktop_service_client_can_be_forced_to_remote_mode(self):
        client = create_desktop_service_client(
            client_mode="remote",
            base_url="http://127.0.0.1:9000",
        )
        self.assertIsInstance(client, RemoteDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "remote")
        self.assertEqual(descriptor.get("base_url"), "http://127.0.0.1:9000")
        self.assertTrue(callable(getattr(client, "get_operational_preflight", None)))

    def test_service_api_auth_helpers(self):
        self.assertFalse(auth_required(""))
        self.assertTrue(validate_bearer_token(None, ""))
        self.assertTrue(validate_bearer_token("Bearer token-123", "token-123"))
        self.assertFalse(validate_bearer_token("Bearer wrong", "token-123"))
        self.assertFalse(host_requires_service_api_token("127.0.0.1"))
        self.assertFalse(host_requires_service_api_token("localhost"))
        self.assertTrue(host_requires_service_api_token("0.0.0.0"))
        self.assertTrue(host_requires_service_api_token("192.168.1.10"))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_exposed_service_api_requires_token(self):
        with self.assertRaisesRegex(RuntimeError, "BOT_SERVICE_API_TOKEN"):
            run_service_api_server(host="0.0.0.0", port=8000, api_token="")
        with self.assertRaisesRegex(RuntimeError, "BOT_SERVICE_API_TOKEN"):
            ServiceApiBackgroundHost(host="0.0.0.0", port=8000, api_token="")

    def test_service_config_patch_round_trip(self):
        service = TradingBotService()
        initial_config = service.get_config_payload().to_dict()
        self.assertEqual(initial_config["mode"], "Demo/Testnet")

        payload = service.update_config(
            {
                "mode": "Demo/Testnet",
                "symbols": ["ETHUSDT", "BTCUSDT"],
                "intervals": ["5m", "15m"],
                "leverage": 10,
                "position_pct": 4.5,
                "order_audit_max_bytes": 4096,
                "order_audit_backup_count": 3,
                "connector_order_circuit_incident_log_max_bytes": 2048,
                "connector_order_circuit_incident_log_backup_count": 4,
                "operational_live_start_gate_enabled": False,
                "operational_live_order_gate_enabled": False,
            }
        ).to_dict()
        self.assertEqual(payload["mode"], "Demo/Testnet")
        self.assertEqual(payload["symbols"], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual(payload["intervals"], ["5m", "15m"])
        self.assertEqual(payload["leverage"], 10)
        self.assertEqual(payload["position_pct"], 4.5)
        self.assertEqual(payload["order_audit_max_bytes"], 4096)
        self.assertEqual(payload["order_audit_backup_count"], 3)
        self.assertEqual(payload["connector_order_circuit_incident_log_max_bytes"], 2048)
        self.assertEqual(payload["connector_order_circuit_incident_log_backup_count"], 4)
        self.assertFalse(payload["operational_live_start_gate_enabled"])
        self.assertFalse(payload["operational_live_order_gate_enabled"])

        summary = service.get_config_summary().to_dict()
        self.assertEqual(summary["symbol_count"], 2)
        self.assertEqual(summary["interval_count"], 2)
        self.assertEqual(summary["llm_provider"], "openai")
        self.assertFalse(summary["llm_enabled"])
        operational = service.get_operational_snapshot()
        self.assertEqual(4096, operational["order_audit"]["max_bytes"])
        self.assertEqual(3, operational["order_audit"]["backup_count"])
        self.assertEqual(2048, operational["connector_order_circuit_incident_log"]["max_bytes"])
        self.assertEqual(4, operational["connector_order_circuit_incident_log"]["backup_count"])

    def test_service_config_patch_rejects_invalid_values_and_preserves_previous_config(self):
        service = TradingBotService()
        previous = service.get_config_payload().to_dict()

        with self.assertRaises(ConfigValidationError) as caught:
            service.update_config(
                {
                    "symbols": [],
                    "intervals": ["bad interval"],
                    "leverage": 0,
                    "position_pct": 0,
                    "order_audit_backup_count": -1,
                    "connector_order_circuit_incident_log_backup_count": 101,
                }
            )

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("symbols", fields)
        self.assertIn("intervals", fields)
        self.assertIn("leverage", fields)
        self.assertIn("position_pct", fields)
        self.assertIn("order_audit_backup_count", fields)
        self.assertIn("connector_order_circuit_incident_log_backup_count", fields)
        self.assertEqual(previous, service.get_config_payload().to_dict())

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_config_validation_errors_are_client_errors(self):
        try:
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover - depends on optional test dependency stack
            self.skipTest(f"FastAPI TestClient unavailable: {exc}")

        app = create_service_api_app(service=TradingBotService())
        client = TestClient(app)

        response = client.patch(
            f"{SERVICE_API_BASE_PATH}/config",
            json={"config": {"leverage": 0, "position_pct": 0}},
        )

        self.assertEqual(422, response.status_code)
        detail = response.json()["detail"]
        fields = {issue["field"] for issue in detail["issues"]}
        self.assertIn("leverage", fields)
        self.assertIn("position_pct", fields)

    def test_service_dashboard_snapshot_contains_expected_sections(self):
        service = TradingBotService()
        snapshot = service.get_dashboard_snapshot(log_limit=5)
        self.assertIn("runtime", snapshot)
        self.assertIn("status", snapshot)
        self.assertIn("execution", snapshot)
        self.assertIn("backtest", snapshot)
        self.assertIn("config", snapshot)
        self.assertIn("config_summary", snapshot)
        self.assertIn("account", snapshot)
        self.assertIn("portfolio", snapshot)
        self.assertIn("logs", snapshot)
        self.assertIn("operational", snapshot)
        self.assertIsInstance(snapshot["logs"], list)
        self.assertIn("control_plane", snapshot["runtime"])
        self.assertEqual(snapshot["runtime"]["control_plane"]["mode"], "intent-only")
        self.assertEqual(snapshot["execution"]["executor_kind"], "unbound")
        self.assertEqual(snapshot["execution"]["workload_kind"], "unbound")
        self.assertEqual(snapshot["backtest"]["state"], "idle")
        self.assertEqual(snapshot["backtest"]["run_count"], 0)
        self.assertIn("llm", snapshot["config"])
        self.assertEqual(snapshot["config"]["llm"]["provider"], "openai")
        self.assertEqual(10 * 1024 * 1024, snapshot["config"]["order_audit_max_bytes"])
        self.assertEqual(1, snapshot["config"]["order_audit_backup_count"])
        self.assertEqual(
            2 * 1024 * 1024,
            snapshot["config"]["connector_order_circuit_incident_log_max_bytes"],
        )
        self.assertEqual(1, snapshot["config"]["connector_order_circuit_incident_log_backup_count"])
        self.assertEqual(120.0, snapshot["config"]["operational_connector_snapshot_stale_seconds"])
        self.assertEqual(10.0, snapshot["config"]["operational_execution_heartbeat_stale_seconds"])
        self.assertEqual(300.0, snapshot["config"]["operational_account_snapshot_stale_seconds"])
        self.assertEqual(300.0, snapshot["config"]["operational_portfolio_snapshot_stale_seconds"])
        self.assertTrue(snapshot["config"]["operational_live_start_gate_enabled"])
        self.assertTrue(snapshot["config"]["operational_live_order_gate_enabled"])
        self.assertEqual(snapshot["operational"]["health"], "ok")
        self.assertEqual(snapshot["status"]["operational_health"], "ok")
        self.assertIn("preflight", snapshot["operational"])
        self.assertIn("start", snapshot["operational"]["preflight"])
        self.assertIn("orders", snapshot["operational"]["preflight"])
        self.assertIn("exchange_connector", snapshot["operational"])
        self.assertIn("connector_order_circuit_breaker", snapshot["operational"])
        self.assertIn("connector_order_circuit_incident_log", snapshot["operational"])
        self.assertEqual(snapshot["status"]["connector_health"], "unknown")
        self.assertEqual(snapshot["operational"]["exchange_connector"]["health"], "unknown")
        self.assertFalse(snapshot["operational"]["connector_order_circuit_breaker"]["active"])
        self.assertEqual(
            "~/.trading-bot/connector_order_circuit_incidents.jsonl",
            snapshot["operational"]["connector_order_circuit_incident_log"]["path"],
        )
        self.assertTrue(snapshot["operational"]["order_audit"]["enabled"])
        self.assertEqual(10 * 1024 * 1024, snapshot["operational"]["order_audit"]["max_bytes"])
        self.assertEqual(1, snapshot["operational"]["order_audit"]["backup_count"])
        self.assertEqual(
            2 * 1024 * 1024,
            snapshot["operational"]["connector_order_circuit_incident_log"]["max_bytes"],
        )
        self.assertEqual(1, snapshot["operational"]["connector_order_circuit_incident_log"]["backup_count"])

    def test_service_operational_snapshot_summarizes_logs_and_audit_health(self):
        service = TradingBotService(config={"order_audit_enabled": False})

        service.record_log_event("guard=opp_open block BUY", source="strategy", level="warning")
        service.record_log_event("futures order failed symbol=BTCUSDT", source="strategy", level="error")

        status = service.get_status().to_dict()
        operational = service.get_operational_snapshot()
        dashboard = service.get_dashboard_snapshot(log_limit=2)

        self.assertEqual("error", status["operational_health"])
        self.assertEqual("error", operational["health"])
        self.assertEqual("error", dashboard["operational"]["health"])
        self.assertFalse(operational["order_audit"]["enabled"])
        self.assertEqual("default", operational["order_audit"]["path_source"])
        self.assertEqual(2, operational["logs"]["total"])
        self.assertEqual(1, operational["logs"]["warning_count"])
        self.assertEqual(1, operational["logs"]["error_count"])
        self.assertIn("futures order failed", operational["logs"]["last_error"]["message"])
        self.assertTrue(any("Order audit logging is disabled." == item for item in operational["attention"]))

    def test_service_operational_snapshot_exposes_exchange_connector_health(self):
        service = TradingBotService()

        service.set_exchange_connector_snapshot(
            {
                "health": "warning",
                "state": "rate_limited",
                "connector_backend": "binance-sdk-spot",
                "rate_limit": {"active": True, "seconds_until_unban": 12.5},
                "last_error": {
                    "category": "rate_limited",
                    "message": "Too many requests signature=leaked",
                    "retryable": True,
                },
            },
            source="unit-test",
        )

        status = service.get_status().to_dict()
        operational = service.get_operational_snapshot()
        dashboard = service.get_dashboard_snapshot(log_limit=1)

        self.assertEqual("warning", status["connector_health"])
        self.assertEqual("warning", status["operational_health"])
        self.assertEqual("rate_limited", status["exchange_connector"]["state"])
        self.assertTrue(operational["exchange_connector"]["rate_limit"]["active"])
        self.assertIn("<redacted>", operational["exchange_connector"]["last_error"]["message"])
        self.assertNotIn("leaked", json.dumps(dashboard))
        self.assertTrue(any("Exchange connector rate_limited" in item for item in operational["attention"]))

    def test_service_operational_snapshot_exposes_order_audit_write_failure(self):
        service = TradingBotService()

        service.set_exchange_connector_snapshot(
            {
                "health": "ok",
                "state": "ready",
                "order_audit": {
                    "enabled": True,
                    "state": "write_failed",
                    "write_ok": False,
                    "last_write_error": {
                        "message": "disk full api_secret=leaked",
                        "path": "C:/tmp/orders.jsonl",
                    },
                    "last_write_error_at": "2026-05-01T00:00:00+00:00",
                },
            },
            source="unit-test",
        )

        status = service.get_status().to_dict()
        operational = service.get_operational_snapshot()
        rendered = json.dumps(operational, sort_keys=True)

        self.assertEqual("warning", status["connector_health"])
        self.assertEqual("warning", status["operational_health"])
        self.assertEqual("warning", operational["exchange_connector"]["health"])
        self.assertEqual("order_audit_write_failed", operational["exchange_connector"]["state"])
        self.assertEqual("write_failed", operational["order_audit"]["state"])
        self.assertFalse(operational["order_audit"]["write_ok"])
        self.assertTrue(any("Order audit write failed" in item for item in operational["attention"]))
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("leaked", rendered)

    def test_service_operational_snapshot_warns_on_stale_active_snapshots(self):
        service = TradingBotService()
        stale_at = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()

        service.set_runtime_state(active=True, active_engine_count=1, source="unit-test")
        service.set_execution_snapshot(
            state="running",
            requested_job_count=1,
            active_engine_count=1,
            heartbeat_at=stale_at,
            source="unit-test",
        )
        service.set_exchange_connector_snapshot(
            {
                "health": "ok",
                "state": "ready",
                "generated_at": stale_at,
            },
            source="unit-test",
        )
        runtime = service._runtime
        with runtime._lock:
            runtime._account_snapshot = replace(
                runtime._account_snapshot,
                source="unit-test",
                generated_at=stale_at,
            )
            runtime._portfolio_snapshot = replace(
                runtime._portfolio_snapshot,
                source="unit-test",
                generated_at=stale_at,
            )

        status = service.get_status().to_dict()
        operational = service.get_operational_snapshot()
        dashboard = service.get_dashboard_snapshot(log_limit=1)
        attention = "\n".join(operational["attention"])

        self.assertEqual("warning", operational["health"])
        self.assertEqual("warning", status["operational_health"])
        self.assertEqual("warning", dashboard["operational"]["health"])
        self.assertTrue(operational["freshness"]["exchange_connector"]["stale"])
        self.assertTrue(operational["freshness"]["execution"]["stale"])
        self.assertTrue(operational["freshness"]["account"]["stale"])
        self.assertTrue(operational["freshness"]["portfolio"]["stale"])
        self.assertEqual(120.0, operational["freshness"]["exchange_connector"]["max_age_seconds"])
        self.assertEqual(10.0, operational["freshness"]["execution"]["max_age_seconds"])
        self.assertEqual(300.0, operational["freshness"]["account"]["max_age_seconds"])
        self.assertEqual(300.0, operational["freshness"]["portfolio"]["max_age_seconds"])
        self.assertGreaterEqual(operational["freshness"]["exchange_connector"]["age_seconds"], 800)
        self.assertIn("Exchange connector snapshot is stale", attention)
        self.assertIn("Execution heartbeat is stale", attention)
        self.assertIn("Account snapshot is stale", attention)
        self.assertIn("Portfolio snapshot is stale", attention)

    def test_service_operational_snapshot_uses_configured_freshness_thresholds(self):
        service = TradingBotService(
            config={
                "operational_connector_snapshot_stale_seconds": 1200,
                "operational_execution_heartbeat_stale_seconds": 1200,
                "operational_account_snapshot_stale_seconds": 1200,
                "operational_portfolio_snapshot_stale_seconds": 1200,
            }
        )
        stale_at = (datetime.now(timezone.utc) - timedelta(seconds=900)).isoformat()

        service.set_runtime_state(active=True, active_engine_count=1, source="unit-test")
        service.set_execution_snapshot(
            state="running",
            requested_job_count=1,
            active_engine_count=1,
            heartbeat_at=stale_at,
            source="unit-test",
        )
        service.set_exchange_connector_snapshot(
            {
                "health": "ok",
                "state": "ready",
                "generated_at": stale_at,
            },
            source="unit-test",
        )
        runtime = service._runtime
        with runtime._lock:
            runtime._account_snapshot = replace(
                runtime._account_snapshot,
                source="unit-test",
                generated_at=stale_at,
            )
            runtime._portfolio_snapshot = replace(
                runtime._portfolio_snapshot,
                source="unit-test",
                generated_at=stale_at,
            )

        operational = service.get_operational_snapshot()
        freshness = operational["freshness"]

        self.assertEqual("ok", operational["health"])
        self.assertEqual(1200.0, freshness["exchange_connector"]["max_age_seconds"])
        self.assertEqual(1200.0, freshness["execution"]["max_age_seconds"])
        self.assertEqual(1200.0, freshness["account"]["max_age_seconds"])
        self.assertEqual(1200.0, freshness["portfolio"]["max_age_seconds"])
        self.assertFalse(freshness["exchange_connector"]["stale"])
        self.assertFalse(freshness["execution"]["stale"])
        self.assertFalse(freshness["account"]["stale"])
        self.assertFalse(freshness["portfolio"]["stale"])

    def test_service_operational_snapshot_exposes_connector_order_circuit_breaker(self):
        service = TradingBotService()

        trip = service.set_connector_order_circuit_breaker_snapshot(
            {
                "active": True,
                "state": "open",
                "reason": "connector_order_block",
                "message": "Connector health circuit breaker paused trading api_secret=leaked",
                "block_count": 2,
                "block_threshold": 2,
                "block_window_seconds": 30,
                "connector_health": "error",
                "connector_state": "network_offline",
            },
            source="unit-test",
        )

        status = service.get_status().to_dict()
        operational = service.get_operational_snapshot()
        dashboard = service.get_dashboard_snapshot(log_limit=1)

        self.assertTrue(trip["active"])
        self.assertEqual("open", trip["state"])
        self.assertEqual("error", status["operational_health"])
        self.assertEqual("error", operational["health"])
        self.assertTrue(operational["connector_order_circuit_breaker"]["active"])
        self.assertIn("<redacted>", json.dumps(dashboard))
        self.assertNotIn("leaked", json.dumps(dashboard))
        self.assertTrue(any("circuit breaker paused" in item for item in operational["attention"]))

        reset = service.reset_connector_order_circuit_breaker(source="unit-test")
        operational_after_reset = service.get_operational_snapshot()
        logs = [item.to_dict() for item in service.get_recent_logs(limit=5)]

        self.assertFalse(reset["active"])
        self.assertEqual("closed", reset["state"])
        self.assertEqual("ok", operational_after_reset["health"])
        self.assertFalse(operational_after_reset["connector_order_circuit_breaker"]["active"])
        self.assertTrue(any("circuit breaker paused" in item["message"] for item in logs))
        self.assertTrue(any("circuit breaker reset" in item["message"] for item in logs))
        self.assertTrue(all(item["level"] == "info" for item in logs))

    def test_service_connector_order_circuit_incidents_are_persisted_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            incident_path = Path(tmpdir) / "connector-order-circuit.jsonl"
            service = TradingBotService(
                config={"connector_order_circuit_incident_log_path": str(incident_path)}
            )

            service.set_connector_order_circuit_breaker_snapshot(
                {
                    "active": True,
                    "state": "open",
                    "reason": "connector_order_block",
                    "message": "Connector health circuit breaker paused trading api_secret=leaked",
                    "block_count": 2,
                    "block_threshold": 2,
                    "connector_health": "error",
                    "connector_state": "network_offline",
                },
                source="unit-test",
            )
            service.reset_connector_order_circuit_breaker(source="unit-test")

            events = [
                json.loads(line)
                for line in incident_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            operational = service.get_operational_snapshot()
            rendered_events = json.dumps(events, sort_keys=True)

            self.assertEqual(
                ["connector_order_circuit_trip", "connector_order_circuit_reset"],
                [event["event"] for event in events],
            )
            self.assertEqual("configured", operational["connector_order_circuit_incident_log"]["path_source"])
            self.assertEqual(str(incident_path), operational["connector_order_circuit_incident_log"]["path"])
            self.assertEqual(
                "reset",
                operational["connector_order_circuit_incident_log"]["last_event"]["action"],
            )
            self.assertIn("<redacted>", rendered_events)
            self.assertNotIn("leaked", rendered_events)

    def test_service_connector_order_circuit_incident_tail_reads_latest_jsonl_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            incident_path = Path(tmpdir) / "connector-order-circuit.jsonl"
            service = TradingBotService(
                config={"connector_order_circuit_incident_log_path": str(incident_path)}
            )

            for index in range(3):
                service.set_connector_order_circuit_breaker_snapshot(
                    {
                        "active": True,
                        "state": "open",
                        "reason": "connector_order_block",
                        "message": f"Connector health circuit breaker paused trading api_secret=leaked-{index}",
                        "block_count": index + 1,
                        "block_threshold": 2,
                    },
                    source="unit-test",
                )
                service.reset_connector_order_circuit_breaker(source="unit-test")

            tail = service.get_connector_order_circuit_incidents(limit=3)
            rendered_tail = json.dumps(tail, sort_keys=True)

            self.assertTrue(tail["exists"])
            self.assertEqual(3, tail["limit"])
            self.assertEqual(3, tail["count"])
            self.assertEqual(6, tail["total_read"])
            self.assertEqual(1, tail["backup_count"])
            self.assertEqual("connector_order_circuit_reset", tail["last_event"]["event"])
            self.assertEqual(
                [
                    "connector_order_circuit_reset",
                    "connector_order_circuit_trip",
                    "connector_order_circuit_reset",
                ],
                [event["event"] for event in tail["events"]],
            )
            self.assertIn("<redacted>", rendered_tail)
            self.assertNotIn("leaked", rendered_tail)

    def test_service_connector_order_circuit_incident_log_rotates_when_size_limit_is_exceeded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            incident_path = Path(tmpdir) / "connector-order-circuit.jsonl"
            backup_path = jsonl_backup_path(incident_path)
            second_backup_path = jsonl_backup_path(incident_path, 2)
            expired_backup_path = jsonl_backup_path(incident_path, 3)
            service = TradingBotService(
                config={
                    "connector_order_circuit_incident_log_path": str(incident_path),
                    "connector_order_circuit_incident_log_max_bytes": 1,
                    "connector_order_circuit_incident_log_backup_count": 2,
                }
            )

            for index in range(3):
                service.set_connector_order_circuit_breaker_snapshot(
                    {
                        "active": True,
                        "state": "open",
                        "reason": "connector_order_block",
                        "message": f"Connector health circuit breaker paused trading api_secret=leaked-{index}",
                        "block_count": index + 1,
                        "block_threshold": 2,
                    },
                    source="unit-test",
                )
                service.reset_connector_order_circuit_breaker(source="unit-test")

            active_rows = [
                json.loads(line)
                for line in incident_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            backup_rows = [
                json.loads(line)
                for line in backup_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            second_backup_rows = [
                json.loads(line)
                for line in second_backup_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            rendered_events = (
                incident_path.read_text(encoding="utf-8")
                + "\n"
                + backup_path.read_text(encoding="utf-8")
                + "\n"
                + second_backup_path.read_text(encoding="utf-8")
            )
            tail = service.get_connector_order_circuit_incidents(limit=10)

            self.assertTrue(incident_path.exists())
            self.assertTrue(backup_path.exists())
            self.assertTrue(second_backup_path.exists())
            self.assertFalse(expired_backup_path.exists())
            self.assertEqual(["connector_order_circuit_reset"], [row["event"] for row in active_rows])
            self.assertEqual(["connector_order_circuit_trip"], [row["event"] for row in backup_rows])
            self.assertEqual(["connector_order_circuit_reset"], [row["event"] for row in second_backup_rows])
            self.assertIn("<redacted>", rendered_events)
            self.assertNotIn("leaked", rendered_events)
            self.assertEqual(3, tail["count"])
            self.assertEqual(3, tail["total_read"])
            self.assertEqual(1, tail["max_bytes"])
            self.assertEqual(2, tail["backup_count"])
            self.assertEqual(
                [
                    "connector_order_circuit_reset",
                    "connector_order_circuit_trip",
                    "connector_order_circuit_reset",
                ],
                [event["event"] for event in tail["events"]],
            )
            self.assertEqual("connector_order_circuit_reset", tail["last_event"]["event"])

    def test_service_connector_order_circuit_incident_write_failure_is_operationally_visible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            incident_path = Path(tmpdir) / "connector-order-circuit.jsonl"
            service = TradingBotService(
                config={"connector_order_circuit_incident_log_path": str(incident_path)}
            )
            original_rotate = bot_runtime_state_module.rotate_jsonl_if_needed

            def fail_rotate(*_args, **_kwargs):
                raise OSError("disk full api_secret=leaked")

            try:
                bot_runtime_state_module.rotate_jsonl_if_needed = fail_rotate
                service.set_connector_order_circuit_breaker_snapshot(
                    {
                        "active": True,
                        "state": "open",
                        "reason": "connector_order_block",
                        "message": "Connector order circuit breaker paused.",
                    },
                    source="unit-test",
                )
                service.reset_connector_order_circuit_breaker(source="unit-test", force=True)
            finally:
                bot_runtime_state_module.rotate_jsonl_if_needed = original_rotate

            operational = service.get_operational_snapshot()
            status = service.get_status().to_dict()
            incident_log = operational["connector_order_circuit_incident_log"]
            rendered = json.dumps(operational, sort_keys=True)

            self.assertEqual("warning", operational["health"])
            self.assertEqual("warning", status["operational_health"])
            self.assertFalse(operational["connector_order_circuit_breaker"]["active"])
            self.assertFalse(incident_log["write_ok"])
            self.assertIn("disk full", incident_log["last_write_error"]["message"])
            self.assertTrue(
                any("incident log write failed" in item for item in operational["attention"])
            )
            self.assertIn("<redacted>", rendered)
            self.assertNotIn("leaked", rendered)

            service.set_connector_order_circuit_breaker_snapshot(
                {
                    "active": True,
                    "state": "open",
                    "reason": "connector_order_block",
                    "message": "Connector order circuit breaker paused.",
                },
                source="unit-test",
            )
            service.reset_connector_order_circuit_breaker(source="unit-test", force=True)

            recovered_log = service.get_operational_snapshot()["connector_order_circuit_incident_log"]
            self.assertTrue(recovered_log["write_ok"])
            self.assertIsNone(recovered_log["last_write_error"])
            self.assertTrue(recovered_log["last_write_ok_at"])

    def test_service_connector_order_circuit_reset_blocks_when_connector_still_error(self):
        service = TradingBotService()
        service.set_exchange_connector_snapshot(
            {
                "last_error": {
                    "category": "auth",
                    "message": "Invalid API key api_secret=leaked",
                    "retryable": False,
                },
            },
            source="unit-test",
        )
        service.set_connector_order_circuit_breaker_snapshot(
            {
                "active": True,
                "state": "open",
                "reason": "connector_order_block",
                "message": "Connector health circuit breaker paused trading.",
                "block_count": 2,
                "block_threshold": 2,
            },
            source="unit-test",
        )

        blocked = service.reset_connector_order_circuit_breaker(source="unit-test")
        dashboard = service.get_dashboard_snapshot(log_limit=5)

        self.assertTrue(blocked["active"])
        self.assertEqual("open", blocked["state"])
        self.assertTrue(blocked["reset_blocked"])
        self.assertIn("reset blocked", blocked["reset_blocked_reason"].lower())
        self.assertIn("<redacted>", blocked["reset_blocked_reason"])
        self.assertNotIn("leaked", json.dumps(dashboard))
        self.assertTrue(dashboard["operational"]["connector_order_circuit_breaker"]["active"])
        self.assertTrue(any("reset blocked" in item["message"].lower() for item in dashboard["logs"]))

        service.set_exchange_connector_snapshot(
            {
                "health": "ok",
                "state": "ready",
            },
            source="unit-test",
        )
        reset = service.reset_connector_order_circuit_breaker(source="unit-test")

        self.assertFalse(reset["active"])
        self.assertEqual("closed", reset["state"])
        self.assertFalse(reset["reset_blocked"])

    def test_service_logs_terminal_and_dashboard_redact_secret_text(self):
        service = TradingBotService(
            config={
                "api_key": "exchange-key",
                "api_secret": "exchange-secret",
                "llm_api_key": "llm-secret",
            }
        )

        service.record_log_event(
            "Authorization: Bearer service-token api_key=exchange-key api_secret=exchange-secret",
            source="source-token=source-secret",
            level="error",
        )
        service.set_execution_snapshot(
            state="running",
            last_message="token=execution-token",
            notes=("api_secret=execution-secret",),
            source="execution-source",
        )
        terminal_result = service.run_terminal_command(
            "config set api_key=command-key api_secret=command-secret llm_api_key=command-llm-key",
            source="test-terminal",
        ).to_dict()

        dashboard = service.get_dashboard_snapshot(log_limit=5)
        status = service.get_status().to_dict()
        rendered = json.dumps(
            {
                "terminal": terminal_result,
                "dashboard": dashboard,
                "status": status,
            },
            sort_keys=True,
        )

        self.assertIn("<redacted>", rendered)
        self.assertTrue(dashboard["config"]["api_credentials_present"])
        self.assertTrue(dashboard["config"]["llm"]["api_key_present"])
        for secret in (
            "exchange-key",
            "exchange-secret",
            "llm-secret",
            "service-token",
            "source-secret",
            "execution-token",
            "execution-secret",
            "command-key",
            "command-secret",
            "command-llm-key",
        ):
            self.assertNotIn(secret, rendered)

    def test_service_terminal_and_llm_config_commands(self):
        service = TradingBotService()

        providers = service.get_llm_provider_catalog()
        provider_by_key = {str(item["key"]): item for item in providers}
        self.assertIn("openai", provider_by_key)
        self.assertIn("anthropic", provider_by_key)
        self.assertIn("gemini", provider_by_key)
        self.assertIn("local", provider_by_key)
        self.assertIn("gpt-5.4-mini", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.3-codex", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("high", provider_by_key["openai"]["reasoning_efforts"])
        self.assertIn("deepseek-v4-flash", provider_by_key["deepseek"]["model_suggestions"])
        self.assertIn("max", provider_by_key["deepseek"]["reasoning_efforts"])
        self.assertEqual("http://127.0.0.1:11434/v1", provider_by_key["local"]["default_base_url"])

        status_result = service.run_terminal_command("status", source="test-terminal").to_dict()
        self.assertTrue(status_result["accepted"])
        self.assertEqual(status_result["exit_code"], 0)
        self.assertIn("lifecycle_phase", status_result["output"])

        llm_result = service.run_terminal_command(
            "llm set llm_provider=deepseek llm_model=deepseek-v4-flash llm_enabled=true llm_reasoning_effort=max",
            source="test-terminal",
        ).to_dict()
        self.assertTrue(llm_result["accepted"])
        llm_config = service.get_llm_config_payload()
        self.assertTrue(llm_config["enabled"])
        self.assertEqual(llm_config["provider"], "deepseek")
        self.assertEqual(llm_config["model"], "deepseek-v4-flash")
        self.assertEqual(llm_config["reasoning_effort"], "max")

        prompt_result = service.run_terminal_command("llm prompt Explain BTC risk", source="test-terminal").to_dict()
        self.assertTrue(prompt_result["accepted"])
        self.assertIn('"dry_run": true', prompt_result["output"])

    def test_local_service_executor_start_stop_updates_runtime(self):
        service = TradingBotService()
        service.enable_local_executor()

        start_result = service.request_start(requested_job_count=3, source="service-cli").to_dict()
        running_status = service.get_status().to_dict()
        runtime = service.describe_runtime().to_dict()
        running_execution = service.get_execution_snapshot().to_dict()

        self.assertTrue(start_result["accepted"])
        self.assertEqual(runtime["control_plane"]["mode"], "local-service-executor")
        self.assertEqual(running_status["lifecycle_phase"], "running")
        self.assertEqual(running_status["active_engine_count"], 3)
        self.assertEqual(running_execution["state"], "running")
        self.assertEqual(running_execution["workload_kind"], "service-runtime-session")
        self.assertEqual(running_execution["active_engine_count"], 3)
        self.assertTrue(running_execution["session_id"])
        deadline = time.monotonic() + 1.8
        while time.monotonic() < deadline:
            running_execution = service.get_execution_snapshot().to_dict()
            if running_execution["tick_count"] > 0 and running_execution["heartbeat_at"]:
                break
            time.sleep(0.1)
        self.assertGreater(running_execution["tick_count"], 0)
        self.assertTrue(running_execution["heartbeat_at"])

        stop_result = service.request_stop(close_positions=True, source="service-cli").to_dict()
        stopped_status = service.get_status().to_dict()
        stopped_execution = service.get_execution_snapshot().to_dict()

        self.assertTrue(stop_result["accepted"])
        self.assertEqual(stopped_status["lifecycle_phase"], "idle")
        self.assertEqual(stopped_status["active_engine_count"], 0)
        self.assertEqual(stopped_execution["state"], "idle")
        self.assertEqual(stopped_execution["active_engine_count"], 0)
        self.assertEqual(stopped_execution["last_action"], "stop")
        self.assertTrue(stopped_execution["session_id"])
        self.assertEqual(stopped_execution["progress_percent"], 100.0)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is not installed in this interpreter")
    def test_service_backtest_executor_runs_with_fake_wrapper(self):
        service = TradingBotService()
        service.enable_backtest_executor(wrapper_factory=_FakeBacktestWrapper)

        result = service.submit_backtest(
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["1h"],
                "logic": "AND",
                "symbol_source": "Futures",
                "capital": 1000.0,
                "start": "2025-01-01T00:00:00",
                "end": "2025-01-10T00:00:00",
                "indicators": [
                    {
                        "key": "rsi",
                        "params": {
                            "length": 14,
                            "buy_value": 30,
                            "sell_value": 70,
                        },
                    }
                ],
            },
            source="test-backtest",
        ).to_dict()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"], "running")

        deadline = time.monotonic() + 5.0
        snapshot = service.get_backtest_snapshot().to_dict()
        while time.monotonic() < deadline:
            snapshot = service.get_backtest_snapshot().to_dict()
            if snapshot["state"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        self.assertEqual(snapshot["state"], "completed")
        self.assertEqual(snapshot["error_count"], 0)
        self.assertEqual(snapshot["run_count"], 1)
        self.assertTrue(snapshot["session_id"])
        self.assertEqual(snapshot["symbols"], ["BTCUSDT"])
        self.assertEqual(snapshot["intervals"], ["1h"])
        self.assertTrue(snapshot["top_runs"])

        execution = service.get_execution_snapshot().to_dict()
        self.assertEqual(execution["executor_kind"], "service-backtest-executor")
        self.assertEqual(execution["workload_kind"], "backtest-run")
        self.assertEqual(execution["last_action"], "complete")

    def test_service_control_handler_dispatches_non_desktop_requests(self):
        service = TradingBotService()
        dispatched: list[dict] = []

        def _handler(request):
            dispatched.append(request.to_dict())
            return {"accepted": True, "message": "Forwarded to desktop GUI."}

        service.set_control_request_handler(_handler)
        result = service.request_start(requested_job_count=2, source="web-ui").to_dict()
        runtime = service.describe_runtime().to_dict()

        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0]["action"], "start")
        self.assertTrue(result["accepted"])
        self.assertIn("Forwarded to desktop GUI.", result["status_message"])
        self.assertEqual(runtime["control_plane"]["mode"], "delegated-dispatch")
        self.assertEqual(runtime["control_plane"]["owner"], "external-control-adapter")
        self.assertTrue(runtime["control_plane"]["start_supported"])

        service.request_start(requested_job_count=1, source="desktop-start")
        self.assertEqual(len(dispatched), 1)

    def test_service_runtime_descriptor_reflects_control_plane_metadata(self):
        service = TradingBotService()

        def _handler(_request):
            return {"accepted": True, "message": "Queued."}

        service.set_control_request_handler(
            _handler,
            mode="desktop-gui-dispatch",
            owner="desktop-gui",
            start_supported=True,
            stop_supported=True,
            notes=("Queued onto desktop runtime.",),
        )
        descriptor = service.describe_runtime().to_dict()

        self.assertEqual(descriptor["control_plane"]["mode"], "desktop-gui-dispatch")
        self.assertEqual(descriptor["control_plane"]["owner"], "desktop-gui")
        self.assertTrue(descriptor["control_plane"]["start_supported"])
        self.assertTrue(descriptor["control_plane"]["stop_supported"])
        self.assertIn("Queued onto desktop runtime.", descriptor["control_plane"]["notes"])

    def test_service_control_handler_can_reject_requests(self):
        service = TradingBotService()

        def _handler(_request):
            return {"accepted": False, "message": "Desktop control dispatch unavailable."}

        service.set_control_request_handler(_handler)
        result = service.request_stop(close_positions=True, source="web-ui").to_dict()
        status = service.get_status().to_dict()

        self.assertFalse(result["accepted"])
        self.assertIn("dispatch unavailable", result["status_message"].lower())
        self.assertEqual(status["lifecycle_phase"], "idle")
        self.assertEqual(status["requested_action"], "")

    def test_service_start_preserves_connector_warning_when_dispatch_rejects(self):
        service = TradingBotService()

        def _handler(_request):
            return {"accepted": False, "message": "Desktop control dispatch unavailable."}

        service.set_control_request_handler(_handler)
        service.set_exchange_connector_snapshot(
            {
                "rate_limit": {"active": True, "seconds_until_unban": 8.0},
                "last_error": {
                    "category": "rate_limited",
                    "message": "Too many requests.",
                    "retryable": True,
                },
            },
            source="unit-test",
        )

        result = service.request_start(requested_job_count=1, source="web-ui").to_dict()

        self.assertFalse(result["accepted"])
        self.assertIn("dispatch unavailable", result["status_message"].lower())
        self.assertIn("rate limited", result["status_message"].lower())

    def test_service_start_blocks_when_exchange_connector_has_error_health(self):
        service = TradingBotService()
        dispatched: list[dict] = []

        def _handler(request):
            dispatched.append(request.to_dict())
            return {"accepted": True, "message": "Should not dispatch."}

        service.set_control_request_handler(_handler)
        service.set_exchange_connector_snapshot(
            {
                "last_error": {
                    "category": "auth",
                    "message": "Invalid API key api_secret=leaked",
                    "retryable": False,
                },
            },
            source="unit-test",
        )

        result = service.request_start(requested_job_count=2, source="web-ui").to_dict()
        status = service.get_status().to_dict()
        dashboard = service.get_dashboard_snapshot(log_limit=5)

        self.assertFalse(result["accepted"])
        self.assertEqual([], dispatched)
        self.assertEqual("idle", status["lifecycle_phase"])
        self.assertEqual("", status["requested_action"])
        self.assertEqual("error", status["connector_health"])
        self.assertIn("start blocked", result["status_message"].lower())
        self.assertIn("auth_error", result["status_message"])
        self.assertIn("<redacted>", result["status_message"])
        self.assertNotIn("leaked", json.dumps(dashboard))
        self.assertTrue(any("Start blocked" in item["message"] for item in dashboard["logs"]))

    def test_service_live_start_blocks_when_operational_inputs_are_stale(self):
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        dispatched: list[dict] = []

        def _handler(request):
            dispatched.append(request.to_dict())
            return {"accepted": True, "message": "Should not dispatch."}

        service.set_control_request_handler(_handler)
        _mark_operational_inputs_stale(service)

        result = service.request_start(requested_job_count=2, source="web-ui").to_dict()
        status = service.get_status().to_dict()
        dashboard = service.get_dashboard_snapshot(log_limit=5)

        self.assertFalse(result["accepted"])
        self.assertEqual([], dispatched)
        self.assertEqual("idle", status["lifecycle_phase"])
        self.assertEqual("", status["requested_action"])
        self.assertIn("operational safety gate", result["status_message"])
        self.assertIn("critical snapshots are stale", result["status_message"])
        self.assertIn("exchange connector", result["status_message"])
        self.assertIn("account", result["status_message"])
        self.assertIn("portfolio", result["status_message"])
        self.assertTrue(any("operational safety gate" in item["message"] for item in dashboard["logs"]))

    def test_service_operational_preflight_allows_idle_live_start_without_execution_heartbeat(self):
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_execution_heartbeat_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        _mark_operational_inputs_fresh(service)

        preflight = service.get_operational_preflight()
        result = service.request_start(requested_job_count=1, source="web-ui").to_dict()

        self.assertEqual("ok", preflight["state"])
        self.assertTrue(preflight["live_mode"])
        self.assertTrue(preflight["start"]["allowed"])
        self.assertTrue(preflight["orders"]["allowed"])
        self.assertFalse(preflight["freshness"]["execution"]["stale"])
        self.assertNotIn("execution heartbeat", preflight["critical_stale"]["start"])
        self.assertNotIn("execution heartbeat", "\n".join(preflight["reasons"]))
        self.assertTrue(result["accepted"])
        self.assertNotIn("operational safety gate", result["status_message"].lower())

    def test_service_live_start_blocks_when_running_execution_heartbeat_is_stale(self):
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_execution_heartbeat_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        dispatched: list[dict] = []

        def _handler(request):
            dispatched.append(request.to_dict())
            return {"accepted": True, "message": "Should not dispatch."}

        service.set_control_request_handler(_handler)
        _mark_operational_inputs_fresh(service)
        _mark_running_execution_heartbeat_stale(service)

        preflight = service.get_operational_preflight()
        result = service.request_start(requested_job_count=1, source="web-ui").to_dict()
        status = service.get_status().to_dict()

        self.assertEqual("blocked", preflight["state"])
        self.assertFalse(preflight["start"]["allowed"])
        self.assertTrue(preflight["orders"]["allowed"])
        self.assertTrue(preflight["freshness"]["execution"]["stale"])
        self.assertIn("execution heartbeat", preflight["critical_stale"]["start"])
        self.assertNotIn("execution heartbeat", preflight["critical_stale"]["orders"])
        self.assertIn("execution heartbeat", "\n".join(preflight["start"]["reasons"]))
        self.assertFalse(result["accepted"])
        self.assertEqual([], dispatched)
        self.assertEqual("running", status["lifecycle_phase"])
        self.assertIn("critical snapshots are stale", result["status_message"])
        self.assertIn("execution heartbeat", result["status_message"])

    def test_service_operational_preflight_reports_live_gate_block_reasons(self):
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        _mark_operational_inputs_stale(service)

        operational = service.get_operational_snapshot()
        preflight = service.get_operational_preflight()
        rendered_reasons = "\n".join(preflight["reasons"])
        order_reasons = "\n".join(preflight["orders"]["reasons"])

        self.assertEqual(operational["preflight"]["state"], preflight["state"])
        self.assertEqual("ok", operational["health"])
        self.assertEqual("blocked", preflight["state"])
        self.assertTrue(preflight["live_mode"])
        self.assertFalse(preflight["start"]["allowed"])
        self.assertFalse(preflight["orders"]["allowed"])
        self.assertTrue(preflight["start"]["gate_enabled"])
        self.assertTrue(preflight["orders"]["gate_enabled"])
        self.assertIn("critical snapshots are stale", rendered_reasons)
        self.assertIn("exchange connector", rendered_reasons)
        self.assertIn("account", rendered_reasons)
        self.assertIn("portfolio", rendered_reasons)
        self.assertNotIn("execution heartbeat", order_reasons)
        self.assertTrue(preflight["freshness"]["exchange_connector"]["stale"])
        self.assertTrue(preflight["freshness"]["account"]["stale"])
        self.assertTrue(preflight["freshness"]["portfolio"]["stale"])

    def test_service_operational_preflight_matches_contract_sample_shape(self):
        sample_path = REPO_ROOT / "apps" / "service-api" / "contracts" / "operational-preflight.sample.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        _mark_operational_inputs_stale(service)

        preflight = service.get_operational_preflight()

        self.assertEqual(SERVICE_API_ROUTE_PATHS["operational_preflight"], "/api/v1/runtime/operational-preflight")
        self.assertEqual(set(sample), set(preflight))
        self.assertEqual(_shape(sample), _shape(preflight))
        self.assertEqual({"allowed", "state", "gate_enabled", "reasons"}, set(sample["start"]))
        self.assertEqual({"allowed", "state", "gate_enabled", "reasons"}, set(sample["orders"]))
        self.assertEqual(
            {"exchange_connector", "execution", "account", "portfolio"},
            set(sample["freshness"]),
        )
        self.assertEqual({"start", "orders"}, set(sample["critical_stale"]))
        self.assertEqual("blocked", sample["state"])
        self.assertFalse(sample["start"]["allowed"])
        self.assertFalse(sample["orders"]["allowed"])

    def test_service_demo_start_warns_but_allows_stale_operational_inputs(self):
        service = TradingBotService(
            config={
                "mode": "Demo/Testnet",
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        _mark_operational_inputs_stale(service)

        result = service.request_start(requested_job_count=1, source="web-ui").to_dict()
        status = service.get_status().to_dict()
        dashboard = service.get_dashboard_snapshot(log_limit=5)

        self.assertTrue(result["accepted"])
        self.assertEqual("starting", status["lifecycle_phase"])
        self.assertIn("demo/test mode start remains allowed", result["status_message"])
        self.assertTrue(any("demo/test mode start remains allowed" in item["message"] for item in dashboard["logs"]))

    def test_service_live_start_gate_can_be_explicitly_disabled(self):
        service = TradingBotService(
            config={
                "mode": "Live",
                "operational_live_start_gate_enabled": False,
                "operational_connector_snapshot_stale_seconds": 60,
                "operational_account_snapshot_stale_seconds": 60,
                "operational_portfolio_snapshot_stale_seconds": 60,
            }
        )
        _mark_operational_inputs_stale(service)

        result = service.request_start(requested_job_count=1, source="web-ui").to_dict()
        status = service.get_status().to_dict()
        dashboard = service.get_dashboard_snapshot(log_limit=5)

        self.assertTrue(result["accepted"])
        self.assertEqual("starting", status["lifecycle_phase"])
        self.assertIn("safety gate is disabled", result["status_message"])
        self.assertTrue(any("safety gate is disabled" in item["message"] for item in dashboard["logs"]))

    def test_service_start_warns_but_allows_rate_limited_exchange_connector(self):
        service = TradingBotService()
        service.enable_local_executor()
        service.set_exchange_connector_snapshot(
            {
                "rate_limit": {"active": True, "seconds_until_unban": 12.0},
                "last_error": {
                    "category": "rate_limited",
                    "message": "Too many requests.",
                    "retryable": True,
                },
            },
            source="unit-test",
        )

        try:
            result = service.request_start(requested_job_count=1, source="web-ui").to_dict()
            status = service.get_status().to_dict()
            dashboard = service.get_dashboard_snapshot(log_limit=5)

            self.assertTrue(result["accepted"])
            self.assertEqual("running", status["lifecycle_phase"])
            self.assertEqual(1, status["active_engine_count"])
            self.assertEqual("warning", status["connector_health"])
            self.assertIn("rate limited", result["status_message"].lower())
            self.assertTrue(any("rate limited" in item["message"].lower() for item in dashboard["logs"]))
        finally:
            service.request_stop(close_positions=False, source="test-cleanup")

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_background_service_api_host_serves_embedded_service_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        client = create_desktop_service_client(config={"mode": "Demo/Testnet"})
        self.assertIsInstance(client, EmbeddedDesktopServiceClient)
        host = ServiceApiBackgroundHost(
            service=client.service,
            host="127.0.0.1",
            port=port,
            api_token="token-123",
        )
        try:
            self.assertTrue(host.start(timeout_seconds=5.0))
            request = Request(
                f"http://127.0.0.1:{port}{SERVICE_API_ROUTE_PATHS['dashboard']}",
                headers={"Authorization": "Bearer token-123"},
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["status"]["mode"], "Demo/Testnet")
            self.assertEqual(payload["service_api"]["host_context"], "desktop-embedded")
            self.assertEqual(payload["service_api"]["host_owner"], "desktop-gui")
            self.assertEqual(payload["service_api"]["version"], SERVICE_API_VERSION)
            self.assertEqual(payload["service_api"]["api_base_path"], SERVICE_API_BASE_PATH)
            self.assertTrue(host.describe()["running"])
            self.assertEqual(host.describe()["host_context"], "desktop-embedded")
            self.assertEqual(host.describe()["api_base_path"], SERVICE_API_BASE_PATH)
        finally:
            self.assertTrue(host.stop(timeout_seconds=5.0))

    @unittest.skipUnless(
        FASTAPI_AVAILABLE and PANDAS_AVAILABLE,
        "FastAPI and pandas optional dependencies are not installed",
    )
    def test_background_service_api_backtest_routes_run_fake_workload(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        service = TradingBotService()
        service.enable_backtest_executor(wrapper_factory=_FakeBacktestWrapper)
        host = ServiceApiBackgroundHost(
            service=service,
            host="127.0.0.1",
            port=port,
            api_token="token-123",
        )
        try:
            self.assertTrue(host.start(timeout_seconds=5.0))
            payload = json.dumps(
                {
                    "request": {
                        "symbols": ["BTCUSDT"],
                        "intervals": ["1h"],
                        "logic": "AND",
                        "symbol_source": "Futures",
                        "capital": 1000.0,
                        "start": "2025-01-01T00:00:00",
                        "end": "2025-01-10T00:00:00",
                        "indicators": [
                            {
                                "key": "rsi",
                                "params": {
                                    "length": 14,
                                    "buy_value": 30,
                                    "sell_value": 70,
                                },
                            }
                        ],
                    },
                    "source": "api-smoke",
                }
            ).encode("utf-8")
            request = Request(
                f"http://127.0.0.1:{port}{SERVICE_API_ROUTE_PATHS['backtest_run']}",
                data=payload,
                headers={
                    "Authorization": "Bearer token-123",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(request, timeout=3) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertTrue(result["accepted"])
            self.assertEqual(result["state"], "running")

            snapshot = {}
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                request = Request(
                    f"http://127.0.0.1:{port}{SERVICE_API_ROUTE_PATHS['backtest']}",
                    headers={"Authorization": "Bearer token-123"},
                )
                with urlopen(request, timeout=3) as response:
                    snapshot = json.loads(response.read().decode("utf-8"))
                if snapshot.get("state") in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.05)

            self.assertEqual(snapshot.get("state"), "completed")
            self.assertEqual(snapshot.get("run_count"), 1)
            self.assertEqual(snapshot.get("error_count"), 0)
            self.assertEqual(snapshot.get("symbols"), ["BTCUSDT"])
            self.assertTrue(snapshot.get("top_runs"))
        finally:
            self.assertTrue(host.stop(timeout_seconds=5.0))


if __name__ == "__main__":
    unittest.main()
