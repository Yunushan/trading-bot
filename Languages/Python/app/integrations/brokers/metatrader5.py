from __future__ import annotations

import math
from collections.abc import Callable, Mapping

from ...security.redaction import redact_text, redact_value
from ...settings.exchange_support import (
    METATRADER5_BROKERS,
    METATRADER5_BROKER_ALIASES,
    METATRADER5_BROKER_OFFICIAL_SOURCES,
    build_exchange_support_payload,
)


MetaTrader5ClientFactory = Callable[[], object]

MT5_BROKER_PROVIDERS: tuple[str, ...] = METATRADER5_BROKERS
MT5_MAX_TIMEOUT_MS = 300_000
MT5_MAX_SYMBOL_UTF8_BYTES = 64
MT5_MAX_COMMENT_UTF8_BYTES = 31
MT5_MAX_SERVER_UTF8_BYTES = 256
MT5_MAX_TERMINAL_PATH_UTF8_BYTES = 4_096


def _provider_key(value: object) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


_PROVIDERS_BY_KEY = {
    **{_provider_key(provider): provider for provider in MT5_BROKER_PROVIDERS},
    **{_provider_key(alias): canonical for alias, canonical in METATRADER5_BROKER_ALIASES.items()},
}


def _canonical_provider(value: object) -> str:
    provider = _PROVIDERS_BY_KEY.get(_provider_key(value), "")
    if not provider:
        supported = ", ".join(MT5_BROKER_PROVIDERS)
        raise ValueError(f"provider must be one of: {supported}")
    return provider


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


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a non-negative integer") from exc
    if parsed < 0 or str(value).strip() not in {str(parsed), f"+{parsed}"}:
        raise ValueError(f"{field} must be a non-negative integer")
    return parsed


def _optional_positive_float(value: object | None, *, field: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _positive_float(value, field=field)


def _bounded_text(
    value: object,
    *,
    field: str,
    max_utf8_bytes: int,
    required: bool = False,
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(f"{field} must not contain control characters")
    if len(text.encode("utf-8")) > max_utf8_bytes:
        raise ValueError(f"{field} must contain at most {max_utf8_bytes} UTF-8 bytes")
    return text


def _plain_payload(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_payload(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    as_dict = getattr(value, "_asdict", None)
    if callable(as_dict):
        try:
            return _plain_payload(as_dict())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return redact_text(repr(value))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _plain_payload(to_dict())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return redact_text(repr(value))
    return redact_text(repr(value))


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class MetaTrader5BrokerConnector:
    """Guarded connector for brokers that officially expose MetaTrader 5."""

    def __init__(
        self,
        *,
        provider: str,
        login: int | str | None = None,
        password: str = "",
        server: str = "",
        terminal_path: str = "",
        timeout_ms: int = 60_000,
        portable: bool = False,
        client: object | None = None,
        client_factory: MetaTrader5ClientFactory | None = None,
    ) -> None:
        self.provider = _canonical_provider(provider)
        self.login = self._parse_login(login)
        self.password = str(password or "")
        self.server = _bounded_text(
            server,
            field="server",
            max_utf8_bytes=MT5_MAX_SERVER_UTF8_BYTES,
        )
        self.terminal_path = _bounded_text(
            terminal_path,
            field="terminal_path",
            max_utf8_bytes=MT5_MAX_TERMINAL_PATH_UTF8_BYTES,
        )
        self.timeout_ms = _positive_timeout(timeout_ms)
        self.portable = bool(portable)
        self._client = client
        self._client_factory = client_factory
        self._initialized = False

    @staticmethod
    def _parse_login(value: int | str | None) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        if isinstance(value, bool):
            raise ValueError("login must be a positive account number")
        try:
            login = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("login must be a positive account number") from exc
        if login <= 0:
            raise ValueError("login must be a positive account number")
        return login

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "metatrader5",
                "selected_forex_broker": self.provider,
            }
        )

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_forex_broker": self.provider,
                "connector_backend": "metatrader5",
                "official_transport_source": METATRADER5_BROKER_OFFICIAL_SOURCES[self.provider],
                "login_present": self.login is not None,
                "password_present": bool(self.password),
                "server": self.server,
                "terminal_path_present": bool(self.terminal_path),
                "timeout_ms": self.timeout_ms,
                "portable": self.portable,
                "injected_client_present": self._client is not None or self._client_factory is not None,
                "initialized": self._initialized,
                "support": self.support_payload(),
            }
        )

    def _client_instance(self) -> object:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader 5 requests require the optional MetaTrader5 package and a local Windows x64 terminal"
            ) from exc
        self._client = mt5
        return self._client

    def _last_error(self, client: object) -> object:
        last_error = getattr(client, "last_error", None)
        if not callable(last_error):
            return "unavailable"
        try:
            return _plain_payload(last_error())
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return redact_text(repr(exc))

    def _ensure_initialized(self) -> object:
        client = self._client_instance()
        if self._initialized:
            return client
        initialize = getattr(client, "initialize", None)
        if not callable(initialize):
            raise RuntimeError("MetaTrader 5 client does not expose initialize")
        kwargs: dict[str, object] = {
            "timeout": self.timeout_ms,
            "portable": self.portable,
        }
        if self.login is not None:
            kwargs["login"] = self.login
        if self.password:
            kwargs["password"] = self.password
        if self.server:
            kwargs["server"] = self.server
        initialized = initialize(self.terminal_path, **kwargs) if self.terminal_path else initialize(**kwargs)
        if not initialized:
            error = redact_value(self._last_error(client))
            raise RuntimeError(f"MetaTrader 5 initialize failed: {error}")
        self._initialized = True
        return client

    @staticmethod
    def _require_method(client: object, name: str) -> Callable[..., object]:
        method = getattr(client, name, None)
        if not callable(method):
            raise RuntimeError(f"MetaTrader 5 client does not expose {name}")
        return method

    def close(self) -> None:
        if not self._initialized or self._client is None:
            return
        shutdown = getattr(self._client, "shutdown", None)
        try:
            if callable(shutdown):
                shutdown()
        finally:
            self._initialized = False

    def __enter__(self) -> MetaTrader5BrokerConnector:
        self._ensure_initialized()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def fetch_terminal_snapshot(self) -> dict[str, object]:
        client = self._ensure_initialized()
        terminal_info = self._require_method(client, "terminal_info")()
        version = self._require_method(client, "version")()
        if terminal_info is None:
            raise RuntimeError(f"MetaTrader 5 terminal_info failed: {redact_value(self._last_error(client))}")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "terminal": _plain_payload(terminal_info),
                "version": _plain_payload(version),
            }
        )

    def fetch_account_snapshot(self) -> dict[str, object]:
        client = self._ensure_initialized()
        account = self._require_method(client, "account_info")()
        if account is None:
            raise RuntimeError(f"MetaTrader 5 account_info failed: {redact_value(self._last_error(client))}")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "account": _plain_payload(account),
            }
        )

    def _ensure_symbol(self, client: object, symbol: str) -> object:
        symbol_info = self._require_method(client, "symbol_info")(symbol)
        if symbol_info is None:
            raise RuntimeError(
                f"MetaTrader 5 symbol_info failed for '{symbol}': {redact_value(self._last_error(client))}"
            )
        if not bool(_field(symbol_info, "visible", True)):
            selected = self._require_method(client, "symbol_select")(symbol, True)
            if not selected:
                raise RuntimeError(
                    f"MetaTrader 5 could not select symbol '{symbol}': {redact_value(self._last_error(client))}"
                )
            symbol_info = self._require_method(client, "symbol_info")(symbol)
            if symbol_info is None:
                raise RuntimeError(f"MetaTrader 5 symbol_info failed after selecting '{symbol}'")
        return symbol_info

    def fetch_market_snapshot(self, symbol: str) -> dict[str, object]:
        clean_symbol = _bounded_text(
            symbol,
            field="symbol",
            max_utf8_bytes=MT5_MAX_SYMBOL_UTF8_BYTES,
            required=True,
        )
        client = self._ensure_initialized()
        symbol_info = self._ensure_symbol(client, clean_symbol)
        tick = self._require_method(client, "symbol_info_tick")(clean_symbol)
        if tick is None:
            raise RuntimeError(
                f"MetaTrader 5 symbol_info_tick failed for '{clean_symbol}': {redact_value(self._last_error(client))}"
            )
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "symbol_info": _plain_payload(symbol_info),
                "tick": _plain_payload(tick),
            }
        )

    def fetch_open_positions_snapshot(self, symbol: str = "") -> dict[str, object]:
        clean_symbol = _bounded_text(
            symbol,
            field="symbol",
            max_utf8_bytes=MT5_MAX_SYMBOL_UTF8_BYTES,
        )
        client = self._ensure_initialized()
        positions_get = self._require_method(client, "positions_get")
        positions = positions_get(symbol=clean_symbol) if clean_symbol else positions_get()
        if positions is None:
            raise RuntimeError(f"MetaTrader 5 positions_get failed: {redact_value(self._last_error(client))}")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "positions": _plain_payload(positions),
            }
        )

    def fetch_open_orders_snapshot(self, symbol: str = "") -> dict[str, object]:
        clean_symbol = _bounded_text(
            symbol,
            field="symbol",
            max_utf8_bytes=MT5_MAX_SYMBOL_UTF8_BYTES,
        )
        client = self._ensure_initialized()
        orders_get = self._require_method(client, "orders_get")
        orders = orders_get(symbol=clean_symbol) if clean_symbol else orders_get()
        if orders is None:
            raise RuntimeError(f"MetaTrader 5 orders_get failed: {redact_value(self._last_error(client))}")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "orders": _plain_payload(orders),
            }
        )

    @staticmethod
    def _filling_candidates(client: object, symbol_info: object, requested: str) -> list[int]:
        requested_key = str(requested or "auto").strip().lower()
        values = {
            "fok": getattr(client, "ORDER_FILLING_FOK", None),
            "ioc": getattr(client, "ORDER_FILLING_IOC", None),
            "return": getattr(client, "ORDER_FILLING_RETURN", None),
        }
        if requested_key not in {"auto", *values}:
            raise ValueError("filling_mode must be 'auto', 'fok', 'ioc', or 'return'")
        if requested_key != "auto":
            selected = values[requested_key]
            if selected is None:
                raise RuntimeError(f"MetaTrader 5 client does not expose ORDER_FILLING_{requested_key.upper()}")
            return [int(selected)]

        candidates: list[int] = []
        flags = int(_field(symbol_info, "filling_mode", 0) or 0)
        flag_pairs = (
            (getattr(client, "SYMBOL_FILLING_IOC", 2), values["ioc"]),
            (getattr(client, "SYMBOL_FILLING_FOK", 1), values["fok"]),
        )
        for flag, value in flag_pairs:
            if value is not None and flags & int(flag):
                candidates.append(int(value))
        for key in ("return", "ioc", "fok"):
            value = values[key]
            if value is not None and int(value) not in candidates:
                candidates.append(int(value))
        if not candidates:
            raise RuntimeError("MetaTrader 5 client does not expose a supported order filling mode")
        return candidates

    def _preflight_request(
        self,
        client: object,
        symbol_info: object,
        request: dict[str, object],
        filling_mode: str,
    ) -> tuple[dict[str, object], object]:
        order_check = self._require_method(client, "order_check")
        failures: list[object] = []
        for candidate in self._filling_candidates(client, symbol_info, filling_mode):
            candidate_request = {**request, "type_filling": candidate}
            check = order_check(candidate_request)
            if check is None:
                failures.append({"type_filling": candidate, "last_error": self._last_error(client)})
                continue
            retcode = _field(check, "retcode")
            if retcode == 0:
                return candidate_request, check
            failures.append(_plain_payload(check))
        raise RuntimeError(f"MetaTrader 5 order preflight failed: {redact_value(failures)}")

    def submit_market_order(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "trading-bot",
        filling_mode: str = "auto",
        position_ticket: int | None = None,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        clean_symbol = _bounded_text(
            symbol,
            field="symbol",
            max_utf8_bytes=MT5_MAX_SYMBOL_UTF8_BYTES,
            required=True,
        )
        clean_side = str(side or "").strip().lower()
        if clean_side not in {"buy", "sell"}:
            raise ValueError("order side must be 'buy' or 'sell'")
        clean_volume = _positive_float(volume, field="volume")
        clean_stop_loss = _optional_positive_float(stop_loss, field="stop_loss")
        clean_take_profit = _optional_positive_float(take_profit, field="take_profit")
        clean_deviation = _nonnegative_int(deviation, field="deviation")
        clean_magic = _nonnegative_int(magic, field="magic")
        clean_comment = _bounded_text(
            comment,
            field="comment",
            max_utf8_bytes=MT5_MAX_COMMENT_UTF8_BYTES,
        )
        clean_position_ticket = None
        if position_ticket is not None:
            clean_position_ticket = _positive_ticket(position_ticket)
        requested_filling = str(filling_mode or "auto").strip().lower()
        if requested_filling not in {"auto", "fok", "ioc", "return"}:
            raise ValueError("filling_mode must be 'auto', 'fok', 'ioc', or 'return'")

        request_preview: dict[str, object] = {
            "action": "TRADE_ACTION_DEAL",
            "symbol": clean_symbol,
            "volume": clean_volume,
            "type": f"ORDER_TYPE_{clean_side.upper()}",
            "deviation": clean_deviation,
            "magic": clean_magic,
            "comment": clean_comment,
            "type_time": "ORDER_TIME_GTC",
            "type_filling": requested_filling,
        }
        if clean_stop_loss is not None:
            request_preview["sl"] = clean_stop_loss
        if clean_take_profit is not None:
            request_preview["tp"] = clean_take_profit
        if clean_position_ticket is not None:
            request_preview["position"] = clean_position_ticket
        if dry_run:
            return redact_value(
                {
                    **self.build_capability_snapshot(),
                    "status": "dry_run",
                    "request": request_preview,
                    "order_check": None,
                    "order": None,
                }
            )
        if not allow_live:
            raise RuntimeError("live MetaTrader 5 order submission requires allow_live=True")

        client = self._ensure_initialized()
        symbol_info = self._ensure_symbol(client, clean_symbol)
        tick = self._require_method(client, "symbol_info_tick")(clean_symbol)
        if tick is None:
            raise RuntimeError(
                f"MetaTrader 5 symbol_info_tick failed for '{clean_symbol}': {redact_value(self._last_error(client))}"
            )
        price = _positive_float(_field(tick, "ask" if clean_side == "buy" else "bid"), field="market price")
        request: dict[str, object] = {
            "action": int(getattr(client, "TRADE_ACTION_DEAL")),
            "symbol": clean_symbol,
            "volume": clean_volume,
            "type": int(getattr(client, f"ORDER_TYPE_{clean_side.upper()}")),
            "price": price,
            "deviation": clean_deviation,
            "magic": clean_magic,
            "comment": clean_comment,
            "type_time": int(getattr(client, "ORDER_TIME_GTC")),
        }
        if clean_stop_loss is not None:
            request["sl"] = clean_stop_loss
        if clean_take_profit is not None:
            request["tp"] = clean_take_profit
        if clean_position_ticket is not None:
            request["position"] = clean_position_ticket
        checked_request, check = self._preflight_request(client, symbol_info, request, requested_filling)
        result = self._require_method(client, "order_send")(checked_request)
        if result is None:
            raise RuntimeError(f"MetaTrader 5 order_send failed: {redact_value(self._last_error(client))}")
        accepted_retcodes = {
            int(getattr(client, name, fallback))
            for name, fallback in (
                ("TRADE_RETCODE_PLACED", 10008),
                ("TRADE_RETCODE_DONE", 10009),
                ("TRADE_RETCODE_DONE_PARTIAL", 10010),
            )
        }
        if _field(result, "retcode") not in accepted_retcodes:
            raise RuntimeError(f"MetaTrader 5 order_send rejected the request: {redact_value(_plain_payload(result))}")
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "request": checked_request,
                "order_check": _plain_payload(check),
                "order": _plain_payload(result),
            }
        )


def _positive_timeout(value: object) -> int:
    timeout = _nonnegative_int(value, field="timeout_ms")
    if timeout == 0:
        raise ValueError("timeout_ms must be a positive integer")
    if timeout > MT5_MAX_TIMEOUT_MS:
        raise ValueError(f"timeout_ms must be at most {MT5_MAX_TIMEOUT_MS}")
    return timeout


def _positive_ticket(value: object) -> int:
    ticket = _nonnegative_int(value, field="position_ticket")
    if ticket == 0:
        raise ValueError("position_ticket must be a positive integer")
    return ticket


class AvaTradeBrokerConnector(MetaTrader5BrokerConnector):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider="AvaTrade", **kwargs)


class EcMarketsBrokerConnector(MetaTrader5BrokerConnector):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider="EC Markets", **kwargs)


class GtcFxBrokerConnector(MetaTrader5BrokerConnector):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider="GTCFX", **kwargs)


class FinaltoBrokerConnector(MetaTrader5BrokerConnector):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(provider="Finalto", **kwargs)


__all__ = [
    "AvaTradeBrokerConnector",
    "EcMarketsBrokerConnector",
    "FinaltoBrokerConnector",
    "GtcFxBrokerConnector",
    "MT5_BROKER_PROVIDERS",
    "MetaTrader5BrokerConnector",
    "MetaTrader5ClientFactory",
]
