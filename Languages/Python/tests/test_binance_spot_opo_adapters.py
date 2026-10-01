from __future__ import annotations

import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.exchanges.binance.clients import connector_clients, sdk_spot_client


class _Values(Enum):
    LIMIT = "LIMIT"
    BUY = "BUY"
    SELL = "SELL"
    STOP_LOSS = "STOP_LOSS"
    MARKET = "MARKET"
    FULL = "FULL"
    FOK = "FOK"
    STOP_ON_FAILURE = "STOP_ON_FAILURE"
    ONLY_NEW = "ONLY_NEW"


class BinanceSpotOpoAdapterTests(unittest.TestCase):
    def test_sdk_adapter_maps_opo_request_and_exact_list_queries(self):
        calls = []

        def endpoint(**kwargs):
            calls.append(("opo", kwargs))
            return {"listStatusType": "EXEC_STARTED"}

        def get_list(**kwargs):
            calls.append(("get", kwargs))
            return {"listStatusType": "EXEC_STARTED"}

        def get_order(**kwargs):
            calls.append(("get_order", kwargs))
            return {"status": "FILLED"}

        def delete_list(**kwargs):
            calls.append(("delete", kwargs))
            return {"listStatusType": "ALL_DONE"}

        def cancel_replace(**kwargs):
            calls.append(("cancel_replace", kwargs))
            return {"cancelResult": "SUCCESS", "newOrderResult": "SUCCESS"}

        client = sdk_spot_client.BinanceSDKSpotClient.__new__(sdk_spot_client.BinanceSDKSpotClient)
        client._rest = SimpleNamespace(
            order_list_opo=endpoint,
            get_order_list=get_list,
            get_order=get_order,
            delete_order_list=delete_list,
            order_cancel_replace=cancel_replace,
        )
        enum_patches = {
            "_SpotOpoWorkingTypeEnum": _Values,
            "_SpotOpoWorkingSideEnum": _Values,
            "_SpotOpoPendingTypeEnum": _Values,
            "_SpotOpoPendingSideEnum": _Values,
            "_SpotOpoOrderRespEnum": _Values,
            "_SpotOpoWorkingTimeInForceEnum": _Values,
            "_SpotCancelReplaceSideEnum": _Values,
            "_SpotCancelReplaceTypeEnum": _Values,
            "_SpotCancelReplaceModeEnum": _Values,
            "_SpotCancelReplaceCancelRestrictionsEnum": _Values,
            "_SpotCancelReplaceTimeInForceEnum": _Values,
            "_SpotCancelReplaceRespEnum": _Values,
        }
        with patch.multiple(sdk_spot_client, **enum_patches):
            client.create_order_list_opo(
                symbol="BTCUSDT",
                workingType="LIMIT",
                workingSide="BUY",
                workingPrice="100.00",
                workingQuantity="0.01",
                workingTimeInForce="FOK",
                workingClientOrderId="working-1",
                listClientOrderId="list-1",
                pendingType="STOP_LOSS",
                pendingSide="SELL",
                pendingStopPrice="95.00",
                pendingClientOrderId="stop-1",
                newOrderRespType="FULL",
            )
            client.get_order_list(origClientOrderId="list-1")
            client.get_order(symbol="BTCUSDT", origClientOrderId="exit-1")
            client.cancel_order_list(symbol="BTCUSDT", listClientOrderId="list-1")
            client.cancel_replace_order(
                symbol="BTCUSDT",
                side="SELL",
                type="MARKET",
                cancelReplaceMode="STOP_ON_FAILURE",
                cancelRestrictions="ONLY_NEW",
                cancelOrigClientOrderId="stop-1",
                cancelNewClientOrderId="cancel-1",
                quantity="0.01",
                newClientOrderId="exit-1",
                newOrderRespType="FULL",
            )

        request = calls[0][1]
        self.assertEqual("BTCUSDT", request["symbol"])
        self.assertIs(_Values.LIMIT, request["working_type"])
        self.assertIs(_Values.BUY, request["working_side"])
        self.assertEqual(100.0, request["working_price"])
        self.assertEqual(0.01, request["working_quantity"])
        self.assertIs(_Values.FOK, request["working_time_in_force"])
        self.assertIs(_Values.STOP_LOSS, request["pending_type"])
        self.assertIs(_Values.SELL, request["pending_side"])
        self.assertEqual(95.0, request["pending_stop_price"])
        self.assertNotIn("pending_quantity", request)
        self.assertEqual(("get", {"orig_client_order_id": "list-1"}), calls[1])
        self.assertEqual(("get_order", {
            "symbol": "BTCUSDT", "orig_client_order_id": "exit-1",
        }), calls[2])
        self.assertEqual(("delete", {
            "symbol": "BTCUSDT",
            "list_client_order_id": "list-1",
        }), calls[3])
        replace = calls[4][1]
        self.assertEqual("BTCUSDT", replace["symbol"])
        self.assertIs(_Values.SELL, replace["side"])
        self.assertIs(_Values.MARKET, replace["type"])
        self.assertIs(_Values.STOP_ON_FAILURE, replace["cancel_replace_mode"])
        self.assertIs(_Values.ONLY_NEW, replace["cancel_restrictions"])
        self.assertEqual("stop-1", replace["cancel_orig_client_order_id"])
        self.assertEqual("cancel-1", replace["cancel_new_client_order_id"])
        self.assertEqual(0.01, replace["quantity"])
        self.assertEqual("exit-1", replace["new_client_order_id"])

    def test_sdk_adapter_fails_closed_when_installed_sdk_lacks_opo(self):
        client = sdk_spot_client.BinanceSDKSpotClient.__new__(sdk_spot_client.BinanceSDKSpotClient)
        client._rest = SimpleNamespace(order_list_opo=lambda **_kwargs: self.fail("OPO call must not be sent"))
        with patch.multiple(
            sdk_spot_client,
            _SpotOpoWorkingTypeEnum=None,
            _SpotOpoWorkingSideEnum=None,
            _SpotOpoPendingTypeEnum=None,
            _SpotOpoPendingSideEnum=None,
            _SpotOpoOrderRespEnum=None,
            _SpotOpoWorkingTimeInForceEnum=None,
        ):
            with self.assertRaisesRegex(RuntimeError, "does not support OPO"):
                client.create_order_list_opo(symbol="BTCUSDT")

    def test_sdk_adapter_fails_closed_when_cancel_restrictions_are_unavailable(self):
        client = sdk_spot_client.BinanceSDKSpotClient.__new__(sdk_spot_client.BinanceSDKSpotClient)
        client._rest = SimpleNamespace(
            order_cancel_replace=lambda **_kwargs: self.fail("cancel-replace call must not be sent"),
        )
        with patch.multiple(
            sdk_spot_client,
            _SpotCancelReplaceSideEnum=_Values,
            _SpotCancelReplaceTypeEnum=_Values,
            _SpotCancelReplaceModeEnum=_Values,
            _SpotCancelReplaceCancelRestrictionsEnum=None,
            _SpotCancelReplaceTimeInForceEnum=_Values,
            _SpotCancelReplaceRespEnum=_Values,
        ):
            with self.assertRaisesRegex(RuntimeError, "does not support cancel-replace"):
                client.cancel_replace_order(
                    symbol="BTCUSDT", side="SELL", type="MARKET",
                    cancelReplaceMode="STOP_ON_FAILURE", cancelRestrictions="ONLY_NEW",
                    cancelOrigClientOrderId="stop-9", quantity="0.01",
                    newClientOrderId="exit-9", newOrderRespType="FULL",
                )

    def test_official_connector_uses_signed_spot_endpoints(self):
        calls = []

        class Spot:
            def sign_request(self, method, path, payload):
                calls.append((method, path, payload))
                return {"method": method, "path": path}

        adapter = connector_clients.OfficialConnectorAdapter.__new__(connector_clients.OfficialConnectorAdapter)
        adapter._spot = Spot()
        adapter._bw_throttled = True
        adapter._bw_throttle = lambda path: calls.append(("throttle", path))

        adapter.create_order_list_opo(symbol="BTCUSDT", listClientOrderId="list-2")
        adapter.get_order_list(origClientOrderId="list-2")
        adapter.get_order(symbol="BTCUSDT", origClientOrderId="exit-2")
        adapter.cancel_order_list(symbol="BTCUSDT", listClientOrderId="list-2")
        replace_request = {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "MARKET",
            "cancelReplaceMode": "STOP_ON_FAILURE",
            "cancelOrigClientOrderId": "stop-2",
            "cancelNewClientOrderId": "cancel-2",
            "quantity": "0.01",
            "newClientOrderId": "exit-2",
        }
        adapter.cancel_replace_order(**replace_request)

        self.assertEqual("POST", calls[1][0])
        self.assertEqual("/api/v3/orderList/opo", calls[1][1])
        self.assertEqual("GET", calls[3][0])
        self.assertEqual("/api/v3/orderList", calls[3][1])
        self.assertEqual("GET", calls[5][0])
        self.assertEqual("/api/v3/order", calls[5][1])
        self.assertEqual("DELETE", calls[7][0])
        self.assertEqual("/api/v3/orderList", calls[7][1])
        self.assertEqual(("POST", "/api/v3/order/cancelReplace", replace_request), calls[9])
        self.assertNotIn("sign_request", [row[1] for row in calls if row[0] == "throttle"])

    def test_ccxt_adapter_uses_signed_order_list_route(self):
        calls = []

        class Exchange:
            def request(self, path, **kwargs):
                calls.append((path, kwargs))
                return {"path": path}

        adapter = connector_clients.CcxtBinanceAdapter.__new__(connector_clients.CcxtBinanceAdapter)
        adapter._exchange = Exchange()
        adapter._bw_throttle = lambda _path: None

        adapter.create_order_list_opo(symbol="BTCUSDT", listClientOrderId="list-3")
        adapter.get_order_list(origClientOrderId="list-3")
        adapter.get_order(symbol="BTCUSDT", origClientOrderId="exit-3")
        adapter.cancel_order_list(symbol="BTCUSDT", listClientOrderId="list-3")
        replace_request = {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "MARKET",
            "cancelReplaceMode": "STOP_ON_FAILURE",
            "cancelOrigClientOrderId": "stop-3",
            "cancelNewClientOrderId": "cancel-3",
            "quantity": "0.01",
            "newClientOrderId": "exit-3",
        }
        adapter.cancel_replace_order(**replace_request)

        self.assertEqual("orderList/opo", calls[0][0])
        self.assertEqual(("private", "POST"), (calls[0][1]["api"], calls[0][1]["method"]))
        self.assertEqual("orderList", calls[1][0])
        self.assertEqual(("private", "GET"), (calls[1][1]["api"], calls[1][1]["method"]))
        self.assertEqual("order", calls[2][0])
        self.assertEqual(("private", "GET"), (calls[2][1]["api"], calls[2][1]["method"]))
        self.assertEqual("orderList", calls[3][0])
        self.assertEqual(("private", "DELETE"), (calls[3][1]["api"], calls[3][1]["method"]))
        self.assertEqual("order/cancelReplace", calls[4][0])
        self.assertEqual(("private", "POST"), (calls[4][1]["api"], calls[4][1]["method"]))
        self.assertEqual(replace_request, calls[4][1]["params"])


if __name__ == "__main__":
    unittest.main()
