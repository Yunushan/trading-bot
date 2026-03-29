from __future__ import annotations

from enum import Enum
from typing import Any

import requests

_USDS_REST_PROD = None
_USDS_REST_TESTNET = None
_UsdsRestAPI = None
_UsdsConfig = None
_UsdsEnums = None
_UsdsMarginTypeEnum = None
_UsdsOrderSideEnum = None
_UsdsPositionSideEnum = None
_UsdsTimeInForceEnum = None
_UsdsWorkingTypeEnum = None
_UsdsOrderRespEnum = None
_UsdsPriceMatchEnum = None
_UsdsStpEnum = None
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
    try:
        from binance_sdk_derivatives_trading_usds_futures.rest_api.models import enums as _UsdsEnums
    except Exception:
        _UsdsEnums = None
    if _UsdsEnums is not None:
        _UsdsMarginTypeEnum = getattr(_UsdsEnums, "ChangeMarginTypeMarginTypeEnum", None)
        _UsdsOrderSideEnum = getattr(_UsdsEnums, "NewOrderSideEnum", None)
        _UsdsPositionSideEnum = getattr(_UsdsEnums, "NewOrderPositionSideEnum", None)
        _UsdsTimeInForceEnum = getattr(_UsdsEnums, "NewOrderTimeInForceEnum", None)
        _UsdsWorkingTypeEnum = getattr(_UsdsEnums, "NewOrderWorkingTypeEnum", None)
        _UsdsOrderRespEnum = getattr(_UsdsEnums, "NewOrderNewOrderRespTypeEnum", None)
        _UsdsPriceMatchEnum = getattr(_UsdsEnums, "NewOrderPriceMatchEnum", None)
        _UsdsStpEnum = getattr(_UsdsEnums, "NewOrderSelfTradePreventionModeEnum", None)
except Exception:
    pass

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


class _SDKBaseClient:
    def __init__(self, api_key: str | None):
        self.API_KEY = api_key or ""
        self._bw_throttled = True
        self._bw_throttle = None

    def _call(self, func, **kwargs):
        clean_kwargs = {key: val for key, val in kwargs.items() if val is not None}
        response = func(**clean_kwargs)
        return _sdk_to_plain(response)

    def _http_get(self, url: str, params: dict[str, Any] | None = None, timeout: float = 10.0):
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
