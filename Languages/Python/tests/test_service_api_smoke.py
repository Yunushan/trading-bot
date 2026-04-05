import json
import math
import socket
import sys
import time
import unittest
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
from app.service.auth import auth_required, validate_bearer_token  # noqa: E402
from app.service.api_contract import (  # noqa: E402
    SERVICE_API_BASE_PATH,
    SERVICE_API_LEGACY_BASE_PATH,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_LEGACY_ROUTE_PATHS,
    SERVICE_API_STREAM_DASHBOARD_PATH,
    SERVICE_API_VERSION,
)
from app.service.api import FASTAPI_AVAILABLE, ServiceApiBackgroundHost, create_service_api_app  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


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
            "logs",
            "execution",
            "backtest",
            "runtime_state",
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

    def test_desktop_service_client_can_be_forced_to_remote_mode(self):
        client = create_desktop_service_client(
            client_mode="remote",
            base_url="http://127.0.0.1:9000",
        )
        self.assertIsInstance(client, RemoteDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "remote")
        self.assertEqual(descriptor.get("base_url"), "http://127.0.0.1:9000")

    def test_service_api_auth_helpers(self):
        self.assertFalse(auth_required(""))
        self.assertTrue(validate_bearer_token(None, ""))
        self.assertTrue(validate_bearer_token("Bearer token-123", "token-123"))
        self.assertFalse(validate_bearer_token("Bearer wrong", "token-123"))

    def test_service_config_patch_round_trip(self):
        service = TradingBotService()
        initial_config = service.get_config_payload().to_dict()
        self.assertEqual(initial_config["mode"], "Live")

        payload = service.update_config(
            {
                "mode": "Demo/Testnet",
                "symbols": ["ETHUSDT", "BTCUSDT"],
                "intervals": ["5m", "15m"],
                "leverage": 10,
                "position_pct": 4.5,
            }
        ).to_dict()
        self.assertEqual(payload["mode"], "Demo/Testnet")
        self.assertEqual(payload["symbols"], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual(payload["intervals"], ["5m", "15m"])
        self.assertEqual(payload["leverage"], 10)
        self.assertEqual(payload["position_pct"], 4.5)

        summary = service.get_config_summary().to_dict()
        self.assertEqual(summary["symbol_count"], 2)
        self.assertEqual(summary["interval_count"], 2)

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
        self.assertIsInstance(snapshot["logs"], list)
        self.assertIn("control_plane", snapshot["runtime"])
        self.assertEqual(snapshot["runtime"]["control_plane"]["mode"], "intent-only")
        self.assertEqual(snapshot["execution"]["executor_kind"], "unbound")
        self.assertEqual(snapshot["execution"]["workload_kind"], "unbound")
        self.assertEqual(snapshot["backtest"]["state"], "idle")
        self.assertEqual(snapshot["backtest"]["run_count"], 0)

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
