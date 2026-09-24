from __future__ import annotations

import hashlib
import hmac
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime import SpotUserDataTransport
from app.settings.live_safety import LiveTradingSafetyError


class SpotUserDataTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = SpotUserDataTransport("offline-api-key", "offline-api-secret")

    def response(self, body: object, status_code: int = 200):
        return SimpleNamespace(status_code=status_code, json=Mock(return_value=body))

    def assert_signed_get(self, call, path: str, expected: dict[str, str] | None = None) -> None:
        args, kwargs = call
        self.assertEqual(f"https://api.binance.com/api{path}", args[0])
        self.assertEqual("offline-api-key", kwargs["headers"]["X-MBX-APIKEY"])
        self.assertEqual((3, 8), kwargs["timeout"])
        params = dict(kwargs["params"])
        signature = params.pop("signature")
        payload = urlencode(params)
        expected_signature = hmac.new(
            b"offline-api-secret", payload.encode("ascii"), hashlib.sha256,
        ).hexdigest()
        self.assertEqual(expected_signature, signature)
        self.assertEqual(5000, params.pop("recvWindow"))
        self.assertGreater(params.pop("timestamp"), 0)
        self.assertEqual(expected or {}, params)
        self.assertNotIn("offline-api-secret", repr(call))

    def test_account_uid_uses_signed_fixed_host_get(self):
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response({"uid": 12345678, "accountType": "SPOT"})
            self.assertEqual(12345678, self.transport.get_account_uid())
        get.assert_called_once()
        self.assert_signed_get(get.call_args, "/v3/account")

    def test_account_overview_validates_balances_and_returns_counts_only(self):
        response = {
            "uid": 12345678,
            "accountType": "SPOT",
            "balances": [
                {"asset": "BTC", "free": "0.25", "locked": "0"},
                {"asset": "USDT", "free": "0", "locked": "12.5"},
                {"asset": "ETH", "free": "0", "locked": "0"},
            ],
        }
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(response)
            result = self.transport.get_account_overview()
        self.assertEqual({
            "account_uid": 12345678,
            "balance_asset_count": 3,
            "nonzero_balance_asset_count": 2,
            "locked_balance_asset_count": 1,
        }, result)
        self.assertNotIn("BTC", repr(result))
        self.assertNotIn("0.25", repr(result))
        self.assert_signed_get(get.call_args, "/v3/account")

    def test_open_orders_uses_fixed_account_wide_signed_get(self):
        orders = [{
            "symbol": "BTCUSDT", "clientOrderId": "known-order", "orderId": 9,
            "status": "NEW",
        }]
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(orders)
            self.assertEqual(orders, self.transport.get_open_orders())
        self.assert_signed_get(get.call_args, "/v3/openOrders")

    def test_account_overview_rejects_duplicate_or_invalid_balances(self):
        for balances in (
            [
                {"asset": "BTC", "free": "1", "locked": "0"},
                {"asset": "BTC", "free": "2", "locked": "0"},
            ],
            [{"asset": "BTC", "free": "-1", "locked": "0"}],
            [{"asset": "BTC", "free": "NaN", "locked": "0"}],
            [{"asset": "BTC", "free": "1", "locked": 0}],
        ):
            with self.subTest(balances=balances), patch(
                "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get",
                return_value=self.response({"uid": 12345678, "accountType": "SPOT", "balances": balances}),
            ), self.assertRaises(LiveTradingSafetyError):
                self.transport.get_account_overview()

    def test_order_query_is_exactly_scoped_to_existing_client_order_id(self):
        expected_response = {"orderId": 55, "clientOrderId": "existing-order-1", "symbol": "BTCUSDT", "status": "FILLED"}
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(expected_response)
            self.assertEqual(
                expected_response,
                self.transport.get_order(symbol="BTCUSDT", origClientOrderId="existing-order-1"),
            )
        get.assert_called_once()
        self.assert_signed_get(
            get.call_args, "/v3/order", {"symbol": "BTCUSDT", "origClientOrderId": "existing-order-1"},
        )

    def test_account_identity_and_order_query_fail_closed(self):
        for body in (
            {"uid": True, "accountType": "SPOT"},
            {"uid": 12345678, "accountType": "MARGIN"},
            {"uid": 0, "accountType": "SPOT"},
            {"uid": 12345678, "accountType": "SPOT", "code": 0},
        ):
            with self.subTest(body=body), patch(
                "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get",
                return_value=self.response(body),
            ):
                with self.assertRaises(LiveTradingSafetyError):
                    self.transport.get_account_uid()

        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get",
            return_value=self.response({"code": -2013}, status_code=400),
        ):
            with self.assertRaisesRegex(LiveTradingSafetyError, "HTTP 400"):
                self.transport.get_order(symbol="BTCUSDT", origClientOrderId="missing-order")

    def test_query_does_not_accept_parameter_injection_or_other_endpoints(self):
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            for client_order_id in ("bad&signature=x", "bad order", "x" * 37):
                with self.subTest(client_order_id=client_order_id), self.assertRaises(LiveTradingSafetyError):
                    self.transport.get_order(symbol="BTCUSDT", origClientOrderId=client_order_id)
            with self.assertRaises(LiveTradingSafetyError):
                self.transport._signed_get("/v3/order/cancel", {"symbol": "BTCUSDT"})
        get.assert_not_called()

    def test_transport_exception_is_redacted_from_operator_error(self):
        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get",
            side_effect=RuntimeError("https://host/path?signature=private-signature"),
        ):
            with self.assertRaises(LiveTradingSafetyError) as raised:
                self.transport.get_order(symbol="BTCUSDT", origClientOrderId="existing-order-1")
        self.assertNotIn("private-signature", str(raised.exception))
        self.assertNotIn("offline-api-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
