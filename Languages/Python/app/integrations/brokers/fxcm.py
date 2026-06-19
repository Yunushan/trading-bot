from __future__ import annotations

from collections.abc import Callable, Mapping

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload


FxcmClientFactory = Callable[[str, str], object]


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


def _plain_payload(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _plain_payload(to_dict())
        except Exception:
            return repr(value)
    return repr(value)


class FxcmBrokerConnector:
    """FXCM connector using fxcmpy-compatible clients for guarded market orders."""

    def __init__(
        self,
        *,
        access_token: str = "",
        server: str = "demo",
        client: object | None = None,
        client_factory: FxcmClientFactory | None = None,
    ) -> None:
        self.access_token = str(access_token or "").strip()
        self.server = str(server or "demo").strip() or "demo"
        self._client = client
        self._client_factory = client_factory

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "fxcmpy",
                "selected_forex_broker": "FXCM",
            }
        )

    def _require_live_credentials(self) -> None:
        if not self.access_token and self._client is None and self._client_factory is None:
            raise RuntimeError("FXCM live request requires access_token or an injected client")

    def _build_client(self) -> object:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            return self._client_factory(self.access_token, self.server)
        self._require_live_credentials()
        try:
            import fxcmpy  # type: ignore
        except Exception as exc:
            raise RuntimeError("FXCM live requests require the optional fxcmpy package") from exc
        return fxcmpy.fxcmpy(access_token=self.access_token, server=self.server)

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_forex_broker": "FXCM",
                "connector_backend": "fxcmpy",
                "server": self.server,
                "access_token_present": bool(self.access_token),
                "injected_client_present": self._client is not None or self._client_factory is not None,
                "support": self.support_payload(),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        client = self._build_client()
        get_accounts = getattr(client, "get_accounts", None)
        if not callable(get_accounts):
            raise RuntimeError("FXCM client does not expose get_accounts")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "accounts": _plain_payload(get_accounts()),
            }
        )

    def fetch_market_snapshot(self, symbol: str = "") -> dict[str, object]:
        client = self._build_client()
        get_offers = getattr(client, "get_offers", None)
        get_prices = getattr(client, "get_prices", None)
        if callable(get_offers):
            market_payload = get_offers()
        elif callable(get_prices):
            clean_symbol = str(symbol or "").strip().upper()
            if not clean_symbol:
                raise ValueError("symbol is required when FXCM client only exposes get_prices")
            market_payload = get_prices(clean_symbol)
        else:
            raise RuntimeError("FXCM client does not expose get_offers or get_prices")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": str(symbol or "").strip().upper(),
                "market": _plain_payload(market_payload),
            }
        )

    def fetch_open_positions_snapshot(self) -> dict[str, object]:
        client = self._build_client()
        get_positions = getattr(client, "get_open_positions", None)
        if not callable(get_positions):
            raise RuntimeError("FXCM client does not expose get_open_positions")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "positions": _plain_payload(get_positions()),
            }
        )

    def submit_market_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        clean_symbol = str(symbol or "").strip().upper()
        if not clean_symbol:
            raise ValueError("symbol is required")
        clean_side = _normalize_side(side)
        clean_amount = _positive_float(amount, field="amount")
        request = {
            "symbol": clean_symbol,
            "side": clean_side,
            "amount": int(clean_amount) if clean_amount.is_integer() else clean_amount,
            "method": f"create_market_{clean_side}_order",
        }
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
            raise RuntimeError("live FXCM order submission requires allow_live=True")
        self._require_live_credentials()
        client = self._build_client()
        method = getattr(client, str(request["method"]), None)
        if callable(method):
            order = method(request["symbol"], request["amount"])
        else:
            open_trade = getattr(client, "open_trade", None)
            if not callable(open_trade):
                raise RuntimeError("FXCM client does not expose market order submission")
            order = open_trade(
                symbol=request["symbol"],
                is_buy=clean_side == "buy",
                amount=str(request["amount"]),
                order_type="AtMarket",
                time_in_force="GTC",
            )
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "request": request,
                "order": _plain_payload(order),
            }
        )


__all__ = ["FxcmBrokerConnector", "FxcmClientFactory"]
