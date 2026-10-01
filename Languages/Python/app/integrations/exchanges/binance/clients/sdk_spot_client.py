from __future__ import annotations

from .sdk_common_runtime import (
    _SDKBaseClient,
    _SPOT_REST_PROD,
    _SPOT_REST_TESTNET,
    _SpotConfig,
    _SpotCancelReplaceCancelRestrictionsEnum,
    _SpotCancelReplaceModeEnum,
    _SpotCancelReplaceRespEnum,
    _SpotCancelReplaceSideEnum,
    _SpotCancelReplaceTimeInForceEnum,
    _SpotCancelReplaceTypeEnum,
    _SpotOrderRespEnum,
    _SpotOrderSideEnum,
    _SpotOrderTypeEnum,
    _SpotOpoOrderRespEnum,
    _SpotOpoPendingSideEnum,
    _SpotOpoPendingTypeEnum,
    _SpotOpoWorkingSideEnum,
    _SpotOpoWorkingTimeInForceEnum,
    _SpotOpoWorkingTypeEnum,
    _SpotRestAPI,
    _SpotStpEnum,
    _SpotTimeInForceEnum,
    _enum_value,
    _is_testnet_mode,
    _maybe_float,
    _maybe_int,
)


class BinanceSDKSpotClient(_SDKBaseClient):
    def __init__(self, api_key, api_secret, *, mode="Live"):
        if _SpotRestAPI is None or _SpotConfig is None or _SPOT_REST_PROD is None:
            raise RuntimeError("binance-sdk-spot library is not available")
        super().__init__(api_key)
        self.mode = mode
        base = _SPOT_REST_TESTNET if _is_testnet_mode(mode) else _SPOT_REST_PROD
        self._base_rest_url = base.rstrip("/")
        configuration = _SpotConfig(
            api_key=api_key or "",
            api_secret=api_secret or "",
            base_path=self._base_rest_url,
            timeout=5000,
        )
        self._rest = _SpotRestAPI(configuration)

    def get_exchange_info(self, **params):
        return self._call(self._rest.exchange_info, **params)

    def get_symbol_info(self, symbol: str):
        data = self._call(self._rest.exchange_info, symbol=symbol)
        if isinstance(data, dict):
            symbols = data.get("symbols") or []
            if symbols:
                return symbols[0]
        return None

    def get_account(self, **params):
        return self._call(
            self._rest.get_account,
            omit_zero_balances=params.get("omitZeroBalances"),
            recv_window=params.get("recvWindow"),
        )

    def get_symbol_ticker(self, symbol: str | None = None, **params):
        return self._call(
            self._rest.ticker_price,
            symbol=symbol or params.get("symbol"),
        )

    def get_klines(self, symbol: str, interval: str, limit: int = 500, **params):
        payload = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if params.get("startTime") is not None:
            payload["startTime"] = params.get("startTime")
        if params.get("endTime") is not None:
            payload["endTime"] = params.get("endTime")
        url = f"{self._base_rest_url}/api/v3/klines"
        return self._http_get(url, params=payload)

    def create_order(self, **params):
        side = _enum_value(_SpotOrderSideEnum, params.get("side"))
        order_type = _enum_value(_SpotOrderTypeEnum, params.get("type"))
        time_in_force = _enum_value(_SpotTimeInForceEnum, params.get("timeInForce"))
        resp_type = _enum_value(_SpotOrderRespEnum, params.get("newOrderRespType"))
        stp_mode = _enum_value(_SpotStpEnum, params.get("selfTradePreventionMode"))
        return self._call(
            self._rest.new_order,
            symbol=params.get("symbol"),
            side=side,
            type=order_type,
            time_in_force=time_in_force,
            quantity=_maybe_float(params.get("quantity")),
            quote_order_qty=_maybe_float(params.get("quoteOrderQty")),
            price=_maybe_float(params.get("price")),
            new_client_order_id=params.get("newClientOrderId"),
            stop_price=_maybe_float(params.get("stopPrice")),
            trailing_delta=_maybe_int(params.get("trailingDelta")),
            iceberg_qty=_maybe_float(params.get("icebergQty")),
            new_order_resp_type=resp_type,
            self_trade_prevention_mode=stp_mode,
            recv_window=params.get("recvWindow"),
        )

    def create_order_list_opo(self, **params):
        endpoint = getattr(self._rest, "order_list_opo", None)
        enums = (
            _SpotOpoWorkingTypeEnum,
            _SpotOpoWorkingSideEnum,
            _SpotOpoPendingTypeEnum,
            _SpotOpoPendingSideEnum,
            _SpotOpoOrderRespEnum,
            _SpotOpoWorkingTimeInForceEnum,
        )
        if not callable(endpoint) or any(enum_type is None for enum_type in enums):
            raise RuntimeError("installed Binance Spot SDK does not support OPO order lists")
        return self._call(
            endpoint,
            symbol=params.get("symbol"),
            working_type=_enum_value(_SpotOpoWorkingTypeEnum, params.get("workingType")),
            working_side=_enum_value(_SpotOpoWorkingSideEnum, params.get("workingSide")),
            working_price=_maybe_float(params.get("workingPrice")),
            working_quantity=_maybe_float(params.get("workingQuantity")),
            pending_type=_enum_value(_SpotOpoPendingTypeEnum, params.get("pendingType")),
            pending_side=_enum_value(_SpotOpoPendingSideEnum, params.get("pendingSide")),
            list_client_order_id=params.get("listClientOrderId"),
            new_order_resp_type=_enum_value(_SpotOpoOrderRespEnum, params.get("newOrderRespType")),
            working_client_order_id=params.get("workingClientOrderId"),
            working_time_in_force=_enum_value(
                _SpotOpoWorkingTimeInForceEnum, params.get("workingTimeInForce"),
            ),
            pending_client_order_id=params.get("pendingClientOrderId"),
            pending_stop_price=_maybe_float(params.get("pendingStopPrice")),
            recv_window=_maybe_float(params.get("recvWindow")),
        )

    def get_order_list(self, **params):
        return self._call(
            self._rest.get_order_list,
            order_list_id=_maybe_int(params.get("orderListId")),
            orig_client_order_id=params.get("origClientOrderId"),
            recv_window=_maybe_float(params.get("recvWindow")),
        )

    def get_order(self, **params):
        endpoint = getattr(self._rest, "get_order", None)
        if not callable(endpoint):
            raise RuntimeError("installed Binance Spot SDK does not support exact order queries")
        return self._call(
            endpoint,
            symbol=params.get("symbol"),
            order_id=_maybe_int(params.get("orderId")),
            orig_client_order_id=params.get("origClientOrderId"),
            recv_window=_maybe_float(params.get("recvWindow")),
        )

    def cancel_order_list(self, **params):
        return self._call(
            self._rest.delete_order_list,
            symbol=params.get("symbol"),
            order_list_id=_maybe_int(params.get("orderListId")),
            list_client_order_id=params.get("listClientOrderId"),
            new_client_order_id=params.get("newClientOrderId"),
            recv_window=_maybe_float(params.get("recvWindow")),
        )

    def cancel_replace_order(self, **params):
        endpoint = getattr(self._rest, "order_cancel_replace", None)
        enums = (
            _SpotCancelReplaceSideEnum,
            _SpotCancelReplaceTypeEnum,
            _SpotCancelReplaceModeEnum,
            _SpotCancelReplaceCancelRestrictionsEnum,
            _SpotCancelReplaceRespEnum,
        )
        if not callable(endpoint) or any(enum_type is None for enum_type in enums):
            raise RuntimeError("installed Binance Spot SDK does not support cancel-replace")
        side = _enum_value(_SpotCancelReplaceSideEnum, params.get("side"))
        order_type = _enum_value(_SpotCancelReplaceTypeEnum, params.get("type"))
        replace_mode = _enum_value(_SpotCancelReplaceModeEnum, params.get("cancelReplaceMode"))
        cancel_restrictions = _enum_value(
            _SpotCancelReplaceCancelRestrictionsEnum,
            params.get("cancelRestrictions"),
        )
        response_type = _enum_value(_SpotCancelReplaceRespEnum, params.get("newOrderRespType"))
        if any(value is None for value in (side, order_type, replace_mode, cancel_restrictions, response_type)):
            raise RuntimeError("installed Binance Spot SDK does not support the requested cancel-replace options")
        return self._call(
            endpoint,
            symbol=params.get("symbol"),
            side=side,
            type=order_type,
            cancel_replace_mode=replace_mode,
            time_in_force=_enum_value(_SpotCancelReplaceTimeInForceEnum, params.get("timeInForce")),
            quantity=_maybe_float(params.get("quantity")),
            quote_order_qty=_maybe_float(params.get("quoteOrderQty")),
            price=_maybe_float(params.get("price")),
            cancel_orig_client_order_id=params.get("cancelOrigClientOrderId"),
            cancel_new_client_order_id=params.get("cancelNewClientOrderId"),
            cancel_order_id=_maybe_int(params.get("cancelOrderId")),
            cancel_restrictions=cancel_restrictions,
            new_client_order_id=params.get("newClientOrderId"),
            stop_price=_maybe_float(params.get("stopPrice")),
            trailing_delta=_maybe_int(params.get("trailingDelta")),
            iceberg_qty=_maybe_float(params.get("icebergQty")),
            new_order_resp_type=response_type,
            recv_window=_maybe_float(params.get("recvWindow")),
        )

    def ticker_price(self, **params):
        return self.get_symbol_ticker(**params)
