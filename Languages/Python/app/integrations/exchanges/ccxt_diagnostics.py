from __future__ import annotations

from collections.abc import Callable, Mapping

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload, ccxt_exchange_id_for


ExchangeFactory = Callable[[str, Mapping[str, object]], object]


def _load_ccxt():
    import ccxt  # type: ignore

    return ccxt


def _compact_ticker(payload: object) -> dict[str, object]:
    raw = dict(payload) if isinstance(payload, Mapping) else {}
    result: dict[str, object] = {}
    for key in ("symbol", "timestamp", "datetime", "last", "bid", "ask", "open", "high", "low", "close", "baseVolume", "quoteVolume"):
        value = raw.get(key)
        if value not in (None, ""):
            result[key] = value
    return result


def _compact_balances(payload: object) -> list[dict[str, object]]:
    raw = dict(payload) if isinstance(payload, Mapping) else {}
    totals = raw.get("total") if isinstance(raw.get("total"), Mapping) else {}
    free = raw.get("free") if isinstance(raw.get("free"), Mapping) else {}
    used = raw.get("used") if isinstance(raw.get("used"), Mapping) else {}
    currencies = sorted({*(totals or {}).keys(), *(free or {}).keys(), *(used or {}).keys()})
    balances: list[dict[str, object]] = []
    for currency in currencies:
        item = {
            "asset": str(currency),
            "total": (totals or {}).get(currency),
            "free": (free or {}).get(currency),
            "used": (used or {}).get(currency),
        }
        balances.append({key: value for key, value in item.items() if value not in (None, "")})
    return balances


def _normalize_order_side(value: object) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("order side must be 'buy' or 'sell'")
    return side


def _normalize_order_type(value: object) -> str:
    order_type = str(value or "market").strip().lower()
    if order_type not in {"market", "limit"}:
        raise ValueError("ccxt order type must be 'market' or 'limit'")
    return order_type


def _positive_float(value: object, *, field: str) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive number")
    return parsed


def _compact_order(payload: object) -> dict[str, object]:
    raw = dict(payload) if isinstance(payload, Mapping) else {}
    result: dict[str, object] = {}
    for key in (
        "id",
        "clientOrderId",
        "timestamp",
        "datetime",
        "symbol",
        "type",
        "side",
        "price",
        "amount",
        "filled",
        "remaining",
        "status",
        "cost",
        "average",
    ):
        value = raw.get(key)
        if value not in (None, ""):
            result[key] = value
    return result


class CcxtDiagnosticsConnector:
    """ccxt connector for diagnostics plus guarded order routing across supported venues."""

    def __init__(
        self,
        *,
        selected_exchange: str,
        api_key: str = "",
        api_secret: str = "",
        password: str = "",
        mode: str = "Demo/Testnet",
        account_type: str = "Futures",
        exchange_factory: ExchangeFactory | None = None,
    ) -> None:
        self.selected_exchange = str(selected_exchange or "").strip()
        self.api_key = str(api_key or "").strip()
        self.api_secret = str(api_secret or "").strip()
        self.password = str(password or "").strip()
        self.mode = str(mode or "").strip()
        self.account_type = str(account_type or "").strip()
        self.exchange_id = ccxt_exchange_id_for(self.selected_exchange)
        self._exchange_factory = exchange_factory

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": self.selected_exchange,
                "connector_backend": "ccxt",
            }
        )

    def _options(self) -> dict[str, object]:
        options: dict[str, object] = {
            "enableRateLimit": True,
            "options": {
                "defaultType": "future" if self.account_type.lower().startswith("future") else "spot",
            },
        }
        if self.api_key:
            options["apiKey"] = self.api_key
        if self.api_secret:
            options["secret"] = self.api_secret
        if self.password:
            options["password"] = self.password
        return options

    def _build_exchange(self) -> object:
        if not self.exchange_id:
            raise ValueError(f"Exchange '{self.selected_exchange}' is not available through the ccxt connector adapter.")
        options = self._options()
        if self._exchange_factory is not None:
            exchange = self._exchange_factory(self.exchange_id, dict(options))
        else:
            ccxt = _load_ccxt()
            exchange_class = getattr(ccxt, self.exchange_id, None)
            if exchange_class is None:
                raise RuntimeError(f"ccxt exchange '{self.exchange_id}' is not installed in this ccxt build.")
            exchange = exchange_class(options)
        if "test" in self.mode.lower() or "demo" in self.mode.lower():
            set_sandbox_mode = getattr(exchange, "set_sandbox_mode", None)
            if callable(set_sandbox_mode):
                set_sandbox_mode(True)
        return exchange

    def build_capability_snapshot(self) -> dict[str, object]:
        support = self.support_payload()
        return redact_value(
            {
                "selected_exchange": self.selected_exchange,
                "connector_backend": "ccxt",
                "ccxt_exchange_id": self.exchange_id,
                "mode": self.mode,
                "account_type": self.account_type,
                "api_credentials_present": bool(self.api_key and self.api_secret),
                "support": support,
            }
        )

    def fetch_market_snapshot(self, symbol: str) -> dict[str, object]:
        exchange = self._build_exchange()
        markets = getattr(exchange, "load_markets", lambda: {})()
        fetch_ticker = getattr(exchange, "fetch_ticker", None)
        ticker = fetch_ticker(symbol) if callable(fetch_ticker) else {}
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": str(symbol or "").strip(),
                "market_count": len(markets) if isinstance(markets, Mapping) else None,
                "ticker": _compact_ticker(ticker),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        exchange = self._build_exchange()
        fetch_balance = getattr(exchange, "fetch_balance", None)
        if not callable(fetch_balance):
            raise RuntimeError(f"ccxt exchange '{self.exchange_id}' does not expose fetch_balance.")
        balance = fetch_balance()
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "balances": _compact_balances(balance),
            }
        )

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
        client_order_id: str = "",
        reduce_only: bool = False,
        dry_run: bool = True,
        allow_live: bool = False,
        params: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        support = self.support_payload()
        if not support.get("order_routing_supported"):
            raise RuntimeError(f"ccxt order routing is not supported for {self.selected_exchange}.")
        clean_symbol = str(symbol or "").strip()
        if not clean_symbol:
            raise ValueError("symbol is required")
        clean_side = _normalize_order_side(side)
        clean_type = _normalize_order_type(order_type)
        clean_amount = _positive_float(amount, field="amount")
        clean_price = None if price in (None, "") else _positive_float(price, field="price")
        if clean_type == "limit" and clean_price is None:
            raise ValueError("limit orders require price")
        order_params = dict(params) if isinstance(params, Mapping) else {}
        if client_order_id:
            order_params.setdefault("clientOrderId", str(client_order_id).strip())
        if reduce_only:
            order_params.setdefault("reduceOnly", True)

        request = {
            "symbol": clean_symbol,
            "type": clean_type,
            "side": clean_side,
            "amount": clean_amount,
            "price": clean_price,
            "params": order_params,
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
            raise RuntimeError("live ccxt order submission requires allow_live=True")
        if not (self.api_key and self.api_secret):
            raise RuntimeError("live ccxt order submission requires API key and secret")

        exchange = self._build_exchange()
        create_order = getattr(exchange, "create_order", None)
        if not callable(create_order):
            raise RuntimeError(f"ccxt exchange '{self.exchange_id}' does not expose create_order.")
        order = create_order(clean_symbol, clean_type, clean_side, clean_amount, clean_price, order_params)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "request": request,
                "order": _compact_order(order),
            }
        )


__all__ = ["CcxtDiagnosticsConnector", "ExchangeFactory"]
