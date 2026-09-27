"""Known error types returned by Spot exchange and local recovery boundaries."""

from __future__ import annotations

from decimal import InvalidOperation

from requests import RequestException

from app.settings.live_safety import LiveTradingSafetyError

from ..clients.connector_clients import CcxtConnectorError, OfficialConnectorError

try:
    import binance_common.errors as _binance_sdk_errors
except ImportError:
    _binance_sdk_errors = None

_SDK_ERROR_NAMES = (
    "BadRequestError",
    "ClientError",
    "ForbiddenError",
    "NetworkError",
    "NotFoundError",
    "RateLimitBanError",
    "RequiredError",
    "ServerError",
    "TooManyRequestsError",
    "UnauthorizedError",
)
_SDK_SPOT_ERRORS = tuple(
    error_type
    for name in _SDK_ERROR_NAMES
    if _binance_sdk_errors is not None
    and isinstance((error_type := getattr(_binance_sdk_errors, name, None)), type)
    and issubclass(error_type, Exception)
)

# Exchange calls can fail after Binance accepted the request. These known
# transport, adapter, protocol and validation failures must leave the intent
# unresolved for exact reconciliation.
SPOT_EXCHANGE_ERRORS = (
    LiveTradingSafetyError,
    RequestException,
    OfficialConnectorError,
    CcxtConnectorError,
    OSError,
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    InvalidOperation,
    *_SDK_SPOT_ERRORS,
)

SPOT_LOCAL_STATE_ERRORS = (
    LiveTradingSafetyError,
    OSError,
    ValueError,
    TypeError,
    KeyError,
    InvalidOperation,
)
