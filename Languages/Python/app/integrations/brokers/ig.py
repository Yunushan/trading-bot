from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import requests

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload
from ._order_validation import merge_extra_order_fields
from ._transport_validation import clean_http_base_url


_PROTECTED_ORDER_FIELDS = frozenset(
    {
        "currencyCode",
        "dealReference",
        "direction",
        "epic",
        "expiry",
        "forceOpen",
        "guaranteedStop",
        "orderType",
        "size",
        "timeInForce",
        "trailingStop",
    }
)


_DEFAULT_BASE_URL = "https://demo-api.ig.com/gateway/deal"


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


def _normalize_direction(value: object) -> str:
    direction = str(value or "").strip().upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("IG direction must be 'BUY' or 'SELL'")
    return direction


def _response_json(response: object) -> dict[str, object]:
    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"IG response was not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("IG response must be a JSON object")
    if not 200 <= status_code < 300:
        raise RuntimeError(f"IG request failed with HTTP {status_code}: {redact_value(payload)}")
    return payload


class IgBrokerConnector:
    """IG REST Trading API connector for account diagnostics and guarded OTC orders."""

    def __init__(
        self,
        *,
        api_key: str = "",
        cst: str = "",
        security_token: str = "",
        account_id: str = "",
        base_url: str = _DEFAULT_BASE_URL,
        allow_insecure_remote: bool = False,
        session: Any | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.cst = str(cst or "").strip()
        self.security_token = str(security_token or "").strip()
        self.account_id = str(account_id or "").strip()
        self.allow_insecure_remote = bool(allow_insecure_remote)
        self.base_url = clean_http_base_url(
            base_url,
            default=_DEFAULT_BASE_URL,
            field_name="IG base_url",
            allow_insecure_remote=self.allow_insecure_remote,
        )
        self.session = session or requests.Session()

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "ig-rest",
                "selected_forex_broker": "IG",
            }
        )

    def _headers(self, *, version: str = "2") -> dict[str, str]:
        headers = {
            "Accept": "application/json; charset=UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
            "Version": version,
        }
        if self.api_key:
            headers["X-IG-API-KEY"] = self.api_key
        if self.cst:
            headers["CST"] = self.cst
        if self.security_token:
            headers["X-SECURITY-TOKEN"] = self.security_token
        if self.account_id:
            headers["IG-ACCOUNT-ID"] = self.account_id
        return headers

    def _path(self, suffix: str) -> str:
        return f"{self.base_url}{suffix}"

    def _require_live_credentials(self) -> None:
        if not self.api_key:
            raise RuntimeError("IG live request requires api_key")
        if not self.cst:
            raise RuntimeError("IG live request requires CST token")
        if not self.security_token:
            raise RuntimeError("IG live request requires X-SECURITY-TOKEN")

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_forex_broker": "IG",
                "connector_backend": "ig-rest",
                "base_url": self.base_url,
                "insecure_remote_transport_allowed": self.allow_insecure_remote,
                "account_id_present": bool(self.account_id),
                "api_key_present": bool(self.api_key),
                "cst_present": bool(self.cst),
                "security_token_present": bool(self.security_token),
                "support": self.support_payload(),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        self._require_live_credentials()
        response = self.session.get(
            self._path("/accounts"),
            headers=self._headers(version="1"),
            timeout=15,
            allow_redirects=False,
        )
        payload = _response_json(response)
        return redact_value({**self.build_capability_snapshot(), "accounts": payload.get("accounts", payload)})

    def fetch_market_snapshot(self, epic: str) -> dict[str, object]:
        self._require_live_credentials()
        clean_epic = str(epic or "").strip()
        if not clean_epic:
            raise ValueError("epic is required")
        response = self.session.get(
            self._path(f"/markets/{quote(clean_epic, safe='')}"),
            headers=self._headers(version="3"),
            timeout=15,
            allow_redirects=False,
        )
        payload = _response_json(response)
        return redact_value({**self.build_capability_snapshot(), "market": payload})

    def submit_market_order(
        self,
        *,
        epic: str,
        direction: str,
        size: float,
        currency_code: str = "USD",
        expiry: str = "-",
        force_open: bool = True,
        deal_reference: str = "",
        dry_run: bool = True,
        allow_live: bool = False,
        extra_order_fields: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        clean_epic = str(epic or "").strip()
        if not clean_epic:
            raise ValueError("epic is required")
        clean_currency = str(currency_code or "").strip().upper()
        if len(clean_currency) != 3:
            raise ValueError("currency_code must be a 3-letter code")
        clean_size = _positive_float(size, field="size")
        request: dict[str, object] = {
            "currencyCode": clean_currency,
            "direction": _normalize_direction(direction),
            "epic": clean_epic,
            "expiry": str(expiry or "-").strip() or "-",
            "forceOpen": bool(force_open),
            "guaranteedStop": False,
            "orderType": "MARKET",
            "size": clean_size,
            "timeInForce": "FILL_OR_KILL",
            "trailingStop": False,
        }
        if deal_reference:
            request["dealReference"] = str(deal_reference).strip()
        merge_extra_order_fields(
            request,
            extra_order_fields,
            protected_fields=_PROTECTED_ORDER_FIELDS,
            provider="IG",
        )
        if dry_run:
            return redact_value(
                {
                    **self.build_capability_snapshot(),
                    "status": "dry_run",
                    "request": request,
                    "order": None,
                }
            )
        if not allow_live:
            raise RuntimeError("live IG order submission requires allow_live=True")
        self._require_live_credentials()
        response = self.session.post(
            self._path("/positions/otc"),
            headers=self._headers(version="2"),
            json=request,
            timeout=15,
            allow_redirects=False,
        )
        payload = _response_json(response)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "request": request,
                "order": payload,
            }
        )


__all__ = ["IgBrokerConnector"]
