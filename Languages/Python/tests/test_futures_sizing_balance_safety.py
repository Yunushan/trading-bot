from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.strategy import StrategyEngine
from app.integrations.exchanges.binance.account import account_futures_runtime as account
from test_fake_exchange_integration import (
    _FakeExchangeWrapper, _build_engine as integration_engine, _signal_order_kwargs,
)
from test_strategy_runtime_behavior import _FakeStrategyBinance, _build_engine


class FuturesSizingBalanceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.spacing = StrategyEngine._ORDER_MIN_SPACING
        StrategyEngine._ORDER_MIN_SPACING = 0.0
        self._reset_runtime()
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in test"))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        StrategyEngine._ORDER_MIN_SPACING = self.spacing
        self._reset_runtime()

    def _reset_runtime(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def margin(self, engine, snapshot, **overrides):
        aborted = Mock()
        kwargs = dict(
            cw={"symbol": "BTCUSDT", "interval": "1m"}, side="BUY", pct=0.1,
            free_usdt=1_000_000.0, price=100.0, futures_balance_snap=snapshot,
            flip_close_qty=0.0, entries_side_all=[], active_slot_tokens_all=set(),
            existing_margin_indicator_total=0.0, slot_label="rsi", slot_token_for_order="rsi",
            lev=5, abort_guard=aborted,
        )
        kwargs.update(overrides)
        return engine._prepare_signal_order_margin_state(**kwargs), aborted

    def test_unknown_balance_pauses_and_never_uses_an_estimate(self):
        bad_snapshots = [None, [], {}, {"total": 1000}]
        for field in ("available", "wallet"):
            for value in (None, "", "invalid", True, False, {}, [], float("nan"), float("inf"), -float("inf")):
                bad_snapshots.append({"available": 1000, "wallet": 1000, field: value})
        for snapshot in bad_snapshots:
            with self.subTest(snapshot=snapshot):
                self._reset_runtime()
                wrapper = _FakeStrategyBinance()
                wrapper.get_futures_balance_snapshot = Mock(return_value=snapshot)
                wrapper.get_total_usdt_value = Mock(return_value=1_000_000.0)
                wrapper.get_total_wallet_balance = Mock(return_value=1_000_000.0)
                wrapper.get_futures_balance_usdt = Mock(return_value=1_000_000.0)
                engine = _build_engine(wrapper=wrapper)
                state = engine._resolve_signal_order_account_state(cw=engine.config, last_price=100)
                self.assertTrue(state["aborted"])
                self.assertTrue(engine.stopped())
                wrapper.get_futures_balance_snapshot.assert_called_once_with(force_refresh=True)
                result, aborted = self.margin(engine, snapshot)
                self.assertTrue(result["aborted"])
                aborted.assert_called_once_with()
                wrapper.get_total_usdt_value.assert_not_called()
                wrapper.get_total_wallet_balance.assert_not_called()
                wrapper.get_futures_balance_usdt.assert_not_called()

    def test_snapshot_transport_failure_redacts_and_pauses(self):
        logs = []
        wrapper = _FakeStrategyBinance()
        wrapper.get_futures_balance_snapshot = Mock(side_effect=RuntimeError("api_key=private-fixture-token"))
        engine = _build_engine(wrapper=wrapper, logs=logs)
        result = engine._resolve_signal_order_account_state(cw=engine.config, last_price=100)
        self.assertTrue(result["aborted"])
        self.assertTrue(engine.stopped())
        self.assertTrue(logs)
        self.assertNotIn("private-fixture-token", "\n".join(logs))

    def test_missing_snapshot_method_does_not_fall_back(self):
        wrapper = SimpleNamespace(account_type="FUTURES", get_total_usdt_value=Mock(return_value=1000))
        engine = _build_engine(wrapper=wrapper)
        self.assertTrue(engine._resolve_signal_order_account_state(cw=engine.config, last_price=100)["aborted"])
        wrapper.get_total_usdt_value.assert_not_called()
        self.assertTrue(engine.stopped())

    def test_known_nonpositive_funds_block_without_being_replaced_or_marked_unknown(self):
        for snapshot in (
            {"available": 0, "wallet": 1000}, {"available": -10, "wallet": 1000},
            {"available": 100, "wallet": 0}, {"available": 100, "wallet": -10},
        ):
            with self.subTest(snapshot=snapshot):
                engine = _build_engine()
                result, aborted = self.margin(engine, snapshot)
                self.assertTrue(result["aborted"])
                aborted.assert_called_once_with()
                self.assertFalse(engine.stopped())

    def test_available_funds_are_not_wallet_or_aggregate_total(self):
        wrapper = _FakeStrategyBinance()
        wrapper.get_futures_balance_snapshot = Mock(return_value={"available": "80", "wallet": "100", "total": 99999})
        engine = _build_engine(wrapper=wrapper)
        result = engine._resolve_signal_order_account_state(cw=engine.config, last_price=100)
        self.assertFalse(result["aborted"])
        self.assertEqual(80, result["free_usdt"])
        self.assertEqual(100, result["futures_balance_snap"]["wallet"])

    def test_wallet_allocation_never_adds_local_margin_or_spot_estimates(self):
        engine = _build_engine()
        engine._leg_ledger = {("OTHERUSDT", "1m", "BUY"): {"margin_usdt": 9000}}
        for available in (700, 1200):
            with self.subTest(available=available):
                result, aborted = self.margin(engine, {"available": available, "wallet": 1000})
                self.assertFalse(result["aborted"])
                self.assertEqual(5, result["qty_est"])
                aborted.assert_not_called()

    def test_no_five_percent_overdraft_tolerance(self):
        engine = _build_engine()
        for available, allowed in ((96, False), (99.99, False), (100, True), (101, True)):
            with self.subTest(available=available):
                result, aborted = self.margin(engine, {"available": available, "wallet": 1000})
                self.assertEqual(not allowed, result["aborted"])
                self.assertEqual(not allowed, aborted.called)

    def test_filter_rounding_cannot_exceed_available_funds(self):
        wrapper = _FakeStrategyBinance()
        wrapper.adjust_qty_to_filters_futures = Mock(return_value=(5.1, None))
        engine = _build_engine(wrapper=wrapper)
        result, aborted = self.margin(engine, {"available": 101, "wallet": 1000})
        self.assertTrue(result["aborted"])
        aborted.assert_called_once_with()

    def test_real_execute_path_releases_guard_on_failed_snapshot_and_recovers_explicitly(self):
        logs, trades = [], []
        wrapper = _FakeExchangeWrapper()
        wrapper.api_key = "synthetic-key"
        wrapper.api_secret = "synthetic-secret"
        wrapper._sync_futures_time_offset = Mock()
        wrapper._get_futures_account_balance_cached = Mock(return_value=[])
        wrapper._get_futures_account_cached = Mock(return_value={})
        wrapper.get_futures_balance_snapshot = lambda **kwargs: account.get_futures_balance_snapshot(wrapper, **kwargs)
        wrapper.get_total_usdt_value = Mock(return_value=1_000_000)
        engine = integration_engine(wrapper=wrapper, logs=logs, trades=trades)
        kwargs = _signal_order_kwargs(engine, side="BUY", price=100, marker=81001)
        with patch.object(engine, "_abort_signal_order_guard", wraps=engine._abort_signal_order_guard) as abort, \
             patch.object(engine, "_submit_futures_signal_order", wraps=engine._submit_futures_signal_order) as submit:
            engine._execute_signal_order(**kwargs)
            self.assertTrue(engine.stopped())
            self.assertEqual([], wrapper.orders)
            self.assertEqual([], trades)
            submit.assert_not_called()
            abort.assert_called_once()
            wrapper.get_total_usdt_value.assert_not_called()
            wrapper._get_futures_account_balance_cached.assert_called_once_with(force_refresh=True)
            wrapper._get_futures_account_cached.assert_called_once_with(force_refresh=True)
            wrapper._get_futures_account_cached.return_value = {"availableBalance": "600", "totalWalletBalance": "1000"}
            self.assertTrue(StrategyEngine.resume_trading())
            engine._execute_signal_order(**kwargs)
            self.assertEqual(1, len(wrapper.orders), logs)
            self.assertEqual(12.5, wrapper.orders[0]["quantity"])
            submit.assert_called_once()

    def test_failed_logging_does_not_prevent_pause_and_guard_release(self):
        wrapper = _FakeExchangeWrapper()
        wrapper.get_futures_balance_snapshot = Mock(side_effect=RuntimeError("unavailable"))
        engine = integration_engine(wrapper=wrapper, logs=[], trades=[])
        with patch.object(engine, "log", side_effect=RuntimeError("log failed")), \
             patch.object(engine, "_abort_signal_order_guard", wraps=engine._abort_signal_order_guard) as abort:
            engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100, marker=81002))
            abort.assert_called_once()
            self.assertTrue(engine.stopped())
            self.assertEqual([], wrapper.orders)


class FuturesBalanceSnapshotCoherenceTests(unittest.TestCase):
    def snapshot(self, rows, payload):
        wrapper = SimpleNamespace(
            api_key="fixture", api_secret="fixture", _sync_futures_time_offset=Mock(),
            _get_futures_account_balance_cached=Mock(return_value=rows),
            _get_futures_account_cached=Mock(return_value=payload),
        )
        return account.get_futures_balance_snapshot(wrapper, force_refresh=True)

    def test_complete_documented_balance_row(self):
        for key in ("balance", "walletBalance"):
            with self.subTest(key=key):
                result = self.snapshot([{"asset": "USDT", "availableBalance": "80", key: "100"}], {})
                self.assertEqual({"asset": "USDT", "available": 80, "wallet": 100, "total": 100}, result)

    def test_partial_responses_cannot_be_combined(self):
        for rows, payload in (
            ([{"asset": "USDT", "availableBalance": 500}], {"totalWalletBalance": 100}),
            ([{"asset": "USDT", "walletBalance": 500}], {"availableBalance": 80}),
            ([], {"availableBalance": 500, "assets": [{"asset": "USDT", "walletBalance": 100}]}),
            ([], {"totalWalletBalance": 500, "assets": [{"asset": "USDT", "availableBalance": 80}]}),
            ([], {"assets": [{"asset": "USDT", "availableBalance": 500}, {"asset": "BUSD", "walletBalance": 100}]}),
        ):
            with self.subTest(rows=rows, payload=payload), self.assertRaises(RuntimeError):
                self.snapshot(rows, payload)

    def test_complete_fallback_replaces_entire_pair_and_preserves_its_unit(self):
        for multi, unit in ((False, "USDT"), (True, "USD")):
            with self.subTest(multi=multi):
                result = self.snapshot([{"asset": "BUSD", "availableBalance": 500}], {
                    "availableBalance": "80", "totalWalletBalance": "100", "multiAssetsMargin": multi,
                })
                self.assertEqual({"asset": unit, "available": 80, "wallet": 100, "total": 100}, result)

    def test_complete_asset_fallback_replaces_entire_pair(self):
        result = self.snapshot([{"asset": "USDT", "availableBalance": 500}], {
            "totalWalletBalance": 99999,
            "assets": [{"asset": "BUSD", "availableBalance": "80", "walletBalance": "100"}],
        })
        self.assertEqual({"asset": "BUSD", "available": 80, "wallet": 100, "total": 100}, result)

    def test_margin_cross_and_withdrawable_balances_are_not_substitutes(self):
        for field in ("availableBalance", "walletBalance"):
            for invalid in (None, True, "bad", "NaN", "inf"):
                row = {"asset": "USDT", "availableBalance": 80, "walletBalance": 100,
                       "marginBalance": 9999, "crossWalletBalance": 9999, "maxWithdrawAmount": 9999, field: invalid}
                payload = {"totalMarginBalance": 9999, "totalCrossWalletBalance": 9999, "maxWithdrawAmount": 9999}
                with self.subTest(field=field, invalid=invalid), self.assertRaises(RuntimeError):
                    self.snapshot([row], payload)

    def test_duplicate_asset_rows_cannot_select_an_arbitrary_balance(self):
        rows = [{"asset": "USDT", "availableBalance": 80, "walletBalance": 100},
                {"asset": "USDT", "availableBalance": 800, "walletBalance": 1000}]
        for balances, payload in ((rows, {}), ([], {"assets": rows})):
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                self.snapshot(balances, payload)


if __name__ == "__main__":
    unittest.main()
