from __future__ import annotations

import copy
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions.strategy_position_flip_runtime import _reconcile_liquidations  # noqa: E402


class _OfflineExchange:
    account_type = "FUTURES"
    mode = "Live"

    def __init__(self):
        self.positions = []
        self.requests = []

    def get_futures_dual_side(self):
        return False

    def list_open_futures_positions(self, **kwargs):
        self.requests.append(kwargs)
        return self.positions


class StrategyTradeBookContractTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        self.exchange = _OfflineExchange()
        config = build_default_config()
        config.update(symbol="BTCUSDT", interval="1m", account_type="FUTURES")
        self.engine = StrategyEngine(self.exchange, config, log_callback=lambda _message: None)
        self.key = ("BTCUSDT", "1m", "BUY")

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def append(self, ledger_id="shared", indicators=("rsi", "macd"), *, qty=1.0, key=None):
        entry = {
            "ledger_id": ledger_id,
            "trigger_signature": indicators,
            "qty": qty,
            "entry_price": 100.0,
            "margin_usdt": qty * 10,
            "timestamp": time.time(),
        }
        self.engine._append_leg_entry(key or self.key, entry)
        self.assertFalse(self.engine._ledger_reconciliation_required)
        return entry

    def assert_empty_tracking(self):
        self.assertEqual({}, self.engine._leg_ledger)
        self.assertEqual({}, self.engine._ledger_index)
        self.assertEqual({}, self.engine._symbol_signature_open)
        self.assertEqual({}, self.engine._trade_book)
        self.assertEqual({}, self.engine._last_order_time)
        for state in self.engine._indicator_state.values():
            self.assertFalse(any(state.values()))

    def assert_not_paused(self):
        self.assertFalse(self.engine._ledger_reconciliation_required)
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_partial_decrement_updates_all_owner_metadata_without_changing_neighbors(self):
        original = self.append()
        neighbor = self.append("neighbor", ("rsi",), qty=2.0)
        self.engine._decrement_leg_entry_qty(self.key, "shared", 1.0, 0.6)
        self.assertIn(neighbor, self.engine._leg_entries(self.key))
        for indicator in ("rsi", "macd"):
            record = self.engine._trade_book[("BTCUSDT", "1m", indicator, "BUY")]["shared"]
            self.assertAlmostEqual(0.6, record["qty"])
            self.assertAlmostEqual(6.0, record["margin_usdt"])
            self.assertEqual(original["entry_price"], record["entry_price"])
            self.assertEqual(original["timestamp"], record["timestamp"])
        self.assert_not_paused()

    def test_invalid_partial_decrement_does_not_publish_any_state(self):
        self.append()
        before_ledger = copy.deepcopy(self.engine._leg_ledger)
        before_book = copy.deepcopy(self.engine._trade_book)
        for ledger_id, previous, remaining in (
            (None, 1.0, 0.6), ("missing", 1.0, 0.6), ("shared", 2.0, 0.6),
            ("shared", 0.0, 0.0), ("shared", True, 0.6), ("shared", 1.0, None),
            ("shared", 1.0, -0.1), ("shared", 1.0, 2.0),
            ("shared", 1.0, float("nan")), ("shared", float("inf"), 0.6),
        ):
            with self.subTest(ledger_id=ledger_id, previous=previous, remaining=remaining):
                with self.assertRaises(ValueError):
                    self.engine._decrement_leg_entry_qty(self.key, ledger_id, previous, remaining)
                self.assertEqual(before_ledger, self.engine._leg_ledger)
                self.assertEqual(before_book, self.engine._trade_book)
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_partial_decrement_continues_other_owner_updates_after_failure(self):
        self.append()
        original_add = self.engine._trade_book_add_entry

        def fail_rsi(symbol, interval, indicator, *args):
            if indicator == "rsi":
                raise RuntimeError("owner index unavailable")
            return original_add(symbol, interval, indicator, *args)

        with patch.object(self.engine, "_trade_book_add_entry", side_effect=fail_rsi):
            with self.assertRaisesRegex(RuntimeError, "requires ledger reconciliation"):
                self.engine._decrement_leg_entry_qty(self.key, "shared", 1.0, 0.6)
        self.assertAlmostEqual(0.6, self.engine._leg_entries(self.key)[0]["qty"])
        self.assertAlmostEqual(6.0, self.engine._trade_book[("BTCUSDT", "1m", "macd", "BUY")]["shared"]["margin_usdt"])
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_purge_shared_entry_removes_every_ownership_index(self):
        self.append()

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assert_empty_tracking()
        self.assertEqual(0.0, self.engine._indicator_open_qty("BTCUSDT", "1m", "macd", "BUY"))
        self.assertFalse(self.engine._symbol_signature_active("BTCUSDT", "BUY", ("rsi", "macd"), "1m"))
        self.assert_not_paused()

    def test_partial_purge_preserves_unrelated_entry_and_shared_indicator_ownership(self):
        self.append()
        survivor = self.append("survivor", ("macd", "ema"), qty=2.0)

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual([survivor], self.engine._leg_entries(self.key))
        self.assertEqual({"survivor": self.key}, self.engine._ledger_index)
        self.assertEqual({("BTCUSDT", "1m", "BUY", ("ema", "macd")): 1}, self.engine._symbol_signature_open)
        self.assertEqual(2.0, self.engine._leg_ledger[self.key]["qty"])
        self.assertEqual(20.0, self.engine._leg_ledger[self.key]["margin_usdt"])
        self.assertEqual(100.0, self.engine._leg_ledger[self.key]["entry_price"])
        self.assertEqual(2.0, self.engine._indicator_open_qty("BTCUSDT", "1m", "macd", "BUY"))
        self.assertEqual({"survivor"}, self.engine._indicator_state[("BTCUSDT", "1m", "macd")]["BUY"])
        self.assertEqual({"survivor"}, set(self.engine._trade_book[("BTCUSDT", "1m", "macd", "BUY")]))
        self.assertIn(self.key, self.engine._last_order_time)
        self.assert_not_paused()

    def test_purge_is_scoped_to_exact_symbol_interval_and_side(self):
        self.append()
        unrelated = [
            ("ETHUSDT", "1m", "BUY"),
            ("BTCUSDT", "5m", "BUY"),
            ("BTCUSDT", "1m", "SELL"),
        ]
        for number, key in enumerate(unrelated):
            self.append(f"other-{number}", ("ema",), key=key)
        before = {key: copy.deepcopy(self.engine._leg_ledger[key]) for key in unrelated}

        self.engine._purge_indicator_tracking("btcusdt", " 1M ", "RSI", "LONG")

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertEqual({f"other-{number}": key for number, key in enumerate(unrelated)}, self.engine._ledger_index)
        self.assertEqual(3, sum(self.engine._symbol_signature_open.values()))
        self.assertEqual(3, len(self.engine._trade_book))
        self.assert_not_paused()

    def test_purge_all_indicators_also_removes_entries_without_indicator_metadata(self):
        self.append()
        self.append("generic", ())

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", None, "BUY")

        self.assert_empty_tracking()
        self.assert_not_paused()

    def test_canonical_remove_all_clears_index_for_entry_without_indicators(self):
        self.append("generic", ())

        self.engine._remove_leg_entry(self.key, None)

        self.assert_empty_tracking()
        self.assert_not_paused()

    def test_repeated_purge_does_not_decrement_survivor_signature(self):
        self.append()
        survivor = self.append("survivor", ("ema", "macd"))

        for _ in range(3):
            self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual([survivor], self.engine._leg_entries(self.key))
        self.assertEqual({("BTCUSDT", "1m", "BUY", ("ema", "macd")): 1}, self.engine._symbol_signature_open)
        self.assertEqual({"survivor": self.key}, self.engine._ledger_index)
        self.assert_not_paused()

    def test_purge_removes_multiple_entries_sharing_the_same_signature(self):
        self.append("first")
        self.append("second")
        self.assertEqual(2, sum(self.engine._symbol_signature_open.values()))

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assert_empty_tracking()
        self.assert_not_paused()

    def test_partial_purge_handles_entry_without_id_without_removing_its_neighbor(self):
        self.append(None)
        survivor = self.append("survivor", ("ema",))

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual([survivor], self.engine._leg_entries(self.key))
        self.assertEqual({"survivor": self.key}, self.engine._ledger_index)
        self.assertEqual({("BTCUSDT", "1m", "BUY", ("ema",)): 1}, self.engine._symbol_signature_open)
        self.assert_not_paused()

    def test_two_fresh_flat_snapshots_clear_tracking_and_allow_later_signature_reuse(self):
        self.append()
        _reconcile_liquidations(self.engine, "BTCUSDT")
        self.assertIn(self.key, self.engine._leg_ledger)

        _reconcile_liquidations(self.engine, "BTCUSDT")

        self.assert_empty_tracking()
        self.assertEqual([{"max_age": 0.0, "force_refresh": True}] * 2, self.exchange.requests)
        self.assert_not_paused()
        self.append("later")
        self.assertEqual(1, sum(self.engine._symbol_signature_open.values()))
        self.engine._remove_leg_entry(self.key, "later")
        self.assert_empty_tracking()

    def test_nonflat_read_resets_liquidation_confirmation_without_mutating_tracking(self):
        self.append()
        _reconcile_liquidations(self.engine, "BTCUSDT")
        self.exchange.positions = [{"symbol": "BTCUSDT", "positionAmt": "1", "positionSide": "BOTH"}]
        _reconcile_liquidations(self.engine, "BTCUSDT")
        self.exchange.positions = []

        _reconcile_liquidations(self.engine, "BTCUSDT")

        self.assertIn(self.key, self.engine._leg_ledger)
        self.assertEqual({"shared": self.key}, self.engine._ledger_index)
        self.assert_not_paused()
        _reconcile_liquidations(self.engine, "BTCUSDT")
        self.assert_empty_tracking()

    def test_absent_indicator_purge_does_not_refresh_or_rewrite_unrelated_leg(self):
        self.append()
        before = copy.deepcopy(self.engine._leg_ledger)

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "ema", "BUY")

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertEqual({"shared": self.key}, self.engine._ledger_index)
        self.assertEqual(2, len(self.engine._trade_book))
        self.assert_not_paused()

    def test_lookup_failure_preserves_primary_and_auxiliary_state_and_pauses(self):
        self.append()
        before_ledger = copy.deepcopy(self.engine._leg_ledger)
        before_book = copy.deepcopy(self.engine._trade_book)
        before_state = copy.deepcopy(self.engine._indicator_state)

        with patch.object(self.engine, "_extract_indicator_keys", side_effect=ValueError("bad ownership")):
            with self.assertRaises(ValueError):
                self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual(before_ledger, self.engine._leg_ledger)
        self.assertEqual(before_book, self.engine._trade_book)
        self.assertEqual(before_state, self.engine._indicator_state)
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_auxiliary_failure_still_attempts_other_cleanup_and_pauses(self):
        self.append()

        with patch.object(self.engine, "_indicator_unregister_entry", side_effect=RuntimeError("unregister failed")):
            with self.assertLogs("app.core.strategy.positions.strategy_position_ledger_runtime", level="ERROR"):
                self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual({}, self.engine._leg_ledger)
        self.assertEqual({}, self.engine._ledger_index)
        self.assertEqual({}, self.engine._symbol_signature_open)
        self.assertEqual({}, self.engine._trade_book)
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_quantity_sync_updates_every_indicator_book_and_preserves_relative_sizes(self):
        self.append("first", ("rsi", "macd"), qty=1.0)
        self.append("second", ("ema",), qty=3.0)

        self.engine._sync_leg_entry_totals(self.key, 2.0)

        self.assertEqual([0.5, 1.5], [entry["qty"] for entry in self.engine._leg_entries(self.key)])
        self.assertEqual([5.0, 15.0], [entry["margin_usdt"] for entry in self.engine._leg_entries(self.key)])
        self.assertEqual(2.0, self.engine._leg_ledger[self.key]["qty"])
        self.assertEqual(20.0, self.engine._leg_ledger[self.key]["margin_usdt"])
        self.assertEqual(0.5, self.engine._indicator_open_qty("BTCUSDT", "1m", "rsi", "BUY"))
        self.assertEqual(0.5, self.engine._indicator_open_qty("BTCUSDT", "1m", "macd", "BUY"))
        self.assertEqual(1.5, self.engine._indicator_open_qty("BTCUSDT", "1m", "ema", "BUY"))
        self.assertEqual(5.0, self.engine._trade_book[("BTCUSDT", "1m", "rsi", "BUY")]["first"]["margin_usdt"])
        self.assertEqual({"first": self.key, "second": self.key}, self.engine._ledger_index)
        self.assertEqual(2, sum(self.engine._symbol_signature_open.values()))
        self.assert_not_paused()

    def test_quantity_sync_from_zero_rebuilds_indicator_book(self):
        self.append("first", ("rsi",), qty=0.0)
        self.append("second", ("ema",), qty=0.0)

        self.engine._sync_leg_entry_totals(self.key, 2.0)

        self.assertEqual([1.0, 1.0], [entry["qty"] for entry in self.engine._leg_entries(self.key)])
        self.assertEqual({"first"}, set(self.engine._trade_book[("BTCUSDT", "1m", "rsi", "BUY")]))
        self.assertEqual(1.0, self.engine._trade_book_total_qty("BTCUSDT", "1m", "rsi", "BUY"))
        self.assertEqual(1.0, self.engine._trade_book_total_qty("BTCUSDT", "1m", "ema", "BUY"))
        self.assert_not_paused()

    def test_invalid_quantity_sync_preserves_ledger_and_book_and_pauses(self):
        self.append()
        ledger = copy.deepcopy(self.engine._leg_ledger)
        book = copy.deepcopy(self.engine._trade_book)
        for actual in (-1.0, float("nan"), float("inf"), "invalid", None, "", False, True):
            with self.subTest(actual=actual):
                self.engine._leg_ledger = copy.deepcopy(ledger)
                self.engine._trade_book = copy.deepcopy(book)
                self.engine._ledger_reconciliation_required = False
                StrategyEngine._GLOBAL_PAUSE.clear()
                with self.assertRaises((TypeError, ValueError)):
                    self.engine._sync_leg_entry_totals(self.key, actual)
                self.assertEqual(ledger, self.engine._leg_ledger)
                self.assertEqual(book, self.engine._trade_book)
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_sync_without_owned_entries_preserves_unattributed_quantity_and_pauses(self):
        self.engine._leg_ledger[self.key] = {"qty": 2.0, "entries": []}

        with self.assertRaises(ValueError):
            self.engine._sync_leg_entry_totals(self.key, 2.0)

        self.assertEqual(2.0, self.engine._leg_ledger[self.key]["qty"])
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_quantity_sync_to_zero_clears_book_but_retains_ledger_until_confirmed_cleanup(self):
        self.append()

        self.engine._sync_leg_entry_totals(self.key, 0.0)

        self.assertEqual(0.0, self.engine._leg_ledger[self.key]["qty"])
        self.assertEqual(0.0, self.engine._leg_ledger[self.key]["margin_usdt"])
        self.assertEqual({}, self.engine._trade_book)
        self.assertEqual({"shared": self.key}, self.engine._ledger_index)
        self.assertEqual(0.0, self.engine._indicator_open_qty("BTCUSDT", "1m", "rsi", "BUY"))
        self.assert_not_paused()
        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")
        self.assert_empty_tracking()

    def test_invalid_recorded_metadata_is_rejected_before_quantity_publication(self):
        self.append()
        original = copy.deepcopy(self.engine._leg_ledger)
        book = copy.deepcopy(self.engine._trade_book)
        for field in ("qty", "entry_price", "margin_usdt", "timestamp"):
            with self.subTest(field=field):
                self.engine._leg_ledger = copy.deepcopy(original)
                self.engine._leg_ledger[self.key]["entries"][0][field] = -1.0
                before = copy.deepcopy(self.engine._leg_ledger)
                with self.assertRaises(ValueError):
                    self.engine._sync_leg_entry_totals(self.key, 0.5)
                self.assertEqual(before, self.engine._leg_ledger)
                self.assertEqual(book, self.engine._trade_book)
                self.assertTrue(self.engine._ledger_reconciliation_required)

    def test_quantity_sync_rejects_overflow_without_mutating_ledger(self):
        self.append()
        before = copy.deepcopy(self.engine._leg_ledger)

        with self.assertRaises(ValueError):
            self.engine._sync_leg_entry_totals(self.key, 1e308)

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_sync_ownership_lookup_failure_does_not_publish_new_quantities(self):
        self.append()
        before = copy.deepcopy(self.engine._leg_ledger)
        with patch.object(self.engine, "_extract_indicator_keys", side_effect=ValueError("ownership failed")):
            with self.assertRaises(ValueError):
                self.engine._sync_leg_entry_totals(self.key, 0.5)

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertEqual(1.0, self.engine._trade_book_total_qty("BTCUSDT", "1m", "rsi", "BUY"))
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_sync_book_update_failure_is_not_silently_accepted(self):
        self.append()
        with patch.object(self.engine, "_trade_book_add_entry", side_effect=RuntimeError("book failed")):
            with self.assertRaises(RuntimeError):
                self.engine._sync_leg_entry_totals(self.key, 0.5)

        self.assertEqual(0.5, self.engine._leg_ledger[self.key]["qty"])
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_remove_by_id_preserves_other_entry_with_identical_signature(self):
        self.append("first")
        survivor = self.append("second")

        self.engine._remove_leg_entry(self.key, "first")

        self.assertEqual([survivor], self.engine._leg_entries(self.key))
        self.assertEqual({"second": self.key}, self.engine._ledger_index)
        self.assertEqual(1, sum(self.engine._symbol_signature_open.values()))
        for book in self.engine._trade_book.values():
            self.assertEqual({"second"}, set(book))
        self.assert_not_paused()

    def test_remove_id_and_indicator_selectors_must_both_match(self):
        self.append("shared")
        self.append("other", ("ema",))
        before = copy.deepcopy(self.engine._leg_ledger)

        self.engine._remove_leg_entry(self.key, "other", indicator_key="rsi")

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertEqual(2, len(self.engine._ledger_index))
        self.assert_not_paused()

    def test_remove_unknown_id_is_a_true_noop(self):
        self.append()
        before = copy.deepcopy(self.engine._leg_ledger)

        self.engine._remove_leg_entry(self.key, "absent")

        self.assertEqual(before, self.engine._leg_ledger)
        self.assertEqual({"shared": self.key}, self.engine._ledger_index)
        self.assert_not_paused()

    def test_signature_cleanup_failure_does_not_prevent_other_index_cleanup(self):
        self.append()
        with patch.object(self.engine, "_bump_symbol_signature_open", side_effect=RuntimeError("count failed")):
            with self.assertLogs("app.core.strategy.positions.strategy_position_ledger_runtime", level="ERROR"):
                self.engine._remove_leg_entry(self.key, "shared")

        self.assertEqual({}, self.engine._leg_ledger)
        self.assertEqual({}, self.engine._ledger_index)
        self.assertEqual({}, self.engine._trade_book)
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_one_book_cleanup_failure_does_not_prevent_other_owner_cleanup(self):
        self.append()
        original_remove = self.engine._trade_book_remove_entry

        def remove(symbol, interval, indicator, side, ledger_id):
            if indicator == "macd":
                raise RuntimeError("macd book failed")
            original_remove(symbol, interval, indicator, side, ledger_id)

        with patch.object(self.engine, "_trade_book_remove_entry", side_effect=remove):
            with self.assertLogs("app.core.strategy.positions.strategy_position_ledger_runtime", level="ERROR"):
                self.engine._remove_leg_entry(self.key, "shared")

        self.assertEqual({}, self.engine._leg_ledger)
        self.assertEqual({}, self.engine._ledger_index)
        self.assertNotIn(("BTCUSDT", "1m", "rsi", "BUY"), self.engine._trade_book)
        self.assertIn(("BTCUSDT", "1m", "macd", "BUY"), self.engine._trade_book)
        for state in self.engine._indicator_state.values():
            self.assertFalse(any(state.values()))
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_removal_snapshot_failure_pauses_and_propagates(self):
        self.append()
        self.append("survivor", ("ema",))
        with patch.object(self.engine, "_update_leg_snapshot", side_effect=ValueError("snapshot failed")):
            with self.assertRaises(ValueError):
                self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_purge_clears_orphan_book_records_only_in_requested_scope(self):
        entry = {"timestamp": 1.0, "entry_price": 100.0, "margin_usdt": 10.0}
        self.engine._trade_book_add_entry("BTCUSDT", "1m", "rsi", "BUY", "orphan", 1.0, entry)
        self.engine._indicator_register_entry("BTCUSDT", "1m", "rsi", "BUY", "orphan")
        self.engine._trade_book_add_entry("BTCUSDT", "5m", "rsi", "BUY", "keep", 1.0, entry)

        self.engine._purge_indicator_tracking("BTCUSDT", "1m", "rsi", "BUY")

        self.assertEqual({("BTCUSDT", "5m", "rsi", "BUY")}, set(self.engine._trade_book))
        self.assertNotIn(("BTCUSDT", "1m", "rsi"), self.engine._indicator_state)
        self.assert_not_paused()


if __name__ == "__main__":
    unittest.main()
