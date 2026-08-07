from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch

import requests

from app.integrations.exchanges.binance.runtime.operational_runtime import (
    _handle_network_offline,
    _handle_network_recovered,
    close_all_spot_positions,
    get_last_price,
    trigger_emergency_close_all,
)


class _ImmediateThread:
    def __init__(self, target=None, **_kwargs) -> None:
        self._target = target
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        self._alive = True
        try:
            if self._target is not None:
                self._target()
        finally:
            self._alive = False


class _FailingThread(_ImmediateThread):
    def start(self) -> None:
        raise RuntimeError("thread start failed")


class _SpotWrapper:
    close_all_spot_positions = close_all_spot_positions

    def __init__(self) -> None:
        self.account_type = "SPOT"
        self.balances = [{"asset": "BTC", "free": "0.1"}]
        self.symbol_info = {"status": "TRADING", "quoteAsset": "USDT"}
        self.filters = {"minNotional": 5.0, "stepSize": 0.01}
        self.price = 100.0
        self.trade = {"ok": True, "computed": {"qty": 0.1}}
        self.orders: list[tuple[str, str, float]] = []
        self._last_price_cache: dict[str, tuple[float, float]] = {}
        self.client = Mock()
        self.logs: list[tuple[str, str]] = []

    def _log(self, message: str, lvl: str = "info") -> None:
        self.logs.append((lvl, message))

    def list_spot_non_usdt_balances(self):
        return list(self.balances)

    def get_symbol_info_spot(self, _symbol: str):
        if isinstance(self.symbol_info, Exception):
            raise self.symbol_info
        return dict(self.symbol_info)

    def get_spot_symbol_filters(self, _symbol: str):
        return dict(self.filters)

    def get_last_price(self, _symbol: str) -> float:
        return self.price

    def _floor_to_step(self, qty: float, step: float) -> float:
        return int(qty / step) * step

    def place_spot_market_order(self, symbol: str, side: str, qty: float):
        self.orders.append((symbol, side, qty))
        return dict(self.trade)

    def _spot_base(self) -> str:
        return "https://api.binance.test/api"


class _EmergencyWrapper:
    trigger_emergency_close_all = trigger_emergency_close_all
    _handle_network_offline = _handle_network_offline
    _handle_network_recovered = _handle_network_recovered

    def __init__(self, *, account_type: str = "SPOT") -> None:
        self.account_type = account_type
        self._emergency_closer_lock = threading.RLock()
        self._emergency_closer_thread = None
        self._emergency_close_requested = False
        self._emergency_close_info: dict = {}
        self._network_emergency_dispatched = False
        self._network_offline = False
        self._network_offline_hits = 0
        self._network_offline_since = 0.0
        self._last_network_error_log = 0.0
        self.logs: list[tuple[str, str]] = []
        self.close_results = [{"ok": True}]
        self.trigger_error: Exception | None = None
        self.trigger_calls: list[dict] = []

    def _log(self, message: str, lvl: str = "info") -> None:
        self.logs.append((lvl, message))

    def close_all_spot_positions(self):
        return list(self.close_results)


class BinanceOperationalRuntimeTests(unittest.TestCase):
    def test_spot_close_executes_valid_order(self):
        wrapper = _SpotWrapper()

        result = close_all_spot_positions(wrapper)

        self.assertEqual([("BTCUSDT", "SELL", 0.1)], wrapper.orders)
        self.assertTrue(result[0]["ok"])
        self.assertEqual(0.1, result[0]["qty"])

    def test_spot_close_marks_metadata_lookup_failure_for_retry(self):
        wrapper = _SpotWrapper()
        wrapper.symbol_info = RuntimeError("token=unit-secret")

        result = close_all_spot_positions(wrapper)

        self.assertFalse(result[0]["ok"])
        self.assertNotIn("unit-secret", result[0]["error"])
        self.assertIn("<redacted>", result[0]["error"])
        self.assertEqual([], wrapper.orders)

    def test_spot_close_only_skips_explicitly_non_tradable_symbol(self):
        wrapper = _SpotWrapper()
        wrapper.symbol_info = {"status": "BREAK", "quoteAsset": "USDT"}

        result = close_all_spot_positions(wrapper)

        self.assertTrue(result[0]["ok"])
        self.assertTrue(result[0]["skipped"])
        self.assertEqual([], wrapper.orders)

    def test_spot_close_rejects_malformed_and_non_finite_balances(self):
        wrapper = _SpotWrapper()
        wrapper.balances = [
            {"asset": "BTC", "free": "not-a-number"},
            {"asset": "ETH", "free": "nan"},
            {"asset": "", "free": "1"},
            {"asset": "XRP", "free": "0"},
        ]

        result = close_all_spot_positions(wrapper)

        self.assertEqual(3, len(result))
        self.assertTrue(all(not item["ok"] for item in result))
        self.assertTrue(all(item["qty"] == 0.0 for item in result[:2]))
        self.assertEqual([], wrapper.orders)

    def test_spot_close_handles_price_filters_dust_and_order_failure(self):
        cases = (
            (float("nan"), {"minNotional": 5.0, "stepSize": 0.01}, None, True),
            (100.0, {"minNotional": float("nan"), "stepSize": 0.01}, None, False),
            (100.0, {"minNotional": 20.0, "stepSize": 0.01}, None, True),
            (100.0, {"minNotional": 5.0, "stepSize": 0.01}, {"ok": False, "error": "denied"}, False),
        )
        for price, filters, trade, skipped in cases:
            with self.subTest(price=price, filters=filters, trade=trade):
                wrapper = _SpotWrapper()
                wrapper.price = price
                wrapper.filters = filters
                wrapper.get_last_price = lambda _symbol, value=price: value
                if trade is not None:
                    wrapper.trade = trade

                result = close_all_spot_positions(wrapper)

                if skipped:
                    self.assertTrue(result[0].get("skipped"))
                else:
                    self.assertFalse(result[0]["ok"])

    def test_last_price_uses_only_fresh_positive_finite_cache_entries(self):
        wrapper = _SpotWrapper()
        wrapper.account_type = "FUTURES"
        wrapper._futures_call = Mock(return_value={"price": "101.25"})
        with patch(
            "app.integrations.exchanges.binance.runtime.operational_runtime.time.time",
            return_value=100.0,
        ):
            wrapper._last_price_cache["BTCUSDT"] = (99.0, 98.0)
            self.assertEqual(99.0, get_last_price(wrapper, "btcusdt", max_age=5.0))
            wrapper._last_price_cache["BTCUSDT"] = (float("nan"), 99.0)
            self.assertEqual(101.25, get_last_price(wrapper, "BTCUSDT", max_age=5.0))

        self.assertEqual(1, wrapper._futures_call.call_count)
        self.assertEqual(0.0, get_last_price(wrapper, ""))

    def test_last_price_spot_http_fallback_rejects_non_finite_sdk_value(self):
        wrapper = _SpotWrapper()
        wrapper.client.get_symbol_ticker.return_value = {"price": "nan"}
        response = Mock(status_code=200)
        response.json.return_value = {"price": "88.5"}

        with patch(
            "app.integrations.exchanges.binance.runtime.operational_runtime.requests.get",
            return_value=response,
        ) as request_get:
            price = get_last_price(wrapper, "ETHUSDT")

        self.assertEqual(88.5, price)
        request_get.assert_called_once()
        self.assertEqual(88.5, wrapper._last_price_cache["ETHUSDT"][0])

    def test_emergency_close_redacts_logs_and_completes(self):
        wrapper = _EmergencyWrapper()
        with patch(
            "app.integrations.exchanges.binance.runtime.operational_runtime.threading.Thread",
            _ImmediateThread,
        ):
            accepted = trigger_emergency_close_all(
                wrapper,
                reason="token=unit-secret",
                source="api_key=source-secret",
                max_attempts=1,
                initial_delay=0.0,
            )

        self.assertTrue(accepted)
        self.assertTrue(wrapper._emergency_close_info["success"])
        rendered = "\n".join(message for _level, message in wrapper.logs)
        self.assertNotIn("unit-secret", rendered)
        self.assertNotIn("source-secret", rendered)
        self.assertIn("<redacted>", rendered)

    def test_emergency_close_thread_start_failure_resets_state(self):
        wrapper = _EmergencyWrapper()
        with patch(
            "app.integrations.exchanges.binance.runtime.operational_runtime.threading.Thread",
            _FailingThread,
        ):
            with self.assertRaisesRegex(RuntimeError, "thread start failed"):
                trigger_emergency_close_all(wrapper, max_attempts=1)

        self.assertIsNone(wrapper._emergency_closer_thread)
        self.assertFalse(wrapper._emergency_close_requested)

    def test_emergency_close_retries_partial_failure(self):
        wrapper = _EmergencyWrapper()
        results = iter(([{"ok": False}], [{"ok": True}]))
        wrapper.close_all_spot_positions = lambda: next(results)
        with (
            patch(
                "app.integrations.exchanges.binance.runtime.operational_runtime.threading.Thread",
                _ImmediateThread,
            ),
            patch("app.integrations.exchanges.binance.runtime.operational_runtime.time.sleep"),
        ):
            accepted = trigger_emergency_close_all(wrapper, max_attempts=2, initial_delay=0.0)

        self.assertTrue(accepted)
        self.assertTrue(wrapper._emergency_close_info["success"])
        self.assertTrue(any("partial failures" in message for _level, message in wrapper.logs))

    def test_network_offline_dispatch_retries_after_trigger_exception(self):
        wrapper = _EmergencyWrapper()
        calls = []

        def trigger(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise requests.ConnectionError("offline")
            wrapper._emergency_close_requested = True
            return True

        wrapper.trigger_emergency_close_all = trigger
        with patch(
            "app.integrations.exchanges.binance.runtime.operational_runtime.time.time",
            side_effect=(100.0, 101.0, 102.0, 103.0, 104.0),
        ):
            for _ in range(4):
                _handle_network_offline(wrapper, "placing order", requests.ConnectionError("offline"))
            self.assertFalse(wrapper._network_emergency_dispatched)
            _handle_network_offline(wrapper, "placing order", requests.ConnectionError("offline"))

        self.assertEqual(2, len(calls))
        self.assertTrue(wrapper._network_emergency_dispatched)

    def test_network_recovery_clears_state(self):
        wrapper = _EmergencyWrapper()
        wrapper._network_offline = True
        wrapper._network_offline_since = 10.0
        wrapper._network_offline_hits = 4
        wrapper._network_emergency_dispatched = True

        _handle_network_recovered(wrapper)

        self.assertFalse(wrapper._network_offline)
        self.assertEqual(0.0, wrapper._network_offline_since)
        self.assertEqual(0, wrapper._network_offline_hits)
        self.assertFalse(wrapper._network_emergency_dispatched)
        self.assertIn(("info", "Network connectivity restored."), wrapper.logs)


if __name__ == "__main__":
    unittest.main()
