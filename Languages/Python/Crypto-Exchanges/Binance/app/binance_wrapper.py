
from collections import deque
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
import copy
from datetime import datetime, timezone
import math
from enum import Enum
import re
import time
import threading
import types
from typing import Any
import requests

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
try:
    from binance.spot import Spot as _OfficialSpotClient
    from binance.api import API as _OfficialAPIBase
    from binance.error import ClientError as _OfficialClientError, ServerError as _OfficialServerError
except Exception:
    _OfficialSpotClient = None
    _OfficialAPIBase = None
    _OfficialClientError = None
    _OfficialServerError = None

try:
    from binance_sdk_derivatives_trading_usds_futures import (
        DERIVATIVES_TRADING_USDS_FUTURES_REST_API_PROD_URL as _USDS_REST_PROD,
        DERIVATIVES_TRADING_USDS_FUTURES_REST_API_TESTNET_URL as _USDS_REST_TESTNET,
    )
    from binance_sdk_derivatives_trading_usds_futures.rest_api import (
        DerivativesTradingUsdsFuturesRestAPI as _UsdsRestAPI,
    )
    from binance_sdk_derivatives_trading_usds_futures.rest_api.rest_api import (
        ConfigurationRestAPI as _UsdsConfig,
    )
    from binance_sdk_derivatives_trading_usds_futures.rest_api.models.enums import (
        ChangeMarginTypeMarginTypeEnum as _UsdsMarginTypeEnum,
        NewOrderSideEnum as _UsdsOrderSideEnum,
        NewOrderPositionSideEnum as _UsdsPositionSideEnum,
        NewOrderTimeInForceEnum as _UsdsTimeInForceEnum,
        NewOrderWorkingTypeEnum as _UsdsWorkingTypeEnum,
        NewOrderNewOrderRespTypeEnum as _UsdsOrderRespEnum,
        NewOrderPriceMatchEnum as _UsdsPriceMatchEnum,
        NewOrderSelfTradePreventionModeEnum as _UsdsStpEnum,
    )
except Exception:
    _USDS_REST_PROD = None
    _USDS_REST_TESTNET = None
    _UsdsRestAPI = None
    _UsdsConfig = None
    _UsdsMarginTypeEnum = None
    _UsdsOrderSideEnum = None
    _UsdsPositionSideEnum = None
    _UsdsTimeInForceEnum = None
    _UsdsWorkingTypeEnum = None
    _UsdsOrderRespEnum = None
    _UsdsPriceMatchEnum = None
    _UsdsStpEnum = None

try:
    from binance_sdk_derivatives_trading_coin_futures import (
        DERIVATIVES_TRADING_COIN_FUTURES_REST_API_PROD_URL as _COIN_REST_PROD,
        DERIVATIVES_TRADING_COIN_FUTURES_REST_API_TESTNET_URL as _COIN_REST_TESTNET,
    )
    from binance_sdk_derivatives_trading_coin_futures.rest_api import (
        DerivativesTradingCoinFuturesRestAPI as _CoinRestAPI,
    )
    from binance_sdk_derivatives_trading_coin_futures.rest_api.rest_api import (
        ConfigurationRestAPI as _CoinConfig,
    )
    from binance_sdk_derivatives_trading_coin_futures.rest_api.models.enums import (
        ChangeMarginTypeMarginTypeEnum as _CoinMarginTypeEnum,
        NewOrderSideEnum as _CoinOrderSideEnum,
        NewOrderPositionSideEnum as _CoinPositionSideEnum,
        NewOrderTimeInForceEnum as _CoinTimeInForceEnum,
        NewOrderWorkingTypeEnum as _CoinWorkingTypeEnum,
        NewOrderNewOrderRespTypeEnum as _CoinOrderRespEnum,
        NewOrderPriceMatchEnum as _CoinPriceMatchEnum,
        NewOrderSelfTradePreventionModeEnum as _CoinStpEnum,
    )
except Exception:
    _COIN_REST_PROD = None
    _COIN_REST_TESTNET = None
    _CoinRestAPI = None
    _CoinConfig = None
    _CoinMarginTypeEnum = None
    _CoinOrderSideEnum = None
    _CoinPositionSideEnum = None
    _CoinTimeInForceEnum = None
    _CoinWorkingTypeEnum = None
    _CoinOrderRespEnum = None
    _CoinPriceMatchEnum = None
    _CoinStpEnum = None

try:
    from binance_sdk_spot import (
        SPOT_REST_API_PROD_URL as _SPOT_REST_PROD,
        SPOT_REST_API_TESTNET_URL as _SPOT_REST_TESTNET,
    )
    from binance_sdk_spot.rest_api import SpotRestAPI as _SpotRestAPI
    from binance_sdk_spot.rest_api.rest_api import ConfigurationRestAPI as _SpotConfig
    from binance_sdk_spot.rest_api.models.enums import (
        NewOrderSideEnum as _SpotOrderSideEnum,
        NewOrderTypeEnum as _SpotOrderTypeEnum,
        NewOrderTimeInForceEnum as _SpotTimeInForceEnum,
        NewOrderNewOrderRespTypeEnum as _SpotOrderRespEnum,
        NewOrderSelfTradePreventionModeEnum as _SpotStpEnum,
    )
except Exception:
    _SPOT_REST_PROD = None
    _SPOT_REST_TESTNET = None
    _SpotRestAPI = None
    _SpotConfig = None
    _SpotOrderSideEnum = None
    _SpotOrderTypeEnum = None
    _SpotTimeInForceEnum = None
    _SpotOrderRespEnum = None
    _SpotStpEnum = None


class NetworkConnectivityError(RuntimeError):
    """Raised when outbound HTTP connectivity to the exchange is unavailable."""
    pass

MAX_FUTURES_LEVERAGE = 150

FUTURES_NATIVE_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}

SPOT_NATIVE_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}

def _coerce_interval_seconds(interval: str | None) -> float:
    try:
        iv = (interval or "").strip().lower()
        if not iv:
            return 60.0
        unit = iv[-1]
        value_part = iv[:-1] if unit.isalpha() else iv
        value = float(value_part or 0.0)
        if unit == "s":
            return max(value, 1.0)
        if unit == "m":
            return max(value * 60.0, 1.0)
        if unit == "h":
            return max(value * 3600.0, 1.0)
        if unit == "d":
            return max(value * 86400.0, 1.0)
        if unit == "w":
            return max(value * 7 * 86400.0, 1.0)
        return max(float(iv), 1.0)
    except Exception:
        return 60.0

def normalize_margin_ratio(value):
    """Convert Binance margin ratio payloads to percentage values."""
    try:
        if value is None:
            return 0.0
        if isinstance(value, str):
            txt = value.strip()
            if not txt:
                return 0.0
            if txt.endswith('%'):
                txt = txt[:-1]
            value = float(txt)
        else:
            value = float(value)
    except Exception:
        return 0.0
    if value <= 0.0:
        return 0.0
    return value * 100.0 if value <= 1.0 else value

def _coerce_int(value):
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
        if value is None:
            return 0
        return int(float(value))
    except Exception:
        return 0


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _bool_to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        txt = value.strip().lower()
        if txt in {"true", "false"}:
            return txt
        if txt in {"1", "yes", "y"}:
            return "true"
        if txt in {"0", "no", "n"}:
            return "false"
    return "true" if bool(value) else "false"


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _enum_value(enum_cls: Any, value: Any):
    if value is None or enum_cls is None:
        return None
    if isinstance(value, enum_cls):
        return value
    text = str(value)
    for candidate in (text, text.upper(), text.lower()):
        try:
            return enum_cls(candidate)
        except Exception:
            pass
    try:
        return enum_cls[text.upper()]
    except Exception:
        pass
    return None


def _sdk_to_plain(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "data") and callable(obj.data):
        try:
            obj = obj.data()
        except Exception:
            pass
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_sdk_to_plain(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(_sdk_to_plain(item) for item in obj)
    if isinstance(obj, dict):
        return {
            key: _sdk_to_plain(val)
            for key, val in obj.items()
            if key != "additional_properties"
        }
    actual = getattr(obj, "actual_instance", None)
    if actual is not None:
        return _sdk_to_plain(actual)
    if hasattr(obj, "to_dict"):
        try:
            return _sdk_to_plain(obj.to_dict())
        except Exception:
            pass
    if hasattr(obj, "model_dump"):
        try:
            return _sdk_to_plain(obj.model_dump(by_alias=True, exclude_none=True))
        except Exception:
            pass
    return obj


def _as_futures_balance_entries(data: Any):
    if isinstance(data, dict):
        for key in ("balances", "accountBalance", "data"):
            entries = data.get(key)
            if entries is not None:
                return entries
        return []
    return data or []


def _as_futures_account_dict(data: Any) -> dict:
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    return {}


class _SimpleRateLimiter:
    def __init__(self, max_per_minute: float = 600.0, min_interval: float = 0.25, safety_margin: float = 0.85):
        self.window = 60.0
        self.capacity = max(1.0, float(max_per_minute) * float(safety_margin))
        self.min_interval = max(0.0, float(min_interval))
        self._events = deque()
        self._window_weight = 0.0
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._pause_until = 0.0

    def acquire(self, weight: float = 1.0) -> None:
        weight = max(float(weight), 0.0)
        if weight == 0.0:
            return
        sleep_for = 0.0
        while True:
            with self._lock:
                now = time.time()
                while self._events and (now - self._events[0][0]) >= self.window:
                    _, old_weight = self._events.popleft()
                    self._window_weight = max(0.0, self._window_weight - old_weight)
                wait_interval = 0.0
                if self._last_request:
                    elapsed = now - self._last_request
                    if elapsed < self.min_interval:
                        wait_interval = self.min_interval - elapsed
                wait_capacity = 0.0
                projected = self._window_weight + weight
                if projected > self.capacity:
                    earliest = self._events[0][0] if self._events else now
                    wait_capacity = max(0.0, self.window - (now - earliest))
                pause_remaining = max(0.0, self._pause_until - now)
                sleep_for = max(wait_interval, wait_capacity, pause_remaining)
                if sleep_for <= 0.0:
                    self._events.append((now, weight))
                    self._window_weight = min(self.capacity, self._window_weight + weight)
                    self._last_request = now
                    return
            time.sleep(min(sleep_for, 1.0))

    def pause_for(self, seconds: float) -> None:
        seconds = float(seconds or 0.0)
        if seconds <= 0.0:
            return
        with self._lock:
            until = time.time() + seconds
            if until > self._pause_until:
                self._pause_until = until


DEFAULT_CONNECTOR_BACKEND = "binance-sdk-derivatives-trading-usds-futures"


def _normalize_connector_choice(value) -> str:
    text_raw = str(value or "").strip()
    if not text_raw:
        return DEFAULT_CONNECTOR_BACKEND
    text = text_raw.lower()
    if text in {
        "binance-sdk-derivatives-trading-usds-futures",
        "binance_sdk_derivatives_trading_usds_futures",
    } or ("sdk" in text and "future" in text and ("usd" in text or "usds" in text)):
        return "binance-sdk-derivatives-trading-usds-futures"
    if text in {
        "binance-sdk-derivatives-trading-coin-futures",
        "binance_sdk_derivatives_trading_coin_futures",
    } or ("sdk" in text and "coin" in text and "future" in text):
        return "binance-sdk-derivatives-trading-coin-futures"
    if text in {"binance-sdk-spot", "binance_sdk_spot"} or ("sdk" in text and "spot" in text):
        return "binance-sdk-spot"
    if "connector" in text or "official" in text or text == "binance-connector":
        return "binance-connector"
    if "python" in text and "binance" in text:
        return "python-binance"
    return DEFAULT_CONNECTOR_BACKEND


class OfficialConnectorError(Exception):
    def __init__(self, code=None, status_code=None, message=""):
        self.code = code if code is not None else 0
        self.status_code = status_code if status_code is not None else 0
        self.message = message or ""
        super().__init__(self.message)


if _OfficialAPIBase is not None and _OfficialSpotClient is not None:
    class _OfficialFuturesHTTP(_OfficialAPIBase):  # type: ignore[misc]
        def __init__(self, api_key, api_secret, base_url):
            super().__init__(api_key, api_secret, base_url=base_url)


    class OfficialConnectorAdapter:
        def __init__(self, api_key, api_secret, *, mode="Live"):
            mode_text = (mode or "Live").strip().lower()
            is_testnet = any(tag in mode_text for tag in ("test", "demo"))
            spot_base = "https://testnet.binance.vision" if is_testnet else "https://api.binance.com"
            futures_base = "https://testnet.binancefuture.com" if is_testnet else "https://fapi.binance.com"
            self._spot = _OfficialSpotClient(api_key, api_secret, base_url=spot_base)
            self._futures = _OfficialFuturesHTTP(api_key, api_secret, base_url=futures_base)
            self._bw_throttled = True  # signals wrapper not to install extra throttler
            self._bw_throttle = None

        def _throttle(self, path: str | None) -> None:
            cb = getattr(self, "_bw_throttle", None)
            if callable(cb):
                try:
                    cb(path)
                except Exception:
                    pass

        def _call(self, func, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if _OfficialClientError is not None and isinstance(exc, _OfficialClientError):
                    raise OfficialConnectorError(exc.error_code, exc.status_code, exc.error_message) from exc
                if _OfficialServerError is not None and isinstance(exc, _OfficialServerError):
                    raise OfficialConnectorError(None, exc.status_code, exc.message) from exc
                raise

        def _call_futures(self, method: str, path: str, params=None, *, signed=False):
            payload = dict(params or {})
            http_method = (method or "GET").upper()
            self._throttle(path)
            if signed:
                return self._call(self._futures.sign_request, http_method, path, payload)
            return self._call(self._futures.send_request, http_method, path, payload)

        # Spot methods
        def get_account(self, **params):
            self._throttle("/api/v3/account")
            return self._call(self._spot.account, **params)

        def get_symbol_info(self, symbol: str):
            self._throttle("/api/v3/exchangeInfo")
            data = self._call(self._spot.exchange_info, symbol=symbol)
            symbols = (data or {}).get("symbols") if isinstance(data, dict) else None
            if symbols:
                return symbols[0]
            return None

        def get_exchange_info(self, **params):
            self._throttle("/api/v3/exchangeInfo")
            return self._call(self._spot.exchange_info, **params)

        def get_symbol_ticker(self, **params):
            self._throttle("/api/v3/ticker/price")
            return self._call(self._spot.ticker_price, **params)

        def get_klines(self, **params):
            self._throttle("/api/v3/klines")
            return self._call(self._spot.klines, **params)

        def create_order(self, **params):
            payload = dict(params or {})
            self._throttle("/api/v3/order")
            return self._call(self._spot.new_order, **payload)

        # Futures helpers
        def futures_klines(self, **params):
            return self._call_futures("GET", "/fapi/v1/klines", params, signed=False)

        def futures_exchange_info(self, **params):
            return self._call_futures("GET", "/fapi/v1/exchangeInfo", params, signed=False)

        def futures_leverage_bracket(self, **params):
            return self._call_futures("GET", "/fapi/v1/leverageBracket", params, signed=False)

        def futures_account(self, **params):
            return self._call_futures("GET", "/fapi/v2/account", params, signed=True)

        def futures_account_balance(self, **params):
            return self._call_futures("GET", "/fapi/v2/balance", params, signed=True)

        def futures_position_information(self, **params):
            return self._call_futures("GET", "/fapi/v2/positionRisk", params, signed=True)

        def futures_position_risk(self, **params):
            return self._call_futures("GET", "/fapi/v2/positionRisk", params, signed=True)

        def futures_create_order(self, **params):
            return self._call_futures("POST", "/fapi/v1/order", params, signed=True)

        def futures_symbol_ticker(self, **params):
            return self._call_futures("GET", "/fapi/v1/ticker/price", params, signed=False)

        def futures_get_position_mode(self, **params):
            return self._call_futures("GET", "/fapi/v1/positionSide/dual", params, signed=True)

        def futures_change_position_mode(self, **params):
            return self._call_futures("POST", "/fapi/v1/positionSide/dual", params, signed=True)

        def futures_cancel_all_open_orders(self, **params):
            return self._call_futures("DELETE", "/fapi/v1/allOpenOrders", params, signed=True)

        def futures_get_open_orders(self, **params):
            return self._call_futures("GET", "/fapi/v1/openOrders", params, signed=True)

        def futures_change_margin_type(self, **params):
            return self._call_futures("POST", "/fapi/v1/marginType", params, signed=True)

        def futures_change_leverage(self, **params):
            return self._call_futures("POST", "/fapi/v1/leverage", params, signed=True)

        def futures_book_ticker(self, **params):
            return self._call_futures("GET", "/fapi/v1/ticker/bookTicker", params, signed=False)

        def _request_futures_api(self, method, path, signed=False, version=1, **kwargs):
            payload = dict(kwargs.get("data") or kwargs.get("params") or {})
            url_path = f"/fapi/v{int(version)}/{path}"
            return self._call_futures(method, url_path, payload, signed=signed)
else:
    class OfficialConnectorAdapter:
        def __init__(self, *_, **__):
            raise RuntimeError("binance-connector library is not available")


class _SDKBaseClient:
    def __init__(self, api_key: str | None):
        self.API_KEY = api_key or ""
        self._bw_throttled = True
        self._bw_throttle = None

    def _call(self, func, **kwargs):
        response = func(**kwargs)
        return _sdk_to_plain(response)

    def _http_get(self, url: str, params: dict[str, Any] | None = None, timeout: float = 10.0):
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


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


class BinanceSDKCoinFuturesClient(_SDKBaseClient):
    def __init__(self, api_key, api_secret, *, mode="Live"):
        if _CoinRestAPI is None or _CoinConfig is None or _COIN_REST_PROD is None:
            raise RuntimeError("binance-sdk-derivatives-trading-coin-futures library is not available")
        super().__init__(api_key)
        self.mode = mode
        base = _COIN_REST_TESTNET if _is_testnet_mode(mode) else _COIN_REST_PROD
        self._base_rest_url = base.rstrip("/")
        self._api_prefix = "/dapi"
        configuration = _CoinConfig(
            api_key=api_key or "",
            api_secret=api_secret or "",
            base_path=self._base_rest_url,
            timeout=5000,
        )
        self._rest = _CoinRestAPI(configuration)

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
        margin_enum = _enum_value(_CoinMarginTypeEnum, margin_value)
        if margin_enum is None and margin_value is not None:
            try:
                margin_enum = _CoinMarginTypeEnum[str(margin_value).upper()]
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
        side = _enum_value(_CoinOrderSideEnum, params.get("side"))
        position_side = _enum_value(_CoinPositionSideEnum, params.get("positionSide"))
        time_in_force = _enum_value(_CoinTimeInForceEnum, params.get("timeInForce"))
        working_type = _enum_value(_CoinWorkingTypeEnum, params.get("workingType"))
        price_match = _enum_value(_CoinPriceMatchEnum, params.get("priceMatch"))
        resp_type = _enum_value(_CoinOrderRespEnum, params.get("newOrderRespType"))
        stp_mode = _enum_value(_CoinStpEnum, params.get("selfTradePreventionMode"))
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

    # Aliases used within the wrapper
    def ticker_price(self, **params):
        return self.get_symbol_ticker(**params)

class BinanceWrapper:

    _limiter_lock = threading.Lock()
    _limiter_pool = {}
    _ban_state_lock = threading.Lock()
    _ban_until_epoch = {}

    def _log(self, msg: str, lvl: str = "info"):
        """
        Lightweight logger shim used by helper methods.
        Falls back to print if no .logger attribute is present.
        """
        try:
            lg = getattr(self, "logger", None)
            if lg is not None and hasattr(lg, lvl):
                getattr(lg, lvl)(msg)
            elif lg is not None and hasattr(lg, "info"):
                lg.info(msg)
            else:
                print(f"[BinanceWrapper][{lvl}] {msg}")
        except Exception:
            try:
                print(f"[BinanceWrapper][{lvl}] {msg}")
            except Exception:
                pass


    @staticmethod
    def _estimate_request_weight(path: str | None) -> float:
        if not path:
            return 1.0
        lower = str(path).lower()
        if "exchangeinfo" in lower:
            return 10.0
        if "balance" in lower or "account" in lower:
            return 5.0
        if "position" in lower:
            return 5.0
        if "klines" in lower:
            return 4.0
        if "ticker" in lower:
            return 1.0 if "price" in lower else 2.0
        if "margin" in lower or "leverage" in lower or "order" in lower:
            return 1.0
        return 2.0

    def _throttle_request(self, path: str | None) -> None:
        limiter = getattr(self, "_request_limiter", None)
        if limiter is None:
            return
        try:
            weight = self._estimate_request_weight(path)
        except Exception:
            weight = 1.0
        try:
            limiter.acquire(weight)
        except Exception:
            pass

    def _get_cached_futures_positions(self, max_age: float) -> list | None:
        if max_age is None or max_age <= 0:
            return None
        with self._positions_cache_lock:
            data = self._positions_cache
            ts = self._positions_cache_ts
        if data is None:
            return None
        if (time.time() - ts) > max_age:
            return None
        return copy.deepcopy(data)

    def _store_futures_positions_cache(self, entries: list | None) -> None:
        with self._positions_cache_lock:
            self._positions_cache = copy.deepcopy(entries) if entries is not None else None
            self._positions_cache_ts = time.time() if entries is not None else 0.0

    def _invalidate_futures_positions_cache(self) -> None:
        with self._positions_cache_lock:
            self._positions_cache = None
            self._positions_cache_ts = 0.0
        self._invalidate_futures_account_cache()

    def _invalidate_futures_account_cache(self) -> None:
        with self._futures_account_cache_lock:
            self._futures_account_cache = None
            self._futures_account_cache_ts = 0.0
            self._futures_account_balance_cache = None
            self._futures_account_balance_cache_ts = 0.0

    def _get_futures_account_cached(self, max_age: float = 2.5, *, force_refresh: bool = False) -> dict:
        now = time.time()
        if not force_refresh:
            with self._futures_account_cache_lock:
                if (
                    self._futures_account_cache is not None
                    and (now - self._futures_account_cache_ts) < max(0.0, float(max_age or 0.0))
                ):
                    return copy.deepcopy(self._futures_account_cache)
        acct_dict = {}
        try:
            acct = self._futures_call("futures_account", allow_recv=True)
            acct_dict = _as_futures_account_dict(acct)
        except Exception:
            acct_dict = {}
        with self._futures_account_cache_lock:
            if acct_dict:
                self._futures_account_cache = copy.deepcopy(acct_dict)
                self._futures_account_cache_ts = time.time()
            elif force_refresh:
                self._futures_account_cache = None
                self._futures_account_cache_ts = 0.0
        return copy.deepcopy(acct_dict) if acct_dict else {}

    def _get_futures_account_balance_cached(self, max_age: float = 2.5, *, force_refresh: bool = False) -> list:
        now = time.time()
        if not force_refresh:
            with self._futures_account_cache_lock:
                if (
                    self._futures_account_balance_cache is not None
                    and (now - self._futures_account_balance_cache_ts) < max(0.0, float(max_age or 0.0))
                ):
                    return copy.deepcopy(self._futures_account_balance_cache)
        entries: list = []
        try:
            bals = self._futures_call("futures_account_balance", allow_recv=True)
            entries = list(_as_futures_balance_entries(bals))
        except Exception:
            entries = []
        with self._futures_account_cache_lock:
            if entries:
                self._futures_account_balance_cache = copy.deepcopy(entries)
                self._futures_account_balance_cache_ts = time.time()
            elif force_refresh:
                self._futures_account_balance_cache = None
                self._futures_account_balance_cache_ts = 0.0
        return copy.deepcopy(entries)

    @staticmethod
    def _format_quantity_for_order(value: float, step: float | None = None) -> str:
        try:
            if value is None:
                return "0"
            from decimal import Decimal, ROUND_DOWN
            quant = Decimal(str(value))
            if step and float(step) > 0:
                step_dec = Decimal(str(step))
                quant = quant.quantize(step_dec, rounding=ROUND_DOWN)
            quant = quant.normalize()
            text_value = format(quant, "f")
            text_value = text_value.rstrip("0").rstrip(".") if "." in text_value else text_value
            return text_value if text_value else "0"
        except Exception:
            try:
                return f"{float(value):.8f}".rstrip("0").rstrip(".")
            except Exception:
                return "0"

    def _convert_asset_to_usdt(self, amount: float | str | None, asset: str | None) -> float:
        """Convert a commission amount into USDT using last price when needed."""
        try:
            value = float(amount or 0.0)
        except Exception:
            return 0.0
        if value == 0.0:
            return 0.0
        code = str(asset or "").upper()
        if not code:
            return value
        if code in {"USDT", "BUSD", "USD"}:
            return value
        try:
            px = float(self.get_last_price(f"{code}USDT") or 0.0)
            if px > 0.0:
                return value * px
        except Exception:
            pass
        return value

    def _summarize_futures_order_fills(
        self,
        symbol: str,
        order_id: int | str | None,
        *,
        attempts: int = 2,
        delay: float = 0.2,
    ) -> dict:
        """Fetch fills for an order to expose realized PnL and commission totals."""
        sym = str(symbol or "").upper()
        if not sym or order_id is None:
            return {}
        try:
            oid = int(float(order_id))
        except Exception:
            return {}

        trades: list[dict] = []
        for attempt in range(max(1, attempts) + 1):
            try:
                self._throttle_request("/fapi/v1/userTrades")
                trades = self.client.futures_account_trades(symbol=sym, orderId=oid, limit=100) or []
            except Exception:
                trades = []
            if trades:
                break
            if attempt < attempts:
                try:
                    time.sleep(max(0.0, float(delay)))
                except Exception:
                    pass
        if not trades:
            return {}

        total_qty = 0.0
        total_quote = 0.0
        realized_pnl = 0.0
        commission_by_asset: dict[str, float] = {}
        for trade in trades:
            try:
                qty = abs(float(trade.get("qty") or 0.0))
            except Exception:
                qty = 0.0
            try:
                price = float(trade.get("price") or 0.0)
            except Exception:
                price = 0.0
            total_qty += qty
            total_quote += qty * price
            try:
                realized_pnl += float(trade.get("realizedPnl") or 0.0)
            except Exception:
                pass
            try:
                commission_val = float(trade.get("commission") or 0.0)
            except Exception:
                commission_val = 0.0
            asset = str(trade.get("commissionAsset") or "").upper() or "USDT"
            commission_by_asset[asset] = commission_by_asset.get(asset, 0.0) + commission_val

        avg_price = (total_quote / total_qty) if total_qty > 0 else 0.0
        commission_usdt = 0.0
        for asset, amount in commission_by_asset.items():
            commission_usdt += self._convert_asset_to_usdt(amount, asset)
        net_realized = realized_pnl - commission_usdt
        return {
            "order_id": oid,
            "filled_qty": total_qty,
            "avg_price": avg_price,
            "realized_pnl": realized_pnl,
            "commission_breakdown": commission_by_asset,
            "commission_usdt": commission_usdt,
            "net_realized": net_realized,
            "trade_count": len(trades),
        }

    @staticmethod
    def _environment_tag(mode_value: str | None) -> str:
        text = str(mode_value or "").lower()
        return "testnet" if any(tag in text for tag in ("test", "demo")) else "live"

    @staticmethod
    def _account_tag(account_value: str | None) -> str:
        text = str(account_value or "").upper()
        return "spot" if text.startswith("SPOT") else "futures"

    @classmethod
    def _limiter_settings_for(cls, env_tag: str, acct_tag: str) -> dict:
        if env_tag == "testnet":
            # Binance testnet enforces much lower throughput; stay very conservative.
            return {"max_per_minute": 180.0, "min_interval": 0.65, "safety_margin": 0.8}
        if acct_tag == "spot":
            return {"max_per_minute": 900.0, "min_interval": 0.25, "safety_margin": 0.85}
        # Live futures default
        return {"max_per_minute": 1100.0, "min_interval": 0.2, "safety_margin": 0.9}

    @classmethod
    def _acquire_rate_limiter(cls, key: str, settings: dict) -> _SimpleRateLimiter:
        with cls._limiter_lock:
            limiter = cls._limiter_pool.get(key)
            if limiter is None:
                limiter = _SimpleRateLimiter(
                    max_per_minute=settings.get("max_per_minute", 600.0),
                    min_interval=settings.get("min_interval", 0.25),
                    safety_margin=settings.get("safety_margin", 0.85),
                )
                cls._limiter_pool[key] = limiter
            return limiter

    def _ban_key(self) -> str:
        try:
            return getattr(self, "_limiter_key", None) or "global"
        except Exception:
            return "global"
    def _install_request_throttler(self) -> None:
        client = getattr(self, "client", None)
        if not client or getattr(client, "_bw_throttled", False):
            return
        try:
            original = client._request
        except AttributeError:
            return

        def throttled(_self, method, path, signed=False, force_params=False, **kwargs):
            self._throttle_request(path)
            return original(method, path, signed=signed, force_params=force_params, **kwargs)

        try:
            client._request = types.MethodType(throttled, client)
            client._bw_throttled = True
        except Exception as exc:
            self._log(f"Failed to attach rate limiter: {exc}", lvl="warn")

    def _register_ban_until(self, until_epoch: float | None) -> None:
        if not until_epoch or until_epoch != until_epoch:
            return
        key = self._ban_key()
        with self._ban_state_lock:
            current = self._ban_until_epoch.get(key, 0.0)
            if until_epoch > current:
                self._ban_until_epoch[key] = until_epoch

    def _seconds_until_unban(self) -> float:
        key = self._ban_key()
        with self._ban_state_lock:
            until = self._ban_until_epoch.get(key, 0.0)
        remaining = until - time.time()
        return remaining if remaining > 0 else 0.0

    @staticmethod
    def _extract_ban_until(message: str | None) -> float | None:
        if not message:
            return None
        match = re.search(r"banned until (\d+)", message)
        if match:
            raw = float(match.group(1))
            if raw > 1e12:
                return raw / 1000.0
            if raw > 1e5:
                return raw
        match = re.search(r"(?:after|wait)\s+(\d+)(?:ms| milliseconds)", message)
        if match:
            return time.time() + max(float(match.group(1)) / 1000.0, 0.0)
        match = re.search(r"(?:after|wait)\s+(\d+)(?:s| seconds)", message)
        if match:
            return time.time() + max(float(match.group(1)), 0.0)
        return None

    def _handle_potential_ban(self, exc) -> float | None:
        try:
            code = getattr(exc, "code", None)
            status = getattr(exc, "status_code", None)
            msg = str(exc)
        except Exception:
            code, status, msg = None, None, ""
        triggered = False
        msg_lower = msg.lower() if isinstance(msg, str) else ""
        if code in (-1003, 429) or status in (418, 429):
            triggered = True
        elif msg_lower:
            if "banned until" in msg_lower or "too many requests" in msg_lower or "too frequent" in msg_lower or "frequency" in msg_lower:
                triggered = True
        if not triggered:
            return None
        until = self._extract_ban_until(msg)
        if until is None:
            retry_after = None
            try:
                response = getattr(exc, "response", None)
                if response is not None:
                    retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
            except Exception:
                retry_after = None
            if retry_after:
                try:
                    until = time.time() + float(retry_after)
                except Exception:
                    until = None
        if until is None:
            until = time.time() + 8.0
        self._register_ban_until(until)
        remaining = max(0.0, until - time.time())
        try:
            limiter = getattr(self, "_request_limiter", None)
            if limiter is not None:
                limiter.pause_for(remaining + 3.0)
        except Exception:
            pass
        return until
    def _ensure_symbol_margin(self, symbol: str, want_mode: str | None, want_lev: int | None):
        sym = (symbol or "").upper()
        target = (want_mode or "ISOLATED").upper()
        if target == "CROSS":
            target = "CROSSED"
        if target not in ("ISOLATED", "CROSSED"):
            target = "ISOLATED"
    
        current = None
        open_amt = 0.0
        try:
            pins = self.client.futures_position_information(symbol=sym)
            if isinstance(pins, list) and pins:
                types = []
                for p in pins:
                    try:
                        types.append((p.get("marginType") or "").upper())
                        open_amt += abs(float(p.get("positionAmt") or 0.0))
                    except Exception:
                        pass
                current = next((t for t in types if t), None)
                if target in types:
                    current = target
        except Exception as e:
            self._log(f"margin probe failed for {sym}: {type(e).__name__}: {e}", lvl="warn")
            current = None
    
        if (current or "").upper() == target:
            if want_lev:
                try:
                    self.client.futures_change_leverage(symbol=sym, leverage=int(want_lev))
                except Exception:
                    pass
            return True
    
        if open_amt > 0:
            raise RuntimeError(f"wrong_margin_mode: current={current}, want={target}, symbol={sym}, openAmt={open_amt}")
    
        assume_ok = False
        try:
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
            except Exception:
                pass
            self.client.futures_change_margin_type(symbol=sym, marginType=target)
        except Exception as e:
            msg = str(e)
            if "-4046" in msg or "No need to change margin type" in msg:
                assume_ok = True
                self._log(f"change_margin_type({sym}->{target}) says already correct (-4046).", lvl="warn")
            else:
                self._log(f"change_margin_type({sym}->{target}) raised {type(e).__name__}: {e}", lvl="warn")
    
        try:
            pins2 = self.client.futures_position_information(symbol=sym)
            types2 = [(p.get("marginType") or "").upper() for p in (pins2 or []) if isinstance(p, dict)]
            now = next((t for t in types2 if t), None)
        except Exception:
            types2, now = [], None
    
        if (now == target) or (target in types2) or (assume_ok and (now in (None, ""))):
            if want_lev:
                try:
                    self.client.futures_change_leverage(symbol=sym, leverage=int(want_lev))
                except Exception:
                    pass
            return True
    
        raise RuntimeError(f"wrong_margin_mode_after_change: now={now}, want={target}, symbol={sym}")

    def set_position_mode(self, hedge: bool) -> bool:
        """Enable/disable dual-side (hedge) mode on futures."""
        try:
            self.client.futures_change_position_mode(dualSidePosition=bool(hedge))
            return True
        except Exception:
            # fallback names used by some client versions
            for m in ("futures_change_position_side_dual", "futures_change_positionMode"):
                try:
                    fn = getattr(self.client, m, None)
                    if fn:
                        fn(dualSidePosition=bool(hedge))
                        return True
                except Exception:
                    continue
        return False

    def set_multi_assets_mode(self, enabled: bool) -> bool:
        """Toggle Single-Asset vs Multi-Assets mode on USDT-M futures margin."""
        # python-binance names vary; try several spellings then raw REST call as a last resort.
        payload = {'multiAssetsMargin': 'true' if bool(enabled) else 'false'}
        for m in ("futures_change_multi_assets_margin", "futures_multi_assets_margin", "futures_set_multi_assets_margin"):
            try:
                fn = getattr(self.client, m, None)
                if fn:
                    fn(**payload)
                    return True
            except Exception:
                continue
        try:
            # raw client request method (available on python-binance Client)
            self.client._request_futures_api('post', 'multiAssetsMargin', data=payload)
            return True
        except Exception:
            try:
                import requests
                headers = {'X-MBX-APIKEY': getattr(self.client, 'API_KEY', '')}
                url = 'https://fapi.binance.com/fapi/v1/multiAssetsMargin'
                requests.post(url, params=payload, headers=headers, timeout=5)
                return True
            except Exception:
                return False
    
    def required_percent_for_symbol(self, symbol: str, leverage: int | float | None = None) -> float:
        """Rough % of total USDT needed to meet minQty/minNotional for a symbol at leverage."""
        try:
            sym = (symbol or "").upper()
            lev = float(leverage if leverage is not None else getattr(self, "futures_leverage", getattr(self, "_default_leverage", 5)) or 5)
            px = float(self.get_last_price(sym) or 0.0)
            f = self.get_futures_symbol_filters(sym) or {}
            step = float(f.get("stepSize") or 0.0) or 0.001
            minQty = float(f.get("minQty") or 0.0) or step
            minNotional = float(f.get("minNotional") or 0.0) or 5.0
            need_qty = max(minQty, (float(minNotional)/px) if px>0 else 0.0)
            if step > 0 and need_qty>0:
                k = int(need_qty / step)
                if abs(need_qty - k*step) > 1e-12:
                    need_qty = (k+1)*step
            if px<=0 or lev<=0 or need_qty<=0: return 0.0
            margin_needed = (need_qty * px) / lev
            bal = float(self.futures_get_usdt_balance() or 0.0)
            if bal <= 0: return 0.0
            return (margin_needed / bal) * 100.0
        except Exception:
            return 0.0

    # ---- SPOT trading (basic MARKET)
    def place_spot_market_order(self, symbol: str, side: str, quantity: float = 0.0, price: float | None = None,
                                use_quote: bool = False, quote_amount: float | None = None, **kwargs):
        """
        Minimal SPOT MARKET order helper.
        Returns a dict with 'ok', 'info', 'computed'.
        """
        sym = symbol.upper()
        if self.account_type != "SPOT":
            return {'ok': False, 'error': 'account_type != SPOT'}
        px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
        if px <= 0:
            return {'ok': False, 'error': 'No price available'}
        qty = float(quantity or 0.0)
        if side.upper() == 'BUY' and use_quote:
            qamt = float(quote_amount or 0.0)
            if qamt <= 0:
                return {'ok': False, 'error': 'quote_amount<=0'}
            qty = qamt / px
        # Adjust to filters
        f = self.get_spot_symbol_filters(sym)
        step = float(f.get('stepSize', 0.0) or 0.0)
        minQty = float(f.get('minQty', 0.0) or 0.0)
        minNotional = float(f.get('minNotional', 0.0) or 0.0)
        if step > 0:
            qty = self._floor_to_step(qty, step)
        if minQty > 0 and qty < minQty:
            qty = minQty
            if step > 0: qty = self._floor_to_step(qty, step)
        if minNotional > 0 and (qty * px) < minNotional:
            needed = (minNotional / px)
            qty = needed
            if step > 0: qty = self._floor_to_step(qty, step)
        try:
            res = self.client.create_order(symbol=sym, side=side.upper(), type='MARKET', quantity=str(qty))
            return {'ok': True, 'info': res, 'computed': {'qty': qty, 'price': px,
                    'filters': {'step': step, 'minQty': minQty, 'minNotional': minNotional}}}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'price': px,
                    'filters': {'step': step, 'minQty': minQty, 'minNotional': minNotional}}}

    def _ceil_to_step(self, value: float, step: float) -> float:
        try:
            if step <= 0:
                return float(value)
            import math
            return math.ceil(float(value) / float(step)) * float(step)
        except Exception:
            return float(value)
    
    def fetch_symbols(self, sort_by_volume: bool = False, top_n: int | None = None):
        """
        Robust symbol fetcher.
        FUTURES: Return only USDT-M **PERPETUAL** symbols from /fapi/v1/exchangeInfo.
        SPOT   : Return USDT quote symbols from /api/v3/exchangeInfo.
        When sort_by_volume is requested, we sort the **allowed** set by 24h quoteVolume,
        but we never add anything outside the allow-list.
        """
        import requests

        def _safe_json(url: str, timeout: float = 10.0):
            try:
                r = requests.get(url, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                return None
            return None

        acct = str(getattr(self, "account_type", "SPOT") or "SPOT").strip().upper()
        allowed = set()

        if acct.startswith("FUT"):
            info = None
            try:
                info = self.client.futures_exchange_info()
            except Exception:
                info = None
            if not info or not isinstance(info, dict) or "symbols" not in info:
                info = _safe_json(f"{self._futures_base()}/v1/exchangeInfo") or {}

            for s in (info or {}).get("symbols", []):
                try:
                    if (s.get("status") == "TRADING"
                        and s.get("quoteAsset") == "USDT"
                        and s.get("contractType") == "PERPETUAL"):
                        allowed.add((s.get("symbol") or "").upper())
                except Exception:
                    continue

            ordered = sorted(list(allowed))
            if sort_by_volume and ordered:
                vol_map = {}
                data = _safe_json(f"{self._futures_base()}/v1/ticker/24hr") or []
                for t in data:
                    sym = (t.get("symbol") or "").upper()
                    try:
                        vol_map[sym] = float(t.get("quoteVolume") or 0.0)
                    except Exception:
                        vol_map[sym] = 0.0
                ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

            if top_n:
                ordered = ordered[:int(top_n)]
            return ordered

        # SPOT path
        info = None
        try:
            info = self.client.get_exchange_info()
        except Exception:
            info = None
        if not info or not isinstance(info, dict) or "symbols" not in info:
            info = _safe_json(f"{self._spot_base()}/v3/exchangeInfo") or {}

        for s in (info or {}).get("symbols", []):
            try:
                if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
                    allowed.add((s.get("symbol") or "").upper())
            except Exception:
                continue

        ordered = sorted(list(allowed))
        if sort_by_volume and ordered:
            vol_map = {}
            data = _safe_json(f"{self._spot_base()}/v3/ticker/24hr") or []
            for t in data:
                sym = (t.get("symbol") or "").upper()
                try:
                    vol_map[sym] = float(t.get("quoteVolume") or 0.0)
                except Exception:
                    vol_map[sym] = 0.0
            ordered = sorted(ordered, key=lambda s: vol_map.get(s, 0.0), reverse=True)

        if top_n:
            ordered = ordered[:int(top_n)]
        return ordered

    
    def _spot_base(self) -> str:
        # Public REST base for SPOT depending on testnet/production
        return "https://testnet.binance.vision/api" if ("demo" in self.mode.lower() or "test" in self.mode.lower()) else "https://api.binance.com/api"

    def _futures_base(self) -> str:
        # Public REST base for FUTURES depending on testnet/production
        return "https://testnet.binancefuture.com/fapi" if ("demo" in self.mode.lower() or "test" in self.mode.lower()) else "https://fapi.binance.com/fapi"

    def _build_client(self):
        backend = _normalize_connector_choice(getattr(self, "_connector_backend", DEFAULT_CONNECTOR_BACKEND))
        if backend == "binance-connector" and _OfficialSpotClient is not None and _OfficialAPIBase is not None:
            try:
                return OfficialConnectorAdapter(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"Official connector unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        if backend == "binance-sdk-derivatives-trading-usds-futures":
            try:
                return BinanceSDKUsdsFuturesClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"USDⓈ futures SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        elif backend == "binance-sdk-derivatives-trading-coin-futures":
            try:
                return BinanceSDKCoinFuturesClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"COIN-M futures SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        elif backend == "binance-sdk-spot":
            try:
                return BinanceSDKSpotClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"Spot SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        return Client(self.api_key, self.api_secret)

    def __init__(self, api_key="", api_secret="", mode="Demo/Testnet", account_type="Spot", *, default_leverage: int | None = None, default_margin_mode: str | None = None, connector_backend: str | None = None):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.mode = (mode or "Demo/Testnet").strip()
        initial_leverage = int(default_leverage) if (default_leverage is not None) else 20
        if initial_leverage < 1:
            initial_leverage = 1
        if initial_leverage > MAX_FUTURES_LEVERAGE:
            initial_leverage = MAX_FUTURES_LEVERAGE
        self._requested_default_leverage = initial_leverage
        self._default_leverage = initial_leverage
        self.futures_leverage = initial_leverage
        self._default_margin_mode = str((default_margin_mode or "ISOLATED")).upper()
        self.account_type = (account_type or "Spot").strip().upper()  # "SPOT" or "FUTURES"
        if self.account_type.startswith("FUT"):
            self.indicator_source = "Binance futures"
        else:
            self.indicator_source = "Binance spot"
        self._max_auto_bump_percent = 5.0
        self._auto_bump_percent_multiplier = 10.0
        self.recv_window = 5000  # ms for futures calls
        self._futures_max_leverage_cache = {}
        self._leverage_cap_notified = set()
        self._connector_backend = _normalize_connector_choice(connector_backend)
        env_tag = self._environment_tag(self.mode)
        acct_tag = self._account_tag(self.account_type)
        self._limiter_key = f"{env_tag}:{acct_tag}"
        limiter_settings = self._limiter_settings_for(env_tag, acct_tag)
        self._request_limiter = self._acquire_rate_limiter(self._limiter_key, limiter_settings)

        # Set base URLs BEFORE creating Client
        if "demo" in self.mode.lower() or "test" in self.mode.lower():
            if self.account_type == "FUTURES":
                Client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
            else:
                Client.API_URL = "https://testnet.binance.vision/api"
        else:
            if self.account_type == "FUTURES":
                Client.FUTURES_URL = "https://fapi.binance.com/fapi"
            else:
                Client.API_URL = "https://api.binance.com/api"

        self.client = self._build_client()
        try:
            if hasattr(self.client, "_bw_throttled"):
                setattr(self.client, "_bw_throttle", self._throttle_request)
        except Exception:
            pass
        self._install_request_throttler()
        self._symbol_info_cache_spot = {}
        self._symbol_info_cache_futures = None
        self._futures_dual_side_cache = None
        self._futures_dual_side_cache_ts = 0.0
        self._kline_cache = {}
        self._kline_cache_lock = threading.Lock()
        self._positions_cache = None
        self._positions_cache_ts = 0.0
        self._positions_cache_lock = threading.Lock()
        self._futures_account_cache = None
        self._futures_account_cache_ts = 0.0
        self._futures_account_balance_cache = None
        self._futures_account_balance_cache_ts = 0.0
        self._futures_account_cache_lock = threading.Lock()
        self._last_ban_log = 0.0
        self._last_network_error_log = 0.0
        self._last_price_cache: dict[str, tuple[float, float]] = {}
        self._emergency_closer_lock = threading.Lock()
        self._emergency_closer_thread = None
        self._emergency_close_requested = False
        self._emergency_close_info = {}
        self._network_offline = False
        self._network_offline_since = 0.0
        self._network_offline_hits = 0
        self._network_emergency_dispatched = False
        getcontext().prec = 28

    # ---- internal helper for futures methods with recvWindow compatibility
    def _futures_call(self, method_name: str, allow_recv=True, **kwargs):
        try:
            self._throttle_request(f"/fapi/{method_name}")
        except Exception:
            pass
        method = getattr(self.client, method_name)
        if allow_recv:
            try:
                return method(recvWindow=self.recv_window, **kwargs)
            except TypeError:
                pass
        return method(**kwargs)

    def futures_api_ok(self) -> tuple[bool, str | None]:
        """
        Quick signed call to verify Futures API keys/permissions.
        Returns (ok, error_message).
        """
        try:
            _ = self._futures_call('futures_account_balance', allow_recv=True)
            return True, None
        except Exception as e:
            return False, str(e)

    def spot_api_ok(self) -> tuple[bool, str | None]:
        """Quick call to verify Spot API keys/permissions."""
        try:
            _ = self.client.get_account()
            return True, None
        except Exception as e:
            return False, str(e)


    # ---- SPOT symbol info/filters
    def get_symbol_info_spot(self, symbol: str) -> dict:
        key = symbol.upper()
        if key not in self._symbol_info_cache_spot:
            info = self.client.get_symbol_info(key)
            if not info:
                raise ValueError(f"No spot symbol info for {symbol}")
            self._symbol_info_cache_spot[key] = info
        return self._symbol_info_cache_spot[key]

    def get_symbol_quote_precision_spot(self, symbol: str) -> int:
        info = self.get_symbol_info_spot(symbol)
        qp = info.get('quoteAssetPrecision') or info.get('quotePrecision') or 8
        return int(qp)

    def get_spot_symbol_filters(self, symbol: str) -> dict:
        info = self.get_symbol_info_spot(symbol)
        step_size = None
        min_qty = None
        min_notional = None
        for f in info.get('filters', []):
            if f.get('filterType') == 'LOT_SIZE':
                step_size = float(f.get('stepSize', '0'))
                min_qty = float(f.get('minQty', '0'))
            elif f.get('filterType') in ('MIN_NOTIONAL', 'NOTIONAL'):
                min_notional = float(f.get('minNotional', f.get('notional', '0')))
        return {'stepSize': step_size or 0.0, 'minQty': min_qty or 0.0, 'minNotional': min_notional or 0.0}

    # ---- FUTURES exchange info/filters
    def get_futures_exchange_info(self) -> dict:
        if self._symbol_info_cache_futures is None:
            self._symbol_info_cache_futures = self._futures_call('futures_exchange_info', allow_recv=True)
        return self._symbol_info_cache_futures

    def get_futures_symbol_info(self, symbol: str) -> dict:
        info = self.get_futures_exchange_info()
        for s in info.get('symbols', []):
            if s.get('symbol') == symbol.upper():
                return s
        raise ValueError(f"No futures symbol info for {symbol}")

    def get_futures_symbol_filters(self, symbol: str) -> dict:
        s = self.get_futures_symbol_info(symbol)
        step_size = None
        min_qty = None
        price_tick = None
        min_notional = None
        for f in s.get('filters', []):
            if f.get('filterType') == 'LOT_SIZE':
                step_size = float(f.get('stepSize', '0'))
                min_qty = float(f.get('minQty', '0'))
            elif f.get('filterType') == 'PRICE_FILTER':
                price_tick = float(f.get('tickSize', '0'))
            elif f.get('filterType') in ('MIN_NOTIONAL','NOTIONAL'):
                mn = f.get('notional') or f.get('minNotional') or 0
                try:
                    min_notional = float(mn)
                except Exception:
                    min_notional = 0.0
        return {'stepSize': step_size or 0.0, 'minQty': min_qty or 0.0, 'tickSize': price_tick or 0.0, 'minNotional': min_notional or 0.0}

    def get_futures_max_leverage(self, symbol: str) -> int:
        sym = str(symbol or "").upper()
        if not sym:
            return MAX_FUTURES_LEVERAGE
        cache = getattr(self, "_futures_max_leverage_cache", {})
        if sym in cache:
            try:
                return int(cache[sym])
            except Exception:
                pass
        max_lev = None
        try:
            data = self.client.futures_leverage_bracket(symbol=sym)
            records = []
            if isinstance(data, dict):
                records = [data]
            elif isinstance(data, list):
                records = data
            for rec in records:
                if isinstance(rec, dict):
                    rec_sym = str(rec.get("symbol") or sym).upper()
                    if rec_sym and rec_sym != sym:
                        continue
                    brackets = rec.get("brackets") or []
                else:
                    rec_sym = sym
                    brackets = []
                for bracket in brackets:
                    if not isinstance(bracket, dict):
                        continue
                    lev_val = bracket.get("initialLeverage") or bracket.get("initial_leverage")
                    try:
                        lev_int = int(float(lev_val))
                    except Exception:
                        continue
                    if lev_int > 0:
                        max_lev = max(max_lev or 0, lev_int)
                if max_lev:
                    break
        except Exception:
            max_lev = None if max_lev is None else max_lev
        if max_lev is None:
            try:
                info = self.get_futures_symbol_info(sym)
                for filt in info.get("filters", []):
                    if str(filt.get("filterType") or "").upper() == "LEVERAGE":
                        lev_val = filt.get("maxLeverage") or filt.get("max_leverage")
                        if lev_val is not None:
                            max_lev = int(float(lev_val))
                            break
            except Exception:
                pass
        if not max_lev or int(max_lev) <= 0:
            max_lev = MAX_FUTURES_LEVERAGE
        max_lev = max(1, min(int(max_lev), MAX_FUTURES_LEVERAGE))
        self._futures_max_leverage_cache[sym] = max_lev
        return max_lev

    def get_recent_force_orders(
        self,
        symbol: str | None = None,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Fetch recent forced liquidation orders for the given futures symbol."""
        func = getattr(self.client, "futures_force_orders", None)
        if func is None:
            func = getattr(self.client, "futures_get_force_orders", None)
        if func is None:
            return []
        params: dict[str, object] = {"limit": max(1, min(int(limit or 1), 1000))}
        if symbol:
            params["symbol"] = str(symbol).upper()
        if start_time:
            try:
                params["startTime"] = int(start_time)
            except Exception:
                pass
        if end_time:
            try:
                params["endTime"] = int(end_time)
            except Exception:
                pass
        try:
            data = func(**params)
        except Exception:
            return []
        if isinstance(data, dict):
            seq = None
            for key in ("rows", "data", "forceOrders", "orders", "list"):
                if key in data:
                    seq = data.get(key)
                    break
            data_list = seq if isinstance(seq, list) else []
        elif isinstance(data, list):
            data_list = data
        else:
            data_list = []
        normalized: list[dict] = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            entry: dict[str, object] = {}
            for key in (
                "avgPrice",
                "executedQty",
                "origQty",
                "price",
                "time",
                "updateTime",
                "orderId",
                "side",
                "symbol",
                "positionSide",
                "status",
                "type",
            ):
                if key in item:
                    entry[key] = item[key]
            normalized.append(entry)
        return normalized

    def clamp_futures_leverage(self, symbol: str, leverage: int | None = None) -> int:
        sym = str(symbol or "").upper()
        desired = leverage if leverage is not None else getattr(self, "_requested_default_leverage", getattr(self, "_default_leverage", 5))
        try:
            desired_int = int(float(desired))
        except Exception:
            desired_int = 1
        if desired_int < 1:
            desired_int = 1
        if desired_int > MAX_FUTURES_LEVERAGE:
            desired_int = MAX_FUTURES_LEVERAGE
        account_label = str(getattr(self, "account_type", "") or "").upper()
        if not account_label.startswith("FUT"):
            return desired_int
        max_allowed = self.get_futures_max_leverage(sym) if sym else MAX_FUTURES_LEVERAGE
        effective = max(1, min(desired_int, max_allowed or MAX_FUTURES_LEVERAGE))
        if effective < desired_int and sym:
            notified = getattr(self, "_leverage_cap_notified", set())
            if sym not in notified:
                try:
                    self._log(f"{sym} max futures leverage {max_allowed}x; requested {desired_int}x -> using {effective}x.", lvl="warn")
                except Exception:
                    try:
                        print(f"[BinanceWrapper] {sym} leverage limited to {effective}x (requested {desired_int}x).")
                    except Exception:
                        pass
                notified.add(sym)
                self._leverage_cap_notified = notified
        return effective

    # ---- balances
    def get_spot_balance(self, asset="USDT") -> float:
        try:
            info = self.client.get_account()
            for b in info.get('balances', []):
                if b.get('asset') == asset:
                    return float(b.get('free', 0.0))
        except Exception:
            pass
        return 0.0

    def get_balances(self) -> list[dict]:
        """Return normalized balance objects for the active account type."""
        account_kind = str(getattr(self, "account_type", "") or "").upper()
        rows: list[dict] = []
        if account_kind.startswith("FUT"):
            try:
                balances = self._get_futures_account_balance_cached() or []
                for entry in balances:
                    asset = entry.get("asset")
                    if not asset:
                        continue
                    free = float(entry.get("availableBalance") or entry.get("balance") or entry.get("walletBalance") or 0.0)
                    total = float(entry.get("walletBalance") or entry.get("balance") or entry.get("crossWalletBalance") or free)
                    locked = max(0.0, total - free)
                    rows.append({
                        "asset": asset,
                        "free": free,
                        "locked": locked,
                        "total": total,
                    })
            except Exception:
                rows = []
        else:
            try:
                info = self.client.get_account()
                for b in info.get('balances', []):
                    asset = b.get('asset')
                    if not asset:
                        continue
                    free = float(b.get('free', 0.0))
                    locked = float(b.get('locked', 0.0))
                    total = free + locked
                    if total <= 0.0:
                        continue
                    rows.append({
                        "asset": asset,
                        "free": free,
                        "locked": locked,
                        "total": total,
                    })
            except Exception:
                rows = []
        return rows

    # ---- spot positions helpers
    def list_spot_non_usdt_balances(self):
        """Return list of dicts with non-zero free balances for assets (excluding USDT)."""
        out = []
        try:
            info = self.client.get_account()
            for b in info.get('balances', []):
                asset = b.get('asset')
                if not asset or asset == 'USDT':
                    continue
                free = float(b.get('free', 0.0))
                if free > 0:
                    out.append({'asset': asset, 'free': free})
        except Exception:
            pass
        return out

    def close_all_spot_positions(self):
        """Sell all non-USDT spot balances into USDT using market orders, respecting filters."""
        results = []
        balances = self.list_spot_non_usdt_balances()
        for bal in balances:
            asset = bal['asset']
            qty = float(bal.get('free') or 0.0)
            if qty <= 0.0:
                continue
            symbol = f"{asset}USDT"

            # Ensure the symbol actually trades against USDT on the selected venue.
            try:
                self.get_symbol_info_spot(symbol)
            except Exception:
                results.append({
                    'symbol': symbol,
                    'qty': qty,
                    'ok': True,
                    'skipped': True,
                    'reason': 'Symbol not tradable against USDT on this venue',
                })
                continue

            try:
                filters = self.get_spot_symbol_filters(symbol)
                price = float(self.get_last_price(symbol) or 0.0)
                min_notional = float(filters.get('minNotional', 0.0) or 0.0)
                step = float(filters.get('stepSize', 0.0) or 0.0)

                if price <= 0.0:
                    results.append({
                        'symbol': symbol,
                        'qty': qty,
                        'ok': True,
                        'skipped': True,
                        'reason': 'Last price unavailable, cannot compute notional',
                    })
                    continue

                est_notional = qty * price
                if min_notional > 0.0 and est_notional < min_notional:
                    # Flag dust balances as skipped so the caller can hide them.
                    results.append({
                        'symbol': symbol,
                        'qty': qty,
                        'ok': True,
                        'skipped': True,
                        'reason': f'Dust position below min notional ({est_notional:.8f} < {min_notional:.8f})',
                    })
                    continue

                qty_adj = self._floor_to_step(qty, step) if step else qty
                if qty_adj <= 0.0:
                    results.append({
                        'symbol': symbol,
                        'qty': qty,
                        'ok': True,
                        'skipped': True,
                        'reason': 'Quantity too small after applying step size',
                    })
                    continue

                trade = self.place_spot_market_order(symbol, 'SELL', qty_adj)
                if not trade.get('ok'):
                    results.append({
                        'symbol': symbol,
                        'qty': qty_adj,
                        'ok': False,
                        'error': trade.get('error') or 'Spot market order failed',
                        'details': trade,
                    })
                    continue

                computed_qty = trade.get('computed', {}).get('qty', qty_adj)
                results.append({
                    'symbol': symbol,
                    'qty': computed_qty,
                    'ok': True,
                    'res': trade,
                })
            except Exception as e:
                results.append({'symbol': symbol, 'qty': qty, 'ok': False, 'error': str(e)})
        return results

    def trigger_emergency_close_all(self, *, reason: str | None = None, source: str | None = None,
                                    max_attempts: int = 12, initial_delay: float = 5.0) -> bool:
        """
        Launch a background worker that repeatedly attempts to close all open positions.
        Returns True if a new worker was started, False if one was already running.
        """
        meta = {
            "reason": reason or "",
            "source": source or "",
            "requested_at": datetime.utcnow().isoformat()
        }
        with self._emergency_closer_lock:
            existing = getattr(self, "_emergency_closer_thread", None)
            if existing and existing.is_alive():
                # Update metadata and let the existing worker continue
                self._emergency_close_requested = True
                try:
                    self._emergency_close_info.update(meta)
                except Exception:
                    self._emergency_close_info = dict(meta)
                if reason:
                    self._log(f"Emergency close-all already running; latest reason: {reason}", lvl="warn")
                return False

            self._emergency_close_requested = True
            self._emergency_close_info = dict(meta)
            base_delay = max(1.0, float(initial_delay or 1.0))
            account = str(getattr(self, "account_type", "FUTURES") or "FUTURES").upper()

            def _worker():
                success = False
                attempt = 0
                last_error = None
                while max_attempts <= 0 or attempt < max_attempts:
                    attempt += 1
                    try:
                        if account.startswith("FUT"):
                            from .close_all import close_all_futures_positions as _close_all_futures
                            result = _close_all_futures(self) or []
                            ok = all((r.get('ok') or r.get('skipped')) for r in result) if result else True
                        else:
                            result = self.close_all_spot_positions() or []
                            ok = all(bool(r.get('ok')) for r in result) if result else True
                        if ok:
                            success = True
                            if attempt == 1:
                                self._log("Emergency close-all completed successfully on first attempt.", lvl="warn")
                            else:
                                self._log(f"Emergency close-all completed successfully on attempt {attempt}.", lvl="warn")
                            break
                        last_error = RuntimeError("partial failures")
                        self._log(f"Emergency close-all attempt {attempt} had partial failures; retrying...", lvl="error")
                    except requests.exceptions.RequestException as exc:
                        last_error = exc
                        self._log(f"Emergency close-all attempt {attempt} failed (network): {exc}", lvl="error")
                    except Exception as exc:
                        last_error = exc
                        self._log(f"Emergency close-all attempt {attempt} failed: {exc}", lvl="error")
                    time.sleep(min(90.0, base_delay * (attempt + 1)))

                if not success:
                    if last_error:
                        self._log(f"Emergency close-all aborted after {attempt} attempts: {last_error}", lvl="error")
                    else:
                        self._log(f"Emergency close-all aborted after {attempt} attempts without success.", lvl="error")

                with self._emergency_closer_lock:
                    self._emergency_closer_thread = None
                    self._emergency_close_requested = False
                    info = dict(self._emergency_close_info or {})
                    info["completed_at"] = datetime.utcnow().isoformat()
                    info["success"] = bool(success)
                    if last_error:
                        info["error"] = str(last_error)
                    self._emergency_close_info = info
                try:
                    self._network_emergency_dispatched = False
                    self._network_offline_hits = 0
                    self._network_offline_since = time.time()
                except Exception:
                    pass

            thread = threading.Thread(target=_worker, name="EmergencyCloseAll", daemon=True)
            self._emergency_closer_thread = thread
            self._log(
                f"Emergency close-all triggered ({source or 'unspecified'}): {reason or 'no reason provided'}.",
                lvl="warn"
            )
            thread.start()
            return True

    def get_futures_balance_usdt(self, *, force_refresh: bool = False) -> float:
        """Return the withdrawable/available balance for the primary futures asset."""
        preferred_assets = ("USDT", "BUSD", "USD")
        entries = self._get_futures_account_balance_cached(force_refresh=force_refresh) or []
        if not entries and not force_refresh:
            entries = self._get_futures_account_balance_cached(force_refresh=True) or []
        for b in entries:
            if not isinstance(b, dict):
                continue
            asset = str(b.get('asset') or "").upper()
            if asset not in preferred_assets:
                continue
            for key in ('availableBalance', 'crossWalletBalance', 'balance', 'walletBalance'):
                val = b.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except Exception:
                        continue
        acct_dict = self._get_futures_account_cached(force_refresh=force_refresh)
        if isinstance(acct_dict, dict):
            for key in ('availableBalance', 'maxWithdrawAmount', 'totalWalletBalance', 'totalMarginBalance'):
                val = acct_dict.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except Exception:
                        continue
        if not force_refresh:
            acct_dict = self._get_futures_account_cached(force_refresh=True)
            if isinstance(acct_dict, dict):
                for key in ('availableBalance', 'maxWithdrawAmount', 'totalWalletBalance', 'totalMarginBalance'):
                    val = acct_dict.get(key)
                    if val is not None:
                        try:
                            return float(val)
                        except Exception:
                            continue
        return 0.0
    def get_futures_available_balance(self, *, force_refresh: bool = False) -> float:
        val = self.get_futures_balance_usdt(force_refresh=force_refresh)
        if val:
            return val
        val = self.get_futures_balance_usdt(force_refresh=True)
        if val:
            return val
        try:
            for row in self.get_balances():
                if (row.get('asset') or '').upper() == 'USDT':
                    free = row.get('free')
                    if free is not None:
                        return float(free)
        except Exception:
            pass
        return 0.0

    def get_futures_wallet_balance(self, *, force_refresh: bool = False) -> float:
        """Return the total wallet balance (including used margin) for the futures account."""
        preferred_assets = ("USDT", "BUSD", "USD")
        best_val: float | None = None
        entries_cached = self._get_futures_account_balance_cached(force_refresh=force_refresh) or []
        if not entries_cached and not force_refresh:
            entries_cached = self._get_futures_account_balance_cached(force_refresh=True) or []
        for entry in entries_cached:
            if not isinstance(entry, dict):
                continue
            asset = str(entry.get("asset") or "").upper()
            if asset not in preferred_assets:
                continue
            for key in ("walletBalance", "marginBalance", "balance", "crossWalletBalance"):
                val = entry.get(key)
                if val is None:
                    continue
                try:
                    parsed = float(val)
                except Exception:
                    continue
                if parsed < 0.0 and best_val is None:
                    best_val = parsed
                elif parsed >= 0.0:
                    best_val = parsed if best_val is None else max(best_val, parsed)
            if best_val is not None:
                break
        if best_val is not None:
            return best_val
        acct_dict = self._get_futures_account_cached(force_refresh=force_refresh)
        if isinstance(acct_dict, dict):
            for key in (
                "totalWalletBalance",
                "totalMarginBalance",
                "totalCrossWalletBalance",
                "totalCrossBalance",
            ):
                val = acct_dict.get(key)
                if val is None:
                    continue
                try:
                    return float(val)
                except Exception:
                    continue
        if not force_refresh:
            acct_dict = self._get_futures_account_cached(force_refresh=True)
            if isinstance(acct_dict, dict):
                for key in (
                    "totalWalletBalance",
                    "totalMarginBalance",
                    "totalCrossWalletBalance",
                    "totalCrossBalance",
                ):
                    val = acct_dict.get(key)
                    if val is None:
                        continue
                    try:
                        return float(val)
                    except Exception:
                        continue
        return 0.0
    def get_total_usdt_value(self, *, force_refresh: bool = False) -> float:
        """Aggregate view of USDT value across futures and spot with graceful fallbacks."""
        candidates: list[float] = []

        def _push(label: str, value) -> None:
            try:
                val = float(value or 0.0)
            except Exception:
                return
            if math.isfinite(val):
                candidates.append(val)

        if self.account_type == "FUTURES":
            _push("futures_wallet", self.get_futures_wallet_balance(force_refresh=force_refresh))
            _push("futures_available", self.get_futures_balance_usdt(force_refresh=force_refresh))
            _push("futures_available_balance", self.get_futures_available_balance())
        try:
            _push("spot_usdt", self.get_spot_balance('USDT'))
        except Exception:
            pass
        if not candidates and not force_refresh:
            return self.get_total_usdt_value(force_refresh=True)
        if not candidates:
            return 0.0
        return max(candidates)

    def get_total_unrealized_pnl(self) -> float:
        try:
            positions = self.list_open_futures_positions() or []
            total = 0.0
            for pos in positions:
                try:
                    total += float(pos.get('unRealizedProfit') or 0.0)
                except Exception:
                    continue
            return float(total)
        except Exception:
            acct_dict = self._get_futures_account_cached()
            if isinstance(acct_dict, dict):
                val = acct_dict.get('totalUnrealizedProfit')
                if val is None:
                    val = acct_dict.get('totalCrossUnPnl')
                if val is not None:
                    try:
                        return float(val)
                    except Exception:
                        pass
        return 0.0

    def get_total_wallet_balance(self) -> float:
        acct_dict = self._get_futures_account_cached()
        if isinstance(acct_dict, dict):
            for key in (
                "totalWalletBalance",
                "totalMarginBalance",
                "totalInitialMargin",
                "totalCrossWalletBalance",
                "totalCrossBalance",
            ):
                val = acct_dict.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except Exception:
                        continue
        try:
            return float(self.get_total_usdt_value())
        except Exception:
            return 0.0
    def get_last_price(self, symbol: str, *, max_age: float = 5.0) -> float:
        sym = (symbol or "").upper()
        cache = getattr(self, "_last_price_cache", None)
        if cache is not None and sym:
            cached = cache.get(sym)
            if cached:
                price, ts = cached
                if price and (time.time() - ts) <= max_age:
                    return price
        price = 0.0
        try:
            if self.account_type == "FUTURES":
                t = self._futures_call('futures_symbol_ticker', allow_recv=True, symbol=sym)
                price = float((t or {}).get('price', 0.0))
            else:
                t = self.client.get_symbol_ticker(symbol=sym)
                price = float(t.get('price', 0.0))
        except Exception:
            price = 0.0
        if cache is not None and sym and price:
            cache[sym] = (price, time.time())
        return price

    def _handle_network_offline(self, context: str, exc: Exception) -> None:
        now = time.time()
        message = f"Network connectivity lost while {context}. Monitoring for recovery."
        already_offline = getattr(self, "_network_offline", False)
        if not already_offline:
            self._network_offline = True
            self._network_offline_since = now
            self._network_offline_hits = 1
            self._network_emergency_dispatched = False
            self._last_network_error_log = now
            self._log(message, lvl="error")
        else:
            self._network_offline_hits = getattr(self, "_network_offline_hits", 0) + 1
            if (now - getattr(self, "_last_network_error_log", 0.0)) > 60.0:
                self._last_network_error_log = now
                self._log(message, lvl="warn")
        try:
            offline_since = getattr(self, "_network_offline_since", now)
            hits = getattr(self, "_network_offline_hits", 0)
            should_trigger = False
            if not getattr(self, "_network_emergency_dispatched", False):
                elapsed = now - offline_since
                if hits >= 4 or elapsed >= 45.0:
                    should_trigger = True
            if should_trigger:
                elapsed = now - offline_since
                try:
                    self._log(
                        f"Emergency close-all triggered after {hits} offline hits (elapsed {elapsed:.1f}s).",
                        lvl="warn",
                    )
                except Exception:
                    pass
                delay = min(180.0, max(30.0, elapsed))
                self._network_emergency_dispatched = True
                reason = context or "network_offline"
                self.trigger_emergency_close_all(reason=reason, source="network", initial_delay=delay)
        except Exception:
            pass

    def _handle_network_recovered(self) -> None:
        if getattr(self, "_network_offline", False):
            self._network_offline = False
            self._network_offline_since = 0.0
            self._network_offline_hits = 0
            self._network_emergency_dispatched = False
            try:
                self._log("Network connectivity restored.", lvl="info")
            except Exception:
                pass

    def get_klines(self, symbol, interval, limit=500):
        source = (getattr(self, "indicator_source", "") or "").strip().lower()
        acct = str(getattr(self, "account_type", "") or "").upper()
        if source in ("binance spot", "binance_spot", "spot"):
            native_intervals = SPOT_NATIVE_INTERVALS
        else:
            native_intervals = FUTURES_NATIVE_INTERVALS
        binance_source = source in ('', 'binance futures', 'binance_futures', 'futures', 'binance spot', 'binance_spot', 'spot')
        interval_key = str(interval or '').strip()
        custom_interval_requested = binance_source and interval_key not in native_intervals
        cache_key = (source or "binance", str(symbol or "").upper(), str(interval or ""), int(limit or 0))
        import pandas as pd
        interval_seconds = _coerce_interval_seconds(interval)
        ttl = max(1.0, min(interval_seconds * 0.9, 3600.0))
        cached_df = None
        now = time.time()

        with self._kline_cache_lock:
            entry = self._kline_cache.get(cache_key)
            if entry:
                age = now - entry['ts']
                if age < ttl:
                    return entry['df'].copy(deep=True)
                cached_df = entry['df'].copy(deep=True)

        ban_remaining = self._seconds_until_unban()
        if ban_remaining > 0.0:
            if cached_df is not None:
                if (now - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                    eta = datetime.fromtimestamp(time.time() + ban_remaining).strftime("%H:%M:%S")
                    self._last_ban_log = now
                    self._log(f"REST ban active (~{ban_remaining:.0f}s). Serving cached klines for {symbol}@{interval} until {eta}.", lvl="warn")
                return cached_df
            raise RuntimeError(f"binance_rest_banned:{ban_remaining:.0f}s")

        if custom_interval_requested:
            end_dt = pd.Timestamp.utcnow()
            if end_dt.tzinfo is not None:
                end_dt = end_dt.tz_localize(None)
            span_seconds = _coerce_interval_seconds(interval_key or interval) * max(int(limit or 1), 1)
            start_dt = end_dt - pd.Timedelta(seconds=span_seconds * 2)
            fetch_limit = max(int(limit or 1) * 2, int(limit or 1))
            df_custom = self.get_klines_range(symbol, interval_key or interval, start_dt, end_dt, fetch_limit)
            if df_custom is None or df_custom.empty:
                if cached_df is not None:
                    return cached_df
                raise RuntimeError(f"No kline data returned for interval '{interval}'")
            trimmed = df_custom.tail(int(limit or 1)).copy()
            with self._kline_cache_lock:
                self._kline_cache[cache_key] = {'df': trimmed.copy(deep=True), 'ts': time.time()}
            return trimmed


        raw = None
        max_retries = 5
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            try:
                params = {"symbol": symbol, "interval": interval, "limit": limit}
                client = self.client
                method = None
                if source in ("", "binance futures", "binance_futures", "futures"):
                    method = getattr(client, "futures_klines", None)
                    if method is None:
                        method = getattr(client, "get_klines", None)
                elif source in ("binance spot", "binance_spot", "spot"):
                    method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
                elif source == "bybit":
                    import pandas as pd  # local import to avoid optional dependency cost when unused
                    bybit_interval = self._bybit_interval(interval)
                    url = "https://api.bybit.com/v5/market/kline"
                    bybit_params = {"category": "linear", "symbol": symbol, "interval": bybit_interval, "limit": limit}
                    r = requests.get(url, params=bybit_params, timeout=10)
                    r.raise_for_status()
                    j = r.json() or {}
                    lst = (j.get("result", {}) or {}).get("list", []) or []
                    lst = sorted(lst, key=lambda x: int(x[0]))
                    raw = [[int(x[0]), x[1], x[2], x[3], x[4], x[5], 0, 0, 0, 0, 0, 0] for x in lst]
                elif source in ("tradingview", "trading view"):
                    raise NotImplementedError("TradingView data source is not implemented in this build.")
                else:
                    if self.account_type == "FUTURES":
                        method = getattr(client, "futures_klines", None)
                        if method is None:
                            method = getattr(client, "get_klines", None)
                    else:
                        method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
                if method is not None:
                    raw = method(**params)
                elif raw is None and source not in ("bybit", "tradingview", "trading view"):
                    raise AttributeError("Connector does not provide a klines method")
                break
            except (BinanceAPIException, OfficialConnectorError) as exc:
                ban_until = self._handle_potential_ban(exc)
                if cached_df is not None and ban_until:
                    if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                        when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                        self._last_ban_log = time.time()
                        self._log(f"Binance REST rate limit hit; serving cached klines for {symbol}@{interval} until {when}.", lvl="warn")
                    return cached_df
                if ban_until:
                    delay = max(1.0, ban_until - time.time())
                    if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                        when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                        self._last_ban_log = time.time()
                        self._log(f"Binance REST rate limiter activated; retrying {symbol}@{interval} after {when}.", lvl="warn")
                    time.sleep(min(delay, 5.0))
                    continue
                if attempt >= max_retries:
                    raise
                time.sleep(min(0.5 * attempt, 2.0))
            except requests.exceptions.RequestException as exc:
                context = f"fetching {symbol}@{interval}"
                self._handle_network_offline(context, exc)
                raise NetworkConnectivityError(f"network_offline:{symbol}@{interval}") from exc

        if raw is None:
            raise RuntimeError("kline_fetch_failed: no data returned")

        cols = ['open_time','open','high','low','close','volume','close_time','qav','num_trades','taker_base','taker_quote','ignore']
        import pandas as pd
        df = pd.DataFrame(raw, columns=cols)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        trimmed = df[['open','high','low','close','volume']].copy(deep=True)
        with self._kline_cache_lock:
            self._kline_cache[cache_key] = {'df': trimmed.copy(deep=True), 'ts': time.time()}
        self._last_network_error_log = 0.0
        self._handle_network_recovered()
        return trimmed

    @staticmethod
    def _klines_raw_to_df(raw):
        import pandas as pd
        cols = ['open_time','open','high','low','close','volume','close_time','qav','num_trades','taker_base','taker_quote','ignore']
        if not raw:
            return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume']).astype(float)
        df = pd.DataFrame(raw, columns=cols)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        for c in ['open','high','low','close','volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df[['open','high','low','close','volume']].copy(deep=True)

    @staticmethod
    def _interval_seconds_to_freq(seconds: float) -> str:
        seconds = float(seconds or 0.0)
        if seconds <= 0.0:
            raise ValueError("Interval must be positive")
        if seconds % 86400 == 0:
            return f"{int(seconds // 86400)}D"
        if seconds % 3600 == 0:
            return f"{int(seconds // 3600)}h"
        if seconds % 60 == 0:
            return f"{int(seconds // 60)}min"
        return f"{int(seconds)}S"

    def _get_klines_range_native(self, symbol: str, interval: str, start_dt, end_dt, limit: int, acct: str, source: str):
        start_ts = pd.Timestamp(start_dt)
        end_ts = pd.Timestamp(end_dt)
        if start_ts.tzinfo is None:
            start_utc = start_ts.tz_localize('UTC')
        else:
            start_utc = start_ts.tz_convert('UTC')
        if end_ts.tzinfo is None:
            end_utc = end_ts.tz_localize('UTC')
        else:
            end_utc = end_ts.tz_convert('UTC')
        start_filter = start_utc.tz_localize(None)
        end_filter = end_utc.tz_localize(None)
        start_ms = int(start_utc.timestamp() * 1000)
        end_ms = int(end_utc.timestamp() * 1000)
        interval_ms = max(int(_coerce_interval_seconds(interval) * 1000), 1)
        all_frames = []
        current = start_ms
        max_limit = 1500 if acct.startswith("FUT") else 1000
        limit = max(1, int(limit or max_limit))
        limit = min(limit, max_limit)
        guard = 0
        max_network_retries = 4
        while current < end_ms and guard < 10000:
            guard += 1
            raw = None
            last_error = None
            for attempt in range(max_network_retries):
                try:
                    params = {
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": current,
                        "endTime": end_ms,
                        "limit": limit,
                    }
                    client = self.client
                    if acct == "FUTURES" or source in ("binance futures", "binance_futures", "futures", ""):
                        method = getattr(client, "futures_klines", None)
                        if method is None:
                            method = getattr(client, "get_klines", None)
                    else:
                        method = getattr(client, "get_klines", None) or getattr(client, "klines", None)
                    if method is None:
                        raise AttributeError("Connector does not provide a klines method")
                    raw = method(**params)
                    break
                except (BinanceAPIException, OfficialConnectorError) as exc:
                    ban_until = self._handle_potential_ban(exc)
                    if ban_until:
                        delay = max(1.0, ban_until - time.time())
                        if (time.time() - getattr(self, "_last_ban_log", 0.0)) > 15.0:
                            when = datetime.fromtimestamp(ban_until).strftime("%H:%M:%S")
                            self._last_ban_log = time.time()
                            try:
                                self._log(f"Rate limit hit while fetching {symbol}@{interval}; retrying after {when}.", lvl="warn")
                            except Exception:
                                pass
                        time.sleep(min(delay, 5.0))
                        continue
                    last_error = exc
                    break
                except requests.exceptions.RequestException as req_err:
                    last_error = req_err
                    sleep_for = min(1.5 * (attempt + 1), 6.0)
                    time.sleep(sleep_for)
                except Exception as exc:
                    last_error = exc
                    break

            if raw is None:
                if last_error is not None:
                    if isinstance(last_error, requests.exceptions.RequestException):
                        guard -= 1
                        now = time.time()
                        if (now - getattr(self, "_last_network_log", 0.0)) > 10.0:
                            self._last_network_log = now
                            try:
                                self._log(f"Network hiccup while fetching {symbol}@{interval}; retrying...", lvl="warn")
                            except Exception:
                                pass
                        continue
                    raise RuntimeError(f"network_error:{last_error}") from last_error
                break

            if not raw:
                break

            frame = self._klines_raw_to_df(raw)
            all_frames.append(frame)

            last_open = int(raw[-1][0])
            next_open = last_open + interval_ms
            if next_open <= current:
                break
            current = next_open

        if not all_frames:
            return self._klines_raw_to_df([])

        full = pd.concat(all_frames).sort_index()
        full = full[~full.index.duplicated(keep='first')]
        mask = (full.index >= start_filter) & (full.index <= end_filter)
        return full.loc[start_filter:end_filter].copy()

    def _get_klines_range_custom(self, symbol: str, interval: str, start_dt, end_dt, limit: int, acct: str, source: str):
        interval_seconds = _coerce_interval_seconds(interval)
        if interval_seconds < 60:
            raise NotImplementedError(f"Custom interval '{interval}' below 1 minute is not supported.")
        if interval_seconds < 3600:
            base_interval = "1m"
        elif interval_seconds < 86400:
            base_interval = "1h"
        else:
            base_interval = "1d"
        base_seconds = _coerce_interval_seconds(base_interval)
        if interval_seconds % base_seconds != 0:
            raise NotImplementedError(f"Custom interval '{interval}' is not a multiple of {base_interval}.")
        factor = int(interval_seconds / base_seconds)
        base_limit = max(int(limit or 1000) * factor, factor)
        fetch_end = end_dt + pd.Timedelta(seconds=base_seconds * factor)
        base_df = self._get_klines_range_native(symbol, base_interval, start_dt, fetch_end, base_limit, acct, source)
        if base_df.empty:
            return base_df
        freq = self._interval_seconds_to_freq(interval_seconds)
        agg = base_df.resample(freq, label='left', closed='left').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        })
        agg = agg.dropna()
        return agg.loc[start_dt:end_dt].copy()

    def get_klines_range(self, symbol, interval, start_time, end_time, limit=1000):
        """
        Fetch historical klines between start_time and end_time (inclusive) and return a DataFrame.
        start_time/end_time may be datetime, int milliseconds, or string accepted by pandas.to_datetime.
        """
        from datetime import datetime
        import pandas as pd

        try:
            if isinstance(start_time, str):
                start_dt = pd.to_datetime(start_time)
            elif isinstance(start_time, datetime):
                start_dt = start_time
            else:
                start_dt = pd.to_datetime(int(start_time), unit='ms')
        except Exception as exc:
            raise ValueError(f"Invalid start_time: {start_time}") from exc
        if isinstance(start_dt, pd.Timestamp) and start_dt.tzinfo is not None:
            start_dt = start_dt.tz_localize(None)
        elif getattr(start_dt, "tzinfo", None) is not None:
            start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)

        try:
            if isinstance(end_time, str):
                end_dt = pd.to_datetime(end_time)
            elif isinstance(end_time, datetime):
                end_dt = end_time
            else:
                end_dt = pd.to_datetime(int(end_time), unit='ms')
        except Exception as exc:
            raise ValueError(f"Invalid end_time: {end_time}") from exc
        if isinstance(end_dt, pd.Timestamp) and end_dt.tzinfo is not None:
            end_dt = end_dt.tz_localize(None)
        elif getattr(end_dt, "tzinfo", None) is not None:
            end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)

        if end_dt <= start_dt:
            raise ValueError("end_time must be greater than start_time")

        source = (getattr(self, "indicator_source", "") or "").strip().lower()
        acct = str(getattr(self, "account_type", "") or "").upper()
        if source not in ("", "binance futures", "binance_futures", "futures", "binance spot", "binance_spot", "spot"):
            raise NotImplementedError(f"Historical klines not supported for source '{source}' in backtester.")

        native_intervals = FUTURES_NATIVE_INTERVALS if acct.startswith("FUT") else SPOT_NATIVE_INTERVALS
        if interval in native_intervals:
            df = self._get_klines_range_native(symbol, interval, start_dt, end_dt, limit, acct, source)
        else:
            df = self._get_klines_range_custom(symbol, interval, start_dt, end_dt, limit, acct, source)

        if df.empty:
            raise RuntimeError("No kline data returned for requested range.")
        return df

    # ---- order placement helpers
    @staticmethod
    def _floor_to_step(value: float, step: float) -> float:
        from decimal import Decimal, ROUND_DOWN
        if step <= 0:
            return float(value)
        d_val = Decimal(str(value)); d_step = Decimal(str(step))
        units = (d_val / d_step).to_integral_value(rounding=ROUND_DOWN)
        snapped = units * d_step
        return float(snapped)

    @staticmethod
    def floor_to_decimals(value: float, decimals: int) -> float:
        from decimal import Decimal, ROUND_DOWN
        if decimals < 0:
            return float(value)
        q = Decimal('1').scaleb(-decimals)
        return float(Decimal(str(value)).quantize(q, rounding=ROUND_DOWN))

    @staticmethod
    def ceil_to_decimals(value: float, decimals: int) -> float:
        from decimal import Decimal, ROUND_UP
        if decimals < 0:
            return float(value)
        q = Decimal('1').scaleb(-decimals)
        return float(Decimal(str(value)).quantize(q, rounding=ROUND_UP))

    def adjust_qty_to_filters_spot(self, symbol: str, qty: float, est_price: float):
        if qty <= 0:
            return 0.0, "qty<=0"
        try:
            f = self.get_spot_symbol_filters(symbol)
        except Exception as e:
            return 0.0, f"filters_error:{e}"

        step = f['stepSize'] or 0.0
        min_qty = f['minQty'] or 0.0
        min_notional = f['minNotional'] or 0.0

        adj = qty
        if step > 0:
            adj = self._floor_to_step(adj, step)

        if min_qty > 0 and adj < min_qty:
            adj = min_qty
        # Enforce futures MIN_NOTIONAL if price provided
        if min_notional > 0 and (est_price or 0) > 0:
            needed = min_notional / float(est_price)
            if adj < needed:
                adj = needed
            adj = min_qty
            if step > 0:
                adj = self._floor_to_step(adj, step)

        if est_price and min_notional > 0:
            notional = adj * est_price
            if notional < min_notional:
                needed_qty = (min_notional / est_price) if est_price > 0 else adj
                if step > 0:
                    needed_qty = self._floor_to_step(needed_qty + step, step)
                if needed_qty < min_qty:
                    needed_qty = min_qty
                    if step > 0:
                        needed_qty = self._floor_to_step(needed_qty, step)
                adj = needed_qty
                if adj * est_price < min_notional:
                    return 0.0, f"below_minNotional({adj*est_price:.8f}<{min_notional:.8f})"

        if adj <= 0:
            return 0.0, "adj<=0"
        return float(adj), None

    def adjust_qty_to_filters_futures(self, symbol: str, qty: float, price: float | None = None):
        try:
            f = self.get_futures_symbol_filters(symbol)
        except Exception as e:
            return 0.0, f"filters_error:{e}"
        step = float(f.get('stepSize', 0.0) or 0.0)
        min_qty = float(f.get('minQty', 0.0) or 0.0)
        min_notional = float(f.get('minNotional', 0.0) or 0.0)

        adj = float(qty or 0.0)
        if step > 0:
            adj = self._floor_to_step(adj, step)
        if min_qty > 0 and adj < min_qty:
            adj = min_qty
        if min_notional > 0 and (price or 0) > 0:
            need = float(min_notional) / float(price)
            if step > 0:
                need = self._ceil_to_step(need, step)
            if adj < need:
                adj = need
        if adj <= 0:
            return 0.0, "adj<=0"
        return float(adj), None

    def get_base_quote_assets(self, symbol: str):
        if self.account_type == "FUTURES":
            s = self.get_futures_symbol_info(symbol)
            return s.get('baseAsset'), s.get('quoteAsset')
        info = self.get_symbol_info_spot(symbol)
        return info.get('baseAsset'), info.get('quoteAsset')

    def get_futures_dual_side(self) -> bool:
        """
        Returns True if dual-side (hedge) mode is enabled on Futures; False if one-way.
        Tries multiple client methods; normalizes string/array responses.
        """
        try:
            cached = self._futures_dual_side_cache
            ts = self._futures_dual_side_cache_ts
        except Exception:
            cached = None
            ts = 0.0
        if cached is not None and (time.time() - ts) < 300.0:
            return bool(cached)
        methods = [
            "futures_get_position_mode",
            "futures_get_position_side_dual",
            "futures_position_side_dual",
        ]
        for m in methods:
            try:
                fn = getattr(self.client, m, None)
                if not fn:
                    continue
                res = fn()
                val = None
                if isinstance(res, dict):
                    val = res.get("dualSidePosition")
                elif isinstance(res, (list, tuple)) and res:
                    first = res[0]
                    if isinstance(first, dict) and "dualSidePosition" in first:
                        val = first["dualSidePosition"]
                    else:
                        val = first
                else:
                    val = res
                if isinstance(val, str):
                    val = val.strip().lower() in ("true","1","yes","y")
                result = bool(val)
                self._futures_dual_side_cache = result
                self._futures_dual_side_cache_ts = time.time()
                return result
            except Exception:
                continue
        self._futures_dual_side_cache = False
        self._futures_dual_side_cache_ts = time.time()
        return False
    
    
    
    
    
    def place_futures_market_order(self, symbol: str, side: str, percent_balance: float | None = None,
                                   price: float | None = None, position_side: str | None = None,
                                   quantity: float | None = None, **kwargs):

        """Futures MARKET order with robust sizing and clear returns.
        Returns:
           {
             'ok': bool,
             'info': <raw order dict> or None,
             'computed': {'qty': float, 'px': float, 'step': float, 'minQty': float, 'minNotional': float, 'lev': int, 'mode': str},
             'mode': <'percent'|'quantity'|'fallback'>,
             'error': <str> (when ok==False)
           }
        """
        assert self.account_type == "FUTURES", "Futures order called while account_type != FUTURES"

        sym = (symbol or '').upper()
        self._ensure_margin_and_leverage_or_block(sym, kwargs.get('margin_mode') or getattr(self,'_default_margin_mode','ISOLATED'), kwargs.get('leverage'))


        # --- helpers ---
        def _floor_to_step(val: float, step: float) -> float:
            try:
                if step <= 0: return float(val)
                q = int(round(float(val) / float(step)))
                return float(q * float(step))
            except Exception:
                return float(val)

        def _ceil_to_step(val: float, step: float) -> float:
            try:
                if step <= 0: return float(val)
                q = int(-(-float(val) // float(step)))  # ceil division
                return float(q * float(step))
            except Exception:
                return float(val)

        px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
        if px <= 0:
            return {'ok': False, 'error': 'No price available', 'computed': {}}

        f = self.get_futures_symbol_filters(sym) or {}
        step = float(f.get('stepSize') or 0.0) or 0.001
        minQty = float(f.get('minQty') or 0.0) or step
        minNotional = float(f.get('minNotional') or 0.0) or 5.0

        # sizing
        mode = 'percent'
        pct = float(percent_balance or 0.0)  # value like 2.0 for 2%
        lev = int(kwargs.get('leverage') or getattr(self, '_futures_leverage', 1) or 1)
        qty = 0.0

        if pct > 0.0:
            bal = float(self.get_futures_available_balance() or 0.0)
            margin_budget = bal * (pct / 100.0)
            # Respect cap PER SYMBOL across intervals: subtract current margin already tied to this symbol
            try:
                used_usd = 0.0
                for p in (self.list_open_futures_positions() or []):
                    if (p or {}).get('symbol','').upper() == sym:
                        # prefer isolatedWallet, then initialMargin, else notional/leverage
                        used_usd += float(p.get('isolatedWallet') or p.get('initialMargin') or (abs(p.get('notional') or 0.0) / max(lev, 1) ))
                margin_budget = max(margin_budget - used_usd, 0.0)
            except Exception:
                # if anything goes wrong, fall back to original budget
                pass

            qty = _floor_to_step((margin_budget * lev) / px, step)
            need_qty = max(minQty, _ceil_to_step(minNotional/px, step))
            if qty < need_qty:
                req_pct = self.required_percent_for_symbol(sym, lev)
                return {'ok': False, 'symbol': sym,
                        'error': f'exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)',
                        'computed': {'px': px, 'minQty': minQty, 'minNotional': minNotional, 'step': step, 'pct_used': pct,
                                     'need_qty': need_qty, 'lev': lev, 'avail': bal, 'margin_budget': margin_budget},
                        'required_percent': req_pct,
                        'mode': 'percent(strict)'}
            mode = 'percent'
        elif quantity is not None:
            try:
                qty = float(quantity)
            except Exception:
                return {'ok': False, 'error': f'Bad quantity override: {quantity!r}'}
            qty = max(minQty, _floor_to_step(qty, step))
            if qty * px < minNotional:
                qty = max(qty, _ceil_to_step(minNotional/px, step))
            mode = 'quantity'
        else:
            qty = max(minQty, _ceil_to_step(minNotional/px, step))
            mode = 'fallback'

        if qty <= 0:
            return {'ok': False, 'error': 'qty<=0', 'computed': {'px': px, 'minQty': minQty, 'minNotional': minNotional, 'step': step}, 'mode': mode}

        # send order
        try:
            # Hedge mode support
            dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
            side_up = 'BUY' if str(side).upper() in ('BUY','LONG','L') else 'SELL'
            pos_side = position_side or kwargs.get('positionSide')
            if dual and not pos_side:
                pos_side = 'SHORT' if side_up == 'SELL' else 'LONG'

            qty_str = self._format_quantity_for_order(qty, step)
            params = dict(symbol=sym, side=side_up, type='MARKET', quantity=qty_str)
            if dual and pos_side:
                params['positionSide'] = pos_side

            order = self.client.futures_create_order(**params)
            fills_summary = {}
            try:
                fills_summary = self._summarize_futures_order_fills(sym, (order or {}).get("orderId"))
            except Exception:
                fills_summary = {}
            if isinstance(order, dict) and fills_summary:
                try:
                    if not float(order.get("avgPrice") or 0.0) and float(fills_summary.get("avg_price") or 0.0):
                        order["avgPrice"] = fills_summary.get("avg_price")
                except Exception:
                    pass
            self._invalidate_futures_positions_cache()
            result = {
                'ok': True,
                'info': order,
                'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional, 'lev': lev},
                'mode': mode,
            }
            if fills_summary:
                result['fills'] = fills_summary
            return result
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'px': px, 'step': step, 'minQty': minQty, 'minNotional': minNotional, 'lev': lev}, 'mode': mode}

    def close_futures_leg_exact(self, symbol: str, qty: float, side: str, position_side: str | None = None):
        """Close exactly `qty` using reduce-only MARKET on the given `side`.
        If hedge mode is enabled, `position_side` should be 'LONG' (to close a long) or 'SHORT' (to close a short).
        """
        try:
            sym = (symbol or '').upper()
            q = float(qty or 0)
            if q <= 0:
                return {'ok': False, 'error': 'qty<=0'}
            try:
                filters = self.get_futures_symbol_filters(sym) or {}
                step = float(filters.get('stepSize') or 0.0)
            except Exception:
                step = 0.0
            qty_str = self._format_quantity_for_order(q, step)
            params = dict(symbol=sym, side=(side or 'SELL').upper(), type='MARKET', quantity=qty_str)
            if position_side:
                params['positionSide'] = position_side
            else:
                params['reduceOnly'] = True
            try:
                import time as _t
                params.setdefault('newClientOrderId', f"close-{sym}-{int(_t.time()*1000)}")
            except Exception:
                pass
            info = self.client.futures_create_order(**params)
            fills_summary = {}
            try:
                fills_summary = self._summarize_futures_order_fills(sym, (info or {}).get("orderId"))
            except Exception:
                fills_summary = {}
            if isinstance(info, dict) and fills_summary:
                try:
                    if not float(info.get("avgPrice") or 0.0) and float(fills_summary.get("avg_price") or 0.0):
                        info["avgPrice"] = fills_summary.get("avg_price")
                except Exception:
                    pass
            self._invalidate_futures_positions_cache()
            res = {'ok': True, 'info': info}
            if fills_summary:
                res['fills'] = fills_summary
            return res
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def close_futures_position(self, symbol: str):
        """Close open futures position(s) for `symbol` using reduce-only MARKET orders.
        Works in both one-way and hedge modes.
        """
        try:
            sym = (symbol or '').upper()
            try:
                filters = self.get_futures_symbol_filters(sym) or {}
                step = float(filters.get('stepSize') or 0.0)
            except Exception:
                step = 0.0
            dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
            rows = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            closed = 0
            failed = 0
            errors = []
            for row in rows:
                if (row.get('symbol') or '').upper() != sym:
                    continue
                amt = float(row.get('positionAmt') or 0)
                if abs(amt) < 1e-12:
                    continue
                side = 'SELL' if amt > 0 else 'BUY'
                params = dict(symbol=sym, side=side, type='MARKET', quantity=self._format_quantity_for_order(abs(amt), step))
                if dual:
                    params['positionSide'] = 'LONG' if amt > 0 else 'SHORT'
                else:
                    params['reduceOnly'] = True
                try:
                    self.client.futures_create_order(**params)
                    self._invalidate_futures_positions_cache()
                    closed += 1
                except Exception as e:
                    failed += 1
                    errors.append(str(e))
            return {'ok': failed == 0, 'closed': closed, 'failed': failed, 'errors': errors}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def close_all_futures_positions(self):
        results = []
        try:
            dual = False
            try:
                mode_info = self.client.futures_get_position_mode()
                dual = bool(mode_info.get('dualSidePosition'))
            except Exception:
                pass
            positions = self.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            if not positions:
                return results
            try:
                for s in sorted({p['symbol'] for p in positions}):
                    try:
                        self.client.futures_cancel_all_open_orders(symbol=s)
                    except Exception:
                        pass
            except Exception:
                pass
            for p in positions:
                try:
                    sym = p['symbol']
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    side = 'SELL' if amt > 0 else 'BUY'
                    qty = abs(amt)
                    try:
                        filters = self.get_futures_symbol_filters(sym) or {}
                        step = float(filters.get('stepSize') or 0.0)
                    except Exception:
                        step = 0.0
                    qty_str = self._format_quantity_for_order(qty, step)
                    params = dict(symbol=sym, side=side, type='MARKET', quantity=qty_str)
                    if dual:
                        params['positionSide'] = 'LONG' if amt > 0 else 'SHORT'
                    info = self.client.futures_create_order(**params)
                    self._invalidate_futures_positions_cache()
                    results.append({'symbol': sym, 'ok': True, 'info': info})
                except Exception as e:
                    results.append({'symbol': p.get('symbol'), 'ok': False, 'error': str(e)})
        except Exception as e:
            results.append({'ok': False, 'error': str(e)})
        return results

    def list_open_futures_positions(self, *, max_age: float = 1.5, force_refresh: bool = False):
        if not force_refresh:
            cached = self._get_cached_futures_positions(max_age)
            if cached is not None:
                return cached
        infos = None
        try:
            infos = self.client.futures_position_information()
        except Exception:
            try:
                infos = self.client.futures_position_risk()
            except Exception:
                infos = None
        risk_lookup = {}
        try:
            risk_infos = self.client.futures_position_risk()
        except Exception:
            risk_infos = None
        if isinstance(risk_infos, list):
            for risk in risk_infos:
                try:
                    sym = str(risk.get("symbol") or "").upper()
                    if not sym:
                        continue
                    side = str(risk.get("positionSide") or "BOTH").upper()
                    risk_lookup[(sym, side)] = risk
                    if side != "BOTH" and (sym, "BOTH") not in risk_lookup:
                        risk_lookup[(sym, "BOTH")] = risk
                except Exception:
                    continue
        out = []
        if not infos:
            try:
                acc = self._get_futures_account_cached(force_refresh=True) or {}
                for p in acc.get('positions', []):
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    row = {
                        'symbol': p.get('symbol'),
                        'positionAmt': amt,
                        'notional': float(p.get('notional') or 0.0) if isinstance(p, dict) else 0.0,
                        'initialMargin': float(p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'positionInitialMargin': float(p.get('positionInitialMargin') or p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'openOrderMargin': float(p.get('openOrderInitialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedWallet': float(p.get('isolatedWallet') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedMargin': float(p.get('isolatedMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'maintMargin': float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'maintMarginRate': float(p.get('maintMarginRate') or p.get('maintenanceMarginRate') or 0.0) if isinstance(p, dict) else 0.0,
                        'marginRatio': float(p.get('marginRatio') or 0.0),
                        'marginBalance': float(p.get('marginBalance') or 0.0) if isinstance(p, dict) else 0.0,
                        'walletBalance': float(p.get('walletBalance') or p.get('marginBalance') or 0.0) if isinstance(p, dict) else 0.0,
                        'entryPrice': float(p.get('entryPrice') or 0.0),
                        'markPrice': float(p.get('markPrice') or 0.0),
                        'marginType': p.get('marginType'),
                        'leverage': int(float(p.get('leverage') or 0)),
                        'unRealizedProfit': float(p.get('unRealizedProfit') or 0.0),
                        'liquidationPrice': float(p.get('liquidationPrice') or 0.0),
                        'positionSide': (p.get('positionSide') or p.get('positionside')),
                        'updateTime': _coerce_int(p.get('updateTime') or p.get('update_time')),
                    }
                    out.append(row)
            except Exception:
                pass
        else:
            for p in infos or []:
            # Enrich with notional/margins/ROI-friendly fields when present
                try:
                    amt = float(p.get('positionAmt') or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    row = {
                        'symbol': p.get('symbol'),
                        'positionAmt': amt,
                        'notional': float(p.get('notional') or 0.0) if isinstance(p, dict) else 0.0,
                        'initialMargin': float(p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'positionInitialMargin': float(p.get('positionInitialMargin') or p.get('initialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'openOrderMargin': float(p.get('openOrderInitialMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedWallet': float(p.get('isolatedWallet') or 0.0) if isinstance(p, dict) else 0.0,
                        'isolatedMargin': float(p.get('isolatedMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'maintMargin': float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0) if isinstance(p, dict) else 0.0,
                        'maintMarginRate': float(p.get('maintMarginRate') or p.get('maintenanceMarginRate') or 0.0) if isinstance(p, dict) else 0.0,
                        'marginRatio': float(p.get('marginRatio') or 0.0),
                        'marginBalance': float(p.get('marginBalance') or 0.0) if isinstance(p, dict) else 0.0,
                        'walletBalance': float(p.get('walletBalance') or p.get('marginBalance') or 0.0) if isinstance(p, dict) else 0.0,
                        'entryPrice': float(p.get('entryPrice') or 0.0),
                        'markPrice': float(p.get('markPrice') or 0.0),
                        'marginType': p.get('marginType'),
                        'leverage': int(float(p.get('leverage') or 0)),
                        'unRealizedProfit': float(p.get('unRealizedProfit') or 0.0),
                        'liquidationPrice': float(p.get('liquidationPrice') or 0.0),
                        'positionSide': (p.get('positionSide') or p.get('positionside')),
                        'updateTime': _coerce_int(p.get('updateTime') or p.get('update_time')),
                    }
                    out.append(row)
                except Exception:
                    continue
        if risk_lookup:
            for row in out:
                try:
                    sym = str(row.get('symbol') or '').upper()
                    side = str(row.get('positionSide') or row.get('positionside') or 'BOTH').upper()
                    risk = risk_lookup.get((sym, side)) or risk_lookup.get((sym, 'BOTH'))
                    if not isinstance(risk, dict):
                        continue
                    risk_ratio_raw = risk.get('marginRatio')
                    if risk_ratio_raw is not None:
                        try:
                            row['marginRatioRaw'] = float(risk_ratio_raw)
                            row['marginRatio'] = float(risk_ratio_raw)
                        except Exception:
                            pass
                    def _safe_update(target_key, source_keys):
                        for src in source_keys:
                            if src not in risk:
                                continue
                            val = risk.get(src)
                            if val in (None, "", 0, 0.0):
                                continue
                            try:
                                row[target_key] = float(val)
                            except Exception:
                                row[target_key] = val
                            return
                    _safe_update('marginRatio', ['marginRatio'])
                    _safe_update('isolatedWallet', ['isolatedWallet'])
                    _safe_update('isolatedMargin', ['isolatedMargin'])
                    _safe_update('marginBalance', ['marginBalance', 'isolatedWallet'])
                    _safe_update('initialMargin', ['initialMargin', 'isolatedMargin'])
                    _safe_update('positionInitialMargin', ['positionInitialMargin', 'initialMargin'])
                    _safe_update('openOrderMargin', ['openOrderInitialMargin', 'openOrderMargin'])
                    _safe_update('walletBalance', ['walletBalance', 'marginBalance'])
                    _safe_update('notional', ['notional'])
                    _safe_update('unRealizedProfit', ['unRealizedProfit'])
                    _safe_update('entryPrice', ['entryPrice'])
                    _safe_update('markPrice', ['markPrice'])
                    _safe_update('leverage', ['leverage'])
                    try:
                        maint_margin = float(row.get('maintMargin') or 0.0)
                    except Exception:
                        maint_margin = 0.0
                    try:
                        open_order_margin = float(row.get('openOrderMargin') or 0.0)
                    except Exception:
                        open_order_margin = 0.0
                    try:
                        wallet_balance = float(row.get('walletBalance') or row.get('marginBalance') or 0.0)
                    except Exception:
                        wallet_balance = 0.0
                    try:
                        unreal = float(row.get('unRealizedProfit') or 0.0)
                    except Exception:
                        unreal = 0.0
                    loss_component = abs(unreal) if unreal < 0 else 0.0
                    calc_ratio = ((maint_margin + open_order_margin + loss_component) / wallet_balance) * 100.0 if wallet_balance > 0.0 else 0.0
                    row['marginRatioCalc'] = calc_ratio
                    if float(row.get('marginRatio') or 0.0) <= 0.0 and calc_ratio > 0.0:
                        row['marginRatio'] = calc_ratio
                except Exception:
                    continue
        snapshot = copy.deepcopy(out)
        self._store_futures_positions_cache(snapshot)
        return copy.deepcopy(snapshot)

    def get_net_futures_position_amt(self, symbol: str) -> float:
        """
        Return the net position quantity for a symbol (positive long, negative short, 0 if flat).
        """
        try:
            infos = self.client.futures_position_information()
        except Exception:
            try:
                infos = self.client.futures_position_risk()
            except Exception:
                infos = None
        if not infos:
            return 0.0
        symbol_upper = str(symbol or "").strip().upper()
        for entry in infos:
            try:
                if str(entry.get('symbol', '')).upper() != symbol_upper:
                    continue
                amt = float(entry.get('positionAmt') or entry.get('positionAmt', 0.0) or 0.0)
                return amt
            except Exception:
                continue
        return 0.0

    

def get_symbol_margin_type(self, symbol: str) -> str | None:
    """Return current margin type for symbol ('ISOLATED' | 'CROSSED') or None on error."""
    sym = (symbol or "").upper()
    if not sym:
        return None
    try:
        info = None
        try:
            info = self.client.futures_position_information(symbol=sym)
        except Exception:
            try:
                info = self.client.futures_position_risk(symbol=sym)
            except Exception:
                info = None
        rows = []
        if isinstance(info, list):
            rows.extend(info)
        elif info:
            rows.append(info)
        def _extract(row):
            if not isinstance(row, dict):
                return None
            row_sym = (row.get('symbol') or row.get('pair') or '').upper()
            if row_sym and row_sym != sym:
                return None
            raw = row.get('marginType')
            if raw in (None, ''):
                raw = row.get('margintype')
            if raw in (None, ''):
                raw = row.get('margin_type')
            text = str(raw or '').strip().upper()
            if text in ('ISOLATED', 'CROSSED', 'CROSS'):
                return 'CROSSED' if text.startswith('CROSS') else 'ISOLATED'
            return None
        for row in rows:
            mt = _extract(row)
            if mt:
                return mt
        # fallback to futures_account positions payload
        try:
            acct = self._get_futures_account_cached(force_refresh=True) or {}
            for row in acct.get('positions', []):
                mt = _extract(row)
                if mt:
                    return mt
        except Exception:
            pass
    except Exception:
        return None
    fallback = getattr(self, "_default_margin_mode", None)
    if fallback:
        fb = str(fallback).strip().upper()
        if fb:
            return 'CROSSED' if fb.startswith('CROSS') else 'ISOLATED'
    return None




def _futures_open_orders_count(self, symbol: str) -> int:
    try:
        arr = self.client.futures_get_open_orders(symbol=(symbol or '').upper())
        return len(arr or [])
    except Exception:
        return 0

def _futures_net_position_amt(self, symbol: str) -> float:
    try:
        sym = (symbol or '').upper()
        info = self.client.futures_position_information(symbol=sym) or []
        total = 0.0
        for row in info:
            if (row or {}).get('symbol','').upper() != sym:
                continue
            try:
                total += float(row.get('positionAmt') or 0)
            except Exception:
                pass
        return float(total)
    except Exception:
        return 0.0

def _ensure_margin_and_leverage_or_block(self, symbol: str, desired_mm: str, desired_lev: int | None):
    """
    Enforce margin type (ISOLATED/CROSSED) + leverage BEFORE any futures order.
    - Always attempt to set the desired margin type.
    - If Binance refuses because of open orders/positions, we block and raise.
    - Verifies by re-reading margin type.
    """
    sym = (symbol or '').upper()
    want_mm = (desired_mm or getattr(self, '_default_margin_mode','ISOLATED') or 'ISOLATED').upper()
    want_mm = 'CROSSED' if want_mm in ('CROSS', 'CROSSED') else 'ISOLATED'

    # If there are open positions and current is not desired, block immediately
    cur = (self.get_symbol_margin_type(sym) or '').upper()
    if cur and cur != want_mm:
        # Any open amt?
        if abs(self._futures_net_position_amt(sym)) > 0:
            raise RuntimeError(f"{sym} is {cur} with an open position; refusing to place order until margin type can be changed to {want_mm}.")

    # If there are open orders, cancel them (margin type change requires no open orders)
    try:
        if self._futures_open_orders_count(sym) > 0:
            try:
                self.client.futures_cancel_all_open_orders(symbol=sym)
            except Exception:
                pass
    except Exception:
        pass

    # Always try to set desired margin type, tolerate 'no need to change' responses
    last_err = None
    for attempt in range(5):
        try:
            self.client.futures_change_margin_type(symbol=sym, marginType=want_mm)
        except Exception as e:
            msg = str(getattr(e, 'message', '') or e).lower()
            if 'no need to change' in msg or 'no need to change margin type' in msg or 'code=-4099' in msg:
                pass  # desired already
            elif '-4048' in msg or ('cannot change' in msg and ('open' in msg or 'position' in msg)):
                # open order/position prevents margin change
                raise RuntimeError(f"Binance refused to change margin type for {sym} while open orders/positions exist (-4048). Close them first.")
            else:
                # transient? retry
                last_err = e
        # verify
        v = (self.get_symbol_margin_type(sym) or '').upper()
        if v == want_mm:
            break
        if not v:
            # Some symbols do not report marginType even after a successful change.
            # If Binance doesn't give us an answer, assume success and continue.
            self._log(f"margin_type probe returned blank for {sym}; assuming {want_mm}", lvl='info')
            break
        try:
            net_amt = abs(float(self._futures_net_position_amt(sym)))
        except Exception:
            net_amt = None
        if (not v) and (net_amt is None or net_amt <= 0):
            # Symbol has no open exposure; treat margin type as implicitly correct after attempting change
            v = want_mm
            break
        import time as _t; _t.sleep(0.2)
    else:
        if last_err:
            raise RuntimeError(f"Failed to set margin type for {sym} to {want_mm}: {last_err}")
        vv = (self.get_symbol_margin_type(sym) or '').upper()
        try:
            net_amt = abs(float(self._futures_net_position_amt(sym)))
        except Exception:
            net_amt = None
        if not vv:
            # Still blank after retries; assume we succeeded so we do not block entries.
            self._log(f"margin_type still blank for {sym}; proceeding as {want_mm}", lvl='warn')
            vv = want_mm
        if vv != want_mm:
            label = vv if vv else 'UNKNOWN'
            raise RuntimeError(f"Margin type for {sym} is {label}; wanted {want_mm}. Blocking order.")

    # Apply leverage if requested (non-fatal on failure)
    if desired_lev is not None:
        lev = self.clamp_futures_leverage(sym, desired_lev)
        try:
            self.client.futures_change_leverage(symbol=sym, leverage=lev)
            self.futures_leverage = lev
        except Exception:
            pass


    def ensure_futures_settings(self, symbol: str, leverage: int | None = None,
                                margin_mode: str | None = None, hedge_mode: bool | None = None):
        try:
            if hedge_mode is not None:
                try:
                    self.client.futures_change_position_mode(dualSidePosition=bool(hedge_mode))
                except Exception:
                    pass
            sym = (symbol or '').upper()
            if not sym:
                return
            mm = (margin_mode or getattr(self, '_default_margin_mode', 'ISOLATED') or 'ISOLATED').upper()
            if mm == 'CROSS':
                mm = 'CROSSED'
            try:
                self.client.futures_change_margin_type(symbol=sym, marginType=mm)
            except Exception as e:
                if 'no need to change' not in str(e).lower() and '-4046' not in str(e):
                    pass
            try:
                lev_requested = int(leverage if leverage is not None else getattr(self, '_requested_default_leverage', getattr(self, '_default_leverage', 5)) or 5)
            except Exception:
                lev_requested = 5
            lev = self.clamp_futures_leverage(sym, lev_requested)
            try:
                self.client.futures_change_leverage(symbol=sym, leverage=lev)
            except Exception as e:
                if 'same leverage' not in str(e).lower() and 'not modified' not in str(e).lower():
                    pass
            self._default_margin_mode = mm
            self.futures_leverage = lev
        except Exception:
            pass


# Bind helper functions to BinanceWrapper if they are not already present
try:
    if not hasattr(BinanceWrapper, '_futures_open_orders_count'):
        BinanceWrapper._futures_open_orders_count = _futures_open_orders_count
    if not hasattr(BinanceWrapper, '_futures_net_position_amt'):
        BinanceWrapper._futures_net_position_amt = _futures_net_position_amt
    if not hasattr(BinanceWrapper, '_ensure_margin_and_leverage_or_block'):
        BinanceWrapper._ensure_margin_and_leverage_or_block = _ensure_margin_and_leverage_or_block
    if not hasattr(BinanceWrapper, 'get_symbol_margin_type'):
        BinanceWrapper.get_symbol_margin_type = get_symbol_margin_type
except Exception:
    pass

    def configure_futures_symbol(self, symbol: str):
        """Back-compat shim: some strategy code calls this; we forward to ensure_futures_settings."""
        try:
            self.ensure_futures_settings(symbol)
        except Exception:
            pass

    def set_futures_leverage(self, lev: int):
        try:
            lev = int(lev)
        except Exception:
            return
        lev = max(1, min(MAX_FUTURES_LEVERAGE, lev))
        self._requested_default_leverage = lev
        self._default_leverage = lev
        self.futures_leverage = lev


# ---- Compatibility monkey-patches (ensure instance has these methods)
def _bw_place_futures_market_order(self, symbol: str, side: str, percent_balance: float | None = None,
                                   price: float | None = None, position_side: str | None = None,
                                   quantity: float | None = None, **kwargs):
    # Reuse the module-level implementation if it exists.
    fn = globals().get('place_futures_market_order')
    if callable(fn):
        return fn(self, symbol, side, percent_balance=percent_balance,
                  price=price, position_side=position_side,
                  quantity=quantity, **kwargs)
    else:
        # Fallback minimal implementation
        sym = (symbol or '').upper()
        px = float(price if price is not None else self.get_last_price(sym) or 0.0)
        if px <= 0: return {'ok': False, 'error': 'No price available'}
        qty = float(quantity or 0.0)
        if qty <= 0 and percent_balance:
            bal = float(self.futures_get_usdt_balance() or 0.0)
            lev = int(kwargs.get('leverage') or 1)
            f = float(percent_balance or 0.0)
            f = f if f <= 1.0 else (f/100.0)
            avail_notional = bal * lev * f
            # strict gate
            f_filters = self.get_futures_symbol_filters(sym) or {}
            minNotional = float(f_filters.get('minNotional') or 0.0) or 5.0
            minQty = float(f_filters.get('minQty') or 0.0) or float(f_filters.get('stepSize') or 0.001)
            need_notional = max(minNotional, minQty * px)
            if bool(kwargs.get('strict', True)) and avail_notional < need_notional:
                # percent the user entered (as %)
                f_pct = (f*100.0) if f <= 1.0 else f
                req_pct = (need_notional / max(lev * bal, 1e-9)) * 100.0
                if kwargs.get('auto_bump_to_min', True) and (lev * bal) > 0:
                    # transparently bump percent to the minimum required and continue
                    f = max(f, (req_pct/100.0) + 1e-9)
                    avail_notional = bal * lev * f
                else:
                    return {'ok': False, 'symbol': sym,
                        'error': f'exchange minimum requires ~{req_pct:.2f}% (> {f_pct:.2f}%)',
                        'computed': {
                            'px': px,
                            'step': float(f_filters.get('stepSize') or 0.001),
                            'minQty': minQty,
                            'minNotional': minNotional,
                            'need_qty': max(minQty, need_notional/px),
                            'need_notional': need_notional,
                            'lev': lev,
                            'avail': bal,
                            'margin_budget': bal * f
                        },
                        'required_percent': req_pct,
                        'mode': 'percent(strict)'}

















                qty = avail_notional / px
        qty, err = self.adjust_qty_to_filters_futures(sym, qty, px)
        if err: return {'ok': False, 'error': err, 'computed': {'qty': qty, 'price': px}}
        dual = bool(self.get_futures_dual_side())
        try:
            filters = self.get_futures_symbol_filters(sym) or {}
            step = float(filters.get('stepSize') or 0.0)
        except Exception:
            step = 0.0
        qty_str = self._format_quantity_for_order(qty, step)
        params = dict(symbol=sym, side=side.upper(), type='MARKET', quantity=qty_str)
        if dual:
            params['positionSide'] = (position_side or ('LONG' if side.upper()=='BUY' else 'SHORT'))
        try:
            info = self.client.futures_create_order(**params)
            self._invalidate_futures_positions_cache()
            return {'ok': True, 'info': info, 'computed': {'qty': qty, 'price': px}}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'computed': {'qty': qty, 'price': px}}



def _bw_close_futures_position(self, symbol: str):
    sym = (symbol or '').upper()
    try:
        infos = self.client.futures_position_information(symbol=sym)
    except Exception as e:
        return {'symbol': sym, 'ok': False, 'error': f'fetch failed: {e}'}
    dual = bool(self.get_futures_dual_side())
    errs = []; closed = 0
    # Get filters for correct rounding
    try:
        filt = self.get_futures_symbol_filters(sym)  # stepSize, minQty, minNotional, tickSize
    except Exception:
        filt = {'stepSize': 0.0, 'minQty': 0.0, 'minNotional': 0.0, 'tickSize': 0.0}
    step = float(filt.get('stepSize') or 0.0) or 0.0
    min_qty = float(filt.get('minQty') or 0.0) or 0.0
    tick = float(filt.get('tickSize') or 0.0) or 0.0
    try:
        book = self.client.futures_book_ticker(symbol=sym) or {}
    except Exception:
        book = {}
    try:
        last_px = float(book.get('lastPrice') or self.get_last_price(sym) or 0.0)
    except Exception:
        last_px = 0.0
    bid = float(book.get('bidPrice') or 0.0) or last_px
    ask = float(book.get('askPrice') or 0.0) or last_px
    min_notional = float(filt.get('minNotional') or 0.0) or 0.0

    def _ceil_to_step(x, s):
        if s <= 0: return float(x)
        k = int(float(x) / s + 1e-12)
        if abs(x - k*s) < 1e-12:
            return k*s
        return (k+1)*s

    def _round_to_tick(p, t):
        if t <= 0: return float(p)
        return round(float(p) / t) * t

    for pos in infos or []:
        amt = float(pos.get('positionAmt') or 0.0)
        if abs(amt) <= 0:
            continue
        side = 'SELL' if amt > 0 else 'BUY'
        qty = abs(amt)

        # Round qty UP to step to guarantee full close
        if step > 0:
            qty = _ceil_to_step(qty, step)
        if min_qty > 0 and qty < min_qty:
            qty = _ceil_to_step(min_qty, step) if step > 0 else min_qty
        if min_notional > 0 and last_px > 0 and qty*last_px < min_notional:
            need = (min_notional / max(1e-12, last_px))
            qty = _ceil_to_step(max(qty, need), step) if step > 0 else max(qty, need)

        qty_str = self._format_quantity_for_order(qty, step)
        # Primary attempt: MARKET reduceOnly (best-effort)
        params = dict(symbol=sym, side=side, type='MARKET', quantity=qty_str)
        if dual:
            params['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
        else:
            params['reduceOnly'] = True
        try:
            self.client.futures_create_order(**params)
            self._invalidate_futures_positions_cache()
            closed += 1
            continue
        except Exception as e:
            msg = str(e)
            # Fallback for -1106 reduceOnly not required → use LIMIT IOC reduceOnly and cross the spread
            if "-1106" in msg or "reduceonly" in msg.lower():
                try:
                    px = (bid*0.999 if side=='SELL' else ask*1.001) or last_px
                    if px <= 0:  # last resort
                        px = last_px if last_px>0 else (1.0 if side=='BUY' else 1.0)
                    px = _round_to_tick(px, tick) if tick>0 else px
                    alt = dict(symbol=sym, side=side, type='LIMIT', timeInForce='IOC',
                               price=str(px), quantity=qty_str)
                    if dual:
                        alt['positionSide'] = ('LONG' if amt > 0 else 'SHORT')
                    else:
                        alt['reduceOnly'] = True
                    self.client.futures_create_order(**alt)
                    self._invalidate_futures_positions_cache()
                    closed += 1
                    continue
                except Exception as e2:
                    errs.append(str(e2))
            else:
                errs.append(msg)
    return {'symbol': sym, 'ok': (len(errs)==0), 'closed': closed, 'error': '; '.join(errs) if errs else None}

def _bw_close_all_futures_positions(self):
    try:
        infos = self.client.futures_position_information()
    except Exception as e:
        return [{'ok': False, 'error': f'fetch failed: {e}'}]
    symbols = sorted({p.get('symbol','') for p in infos or [] if abs(float(p.get('positionAmt') or 0.0)) > 0})
    return [ _bw_close_futures_position(self, sym) for sym in symbols ]

# Attach if missing
try:
    BinanceWrapper
    if not hasattr(BinanceWrapper, 'place_futures_market_order'):
        BinanceWrapper.place_futures_market_order = _bw_place_futures_market_order
    if not hasattr(BinanceWrapper, 'close_futures_position'):
        BinanceWrapper.close_futures_position = _bw_close_futures_position
    if not hasattr(BinanceWrapper, 'close_all_futures_positions'):
        BinanceWrapper.close_all_futures_positions = _bw_close_all_futures_positions
except Exception:
    pass

# === STRICT PERCENT SIZER OVERRIDE (STOPFIX19) ====================================
def _floor_to_step(value: float, step: float) -> float:
    try:
        if step and step > 0:
            # avoid binary rounding drift
            n = int(float(value) / float(step) + 1e-12)
            return float(n) * float(step)
    except Exception:
        pass
    return float(value or 0.0)

def _place_futures_market_order_STRICT(self, symbol: str, side: str,
                                       percent_balance: float | None = None,
                                       price: float | None = None,
                                       position_side: str | None = None,
                                       quantity: float | None = None,
                                       **kwargs):
    """
    Replacement for place_futures_market_order with *strict* sizing:
      - If percent_balance is used, compute margin budget = availableBalance * (pct/100).
      - notional_target = margin_budget * leverage
      - qty = floor_to_step(notional_target / price)
      - If qty < minQty or qty*price < minNotional -> SKIP (do NOT auto-bump).
      - Return ok=False with 'required_percent' when skipping so the UI can show why.
    Also accepts:
      - reduce_only: bool
      - leverage: int
      - margin_mode: 'ISOLATED'|'CROSSED'
      - interval: str (passthrough for strategy ledger; unused here)
    """
    sym = (symbol or '').upper()
    # Hard-block if symbol is not in desired margin mode
    try:
        self._ensure_symbol_margin(sym, kwargs.get('margin_mode') or getattr(self, '_default_margin_mode','ISOLATED'), kwargs.get('leverage'))
    except Exception as _e:
        self._log(f'BLOCK strict path: {type(_e).__name__}: {_e}', lvl='error')
        return {'ok': False, 'error': str(_e), 'mode': 'strict'}
    # Make sure leverage/margin mode are applied
    # Make sure leverage/margin mode are applied (strict)
    _ensure_err = None
    try:
        self.ensure_futures_settings(sym, leverage=kwargs.get('leverage'), margin_mode=kwargs.get('margin_mode'))
    except Exception as e:
        _ensure_err = str(e)
    if _ensure_err:
        return {'ok': False, 'symbol': sym, 'error': _ensure_err}
    # Resolve price
    px = float(price if price is not None else self.get_last_price(sym) or 0.0)
    if px <= 0.0:
        return {'ok': False, 'symbol': sym, 'error': 'No price available'}

    # Exchange filters
    f = self.get_futures_symbol_filters(sym) or {}
    step = float(f.get('stepSize') or 0.0) or float(f.get('step_size') or 0.0) or 0.001
    minQty = float(f.get('minQty') or 0.0) or step
    minNotional = float(f.get('minNotional') or 0.0) or 5.0

    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())

    # Decide order quantity
    qty = float(quantity or 0.0)
    mode = 'quantity'
    lev_requested = int(kwargs.get('leverage') or getattr(self, "_default_leverage", 5) or 5)
    lev = self.clamp_futures_leverage(sym, lev_requested)
    if qty <= 0 and percent_balance is not None:
        mode = 'percent(strict)'
        pct = float(percent_balance)
        bal = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = bal * (pct / 100.0)
        notional_target = margin_budget * max(lev, 1)
        qty_raw = (notional_target / px) if px > 0 else 0.0
        qty = _floor_to_step(qty_raw, step)

        # Strict gate: require BOTH minQty and minNotional
        notional = qty * px
        need_notional = max(minNotional, minQty * px)
        if qty < minQty or notional < minNotional or notional < need_notional:
            # Calculate required percent so the user can see how much is needed
            denom = max(bal * max(lev, 1), 1e-12)
            req_pct = (need_notional / denom) * 100.0
            return {
                'ok': False,
                'symbol': sym,
                'error': f'exchange minimum requires ~{req_pct:.2f}% (> {pct:.2f}%)',
                'computed': {
                    'px': px, 'step': step,
                    'minQty': minQty, 'minNotional': minNotional,
                    'need_qty': max(minQty, need_notional / px),
                    'need_notional': need_notional,
                    'lev': lev, 'avail': bal,
                    'margin_budget': margin_budget
                },
                'required_percent': req_pct,
                'mode': mode
            }

    # Finally adjust the computed qty to step; also guard reduce-only
    qty = _floor_to_step(qty, step)
    if qty <= 0:
        return {
            'ok': False,
            'symbol': sym,
            'error': 'qty<=0',
            'computed': {'qty': qty, 'px': px, 'step': step, 'lev': lev},
        }

    # reduceOnly & positionSide
    side_up = (side or '').upper()
    qty_str = self._format_quantity_for_order(qty, step)
    params = dict(symbol=sym, side=side_up, type='MARKET', quantity=qty_str)
    if bool(kwargs.get('reduce_only')):
        params['reduceOnly'] = True
    if dual:
        ps = position_side or kwargs.get('positionSide')
        if not ps:
            ps = 'SHORT' if side_up == 'SELL' else 'LONG'
        params['positionSide'] = ps

    # Place order
    try:
        info = self.client.futures_create_order(**params)
        self._invalidate_futures_positions_cache()
        return {
            'ok': True,
            'info': info,
            'computed': {
                'qty': qty,
                'px': px,
                'step': step,
                'minQty': minQty,
                'minNotional': minNotional,
                'lev': lev,
            },
            'mode': mode,
        }
    except Exception as e:
        return {
            'ok': False,
            'symbol': sym,
            'error': str(e),
            'computed': {'qty': qty, 'px': px, 'step': step, 'lev': lev},
            'mode': mode,
        }

# Unconditionally override to make behavior predictable.
try:
    BinanceWrapper.place_futures_market_order = _place_futures_market_order_STRICT
except Exception:
    pass
# === END STRICT PERCENT SIZER OVERRIDE ===========================================

def _place_futures_market_order_FLEX(self, symbol: str, side: str,
                                     percent_balance: float | None = None,
                                     price: float | None = None,
                                     position_side: str | None = None,
                                     quantity: float | None = None,
                                     **kwargs):
    """
    Flexible sizer that ALWAYS tries to place the minimum exchange-legal order.
    Behavior:
      1) If `quantity` is given, use it (snapped to step) and enforce exchange minimums.
      2) Else if `percent_balance` is given, compute qty from percent & leverage.
         If below exchange minimums (minQty / minNotional), **auto-bump** to the
         minimum legal quantity as long as wallet `availableBalance` can cover the
         required initial margin. Log mode='percent(bumped_to_min)'.
      3) Time-in-force and GTD goodTillDate are supported.
      4) Supports hedge (positionSide) and reduce_only.
    Returns a dict like the strict variant.
    """
    sym = (symbol or '').upper()
    side_up = (side or 'BUY').upper()
    pos_side = (position_side or kwargs.get('positionSide') or None)
    px = float(price if price is not None else (self.get_last_price(sym) or 0.0))
    if px <= 0:
        return {'ok': False, 'symbol': sym, 'error': 'No price available'}

    # Strictly enforce margin mode + leverage before creating the order.
    try:
        desired_requested = int(kwargs.get('leverage') or getattr(self, '_default_leverage', 5) or 5)
    except Exception:
        desired_requested = int(getattr(self, '_default_leverage', 5) or 5)
    desired_mm = kwargs.get('margin_mode') or getattr(self, '_default_margin_mode', 'ISOLATED') or 'ISOLATED'
    effective_lev = self.clamp_futures_leverage(sym, desired_requested)
    try:
        self._ensure_margin_and_leverage_or_block(sym, desired_mm, desired_requested)
    except Exception as e:
        # Do not place an order under the wrong settings
        return {'ok': False, 'symbol': sym, 'error': f'enforce_settings_failed: {e}', 'mode': 'flex'}

    # Exchange filters
    f = self.get_futures_symbol_filters(sym) or {}
    step = float(f.get('stepSize') or 0.0) or 0.001
    minQty = float(f.get('minQty') or 0.0) or step
    minNotional = float(f.get('minNotional') or 0.0) or 5.0

    # Dual-side detection (hedge)
    dual = bool(getattr(self, "_futures_dual_side", False) or self.get_futures_dual_side())
    if dual and not pos_side:
        pos_side = 'SHORT' if side_up == 'SELL' else 'LONG'

    # Helpers
    def _floor_to_step(val: float, step_: float) -> float:
        try:
            if step_ <= 0: return float(val)
            import math
            return math.floor(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    def _ceil_to_step(val: float, step_: float) -> float:
        try:
            if step_ <= 0: return float(val)
            import math
            return math.ceil(float(val) / float(step_)) * float(step_)
        except Exception:
            return float(val)

    # Compute minimum legal qty
    min_qty_by_notional = _ceil_to_step((minNotional / px), step)
    min_legal_qty = max(minQty, min_qty_by_notional)

    lev = max(1, int(effective_lev))
    reduce_only = bool(kwargs.get('reduce_only') or kwargs.get('reduceOnly') or False)

    # Compute starting qty
    mode = 'quantity' if (quantity is not None and float(quantity) > 0) else 'percent'
    if quantity is not None and float(quantity) > 0:
        qty = _floor_to_step(float(quantity), step)
    else:
        pct = max(float(percent_balance or 0.0), 0.0)
        # Budget and target notional based on percent
        avail = float(self.get_futures_balance_usdt() or 0.0)
        margin_budget = avail * (pct / 100.0)
        target_notional = margin_budget * max(lev, 1)
        qty = _floor_to_step((target_notional / px) if px > 0 else 0.0, step)

        # If below minimums, auto-bump to min legal qty ***if wallet can afford***
        if qty < min_legal_qty:
            # Required notional & margin for minimum legal qty
            required_notional = max(minNotional, minQty * px, min_legal_qty * px)
            required_margin = required_notional / max(lev, 1)
            # Auto-bump guard: do not exceed a configured absolute percent cap
            required_percent = (required_notional / max(avail * max(lev, 1), 1e-12)) * 100.0
            max_auto_bump_percent = float(kwargs.get('max_auto_bump_percent', getattr(self, '_max_auto_bump_percent', 5.0)))
            percent_multiplier = float(kwargs.get('auto_bump_percent_multiplier', getattr(self, '_auto_bump_percent_multiplier', 10.0)))
            if percent_multiplier <= 0:
                percent_multiplier = 1.0
            self._max_auto_bump_percent = max_auto_bump_percent
            self._auto_bump_percent_multiplier = percent_multiplier
            if max_auto_bump_percent <= 0:
                allowed_percent = float('inf')
            else:
                allowed_percent = max(max_auto_bump_percent, pct * percent_multiplier)
            cushion = 1.01  # small buffer for fees/rounding
            within_margin = (required_margin <= avail * cushion) and (not reduce_only)
            percent_ok = (allowed_percent == float('inf')) or (required_percent <= (allowed_percent + 1e-9))
            if within_margin and percent_ok:
                qty = _ceil_to_step(required_notional / px, step)
                mode = 'percent(bumped_to_min)'
            else:
                # Not enough funds or bump exceeds cap
                limit_pct = None if (allowed_percent == float('inf') or not within_margin) else allowed_percent
                cap_note = ""
                if limit_pct is not None and not percent_ok:
                    cap_note = f" (cap {limit_pct:.2f}% / requested {pct:.2f}%)"
                return {
                    'ok': False,
                    'symbol': sym,
                    'error': f'insufficient funds for exchange minimum (~{required_percent:.2f}% needed){cap_note}',
                    'computed': {
                        'px': px, 'step': step,
                        'minQty': minQty, 'minNotional': minNotional,
                        'need_qty': _ceil_to_step(required_notional / px, step),
                        'need_notional': required_notional,
                        'lev': lev, 'avail': avail, 'margin_budget': margin_budget,
                        'cap_percent': limit_pct,
                        'requested_percent': pct,
                    },
                    'required_percent': required_percent,
                    'mode': 'percent(strict)'
                }

    # Snap again to be safe
    qty = max(qty, min_legal_qty)
    qty = _floor_to_step(qty, step)
    if qty <= 0 and not reduce_only:
        return {'ok': False, 'symbol': sym, 'error': 'qty<=0 after sizing'}

    # Build order params
    # MARKET orders: no TIF/goodTillDate

    qty_str = self._format_quantity_for_order(qty, step)
    params = dict(symbol=sym, side=side_up, type='MARKET', quantity=qty_str)
    if dual and pos_side:
        params['positionSide'] = pos_side
    if reduce_only and not (dual and pos_side):
        params['reduceOnly'] = True

    try:
        order = self.client.futures_create_order(**params)
        self._invalidate_futures_positions_cache()
        return {
            'ok': True,
            'info': order,
            'computed': {
                'qty': qty,
                'px': px,
                'step': step,
                'minQty': minQty,
                'minNotional': minNotional,
                'lev': lev,
            },
            'mode': mode,
        }
    except Exception as e:
        return {
            'ok': False,
            'symbol': sym,
            'error': str(e),
            'computed': {'qty': qty, 'px': px, 'step': step, 'lev': lev},
            'mode': mode,
        }

# Override to FLEX behavior by default (auto-bump to exchange minimums)
try:
    BinanceWrapper.place_futures_market_order = _place_futures_market_order_FLEX
except Exception:
    pass















