import json
import math
import socket
import sys
import time
import unittest
import warnings
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

from app.desktop import EmbeddedDesktopServiceClient, create_desktop_service_client  # noqa: E402
from app.service.api import FASTAPI_AVAILABLE, ServiceApiBackgroundHost  # noqa: E402
from app.service.api_contract import SERVICE_API_BASE_PATH, SERVICE_API_ROUTE_PATHS, SERVICE_API_VERSION  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


def _start_background_host_for_test(host: ServiceApiBackgroundHost, *, timeout_seconds: float = 5.0) -> bool:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"websockets\.server\.WebSocketServerProtocol is deprecated",
            category=DeprecationWarning,
        )
        return host.start(timeout_seconds=timeout_seconds)


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


class ServiceBackgroundHostIntegrationTests(unittest.TestCase):
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
        self.assertTrue(snapshot["runs"])
        self.assertTrue(snapshot["top_runs"])
        self.assertEqual(snapshot["run_count"], len(snapshot["runs"]))

        execution = service.get_execution_snapshot().to_dict()
        self.assertEqual(execution["executor_kind"], "service-backtest-executor")
        self.assertEqual(execution["workload_kind"], "backtest-run")
        self.assertEqual(execution["last_action"], "complete")

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
            self.assertTrue(_start_background_host_for_test(host, timeout_seconds=5.0))
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
            self.assertTrue(_start_background_host_for_test(host, timeout_seconds=5.0))
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
            self.assertTrue(snapshot.get("runs"))
            self.assertTrue(snapshot.get("top_runs"))
        finally:
            self.assertTrue(host.stop(timeout_seconds=5.0))
