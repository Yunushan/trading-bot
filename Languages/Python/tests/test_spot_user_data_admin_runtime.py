from __future__ import annotations

import hashlib
import hmac
import unittest
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime import (
    SpotOrderListCancellationTransport,
    SpotResidualStopTransport,
    SpotUserDataTransport,
)
from app.integrations.exchanges.binance.orders.spot_opo_runtime import validate_spot_opo_residual_stop_request
from app.settings.live_safety import LiveTradingSafetyError


class SpotUserDataTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = SpotUserDataTransport("offline-api-key", "offline-api-secret")

    def response(self, body: object, status_code: int = 200):
        return SimpleNamespace(status_code=status_code, json=Mock(return_value=body))

    def assert_signed_get(self, call, path: str, expected: dict[str, str | int] | None = None) -> None:
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

    def test_order_list_query_is_exactly_scoped_to_list_client_order_id(self):
        # Numeric IDs remain stable when Binance renames a canceled child.
        expected = {"orderId": 55, "clientOrderId": "cancellation-alias", "symbol": "BTCUSDT", "status": "CANCELED"}
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(expected)
            self.assertEqual(expected, self.transport.get_order(symbol="BTCUSDT", orderId=55))
        self.assert_signed_get(get.call_args, "/v3/order", {"symbol": "BTCUSDT", "orderId": 55})
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            for params in ({"orderId": 0}, {"orderId": True}, {"orderId": "55"}, {},
                           {"orderId": 55, "origClientOrderId": "old-child"}):
                with self.subTest(params=params), self.assertRaises(LiveTradingSafetyError):
                    self.transport.get_order(symbol="BTCUSDT", **params)
            get.assert_not_called()

    def test_order_list_query_keeps_its_exact_client_order_id_selector(self):
        expected_response = {
            "orderListId": 13, "contingencyType": "OTO", "listStatusType": "EXEC_STARTED",
            "listClientOrderId": "op-list-13", "symbol": "BTCUSDT", "orders": [],
        }
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(expected_response)
            self.assertEqual(expected_response, self.transport.get_order_list(origClientOrderId="op-list-13"))
        self.assert_signed_get(get.call_args, "/v3/orderList", {"origClientOrderId": "op-list-13"})

    def test_my_trades_query_is_scoped_to_one_order_and_supports_bounded_pagination(self):
        trades = [{"id": 17, "orderId": 91, "symbol": "BTCUSDT"}]
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = self.response(trades)
            self.assertEqual(
                trades,
                self.transport.get_my_trades(
                    symbol="BTCUSDT", order_id=91, from_id=17, limit=1000,
                ),
            )
        self.assert_signed_get(
            get.call_args,
            "/v3/myTrades",
            {"symbol": "BTCUSDT", "orderId": 91, "fromId": 17, "limit": 1000},
        )

    def test_my_trades_rejects_unscoped_or_invalid_queries_before_network(self):
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            for params in (
                {"symbol": "BTCUSDT", "order_id": 91, "from_id": -1},
                {"symbol": "BTCUSDT", "order_id": 0},
                {"symbol": "BTCUSDT", "order_id": 91, "limit": 1001},
                {"symbol": "../BTC", "order_id": 91},
            ):
                with self.subTest(params=params), self.assertRaises(LiveTradingSafetyError):
                    self.transport.get_my_trades(**params)
        get.assert_not_called()

    def test_public_symbol_metadata_uses_only_the_fixed_https_host(self):
        response = self.response({"symbols": [{
            "symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT",
        }]})
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.return_value = response
            self.assertEqual(("BTC", "USDT"), self.transport.get_symbol_assets(symbol="BTCUSDT"))
        args, kwargs = get.call_args
        self.assertEqual("https://api.binance.com/api/v3/exchangeInfo", args[0])
        self.assertEqual({"symbol": "BTCUSDT"}, kwargs["params"])
        self.assertNotIn("headers", kwargs)
        self.assertNotIn("offline-api-secret", repr(get.call_args))

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
                with self.subTest(order_list_id=client_order_id), self.assertRaises(LiveTradingSafetyError):
                    self.transport.get_order_list(origClientOrderId=client_order_id)
            with self.assertRaises(LiveTradingSafetyError):
                self.transport._signed_get("/v3/order/cancel", {"symbol": "BTCUSDT"})
            with self.assertRaises(LiveTradingSafetyError):
                self.transport._signed_get("/v3/orderList", {"symbol": "BTCUSDT"})
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

    def test_exact_order_list_cancellation_uses_signed_delete_and_exact_identity(self):
        transport = SpotOrderListCancellationTransport("offline-api-key", "offline-api-secret")
        body = {
            "symbol": "BTCUSDT", "listClientOrderId": "op-list-13", "orderListId": 13,
            "listStatusType": "ALL_DONE",
        }
        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.delete",
            return_value=self.response(body),
        ) as delete:
            self.assertEqual(
                body,
                transport.cancel_order_list(symbol="BTCUSDT", listClientOrderId="op-list-13"),
            )
        args, kwargs = delete.call_args
        self.assertEqual("https://api.binance.com/api/v3/orderList", args[0])
        self.assertEqual("offline-api-key", kwargs["headers"]["X-MBX-APIKEY"])
        self.assertEqual((3, 8), kwargs["timeout"])
        params = dict(kwargs["params"])
        signature = params.pop("signature")
        payload = urlencode(params)
        self.assertEqual(
            hmac.new(b"offline-api-secret", payload.encode("ascii"), hashlib.sha256).hexdigest(),
            signature,
        )
        self.assertEqual("BTCUSDT", params.pop("symbol"))
        self.assertEqual("op-list-13", params.pop("listClientOrderId"))
        self.assertEqual(5000, params.pop("recvWindow"))
        self.assertGreater(params.pop("timestamp"), 0)
        self.assertEqual({}, params)
        self.assertNotIn("offline-api-secret", repr(delete.call_args))

    def test_order_list_cancellation_rejects_broad_or_conflicting_requests(self):
        transport = SpotOrderListCancellationTransport("offline-api-key", "offline-api-secret")
        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.delete",
        ) as delete:
            for symbol, list_client_id in (
                ("", "op-list-13"), ("BTCUSDT", ""), ("BTCUSDT", "x" * 37),
                ("BTCUSDT", "op-list&symbol=ETHUSDT"),
            ):
                with self.subTest(symbol=symbol, list_client_id=list_client_id):
                    with self.assertRaises(LiveTradingSafetyError):
                        transport.cancel_order_list(symbol=symbol, listClientOrderId=list_client_id)
        delete.assert_not_called()

    def test_cancellation_transport_failure_is_redacted(self):
        transport = SpotOrderListCancellationTransport("offline-api-key", "offline-api-secret")
        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.delete",
            side_effect=RuntimeError("https://host/path?signature=private-signature"),
        ):
            with self.assertRaises(LiveTradingSafetyError) as raised:
                transport.cancel_order_list(symbol="BTCUSDT", listClientOrderId="op-list-13")
        self.assertNotIn("private-signature", str(raised.exception))
        self.assertNotIn("offline-api-secret", str(raised.exception))

    def test_residual_stop_submission_is_fixed_host_signed_and_exactly_scoped(self):
        transport = SpotResidualStopTransport("offline-api-key", "offline-api-secret")
        request = validate_spot_opo_residual_stop_request({
            "symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS",
            "quantity": "0.0399", "stopPrice": "95.00",
            "newClientOrderId": "residual-stop-01", "newOrderRespType": "FULL",
        })
        response_body = {
            "symbol": "BTCUSDT", "orderId": 203, "orderListId": -1,
            "clientOrderId": "residual-stop-01", "side": "SELL", "type": "STOP_LOSS",
            "status": "NEW", "origQty": "0.0399", "executedQty": "0", "stopPrice": "95.00",
        }
        with patch(
            "app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.post",
            return_value=self.response(response_body),
        ) as post:
            self.assertEqual(response_body, transport.place_stop_loss_sell(request))
        args, kwargs = post.call_args
        self.assertEqual("https://api.binance.com/api/v3/order", args[0])
        self.assertEqual("offline-api-key", kwargs["headers"]["X-MBX-APIKEY"])
        self.assertEqual((3, 8), kwargs["timeout"])
        params = dict(kwargs["params"])
        signature = params.pop("signature")
        self.assertEqual(
            hmac.new(b"offline-api-secret", urlencode(params).encode("ascii"), hashlib.sha256).hexdigest(),
            signature,
        )
        self.assertEqual("BTCUSDT", params.pop("symbol"))
        self.assertEqual("SELL", params.pop("side"))
        self.assertEqual("STOP_LOSS", params.pop("type"))
        self.assertEqual("0.0399", params.pop("quantity"))
        self.assertEqual("95.00", params.pop("stopPrice"))
        self.assertEqual("residual-stop-01", params.pop("newClientOrderId"))
        self.assertEqual("FULL", params.pop("newOrderRespType"))
        self.assertEqual(5000, params.pop("recvWindow"))
        self.assertGreater(params.pop("timestamp"), 0)
        self.assertEqual({}, params)
        self.assertNotIn("offline-api-secret", repr(post.call_args))

    def test_residual_stop_transport_rejects_broad_or_invalid_submission_before_network(self):
        transport = SpotResidualStopTransport("offline-api-key", "offline-api-secret")
        bad_requests = (
            {"symbol": "BTCUSDT", "side": "BUY", "type": "STOP_LOSS", "quantity": "0.1", "stopPrice": "95",
             "newClientOrderId": "residual-stop-02", "newOrderRespType": "FULL"},
            {"symbol": "BTCUSDT", "side": "SELL", "type": "MARKET", "quantity": "0.1", "stopPrice": "95",
             "newClientOrderId": "residual-stop-02", "newOrderRespType": "FULL"},
            {"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_LOSS", "quantity": "0.1", "stopPrice": "95",
             "newClientOrderId": "bad&signature=x", "newOrderRespType": "FULL"},
        )
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.post") as post:
            for request in bad_requests:
                with self.subTest(request=request), self.assertRaises(LiveTradingSafetyError):
                    transport.place_stop_loss_sell(request)
        post.assert_not_called()

    def test_symbol_filters_and_public_prices_are_exact_symbol_fixed_host_gets(self):
        info = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING", "filters": []}]}
        with patch("app.integrations.exchanges.binance.orders.spot_user_data_admin_runtime.requests.get") as get:
            get.side_effect = [
                self.response(info),
                self.response({"symbol": "BTCUSDT", "price": "100.01"}),
                self.response({"symbol": "BTCUSDT", "mins": 5, "price": "100.02", "closeTime": 1}),
            ]
            self.assertEqual(info["symbols"][0], self.transport.get_symbol_info(symbol="BTCUSDT"))
            self.assertEqual(Decimal("100.01"), self.transport.get_last_price(symbol="BTCUSDT"))
            self.assertEqual({"symbol": "BTCUSDT", "mins": 5, "price": "100.02"}, self.transport.get_average_price(symbol="BTCUSDT"))
        self.assertEqual(3, get.call_count)
        expected_paths = (
            "https://api.binance.com/api/v3/exchangeInfo",
            "https://api.binance.com/api/v3/ticker/price",
            "https://api.binance.com/api/v3/avgPrice",
        )
        for call, expected_path in zip(get.call_args_list, expected_paths, strict=True):
            args, kwargs = call
            self.assertEqual(expected_path, args[0])
            self.assertEqual({"symbol": "BTCUSDT"}, kwargs["params"])
            self.assertNotIn("headers", kwargs)


if __name__ == "__main__":
    unittest.main()
