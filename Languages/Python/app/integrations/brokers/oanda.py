from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload


def _clean_base_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    return text or "https://api-fxpractice.oanda.com"


def _positive_float(value: object, *, field: str) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive number")
    return parsed


def _normalize_side(value: object) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("order side must be 'buy' or 'sell'")
    return side


def _response_json(response: object) -> dict[str, object]:
    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"OANDA response was not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OANDA response must be a JSON object")
    if status_code >= 400:
        raise RuntimeError(f"OANDA request failed with HTTP {status_code}: {redact_value(payload)}")
    return payload


class OandaBrokerConnector:
    """OANDA REST-v20 connector for account diagnostics and guarded market orders."""

    def __init__(
        self,
        *,
        account_id: str,
        token: str = "",
        base_url: str = "https://api-fxpractice.oanda.com",
        session: Any | None = None,
    ) -> None:
        self.account_id = str(account_id or "").strip()
        self.token = str(token or "").strip()
        self.base_url = _clean_base_url(base_url)
        self.session = session or requests.Session()

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "oanda-rest",
                "selected_forex_broker": "OANDA",
            }
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _account_path(self, suffix: str) -> str:
        if not self.account_id:
            raise RuntimeError("OANDA account_id is required")
        return f"{self.base_url}/v3/accounts/{self.account_id}{suffix}"

    def _require_live_credentials(self) -> None:
        if not self.account_id:
            raise RuntimeError("OANDA live request requires account_id")
        if not self.token:
            raise RuntimeError("OANDA live request requires token")

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_forex_broker": "OANDA",
                "connector_backend": "oanda-rest",
                "base_url": self.base_url,
                "account_id_present": bool(self.account_id),
                "token_present": bool(self.token),
                "support": self.support_payload(),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        self._require_live_credentials()
        response = self.session.get(self._account_path("/summary"), headers=self._headers(), timeout=15)
        payload = _response_json(response)
        return redact_value({**self.build_capability_snapshot(), "account": payload.get("account", payload)})

    def fetch_pricing_snapshot(self, instruments: list[str]) -> dict[str, object]:
        self._require_live_credentials()
        clean_instruments = [
            str(item or "").strip().upper().replace("/", "_") for item in instruments if str(item or "").strip()
        ]
        if not clean_instruments:
            raise ValueError("at least one OANDA instrument is required")
        response = self.session.get(
            self._account_path("/pricing"),
            headers=self._headers(),
            params={"instruments": ",".join(clean_instruments)},
            timeout=15,
        )
        payload = _response_json(response)
        return redact_value({**self.build_capability_snapshot(), "prices": payload.get("prices", [])})

    def submit_market_order(
        self,
        *,
        instrument: str,
        side: str,
        units: float,
        client_order_id: str = "",
        dry_run: bool = True,
        allow_live: bool = False,
        extra_order_fields: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        clean_instrument = str(instrument or "").strip().upper().replace("/", "_")
        if not clean_instrument:
            raise ValueError("instrument is required")
        clean_side = _normalize_side(side)
        clean_units = _positive_float(units, field="units")
        signed_units = clean_units if clean_side == "buy" else -clean_units
        order: dict[str, object] = {
            "instrument": clean_instrument,
            "units": str(int(signed_units) if signed_units.is_integer() else signed_units),
            "type": "MARKET",
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
        }
        if client_order_id:
            order["clientExtensions"] = {"id": str(client_order_id).strip()}
        if isinstance(extra_order_fields, Mapping):
            order.update(dict(extra_order_fields))
        request = {"order": order}
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
            raise RuntimeError("live OANDA order submission requires allow_live=True")
        self._require_live_credentials()
        response = self.session.post(self._account_path("/orders"), headers=self._headers(), json=request, timeout=15)
        payload = _response_json(response)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "request": request,
                "order": payload,
            }
        )


__all__ = ["OandaBrokerConnector"]
