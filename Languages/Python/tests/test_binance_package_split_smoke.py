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
from app.integrations.exchanges.binance.orders.order_audit_runtime import (
    bind_binance_order_audit_runtime as new_bind_order_audit,
)
from app.integrations.exchanges.binance.orders import order_audit_runtime as order_audit_runtime_module
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
from app.integrations.exchanges.binance.transport import http_request_runtime as http_request_runtime_module
from app.integrations.exchanges.binance.transport.http_runtime import bind_binance_http_runtime as new_bind_http
from app.integrations.exchanges.binance.transport.rate_limit_runtime import (
    bind_binance_rate_limit_runtime as new_bind_rate_limit,
)
from app.integrations.exchanges.binance.transport.ws_runtime import bind_binance_ws_runtime as new_bind_ws
from app.jsonl_rotation import jsonl_backup_path
from app.settings import LiveTradingSafetyError


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


class _SpotSizingClient:
    def __init__(self):
        self.orders = []

    def create_order(self, **kwargs):
        self.orders.append(dict(kwargs))
        return {"orderId": 1, **kwargs}


class _SpotSizingWrapper:
    def __init__(self, *, price=100.0, filters=None):
        self.account_type = "SPOT"
        self.client = _SpotSizingClient()
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

    def _log(self, message, lvl="info"):
        self.warned.append((lvl, message))

    def _testnet_order_fallback_client(self):
        return None


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


new_bind_order_audit(_SpotSizingWrapper)
new_bind_order_sizing(_SpotSizingWrapper)
new_bind_order_audit(_FuturesAuditWrapper)
new_bind_order_fallback(_FuturesAuditWrapper)
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


if __name__ == "__main__":
    unittest.main()
