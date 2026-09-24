"""Narrow read-only Binance Spot USER_DATA transport for recovery tooling.

This transport exposes only signed GET requests for account identity and one
existing order lookup. It has no order placement, cancellation, or endpoint
override surface.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from urllib.parse import urlencode

import requests

from app.settings.live_safety import LiveTradingSafetyError


_SPOT_API_BASE = "https://api.binance.com/api"
_SIGNED_PATHS = {"/v3/account", "/v3/order"}
_REQUEST_TIMEOUT = (3, 8)


class SpotUserDataTransport:
    """HMAC signed GET-only access to the fixed Binance Spot REST host."""

    def __init__(self, api_key: str | None, api_secret: str | None) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise LiveTradingSafetyError("Spot reconciliation requires an API key from its environment variable.")
        if not isinstance(api_secret, str) or not api_secret.strip():
            raise LiveTradingSafetyError("Spot reconciliation requires an API secret from its environment variable.")
        self._api_key = api_key.strip()
        self._api_secret = api_secret.strip()

    def _signed_get(self, path: str, params: Mapping[str, str] | None = None) -> dict[str, object]:
        if path not in _SIGNED_PATHS:
            raise LiveTradingSafetyError("Spot reconciliation requested an unsupported read-only endpoint.")
        if (path == "/v3/account" and params) or (
            path == "/v3/order" and set(params or {}) != {"symbol", "origClientOrderId"}
        ):
            raise LiveTradingSafetyError("Spot reconciliation requested invalid read-only query parameters.")
        payload: dict[str, str | int] = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = 5000
        query = urlencode(payload)
        signature = hmac.new(self._api_secret.encode("utf-8"), query.encode("ascii"), hashlib.sha256).hexdigest()
        try:
            response = requests.get(
                f"{_SPOT_API_BASE}{path}",
                params={**payload, "signature": signature},
                headers={"X-MBX-APIKEY": self._api_key},
                timeout=_REQUEST_TIMEOUT,
            )
        except Exception:
            # Request exceptions may include the signed query URL. Never echo
            # them into the operator console or persistent intent ledger.
            raise LiveTradingSafetyError("Binance Spot USER_DATA request failed.") from None
        status_code = getattr(response, "status_code", None)
        if type(status_code) is not int or status_code != 200:
            suffix = f" (HTTP {status_code})" if type(status_code) is int else ""
            raise LiveTradingSafetyError(f"Binance Spot USER_DATA request failed{suffix}.")
        try:
            body = response.json()
        except Exception:
            raise LiveTradingSafetyError("Binance Spot USER_DATA response was not valid JSON.") from None
        if not isinstance(body, Mapping):
            raise LiveTradingSafetyError("Binance Spot USER_DATA response was not an object.")
        return dict(body)

    def get_account_uid(self) -> int:
        response = self._signed_get("/v3/account")
        uid = response.get("uid")
        if (
            "code" in response
            or response.get("accountType") != "SPOT"
            or type(uid) is not int
            or uid <= 0
        ):
            raise LiveTradingSafetyError("Signed Binance Spot account identity is missing or invalid.")
        return uid

    def get_order(self, *, symbol: str, origClientOrderId: str) -> dict[str, object]:
        if (
            not isinstance(symbol, str)
            or not symbol
            or not symbol.isascii()
            or not symbol.isalnum()
            or symbol != symbol.upper()
            or not isinstance(origClientOrderId, str)
            or not origClientOrderId
            or len(origClientOrderId) > 36
            or not origClientOrderId.isascii()
            or any(not (character.isalnum() or character in "._:/-") for character in origClientOrderId)
        ):
            raise LiveTradingSafetyError("Spot order reconciliation requires a valid symbol and client order ID.")
        return self._signed_get(
            "/v3/order",
            {"symbol": symbol, "origClientOrderId": origClientOrderId},
        )
