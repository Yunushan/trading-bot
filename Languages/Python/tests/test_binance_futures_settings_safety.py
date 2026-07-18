from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.runtime.futures_settings import (  # noqa: E402
    bind_binance_futures_settings,
)
from app.integrations.exchanges.binance.runtime.futures_mode_runtime import (  # noqa: E402
    bind_binance_futures_mode_runtime,
)


class _FuturesSettingsClient:
    def __init__(self, *, position_rows=None, open_orders=None, cancel_error=None):
        self.position_rows = list(position_rows or [])
        self.open_orders = list(open_orders or [])
        self.cancel_error = cancel_error
        self.margin_changes = []
        self.leverage_changes = []
        self.position_mode_changes = []
        self.cancel_calls = []

    def futures_position_information(self, **_kwargs):
        return list(self.position_rows)

    def futures_position_risk(self, **_kwargs):
        return list(self.position_rows)

    def futures_get_open_orders(self, **_kwargs):
        return list(self.open_orders)

    def futures_cancel_all_open_orders(self, **kwargs):
        self.cancel_calls.append(dict(kwargs))
        if self.cancel_error is not None:
            raise self.cancel_error
        return {"ok": True}

    def futures_change_margin_type(self, **kwargs):
        self.margin_changes.append(dict(kwargs))
        return {"code": 200}

    def futures_change_leverage(self, **kwargs):
        self.leverage_changes.append(dict(kwargs))
        return {"leverage": kwargs["leverage"]}

    def futures_change_position_mode(self, **kwargs):
        self.position_mode_changes.append(dict(kwargs))
        return {"code": 200}


class _FuturesSettingsWrapper:
    def __init__(self, client):
        self.client = client
        self._default_margin_mode = "ISOLATED"
        self._default_leverage = 5
        self._requested_default_leverage = 5
        self.futures_leverage = 5
        self.logs = []

    def _get_futures_account_cached(self, *, force_refresh=False):  # noqa: ARG002
        return {}

    def _log(self, message, lvl="info"):
        self.logs.append((lvl, str(message)))

    def clamp_futures_leverage(self, _symbol, leverage):
        return max(1, min(self._max_futures_leverage_constant, int(leverage)))

    def _futures_base(self):
        return "https://testnet.binancefuture.com/fapi"


bind_binance_futures_settings(_FuturesSettingsWrapper, max_futures_leverage=20)
bind_binance_futures_mode_runtime(_FuturesSettingsWrapper)


class BinanceFuturesSettingsSafetyTests(unittest.TestCase):
    def test_margin_type_uses_matching_symbol_and_normalizes_cross_alias(self):
        wrapper = _FuturesSettingsWrapper(
            _FuturesSettingsClient(
                position_rows=[
                    {"symbol": "ETHUSDT", "marginType": "ISOLATED", "positionAmt": "0"},
                    {"symbol": "BTCUSDT", "marginType": "cross", "positionAmt": "0"},
                ]
            )
        )

        self.assertEqual("CROSSED", wrapper.get_symbol_margin_type("btcusdt"))
        self.assertIsNone(wrapper.get_symbol_margin_type(""))

    def test_margin_change_blocks_when_exchange_position_amount_is_nonfinite(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "nan"}]
        )
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "open position"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "CROSSED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_margin_change_blocks_when_exchange_position_lookup_fails(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_position_information = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("unavailable"))
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "open position"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "CROSSED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_strict_margin_helper_blocks_when_exchange_position_data_is_invalid(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "nan"}]
        )
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "unable to verify futures exposure"):
            wrapper._ensure_symbol_margin("BTCUSDT", "CROSSED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.cancel_calls)
        self.assertEqual([], client.leverage_changes)

    def test_strict_margin_helper_blocks_when_open_order_cancellation_fails(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}],
            cancel_error=RuntimeError("cancel rejected"),
        )
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "unable to cancel open futures orders"):
            wrapper._ensure_symbol_margin("BTCUSDT", "CROSSED", 10)

        self.assertEqual([{"symbol": "BTCUSDT"}], client.cancel_calls)
        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_strict_margin_helper_blocks_when_open_order_cancellation_is_unacknowledged(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_cancel_all_open_orders = lambda **_kwargs: None
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "unable to cancel open futures orders"):
            wrapper._ensure_symbol_margin("BTCUSDT", "CROSSED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_strict_margin_helper_blocks_when_leverage_update_fails(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_change_leverage = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("rejected"))
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "unable to set leverage"):
            wrapper._ensure_symbol_margin("BTCUSDT", "ISOLATED", 10)

        self.assertEqual([], client.margin_changes)

    def test_order_settings_guard_blocks_when_leverage_update_fails(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_change_leverage = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("rejected"))
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to set leverage"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

    def test_order_settings_guard_blocks_when_margin_change_cannot_be_verified(self):
        client = _FuturesSettingsClient()
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to verify margin type"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

        self.assertEqual([], client.leverage_changes)

    def test_order_settings_guard_blocks_when_required_open_order_cancellation_fails(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}],
            open_orders=[{"symbol": "BTCUSDT", "orderId": 1}],
            cancel_error=RuntimeError("cancel rejected"),
        )
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to cancel open futures orders"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "CROSSED", 10)

        self.assertEqual([{"symbol": "BTCUSDT"}], client.cancel_calls)
        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_order_settings_guard_blocks_when_open_order_cancellation_is_unacknowledged(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}],
            open_orders=[{"symbol": "BTCUSDT", "orderId": 1}],
        )
        client.futures_cancel_all_open_orders = lambda **_kwargs: {"status": "PENDING"}
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to cancel open futures orders"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "CROSSED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_order_settings_guard_blocks_when_margin_status_lookup_fails(self):
        client = _FuturesSettingsClient()
        client.futures_position_information = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
        client.futures_position_risk = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to read margin type"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_order_settings_guard_blocks_when_margin_status_returns_error_payload(self):
        client = _FuturesSettingsClient()
        client.futures_position_information = lambda **_kwargs: {"code": -2015, "msg": "rejected"}
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to read margin type"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_pre_order_margin_guard_blocks_when_leverage_is_unacknowledged(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_change_leverage = lambda **_kwargs: {"leverage": "NaN"}
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to set leverage"):
            wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

    def test_strict_margin_helper_blocks_when_leverage_is_unacknowledged(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        client.futures_change_leverage = lambda **_kwargs: {"leverage": "NaN"}
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "unable to set leverage"):
            wrapper._ensure_symbol_margin("BTCUSDT", "ISOLATED", 10)

    def test_ensure_futures_settings_reports_rejected_explicit_configuration(self):
        client = _FuturesSettingsClient()
        client.futures_change_leverage = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("rejected"))
        wrapper = _FuturesSettingsWrapper(client)

        with self.assertRaisesRegex(RuntimeError, "Unable to set leverage"):
            wrapper.ensure_futures_settings("BTCUSDT", leverage=10, margin_mode="ISOLATED")

        self.assertEqual([{"symbol": "BTCUSDT", "marginType": "ISOLATED"}], client.margin_changes)

    def test_ensure_futures_settings_rejects_unacknowledged_mutations(self):
        cases = (
            ("position", "Unable to set futures position mode"),
            ("margin", "Unable to set margin mode"),
            ("leverage", "Unable to set leverage"),
        )
        for target, message in cases:
            with self.subTest(target=target):
                client = _FuturesSettingsClient()
                if target == "position":
                    client.futures_change_position_mode = lambda **_kwargs: None
                elif target == "margin":
                    client.futures_change_margin_type = lambda **_kwargs: {}
                else:
                    client.futures_change_leverage = lambda **_kwargs: {"leverage": "NaN"}
                wrapper = _FuturesSettingsWrapper(client)

                with self.assertRaisesRegex(RuntimeError, message):
                    wrapper.ensure_futures_settings("BTCUSDT", leverage=10, margin_mode="ISOLATED", hedge_mode=True)

    def test_position_mode_rejects_exchange_error_payload(self):
        client = _FuturesSettingsClient()
        client.futures_change_position_mode = lambda **_kwargs: {"code": -2015, "msg": "rejected"}
        wrapper = _FuturesSettingsWrapper(client)

        self.assertFalse(wrapper.set_position_mode(True))

    def test_position_mode_rejects_empty_or_malformed_acknowledgements(self):
        for response in (None, {}, "accepted", {"status": "PENDING"}):
            with self.subTest(response=response):
                client = _FuturesSettingsClient()
                client.futures_change_position_mode = lambda **_kwargs: response
                wrapper = _FuturesSettingsWrapper(client)

                self.assertFalse(wrapper.set_position_mode(True))

    def test_multi_assets_mode_rejects_error_payload_and_failed_http_fallback(self):
        client = _FuturesSettingsClient()
        client.futures_change_multi_assets_margin = lambda **_kwargs: {"code": -2015, "msg": "rejected"}
        client._request_futures_api = lambda *_args, **_kwargs: {"code": -2015, "msg": "rejected"}
        wrapper = _FuturesSettingsWrapper(client)
        wrapper.api_key = "key"
        wrapper.api_secret = "secret"

        failed_response = mock.Mock()
        failed_response.raise_for_status.side_effect = RuntimeError("403")
        with mock.patch(
            "app.integrations.exchanges.binance.runtime.futures_mode_runtime.requests.post",
            return_value=failed_response,
        ):
            self.assertFalse(wrapper.set_multi_assets_mode(True))

    def test_multi_assets_mode_rejects_empty_or_malformed_acknowledgements(self):
        for response in (None, {}, "accepted", {"status": "PENDING"}):
            with self.subTest(response=response):
                client = _FuturesSettingsClient()
                client.futures_change_multi_assets_margin = lambda **_kwargs: response
                client._request_futures_api = lambda *_args, **_kwargs: response
                wrapper = _FuturesSettingsWrapper(client)
                wrapper.api_key = "key"
                wrapper.api_secret = "secret"

                failed_response = mock.Mock()
                failed_response.raise_for_status.side_effect = RuntimeError("403")
                with mock.patch(
                    "app.integrations.exchanges.binance.runtime.futures_mode_runtime.requests.post",
                    return_value=failed_response,
                ):
                    self.assertFalse(wrapper.set_multi_assets_mode(True))

    def test_fast_mode_uses_fresh_matching_settings_cache_without_exchange_mutation(self):
        client = _FuturesSettingsClient(
            position_rows=[{"symbol": "BTCUSDT", "marginType": "ISOLATED", "positionAmt": "0"}]
        )
        wrapper = _FuturesSettingsWrapper(client)
        wrapper._fast_order_mode = True
        wrapper._fast_order_cache_ttl = 60.0
        wrapper._futures_settings_cache = {
            "BTCUSDT": {"margin_mode": "ISOLATED", "leverage": 10, "ts": time.time()}
        }

        wrapper._ensure_margin_and_leverage_or_block("BTCUSDT", "ISOLATED", 10)

        self.assertEqual([], client.margin_changes)
        self.assertEqual([], client.leverage_changes)

    def test_ensure_futures_settings_normalizes_margin_mode_and_clamps_leverage(self):
        client = _FuturesSettingsClient()
        wrapper = _FuturesSettingsWrapper(client)

        wrapper.ensure_futures_settings("btcusdt", leverage=99, margin_mode="cross", hedge_mode=True)

        self.assertEqual([{"dualSidePosition": True}], client.position_mode_changes)
        self.assertEqual([{"symbol": "BTCUSDT", "marginType": "CROSSED"}], client.margin_changes)
        self.assertEqual([{"symbol": "BTCUSDT", "leverage": 20}], client.leverage_changes)
        self.assertEqual("CROSSED", wrapper._default_margin_mode)
        self.assertEqual(20, wrapper.futures_leverage)

    def test_set_futures_leverage_clamps_to_bound_constant_and_ignores_invalid_input(self):
        wrapper = _FuturesSettingsWrapper(_FuturesSettingsClient())

        wrapper.set_futures_leverage(999)
        self.assertEqual(20, wrapper.futures_leverage)
        wrapper.set_futures_leverage("invalid")
        self.assertEqual(20, wrapper.futures_leverage)


if __name__ == "__main__":
    unittest.main()
