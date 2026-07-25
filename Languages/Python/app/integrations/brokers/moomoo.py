from __future__ import annotations

import math
from collections.abc import Mapping
from importlib import import_module
from typing import Any

from ...security.redaction import redact_value
from ...settings.exchange_support import build_exchange_support_payload
from ._order_validation import merge_extra_order_fields


MOOMOO_ORDER_TYPES = (
    "NORMAL",
    "MARKET",
    "ABSOLUTE_LIMIT",
    "AUCTION",
    "AUCTION_LIMIT",
    "SPECIAL_LIMIT",
    "SPECIAL_LIMIT_ALL",
    "STOP",
    "STOP_LIMIT",
    "MARKET_IF_TOUCHED",
    "LIMIT_IF_TOUCHED",
    "TRAILING_STOP",
    "TRAILING_STOP_LIMIT",
)
_AUX_PRICE_ORDER_TYPES = {"STOP", "STOP_LIMIT", "MARKET_IF_TOUCHED", "LIMIT_IF_TOUCHED"}
_TRAILING_ORDER_TYPES = {"TRAILING_STOP", "TRAILING_STOP_LIMIT"}
_MARKET_PRICE_OPTIONAL_ORDER_TYPES = {"MARKET", "AUCTION"}
_PROTECTED_ORDER_FIELDS = frozenset(
    {
        "acc_id",
        "acc_index",
        "adjust_limit",
        "aux_price",
        "code",
        "order_type",
        "price",
        "qty",
        "remark",
        "session",
        "time_in_force",
        "trail_spread",
        "trail_type",
        "trail_value",
        "trd_env",
        "trd_side",
    }
)
_ENUM_ALIASES = {
    ("TimeInForce", "GTC"): ("GTC", "GOOD_TILL_CANCEL"),
    ("TimeInForce", "GOOD_TILL_CANCEL"): ("GOOD_TILL_CANCEL", "GTC"),
}


def _clean_host(value: object) -> str:
    host = str(value or "127.0.0.1").strip()
    if not host:
        raise ValueError("moomoo OpenD host is required")
    if "://" in host or "/" in host or "\\" in host or any(char.isspace() for char in host):
        raise ValueError("moomoo OpenD host must be a hostname or IP address without a URL scheme or path")
    return host


def _clean_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("moomoo OpenD port must be an integer") from exc
    if port < 1 or port > 65535:
        raise ValueError("moomoo OpenD port must be between 1 and 65535")
    return port


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


def _non_negative_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative number")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return parsed


def _normalized_name(value: object, *, field: str) -> str:
    name = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not name:
        raise ValueError(f"{field} is required")
    return name


def _normalize_environment(value: object) -> str:
    key = _normalized_name(value or "SIMULATE", field="environment")
    aliases = {"DEMO": "SIMULATE", "PAPER": "SIMULATE", "SIMULATE": "SIMULATE", "LIVE": "REAL", "REAL": "REAL"}
    environment = aliases.get(key)
    if environment is None:
        raise ValueError("moomoo environment must be 'simulate' or 'real'")
    return environment


def _normalize_order_type(value: object) -> str:
    order_type = _normalized_name(value or "NORMAL", field="order_type")
    if order_type not in MOOMOO_ORDER_TYPES:
        raise ValueError(f"moomoo order_type must be one of: {', '.join(MOOMOO_ORDER_TYPES)}")
    return order_type


def _resolve_enum(module: object, enum_name: str, value: str) -> object:
    enum_type = getattr(module, enum_name, None)
    if enum_type is None:
        raise RuntimeError(f"moomoo SDK does not expose {enum_name}")
    candidates = _ENUM_ALIASES.get((enum_name, value), (value,))
    for candidate in candidates:
        resolved = getattr(enum_type, candidate, None)
        if resolved is not None:
            return resolved
    raise ValueError(f"moomoo {enum_name} does not support '{value}'")


def _records(value: object) -> list[object] | dict[str, object] | object:
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            try:
                return value.to_dict()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                return str(value)
        except (AttributeError, RuntimeError, ValueError):
            return str(value)
    if isinstance(value, (dict, list, tuple)):
        return list(value) if isinstance(value, tuple) else value
    return str(value)


class MoomooOpenDConnector:
    """Official moomoo SDK connector through a local or remote OpenD gateway."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        market: str = "US",
        environment: str = "simulate",
        account_id: int = 0,
        account_index: int = 0,
        security_firm: str = "",
        unlock_password: str = "",
        sdk_module: Any | None = None,
        trade_context: Any | None = None,
        quote_context: Any | None = None,
    ) -> None:
        self.host = _clean_host(host)
        self.port = _clean_port(port)
        self.market = _normalized_name(market, field="market")
        self.environment = _normalize_environment(environment)
        self.account_id = int(account_id)
        self.account_index = int(account_index)
        if self.account_id < 0 or self.account_index < 0:
            raise ValueError("moomoo account_id and account_index must not be negative")
        self.security_firm = _normalized_name(security_firm, field="security_firm") if security_firm else ""
        self.unlock_password = str(unlock_password or "")
        self._sdk_module = sdk_module
        self._trade_context_value = trade_context
        self._quote_context_value = quote_context
        self._trade_unlocked = False

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "moomoo-opend",
                "selected_forex_broker": "moomoo",
            }
        )

    def _sdk(self) -> Any:
        if self._sdk_module is None:
            try:
                self._sdk_module = import_module("moomoo")
            except ImportError as exc:
                raise RuntimeError("moomoo OpenD support requires the optional 'moomoo-api' package") from exc
        return self._sdk_module

    def _trade_context(self) -> Any:
        if self._trade_context_value is None:
            sdk = self._sdk()
            factory = getattr(sdk, "OpenSecTradeContext", None)
            if not callable(factory):
                raise RuntimeError("moomoo SDK does not expose OpenSecTradeContext")
            kwargs: dict[str, object] = {
                "filter_trdmarket": _resolve_enum(sdk, "TrdMarket", self.market),
                "host": self.host,
                "port": self.port,
            }
            if self.security_firm:
                kwargs["security_firm"] = _resolve_enum(sdk, "SecurityFirm", self.security_firm)
            self._trade_context_value = factory(**kwargs)
        return self._trade_context_value

    def _quote_context(self) -> Any:
        if self._quote_context_value is None:
            sdk = self._sdk()
            factory = getattr(sdk, "OpenQuoteContext", None)
            if not callable(factory):
                raise RuntimeError("moomoo SDK does not expose OpenQuoteContext")
            kwargs: dict[str, object] = {"host": self.host, "port": self.port}
            if self.security_firm:
                kwargs["security_firm"] = _resolve_enum(sdk, "SecurityFirm", self.security_firm)
            self._quote_context_value = factory(**kwargs)
        return self._quote_context_value

    def _result(self, result: object, *, operation: str) -> object:
        if not isinstance(result, tuple) or len(result) != 2:
            raise RuntimeError(f"moomoo {operation} returned an invalid SDK result")
        ret, data = result
        if ret != getattr(self._sdk(), "RET_OK", 0):
            raise RuntimeError(f"moomoo {operation} failed: {redact_value(_records(data))}")
        return _records(data)

    def _trade_environment(self) -> object:
        return _resolve_enum(self._sdk(), "TrdEnv", self.environment)

    def _unlock_real_trade_if_configured(self) -> None:
        if self.environment != "REAL" or self._trade_unlocked or not self.unlock_password:
            return
        self._result(
            self._trade_context().unlock_trade(self.unlock_password),
            operation="trade unlock",
        )
        self._trade_unlocked = True

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_broker": "moomoo",
                "selected_forex_broker": "moomoo",
                "connector_backend": "moomoo-opend",
                "transport": "OpenD TCP gateway",
                "host": self.host,
                "port": self.port,
                "market": self.market,
                "environment": self.environment,
                "account_id": self.account_id,
                "account_index": self.account_index,
                "security_firm": self.security_firm,
                "unlock_password_present": bool(self.unlock_password),
                "provider_api_scope": "stocks-etfs-options-futures-funds-and-supported-crypto",
                "forex_order_routing_supported": False,
                "supported_order_types": list(MOOMOO_ORDER_TYPES),
                "support": self.support_payload(),
            }
        )

    def fetch_accounts_snapshot(self) -> dict[str, object]:
        accounts = self._result(self._trade_context().get_acc_list(), operation="account list")
        return redact_value({**self.build_capability_snapshot(), "accounts": accounts})

    def fetch_account_snapshot(self) -> dict[str, object]:
        account = self._result(
            self._trade_context().accinfo_query(
                trd_env=self._trade_environment(),
                acc_id=self.account_id,
                acc_index=self.account_index,
            ),
            operation="account funds",
        )
        return redact_value({**self.build_capability_snapshot(), "account": account})

    def fetch_positions_snapshot(self) -> dict[str, object]:
        positions = self._result(
            self._trade_context().position_list_query(
                trd_env=self._trade_environment(),
                acc_id=self.account_id,
                acc_index=self.account_index,
            ),
            operation="positions",
        )
        return redact_value({**self.build_capability_snapshot(), "positions": positions})

    def fetch_orders_snapshot(self, *, refresh_cache: bool = False) -> dict[str, object]:
        orders = self._result(
            self._trade_context().order_list_query(
                trd_env=self._trade_environment(),
                acc_id=self.account_id,
                acc_index=self.account_index,
                refresh_cache=bool(refresh_cache),
            ),
            operation="open orders",
        )
        return redact_value({**self.build_capability_snapshot(), "orders": orders})

    def fetch_market_snapshot(self, codes: str | list[str]) -> dict[str, object]:
        raw_codes = [codes] if isinstance(codes, str) else list(codes)
        clean_codes = [str(code or "").strip().upper() for code in raw_codes if str(code or "").strip()]
        if not clean_codes:
            raise ValueError("at least one moomoo market code is required")
        market = self._result(
            self._quote_context().get_market_snapshot(clean_codes),
            operation="market snapshot",
        )
        return redact_value({**self.build_capability_snapshot(), "codes": clean_codes, "market": market})

    def submit_order(
        self,
        *,
        code: str,
        side: str,
        quantity: float,
        order_type: str = "NORMAL",
        price: float = 0,
        adjust_limit: float = 0,
        remark: str = "",
        time_in_force: str = "DAY",
        session: str = "NONE",
        aux_price: float | None = None,
        trail_type: str | None = None,
        trail_value: float | None = None,
        trail_spread: float | None = None,
        dry_run: bool = True,
        allow_live: bool = False,
        extra_order_fields: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        clean_code = str(code or "").strip().upper()
        if not clean_code or "." not in clean_code:
            raise ValueError("moomoo code must include a market prefix, for example 'US.AAPL'")
        clean_side = _normalized_name(side, field="side")
        if clean_side not in {"BUY", "SELL"}:
            raise ValueError("moomoo side must be 'buy' or 'sell'")
        clean_order_type = _normalize_order_type(order_type)
        clean_quantity = _positive_float(quantity, field="quantity")
        clean_price = _non_negative_float(price, field="price")
        if clean_order_type not in _MARKET_PRICE_OPTIONAL_ORDER_TYPES and clean_price <= 0:
            raise ValueError(f"price must be positive for moomoo {clean_order_type} orders")
        clean_remark = str(remark or "")
        if len(clean_remark.encode("utf-8")) > 64:
            raise ValueError("moomoo remark must not exceed 64 UTF-8 bytes")
        request: dict[str, object] = {
            "price": clean_price,
            "qty": clean_quantity,
            "code": clean_code,
            "trd_side": clean_side,
            "order_type": clean_order_type,
            "adjust_limit": float(adjust_limit),
            "trd_env": self.environment,
            "acc_id": self.account_id,
            "acc_index": self.account_index,
            "remark": clean_remark,
            "time_in_force": _normalized_name(time_in_force, field="time_in_force"),
            "session": _normalized_name(session, field="session"),
        }
        if clean_order_type in _AUX_PRICE_ORDER_TYPES:
            if aux_price is None:
                raise ValueError(f"aux_price is required for moomoo {clean_order_type} orders")
            request["aux_price"] = _positive_float(aux_price, field="aux_price")
        if clean_order_type in _TRAILING_ORDER_TYPES:
            if trail_type is None or trail_value is None:
                raise ValueError(f"trail_type and trail_value are required for moomoo {clean_order_type} orders")
            request["trail_type"] = _normalized_name(trail_type, field="trail_type")
            request["trail_value"] = _positive_float(trail_value, field="trail_value")
        if clean_order_type == "TRAILING_STOP_LIMIT":
            if trail_spread is None:
                raise ValueError("trail_spread is required for moomoo TRAILING_STOP_LIMIT orders")
            request["trail_spread"] = _positive_float(trail_spread, field="trail_spread")
        merge_extra_order_fields(
            request,
            extra_order_fields,
            protected_fields=_PROTECTED_ORDER_FIELDS,
            provider="moomoo",
        )

        snapshot = {**self.build_capability_snapshot(), "request": request}
        if dry_run:
            return redact_value({**snapshot, "status": "dry_run", "order": None})
        if not allow_live:
            raise RuntimeError("moomoo order submission requires allow_live=True")
        self._unlock_real_trade_if_configured()
        sdk = self._sdk()
        sdk_request = dict(request)
        sdk_request["trd_side"] = _resolve_enum(sdk, "TrdSide", clean_side)
        sdk_request["order_type"] = _resolve_enum(sdk, "OrderType", clean_order_type)
        sdk_request["trd_env"] = self._trade_environment()
        sdk_request["time_in_force"] = _resolve_enum(sdk, "TimeInForce", str(request["time_in_force"]))
        sdk_request["session"] = _resolve_enum(sdk, "Session", str(request["session"]))
        if "trail_type" in sdk_request:
            sdk_request["trail_type"] = _resolve_enum(sdk, "TrailType", str(request["trail_type"]))
        order = self._result(
            self._trade_context().place_order(**sdk_request),
            operation="order placement",
        )
        return redact_value({**snapshot, "status": "submitted", "order": order})

    def cancel_order(
        self,
        order_id: str,
        *,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        clean_order_id = str(order_id or "").strip()
        if not clean_order_id:
            raise ValueError("moomoo order_id is required")
        request = {"order_id": clean_order_id}
        snapshot = {**self.build_capability_snapshot(), "request": request}
        if dry_run:
            return redact_value({**snapshot, "status": "dry_run", "cancelled": False})
        if not allow_live:
            raise RuntimeError("moomoo order cancellation requires allow_live=True")
        self._unlock_real_trade_if_configured()
        sdk = self._sdk()
        result = self._result(
            self._trade_context().modify_order(
                modify_order_op=_resolve_enum(sdk, "ModifyOrderOp", "CANCEL"),
                order_id=clean_order_id,
                qty=0,
                price=0,
                trd_env=self._trade_environment(),
                acc_id=self.account_id,
                acc_index=self.account_index,
            ),
            operation="order cancellation",
        )
        return redact_value({**snapshot, "status": "submitted", "cancelled": True, "response": result})

    def close(self) -> None:
        for context in (self._quote_context_value, self._trade_context_value):
            close = getattr(context, "close", None)
            if callable(close):
                close()
        self._quote_context_value = None
        self._trade_context_value = None
        self._trade_unlocked = False

    def __enter__(self) -> MoomooOpenDConnector:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = ["MOOMOO_ORDER_TYPES", "MoomooOpenDConnector"]
