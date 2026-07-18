import importlib.util
import sys
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
    / "close_all_runtime.py"
)
spec = importlib.util.spec_from_file_location("binance_close_all_runtime", MODULE_PATH)
close_all_runtime = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(close_all_runtime)
close_all_futures_positions = close_all_runtime.close_all_futures_positions


class _GhostClient:
    def __init__(self):
        self.margin_calls = []
        self.cancel_calls = []
        self.cleared = False

    def futures_get_position_mode(self):
        return {"dualSidePosition": False}

    def futures_cancel_all_open_orders(self, **params):
        self.cancel_calls.append(dict(params))
        return {"ok": True}

    def futures_position_information(self):
        if self.cleared:
            return []
        return [
            {
                "symbol": "DOGEUSDT",
                "positionAmt": "0",
                "positionSide": "BOTH",
                "isolatedWallet": "-25999.60",
                "isolatedMargin": "-25999.60",
                "notional": "0",
            }
        ]

    def futures_change_position_margin(self, **params):
        self.margin_calls.append(dict(params))
        self.cleared = True
        return {
            "amount": params.get("amount"),
            "code": 200,
            "msg": "Successfully modify position margin.",
            "type": params.get("type"),
        }


class _GhostWrapper:
    def __init__(self, mode="Demo/Testnet", client=None):
        self.mode = mode
        self.client = client or _GhostClient()


class _DirectFallbackClient(_GhostClient):
    def futures_change_position_margin(self, **params):
        raise AttributeError("not available")


class _DirectFallbackWrapper(_GhostWrapper):
    def __init__(self):
        super().__init__(client=_DirectFallbackClient())
        self.direct_calls = []
        self._last_futures_http_error = None

    def _futures_api_prefix(self):
        return "/fapi"

    def _http_signed_futures_request(self, method, path, params, *, prefix=None):
        self.direct_calls.append(
            {
                "method": method,
                "path": path,
                "params": dict(params),
                "prefix": prefix,
            }
        )
        self.client.cleared = True
        return {"amount": params.get("amount"), "code": 200, "msg": "ok", "type": params.get("type")}


class _DelayedCloseClient(_GhostClient):
    def __init__(self, *, close_after_orders=2):
        super().__init__()
        self.close_after_orders = int(close_after_orders)
        self.orders = []

    def futures_position_information(self):
        if len(self.orders) >= self.close_after_orders:
            return []
        return [
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0.2",
                "positionSide": "BOTH",
            }
        ]

    def futures_create_order(self, **params):
        self.orders.append(dict(params))
        return {"orderId": len(self.orders), "status": "NEW"}


class _DelayedCloseWrapper(_GhostWrapper):
    def __init__(self, *, close_after_orders=2):
        super().__init__(mode="Live", client=_DelayedCloseClient(close_after_orders=close_after_orders))


class _HedgeCloseClient(_DelayedCloseClient):
    def __init__(self):
        super().__init__(close_after_orders=2)

    def futures_get_position_mode(self):
        return {"dualSidePosition": True}

    def futures_position_information(self):
        if len(self.orders) >= self.close_after_orders:
            return []
        return [
            {"symbol": "BTCUSDT", "positionAmt": "0.2", "positionSide": "LONG"},
            {"symbol": "ETHUSDT", "positionAmt": "-0.3", "positionSide": "SHORT"},
        ]


class _HedgeCloseWrapper(_GhostWrapper):
    def __init__(self):
        super().__init__(mode="Live", client=_HedgeCloseClient())


class _BelowMinimumWrapper(_DelayedCloseWrapper):
    def __init__(self):
        super().__init__(close_after_orders=99)
        self.client.close_after_orders = 99
        self.client.futures_position_information = lambda: [
            {"symbol": "ETHUSDT", "positionAmt": "0.05", "positionSide": "BOTH"}
        ]

    def get_futures_symbol_filters(self, _symbol):
        return {"stepSize": "0.01", "minQty": "0.10", "maxQty": "100"}


class _UnknownExecutionError(RuntimeError):
    code = -1007


class _UnknownExecutionClient(_DelayedCloseClient):
    def __init__(self):
        super().__init__(close_after_orders=1)

    def futures_create_order(self, **params):
        self.orders.append(dict(params))
        raise _UnknownExecutionError("execution status unknown")


class _UnknownExecutionWrapper(_GhostWrapper):
    def __init__(self):
        super().__init__(mode="Live", client=_UnknownExecutionClient())


class _CancelFallbackClient(_GhostClient):
    def __init__(self):
        super().__init__()
        self.individual_cancel_calls = []

    def futures_cancel_all_open_orders(self, **params):
        raise RuntimeError(f"bulk cancel unavailable for {params.get('symbol')}")

    def futures_get_open_orders(self, **_params):
        return [{"orderId": 11}, {"orderId": 12}]

    def futures_cancel_order(self, **params):
        self.individual_cancel_calls.append(dict(params))
        return {"code": 200}


class _CancelFailureCloseClient(_DelayedCloseClient):
    def futures_cancel_all_open_orders(self, **_params):
        raise RuntimeError("bulk cancel unavailable")

    def futures_get_open_orders(self, **_params):
        raise RuntimeError("open-order snapshot unavailable")


class _CancelFailureCloseWrapper(_GhostWrapper):
    def __init__(self):
        super().__init__(mode="Live", client=_CancelFailureCloseClient(close_after_orders=1))


class BinanceGhostPositionCloseAllTests(unittest.TestCase):
    def test_demo_stop_clears_zero_qty_negative_isolated_margin(self):
        wrapper = _GhostWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["symbol"], "DOGEUSDT")
        self.assertEqual(results[0]["method"], "positionMargin")
        self.assertEqual(results[0]["amount"], "25999.6")
        self.assertEqual(
            wrapper.client.margin_calls,
            [{"symbol": "DOGEUSDT", "amount": "25999.6", "type": 1}],
        )

    def test_live_mode_does_not_auto_transfer_margin_for_zero_qty_residual(self):
        wrapper = _GhostWrapper(mode="Live")

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(results, [])
        self.assertEqual(wrapper.client.margin_calls, [])

    def test_demo_cleanup_uses_signed_futures_request_fallback(self):
        wrapper = _DirectFallbackWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["method"], "positionMargin")
        self.assertEqual(
            wrapper.direct_calls,
            [
                {
                    "method": "POST",
                    "path": "/v1/positionMargin",
                    "params": {"symbol": "DOGEUSDT", "amount": "25999.6", "type": 1},
                    "prefix": "/fapi",
                }
            ],
        )

    def test_fast_close_retries_when_successful_order_leaves_position_open(self):
        wrapper = _DelayedCloseWrapper(close_after_orders=2)

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(2, len(wrapper.client.orders))
        self.assertEqual(1, len(results))
        self.assertTrue(results[0]["ok"])
        self.assertEqual("reduceOnly", results[0]["method"])
        self.assertEqual(
            {
                "symbol": "ETHUSDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": "0.20000000",
                "reduceOnly": True,
            },
            wrapper.client.orders[-1],
        )
        self.assertEqual([{"symbol": "ETHUSDT"}], wrapper.client.cancel_calls)

    def test_fast_close_reports_position_that_remains_open_after_retries(self):
        wrapper = _DelayedCloseWrapper(close_after_orders=99)

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(3, len(wrapper.client.orders))
        self.assertEqual(1, len(results))
        self.assertFalse(results[0]["ok"])
        self.assertEqual("verification", results[0]["method"])
        self.assertIn("position remained open", results[0]["error"])

    def test_default_close_uses_immediate_quantity_order_not_conditional_close_position(self):
        wrapper = _DelayedCloseWrapper(close_after_orders=1)

        results = close_all_futures_positions(wrapper)

        self.assertEqual(1, len(results))
        self.assertTrue(results[0]["ok"])
        self.assertEqual("reduceOnly", results[0]["method"])
        self.assertNotIn("closePosition", wrapper.client.orders[0])
        self.assertEqual("0.20000000", wrapper.client.orders[0]["quantity"])
        self.assertEqual([{"symbol": "ETHUSDT"}], wrapper.client.cancel_calls)

    def test_hedge_close_uses_position_side_without_reduce_only(self):
        wrapper = _HedgeCloseWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(2, len(results))
        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "type": "MARKET",
                    "quantity": "0.20000000",
                    "positionSide": "LONG",
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": "0.30000000",
                    "positionSide": "SHORT",
                },
            ],
            wrapper.client.orders,
        )
        self.assertTrue(all("reduceOnly" not in order for order in wrapper.client.orders))

    def test_below_minimum_position_is_not_increased_into_an_oversized_close(self):
        wrapper = _BelowMinimumWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual([], wrapper.client.orders)
        self.assertEqual(1, len(results))
        self.assertFalse(results[0]["ok"])
        self.assertEqual("validation", results[0]["method"])
        self.assertIn("cannot be safely represented", results[0]["error"])

    def test_unknown_execution_is_reconciled_from_authoritative_position_snapshot(self):
        wrapper = _UnknownExecutionWrapper()

        with mock.patch.object(close_all_runtime.time, "sleep"):
            results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual(1, len(results))
        self.assertTrue(results[0]["ok"])
        self.assertTrue(results[0]["reconciled"])

    def test_close_order_submission_rejects_unacknowledged_responses(self):
        cases = (None, "accepted", {}, {"status": "NEW"}, {"code": -2010, "msg": "rejected"})
        for response in cases:
            with self.subTest(response=response):
                wrapper = _GhostWrapper(mode="Live")
                wrapper.client.futures_create_order = lambda **_params: response

                with self.assertRaisesRegex(RuntimeError, "not explicitly acknowledged"):
                    close_all_runtime._submit_futures_order(
                        wrapper,
                        {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"},
                    )

    def test_symbol_cancel_falls_back_to_individual_orders(self):
        wrapper = _GhostWrapper(client=_CancelFallbackClient())

        self.assertTrue(close_all_runtime._cancel_all(wrapper, "BTCUSDT"))

        self.assertEqual(
            [
                {"symbol": "BTCUSDT", "orderId": 11},
                {"symbol": "BTCUSDT", "orderId": 12},
            ],
            wrapper.client.individual_cancel_calls,
        )

    def test_close_all_blocks_a_symbol_when_open_order_cancellation_is_unverified(self):
        wrapper = _CancelFailureCloseWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual([], wrapper.client.orders)
        self.assertEqual(1, len(results))
        self.assertFalse(results[0]["ok"])
        self.assertEqual("cancel-verification", results[0]["method"])
        self.assertIn("cancellation was not confirmed", results[0]["error"])


if __name__ == "__main__":
    unittest.main()
