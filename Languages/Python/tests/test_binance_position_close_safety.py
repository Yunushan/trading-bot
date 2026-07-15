import importlib.util
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

MODULE_PATH = (
    PYTHON_ROOT
    / "app"
    / "integrations"
    / "exchanges"
    / "binance"
    / "positions"
    / "futures_position_close_runtime.py"
)
spec = importlib.util.spec_from_file_location(
    "app.integrations.exchanges.binance.positions.futures_position_close_runtime_under_test",
    MODULE_PATH,
)
position_close_runtime = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(position_close_runtime)
cancel_all_open_futures_orders = position_close_runtime.cancel_all_open_futures_orders
close_futures_leg_exact = position_close_runtime.close_futures_leg_exact
close_futures_position = position_close_runtime.close_futures_position
close_all_futures_positions = position_close_runtime.close_all_futures_positions

FORMATTER_MODULE_PATH = MODULE_PATH.with_name("futures_positions_cache_runtime.py")
formatter_spec = importlib.util.spec_from_file_location("binance_position_cache_runtime", FORMATTER_MODULE_PATH)
formatter_runtime = importlib.util.module_from_spec(formatter_spec)
assert formatter_spec is not None and formatter_spec.loader is not None
formatter_spec.loader.exec_module(formatter_runtime)
format_quantity_for_order = formatter_runtime._format_quantity_for_order
get_cached_futures_positions = formatter_runtime._get_cached_futures_positions
store_futures_positions_cache = formatter_runtime._store_futures_positions_cache
invalidate_futures_positions_cache = formatter_runtime._invalidate_futures_positions_cache


class _CancelClient:
    def __init__(self, *, orders=None, order_error=None, fail_symbol=None):
        self.orders = list(orders or [])
        self.order_error = order_error
        self.fail_symbol = fail_symbol
        self.cancel_calls = []

    def futures_get_open_orders(self):
        if self.order_error is not None:
            raise self.order_error
        return list(self.orders)

    def futures_cancel_all_open_orders(self, *, symbol):
        self.cancel_calls.append(symbol)
        if symbol == self.fail_symbol:
            raise RuntimeError("cancel rejected")
        return {"code": 200}


class _CancelWrapper:
    def __init__(self, client, *, positions=None, position_error=None):
        self.client = client
        self.positions = list(positions or [])
        self.position_error = position_error
        self.position_calls = 0

    def list_open_futures_positions(self, *, max_age, force_refresh):
        self.position_calls += 1
        self.asserted_args = (max_age, force_refresh)
        if self.position_error is not None:
            raise self.position_error
        return list(self.positions)


class _ExactCloseWrapper:
    def __init__(
        self,
        *,
        positions=None,
        dual=False,
        fail_orders=False,
        step="0.005",
        clear_after_orders=None,
    ):
        self.positions = list(positions or [])
        self._futures_dual_side = bool(dual)
        self.fail_orders = fail_orders
        self.step = step
        self.orders = []
        self.invalidations = 0
        self.clear_after_orders = clear_after_orders
        self.clear_raw_after_order = False

    def get_futures_dual_side(self):
        return self._futures_dual_side

    def get_futures_symbol_filters(self, _symbol):
        return {"stepSize": self.step}

    def list_open_futures_positions(self, *, max_age, force_refresh):
        self.snapshot_args = (max_age, force_refresh)
        if self.clear_after_orders is not None and len(self.orders) >= self.clear_after_orders:
            return []
        return list(self.positions)

    def _format_quantity_for_order(self, value, step):
        return format_quantity_for_order(value, step)

    def _futures_create_order_with_fallback(self, params):
        self.orders.append(dict(params))
        if self.fail_orders:
            raise RuntimeError("order rejected")
        if self.clear_raw_after_order and hasattr(self, "client"):
            self.client.rows = []
        return {"orderId": len(self.orders), "avgPrice": "0"}, "primary"

    def _summarize_futures_order_fills(self, _symbol, _order_id):
        return {"avg_price": 100.0, "executed_qty": 0.125}

    def _invalidate_futures_positions_cache(self):
        self.invalidations += 1


class _RawPositionClient:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def futures_position_information(self, *, symbol):
        return [row for row in self.rows if str(row.get("symbol") or "").upper() == symbol]


class _LogWrapper:
    def __init__(self):
        self.logs = []

    def _log(self, message, lvl="info"):
        self.logs.append((lvl, message))


class _PositionCacheWrapper:
    def __init__(self):
        self._positions_cache_lock = threading.RLock()
        self._positions_cache = None
        self._positions_cache_ts = 0.0
        self.account_invalidations = 0

    def _invalidate_futures_account_cache(self):
        self.account_invalidations += 1


class BinancePositionCloseSafetyTests(unittest.TestCase):
    def test_close_all_delegates_to_canonical_runtime(self):
        module_name = "app.integrations.exchanges.binance.positions.close_all_runtime"
        canonical = types.ModuleType(module_name)
        canonical.close_all_futures_positions = lambda _wrapper: [{"ok": True, "source": "canonical"}]

        with mock.patch.dict(sys.modules, {module_name: canonical}):
            result = close_all_futures_positions(object())

        self.assertEqual([{"ok": True, "source": "canonical"}], result)

    def test_close_all_reports_canonical_runtime_failure_without_legacy_trading_fallback(self):
        module_name = "app.integrations.exchanges.binance.positions.close_all_runtime"
        canonical = types.ModuleType(module_name)

        def fail_close(_wrapper):
            raise RuntimeError("reconciliation unavailable")

        canonical.close_all_futures_positions = fail_close
        wrapper = _LogWrapper()

        with mock.patch.dict(sys.modules, {module_name: canonical}):
            result = close_all_futures_positions(wrapper)

        self.assertFalse(result[0]["ok"])
        self.assertIn("reconciliation unavailable", result[0]["error"])
        self.assertTrue(any("Canonical close-all runtime failed" in message for _level, message in wrapper.logs))

    def test_quantity_formatter_floors_to_actual_non_power_of_ten_step(self):
        self.assertEqual("1.23", format_quantity_for_order(1.234, 0.005))
        self.assertEqual("0", format_quantity_for_order(0.004, 0.005))

    def test_position_cache_stores_and_returns_independent_snapshots(self):
        wrapper = _PositionCacheWrapper()
        source = [{"symbol": "BTCUSDT", "positionAmt": 1.0}]

        store_futures_positions_cache(wrapper, source)
        source[0]["positionAmt"] = 9.0
        cached = get_cached_futures_positions(wrapper, 10.0)

        self.assertEqual(1.0, cached[0]["positionAmt"])
        cached[0]["positionAmt"] = 7.0
        self.assertEqual(1.0, get_cached_futures_positions(wrapper, 10.0)[0]["positionAmt"])

    def test_position_cache_rejects_disabled_and_stale_entries(self):
        wrapper = _PositionCacheWrapper()
        store_futures_positions_cache(wrapper, [{"symbol": "BTCUSDT"}])

        self.assertIsNone(get_cached_futures_positions(wrapper, 0.0))
        wrapper._positions_cache_ts = 1.0
        with mock.patch.object(formatter_runtime.time, "time", return_value=100.0):
            self.assertIsNone(get_cached_futures_positions(wrapper, 1.0))

    def test_position_cache_invalidation_clears_positions_and_account_snapshot(self):
        wrapper = _PositionCacheWrapper()
        store_futures_positions_cache(wrapper, [{"symbol": "BTCUSDT"}])

        invalidate_futures_positions_cache(wrapper)

        self.assertIsNone(wrapper._positions_cache)
        self.assertEqual(0.0, wrapper._positions_cache_ts)
        self.assertEqual(1, wrapper.account_invalidations)

    def test_exact_close_skips_when_authoritative_snapshot_is_flat(self):
        wrapper = _ExactCloseWrapper(positions=[])

        result = close_futures_leg_exact(wrapper, "BTCUSDT", 1.0, "SELL")

        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual("position already flat", result["reason"])
        self.assertEqual([], wrapper.orders)

    def test_exact_close_caps_requested_quantity_to_live_exposure(self):
        wrapper = _ExactCloseWrapper(
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.127", "positionSide": "BOTH"}]
        )

        result = close_futures_leg_exact(wrapper, "BTCUSDT", 1.0, "SELL")

        self.assertTrue(result["ok"])
        self.assertEqual(0.125, result["sent_qty"])
        self.assertEqual("0.125", wrapper.orders[0]["quantity"])
        self.assertTrue(wrapper.orders[0]["reduceOnly"])
        self.assertEqual(100.0, result["info"]["avgPrice"])
        self.assertEqual(1, wrapper.invalidations)

    def test_exact_hedge_close_never_falls_back_to_reduce_only_without_position_side(self):
        wrapper = _ExactCloseWrapper(
            dual=True,
            fail_orders=True,
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.2", "positionSide": "LONG"}],
        )

        result = close_futures_leg_exact(wrapper, "BTCUSDT", 0.2, "SELL", "LONG")

        self.assertFalse(result["ok"])
        self.assertEqual(1, len(wrapper.orders))
        self.assertEqual("LONG", wrapper.orders[0]["positionSide"])
        self.assertNotIn("reduceOnly", wrapper.orders[0])

    def test_symbol_close_submits_each_hedge_leg_with_explicit_position_side(self):
        wrapper = _ExactCloseWrapper(
            dual=True,
            clear_after_orders=2,
            positions=[
                {"symbol": "BTCUSDT", "positionAmt": "0.2", "positionSide": "LONG"},
                {"symbol": "BTCUSDT", "positionAmt": "-0.3", "positionSide": "SHORT"},
            ],
        )

        result = close_futures_position(wrapper, "BTCUSDT")

        self.assertEqual(
            {"ok": True, "closed": 2, "failed": 0, "errors": [], "remaining": 0},
            result,
        )
        self.assertEqual(["LONG", "SHORT"], [order["positionSide"] for order in wrapper.orders])
        self.assertTrue(all("reduceOnly" not in order for order in wrapper.orders))

    def test_symbol_close_uses_raw_exchange_snapshot_when_cached_view_is_empty(self):
        wrapper = _ExactCloseWrapper(positions=[])
        wrapper.client = _RawPositionClient(
            [{"symbol": "ETHUSDT", "positionAmt": "0.5", "positionSide": "BOTH"}]
        )
        wrapper.clear_raw_after_order = True

        result = close_futures_position(wrapper, "ETHUSDT")

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["closed"])
        self.assertEqual("SELL", wrapper.orders[0]["side"])
        self.assertTrue(wrapper.orders[0]["reduceOnly"])

    def test_symbol_close_reports_accepted_order_when_position_remains_open(self):
        wrapper = _ExactCloseWrapper(
            positions=[{"symbol": "BTCUSDT", "positionAmt": "0.2", "positionSide": "BOTH"}]
        )
        wrapper.client = _RawPositionClient(wrapper.positions)

        with mock.patch.object(position_close_runtime.time, "sleep"):
            result = close_futures_position(wrapper, "BTCUSDT")

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["remaining"])
        self.assertTrue(any("position remained open" in error for error in result["errors"]))

    def test_cancel_all_enumerates_unique_symbols_before_symbol_scoped_calls(self):
        client = _CancelClient(
            orders=[
                {"symbol": "btcusdt"},
                {"symbol": "ETHUSDT"},
                {"symbol": "BTCUSDT"},
            ]
        )
        wrapper = _CancelWrapper(client)

        result = cancel_all_open_futures_orders(wrapper)

        self.assertEqual({"ok": True, "canceled_symbols": 2, "errors": []}, result)
        self.assertEqual(["BTCUSDT", "ETHUSDT"], client.cancel_calls)
        self.assertEqual(0, wrapper.position_calls)

    def test_cancel_all_uses_open_positions_when_order_snapshot_is_empty(self):
        client = _CancelClient()
        wrapper = _CancelWrapper(client, positions=[{"symbol": "XRPUSDT"}])

        result = cancel_all_open_futures_orders(wrapper)

        self.assertTrue(result["ok"])
        self.assertEqual(1, result["canceled_symbols"])
        self.assertEqual(["XRPUSDT"], client.cancel_calls)
        self.assertEqual((0.0, True), wrapper.asserted_args)

    def test_cancel_all_reports_uncertain_order_snapshot_even_after_position_fallback(self):
        client = _CancelClient(order_error=RuntimeError("orders unavailable"))
        wrapper = _CancelWrapper(client, positions=[{"symbol": "BTCUSDT"}])

        result = cancel_all_open_futures_orders(wrapper)

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["canceled_symbols"])
        self.assertEqual(["BTCUSDT"], client.cancel_calls)
        self.assertTrue(any("orders unavailable" in error for error in result["errors"]))

    def test_cancel_all_reports_per_symbol_exchange_rejection(self):
        client = _CancelClient(
            orders=[{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
            fail_symbol="ETHUSDT",
        )
        wrapper = _CancelWrapper(client)

        result = cancel_all_open_futures_orders(wrapper)

        self.assertFalse(result["ok"])
        self.assertEqual(1, result["canceled_symbols"])
        self.assertTrue(any("ETHUSDT: cancel rejected" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
