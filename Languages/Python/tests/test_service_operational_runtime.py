import json
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.jsonl_rotation import jsonl_backup_path  # noqa: E402
from app.service.runners import bot_runtime_state as bot_runtime_state_module  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


class ServiceOperationalRuntimeTests(unittest.TestCase):
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
        self.assertEqual(snapshot["runtime"]["control_plane"]["execution_scope"], "intent-only")
        self.assertFalse(snapshot["runtime"]["control_plane"]["trading_execution_supported"])
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
            self.assertTrue(any("incident log write failed" in item for item in operational["attention"]))
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
