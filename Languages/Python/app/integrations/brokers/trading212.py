from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import requests

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload
from ._order_validation import merge_extra_order_fields
from ._transport_validation import clean_http_base_url


_ENVIRONMENT_BASE_URLS = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0",
}
_ENVIRONMENT_ALIASES = {
    "demo": "demo",
    "paper": "demo",
    "paper-trading": "demo",
    "practice": "demo",
    "live": "live",
    "real": "live",
}
_ORDER_PATHS = {
    "market": "/equity/orders/market",
    "limit": "/equity/orders/limit",
    "stop": "/equity/orders/stop",
    "stop_limit": "/equity/orders/stop_limit",
}
_TIME_VALIDITIES = {"DAY", "GOOD_TILL_CANCEL"}
_PROTECTED_ORDER_FIELDS = frozenset({"extendedHours", "limitPrice", "quantity", "stopPrice", "ticker", "timeValidity"})


def _normalize_environment(value: object) -> str:
    key = str(value or "demo").strip().lower().replace("_", "-")
    environment = _ENVIRONMENT_ALIASES.get(key)
    if environment is None:
        raise ValueError("Trading 212 environment must be 'demo' or 'live'")
    return environment


def _positive_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field} must be a positive number")
    return parsed


def _normalize_side(value: object) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("Trading 212 side must be 'buy' or 'sell'")
    return side


def _normalize_order_type(value: object) -> str:
    order_type = str(value or "market").strip().lower().replace("-", "_")
    if order_type not in _ORDER_PATHS:
        choices = ", ".join(sorted(_ORDER_PATHS))
        raise ValueError(f"Trading 212 order_type must be one of: {choices}")
    return order_type


def _normalize_time_validity(value: object) -> str:
    validity = str(value or "DAY").strip().upper().replace("-", "_")
    if validity not in _TIME_VALIDITIES:
        raise ValueError("Trading 212 time_validity must be 'DAY' or 'GOOD_TILL_CANCEL'")
    return validity


def _response_json(response: object, *, operation: str) -> dict[str, object] | list[object] | None:
    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except ValueError as exc:
        if status_code < 400 and not getattr(response, "content", b""):
            payload = None
        else:
            raise RuntimeError(f"Trading 212 {operation} response was not JSON: {exc}") from exc
    if payload is not None and not isinstance(payload, (dict, list)):
        raise RuntimeError(f"Trading 212 {operation} response must be a JSON object or array")
    if not 200 <= status_code < 300:
        raise RuntimeError(f"Trading 212 {operation} failed with HTTP {status_code}: {redact_value(payload)}")
    return payload


class Trading212BrokerConnector:
    """Trading 212 Public API client for its Invest/Stocks ISA equity scope.

    Trading 212 does not expose CFD or forex account routing through this public API.
    The connector deliberately reports that limitation while implementing the API's
    documented account, instrument, position, order, and cancellation operations.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        environment: str = "demo",
        base_url: str = "",
        timeout: float = 15.0,
        allow_insecure_remote: bool = False,
        session: Any | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.api_secret = str(api_secret or "").strip()
        self.environment = _normalize_environment(environment)
        self.allow_insecure_remote = bool(allow_insecure_remote)
        self.base_url = clean_http_base_url(
            base_url,
            default=_ENVIRONMENT_BASE_URLS[self.environment],
            field_name="Trading 212 base_url",
            allow_insecure_remote=self.allow_insecure_remote,
        )
        self.timeout = _positive_float(timeout, field="timeout")
        self.session = session or requests.Session()

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "trading212-public-api",
                "selected_forex_broker": "Trading 212",
            }
        )

    def _auth(self) -> tuple[str, str]:
        return (self.api_key, self.api_secret)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _path(self, suffix: str) -> str:
        return f"{self.base_url}/{str(suffix or '').lstrip('/')}"

    def _require_credentials(self) -> None:
        if not self.api_key:
            raise RuntimeError("Trading 212 request requires api_key")
        if not self.api_secret:
            raise RuntimeError("Trading 212 request requires api_secret")

    def _get(self, suffix: str, *, operation: str) -> dict[str, object] | list[object] | None:
        self._require_credentials()
        response = self.session.get(
            self._path(suffix),
            auth=self._auth(),
            headers=self._headers(),
            timeout=self.timeout,
            allow_redirects=False,
        )
        return _response_json(response, operation=operation)

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_broker": "Trading 212",
                "selected_forex_broker": "Trading 212",
                "connector_backend": "trading212-public-api",
                "environment": self.environment,
                "base_url": self.base_url,
                "insecure_remote_transport_allowed": self.allow_insecure_remote,
                "api_key_present": bool(self.api_key),
                "api_secret_present": bool(self.api_secret),
                "provider_api_status": "beta",
                "provider_api_scope": "invest-and-stocks-isa-equities",
                "forex_order_routing_supported": False,
                "supported_order_types": list(_ORDER_PATHS),
                "support": self.support_payload(),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        payload = self._get("/equity/account/summary", operation="account summary")
        if not isinstance(payload, dict):
            raise RuntimeError("Trading 212 account summary response must be a JSON object")
        return redact_value({**self.build_capability_snapshot(), "account": payload})

    def fetch_instruments_snapshot(self) -> dict[str, object]:
        payload = self._get("/equity/metadata/instruments", operation="instrument metadata")
        if not isinstance(payload, list):
            raise RuntimeError("Trading 212 instrument metadata response must be a JSON array")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "instrument_count": len(payload),
                "instruments": payload,
            }
        )

    def fetch_exchanges_snapshot(self) -> dict[str, object]:
        payload = self._get("/equity/metadata/exchanges", operation="exchange metadata")
        if not isinstance(payload, list):
            raise RuntimeError("Trading 212 exchange metadata response must be a JSON array")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "exchange_count": len(payload),
                "exchanges": payload,
            }
        )

    def fetch_positions_snapshot(self) -> dict[str, object]:
        payload = self._get("/equity/positions", operation="positions")
        if not isinstance(payload, list):
            raise RuntimeError("Trading 212 positions response must be a JSON array")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "position_count": len(payload),
                "positions": payload,
            }
        )

    def fetch_pending_orders_snapshot(self) -> dict[str, object]:
        payload = self._get("/equity/orders", operation="pending orders")
        if not isinstance(payload, list):
            raise RuntimeError("Trading 212 pending orders response must be a JSON array")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "order_count": len(payload),
                "orders": payload,
            }
        )

    def fetch_order_snapshot(self, order_id: int) -> dict[str, object]:
        clean_order_id = int(order_id)
        if clean_order_id <= 0:
            raise ValueError("Trading 212 order_id must be positive")
        payload = self._get(f"/equity/orders/{clean_order_id}", operation="pending order")
        if not isinstance(payload, dict):
            raise RuntimeError("Trading 212 pending order response must be a JSON object")
        return redact_value({**self.build_capability_snapshot(), "order": payload})

    def submit_order(
        self,
        *,
        ticker: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_validity: str = "DAY",
        extended_hours: bool = False,
        dry_run: bool = True,
        allow_live: bool = False,
        extra_order_fields: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        clean_ticker = str(ticker or "").strip()
        if not clean_ticker:
            raise ValueError("Trading 212 ticker is required")
        clean_side = _normalize_side(side)
        clean_quantity = _positive_float(quantity, field="quantity")
        clean_order_type = _normalize_order_type(order_type)
        request: dict[str, object] = {
            "ticker": clean_ticker,
            "quantity": clean_quantity if clean_side == "buy" else -clean_quantity,
        }
        if clean_order_type == "market":
            request["extendedHours"] = bool(extended_hours)
        else:
            request["timeValidity"] = _normalize_time_validity(time_validity)
        if clean_order_type in {"limit", "stop_limit"}:
            if limit_price is None:
                raise ValueError(f"limit_price is required for Trading 212 {clean_order_type} orders")
            request["limitPrice"] = _positive_float(limit_price, field="limit_price")
        if clean_order_type in {"stop", "stop_limit"}:
            if stop_price is None:
                raise ValueError(f"stop_price is required for Trading 212 {clean_order_type} orders")
            request["stopPrice"] = _positive_float(stop_price, field="stop_price")
        merge_extra_order_fields(
            request,
            extra_order_fields,
            protected_fields=_PROTECTED_ORDER_FIELDS,
            provider="Trading 212",
        )

        snapshot = {
            **self.build_capability_snapshot(),
            "request": request,
            "order_type": clean_order_type,
            "provider_request_idempotent": False,
        }
        if dry_run:
            return redact_value({**snapshot, "status": "dry_run", "order": None})
        if not allow_live:
            raise RuntimeError("Trading 212 order submission requires allow_live=True")
        self._require_credentials()
        response = self.session.post(
            self._path(_ORDER_PATHS[clean_order_type]),
            auth=self._auth(),
            headers=self._headers(),
            json=request,
            timeout=self.timeout,
            allow_redirects=False,
        )
        payload = _response_json(response, operation=f"{clean_order_type} order")
        if not isinstance(payload, dict):
            raise RuntimeError("Trading 212 order response must be a JSON object")
        return redact_value({**snapshot, "status": "submitted", "order": payload})

    def submit_market_order(self, **kwargs: object) -> dict[str, object]:
        return self.submit_order(order_type="market", **kwargs)

    def submit_limit_order(self, **kwargs: object) -> dict[str, object]:
        return self.submit_order(order_type="limit", **kwargs)

    def submit_stop_order(self, **kwargs: object) -> dict[str, object]:
        return self.submit_order(order_type="stop", **kwargs)

    def submit_stop_limit_order(self, **kwargs: object) -> dict[str, object]:
        return self.submit_order(order_type="stop_limit", **kwargs)

    def cancel_order(
        self,
        order_id: int,
        *,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        clean_order_id = int(order_id)
        if clean_order_id <= 0:
            raise ValueError("Trading 212 order_id must be positive")
        request = {"order_id": clean_order_id}
        snapshot = {**self.build_capability_snapshot(), "request": request}
        if dry_run:
            return redact_value({**snapshot, "status": "dry_run", "cancelled": False})
        if not allow_live:
            raise RuntimeError("Trading 212 order cancellation requires allow_live=True")
        self._require_credentials()
        response = self.session.delete(
            self._path(f"/equity/orders/{clean_order_id}"),
            auth=self._auth(),
            headers=self._headers(),
            timeout=self.timeout,
            allow_redirects=False,
        )
        payload = _response_json(response, operation="order cancellation")
        return redact_value(
            {
                **snapshot,
                "status": "submitted",
                "cancelled": True,
                "response": payload,
            }
        )


__all__ = ["Trading212BrokerConnector"]
