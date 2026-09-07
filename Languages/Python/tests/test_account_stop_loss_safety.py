from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.runtime import strategy_cycle_runtime  # noqa: E402
from app.integrations.exchanges.binance.account import account_futures_runtime as account  # noqa: E402
from test_strategy_cycle_runtime import _cycle_context  # noqa: E402
from test_strategy_stop_loss_hardening import _build_stop_engine  # noqa: E402


class AccountStopLossSafetyTests(unittest.TestCase):
    def setUp(self):
        self.reset_pause()
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in safety tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.addCleanup(self.reset_pause)

    @staticmethod
    def reset_pause():
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def engine(self, *, pnl=-10.0, wallet=100.0, account_payload=None):
        engine, wrapper, logs, *_ = _build_stop_engine()
        wrapper.get_total_unrealized_pnl = Mock(return_value=pnl)
        wrapper.get_total_wallet_balance = Mock(return_value=wallet)
        if account_payload is not None:
            wrapper._get_futures_account_cached = Mock(return_value=account_payload)
            wrapper.get_total_usdt_value = Mock(return_value=1_000_000.0)
            wrapper.get_total_wallet_balance = lambda: account.get_total_wallet_balance(wrapper)
        engine._trigger_emergency_close = Mock()
        return engine, wrapper, logs

    @staticmethod
    def context(**updates):
        return {
            **_cycle_context(), "is_entire_account": True,
            "apply_usdt_limit": False, "apply_percent_limit": True,
            "stop_percent_limit": 5.0, **updates,
        }

    def assert_paused_without_close(self, engine, logs, *, field="wallet"):
        self.assertTrue(engine.stopped())
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set() or StrategyEngine._GLOBAL_PAUSE_FALLBACK)
        engine._trigger_emergency_close.assert_not_called()
        self.assertIn(f"stop-loss {field} snapshot failed", "\n".join(logs))
        self.assertNotIn("stop-loss triggered", "\n".join(logs))

    def test_real_wallet_lookup_failure_pauses_instead_of_using_spot_estimate(self):
        engine, wrapper, logs = self.engine(account_payload={})

        self.assertFalse(engine._apply_entire_account_stop_loss(ctx=self.context()))

        self.assert_paused_without_close(engine, logs)
        wrapper.get_total_usdt_value.assert_not_called()

    def test_real_wallet_transport_exception_pauses_and_redacts_logs(self):
        engine, wrapper, logs = self.engine(account_payload={})
        wrapper._get_futures_account_cached.side_effect = RuntimeError("api_key=private-unit-token")

        self.assertFalse(engine._apply_entire_account_stop_loss(ctx=self.context()))

        self.assert_paused_without_close(engine, logs)
        self.assertNotIn("private-unit-token", "\n".join(logs))

    def test_invalid_or_nonpositive_wallet_never_silently_disables_percentage_stop(self):
        for value in (None, "", "bad", {}, [], True, False, math.nan, math.inf, -math.inf, "NaN", 0, "0", -1):
            with self.subTest(wallet=value):
                self.reset_pause()
                engine, _, logs = self.engine(wallet=value)
                self.assertFalse(engine._apply_entire_account_stop_loss(ctx=self.context()))
                self.assert_paused_without_close(engine, logs)

    def test_invalid_pnl_never_becomes_zero_or_skips_the_absolute_stop(self):
        for value in (None, "", "bad", {}, [], True, False, math.nan, math.inf, -math.inf, "NaN"):
            for percent in (False, True):
                with self.subTest(pnl=value, percent=percent):
                    self.reset_pause()
                    engine, wrapper, logs = self.engine(pnl=value)
                    context = self.context(apply_usdt_limit=not percent, apply_percent_limit=percent)
                    self.assertFalse(engine._apply_entire_account_stop_loss(ctx=context))
                    self.assert_paused_without_close(engine, logs, field="PnL")
                    wrapper.get_total_wallet_balance.assert_not_called()

    def test_percentage_threshold_control_uses_authoritative_wallet(self):
        for pnl, expected in ((-10.0, True), (-5.0, True), (-4.99, False), (0.0, False), (12.0, False)):
            with self.subTest(pnl=pnl):
                engine, wrapper, logs = self.engine(pnl=pnl, account_payload={"totalWalletBalance": "100"})
                self.assertEqual(expected, engine._apply_entire_account_stop_loss(ctx=self.context()))
                self.assertEqual(expected, engine._trigger_emergency_close.called)
                self.assertFalse(engine.stopped())
                wrapper.get_total_usdt_value.assert_not_called()
                if expected:
                    self.assertIn("entire-account-percent-limit", engine._trigger_emergency_close.call_args.args[2])

    def test_absolute_stop_remains_available_without_wallet_when_it_is_triggered(self):
        engine, wrapper, _ = self.engine(pnl=-100.0)
        wrapper.get_total_wallet_balance.side_effect = RuntimeError("wallet unavailable")

        self.assertTrue(engine._apply_entire_account_stop_loss(ctx=self.context(apply_usdt_limit=True)))

        wrapper.get_total_wallet_balance.assert_not_called()
        engine._trigger_emergency_close.assert_called_once()

    def test_wallet_failure_is_not_consulted_for_absolute_only_stop(self):
        engine, wrapper, _ = self.engine(pnl=-1.0)
        wrapper.get_total_wallet_balance.side_effect = RuntimeError("wallet unavailable")

        self.assertFalse(engine._apply_entire_account_stop_loss(
            ctx=self.context(apply_usdt_limit=True, apply_percent_limit=False),
        ))

        wrapper.get_total_wallet_balance.assert_not_called()
        self.assertFalse(engine.stopped())

    def test_wallet_failure_stops_real_cycle_before_market_fetch_or_order_preparation(self):
        engine, _, logs = self.engine(account_payload={})
        engine._build_cycle_context = Mock(return_value=self.context())
        engine._fetch_cycle_market_state = Mock(return_value=None)
        engine._prepare_signal_orders = Mock()
        engine._execute_signal_order = Mock()

        strategy_cycle_runtime.run_once(engine)

        self.assert_paused_without_close(engine, logs)
        engine._fetch_cycle_market_state.assert_not_called()
        engine._prepare_signal_orders.assert_not_called()
        engine._execute_signal_order.assert_not_called()

    def test_failed_pause_event_still_blocks_cycle_via_existing_fallback(self):
        engine, _, logs = self.engine(account_payload={})
        broken_event = Mock()
        broken_event.set.side_effect = RuntimeError("synthetic event failure")
        with patch.object(StrategyEngine, "_GLOBAL_PAUSE", broken_event):
            self.assertFalse(engine._apply_entire_account_stop_loss(ctx=self.context()))
            self.assertTrue(StrategyEngine._GLOBAL_PAUSE_FALLBACK)
            self.assertTrue(engine.stopped())
        engine._trigger_emergency_close.assert_not_called()

    def test_logging_failure_cannot_prevent_pause(self):
        engine, _, _ = self.engine(account_payload={})
        engine.log = Mock(side_effect=RuntimeError("synthetic log failure"))
        self.assertFalse(engine._apply_entire_account_stop_loss(ctx=self.context()))
        self.assertTrue(engine.stopped())
        engine._trigger_emergency_close.assert_not_called()


class AuthoritativeFuturesWalletTests(unittest.TestCase):
    def owner(self, payload):
        return SimpleNamespace(
            _get_futures_account_cached=Mock(return_value=payload),
            get_total_usdt_value=Mock(return_value=1_000_000.0),
        )

    def test_wallet_preserves_real_zero_and_signed_finite_values(self):
        for value, expected in ((0, 0.0), ("0", 0.0), ("12.5", 12.5), (-1, -1.0)):
            with self.subTest(value=value):
                owner = self.owner({"totalWalletBalance": value})
                self.assertEqual(expected, account.get_total_wallet_balance(owner))
                owner.get_total_usdt_value.assert_not_called()

    def test_malformed_or_missing_total_never_uses_other_account_measures(self):
        for alternate in ("totalMarginBalance", "totalInitialMargin", "totalCrossWalletBalance", "totalCrossBalance"):
            for value in (None, "", "bad", True, False, {}, [], math.nan, math.inf, -math.inf):
                with self.subTest(alternate=alternate, value=value):
                    owner = self.owner({"totalWalletBalance": value, alternate: "10000"})
                    with self.assertRaisesRegex(RuntimeError, "wallet balance is unavailable or invalid"):
                        account.get_total_wallet_balance(owner)
                    owner.get_total_usdt_value.assert_not_called()
            with self.subTest(alternate=alternate, total="missing"):
                with self.assertRaises(RuntimeError):
                    account.get_total_wallet_balance(self.owner({alternate: "10000"}))

    def test_non_mapping_account_payload_is_unavailable(self):
        for payload in (None, [], "100", 100):
            with self.subTest(payload=payload):
                with self.assertRaises(RuntimeError):
                    account.get_total_wallet_balance(self.owner(payload))

    def test_finite_pnl_rows_cannot_overflow_into_an_unchecked_account_total(self):
        owner = SimpleNamespace(
            list_open_futures_positions=lambda: [{"unRealizedProfit": "-1e308"}] * 2,
            _get_futures_account_cached=Mock(return_value={}),
        )
        with self.assertRaisesRegex(RuntimeError, "unrealized PnL is unavailable"):
            account.get_total_unrealized_pnl(owner)
        owner._get_futures_account_cached.return_value = {"totalUnrealizedProfit": "-5.25"}
        self.assertEqual(-5.25, account.get_total_unrealized_pnl(owner))


if __name__ == "__main__":
    unittest.main()
