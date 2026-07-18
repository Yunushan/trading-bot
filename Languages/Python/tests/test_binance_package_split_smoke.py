# ruff: noqa: E402

import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges import binance as binance_pkg
from app.native_parity import ORDER_GUARD_BEHAVIOR
from app.integrations.exchanges.binance import (
    BinanceWrapper,
    MAX_FUTURES_LEVERAGE,
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
    _place_futures_market_order_STRICT as new_place_futures_market_order_strict,
    bind_binance_futures_orders as new_bind_futures_orders,
    place_futures_market_order as new_place_futures_market_order,
)
from app.integrations.exchanges.binance.orders.order_audit_runtime import (
    bind_binance_order_audit_runtime as new_bind_order_audit,
)
from app.integrations.exchanges.binance.orders import order_audit_runtime as order_audit_runtime_module
from app.integrations.exchanges.binance.orders.order_fallback_runtime import (
    bind_binance_order_fallback_runtime as new_bind_order_fallback,
)
from app.integrations.exchanges.binance.orders.order_intent_runtime import (
    bind_binance_order_intent_runtime as new_bind_order_intent,
)
from app.integrations.exchanges.binance.orders.order_sizing_runtime import (
    adjust_qty_to_filters_futures as new_adjust_qty_to_filters_futures,
    bind_binance_order_sizing_runtime as new_bind_order_sizing,
)
from app.integrations.exchanges.binance.orders.order_submit_guard_runtime import (
    bind_binance_order_submit_guard_runtime as new_bind_order_submit_guard,
)
from app.integrations.exchanges.binance.positions.futures_positions import (
    close_all_futures_positions as new_close_all_futures_positions,
    bind_binance_futures_positions as new_bind_positions,
)
from app.integrations.exchanges.binance.positions import close_all_runtime as close_all_runtime_module
from app.integrations.exchanges.binance.positions.futures_fill_summary_runtime import (
    _convert_asset_to_usdt as new_convert_asset_to_usdt,
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
from app.integrations.exchanges.binance.transport import http_request_runtime as http_request_runtime_module
from app.integrations.exchanges.binance.transport.http_runtime import bind_binance_http_runtime as new_bind_http
from app.integrations.exchanges.binance.transport.rate_limit_runtime import (
    bind_binance_rate_limit_runtime as new_bind_rate_limit,
)
from app.integrations.exchanges.binance.transport.ws_runtime import bind_binance_ws_runtime as new_bind_ws
from app.jsonl_rotation import jsonl_backup_path
from app.settings import LiveTradingSafetyError
from app.settings.exchange_limits import BINANCE_MAX_FUTURES_LEVERAGE
from app.settings import live_safety as live_safety_module
from app.settings import validation as validation_module


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


_DEFAULT_SPOT_ORDER_RESPONSE = object()


class _SpotSizingClient:
    def __init__(self, response=_DEFAULT_SPOT_ORDER_RESPONSE):
        self.orders = []
        self.response = response

    def create_order(self, **kwargs):
        self.orders.append(dict(kwargs))
        if self.response is not _DEFAULT_SPOT_ORDER_RESPONSE:
            return self.response
        return {"orderId": 1, **kwargs}


class _SpotSizingWrapper:
    def __init__(self, *, price=100.0, filters=None, order_response=_DEFAULT_SPOT_ORDER_RESPONSE):
        self.account_type = "SPOT"
        self.client = _SpotSizingClient(response=order_response)
        self._price = float(price)
        self._filters = dict(
            filters
            or {
                "stepSize": 0.001,
                "minQty": 0.001,
                "minNotional": 5.0,
            }
        )

    def get_last_price(self, _symbol):
        return self._price

    def get_spot_symbol_filters(self, _symbol):
        return dict(self._filters)


class _FuturesFillSummaryClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def futures_account_trades(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self._responses.pop(0) if self._responses else []


class _FuturesFillSummaryWrapper:
    def __init__(self, responses, prices=None):
        self.client = _FuturesFillSummaryClient(responses)
        self.prices = dict(prices or {})
        self.throttled_paths = []

    def _throttle_request(self, path):
        self.throttled_paths.append(path)

    def get_last_price(self, symbol):
        return self.prices.get(symbol, 0.0)

    def _convert_asset_to_usdt(self, amount, asset):
        return new_convert_asset_to_usdt(self, amount, asset)


class _FuturesAuditClient:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.orders = []

    def futures_create_order(self, **kwargs):
        self.orders.append(dict(kwargs))
        if self.fail:
            raise RuntimeError("exchange rejected")
        return {"orderId": 99, "status": "FILLED", **kwargs}


class _FuturesAuditWrapper:
    def __init__(self, *, fail=False):
        self.mode = "Live"
        self.account_type = "FUTURES"
        self._connector_backend = "unit-test"
        self.client = _FuturesAuditClient(fail=fail)
        self.warned = []
        self._test_order_state_dir = tempfile.TemporaryDirectory()
        self._configure_order_audit(path=Path(self._test_order_state_dir.name) / "futures-orders.jsonl")

    def _log(self, message, lvl="info"):
        self.warned.append((lvl, message))

    def _testnet_order_fallback_client(self):
        return None


class _GuardedFuturesAuditWrapper(_FuturesAuditWrapper):
    def __init__(self, *, fail=False, live_safety_config=None, price=100.0, filters=None):
        super().__init__(fail=fail)
        self.api_key = "unit-live-api-key"
        self.api_secret = "unit-live-api-secret"
        self._default_leverage = 1
        self.futures_leverage = 1
        self._default_margin_mode = "ISOLATED"
        self._live_safety_config = dict(live_safety_config or {})
        self._price = float(price)
        self._filters = dict(
            filters
            or {
                "stepSize": 0.001,
                "minQty": 0.001,
                "tickSize": 0.01,
                "minNotional": 5.0,
            }
        )

    def get_last_price(self, _symbol):
        return self._price

    def get_futures_symbol_filters(self, _symbol):
        return dict(self._filters)


class _FakeDirectHttpResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers = dict(headers or {})

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _DirectFuturesHttpWrapper:
    _limiter_lock = threading.Lock()
    _limiter_pool = {}
    _ban_state_lock = threading.Lock()
    _ban_until_epoch = {}
    _instance_counter = 0

    def __init__(self):
        type(self)._instance_counter += 1
        self.api_key = "unit-api-key"
        self.api_secret = "unit-api-secret"
        self.mode = "Demo/Testnet"
        self.account_type = "FUTURES"
        self.recv_window = 5000
        self._connector_backend = "unit-test"
        self._limiter_key = f"unit-test:{type(self)._instance_counter}"
        self._request_limiter = None
        self._last_futures_http_error = None
        self._futures_time_offset_ms = 0
        self._futures_time_offset_ts = 1.0
        self.offline = []
        self.recovered = 0
        self.synced_time = 0
        self.logged = []

    def _log(self, message, lvl="info"):
        self.logged.append((lvl, message))

    def _sync_futures_time_offset(self, *, force=False):
        self.synced_time += 1

    def _handle_network_offline(self, context, exc):
        self.offline.append((context, str(exc)))

    def _handle_network_recovered(self):
        self.recovered += 1


class _GuardedSpotSizingWrapper(_SpotSizingWrapper):
    def __init__(self, *, price=100.0, filters=None, live_safety_config=None):
        super().__init__(price=price, filters=filters)
        self.mode = "Live"
        self.api_key = "unit-live-api-key"
        self.api_secret = "unit-live-api-secret"
        self._connector_backend = "unit-test"
        self._live_safety_config = dict(live_safety_config or {})


class _FlexFuturesOrderWrapper:
    def __init__(self, *, mode="Demo/Testnet", live_safety_config=None):
        self.mode = mode
        self.account_type = "FUTURES"
        self._connector_backend = "unit-test"
        self._live_safety_config = dict(live_safety_config or {})
        self._default_leverage = 1
        self._futures_leverage = 1
        self._default_margin_mode = "ISOLATED"
        self.submit_calls = []

    def get_last_price(self, _symbol):
        return 100.0

    def clamp_futures_leverage(self, _symbol, requested):
        return int(requested or 1)

    def _ensure_margin_and_leverage_or_block(self, *_args, **_kwargs):
        return None

    def get_futures_symbol_filters(self, _symbol):
        return {"stepSize": 0.001, "minQty": 0.001, "minNotional": 5.0}

    def get_futures_dual_side(self):
        return False

    def get_futures_balance_usdt(self):
        return 10.0

    def _format_quantity_for_order(self, qty, _step):
        return f"{float(qty):.3f}"

    def _futures_create_order_with_fallback(self, params):
        self.submit_calls.append(dict(params))
        return {"orderId": 123, **params}, "primary"

    def _invalidate_futures_positions_cache(self):
        return None


class _BaseFuturesExposureWrapper:
    def __init__(self, *, mode="Live"):
        self.mode = mode
        self.account_type = "FUTURES"
        self._futures_leverage = 1
        self._default_margin_mode = "ISOLATED"
        self.logged = []

    def _ensure_margin_and_leverage_or_block(self, *_args, **_kwargs):
        return None

    def get_last_price(self, _symbol):
        return 100.0

    def get_futures_symbol_filters(self, _symbol):
        return {"stepSize": 0.001, "minQty": 0.001, "minNotional": 5.0}

    def get_futures_available_balance(self):
        return 100.0

    def list_open_futures_positions(self):
        raise RuntimeError("positions endpoint unavailable")

    def required_percent_for_symbol(self, _symbol, _leverage):
        return 1.0

    def _log(self, message, lvl="info"):
        self.logged.append((lvl, message))


def _live_ack_config(**overrides):
    config = {
        "live_trading_enabled": True,
        "live_trading_acknowledgement": live_safety_module.LIVE_TRADING_ACKNOWLEDGEMENT,
        "position_pct": 2.0,
        "live_trading_max_leverage": 20,
        "live_trading_max_position_pct": 10.0,
        "order_audit_enabled": True,
    }
    config.update(overrides)
    return config


new_bind_order_audit(_SpotSizingWrapper)
new_bind_order_sizing(_SpotSizingWrapper)
new_bind_order_audit(_FuturesAuditWrapper)
new_bind_order_intent(_FuturesAuditWrapper)
new_bind_order_fallback(_FuturesAuditWrapper)
new_bind_order_submit_guard(_GuardedSpotSizingWrapper)
new_bind_order_submit_guard(_GuardedFuturesAuditWrapper)
new_bind_futures_orders(_FlexFuturesOrderWrapper)
new_bind_order_audit(_DirectFuturesHttpWrapper)
new_bind_http(_DirectFuturesHttpWrapper)
new_bind_rate_limit(_DirectFuturesHttpWrapper)


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

    def test_binance_futures_leverage_limit_is_shared_across_runtime_layers(self):
        self.assertEqual(125, BINANCE_MAX_FUTURES_LEVERAGE)
        self.assertEqual(BINANCE_MAX_FUTURES_LEVERAGE, validation_module.BINANCE_MAX_FUTURES_LEVERAGE)
        self.assertEqual(BINANCE_MAX_FUTURES_LEVERAGE, live_safety_module.BINANCE_MAX_FUTURES_LEVERAGE)
        self.assertEqual(BINANCE_MAX_FUTURES_LEVERAGE, MAX_FUTURES_LEVERAGE)
        self.assertEqual(BINANCE_MAX_FUTURES_LEVERAGE, BinanceWrapper._max_futures_leverage_constant)

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

    def test_futures_fill_summary_aggregates_weighted_price_and_converted_commissions(self):
        wrapper = _FuturesFillSummaryWrapper(
            [
                [
                    {
                        "qty": "0.5",
                        "price": "100",
                        "realizedPnl": "2.5",
                        "commission": "0.01",
                        "commissionAsset": "USDT",
                    },
                    {
                        "qty": "0.5",
                        "price": "110",
                        "realizedPnl": "-0.5",
                        "commission": "0.002",
                        "commissionAsset": "BNB",
                    },
                ]
            ],
            prices={"BNBUSDT": 600.0},
        )

        summary = new_summarize_futures_order_fills(wrapper, "btcusdt", "42", delay=0.0)

        self.assertEqual(42, summary["order_id"])
        self.assertEqual(2, summary["trade_count"])
        self.assertAlmostEqual(1.0, summary["filled_qty"])
        self.assertAlmostEqual(105.0, summary["avg_price"])
        self.assertAlmostEqual(2.0, summary["realized_pnl"])
        self.assertEqual({"USDT": 0.01, "BNB": 0.002}, summary["commission_breakdown"])
        self.assertAlmostEqual(1.21, summary["commission_usdt"])
        self.assertAlmostEqual(0.79, summary["net_realized"])
        self.assertEqual(["/fapi/v1/userTrades"], wrapper.throttled_paths)
        self.assertEqual(
            [{"symbol": "BTCUSDT", "orderId": 42, "limit": 100}],
            wrapper.client.calls,
        )

    def test_futures_fill_summary_retries_empty_response_and_ignores_nonfinite_exchange_values(self):
        wrapper = _FuturesFillSummaryWrapper(
            [
                [],
                [
                    {
                        "qty": "nan",
                        "price": "inf",
                        "realizedPnl": "nan",
                        "commission": "inf",
                        "commissionAsset": "BNB",
                    },
                    {
                        "qty": "0.25",
                        "price": "200",
                        "realizedPnl": "-1.0",
                        "commission": "0.5",
                        "commissionAsset": "USDT",
                    },
                ],
            ]
        )

        with mock.patch("app.integrations.exchanges.binance.positions.futures_fill_summary_runtime.time.sleep"):
            summary = new_summarize_futures_order_fills(wrapper, "BTCUSDT", 99, attempts=2, delay=0.2)

        self.assertEqual(2, len(wrapper.client.calls))
        self.assertEqual(2, len(wrapper.throttled_paths))
        self.assertEqual(2, summary["trade_count"])
        self.assertAlmostEqual(0.25, summary["filled_qty"])
        self.assertAlmostEqual(200.0, summary["avg_price"])
        self.assertAlmostEqual(-1.0, summary["realized_pnl"])
        self.assertEqual({"BNB": 0.0, "USDT": 0.5}, summary["commission_breakdown"])
        self.assertAlmostEqual(0.5, summary["commission_usdt"])
        self.assertAlmostEqual(-1.5, summary["net_realized"])
        self.assertEqual({}, new_summarize_futures_order_fills(wrapper, "", 99))
        self.assertEqual({}, new_summarize_futures_order_fills(wrapper, "BTCUSDT", "not-an-order"))

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
            "get_connector_health_snapshot",
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

    def test_binance_wrapper_blocks_live_mode_without_safety_confirmation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LiveTradingSafetyError):
                BinanceWrapper("key", "secret", mode="Live", account_type="Futures")

    def test_spot_market_order_writes_append_only_audit_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "orders.jsonl"
            wrapper = _SpotSizingWrapper(price=100.0)
            wrapper._configure_order_audit(path=audit_path)

            result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.001)

            self.assertTrue(result["ok"])
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["order_intent", "order_accepted"], [row["event"] for row in rows])
            self.assertEqual("BTCUSDT", rows[0]["symbol"])
            self.assertEqual("BUY", rows[0]["side"])
            self.assertEqual("spot", rows[0]["market"])
            self.assertEqual(1, rows[1]["order_id"])

    def test_spot_market_order_rejects_empty_error_and_malformed_acknowledgements(self):
        cases = (
            (None, "empty response"),
            ({}, "empty response"),
            ({"code": -2010, "msg": "insufficient balance"}, "code=-2010"),
            ({"success": False, "message": "denied"}, "denied"),
            ({"status": "REJECTED", "message": "denied"}, "status=REJECTED"),
            ({"status": "NEW"}, "no order identifier"),
            ("accepted", "malformed response"),
        )
        for response, message in cases:
            with self.subTest(response=response):
                wrapper = _SpotSizingWrapper(order_response=response)
                result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1)

                self.assertFalse(result["ok"])
                self.assertIn(message, result["error"])
                self.assertEqual(1, len(wrapper.client.orders))

    def test_futures_exchange_submit_writes_response_and_error_audit_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "futures.jsonl"
            wrapper = _FuturesAuditWrapper()
            wrapper._configure_order_audit(path=audit_path)

            order, via = wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"}
            )

            self.assertEqual("primary", via)
            self.assertEqual(99, order["orderId"])
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["exchange_order_request", "exchange_order_response"], [row["event"] for row in rows])
            self.assertEqual("ETHUSDT", rows[1]["symbol"])
            self.assertEqual(99, rows[1]["order_id"])
            request_id = rows[0]["params"]["newClientOrderId"]
            self.assertRegex(request_id, r"^tb-[0-9a-f]{32}$")
            self.assertEqual(request_id, wrapper.client.orders[0]["newClientOrderId"])

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "futures-error.jsonl"
            wrapper = _FuturesAuditWrapper(fail=True)
            wrapper._configure_order_audit(path=audit_path)

            with self.assertRaisesRegex(RuntimeError, "exchange rejected"):
                wrapper._futures_create_order_with_fallback(
                    {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"}
                )

            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["exchange_order_request", "exchange_order_error"], [row["event"] for row in rows])
            self.assertIn("exchange rejected", rows[1]["error"])

    def test_futures_exchange_submit_rejects_malformed_or_unidentified_acknowledgements(self):
        cases = (
            (None, "empty response"),
            ("accepted", "malformed response"),
            ([{"status": "NEW"}], "malformed response"),
            ({}, "response has no order identifier"),
            ({"status": "NEW"}, "response has no order identifier"),
        )
        for response, message in cases:
            with self.subTest(response=response):
                with tempfile.TemporaryDirectory() as tmp:
                    wrapper = _FuturesAuditWrapper()
                    wrapper._configure_order_audit(path=Path(tmp) / "malformed-futures.jsonl")
                    wrapper.client.futures_create_order = lambda **_kwargs: response

                    with self.assertRaisesRegex(RuntimeError, message):
                        wrapper._futures_create_order_with_fallback(
                            {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"}
                        )

    def test_futures_order_intents_block_ambiguous_recovery_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "futures.jsonl"
            wrapper = _FuturesAuditWrapper()
            wrapper._configure_order_audit(path=audit_path)
            params = {
                "symbol": "ETHUSDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "0.1",
                "newClientOrderId": "tb-idempotency-test",
            }

            wrapper._futures_create_order_with_fallback(params)
            status = wrapper.get_order_intent_status()
            self.assertEqual(1, status["intent_count"])
            self.assertEqual(0, status["unresolved_count"])
            with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
                wrapper._futures_create_order_with_fallback(params)
            self.assertEqual(1, len(wrapper.client.orders))

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "futures-ambiguous.jsonl"
            wrapper = _FuturesAuditWrapper(fail=True)
            wrapper._configure_order_audit(path=audit_path)
            with self.assertRaisesRegex(RuntimeError, "exchange rejected"):
                wrapper._futures_create_order_with_fallback(
                    {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
                )

            status = wrapper.get_order_intent_status()
            self.assertEqual(1, status["unresolved_count"])
            self.assertRegex(status["unresolved_client_order_ids"][0], r"^tb-[0-9a-f]{32}$")
            wrapper.client.fail = False
            with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
                wrapper._futures_create_order_with_fallback(
                    {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
                )
            self.assertEqual(1, len(wrapper.client.orders))
            client_order_id = status["unresolved_client_order_ids"][0]
            wrapper._query_order_intent_exchange = lambda _record: {
                "orderId": 100,
                "status": "FILLED",
                "clientOrderId": client_order_id,
            }
            reconciled = wrapper.reconcile_order_intent(client_order_id)
            self.assertTrue(reconciled["reconciled"])
            self.assertEqual("accepted", reconciled["state"])
            self.assertEqual(0, wrapper.get_order_intent_status()["unresolved_count"])
            wrapper._futures_create_order_with_fallback(
                {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
            )
            self.assertEqual(2, len(wrapper.client.orders))

    def test_live_futures_submit_guard_blocks_unconfirmed_submit_before_client_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "guarded-futures.jsonl"
            wrapper = _GuardedFuturesAuditWrapper(live_safety_config={})
            wrapper._configure_order_audit(path=audit_path)

            with self.assertRaisesRegex(LiveTradingSafetyError, "Live order submit blocked"):
                wrapper._futures_create_order_with_fallback(
                    {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"}
                )

            self.assertEqual([], wrapper.client.orders)
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["exchange_order_request", "live_order_blocked", "exchange_order_error"], [r["event"] for r in rows])

    def test_close_all_submit_path_keeps_live_order_guard_before_client_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "close-all-guarded-futures.jsonl"
            wrapper = _GuardedFuturesAuditWrapper(live_safety_config={})
            wrapper._configure_order_audit(path=audit_path)

            with self.assertRaisesRegex(LiveTradingSafetyError, "Live order submit blocked"):
                close_all_runtime_module._submit_futures_order(
                    wrapper,
                    {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"},
                )

            self.assertEqual([], wrapper.client.orders)
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                ["exchange_order_request", "live_order_blocked", "exchange_order_error"],
                [row["event"] for row in rows],
            )

    def test_live_order_block_audit_failure_is_logged(self):
        wrapper = _GuardedFuturesAuditWrapper(live_safety_config={})

        def fail_audit(*_args, **_kwargs):
            raise OSError("audit disk full")

        wrapper._audit_order_event = fail_audit

        with self.assertRaisesRegex(LiveTradingSafetyError, "Live order submit blocked"):
            wrapper._guard_live_order_submit(
                market="futures",
                params={"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"},
                source="unit-test",
            )

        self.assertTrue(any("audit disk full" in message for _level, message in wrapper.warned))

    def test_live_futures_submit_guard_allows_confirmed_submit(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "guarded-futures-ok.jsonl"
            wrapper = _GuardedFuturesAuditWrapper(live_safety_config=_live_ack_config())
            wrapper._configure_order_audit(path=audit_path)

            order, via = wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
            )

            self.assertEqual("primary", via)
            self.assertEqual(99, order["orderId"])
            self.assertEqual(1, len(wrapper.client.orders))
            self.assertEqual("ETHUSDT", wrapper.client.orders[0]["symbol"])
            self.assertEqual("BUY", wrapper.client.orders[0]["side"])
            self.assertEqual("0.1", wrapper.client.orders[0]["quantity"])
            self.assertRegex(wrapper.client.orders[0]["newClientOrderId"], r"^tb-[0-9a-f]{32}$")

    def test_demo_futures_submit_guard_validates_order_without_live_credentials_or_session_count(self):
        self.assertTrue(ORDER_GUARD_BEHAVIOR["validate_intent_all_modes"])
        self.assertTrue(ORDER_GUARD_BEHAVIOR["validate_exchange_filters_all_modes"])
        self.assertTrue(ORDER_GUARD_BEHAVIOR["validate_connector_health_all_modes"])
        self.assertTrue(ORDER_GUARD_BEHAVIOR["validate_audit_enabled_all_modes"])
        self.assertTrue(ORDER_GUARD_BEHAVIOR["validate_audit_writable_all_modes"])
        wrapper = _GuardedFuturesAuditWrapper(live_safety_config={})
        wrapper.mode = "Demo/Testnet"

        with self.assertRaisesRegex(LiveTradingSafetyError, "order symbol is required"):
            wrapper._guard_live_order_submit(
                market="futures",
                params={"symbol": "", "side": "HOLD", "type": "STOP_MARKET", "quantity": "0.1"},
                source="demo-unit-test",
            )

        wrapper._guard_live_order_submit(
            market="futures",
            params={"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"},
            source="demo-unit-test",
        )
        self.assertEqual(0, getattr(wrapper, "_live_order_submit_attempt_count", 0))

    def test_live_futures_submit_guard_blocks_after_session_order_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "guarded-futures-session-cap.jsonl"
            wrapper = _GuardedFuturesAuditWrapper(
                live_safety_config=_live_ack_config(live_trading_max_session_orders=1)
            )
            wrapper._configure_order_audit(path=audit_path)

            first, via = wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
            )
            with self.assertRaisesRegex(LiveTradingSafetyError, "live session order cap 1 reached"):
                wrapper._futures_create_order_with_fallback(
                    {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1"}
                )

            self.assertEqual("primary", via)
            self.assertEqual(99, first["orderId"])
            self.assertEqual(1, len(wrapper.client.orders))
            self.assertEqual("ETHUSDT", wrapper.client.orders[0]["symbol"])
            self.assertEqual("BUY", wrapper.client.orders[0]["side"])
            self.assertEqual("0.1", wrapper.client.orders[0]["quantity"])
            self.assertRegex(wrapper.client.orders[0]["newClientOrderId"], r"^tb-[0-9a-f]{32}$")
            rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(
                [
                    "exchange_order_request",
                    "exchange_order_response",
                    "exchange_order_request",
                    "live_order_blocked",
                    "exchange_order_error",
                ],
                [row["event"] for row in rows],
            )

    def test_live_futures_submit_guard_blocks_filter_invalid_order(self):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(),
            price=100.0,
            filters={"stepSize": 0.01, "minQty": 0.01, "tickSize": 0.01, "minNotional": 20.0},
        )

        with self.assertRaisesRegex(LiveTradingSafetyError, "minNotional"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.10"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_non_finite_order_numbers(self):
        wrapper = _GuardedFuturesAuditWrapper(live_safety_config=_live_ack_config())

        with self.assertRaisesRegex(LiveTradingSafetyError, "quantity must be a finite number"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "NaN"}
            )
        with self.assertRaisesRegex(LiveTradingSafetyError, "price must be a finite number"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "LIMIT", "quantity": "0.10", "price": "Infinity"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_non_finite_exchange_filters(self):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(),
            filters={"stepSize": "NaN", "minQty": 0.01, "tickSize": 0.01, "minNotional": 5.0},
        )

        with self.assertRaisesRegex(LiveTradingSafetyError, "stepSize must be a finite number"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.10"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_step_misaligned_order(self):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(),
            filters={"stepSize": 0.01, "minQty": 0.01, "tickSize": 0.01, "minNotional": 5.0},
        )

        with self.assertRaisesRegex(LiveTradingSafetyError, "stepSize"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.105"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_limit_price_tick_misalignment(self):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(),
            filters={"stepSize": 0.01, "minQty": 0.01, "tickSize": 0.01, "minNotional": 5.0},
        )

        with self.assertRaisesRegex(LiveTradingSafetyError, "tickSize"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "LIMIT", "quantity": "0.10", "price": "100.005"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_malformed_order_intent(self):
        wrapper = _GuardedFuturesAuditWrapper(live_safety_config=_live_ack_config())

        with self.assertRaisesRegex(LiveTradingSafetyError, "order symbol is required"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "", "side": "HOLD", "type": "STOP_MARKET", "quantity": "0.10"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_blocks_unavailable_symbol_filters(self):
        wrapper = _GuardedFuturesAuditWrapper(live_safety_config=_live_ack_config())

        def fail_filters(_symbol):
            raise RuntimeError("metadata offline")

        wrapper.get_futures_symbol_filters = fail_filters

        with self.assertRaisesRegex(LiveTradingSafetyError, "symbol filters unavailable"):
            wrapper._futures_create_order_with_fallback(
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.10"}
            )

        self.assertEqual([], wrapper.client.orders)

    def test_live_futures_submit_guard_allows_reduce_only_below_entry_notional(self):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(),
            price=100.0,
            filters={"stepSize": 0.01, "minQty": 0.01, "tickSize": 0.01, "minNotional": 20.0},
        )

        order, via = wrapper._futures_create_order_with_fallback(
            {"symbol": "ETHUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.10", "reduceOnly": True}
        )

        self.assertEqual("primary", via)
        self.assertEqual(99, order["orderId"])
        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual("ETHUSDT", wrapper.client.orders[0]["symbol"])
        self.assertEqual("SELL", wrapper.client.orders[0]["side"])
        self.assertEqual("0.10", wrapper.client.orders[0]["quantity"])
        self.assertTrue(wrapper.client.orders[0]["reduceOnly"])
        self.assertRegex(wrapper.client.orders[0]["newClientOrderId"], r"^tb-[0-9a-f]{32}$")

    def test_live_spot_submit_guard_blocks_disabled_audit_before_client_call(self):
        wrapper = _GuardedSpotSizingWrapper(live_safety_config=_live_ack_config())
        wrapper._configure_order_audit(enabled=False)

        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1)

        self.assertFalse(result["ok"])
        self.assertIn("order audit is disabled", result["error"])
        self.assertEqual([], wrapper.client.orders)

    def test_live_spot_order_returns_error_when_filters_unavailable(self):
        wrapper = _GuardedSpotSizingWrapper(live_safety_config=_live_ack_config())

        def fail_filters(_symbol):
            raise RuntimeError("metadata offline")

        wrapper.get_spot_symbol_filters = fail_filters

        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1)

        self.assertFalse(result["ok"])
        self.assertIn("spot symbol filters unavailable", result["error"])
        self.assertEqual([], wrapper.client.orders)

    def test_spot_sizer_rejects_non_finite_inputs_and_filters_before_submission(self):
        cases = (
            ({"price": float("nan"), "quantity": 0.1}, "No price available"),
            ({"price": 100.0, "quantity": float("inf")}, "quantity must be a finite number"),
            (
                {"price": 100.0, "quantity": 0.0, "use_quote": True, "quote_amount": float("nan")},
                "quote_amount<=0",
            ),
        )
        for kwargs, expected_error in cases:
            with self.subTest(kwargs=kwargs):
                wrapper = _SpotSizingWrapper()
                result = wrapper.place_spot_market_order("BTCUSDT", "BUY", **kwargs)
                self.assertFalse(result["ok"])
                self.assertEqual(expected_error, result["error"])
                self.assertEqual([], wrapper.client.orders)

        wrapper = _SpotSizingWrapper(filters={"stepSize": "NaN", "minQty": 0.001, "minNotional": 5.0})
        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=0.1)
        self.assertFalse(result["ok"])
        self.assertIn("stepSize", result["error"])
        self.assertEqual([], wrapper.client.orders)

    def test_market_order_sizers_reject_unknown_sides_before_side_effects(self):
        spot_wrapper = _SpotSizingWrapper()
        spot_result = spot_wrapper.place_spot_market_order("BTCUSDT", "buy-now", quantity=0.1)
        self.assertFalse(spot_result["ok"])
        self.assertIn("Unsupported spot order side", spot_result["error"])
        self.assertEqual([], spot_wrapper.client.orders)

        flex_wrapper = _FlexFuturesOrderWrapper()
        flex_result = flex_wrapper.place_futures_market_order("BTCUSDT", "sell-now", quantity=0.1)
        self.assertFalse(flex_result["ok"])
        self.assertIn("Unsupported futures order side", flex_result["error"])
        self.assertEqual([], flex_wrapper.submit_calls)

        base_wrapper = _BaseFuturesExposureWrapper(mode="Demo/Testnet")
        base_result = new_place_futures_market_order(base_wrapper, "BTCUSDT", "sell-now", quantity=0.1)
        self.assertFalse(base_result["ok"])
        self.assertIn("Unsupported futures order side", base_result["error"])

        strict_result = new_place_futures_market_order_strict(
            _FlexFuturesOrderWrapper(),
            "BTCUSDT",
            "sell-now",
            quantity=0.1,
        )
        self.assertFalse(strict_result["ok"])
        self.assertIn("Unsupported futures order side", strict_result["error"])

    def test_futures_market_order_sizers_reject_non_finite_or_fractional_leverage(self):
        for leverage in (float("nan"), float("inf"), 2.5, 0):
            with self.subTest(leverage=leverage):
                flex_wrapper = _FlexFuturesOrderWrapper()
                flex_result = flex_wrapper.place_futures_market_order(
                    "BTCUSDT", "BUY", quantity=0.1, leverage=leverage
                )
                self.assertFalse(flex_result["ok"])
                self.assertIn("Bad leverage", flex_result["error"])
                self.assertEqual([], flex_wrapper.submit_calls)

                base_result = new_place_futures_market_order(
                    _BaseFuturesExposureWrapper(mode="Demo/Testnet"),
                    "BTCUSDT",
                    "BUY",
                    quantity=0.1,
                    leverage=leverage,
                )
                self.assertFalse(base_result["ok"])
                self.assertIn("Bad leverage", base_result["error"])

                strict_result = new_place_futures_market_order_strict(
                    _FlexFuturesOrderWrapper(),
                    "BTCUSDT",
                    "BUY",
                    quantity=0.1,
                    leverage=leverage,
                )
                self.assertFalse(strict_result["ok"])
                self.assertIn("Bad leverage", strict_result["error"])

    def test_futures_market_order_sizers_reject_invalid_filter_metadata(self):
        invalid_filters = {"stepSize": "NaN", "minQty": 0.001, "minNotional": 5.0}

        base_wrapper = _BaseFuturesExposureWrapper(mode="Demo/Testnet")
        base_wrapper.get_futures_symbol_filters = lambda _symbol: dict(invalid_filters)
        base_result = new_place_futures_market_order(base_wrapper, "BTCUSDT", "BUY", quantity=0.1)
        self.assertFalse(base_result["ok"])
        self.assertIn("stepSize", base_result["error"])

        flex_wrapper = _FlexFuturesOrderWrapper()
        flex_wrapper.get_futures_symbol_filters = lambda _symbol: dict(invalid_filters)
        flex_result = flex_wrapper.place_futures_market_order("BTCUSDT", "BUY", quantity=0.1)
        self.assertFalse(flex_result["ok"])
        self.assertIn("stepSize", flex_result["error"])
        self.assertEqual([], flex_wrapper.submit_calls)

        strict_wrapper = _FlexFuturesOrderWrapper()
        strict_wrapper._ensure_symbol_margin = lambda *_args, **_kwargs: None
        strict_wrapper.ensure_futures_settings = lambda *_args, **_kwargs: None
        strict_wrapper.get_futures_symbol_filters = lambda _symbol: dict(invalid_filters)
        strict_result = new_place_futures_market_order_strict(strict_wrapper, "BTCUSDT", "BUY", quantity=0.1)
        self.assertFalse(strict_result["ok"])
        self.assertIn("stepSize", strict_result["error"])

    def test_live_futures_flex_sizer_requires_explicit_auto_bump_opt_in(self):
        wrapper = _FlexFuturesOrderWrapper(mode="Live", live_safety_config=_live_ack_config())

        result = wrapper.place_futures_market_order(
            "BTCUSDT",
            "BUY",
            percent_balance=0.01,
            max_auto_bump_percent=100.0,
        )

        self.assertFalse(result["ok"])
        self.assertIn("live auto-bump", result["error"])
        self.assertEqual([], wrapper.submit_calls)

    def test_live_futures_flex_sizer_allows_auto_bump_when_explicitly_enabled(self):
        wrapper = _FlexFuturesOrderWrapper(
            mode="Live",
            live_safety_config=_live_ack_config(live_allow_auto_bump_to_min_order=True),
        )

        result = wrapper.place_futures_market_order(
            "BTCUSDT",
            "BUY",
            percent_balance=0.01,
            max_auto_bump_percent=100.0,
        )

        self.assertTrue(result["ok"])
        self.assertEqual("percent(bumped_to_min)", result["mode"])
        self.assertEqual(1, len(wrapper.submit_calls))

    def test_live_base_futures_sizer_blocks_when_exposure_cannot_be_verified(self):
        wrapper = _BaseFuturesExposureWrapper(mode="Live")

        result = new_place_futures_market_order(
            wrapper,
            "BTCUSDT",
            "BUY",
            percent_balance=2.0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("percent(exposure-unverified)", result["mode"])
        self.assertIn("exposure", result["error"])

    def test_live_base_futures_sizer_blocks_when_snapshot_is_explicitly_unknown(self):
        wrapper = _BaseFuturesExposureWrapper(mode="Live")
        wrapper.list_open_futures_positions = lambda: None

        result = new_place_futures_market_order(
            wrapper,
            "BTCUSDT",
            "BUY",
            percent_balance=2.0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("percent(exposure-unverified)", result["mode"])
        self.assertIn("exposure", result["error"])

    def test_demo_base_futures_sizer_logs_exposure_lookup_failure_and_continues(self):
        wrapper = _BaseFuturesExposureWrapper(mode="Demo/Testnet")

        result = new_place_futures_market_order(
            wrapper,
            "BTCUSDT",
            "BUY",
            percent_balance=2.0,
        )

        self.assertTrue(wrapper.logged)
        self.assertEqual("warn", wrapper.logged[0][0])
        self.assertIn("exposure lookup failed", wrapper.logged[0][1])
        self.assertNotEqual("percent(exposure-unverified)", result["mode"])

    def test_futures_sizers_reject_non_finite_inputs_without_submitting_orders(self):
        for invalid in (float("nan"), float("inf")):
            flex_wrapper = _FlexFuturesOrderWrapper()
            invalid_price = flex_wrapper.place_futures_market_order("BTCUSDT", "BUY", price=invalid, quantity=0.1)
            invalid_percent = flex_wrapper.place_futures_market_order(
                "BTCUSDT", "BUY", price=100.0, percent_balance=invalid
            )
            invalid_quantity = flex_wrapper.place_futures_market_order(
                "BTCUSDT", "BUY", price=100.0, quantity=invalid
            )

            self.assertFalse(invalid_price["ok"])
            self.assertEqual("No price available", invalid_price["error"])
            self.assertFalse(invalid_percent["ok"])
            self.assertIn("Bad percent balance", invalid_percent["error"])
            self.assertFalse(invalid_quantity["ok"])
            self.assertIn("Bad quantity override", invalid_quantity["error"])
            self.assertEqual([], flex_wrapper.submit_calls)

            base_wrapper = _BaseFuturesExposureWrapper(mode="Demo/Testnet")
            base_result = new_place_futures_market_order(
                base_wrapper,
                "BTCUSDT",
                "BUY",
                price=100.0,
                quantity=invalid,
            )
            self.assertFalse(base_result["ok"])
            self.assertIn("Bad quantity override", base_result["error"])

            strict_wrapper = _FlexFuturesOrderWrapper()
            strict_wrapper._ensure_symbol_margin = lambda *_args, **_kwargs: None
            strict_wrapper.ensure_futures_settings = lambda *_args, **_kwargs: None
            strict_result = new_place_futures_market_order_strict(
                strict_wrapper,
                "BTCUSDT",
                "BUY",
                price=100.0,
                quantity=invalid,
            )
            self.assertFalse(strict_result["ok"])
            self.assertIn("Bad quantity override", strict_result["error"])
            self.assertEqual([], strict_wrapper.submit_calls)

    def test_order_audit_redacts_nested_secret_values_and_error_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "secrets.jsonl"
            wrapper = _FuturesAuditWrapper()
            wrapper._configure_order_audit(path=audit_path)

            wrapper._audit_order_event(
                "exchange_order_error",
                symbol="BTCUSDT",
                side="BUY",
                market="futures",
                params={
                    "symbol": "BTCUSDT",
                    "signature": "order-signature",
                    "headers": {"X-MBX-APIKEY": "header-api-key"},
                },
                result={
                    "info": {
                        "orderId": 100,
                        "authorization": "Bearer result-token",
                        "api_secret": "result-secret",
                    }
                },
                error=RuntimeError("Authorization: Bearer error-token api_secret=error-secret"),
                extra={"llm_api_key": "llm-secret"},
            )

            raw = audit_path.read_text(encoding="utf-8")
            row = json.loads(raw)
            self.assertEqual("exchange_order_error", row["event"])
            self.assertEqual("<redacted>", row["params"]["signature"])
            self.assertEqual("<redacted>", row["params"]["headers"]["X-MBX-APIKEY"])
            self.assertEqual("<redacted>", row["result"]["info"]["authorization"])
            self.assertEqual("<redacted>", row["result"]["info"]["api_secret"])
            self.assertIn("<redacted>", row["error"])
            for secret in (
                "order-signature",
                "header-api-key",
                "result-token",
                "result-secret",
                "error-token",
                "error-secret",
                "llm-secret",
            ):
                self.assertNotIn(secret, raw)

    def test_order_audit_rotates_when_size_limit_is_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "rotating-orders.jsonl"
            backup_path = jsonl_backup_path(audit_path)
            second_backup_path = jsonl_backup_path(audit_path, 2)
            expired_backup_path = jsonl_backup_path(audit_path, 3)
            wrapper = _FuturesAuditWrapper()
            wrapper._configure_order_audit(path=audit_path, max_bytes=1, backup_count=2)

            for index in range(4):
                wrapper._audit_order_event(
                    "exchange_order_request",
                    symbol="BTCUSDT",
                    side="BUY",
                    market="futures",
                    extra={"index": index},
                )

            self.assertTrue(audit_path.exists())
            self.assertTrue(backup_path.exists())
            self.assertTrue(second_backup_path.exists())
            self.assertFalse(expired_backup_path.exists())
            active_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            backup_rows = [json.loads(line) for line in backup_path.read_text(encoding="utf-8").splitlines()]
            second_backup_rows = [
                json.loads(line) for line in second_backup_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([3], [row["extra"]["index"] for row in active_rows])
            self.assertEqual([2], [row["extra"]["index"] for row in backup_rows])
            self.assertEqual([1], [row["extra"]["index"] for row in second_backup_rows])

    def test_order_audit_write_failure_is_exposed_in_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "orders.jsonl"
            wrapper = _DirectFuturesHttpWrapper()
            wrapper._configure_order_audit(path=audit_path)
            original_rotate = order_audit_runtime_module.rotate_jsonl_if_needed

            def fail_rotate(*_args, **_kwargs):
                raise OSError("disk full api_secret=leaked")

            try:
                order_audit_runtime_module.rotate_jsonl_if_needed = fail_rotate
                wrapper._audit_order_event(
                    "exchange_order_request",
                    symbol="BTCUSDT",
                    side="BUY",
                    market="futures",
                )
            finally:
                order_audit_runtime_module.rotate_jsonl_if_needed = original_rotate

            audit_status = wrapper.get_order_audit_status()
            connector_status = wrapper.get_connector_health_snapshot()
            rendered_status = json.dumps({"audit": audit_status, "connector": connector_status}, sort_keys=True)

            self.assertEqual("write_failed", audit_status["state"])
            self.assertFalse(audit_status["write_ok"])
            self.assertIn("disk full", audit_status["last_write_error"]["message"])
            self.assertEqual("warning", connector_status["health"])
            self.assertEqual("order_audit_write_failed", connector_status["state"])
            self.assertEqual("write_failed", connector_status["order_audit"]["state"])
            self.assertIn("<redacted>", rendered_status)
            self.assertNotIn("leaked", rendered_status)

            wrapper._audit_order_event(
                "exchange_order_request",
                symbol="BTCUSDT",
                side="BUY",
                market="futures",
            )

            recovered_status = wrapper.get_order_audit_status()
            self.assertTrue(recovered_status["write_ok"])
            self.assertEqual("ready", recovered_status["state"])
            self.assertTrue(recovered_status["last_write_ok_at"])

    def test_direct_futures_http_rate_limit_records_structured_backoff(self):
        wrapper = _DirectFuturesHttpWrapper()
        response = _FakeDirectHttpResponse(
            429,
            {"code": -1003, "msg": "Too many requests; banned until 2524608000000 signature=leaked"},
        )

        with mock.patch.object(http_request_runtime_module.requests, "request", return_value=response) as request_mock:
            result = wrapper._http_signed_futures("/v1/order", {"symbol": "BTCUSDT"})

        self.assertEqual({}, result)
        self.assertEqual(1, request_mock.call_count)
        error = wrapper._last_futures_http_error
        self.assertIsInstance(error, dict)
        self.assertEqual("rate_limited", error["category"])
        self.assertTrue(error["retryable"])
        self.assertEqual(429, error["status_code"])
        self.assertEqual(-1003, error["code"])
        self.assertIn("<redacted>", error["message"])
        self.assertNotIn("leaked", error["message"])
        self.assertGreater(wrapper._seconds_until_unban(), 0.0)

    def test_direct_futures_http_retries_timeout_and_marks_recovery(self):
        wrapper = _DirectFuturesHttpWrapper()
        calls = []

        def fake_request(method, url, headers=None, timeout=None):
            calls.append((method, url, headers, timeout))
            if len(calls) == 1:
                raise http_request_runtime_module.requests.exceptions.Timeout(f"Read timed out for {url}")
            return _FakeDirectHttpResponse(200, {"ok": True})

        with (
            mock.patch.object(http_request_runtime_module.time, "sleep", return_value=None),
            mock.patch.object(http_request_runtime_module.requests, "request", side_effect=fake_request),
        ):
            result = wrapper._http_signed_futures("/v1/account", {"symbol": "BTCUSDT"})

        self.assertEqual({"ok": True}, result)
        self.assertEqual(2, len(calls))
        self.assertIsNone(wrapper._last_futures_http_error)
        self.assertEqual(1, len(wrapper.offline))
        self.assertEqual(1, wrapper.recovered)

    def test_direct_futures_http_redacts_persistent_network_error(self):
        wrapper = _DirectFuturesHttpWrapper()

        with (
            mock.patch.object(http_request_runtime_module.time, "sleep", return_value=None),
            mock.patch.object(
                http_request_runtime_module.requests,
                "request",
                side_effect=http_request_runtime_module.requests.exceptions.Timeout(
                    "signature=leaked api_secret=unit-api-secret"
                ),
            ),
        ):
            result = wrapper._http_signed_futures("/v1/account", {"symbol": "BTCUSDT"})

        self.assertEqual({}, result)
        error = wrapper._last_futures_http_error
        self.assertIsInstance(error, dict)
        self.assertEqual("network", error["category"])
        self.assertTrue(error["retryable"])
        self.assertEqual(2, error["attempt"])
        self.assertIn("<redacted>", error["message"])
        self.assertNotIn("leaked", error["message"])
        self.assertNotIn("unit-api-secret", error["message"])

    def test_signed_spot_http_failure_records_connector_health_error(self):
        wrapper = _DirectFuturesHttpWrapper()
        wrapper.account_type = "SPOT"
        response = _FakeDirectHttpResponse(
            401,
            {"code": -2015, "msg": "Invalid API-key api_secret=unit-api-secret signature=leaked"},
        )

        with mock.patch.object(http_request_runtime_module.requests, "get", return_value=response) as get_mock:
            result = wrapper._http_signed_spot("/v3/account")

        self.assertEqual({}, result)
        self.assertEqual(1, get_mock.call_count)
        error = wrapper._last_futures_http_error
        self.assertIsInstance(error, dict)
        self.assertEqual("/v3/account", error["path"])
        self.assertEqual("https://testnet.binance.vision/api", error["base"])
        self.assertEqual("auth", error["category"])
        self.assertFalse(error["retryable"])
        self.assertEqual(401, error["status_code"])
        self.assertEqual(-2015, error["code"])
        self.assertIn("<redacted>", error["message"])
        self.assertNotIn("unit-api-secret", error["message"])
        self.assertNotIn("leaked", error["message"])

        snapshot = wrapper.get_connector_health_snapshot()
        self.assertEqual("error", snapshot["health"])
        self.assertEqual("auth_error", snapshot["state"])

    def test_signed_spot_success_only_clears_prior_spot_error(self):
        wrapper = _DirectFuturesHttpWrapper()
        wrapper._record_futures_http_error(
            "/v2/account",
            status_code=503,
            message="futures unavailable",
            category="exchange_unavailable",
            retryable=True,
            method="GET",
        )
        response = _FakeDirectHttpResponse(200, {"balances": []})

        with mock.patch.object(http_request_runtime_module.requests, "get", return_value=response):
            result = wrapper._http_signed_spot("/v3/account")

        self.assertEqual({"balances": []}, result)
        self.assertIsInstance(wrapper._last_futures_http_error, dict)
        self.assertEqual("/v2/account", wrapper._last_futures_http_error["path"])

        wrapper._record_futures_http_error(
            "/v3/account",
            status_code=401,
            message="spot auth failed",
            category="auth",
            retryable=False,
            method="GET",
            base_url="https://testnet.binance.vision/api",
        )

        with mock.patch.object(http_request_runtime_module.requests, "get", return_value=response):
            result = wrapper._http_signed_spot("/v3/account")

        self.assertEqual({"balances": []}, result)
        self.assertIsNone(wrapper._last_futures_http_error)

    def test_connector_health_snapshot_reflects_last_http_error(self):
        wrapper = _DirectFuturesHttpWrapper()

        wrapper._record_futures_http_error(
            "/v2/account",
            status_code=401,
            code=-2015,
            message="api_secret=unit-api-secret signature=leaked",
            category="auth",
            retryable=False,
            method="GET",
        )

        snapshot = wrapper.get_connector_health_snapshot()

        self.assertEqual("error", snapshot["health"])
        self.assertEqual("auth_error", snapshot["state"])
        self.assertEqual("unit-test", snapshot["connector_backend"])
        self.assertIn("<redacted>", snapshot["last_error"]["message"])
        self.assertNotIn("unit-api-secret", snapshot["last_error"]["message"])
        self.assertNotIn("leaked", snapshot["last_error"]["message"])

    def test_new_subpackages_expose_expected_binders(self):
        binders = [
            new_bind_http,
            new_bind_rate_limit,
            new_bind_ws,
            new_bind_futures_orders,
            new_bind_order_audit,
            new_bind_order_fallback,
            new_bind_order_sizing,
            new_bind_order_submit_guard,
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

    def test_spot_market_order_ceil_sizes_to_min_notional(self):
        wrapper = _SpotSizingWrapper(price=1999.0)

        result = wrapper.place_spot_market_order(
            "ETHUSDT",
            "BUY",
            price=1999.0,
            use_quote=True,
            quote_amount=5.0,
        )

        self.assertTrue(result["ok"])
        qty = float(result["computed"]["qty"])
        self.assertGreaterEqual(qty * 1999.0, 5.0)
        self.assertEqual(wrapper.client.orders[-1]["quantity"], str(qty))

    def test_adjust_spot_quantity_keeps_min_notional_quantity(self):
        wrapper = _SpotSizingWrapper(price=100.0)

        qty, error = wrapper.adjust_qty_to_filters_spot("ETHUSDT", 0.002, 100.0)

        self.assertIsNone(error)
        self.assertEqual(qty, 0.05)

    def test_quantity_adjustment_rejects_non_finite_values_and_filters(self):
        spot_wrapper = _SpotSizingWrapper()
        for qty, price, expected_error in (
            (float("nan"), 100.0, "qty must be a finite number"),
            (0.1, float("inf"), "price must be a finite number"),
        ):
            with self.subTest(market="spot", qty=qty, price=price):
                adjusted, error = spot_wrapper.adjust_qty_to_filters_spot("BTCUSDT", qty, price)
                self.assertEqual(0.0, adjusted)
                self.assertEqual(expected_error, error)

        futures_wrapper = _FlexFuturesOrderWrapper()
        adjusted, error = new_adjust_qty_to_filters_futures(futures_wrapper, "BTCUSDT", 0.1, float("nan"))
        self.assertEqual(0.0, adjusted)
        self.assertEqual("price must be a finite number", error)

        invalid_filters_wrapper = _SpotSizingWrapper(
            filters={"stepSize": "NaN", "minQty": 0.001, "minNotional": 5.0}
        )
        adjusted, error = invalid_filters_wrapper.adjust_qty_to_filters_spot("BTCUSDT", 0.1, 100.0)
        self.assertEqual(0.0, adjusted)
        self.assertIn("stepSize", str(error))


if __name__ == "__main__":
    unittest.main()
