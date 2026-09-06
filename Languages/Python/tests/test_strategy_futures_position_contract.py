from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions import strategy_position_futures_runtime as runtime  # noqa: E402


class _Exchange:
    account_type = "FUTURES"
    mode = "Live"

    def __init__(self):
        self.list_open_futures_positions = Mock(return_value=[])

    def get_futures_dual_side(self):
        return False


class FuturesPositionContractTests(unittest.TestCase):
    def setUp(self):
        self.reset_engine()

    def reset_engine(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        config = build_default_config()
        config.update(symbol="BTCUSDT", interval="1m", account_type="FUTURES")
        self.logs = []
        self.engine = StrategyEngine(_Exchange(), config, log_callback=self.logs.append)
        self.key = ("BTCUSDT", "1m", "BUY")

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def seed_leg(self, *, timestamp=100.0, qty=1.0):
        entry = {
            "ledger_id": "test-leg",
            "qty": qty,
            "timestamp": timestamp,
            "entry_price": 100.0,
            "margin_usdt": 10.0,
            "trigger_indicators": ["RSI"],
        }
        self.engine._leg_ledger[self.key] = {
            "qty": qty,
            "timestamp": timestamp,
            "entries": [entry],
        }
        return entry

    def purge(self, positions=None, *, dual=False):
        with patch.object(runtime.time, "time", return_value=1_000.0):
            self.engine._purge_flat_futures_legs(
                "btcusdt",
                [] if positions is None else positions,
                dual_side=dual,
            )

    def test_one_way_and_hedged_quantity_queries_keep_sides_separate(self):
        cases = [
            ("BUY", None, "BOTH", "2", 2.0),
            ("SELL", None, "BOTH", "2", 0.0),
            ("BUY", None, "BOTH", "-3", 0.0),
            ("SELL", None, "BOTH", "-3", 3.0),
            ("LONG", None, "LONG", "2", 2.0),
            ("SHORT", None, "LONG", "2", 0.0),
            ("BUY", None, "SHORT", "-3", 0.0),
            ("SELL", None, "SHORT", "-3", 3.0),
            ("BUY", "LONG", "LONG", "2", 2.0),
            ("BUY", "LONG", "SHORT", "-3", 0.0),
            ("SELL", "SHORT", "SHORT", "-3", 3.0),
            ("SELL", "SHORT", "LONG", "2", 0.0),
            ("BUY", None, "BOTH", "0.0000001", 0.0),
        ]
        for side, desired, position_side, amount, expected in cases:
            with self.subTest(side=side, desired=desired, amount=amount, row_side=position_side):
                rows = [
                    {"symbol": "ETHUSDT", "positionAmt": "99"},
                    {"symbol": "BTCUSDT", "positionSide": position_side, "positionAmt": amount},
                ]
                self.assertEqual(
                    expected,
                    self.engine._current_futures_position_qty(
                        "btcusdt",
                        side,
                        desired,
                        rows,
                    ),
                )
        self.engine.binance.list_open_futures_positions.assert_not_called()

    def test_position_fetch_is_forced_fresh_and_failures_are_unknown_not_flat(self):
        fetch = self.engine.binance.list_open_futures_positions
        fetch.return_value = [{"symbol": "BTCUSDT", "positionAmt": "2"}]
        self.assertEqual(2.0, self.engine._current_futures_position_qty("BTCUSDT", "BUY", None))
        fetch.assert_called_once_with(max_age=0.0, force_refresh=True)
        for result in ({}, "invalid", None):
            with self.subTest(result=result):
                fetch.return_value = result
                self.assertIsNone(self.engine._current_futures_position_qty("BTCUSDT", "BUY", None))
        fetch.side_effect = TimeoutError("offline fixture")
        self.assertIsNone(self.engine._current_futures_position_qty("BTCUSDT", "BUY", None))

    def test_malformed_snapshot_rows_are_unknown_even_for_another_symbol(self):
        for row in (
            None,
            "invalid",
            {"symbol": "BTCUSDT", "positionAmt": "invalid"},
            {"symbol": "BTCUSDT", "positionAmt": "nan"},
            {"symbol": "ETHUSDT", "positionAmt": "inf"},
            {"symbol": "BTCUSDT", "positionAmt": "-inf"},
        ):
            with self.subTest(row=row):
                self.assertIsNone(self.engine._current_futures_position_qty("BTCUSDT", "BUY", None, [row]))

    def test_flat_purge_requires_consecutive_absence_and_resets_on_live_observation(self):
        self.seed_leg()
        other = ("ETHUSDT", "1m", "BUY")
        self.engine._leg_ledger[other] = {"qty": 1, "entries": []}
        self.engine._flat_purge_miss_threshold = 2
        self.purge()
        self.assertIn(self.key, self.engine._leg_ledger)
        self.assertEqual(1, self.engine._flat_purge_miss_counts[self.key])
        self.purge([{"symbol": "BTCUSDT", "positionAmt": "1"}])
        self.assertNotIn(self.key, self.engine._flat_purge_miss_counts)
        self.purge()
        self.assertIn(self.key, self.engine._leg_ledger)
        self.purge()
        self.assertNotIn(self.key, self.engine._leg_ledger)
        self.assertIn(other, self.engine._leg_ledger)
        self.assertNotIn(self.key, self.engine._flat_purge_miss_counts)
        self.assertTrue(any("Purged stale BUY leg" in text for text in self.logs))
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_recent_entries_and_demo_grace_prevent_premature_purge(self):
        self.engine._flat_purge_miss_threshold = 1
        for mode, timestamp in (("Live", 995.0), ("Demo/Testnet", 975.0)):
            with self.subTest(mode=mode):
                self.engine.binance.mode = mode
                self.seed_leg(timestamp=timestamp)
                self.purge(dual=True)
                self.assertIn(self.key, self.engine._leg_ledger)
                self.assertNotIn(self.key, self.engine._flat_purge_miss_counts)

    def test_legacy_leg_timestamp_is_used_when_entries_have_no_timestamp(self):
        self.engine._flat_purge_miss_threshold = 1
        entry = self.seed_leg(timestamp=995.0)
        entry.pop("timestamp")
        self.purge()
        self.assertIn(self.key, self.engine._leg_ledger)
        self.engine._leg_ledger[self.key]["timestamp"] = 100.0
        self.purge()
        self.assertNotIn(self.key, self.engine._leg_ledger)

    def test_uncertain_observations_preserve_the_leg_and_pause(self):
        entry = self.seed_leg()
        before = copy.deepcopy(self.engine._leg_ledger[self.key])
        self.purge([{"symbol": "BTCUSDT", "positionAmt": "nan"}])
        self.assertEqual(before, self.engine._leg_ledger[self.key])
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertNotIn(self.key, self.engine._flat_purge_miss_counts)
        self.assertEqual(entry, self.engine._leg_ledger[self.key]["entries"][0])

    def test_invalid_purge_policy_and_entry_timestamps_require_reconciliation(self):
        for attribute, value in (("_flat_purge_grace_seconds", "invalid"), ("_flat_purge_miss_threshold", "invalid")):
            with self.subTest(attribute=attribute):
                self.reset_engine()
                self.seed_leg()
                setattr(self.engine, attribute, value)
                self.purge()
                self.assertIn(self.key, self.engine._leg_ledger)
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        for timestamp in ("invalid", -1.0, float("nan"), float("inf")):
            with self.subTest(timestamp=timestamp):
                self.reset_engine()
                self.seed_leg(timestamp=timestamp)
                self.purge()
                self.assertIn(self.key, self.engine._leg_ledger)
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_entry_lookup_failure_preserves_ledger_and_pauses(self):
        self.seed_leg()
        self.engine._leg_entries = Mock(side_effect=RuntimeError("fixture storage unavailable"))
        self.purge()
        self.assertIn(self.key, self.engine._leg_ledger)
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_cleanup_failure_after_confirmed_flatness_pauses_for_reconciliation(self):
        for name in ("_mark_indicator_reentry_signal_block", "_record_indicator_close", "_queue_flip_on_close"):
            with self.subTest(name=name):
                self.reset_engine()
                self.seed_leg()
                self.engine._flat_purge_miss_threshold = 1
                operation = Mock(side_effect=RuntimeError("fixture cleanup unavailable"))
                setattr(self.engine, name, operation)
                self.purge()
                operation.assert_called()
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_invalid_recorded_quantity_is_not_silently_treated_as_a_flat_leg(self):
        for quantity in ("invalid", float("inf"), float("nan"), float("-inf"), -1):
            with self.subTest(quantity=quantity):
                self.reset_engine()
                self.seed_leg(qty=quantity)
                self.engine._flat_purge_miss_threshold = 1
                self.purge()
                self.assertIn(self.key, self.engine._leg_ledger)
                self.assertTrue(self.engine._ledger_reconciliation_required)
                self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_entry_margin_uses_explicit_margin_then_quantity_price_and_leverage(self):
        cases = [
            (None, 1, 0.0),
            ({"margin_usdt": 15, "qty": 4, "entry_price": 50}, 1, 15.0),
            ({"qty": 4, "entry_price": 50, "leverage": 4}, 1, 50.0),
            ({"margin_usdt": "invalid", "qty": 4, "entry_price": 50, "leverage": "invalid"}, 2, 100.0),
            ({"qty": "invalid", "entry_price": 50}, 1, 0.0),
            ({"qty": 4, "entry_price": "invalid"}, 1, 0.0),
            ({"qty": 4, "entry_price": 50, "leverage": -2}, 1, 200.0),
        ]
        for entry, leverage, expected in cases:
            with self.subTest(entry=entry):
                self.assertEqual(expected, runtime._entry_margin_value(entry, leverage))

    def test_position_margin_arithmetic_and_maintenance_cap(self):
        cases = [
            (None, {}, (0.0, 0.0, 0.0, 0.0)),
            (
                {"isolatedMargin": 100, "marginBalance": 90, "maintMargin": 10, "unRealizedProfit": -10},
                {},
                (100.0, 90.0, 10.0, 10.0),
            ),
            (
                {"leverage": 4, "unRealizedProfit": -5, "maintMarginRate": 0.01},
                {"qty_hint": 4, "entry_price_hint": 50},
                (50.0, 45.0, 2.0, 5.0),
            ),
            (
                {"notional": -200, "leverage": 4, "unRealizedProfit": -40, "maintenanceMargin": 20},
                {},
                (50.0, 10.0, 10.0, 40.0),
            ),
            ({"isolatedWallet": 20, "unRealizedProfit": 5}, {}, (20.0, 20.0, 0.0, 0.0)),
            ({"notional": 200, "unRealizedProfit": -300}, {}, (200.0, 200.0, 0.0, 300.0)),
            (
                {
                    key: "invalid"
                    for key in (
                        "isolatedMargin",
                        "leverage",
                        "entryPrice",
                        "notional",
                        "marginBalance",
                        "isolatedWallet",
                        "unRealizedProfit",
                        "maintMargin",
                        "maintMarginRate",
                    )
                },
                {"qty_hint": 4, "entry_price_hint": 50},
                (200.0, 200.0, 0.0, 0.0),
            ),
        ]
        for position, hints, expected in cases:
            with self.subTest(position=position):
                self.assertEqual(expected, runtime._compute_position_margin_fields(position, **hints))
