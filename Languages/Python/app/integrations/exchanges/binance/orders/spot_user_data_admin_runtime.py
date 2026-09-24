"""Narrow read-only Binance Spot USER_DATA transport for recovery tooling.

This transport exposes only signed GET requests for account identity, account
balances, account-wide open orders, and one existing order lookup. It has no
order placement, cancellation, or endpoint override surface.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import requests

from app.settings.live_safety import LiveTradingSafetyError


_SPOT_API_BASE = "https://api.binance.com/api"
_SIGNED_PATHS = {"/v3/account", "/v3/order", "/v3/openOrders"}
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

    def _signed_get(
        self, path: str, params: Mapping[str, str] | None = None,
    ) -> dict[str, object] | list[object]:
        if path not in _SIGNED_PATHS:
            raise LiveTradingSafetyError("Spot reconciliation requested an unsupported read-only endpoint.")
        if (path == "/v3/account" and params) or (
            path == "/v3/order" and set(params or {}) != {"symbol", "origClientOrderId"}
        ) or (path == "/v3/openOrders" and params):
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
        if isinstance(body, Mapping):
            return dict(body)
        if isinstance(body, list):
            return body
        raise LiveTradingSafetyError("Binance Spot USER_DATA response had an invalid JSON shape.")

    @staticmethod
    def _account_object(response: object) -> dict[str, object]:
        if not isinstance(response, dict):
            raise LiveTradingSafetyError("Signed Binance Spot account identity is missing or invalid.")
        uid = response.get("uid")
        if (
            "code" in response
            or response.get("accountType") != "SPOT"
            or type(uid) is not int
            or uid <= 0
        ):
            raise LiveTradingSafetyError("Signed Binance Spot account identity is missing or invalid.")
        return response

    def get_account_uid(self) -> int:
        return int(self._account_object(self._signed_get("/v3/account"))["uid"])

    def get_account_overview(self) -> dict[str, int]:
        """Validate account balances, returning counts only (never amounts/assets)."""
        response = self._account_object(self._signed_get("/v3/account"))
        balances = response.get("balances")
        if not isinstance(balances, list) or len(balances) > 100_000:
            raise LiveTradingSafetyError("Binance Spot account balances are missing or invalid.")
        seen_assets: set[str] = set()
        nonzero_assets = 0
        locked_assets = 0
        for balance in balances:
            if not isinstance(balance, Mapping):
                raise LiveTradingSafetyError("Binance Spot account balances are malformed.")
            asset = balance.get("asset")
            if (
                not isinstance(asset, str)
                or not asset
                or not asset.isascii()
                or not asset.isalnum()
                or asset != asset.upper()
                or asset in seen_assets
            ):
                raise LiveTradingSafetyError("Binance Spot account balances contain an invalid asset identity.")
            seen_assets.add(asset)
            values: list[Decimal] = []
            for field in ("free", "locked"):
                raw = balance.get(field)
                if not isinstance(raw, str):
                    raise LiveTradingSafetyError("Binance Spot account balances contain an invalid amount.")
                try:
                    amount = Decimal(raw)
                except InvalidOperation:
                    raise LiveTradingSafetyError("Binance Spot account balances contain an invalid amount.") from None
                if not amount.is_finite() or amount < 0:
                    raise LiveTradingSafetyError("Binance Spot account balances contain an invalid amount.")
                values.append(amount)
            if values[0] > 0 or values[1] > 0:
                nonzero_assets += 1
            if values[1] > 0:
                locked_assets += 1
        return {
            "account_uid": int(response["uid"]),
            "balance_asset_count": len(seen_assets),
            "nonzero_balance_asset_count": nonzero_assets,
            "locked_balance_asset_count": locked_assets,
        }

    def get_open_orders(self) -> list[dict[str, object]]:
        """Read all Spot open orders; callers must not treat this as exchange-side fencing."""
        response = self._signed_get("/v3/openOrders")
        if not isinstance(response, list) or len(response) > 10_000:
            raise LiveTradingSafetyError("Binance Spot open orders response is missing or too large.")
        if any(not isinstance(order, Mapping) for order in response):
            raise LiveTradingSafetyError("Binance Spot open orders response is malformed.")
        return [dict(order) for order in response if isinstance(order, Mapping)]

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
        response = self._signed_get(
            "/v3/order",
            {"symbol": symbol, "origClientOrderId": origClientOrderId},
        )
        if not isinstance(response, dict):
            raise LiveTradingSafetyError("Binance Spot order response was not an object.")
        return response
