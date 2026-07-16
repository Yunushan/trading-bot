# ruff: noqa: E402

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.transport import ws_runtime


class _Harness:
    _use_live_futures_data_for_indicators = ws_runtime._use_live_futures_data_for_indicators
    _live_futures_symbol_set = ws_runtime._live_futures_symbol_set
    _symbol_available_on_live_futures = ws_runtime._symbol_available_on_live_futures
    _ensure_ws_manager = ws_runtime._ensure_ws_manager
    _ws_kline_handler = ws_runtime._ws_kline_handler
    _ensure_ws_stream = ws_runtime._ensure_ws_stream
    _ws_latest_candle = ws_runtime._ws_latest_candle

    def __init__(self, *, mode="Live", enabled=True):
        self.mode = mode
        self.api_key = "key"
        self.api_secret = "secret"
        self._ws_enabled = enabled
        self._ws_twm = None
        self._ws_streams = {}
        self._ws_kline_cache = {}
        self._ws_lock = threading.RLock()
        self._live_fut_symbols_cache = set()
        self._live_fut_symbols_ts = 0.0
        self.logs = []

    def _futures_base_live(self):
        return "https://fapi.binance.com"

    def _log(self, message, *, lvl):
        self.logs.append((message, lvl))


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _Manager:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.subscriptions = []
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def start_kline_futures_socket(self, *, callback, symbol, interval):
        self.subscriptions.append((callback, symbol, interval))
        return f"{symbol}@{interval}"


class BinanceWebSocketRuntimeTests(unittest.TestCase):
    def setUp(self):
        _Manager.instances = []

    def test_live_symbol_cache_reads_exchange_once_and_reuses_fresh_result(self):
        harness = _Harness()
        response = _Response(
            {
                "symbols": [
                    {"symbol": "BTCUSDT", "status": "TRADING"},
                    {"symbol": "ETHUSDT", "status": "BREAK"},
                ]
            }
        )
        with patch.object(ws_runtime.time, "time", side_effect=[1_000.0, 1_100.0]), patch.object(
            ws_runtime.requests, "get", return_value=response
        ) as get:
            first = ws_runtime._live_futures_symbol_set(harness)
            second = ws_runtime._live_futures_symbol_set(harness)

        self.assertEqual(first, {"BTCUSDT"})
        self.assertEqual(second, {"BTCUSDT"})
        get.assert_called_once_with("https://fapi.binance.com/v1/exchangeInfo", timeout=10)

    def test_live_symbol_lookup_uses_cached_data_when_exchange_request_fails(self):
        harness = _Harness(mode="Testnet")
        harness._live_fut_symbols_cache = {"ETHUSDT"}
        with patch.object(ws_runtime.requests, "get", side_effect=RuntimeError("offline")):
            self.assertTrue(ws_runtime._symbol_available_on_live_futures(harness, "ethusdt"))
            self.assertFalse(ws_runtime._symbol_available_on_live_futures(harness, "BTCUSDT"))

    def test_testnet_symbol_lookup_allows_unknown_symbol_only_when_live_catalog_is_unavailable(self):
        harness = _Harness(mode="Demo/Testnet")
        with patch.object(ws_runtime.requests, "get", side_effect=RuntimeError("offline")):
            self.assertTrue(ws_runtime._symbol_available_on_live_futures(harness, "NEWUSDT"))
        self.assertFalse(ws_runtime._symbol_available_on_live_futures(harness, ""))

    def test_ws_manager_uses_live_data_override_for_testnet_indicators(self):
        harness = _Harness(mode="Testnet")
        with patch.object(ws_runtime, "_TWM", _Manager), patch.object(
            _Harness, "_use_live_futures_data_for_indicators", return_value=True
        ):
            ws_runtime._ensure_ws_manager(harness)

        manager = _Manager.instances[0]
        self.assertTrue(manager.started)
        self.assertFalse(manager.kwargs["testnet"])
        self.assertEqual(manager.kwargs["api_key"], "key")

    def test_ws_manager_failure_disables_fast_indicators(self):
        harness = _Harness()

        class _BrokenManager:
            def __init__(self, **_kwargs):
                raise RuntimeError("manager unavailable")

        with patch.object(ws_runtime, "_TWM", _BrokenManager):
            ws_runtime._ensure_ws_manager(harness)

        self.assertIsNone(harness._ws_twm)
        self.assertFalse(harness._ws_enabled)
        self.assertEqual(harness.logs[-1][1], "warn")
        self.assertIn("disabling fast indicators", harness.logs[-1][0])

    def test_kline_handler_caches_valid_message_and_discards_invalid_payloads(self):
        harness = _Harness()
        ws_runtime._ws_kline_handler(
            harness,
            {
                "E": 123,
                "k": {
                    "s": "btcusdt",
                    "i": "1m",
                    "t": 100,
                    "o": "1",
                    "h": "2",
                    "l": "0.5",
                    "c": "1.5",
                    "v": "42",
                    "x": True,
                },
            },
        )
        ws_runtime._ws_kline_handler(harness, {"k": {"s": "", "i": "1m"}})
        ws_runtime._ws_kline_handler(harness, "not-a-message")

        self.assertEqual(
            ws_runtime._ws_latest_candle(harness, "BTCUSDT", "1m"),
            {
                "open_time": 100,
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 42.0,
                "closed": True,
                "event_time": 123,
            },
        )

    def test_stream_subscription_is_idempotent_and_logs_subscription_failure(self):
        harness = _Harness()
        with patch.object(ws_runtime, "_TWM", _Manager):
            ws_runtime._ensure_ws_stream(harness, "btcusdt", "5m")
            ws_runtime._ensure_ws_stream(harness, "BTCUSDT", "5m")

        manager = _Manager.instances[0]
        self.assertEqual(len(manager.subscriptions), 1)
        self.assertEqual(harness._ws_streams, {("BTCUSDT", "5m"): "BTCUSDT@5m"})

        class _BrokenSubscriptionManager:
            def start_kline_futures_socket(self, **_kwargs):
                raise RuntimeError("subscribe failed")

        failed = _Harness()
        failed._ws_twm = _BrokenSubscriptionManager()
        with patch.object(ws_runtime, "_TWM", _Manager):
            ws_runtime._ensure_ws_stream(failed, "ETHUSDT", "1m")
        self.assertEqual(failed._ws_streams, {})
        self.assertIn("continuing without WS", failed.logs[-1][0])

    def test_binder_attaches_all_runtime_helpers(self):
        class _Wrapper:
            pass

        ws_runtime.bind_binance_ws_runtime(_Wrapper)
        self.assertIs(_Wrapper._ws_kline_handler, ws_runtime._ws_kline_handler)
        self.assertIs(_Wrapper._ensure_ws_stream, ws_runtime._ensure_ws_stream)
        self.assertIs(_Wrapper._ws_latest_candle, ws_runtime._ws_latest_candle)
