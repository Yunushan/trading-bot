from __future__ import annotations

from .sdk_common_runtime import (
    _SDKBaseClient,
    _USDS_REST_PROD,
    _USDS_REST_TESTNET,
    _UsdsConfig,
    _UsdsMarginTypeEnum,
    _UsdsOrderRespEnum,
    _UsdsOrderSideEnum,
    _UsdsPositionSideEnum,
    _UsdsPriceMatchEnum,
    _UsdsRestAPI,
    _UsdsStpEnum,
    _UsdsTimeInForceEnum,
    _UsdsWorkingTypeEnum,
    _bool_to_str,
    _enum_value,
    _is_testnet_mode,
    _maybe_float,
    _maybe_int,
)


class BinanceSDKUsdsFuturesClient(_SDKBaseClient):
    def __init__(self, api_key, api_secret, *, mode="Live"):
        if _UsdsRestAPI is None or _UsdsConfig is None or _USDS_REST_PROD is None:
            raise RuntimeError("binance-sdk-derivatives-trading-usds-futures library is not available")
        super().__init__(api_key)
        self.mode = mode
        base = _USDS_REST_TESTNET if _is_testnet_mode(mode) else _USDS_REST_PROD
        self._base_rest_url = base.rstrip("/")
        self._api_prefix = "/fapi"
        configuration = _UsdsConfig(
            api_key=api_key or "",
            api_secret=api_secret or "",
            base_path=self._base_rest_url,
            timeout=5000,
        )
        self._rest = _UsdsRestAPI(configuration)

    def futures_account_trades(self, symbol: str | None = None, **params):
        return self._call(
            self._rest.account_trade_list,
            symbol=symbol or params.get("symbol"),
            order_id=params.get("orderId"),
            start_time=params.get("startTime"),
            end_time=params.get("endTime"),
            from_id=params.get("fromId"),
            limit=params.get("limit"),
            recv_window=params.get("recvWindow"),
        )

    def futures_position_information(self, symbol: str | None = None, **params):
        data = self._call(
            self._rest.position_information_v3,
            symbol=symbol or params.get("symbol"),
            recv_window=params.get("recvWindow"),
        )
        return data or []

    def futures_position_risk(self, symbol: str | None = None, **params):
        return self.futures_position_information(symbol=symbol, **params)

    def futures_change_leverage(self, symbol: str, leverage: int | None = None, **params):
        lev = _maybe_int(params.get("leverage", leverage))
        return self._call(
            self._rest.change_initial_leverage,
            symbol=symbol,
            leverage=lev,
            recv_window=params.get("recvWindow"),
        )

    def futures_change_margin_type(self, symbol: str, marginType: str | None = None, **params):
        margin_value = params.get("marginType", marginType)
        margin_enum = _enum_value(_UsdsMarginTypeEnum, margin_value)
        if margin_enum is None and margin_value is not None:
            try:
                margin_enum = _UsdsMarginTypeEnum[str(margin_value).upper()]
            except Exception:
                margin_enum = None
        return self._call(
            self._rest.change_margin_type,
            symbol=symbol,
            margin_type=margin_enum,
            recv_window=params.get("recvWindow"),
        )

    def futures_change_position_mode(self, dualSidePosition: bool | str | None = None, **params):
        flag = params.get("dualSidePosition", dualSidePosition)
        return self._call(
            self._rest.change_position_mode,
            dual_side_position=_bool_to_str(flag),
            recv_window=params.get("recvWindow"),
        )

    def futures_get_position_mode(self, **params):
        data = self._call(self._rest.get_current_position_mode, recv_window=params.get("recvWindow"))
        if isinstance(data, dict) and "dualSidePosition" in data:
            val = data["dualSidePosition"]
            if isinstance(val, str):
                data["dualSidePosition"] = val.lower() == "true"
        return data

    def futures_cancel_all_open_orders(self, symbol: str | None = None, **params):
        return self._call(
            self._rest.cancel_all_open_orders,
            symbol=symbol or params.get("symbol"),
            recv_window=params.get("recvWindow"),
        )

    def futures_get_open_orders(self, symbol: str | None = None, **params):
        return self._call(
            self._rest.current_all_open_orders,
            symbol=symbol or params.get("symbol"),
            recv_window=params.get("recvWindow"),
        )

    def futures_exchange_info(self, **params):
        return self._call(self._rest.exchange_information, **params)

    def futures_leverage_bracket(self, symbol: str | None = None, **params):
        return self._call(
            self._rest.notional_and_leverage_brackets,
            symbol=symbol or params.get("symbol"),
            recv_window=params.get("recvWindow"),
        )

    def futures_account_balance(self, **params):
        return self._call(
            self._rest.futures_account_balance_v3,
            recv_window=params.get("recvWindow"),
        )

    def futures_account(self, **params):
        return self._call(
            self._rest.account_information_v3,
            recv_window=params.get("recvWindow"),
        )

    def futures_symbol_ticker(self, symbol: str | None = None, **params):
        data = self._call(
            self._rest.symbol_price_ticker,
            symbol=symbol or params.get("symbol"),
        )
        if isinstance(data, list):
            data = data[0] if data else {}
        return data

    def futures_book_ticker(self, symbol: str | None = None, **params):
        data = self._call(
            self._rest.symbol_order_book_ticker,
            symbol=symbol or params.get("symbol"),
        )
        if isinstance(data, list):
            data = data[0] if data else {}
        return data

    def futures_change_multi_assets_margin(self, **params):
        flag = params.get("multiAssetsMargin")
        return self._call(
            self._rest.change_multi_assets_mode,
            multi_assets_margin=_bool_to_str(flag),
            recv_window=params.get("recvWindow"),
        )

    def futures_multi_assets_margin(self, **params):
        return self.futures_change_multi_assets_margin(**params)

    def futures_set_multi_assets_margin(self, **params):
        return self.futures_change_multi_assets_margin(**params)

    def futures_klines(self, symbol: str, interval: str, limit: int = 500, **params):
        payload = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if params.get("startTime") is not None:
            payload["startTime"] = params.get("startTime")
        if params.get("endTime") is not None:
            payload["endTime"] = params.get("endTime")
        url = f"{self._base_rest_url}{self._api_prefix}/v1/klines"
        return self._http_get(url, params=payload)

    def _request_futures_api(self, method, path, signed=False, version=1, **kwargs):
        key = path.lower().strip()
        if key == "multiassetsmargin" and method.upper() == "POST":
            data = dict(kwargs.get("data") or kwargs.get("params") or {})
            return self.futures_change_multi_assets_margin(**data)
        raise NotImplementedError(f"Raw futures API path '{path}' not supported for SDK adapter")

    def futures_create_order(self, **params):
        symbol = params.get("symbol")
        side = _enum_value(_UsdsOrderSideEnum, params.get("side"))
        position_side = _enum_value(_UsdsPositionSideEnum, params.get("positionSide"))
        time_in_force = _enum_value(_UsdsTimeInForceEnum, params.get("timeInForce"))
        working_type = _enum_value(_UsdsWorkingTypeEnum, params.get("workingType"))
        price_match = _enum_value(_UsdsPriceMatchEnum, params.get("priceMatch"))
        resp_type = _enum_value(_UsdsOrderRespEnum, params.get("newOrderRespType"))
        stp_mode = _enum_value(_UsdsStpEnum, params.get("selfTradePreventionMode"))
        reduce_only = _bool_to_str(params.get("reduceOnly"))
        close_position = _bool_to_str(params.get("closePosition"))
        price_protect = _bool_to_str(params.get("priceProtect"))
        return self._call(
            self._rest.new_order,
            symbol=symbol,
            side=side,
            type=params.get("type"),
            position_side=position_side,
            time_in_force=time_in_force,
            quantity=_maybe_float(params.get("quantity")),
            reduce_only=reduce_only,
            price=_maybe_float(params.get("price")),
            new_client_order_id=params.get("newClientOrderId"),
            stop_price=_maybe_float(params.get("stopPrice")),
            close_position=close_position,
            activation_price=_maybe_float(params.get("activationPrice")),
            callback_rate=_maybe_float(params.get("callbackRate")),
            working_type=working_type,
            price_protect=price_protect,
            new_order_resp_type=resp_type,
            price_match=price_match,
            self_trade_prevention_mode=stp_mode,
            recv_window=params.get("recvWindow"),
            good_till_date=_maybe_int(params.get("goodTillDate")),
        )
