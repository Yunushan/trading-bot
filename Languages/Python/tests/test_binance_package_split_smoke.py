# ruff: noqa: E402

import importlib
import sys
import threading
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges import binance as binance_pkg
from app.integrations.exchanges.binance import (
    BinanceWrapper,
    _coerce_interval_seconds,
    _normalize_connector_choice,
    normalize_margin_ratio,
)
from app.integrations.exchanges.binance.account.account_data import bind_binance_account_data as new_bind_account
from app.integrations.exchanges.binance.clients.connector_clients import (
    CcxtBinanceAdapter as NewCcxtBinanceAdapter,
)
from app.integrations.exchanges.binance.clients.sdk_coin_futures_client import (
    BinanceSDKCoinFuturesClient as new_sdk_coin_client,
)
from app.integrations.exchanges.binance.clients.sdk_spot_client import (
    BinanceSDKSpotClient as new_sdk_spot_client,
)
from app.integrations.exchanges.binance.clients.sdk_usds_futures_client import (
    BinanceSDKUsdsFuturesClient as new_sdk_usds_client,
)
from app.integrations.exchanges.binance.market.market_data import bind_binance_market_data as new_bind_market
from app.integrations.exchanges.binance.metadata.exchange_metadata import (
    bind_binance_exchange_metadata as new_bind_metadata,
)
from app.integrations.exchanges.binance.orders.futures_orders import (
    bind_binance_futures_orders as new_bind_futures_orders,
)
from app.integrations.exchanges.binance.orders.order_fallback_runtime import (
    bind_binance_order_fallback_runtime as new_bind_order_fallback,
)
from app.integrations.exchanges.binance.orders.order_sizing_runtime import (
    bind_binance_order_sizing_runtime as new_bind_order_sizing,
)
from app.integrations.exchanges.binance.positions.futures_positions import (
    close_all_futures_positions as new_close_all_futures_positions,
    bind_binance_futures_positions as new_bind_positions,
)
from app.integrations.exchanges.binance.positions import close_all_runtime as close_all_runtime_module
from app.integrations.exchanges.binance.positions.futures_fill_summary_runtime import (
    _summarize_futures_order_fills as new_summarize_futures_order_fills,
)
from app.integrations.exchanges.binance.positions.futures_position_close_runtime import (
    close_futures_position as new_close_futures_position,
)
from app.integrations.exchanges.binance.positions.futures_position_query_runtime import (
    list_open_futures_positions as new_list_open_futures_positions,
)
from app.integrations.exchanges.binance.positions.futures_positions_cache_runtime import (
    _format_quantity_for_order as new_format_quantity_for_order,
)
from app.integrations.exchanges.binance.runtime.futures_mode_runtime import (
    bind_binance_futures_mode_runtime as new_bind_futures_mode,
)
from app.integrations.exchanges.binance.runtime.futures_settings import (
    bind_binance_futures_settings as new_bind_futures_settings,
)
from app.integrations.exchanges.binance.runtime.operational_runtime import (
    bind_binance_operational_runtime as new_bind_operational,
    trigger_emergency_close_all as runtime_trigger_emergency_close_all,
)
from app.integrations.exchanges.binance.transport.helpers import (
    _coerce_interval_seconds as new_coerce_interval_seconds,
)
from app.integrations.exchanges.binance.transport.http_runtime import bind_binance_http_runtime as new_bind_http
from app.integrations.exchanges.binance.transport.rate_limit_runtime import (
    bind_binance_rate_limit_runtime as new_bind_rate_limit,
)
from app.integrations.exchanges.binance.transport.ws_runtime import bind_binance_ws_runtime as new_bind_ws


class _DummyThread:
    def __init__(self, target=None, name=None, daemon=None):
        self._target = target
        self._alive = False

    def is_alive(self):
        return self._alive

    def start(self):
        self._alive = True
        try:
            if callable(self._target):
                self._target()
        finally:
            self._alive = False


class _DummyOperationalWrapper:
    def __init__(self):
        self._emergency_closer_lock = threading.RLock()
        self._emergency_closer_thread = None
        self._emergency_close_requested = False
        self._emergency_close_info = {}
        self._network_emergency_dispatched = False
        self._network_offline_hits = 0
        self._network_offline_since = 0.0
        self.account_type = "FUTURES"
        self.logged = []

    def _log(self, message, lvl="info"):
        self.logged.append((lvl, message))


class BinancePackageSplitSmokeTests(unittest.TestCase):
    def test_public_surface_is_unchanged(self):
        self.assertIs(binance_pkg.BinanceWrapper, BinanceWrapper)
        self.assertIs(binance_pkg._coerce_interval_seconds, _coerce_interval_seconds)
        self.assertIs(binance_pkg._normalize_connector_choice, _normalize_connector_choice)
        self.assertIs(binance_pkg.normalize_margin_ratio, normalize_margin_ratio)
        self.assertEqual(_coerce_interval_seconds("5m"), 300.0)
        self.assertEqual(normalize_margin_ratio("0.5"), 50.0)
        self.assertEqual(
            _normalize_connector_choice("binance_sdk_spot"),
            "binance-sdk-spot",
        )

    def test_final_subpackages_resolve_expected_objects(self):
        self.assertTrue(callable(new_bind_account))
        self.assertTrue(callable(NewCcxtBinanceAdapter))
        self.assertTrue(callable(new_sdk_coin_client))
        self.assertTrue(callable(new_sdk_spot_client))
        self.assertTrue(callable(new_sdk_usds_client))
        self.assertTrue(callable(new_bind_market))
        self.assertTrue(callable(new_bind_metadata))
        self.assertTrue(callable(new_bind_futures_mode))
        self.assertTrue(callable(new_bind_futures_settings))
        self.assertTrue(callable(new_bind_operational))
        self.assertTrue(callable(new_close_all_futures_positions))
        self.assertTrue(callable(new_summarize_futures_order_fills))
        self.assertTrue(callable(new_format_quantity_for_order))
        self.assertTrue(callable(new_close_futures_position))
        self.assertTrue(callable(new_list_open_futures_positions))
        self.assertIs(new_coerce_interval_seconds, _coerce_interval_seconds)

    def test_removed_intermediate_binance_modules_raise_import_error(self):
        removed_modules = [
            "app.binance_wrapper",
            "app.close_all",
            "app.integrations.exchanges.binance.account_data",
            "app.integrations.exchanges.binance.connector_clients",
            "app.integrations.exchanges.binance.exchange_metadata",
            "app.integrations.exchanges.binance.futures_mode_runtime",
            "app.integrations.exchanges.binance.futures_orders",
            "app.integrations.exchanges.binance.futures_positions",
            "app.integrations.exchanges.binance.futures_settings",
            "app.integrations.exchanges.binance.http_runtime",
            "app.integrations.exchanges.binance.market_data",
            "app.integrations.exchanges.binance.operational_runtime",
            "app.integrations.exchanges.binance.order_fallback_runtime",
            "app.integrations.exchanges.binance.order_sizing_runtime",
            "app.integrations.exchanges.binance.rate_limit_runtime",
            "app.integrations.exchanges.binance.sdk_clients",
            "app.integrations.exchanges.binance.transport_helpers",
            "app.integrations.exchanges.binance.ws_runtime",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)

    def test_wrapper_wiring_still_exposes_bound_helpers(self):
        expected_methods = [
            "futures_api_ok",
            "get_klines",
            "fetch_symbols",
            "list_open_futures_positions",
            "get_balances",
            "get_futures_balance_snapshot",
            "get_total_wallet_balance",
            "place_futures_market_order",
            "place_spot_market_order",
            "get_last_price",
            "set_position_mode",
            "ensure_futures_settings",
            "trigger_emergency_close_all",
            "_futures_create_order_with_fallback",
            "_throttle_request",
            "_ws_latest_candle",
        ]
        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(BinanceWrapper, method_name))
                self.assertTrue(callable(getattr(BinanceWrapper, method_name)))

    def test_new_subpackages_expose_expected_binders(self):
        binders = [
            new_bind_http,
            new_bind_rate_limit,
            new_bind_ws,
            new_bind_futures_orders,
            new_bind_order_fallback,
            new_bind_order_sizing,
            new_bind_positions,
            new_bind_market,
            new_bind_metadata,
            new_bind_futures_mode,
            new_bind_futures_settings,
            new_bind_operational,
            new_bind_account,
        ]
        for binder in binders:
            self.assertTrue(callable(binder))

    def test_positions_close_all_delegates_via_runtime_module(self):
        sentinel = [{"ok": True, "symbol": "BTCUSDT"}]
        original = close_all_runtime_module.close_all_futures_positions
        try:
            close_all_runtime_module.close_all_futures_positions = lambda _wrapper: sentinel
            self.assertIs(new_close_all_futures_positions(object()), sentinel)
        finally:
            close_all_runtime_module.close_all_futures_positions = original

    def test_runtime_emergency_close_all_uses_runtime_close_all_path(self):
        sentinel = [{"ok": True, "symbol": "BTCUSDT"}]
        original_close_all = close_all_runtime_module.close_all_futures_positions
        original_thread = runtime_trigger_emergency_close_all.__globals__["threading"].Thread
        wrapper = _DummyOperationalWrapper()
        try:
            close_all_runtime_module.close_all_futures_positions = lambda _wrapper: sentinel
            runtime_trigger_emergency_close_all.__globals__["threading"].Thread = _DummyThread
            accepted = runtime_trigger_emergency_close_all(
                wrapper,
                reason="test",
                source="unit-test",
                max_attempts=1,
                initial_delay=0.0,
            )
            self.assertTrue(accepted)
            self.assertTrue(wrapper._emergency_close_info.get("success"))
        finally:
            close_all_runtime_module.close_all_futures_positions = original_close_all
            runtime_trigger_emergency_close_all.__globals__["threading"].Thread = original_thread


if __name__ == "__main__":
    unittest.main()
