# ruff: noqa: E402
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import service_bridge_snapshot_runtime as bridge
from app.desktop.adapters.service_client import EmbeddedDesktopServiceClient
from app.gui.runtime import background_workers
from app.gui.runtime.account import account_runtime, balance_runtime
from app.gui.runtime.window.positions_runtime import _mw_reconfigure_positions_worker
from app.gui.runtime.window.portfolio_runtime import _update_positions_balance_labels
from app.integrations.exchanges.binance.account import account_balance_runtime as spot_account
from app.integrations.exchanges.binance.account import account_futures_runtime as futures_account
from app.service.runtime import TradingBotService


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class _DeferredWorker:
    def __init__(self, function, parent):
        self.function = function
        self.progress = _Signal()
        self.done = _Signal()

    def start(self):
        pass

    def isRunning(self):  # noqa: N802
        return True


class BalanceObservationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(background_workers, "CallWorker", _DeferredWorker))
        self.timer = self.enterContext(patch.object(balance_runtime.QtCore.QTimer, "singleShot"))
        self.enterContext(patch.object(bridge, "_ensure_service_client", side_effect=lambda owner: owner.client))

    def owner(self, account="FUTURES"):
        config = {"mode": "Live", "account_type": account, "api_key": "fixture-A", "api_secret": "fixture-secret"}
        service = TradingBotService(config=config)
        client = EmbeddedDesktopServiceClient(service_cls=lambda **kwargs: service)
        wrapper = Mock()
        wrapper.get_futures_balance_snapshot.return_value = {"total": "100", "available": "90"}
        wrapper.get_spot_balance.return_value = 90.0
        wrapper.get_total_usdt_value.return_value = 100.0
        owner = SimpleNamespace(
            config=config, service=service, client=client, wrapper=wrapper,
            api_key_edit=Mock(), api_secret_edit=Mock(), mode_combo=Mock(), account_combo=Mock(),
            connector_combo=Mock(), leverage_spin=Mock(), margin_mode_combo=Mock(),
            refresh_balance_btn=Mock(), _chart_debug_log=Mock(), log=Mock(),
            _create_binance_wrapper=lambda **kwargs: wrapper,
            _sync_service_portfolio_snapshot=lambda **kwargs: None,
            _sync_service_exchange_connector_snapshot=lambda **kwargs: None,
        )
        owner.api_key_edit.text.return_value = "fixture-A"
        owner.api_secret_edit.text.return_value = "fixture-secret"
        owner.mode_combo.currentText.return_value = "Live"
        owner.account_combo.currentText.return_value = account
        owner.connector_combo.currentData.return_value = "python-binance"
        owner.leverage_spin.value.return_value = 1
        owner.margin_mode_combo.currentText.return_value = "Isolated"
        owner.refresh_balance_btn.text.return_value = "Refresh Balance"
        owner._sync_service_account_snapshot = lambda **kwargs: bridge._sync_service_account_snapshot(owner, **kwargs)
        owner._update_positions_balance_labels = lambda *args, **kwargs: _update_positions_balance_labels(owner, *args, **kwargs)
        bridge._sync_service_config_snapshot(owner)
        owner._update_positions_balance_labels(500.0, 400.0, observed_at=datetime.now(timezone.utc).isoformat())
        return owner

    def start(self, owner):
        balance_runtime.update_balance_label(owner)
        return owner._balance_refresh_worker

    def assert_unavailable(self, owner, *, preserve=True):
        snapshot = owner.service.get_account_snapshot()
        self.assertEqual("", snapshot.generated_at)
        self.assertTrue(owner.service.get_operational_preflight()["freshness"]["account"]["stale"])
        self.assertEqual(500.0 if preserve else None, snapshot.total_balance)
        self.assertIsNone(owner._balance_refresh_token)
        owner.refresh_balance_btn.setEnabled.assert_called_with(True)

    def test_futures_invalid_observations_preserve_display_but_invalidate_freshness(self):
        invalid = [None, [], {}, {"total": 1}, {"available": 0}, {"total": 0, "available": 1}]
        for field in ("total", "available", "wallet"):
            for value in (None, "", "bad", True, False, float("nan"), float("inf"), "-Infinity", -1):
                invalid.append({"total": 100, "available": 90, field: value})
        for response in invalid:
            with self.subTest(response=response):
                owner = self.owner()
                owner.wrapper.get_futures_balance_snapshot.return_value = response
                worker = self.start(owner)
                worker.done.emit(worker.function(), None)
                self.assert_unavailable(owner)
                owner.wrapper.get_futures_balance_snapshot.assert_called_once_with(force_refresh=True)

    def test_spot_invalid_observations_do_not_fall_back_to_available_balance(self):
        for method in ("get_spot_balance", "get_total_usdt_value"):
            for value in (None, "", "bad", True, float("nan"), float("inf"), -1):
                with self.subTest(method=method, value=value):
                    owner = self.owner("SPOT")
                    getattr(owner.wrapper, method).return_value = value
                    worker = self.start(owner)
                    worker.done.emit(worker.function(), None)
                    self.assert_unavailable(owner)
        owner = self.owner("SPOT")
        owner.wrapper.get_total_usdt_value.side_effect = RuntimeError("unavailable")
        worker = self.start(owner)
        worker.done.emit(worker.function(), None)
        self.assert_unavailable(owner)

    def test_successful_zero_and_positive_observations_restore_freshness(self):
        for account in ("FUTURES", "SPOT"):
            for total, available in ((0.0, 0.0), (100.0, 0.0), (100.0, 90.0)):
                with self.subTest(account=account, total=total, available=available):
                    owner = self.owner(account)
                    balance_runtime._invalidate_balance_observation(owner)
                    owner.wrapper.get_futures_balance_snapshot.return_value = {"total": total, "available": available}
                    owner.wrapper.get_spot_balance.return_value = available
                    owner.wrapper.get_total_usdt_value.return_value = total
                    worker = self.start(owner)
                    worker.done.emit(worker.function(), None)
                    snapshot = owner.service.get_account_snapshot()
                    self.assertEqual(total, snapshot.total_balance)
                    self.assertEqual(available, snapshot.available_balance)
                    self.assertTrue(snapshot.generated_at)
                    self.assertFalse(owner.service.get_operational_preflight()["freshness"]["account"]["stale"])

    def test_late_callback_cannot_repopulate_changed_config_or_shared_wrapper(self):
        for change_back in (False, True):
            for failed in (False, True):
                with self.subTest(change_back=change_back, failed=failed):
                    owner = self.owner()
                    worker = self.start(owner)
                    result = worker.function()
                    original = dict(owner.config)
                    owner.config = dict(original, api_key="fixture-B")
                    bridge._sync_service_config_snapshot(owner)
                    if change_back:
                        owner.config = original
                        bridge._sync_service_config_snapshot(owner)
                    worker.done.emit(result, "old failure" if failed else None)
                    self.assert_unavailable(owner, preserve=False)
                    self.assertIsNone(getattr(owner, "shared_binance", None))

    def test_unsynchronized_ui_scope_changes_reject_old_completion(self):
        for field, method, value in (
            ("api_key_edit", "text", "fixture-B"), ("api_secret_edit", "text", "fixture-new-secret"),
            ("mode_combo", "currentText", "Demo/Testnet"), ("account_combo", "currentText", "SPOT"),
            ("connector_combo", "currentData", "binance-sdk-spot"),
        ):
            with self.subTest(field=field):
                owner = self.owner()
                worker = self.start(owner)
                result = worker.function()
                getattr(getattr(owner, field), method).return_value = value
                worker.done.emit(result, None)
                self.assert_unavailable(owner, preserve=False)
                self.assertIsNone(getattr(owner, "shared_binance", None))

    def test_credential_hook_immediately_invalidates_balance_without_a_refresh(self):
        owner = self.owner()
        owner.shared_binance = owner.wrapper
        owner._invalidate_shared_binance = lambda reason: account_runtime._invalidate_shared_binance(owner, reason)
        owner._reconfigure_positions_worker = lambda: _mw_reconfigure_positions_worker(owner)
        owner.api_key_edit.text.return_value = "fixture-B"
        account_runtime._on_api_credentials_changed(owner)
        snapshot = owner.service.get_account_snapshot()
        self.assertIsNone(snapshot.total_balance)
        self.assertIsNone(snapshot.available_balance)
        self.assertEqual("", snapshot.generated_at)
        self.assertTrue(owner.service.get_operational_preflight()["freshness"]["account"]["stale"])
        self.assertIsNone(owner.shared_binance)
        self.assertEqual(1, owner._account_observation_generation)

    def test_credential_hook_rejects_old_callback_after_ui_changes_back(self):
        for error in (None, "old failure"):
            with self.subTest(error=error):
                owner = self.owner()
                owner._invalidate_shared_binance = lambda reason: account_runtime._invalidate_shared_binance(owner, reason)
                owner._reconfigure_positions_worker = lambda: _mw_reconfigure_positions_worker(owner)
                worker = self.start(owner)
                old = worker.function()
                for key in ("fixture-B", "fixture-A"):
                    owner.api_key_edit.text.return_value = key
                    account_runtime._on_api_credentials_changed(owner)
                    self.assertEqual("", owner.service.get_account_snapshot().generated_at)
                worker.done.emit(old, error)
                self.assert_unavailable(owner, preserve=False)
                self.assertIsNone(getattr(owner, "shared_binance", None))
                self.assertEqual(2, owner._account_observation_generation)
                fresh = self.start(owner)
                fresh.done.emit(fresh.function(), None)
                self.assertEqual(100.0, owner.service.get_account_snapshot().total_balance)
                self.assertFalse(owner.service.get_operational_preflight()["freshness"]["account"]["stale"])

    def test_superseded_refresh_cannot_overwrite_or_invalidate_new_observation(self):
        for error in (None, "late failure"):
            with self.subTest(error=error):
                owner = self.owner()
                first = self.start(owner)
                old = first.function()
                second = self.start(owner)
                owner.wrapper.get_futures_balance_snapshot.return_value = {"total": 700, "available": 600}
                second.done.emit(second.function(), None)
                expected = owner.service.get_account_snapshot()
                first.done.emit(old, error)
                self.assertEqual(expected, owner.service.get_account_snapshot())

    def test_timeout_invalidates_freshness_and_late_completion_cannot_restore_it(self):
        owner = self.owner()
        worker = self.start(owner)
        result = worker.function()
        self.timer.call_args.args[1]()
        self.assert_unavailable(owner)
        worker.done.emit(result, None)
        self.assert_unavailable(owner)

    def test_real_spot_normalization_failure_reaches_desktop_unavailability(self):
        owner = self.owner("SPOT")
        owner.wrapper._spot_account_dict.return_value = {"balances": [{"asset": "USDT", "free": "bad", "locked": 0}]}
        owner.wrapper.get_spot_balance.side_effect = lambda asset: spot_account.get_spot_balance(owner.wrapper, asset)
        worker = self.start(owner)
        worker.done.emit(worker.function(), None)
        self.assert_unavailable(owner)


class BinanceBalanceObservationTests(unittest.TestCase):
    def test_spot_adapter_rejects_whole_malformed_snapshot(self):
        good = {"asset": "USDT", "free": "10", "locked": "0"}
        invalid = [None, {}, {"balances": None}, {"balances": {}}, {"balances": [None]}, {"balances": [good, good]}]
        for field, values in (
            ("asset", (None, "", "-", "Unknown", 1, "B TC")),
            ("free", (None, "", "bad", True, float("nan"), float("inf"), -1)),
            ("locked", (None, "", "bad", False, float("nan"), float("inf"), -1)),
        ):
            for value in values:
                invalid.append({"balances": [good, {"asset": "BTC", "free": 1, "locked": 0, field: value}]})
        invalid.append({"balances": [{"asset": "BTC", "free": 1e308, "locked": 1e308}]})
        for payload in invalid:
            for method in (spot_account.get_spot_balance, spot_account.get_balances):
                with self.subTest(payload=payload, method=method.__name__):
                    wrapper = SimpleNamespace(account_type="SPOT", _spot_account_dict=Mock(return_value=payload))
                    with self.assertRaises(RuntimeError):
                        method(wrapper)

    def test_explicit_empty_and_zero_spot_balances_are_valid(self):
        for rows in ([], [{"asset": "USDT", "free": "0", "locked": "0"}]):
            with self.subTest(rows=rows):
                wrapper = SimpleNamespace(account_type="SPOT", _spot_account_dict=Mock(return_value={"balances": rows}))
                self.assertEqual(0.0, spot_account.get_spot_balance(wrapper))
                self.assertEqual([], spot_account.get_balances(wrapper))

    def test_spot_total_does_not_convert_failed_authoritative_read_to_zero(self):
        wrapper = SimpleNamespace(account_type="SPOT", get_spot_balance=Mock(side_effect=RuntimeError("unavailable")))
        with self.assertRaises(RuntimeError):
            futures_account.get_total_usdt_value(wrapper, force_refresh=True)

    def test_incomplete_futures_balance_never_pads_missing_fields_with_zero(self):
        for row in (
            {"asset": "USDT", "availableBalance": "10"},
            {"asset": "USDT", "walletBalance": "10"},
            {"asset": "USDT", "availableBalance": True, "walletBalance": "10"},
        ):
            with self.subTest(row=row):
                wrapper = SimpleNamespace(
                    api_key="fixture", api_secret="fixture", _sync_futures_time_offset=Mock(),
                    _get_futures_account_balance_cached=Mock(return_value=[row]),
                    _get_futures_account_cached=Mock(return_value={}),
                )
                with self.assertRaisesRegex(RuntimeError, "incomplete balance"):
                    futures_account.get_futures_balance_snapshot(wrapper, force_refresh=True)

    def test_futures_explicit_zero_is_a_complete_observation(self):
        wrapper = SimpleNamespace(
            api_key="fixture", api_secret="fixture", _sync_futures_time_offset=Mock(),
            _get_futures_account_balance_cached=Mock(return_value=[
                {"asset": "USDT", "availableBalance": "0", "walletBalance": "0"},
            ]),
            _get_futures_account_cached=Mock(return_value={}),
        )
        result = futures_account.get_futures_balance_snapshot(wrapper, force_refresh=True)
        self.assertEqual({"asset": "USDT", "total": 0.0, "wallet": 0.0, "available": 0.0}, result)


if __name__ == "__main__":
    unittest.main()
