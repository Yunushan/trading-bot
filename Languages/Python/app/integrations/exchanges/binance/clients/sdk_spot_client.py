from __future__ import annotations

from .sdk_common_runtime import (
    _SDKBaseClient,
    _SPOT_REST_PROD,
    _SPOT_REST_TESTNET,
    _SpotConfig,
    _SpotOrderRespEnum,
    _SpotOrderSideEnum,
    _SpotOrderTypeEnum,
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

    def ticker_price(self, **params):
        return self.get_symbol_ticker(**params)
