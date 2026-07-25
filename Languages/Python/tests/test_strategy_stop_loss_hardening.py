from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.runtime.strategy_cycle_risk_stop_cumulative_runtime import (  # noqa: E402
    apply_cumulative_futures_stop_management,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_directional_runtime import (  # noqa: E402
    _apply_long_futures_stop,
    _apply_short_futures_stop,
)


class _CloseWrapper:
    account_type = "FUTURES"

    def __init__(self) -> None:
        self.close_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def close_futures_leg_exact(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))
        return {"ok": True, "executedQty": "1", "avgPrice": "95"}


def _build_stop_engine(*, log_callback=None):
    wrapper = _CloseWrapper()
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    logs: list[str] = []
    engine = StrategyEngine(wrapper, config, log_callback=log_callback or logs.append)
    removed: list[tuple[object, ...]] = []
    guarded: list[tuple[object, ...]] = []
    notifications: list[tuple[tuple[object, ...], dict[str, object]]] = []
    engine._compute_position_margin_fields = lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0)
    engine._build_close_event_payload = lambda *_args, **_kwargs: {"qty": 1.0}
    engine._leg_entries = lambda _key: []
    engine._remove_leg_entry = lambda *args: removed.append(args)
    engine._mark_guard_closed = lambda *args, **kwargs: guarded.append((args, kwargs))
    engine._log_latency_metric = lambda *_args, **_kwargs: None
    engine._notify_interval_closed = lambda *args, **kwargs: notifications.append((args, kwargs))
    return engine, wrapper, logs, removed, guarded, notifications


class StrategyStopLossHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    @staticmethod
    def _long_position_state():
        return {
            "load_positions_cache": lambda: [
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "BOTH",
                    "positionAmt": "1",
                    "entryPrice": "100",
                    "isolatedWallet": "100",
                }
            ]
        }

    def test_completed_directional_stops_emit_one_reason_without_duplicate_keyword_failure(self):
        cases = (
            (_apply_long_futures_stop, "BUY", "stop_loss_long", 100.0, 90.0, "SELL"),
            (_apply_short_futures_stop, "SELL", "stop_loss_short", 100.0, 110.0, "BUY"),
        )

        for function, side, reason, entry_price, last_price, close_side in cases:
            with self.subTest(side=side):
                engine, wrapper, logs, removed, guarded, notifications = _build_stop_engine()
                common = {
                    "cw": {"symbol": "BTCUSDT", "interval": "1m"},
                    "dual_side": False,
                    "apply_usdt_limit": True,
                    "apply_percent_limit": False,
                    "stop_usdt_limit": 5.0,
                    "stop_percent_limit": 0.0,
                    "last_price": last_price,
                }
                if side == "BUY":
                    function(
                        engine,
                        key_long=("BTCUSDT", "1m", "BUY"),
                        qty_long=1.0,
                        entry_price_long=entry_price,
                        pos_long={},
                        pos_long_qty_total=1.0,
                        **common,
                    )
                else:
                    function(
                        engine,
                        key_short=("BTCUSDT", "1m", "SELL"),
                        qty_short=1.0,
                        entry_price_short=entry_price,
                        pos_short={},
                        pos_short_qty_total=1.0,
                        **common,
                    )

                self.assertEqual(1, len(wrapper.close_calls))
                self.assertEqual(close_side, wrapper.close_calls[0][1]["side"])
                self.assertEqual(1, len(removed))
                self.assertEqual(1, len(guarded))
                self.assertEqual(1, len(notifications))
                self.assertEqual(reason, notifications[0][1]["reason"])
                self.assertIn("latency_seconds", notifications[0][1])
                self.assertNotIn("close error", "\n".join(logs).lower())

    def test_log_callback_failure_does_not_interrupt_successful_stop_reconciliation(self):
        def fail_log(_message):
            raise RuntimeError("log callback failed")

        engine, _wrapper, _logs, removed, guarded, notifications = _build_stop_engine(
            log_callback=fail_log
        )

        with self.assertLogs(
            "app.core.strategy.runtime.strategy_cycle_risk_stop_directional_runtime",
            level="ERROR",
        ):
            _apply_long_futures_stop(
                engine,
                cw={"symbol": "BTCUSDT", "interval": "1m"},
                dual_side=False,
                key_long=("BTCUSDT", "1m", "BUY"),
                qty_long=1.0,
                entry_price_long=100.0,
                pos_long={},
                pos_long_qty_total=1.0,
                apply_usdt_limit=True,
                apply_percent_limit=False,
                stop_usdt_limit=5.0,
                stop_percent_limit=0.0,
                last_price=90.0,
            )

        self.assertEqual(1, len(removed))
        self.assertEqual(1, len(guarded))
        self.assertEqual(1, len(notifications))

    def test_indicator_bookkeeping_failure_is_reported_but_close_state_is_reconciled(self):
        engine, _wrapper, logs, removed, guarded, notifications = _build_stop_engine()
        engine._leg_entries = lambda _key: [{"qty": 1.0}]

        def fail_reentry(*_args, **_kwargs):
            raise RuntimeError("reentry state failed")

        engine._mark_indicator_reentry_signal_block = fail_reentry

        _apply_short_futures_stop(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            dual_side=False,
            key_short=("BTCUSDT", "1m", "SELL"),
            qty_short=1.0,
            entry_price_short=100.0,
            pos_short={},
            pos_short_qty_total=1.0,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            last_price=110.0,
        )

        self.assertEqual(1, len(removed))
        self.assertEqual(1, len(guarded))
        self.assertEqual(1, len(notifications))
        self.assertIn("Failed to prepare SELL stop-loss", "\n".join(logs))

    def test_completed_cumulative_stop_emits_reason_and_reconciles_local_state(self):
        engine, wrapper, logs, removed, guarded, notifications = _build_stop_engine()
        engine._leg_ledger[("BTCUSDT", "1m", "BUY")] = {"entries": []}

        triggered = apply_cumulative_futures_stop_management(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            last_price=90.0,
            dual_side=False,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            state=self._long_position_state(),
        )

        self.assertTrue(triggered)
        self.assertEqual(1, len(wrapper.close_calls))
        self.assertEqual(1, len(removed))
        self.assertEqual(1, len(guarded))
        self.assertEqual(1, len(notifications))
        self.assertEqual("cumulative_stop_loss", notifications[0][1]["reason"])
        self.assertNotIn("close error", "\n".join(logs).lower())

    def test_cumulative_close_uses_minimal_event_when_metadata_builder_fails(self):
        engine, _wrapper, logs, _removed, guarded, notifications = _build_stop_engine()

        def fail_payload(*_args, **_kwargs):
            raise RuntimeError("metadata failed")

        engine._build_close_event_payload = fail_payload

        triggered = apply_cumulative_futures_stop_management(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            last_price=90.0,
            dual_side=False,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            state=self._long_position_state(),
        )

        self.assertTrue(triggered)
        self.assertEqual(1, len(guarded))
        self.assertEqual(1, len(notifications))
        self.assertEqual(1.0, notifications[0][1]["qty"])
        self.assertEqual("cumulative_stop_loss", notifications[0][1]["reason"])
        self.assertIn("using minimal payload", "\n".join(logs))

    def test_confirmed_per_trade_close_uses_minimal_event_when_metadata_fails(self):
        engine, _wrapper, logs, removed, guarded, notifications = _build_stop_engine()
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 1.0
        engine._mark_indicator_reentry_signal_block = lambda *_args, **_kwargs: None
        engine._extract_indicator_keys = lambda _entry: []

        def fail_payload(*_args, **_kwargs):
            raise RuntimeError("metadata failed")

        engine._build_close_event_payload = fail_payload
        entry = {"qty": 1.0, "entry_price": 100.0, "ledger_id": "ledger-1"}

        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            entry,
            "BUY",
            "SELL",
            None,
            loss_usdt=10.0,
            price_pct=10.0,
            margin_pct=50.0,
            queue_flip=False,
        )

        self.assertEqual(1.0, closed_qty)
        self.assertEqual(1, len(removed))
        self.assertEqual(1, len(guarded))
        self.assertEqual(1, len(notifications))
        self.assertEqual(1.0, notifications[0][1]["qty"])
        self.assertEqual("per_trade_stop_loss", notifications[0][1]["reason"])
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("close metadata failed", "\n".join(logs))

    def test_confirmed_close_state_failure_returns_executed_qty_and_pauses(self):
        engine, _wrapper, logs, _removed, _guarded, notifications = _build_stop_engine()
        engine._current_futures_position_qty = lambda *_args, **_kwargs: 1.0

        def fail_remove(*_args, **_kwargs):
            raise RuntimeError("ledger removal failed")

        engine._remove_leg_entry = fail_remove
        entry = {"qty": 1.0, "entry_price": 100.0, "ledger_id": "ledger-1"}

        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            entry,
            "BUY",
            "SELL",
            None,
            loss_usdt=10.0,
            price_pct=10.0,
            margin_pct=50.0,
            queue_flip=False,
        )

        self.assertEqual(1.0, closed_qty)
        self.assertEqual(1, len(notifications))
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("could not reconcile local state", "\n".join(logs))

    def test_entire_account_snapshot_failure_pauses_instead_of_disabling_stop_silently(self):
        engine, wrapper, logs, _removed, _guarded, _notifications = _build_stop_engine()

        def fail_pnl_snapshot():
            raise RuntimeError("account snapshot unavailable")

        wrapper.get_total_unrealized_pnl = fail_pnl_snapshot

        triggered = engine._apply_entire_account_stop_loss(
            ctx={
                "cw": {"symbol": "BTCUSDT", "interval": "1m"},
                "account_type": "FUTURES",
                "is_entire_account": True,
                "apply_usdt_limit": True,
                "apply_percent_limit": False,
                "stop_usdt_limit": 5.0,
                "stop_percent_limit": 0.0,
            }
        )

        self.assertFalse(triggered)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertIn("PnL snapshot failed", "\n".join(logs))


if __name__ == "__main__":
    unittest.main()
