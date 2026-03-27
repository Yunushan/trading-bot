"""Client adapter helpers for the Binance integration."""

from .connector_clients import (
    DEFAULT_CONNECTOR_BACKEND,
    CcxtBinanceAdapter,
    CcxtConnectorError,
    OfficialConnectorAdapter,
    OfficialConnectorError,
    _normalize_connector_choice,
)
from .sdk_clients import (
    BinanceSDKCoinFuturesClient,
    BinanceSDKSpotClient,
    BinanceSDKUsdsFuturesClient,
)

__all__ = [
    "DEFAULT_CONNECTOR_BACKEND",
    "CcxtBinanceAdapter",
    "CcxtConnectorError",
    "OfficialConnectorAdapter",
    "OfficialConnectorError",
    "BinanceSDKCoinFuturesClient",
    "BinanceSDKSpotClient",
    "BinanceSDKUsdsFuturesClient",
    "_normalize_connector_choice",
]
