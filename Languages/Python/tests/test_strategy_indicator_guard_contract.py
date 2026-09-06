from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions import strategy_indicator_guard as runtime  # noqa: E402
from app.core.strategy.orders import strategy_signal_order_collect_runtime as collect_runtime  # noqa: E402


class IndicatorGuardContractTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        config = build_default_config()
        config.update(symbol="BTCUSDT", interval="1m", account_type="FUTURES")
        self.logs = []
        self.engine = StrategyEngine(object(), config, log_callback=self.logs.append)

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def confirm(self, timestamp, action="buy", *, symbol="BTCUSDT", interval="1m"):
        return self.engine._indicator_signal_confirmation_ready(
            symbol,
            interval,
            "rsi",
            action,
            60.0,
            timestamp,
        )

    def test_confirmation_counts_distinct_bars_not_repeated_poll_iterations(self):
        self.engine._indicator_flip_confirm_bars = 3
        self.assertFalse(self.confirm(1_000.0))
        for timestamp in (1_000.0, 1_001.0, 1_019.0):
            with self.subTest(timestamp=timestamp):
                self.assertFalse(self.confirm(timestamp))
        self.assertFalse(self.confirm(1_060.0))
        self.assertFalse(self.confirm(1_061.0))
        self.assertTrue(self.confirm(1_120.0))
        self.assertTrue(self.confirm(1_121.0))

    def test_confirmation_direction_gap_and_scope_reset_are_independent(self):
        self.engine._indicator_flip_confirm_bars = 3
        self.assertFalse(self.confirm(1_000.0))
        self.assertFalse(self.confirm(1_060.0))
        self.assertFalse(self.confirm(1_120.0, "sell"))
        self.assertFalse(self.confirm(1_180.0, "sell"))
        self.assertTrue(self.confirm(1_240.0, "sell"))
        self.assertFalse(self.confirm(1_541.0, "sell"))
        self.assertFalse(self.confirm(1_601.0, "sell", symbol="ETHUSDT"))
        self.assertFalse(self.confirm(1_601.0, "sell", interval="5m"))

    def test_confirmation_rejects_older_or_invalid_observations_without_advancing(self):
        engine = self.engine
        engine._indicator_flip_confirm_bars = 3
        self.assertFalse(self.confirm(1_000.0))
        self.assertFalse(self.confirm(1_060.0))
        key = ("BTCUSDT", "1m", "rsi")
        before = dict(engine._indicator_signal_tracker[key])
        self.assertFalse(self.confirm(900.0))
        self.assertEqual(before, engine._indicator_signal_tracker[key])
        for timestamp in (None, "invalid", -1, 0, float("nan"), float("inf")):
            with self.subTest(timestamp=timestamp):
                self.assertFalse(self.confirm(timestamp))
                self.assertEqual(before, engine._indicator_signal_tracker[key])
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertTrue(engine._ledger_reconciliation_required)

    def test_order_collection_uses_candle_identity_not_wall_time_or_fallback_attempts(self):
        engine = self.engine
        engine._indicator_flip_confirm_bars = 3
        engine._indicator_live_qty_total = Mock(return_value=0.0)
        engine._recent_indicator_close = Mock(return_value=None)
        engine._indicator_cooldown_remaining = Mock(return_value=0.0)
        engine._reentry_block_remaining = Mock(return_value=0.0)
        engine._indicator_signal_confirmation_ready = Mock(wraps=engine._indicator_signal_confirmation_ready)
        request = {"indicator_key": "rsi", "side": "BUY", "qty": 1.0}
        with patch.object(collect_runtime, "_build_directional_indicator_order_request", return_value=request) as build:
            with patch.object(collect_runtime, "_build_fallback_indicator_order_request") as fallback:
                for wall_time, bar_time, expected in (
                    (2_000.0, 1_000, []),
                    (2_600.0, 1_000, []),
                    (2_601.0, 1_060, []),
                    (2_602.0, 1_120, [request]),
                ):
                    with self.subTest(bar_time=bar_time, wall_time=wall_time):
                        with patch.object(collect_runtime.time, "time", return_value=wall_time):
                            actual, tolerance = engine._collect_indicator_order_requests(
                                cw=engine.config,
                                trigger_actions={"RSI": "buy"},
                                dual_side=False,
                                account_type="FUTURES",
                                allow_opposite_enabled=False,
                                hedge_overlap_allowed=False,
                                now_ts=wall_time,
                                current_bar_marker=bar_time * 1_000_000_000,
                            )
                        self.assertEqual(expected, actual)
                        self.assertGreater(tolerance, 0.0)
                        candidates = engine._build_signal_order_candidates(
                            cw=engine.config,
                            indicator_order_requests=actual,
                            signal="buy",
                            signal_timestamp=wall_time,
                            trigger_sources=["RSI"],
                            trigger_desc="RSI -> BUY",
                            trigger_actions={"RSI": "buy"},
                            trigger_segments=["RSI -> BUY"],
                        )
                        self.assertEqual(len(expected), len(candidates))
                build.assert_called_once()
                fallback.assert_not_called()
        timestamps = [call.args[-1] for call in engine._indicator_signal_confirmation_ready.call_args_list]
        self.assertEqual([1_000.0] * 4 + [1_060.0] * 2 + [1_120.0], timestamps)

    def test_generic_fallback_cannot_override_an_actionable_indicator_rejection(self):
        engine = self.engine
        for confirmations in (1, 3):
            engine._indicator_flip_confirm_bars = confirmations
            with self.subTest(confirmations=confirmations):
                candidates = engine._build_signal_order_candidates(
                    cw=engine.config,
                    indicator_order_requests=[],
                    signal="buy",
                    signal_timestamp=1_000.0,
                    trigger_sources=["RSI"],
                    trigger_desc="RSI -> BUY",
                    trigger_actions={"RSI": "buy"},
                    trigger_segments=["RSI -> BUY"],
                )
                self.assertEqual([], candidates)
        candidates = engine._build_signal_order_candidates(
            cw=engine.config,
            indicator_order_requests=[],
            signal="sell",
            signal_timestamp=1_000.0,
            trigger_sources=[],
            trigger_desc="combined signal",
            trigger_actions={},
            trigger_segments=[],
        )
        self.assertEqual(1, len(candidates))
        self.assertEqual("SELL", candidates[0]["side"])

    def test_hold_uses_larger_seconds_or_bar_window_and_explicit_override(self):
        engine = self.engine
        engine._indicator_min_hold_seconds = 30.0
        engine._indicator_min_hold_bars = 2
        self.assertFalse(engine._indicator_hold_ready(1_000, "BTCUSDT", "1m", "RSI", "BUY", 60, 1_119))
        self.assertTrue(engine._indicator_hold_ready(1_000, "BTCUSDT", "1m", "RSI", "BUY", 60, 1_120))
        engine.config["allow_close_ignoring_hold"] = False
        self.assertFalse(
            engine._indicator_hold_ready(1_000, "BTCUSDT", "1m", "RSI", "BUY", 60, 1_001, ignore_hold=True)
        )
        engine.config["allow_close_ignoring_hold"] = True
        self.assertTrue(engine._indicator_hold_ready(1_000, "BTCUSDT", "1m", "RSI", "BUY", 60, 1_001, ignore_hold=True))
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertTrue(any("hold guard: waiting" in message for message in self.logs))

    def test_missing_hold_timestamp_and_invalid_interval_block(self):
        self.engine._indicator_min_hold_seconds = 30.0
        self.assertFalse(self.engine._indicator_hold_ready(None, "BTCUSDT", "1m", "rsi", "BUY", 60, 1_000))
        self.assertTrue(self.engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertFalse(self.engine._indicator_hold_ready(900, "BTCUSDT", "1m", "rsi", "BUY", "invalid", 1_000))

    def test_indicator_close_matches_ownership_and_requires_multi_indicator_opt_in(self):
        engine = self.engine
        engine.config["allow_multi_indicator_close"] = False
        self.assertFalse(engine._indicator_entry_matches_close({}, "rsi"))
        self.assertFalse(engine._indicator_entry_matches_close({"trigger_indicators": ["MACD"]}, "rsi"))
        self.assertTrue(engine._indicator_entry_matches_close({"trigger_indicators": ["RSI"]}, "rsi"))
        multi = {"trigger_indicators": ["RSI", "MACD"]}
        self.assertFalse(engine._indicator_entry_matches_close(multi, "rsi"))
        self.assertTrue(engine._indicator_entry_matches_close(multi, "rsi", allow_multi_override=True))
        engine.config["allow_multi_indicator_close"] = True
        self.assertTrue(engine._indicator_entry_matches_close(multi, "rsi"))

    def test_reentry_cooldown_is_scoped_and_expires_at_boundary(self):
        engine = self.engine
        engine._indicator_reentry_cooldown_seconds = 30.0
        engine._indicator_reentry_cooldown_bars = 2
        with patch.object(runtime.time, "time", return_value=1_000.0):
            engine._record_reentry_block("btcusdt", "1M", "LONG")
            self.assertEqual(120.0, engine._reentry_block_remaining("BTCUSDT", "1m", "BUY"))
        self.assertEqual(0.0, engine._reentry_block_remaining("ETHUSDT", "1m", "BUY", now_ts=1_000))
        self.assertEqual(0.0, engine._reentry_block_remaining("BTCUSDT", "5m", "BUY", now_ts=1_000))
        self.assertEqual(0.0, engine._reentry_block_remaining("BTCUSDT", "1m", "SELL", now_ts=1_000))
        self.assertEqual(1.0, engine._reentry_block_remaining("BTCUSDT", "1m", "BUY", now_ts=1_119))
        self.assertEqual(0.0, engine._reentry_block_remaining("BTCUSDT", "1m", "BUY", now_ts=1_120))
        self.assertEqual({}, engine._reentry_blocks)

    def test_signal_reset_blocks_are_removed_only_when_the_matching_signal_changes(self):
        engine = self.engine
        engine._indicator_reentry_requires_reset = True
        entry = {"trigger_indicators": ["RSI", "MACD"]}
        engine._mark_indicator_reentry_signal_block("btcusdt", "1M", entry, "LONG")
        engine._mark_indicator_reentry_signal_block("ETHUSDT", "1m", entry, "BUY")
        engine._mark_indicator_reentry_signal_block("BTCUSDT", "5m", entry, "BUY")
        engine._refresh_indicator_reentry_signal_blocks("BTCUSDT", "1m", {"RSI": "BUY", "MACD": "SELL"})
        self.assertEqual("BUY", engine._indicator_reentry_signal_blocks[("BTCUSDT", "1m", "rsi")])
        self.assertNotIn(("BTCUSDT", "1m", "macd"), engine._indicator_reentry_signal_blocks)
        self.assertIn(("BTCUSDT", "5m", "macd"), engine._indicator_reentry_signal_blocks)
        self.assertIn(("ETHUSDT", "1m", "macd"), engine._indicator_reentry_signal_blocks)
        engine._refresh_indicator_reentry_signal_blocks("BTCUSDT", "1m", {})
        self.assertNotIn(("BTCUSDT", "1m", "rsi"), engine._indicator_reentry_signal_blocks)

    def test_recent_close_window_and_side_are_not_shared(self):
        engine = self.engine
        engine._record_indicator_close("btcusdt", "1M", "RSI", "LONG", 2.5, ts=1_000)
        with patch.object(runtime.time, "time", return_value=1_090.0):
            info = engine._recent_indicator_close("BTCUSDT", "1m", "rsi", "BUY")
            self.assertEqual({"ts": 1_000.0, "qty": 2.5}, info)
            self.assertIsNone(engine._recent_indicator_close("BTCUSDT", "1m", "rsi", "SELL"))
        with patch.object(runtime.time, "time", return_value=1_090.01):
            self.assertIsNone(engine._recent_indicator_close("BTCUSDT", "1m", "rsi", "BUY"))
        self.assertEqual({}, engine._indicator_recent_closes)

    def test_guard_close_preserves_context_and_cooldown_and_pauses_on_write_failure(self):
        engine = self.engine
        engine._indicator_reentry_cooldown_seconds = 30.0
        engine.guard = Mock()
        engine.guard.context_key_from_entry.return_value = "rsi:owned"
        with patch.object(runtime.time, "time", return_value=1_000.0):
            engine._mark_guard_closed("BTCUSDT", "1m", "LONG", {"context_key": "fallback"})
        engine.guard.mark_closed.assert_called_once_with("BTCUSDT", "1m", "BUY", context="rsi:owned")
        self.assertGreater(engine._reentry_block_remaining("BTCUSDT", "1m", "BUY", now_ts=1_000), 0)
        engine.guard.context_key_from_entry.side_effect = RuntimeError("fixture resolver unavailable")
        engine.guard.mark_closed.reset_mock()
        engine._mark_guard_closed("BTCUSDT", "1m", "SELL", {"context_key": "fallback"})
        engine.guard.mark_closed.assert_called_once_with("BTCUSDT", "1m", "SELL", context="fallback")
        engine.guard.mark_closed.side_effect = RuntimeError("fixture persistence unavailable")
        engine._guard_mark_leg_closed(("BTCUSDT", "1m", "BUY"))
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_close_guard_nested_lifetime_and_opposite_side_exclusion(self):
        engine = self.engine
        engine.config["allow_opposite_positions"] = False
        self.assertIsNone(engine._describe_close_guard("BTCUSDT"))
        self.assertTrue(engine._enter_close_guard("btcusdt", "LONG", "stop-loss"))
        self.assertTrue(engine._enter_close_guard("BTCUSDT", "BUY", "nested"))
        self.assertEqual({"side": "BUY", "label": "stop-loss"}, engine._describe_close_guard("BTCUSDT"))
        self.assertFalse(engine._enter_close_guard("BTCUSDT", "SELL"))
        engine._exit_close_guard("BTCUSDT", "BUY")
        self.assertFalse(engine._enter_close_guard("BTCUSDT", "SELL"))
        engine._exit_close_guard("BTCUSDT", "BUY")
        self.assertIsNone(engine._describe_close_guard("BTCUSDT"))
        self.assertTrue(engine._enter_close_guard("BTCUSDT", "SELL"))
        engine.config["allow_opposite_positions"] = True
        self.assertTrue(engine._enter_close_guard("BTCUSDT", "BUY"))
        engine._exit_close_guard("BTCUSDT", "BUY")
        engine._exit_close_guard("BTCUSDT", "SELL")
        self.assertEqual({}, engine._close_inflight)

    def test_flip_cooldown_applies_to_direction_change_and_uses_larger_window(self):
        engine = self.engine
        engine._indicator_flip_cooldown_seconds = 30.0
        engine._indicator_flip_cooldown_bars = 2
        engine._indicator_last_action[("BTCUSDT", "1m", "rsi")] = {"side": "BUY", "ts": 1_000.0}
        self.assertEqual(0.0, engine._indicator_cooldown_remaining("BTCUSDT", "1m", "RSI", "BUY", 60, 1_001))
        self.assertEqual(119.0, engine._indicator_cooldown_remaining("BTCUSDT", "1m", "RSI", "SELL", 60, 1_001))
        self.assertEqual(0.0, engine._indicator_cooldown_remaining("BTCUSDT", "1m", "RSI", "SELL", 60, 1_120))
        self.assertEqual(0.0, engine._indicator_cooldown_remaining("ETHUSDT", "1m", "RSI", "SELL", 60, 1_001))
