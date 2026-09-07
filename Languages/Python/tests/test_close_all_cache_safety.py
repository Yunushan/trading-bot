import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.positions.close_results import confirmed_closed_position_keys
from app.gui.positions.tracking_runtime import _apply_close_all_to_positions_cache
from app.integrations.exchanges.binance.positions.close_all_runtime import (
    _gather_positions,
    close_all_futures_positions,
)


def window_state():
    keys = (("BTCUSDT", "L"), ("BTCUSDT", "S"), ("ETHUSDT", "L"))
    return SimpleNamespace(
        config={"positions_closed_history_max": 200},
        _open_position_records={
            key: {"symbol": key[0], "side_key": key[1], "status": "Open", "data": {"qty": 2.0}}
            for key in keys
        },
        _entry_allocations={key: [{"qty": 2.0, "interval": "1m"}] for key in keys},
        _closed_position_records=[],
        _pending_close_times={},
        _position_missing_counts={},
        _entry_intervals={},
        _entry_times={key: "open-time" for key in keys},
        _entry_times_by_iv={(key[0], key[1], "1m"): "open-time" for key in keys},
        guard=SimpleNamespace(clear_symbol_side=Mock()),
        _format_display_time=lambda _dt: "close-time",
        _compute_global_pnl_totals=lambda: (0.0, 0.0),
        _update_global_pnl_display=Mock(),
        _render_positions_table=Mock(),
        _chart_debug_log=Mock(),
    )


def closure(**updates):
    return {"symbol": "BTCUSDT", "side_key": "L", "ok": True, "position_closed": True, **updates}


class CloseAllCacheSafetyTests(unittest.TestCase):
    def test_only_the_confirmed_hedge_side_is_removed(self):
        window = window_state()
        _apply_close_all_to_positions_cache(window, [
            closure(), closure(side_key="S", ok=False, position_closed=False, error="still open"),
        ])
        self.assertNotIn(("BTCUSDT", "L"), window._open_position_records)
        self.assertEqual({("BTCUSDT", "S"), ("ETHUSDT", "L")}, set(window._open_position_records))
        self.assertEqual({("BTCUSDT", "S"), ("ETHUSDT", "L")}, set(window._entry_allocations))
        self.assertEqual(["L"], [record["side_key"] for record in window._closed_position_records])
        window.guard.clear_symbol_side.assert_called_once_with("BTCUSDT", "BUY")
        self.assertIn(("BTCUSDT", "S", "1m"), window._entry_times_by_iv)

    def test_unverified_results_cannot_erase_local_exposure(self):
        cases = (
            None, [], {}, [None], [{"symbol": "BTCUSDT", "ok": True}],
            [closure(position_closed=False)], [closure(ok=False)],
            [closure(skipped=True)], [closure(position_closed="true")],
            [closure(skipped="false")],
            [closure(ok="true")], [closure(side_key="BOTH")],
            [closure(side_key="")], [closure(), {"ok": False, "error": "snapshot unavailable"}],
            [closure(), closure(position_closed=False)],
        )
        for results in cases:
            with self.subTest(results=results):
                window = window_state()
                records = copy.deepcopy(window._open_position_records)
                allocations = copy.deepcopy(window._entry_allocations)
                _apply_close_all_to_positions_cache(window, results)
                self.assertEqual(records, window._open_position_records)
                self.assertEqual(allocations, window._entry_allocations)
                self.assertEqual([], window._closed_position_records)
                self.assertEqual({}, window._pending_close_times)
                window.guard.clear_symbol_side.assert_not_called()

    def test_confirmed_short_closure_does_not_clear_long_or_duplicate_history(self):
        window = window_state()
        result = closure(side_key="S")
        _apply_close_all_to_positions_cache(window, [result, result])
        _apply_close_all_to_positions_cache(window, [result])
        self.assertIn(("BTCUSDT", "L"), window._open_position_records)
        self.assertEqual(["S"], [record["side_key"] for record in window._closed_position_records])
        window.guard.clear_symbol_side.assert_called_once_with("BTCUSDT", "SELL")

    def test_result_contract_normalizes_keys_but_not_boolean_authority(self):
        self.assertEqual({("BTCUSDT", "S")}, confirmed_closed_position_keys(
            closure(symbol=" btcusdt ", side_key=" s "),
        ))
        self.assertEqual({("BTCUSDT", "SPOT")}, confirmed_closed_position_keys(
            [closure(side_key="SPOT")],
        ))
        self.assertEqual(set(), confirmed_closed_position_keys("closed"))
        self.assertEqual(set(), confirmed_closed_position_keys([closure(symbol="?")]))
        self.assertEqual(set(), confirmed_closed_position_keys([closure(), closure(side_key="BOTH")]))


class OfflineCloseClient:
    def __init__(self, *, hedge=True, verification_failure=False):
        self.hedge = hedge
        self.verification_failure = verification_failure
        self.orders = []
        self.rows = [
            {"symbol": "BTCUSDT", "positionSide": "LONG", "positionAmt": "2"},
            {"symbol": "BTCUSDT", "positionSide": "SHORT", "positionAmt": "-3"},
        ] if hedge else [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "-2"}]

    def futures_get_position_mode(self):
        return {"dualSidePosition": self.hedge}

    def futures_position_information(self):
        if self.verification_failure and self.orders:
            raise OSError("offline snapshot fixture failure")
        return copy.deepcopy(self.rows)

    def futures_account(self):
        raise OSError("offline fallback fixture failure")

    def futures_cancel_all_open_orders(self, **_params):
        return {"code": 200}

    def futures_create_order(self, **params):
        self.orders.append(params)
        if self.hedge and params.get("positionSide") == "SHORT":
            raise RuntimeError("offline short-close fixture rejection")
        self.rows = [row for row in self.rows if row["positionSide"] == "SHORT"] if self.hedge else []
        return {"orderId": len(self.orders), "status": "FILLED", "executedQty": params["quantity"]}


class CloseAllVerificationTests(unittest.TestCase):
    def wrapper(self, **kwargs):
        return SimpleNamespace(mode="Live", client=OfflineCloseClient(**kwargs))

    def test_real_close_producer_and_cache_preserve_the_failed_hedge_side(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                wrapper = self.wrapper()
                results = close_all_futures_positions(wrapper, fast=fast, max_workers=1)
                by_side = {result.get("side_key"): result for result in results}
                self.assertEqual({"L", "S"}, set(by_side))
                self.assertTrue(by_side["L"]["position_closed"])
                self.assertFalse(by_side["S"]["position_closed"])
                window = window_state()
                _apply_close_all_to_positions_cache(window, results)
                self.assertEqual({("BTCUSDT", "S"), ("ETHUSDT", "L")}, set(window._open_position_records))
                self.assertEqual(1, sum(order.get("positionSide") == "LONG" for order in wrapper.client.orders))

    def test_one_way_short_retains_direction_after_exchange_is_flat(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                wrapper = self.wrapper(hedge=False)
                results = close_all_futures_positions(wrapper, fast=fast, max_workers=1)
                self.assertEqual(1, len(results))
                self.assertEqual("S", results[0].get("side_key"))
                self.assertTrue(results[0].get("position_closed"))
                self.assertEqual("BUY", wrapper.client.orders[0]["side"])

    def test_unavailable_final_snapshot_cannot_be_reported_as_a_closed_position(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                results = close_all_futures_positions(
                    self.wrapper(hedge=False, verification_failure=True), fast=fast, max_workers=1,
                )
                self.assertTrue(results)
                self.assertTrue(all(result.get("position_closed") is False for result in results))
                self.assertTrue(all(result.get("ok") is False for result in results))
                self.assertIn("verification", results[0]["error"])

    def test_malformed_snapshot_is_unknown_not_flat(self):
        invalid = (None, {}, {"code": -1}, [None], [{}],
                   [{"symbol": "BTCUSDT", "positionAmt": True}],
                   [{"symbol": "BTCUSDT", "positionAmt": "NaN"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "inf"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "bad"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "1e-999"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "0", "positionSide": "UNKNOWN"}],
                   [{"symbol": "", "positionAmt": "0"}],
                   [{"symbol": "BTCUSDT", "positionAmt": "2"}, {"symbol": "ETHUSDT"}])
        for snapshot in invalid:
            with self.subTest(snapshot=snapshot):
                client = SimpleNamespace(
                    futures_position_information=Mock(return_value=snapshot),
                    futures_account=Mock(return_value={}),
                )
                rows, ok = _gather_positions(SimpleNamespace(client=client))
                self.assertFalse(ok)
                self.assertEqual([], rows)

    def test_valid_empty_fallback_snapshot_is_distinct_from_missing_positions(self):
        client = SimpleNamespace(
            futures_position_information=Mock(side_effect=OSError("offline primary failure")),
            futures_account=Mock(return_value={"positions": []}),
        )
        self.assertEqual(([], True), _gather_positions(SimpleNamespace(client=client)))

    def test_unknown_initial_snapshot_reports_failure_without_submitting(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                wrapper = self.wrapper()
                wrapper.client.futures_position_information = Mock(return_value={"code": -1})
                results = close_all_futures_positions(wrapper, fast=fast, max_workers=1)
                self.assertEqual([], wrapper.client.orders)
                self.assertEqual(1, len(results))
                self.assertFalse(results[0]["ok"])
                self.assertFalse(results[0]["position_closed"])

    def test_reopened_opposite_one_way_position_is_not_marked_closed(self):
        for fast in (False, True):
            with self.subTest(fast=fast):
                wrapper = self.wrapper(hedge=False)
                original_submit = wrapper.client.futures_create_order

                def submit(**params):
                    if params["side"] == "SELL":
                        raise RuntimeError("offline reopened long cannot close")
                    result = original_submit(**params)
                    wrapper.client.rows = [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "1"}]
                    return result

                wrapper.client.futures_create_order = submit
                results = close_all_futures_positions(wrapper, fast=fast, max_workers=1)
                by_side = {result["side_key"]: result for result in results}
                self.assertTrue(by_side["S"]["position_closed"])
                self.assertFalse(by_side["L"]["position_closed"])
                self.assertEqual(1.0, by_side["L"]["remaining_qty"])


if __name__ == "__main__":
    unittest.main()
