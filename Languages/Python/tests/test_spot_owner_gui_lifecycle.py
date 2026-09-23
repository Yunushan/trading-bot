"""Offline coverage for the GUI's active Spot execution owner lifecycle."""
from __future__ import annotations

import importlib.util
import socket
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.positions.tracking_runtime import _close_all_positions_sync  # noqa: E402
from app.gui.runtime.strategy.stop_runtime import stop_strategy_sync  # noqa: E402
from app.settings.live_safety import LiveTradingSafetyError  # noqa: E402


SPOT_AUTH = {
    "mode": "Live", "account_type": "Spot", "api_key": "offline-key", "api_secret": "offline-secret",
}


def _owned_spot_wrapper():
    return SimpleNamespace(
        _spot_execution_owner=object(),
        api_key=SPOT_AUTH["api_key"],
        api_secret=SPOT_AUTH["api_secret"],
        mode=SPOT_AUTH["mode"],
        account_type="SPOT",
        close_all_spot_positions=Mock(return_value=[{"ok": True}]),
    )


def _account_runtime_without_gui_or_exchange_sdk():
    """Load the real account runtime with only its unrelated imports stubbed."""
    pyqt = ModuleType("PyQt6")
    pyqt.QtCore = SimpleNamespace()
    binance = ModuleType("app.integrations.exchanges.binance")
    binance.BinanceWrapper = object
    balance = ModuleType("app.gui.runtime.account.balance_runtime")
    balance._invalidate_balance_observation = Mock()
    path = PYTHON_ROOT / "app" / "gui" / "runtime" / "account" / "account_runtime.py"
    spec = importlib.util.spec_from_file_location("app.gui.runtime.account._owner_test_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "PyQt6": pyqt,
        "app.integrations.exchanges.binance": binance,
        "app.gui.runtime.account.balance_runtime": balance,
    }):
        spec.loader.exec_module(module)
    return module, balance


class SpotOwnerGuiLifecycleTests(unittest.TestCase):
    def setUp(self):
        # The close helper imports Futures routing even for Spot. Stub that
        # unused transport so these lifecycle tests never load an SDK.
        self.close_futures = Mock(return_value=[{"ok": True}])
        module = ModuleType("app.integrations.exchanges.binance.positions.close_all_runtime")
        module.close_all_futures_positions = self.close_futures
        self.enterContext(patch.dict(sys.modules, {module.__name__: module}))
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")))

    def test_close_all_reuses_matching_active_spot_owner(self):
        owner = _owned_spot_wrapper()
        runtime = SimpleNamespace(
            shared_binance=owner,
            _build_wrapper_from_values=Mock(side_effect=AssertionError("owner wrapper must not be replaced")),
        )

        result = _close_all_positions_sync(runtime, auth=dict(SPOT_AUTH))

        self.assertEqual([{"ok": True}], result)
        self.assertIs(owner, runtime.shared_binance)
        runtime._build_wrapper_from_values.assert_not_called()
        owner.close_all_spot_positions.assert_called_once_with()

    def test_close_all_blocks_changed_spot_auth_before_rebuild_or_close(self):
        changes = (
            {"api_key": "other-key"},
            {"api_secret": "other-secret"},
            {"mode": "Demo/Testnet"},
            {"account_type": "Margin"},
        )
        for change in changes:
            with self.subTest(change=change):
                owner = _owned_spot_wrapper()
                runtime = SimpleNamespace(shared_binance=owner, _build_wrapper_from_values=Mock())
                auth = {**SPOT_AUTH, **change}

                with self.assertRaisesRegex(LiveTradingSafetyError, "active owner credentials and account mode"):
                    _close_all_positions_sync(runtime, auth=auth)

                self.assertIs(owner, runtime.shared_binance)
                runtime._build_wrapper_from_values.assert_not_called()
                owner.close_all_spot_positions.assert_not_called()

    def test_close_all_futures_still_builds_wrapper_from_auth(self):
        owner = _owned_spot_wrapper()
        futures = SimpleNamespace(list_open_futures_positions=Mock(return_value=[]))
        auth = {**SPOT_AUTH, "account_type": "Futures"}
        builder = Mock(return_value=futures)
        runtime = SimpleNamespace(shared_binance=owner, _build_wrapper_from_values=builder)
        result = _close_all_positions_sync(runtime, auth=auth)

        self.assertEqual([{"ok": True}], result)
        builder.assert_called_once_with(auth)
        self.assertIs(futures, runtime.shared_binance)
        self.close_futures.assert_called_once_with(futures, fast=False)
        futures.list_open_futures_positions.assert_called_once_with(force_refresh=True)
        owner.close_all_spot_positions.assert_not_called()

    def test_stop_closes_with_existing_spot_owner_without_replacing_it(self):
        owner = _owned_spot_wrapper()
        builder = Mock(side_effect=AssertionError("owner wrapper must not be replaced"))
        runtime = SimpleNamespace(
            guard=None,
            strategy_engines={},
            shared_binance=owner,
            _service_request_stop=Mock(),
            _build_wrapper_from_values=builder,
            log=Mock(),
        )
        runtime._close_all_positions_blocking = lambda **kwargs: _close_all_positions_sync(runtime, **kwargs)

        result = stop_strategy_sync(runtime, auth=dict(SPOT_AUTH))

        self.assertTrue(result["ok"])
        self.assertEqual([{"ok": True}], result["close_all_result"])
        self.assertIs(owner, runtime.shared_binance)
        builder.assert_not_called()
        owner.close_all_spot_positions.assert_called_once_with()

    def test_stop_with_changed_spot_auth_reports_failure_without_replacing_owner(self):
        owner = _owned_spot_wrapper()
        builder = Mock(side_effect=AssertionError("owner wrapper must not be replaced"))
        runtime = SimpleNamespace(
            guard=None,
            strategy_engines={},
            shared_binance=owner,
            _service_request_stop=Mock(),
            _build_wrapper_from_values=builder,
            log=Mock(),
        )
        runtime._close_all_positions_blocking = lambda **kwargs: _close_all_positions_sync(runtime, **kwargs)

        result = stop_strategy_sync(runtime, auth={**SPOT_AUTH, "api_key": "other-key"})

        self.assertFalse(result["ok"])
        self.assertIn("active owner credentials and account mode", result["error"])
        self.assertIsNone(result["close_all_result"])
        self.assertIs(owner, runtime.shared_binance)
        builder.assert_not_called()
        owner.close_all_spot_positions.assert_not_called()

    def test_invalidate_revokes_owner_before_clearing_wrapper_even_if_revoke_raises(self):
        account_runtime, balance = _account_runtime_without_gui_or_exchange_sdk()
        for error in (None, RuntimeError("offline revoke failure")):
            with self.subTest(revoke_error=error):
                observations = []
                owner = _owned_spot_wrapper()
                runtime = SimpleNamespace(shared_binance=owner, balance_label=None, log=Mock())

                def revoke():
                    observations.append(runtime.shared_binance)
                    if error is not None:
                        raise error

                owner._revoke_spot_execution_owner = Mock(side_effect=revoke)

                account_runtime._invalidate_shared_binance(runtime, "credentials_changed")

                owner._revoke_spot_execution_owner.assert_called_once_with()
                self.assertEqual([owner], observations)
                self.assertIsNone(runtime.shared_binance)
                self.assertEqual("credentials_changed", runtime._shared_binance_invalidated_reason)
                self.assertEqual(1, runtime._account_observation_generation)
        self.assertEqual(2, balance._invalidate_balance_observation.call_count)


if __name__ == "__main__":
    unittest.main()
