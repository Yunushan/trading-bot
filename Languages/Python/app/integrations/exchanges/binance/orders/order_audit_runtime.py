from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from app.settings.risk import coerce_bool

ORDER_AUDIT_LOG_ENV = "BOT_ORDER_AUDIT_LOG"
ORDER_AUDIT_LOG_PATH_ENV = "BOT_ORDER_AUDIT_LOG_PATH"
ORDER_AUDIT_DISABLED_ENV = "BOT_ORDER_AUDIT_DISABLED"

_AUDIT_LOCK = threading.Lock()
_SENSITIVE_KEY_PARTS = ("api", "secret", "signature", "token", "authorization", "x-mbx-apikey")


def _default_order_audit_path() -> Path:
    return Path.home() / ".trading-bot" / "order_audit.jsonl"


def _configured_audit_path(value: object | None = None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raw = str(os.environ.get(ORDER_AUDIT_LOG_PATH_ENV) or os.environ.get(ORDER_AUDIT_LOG_ENV) or "").strip()
    if not raw:
        return _default_order_audit_path()
    return Path(raw).expanduser()


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if any(part in key_lower for part in _SENSITIVE_KEY_PARTS):
                out[key_text] = "<redacted>"
            else:
                out[key_text] = _sanitize(item)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _extract_order_id(payload: Any) -> Any:
    if not isinstance(payload, Mapping):
        return None
    info = payload.get("info")
    candidates = payload
    if isinstance(info, Mapping):
        candidates = info
    for key in ("orderId", "order_id", "id", "clientOrderId", "client_order_id", "clientOrderID"):
        value = candidates.get(key)
        if value not in (None, ""):
            return value
    return None


def _configure_order_audit(
    self,
    *,
    config: Mapping[str, object] | None = None,
    path: object | None = None,
    enabled: bool | None = None,
) -> None:
    cfg = config if isinstance(config, Mapping) else {}
    env_disabled = coerce_bool(os.environ.get(ORDER_AUDIT_DISABLED_ENV), False)
    if enabled is None:
        enabled = coerce_bool(cfg.get("order_audit_enabled"), True)
    self._order_audit_enabled = bool(enabled) and not env_disabled
    self._order_audit_log_path = _configured_audit_path(path if path is not None else cfg.get("order_audit_log_path"))
    self._order_audit_warned = False


def _audit_order_event(
    self,
    event: str,
    *,
    symbol: object | None = None,
    side: object | None = None,
    market: object | None = None,
    params: Mapping[str, object] | None = None,
    result: Mapping[str, object] | None = None,
    error: object | None = None,
    source: object | None = None,
    via: object | None = None,
    computed: Mapping[str, object] | None = None,
    extra: Mapping[str, object] | None = None,
) -> None:
    if not bool(getattr(self, "_order_audit_enabled", True)):
        return
    path = getattr(self, "_order_audit_log_path", None)
    if path is None:
        path = _configured_audit_path()
    try:
        path = Path(path).expanduser()
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": str(event or "order_event"),
            "mode": str(getattr(self, "mode", "") or ""),
            "account_type": str(getattr(self, "account_type", "") or ""),
            "connector_backend": str(getattr(self, "_connector_backend", "") or ""),
        }
        if symbol is not None:
            payload["symbol"] = str(symbol or "").upper()
        if side is not None:
            payload["side"] = str(side or "").upper()
        if market is not None:
            payload["market"] = str(market or "")
        if via is not None:
            payload["via"] = str(via or "")
        if source is not None:
            payload["source"] = str(source or "")
        if params:
            payload["params"] = _sanitize(dict(params))
        if computed:
            payload["computed"] = _sanitize(dict(computed))
        if result:
            payload["result"] = _sanitize(dict(result))
            order_id = _extract_order_id(result)
            if order_id is not None:
                payload["order_id"] = order_id
        if error is not None:
            payload["error"] = str(error)
        if extra:
            payload["extra"] = _sanitize(dict(extra))
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        with _AUDIT_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as exc:
        if not getattr(self, "_order_audit_warned", False):
            self._order_audit_warned = True
            try:
                self._log(f"Order audit write failed: {exc}", lvl="warn")
            except Exception:
                pass


def _extract_symbol_side(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> tuple[Any, Any]:
    symbol = kwargs.get("symbol")
    side = kwargs.get("side")
    if symbol is None and len(args) >= 1:
        symbol = args[0]
    if side is None and len(args) >= 2:
        side = args[1]
    return symbol, side


def audit_order_method(method: Callable, *, market: str) -> Callable:
    @wraps(method)
    def _wrapped(self, *args, **kwargs):
        symbol, side = _extract_symbol_side(args, kwargs)
        audit = getattr(self, "_audit_order_event", None)
        if callable(audit):
            audit(
                "order_intent",
                symbol=symbol,
                side=side,
                market=market,
                source=getattr(method, "__name__", "order_method"),
                params={"args": args[2:] if len(args) > 2 else [], "kwargs": kwargs},
            )
        try:
            result = method(self, *args, **kwargs)
        except Exception as exc:
            if callable(audit):
                audit(
                    "order_error",
                    symbol=symbol,
                    side=side,
                    market=market,
                    source=getattr(method, "__name__", "order_method"),
                    error=exc,
                )
            raise
        if callable(audit):
            result_map = result if isinstance(result, Mapping) else {"value": result}
            ok = bool(result_map.get("ok", True))
            audit(
                "order_accepted" if ok else "order_rejected",
                symbol=result_map.get("symbol", symbol),
                side=side,
                market=market,
                source=getattr(method, "__name__", "order_method"),
                result=result_map,
                error=result_map.get("error") if not ok else None,
                computed=result_map.get("computed") if isinstance(result_map.get("computed"), Mapping) else None,
                via=result_map.get("via"),
            )
            fills = result_map.get("fills")
            if ok and isinstance(fills, Mapping) and fills:
                audit(
                    "order_fills",
                    symbol=result_map.get("symbol", symbol),
                    side=side,
                    market=market,
                    source=getattr(method, "__name__", "order_method"),
                    result={"fills": fills, "order_id": _extract_order_id(result_map)},
                )
        return result

    return _wrapped


def bind_binance_order_audit_runtime(wrapper_cls) -> None:
    wrapper_cls._configure_order_audit = _configure_order_audit
    wrapper_cls._audit_order_event = _audit_order_event
