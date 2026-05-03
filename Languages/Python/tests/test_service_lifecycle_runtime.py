import json
import sys
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api_contract import SERVICE_API_ROUTE_PATHS  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402

REPO_ROOT = PYTHON_ROOT.parents[1]


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


def _control_plane_payload(service: TradingBotService) -> dict[str, object]:
    payload = service.describe_runtime().to_dict()["control_plane"]
    if not isinstance(payload, dict):
        raise AssertionError("runtime control_plane payload must serialize as a dict")
    return payload


class ServiceLifecycleRuntimeTests(unittest.TestCase):
    def test_local_service_executor_start_stop_updates_runtime(self):
        service = TradingBotService()
        service.enable_local_executor()

        start_result = service.request_start(requested_job_count=3, source="service-cli").to_dict()
        running_status = service.get_status().to_dict()
        runtime = service.describe_runtime().to_dict()
        running_execution = service.get_execution_snapshot().to_dict()

        self.assertTrue(start_result["accepted"])
        self.assertEqual(runtime["control_plane"]["mode"], "local-service-executor")
        self.assertEqual(runtime["control_plane"]["execution_scope"], "service-lifecycle-heartbeat")
        self.assertFalse(runtime["control_plane"]["trading_execution_supported"])
        self.assertIn("lifecycle heartbeat", start_result["status_message"])
        self.assertIn("no trading engines were launched", start_result["status_message"])
        self.assertNotIn("engine(s)", start_result["status_message"])
        self.assertEqual(running_status["lifecycle_phase"], "running")
        self.assertEqual(running_status["active_engine_count"], 3)
        self.assertEqual(running_execution["state"], "running")
        self.assertEqual(running_execution["workload_kind"], "service-lifecycle-heartbeat")
        self.assertEqual(running_execution["active_engine_count"], 3)
        self.assertIn("no trading engines", running_execution["last_message"])
        self.assertTrue(any("does not run trading strategies" in note for note in running_execution["notes"]))
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
        self.assertEqual(stopped_execution["workload_kind"], "service-lifecycle-heartbeat")
        self.assertTrue(stopped_execution["session_id"])
        self.assertEqual(stopped_execution["progress_percent"], 100.0)

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

    def test_service_control_plane_descriptor_contract_for_runtime_modes(self):
        service = TradingBotService()
        descriptor_keys = (
            "mode",
            "owner",
            "start_supported",
            "stop_supported",
            "execution_scope",
            "trading_execution_supported",
        )

        control_plane = _control_plane_payload(service)
        self.assertEqual(
            {
                "mode": "intent-only",
                "owner": "service-runtime",
                "start_supported": False,
                "stop_supported": False,
                "execution_scope": "intent-only",
                "trading_execution_supported": False,
            },
            {key: control_plane[key] for key in descriptor_keys},
        )
        self.assertIn(
            "Control requests are recorded as service intent until an execution adapter is attached.",
            control_plane["notes"],
        )

        service.enable_local_executor()
        control_plane = _control_plane_payload(service)
        self.assertEqual(
            {
                "mode": "local-service-executor",
                "owner": "service-process",
                "start_supported": True,
                "stop_supported": True,
                "execution_scope": "service-lifecycle-heartbeat",
                "trading_execution_supported": False,
            },
            {key: control_plane[key] for key in descriptor_keys},
        )
        self.assertIn("This adapter only maintains a service lifecycle heartbeat.", control_plane["notes"])
        self.assertIn(
            "It does not run trading strategies, market-data loops, or exchange order execution.",
            control_plane["notes"],
        )

        def _handler(_request):
            return {"accepted": True, "message": "Queued."}

        service.set_control_request_handler(_handler)
        control_plane = _control_plane_payload(service)
        execution = service.get_execution_snapshot().to_dict()
        self.assertEqual(
            {
                "mode": "delegated-dispatch",
                "owner": "external-control-adapter",
                "start_supported": True,
                "stop_supported": True,
                "execution_scope": "delegated-runtime",
                "trading_execution_supported": False,
            },
            {key: control_plane[key] for key in descriptor_keys},
        )
        self.assertIn("Control requests are forwarded to an external execution adapter.", control_plane["notes"])
        self.assertEqual(execution["workload_kind"], "delegated-runtime")

        service.set_control_request_handler(
            _handler,
            mode="desktop-gui-dispatch",
            owner="desktop-gui",
            start_supported=True,
            stop_supported=True,
            execution_scope="desktop-trading-runtime",
            trading_execution_supported=True,
            notes=("Queued onto desktop runtime.",),
        )
        control_plane = _control_plane_payload(service)
        execution = service.get_execution_snapshot().to_dict()
        self.assertEqual(
            {
                "mode": "desktop-gui-dispatch",
                "owner": "desktop-gui",
                "start_supported": True,
                "stop_supported": True,
                "execution_scope": "desktop-trading-runtime",
                "trading_execution_supported": True,
            },
            {key: control_plane[key] for key in descriptor_keys},
        )
        self.assertIn("Queued onto desktop runtime.", control_plane["notes"])
        self.assertEqual(execution["workload_kind"], "desktop-trading-runtime")

        service.set_control_request_handler(None)
        control_plane = _control_plane_payload(service)
        self.assertEqual(
            {
                "mode": "intent-only",
                "owner": "service-runtime",
                "start_supported": False,
                "stop_supported": False,
                "execution_scope": "intent-only",
                "trading_execution_supported": False,
            },
            {key: control_plane[key] for key in descriptor_keys},
        )
        self.assertIn(
            "Control requests are recorded as service intent until an execution adapter is attached.",
            control_plane["notes"],
        )

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
            execution_scope="desktop-trading-runtime",
            trading_execution_supported=True,
            notes=("Queued onto desktop runtime.",),
        )
        descriptor = service.describe_runtime().to_dict()

        self.assertEqual(descriptor["control_plane"]["mode"], "desktop-gui-dispatch")
        self.assertEqual(descriptor["control_plane"]["owner"], "desktop-gui")
        self.assertTrue(descriptor["control_plane"]["start_supported"])
        self.assertTrue(descriptor["control_plane"]["stop_supported"])
        self.assertEqual(descriptor["control_plane"]["execution_scope"], "desktop-trading-runtime")
        self.assertTrue(descriptor["control_plane"]["trading_execution_supported"])
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

    def test_service_runtime_matches_contract_sample_shape(self):
        sample_path = REPO_ROOT / "apps" / "service-api" / "contracts" / "runtime.sample.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        service = TradingBotService()
        service.enable_local_executor()

        runtime = service.describe_runtime().to_dict()

        self.assertEqual(SERVICE_API_ROUTE_PATHS["runtime"], "/api/v1/runtime")
        self.assertEqual(set(sample), set(runtime))
        self.assertEqual(_shape(sample), _shape(runtime))
        self.assertEqual(set(sample["capabilities"]), set(runtime["capabilities"]))
        self.assertEqual(sample["capabilities"], runtime["capabilities"])
        self.assertEqual(
            {
                "mode",
                "owner",
                "start_supported",
                "stop_supported",
                "execution_scope",
                "trading_execution_supported",
                "notes",
            },
            set(sample["control_plane"]),
        )
        self.assertEqual(sample["control_plane"], runtime["control_plane"])
        self.assertEqual("local-service-executor", sample["control_plane"]["mode"])
        self.assertEqual("service-lifecycle-heartbeat", sample["control_plane"]["execution_scope"])
        self.assertFalse(sample["control_plane"]["trading_execution_supported"])
        self.assertIn(
            "This adapter only maintains a service lifecycle heartbeat.",
            sample["control_plane"]["notes"],
        )

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
