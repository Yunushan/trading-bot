from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from app.jsonl_rotation import rotate_jsonl_if_needed
from app.security.redaction import redact_text, redact_value
from app.settings.risk import coerce_bool

DEFAULT_ORDER_AUDIT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_ORDER_AUDIT_BACKUP_COUNT = 1
ORDER_AUDIT_LOG_ENV = "BOT_ORDER_AUDIT_LOG"
ORDER_AUDIT_LOG_PATH_ENV = "BOT_ORDER_AUDIT_LOG_PATH"
ORDER_AUDIT_DISABLED_ENV = "BOT_ORDER_AUDIT_DISABLED"

_AUDIT_LOCK = threading.Lock()


def _default_order_audit_path() -> Path:
    return Path.home() / ".trading-bot" / "order_audit.jsonl"


def _configured_audit_path(value: object | None = None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raw = str(os.environ.get(ORDER_AUDIT_LOG_PATH_ENV) or os.environ.get(ORDER_AUDIT_LOG_ENV) or "").strip()
    if not raw:
        return _default_order_audit_path()
    return Path(raw).expanduser()


def _configured_audit_max_bytes(value: object | None = None) -> int:
    try:
        return max(1, int(float(str(value).strip() if isinstance(value, str) else value)))
    except Exception:
        return DEFAULT_ORDER_AUDIT_MAX_BYTES


def _configured_audit_backup_count(value: object | None = None) -> int:
    if value in (None, ""):
        return DEFAULT_ORDER_AUDIT_BACKUP_COUNT
    try:
        return max(0, min(100, int(float(str(value).strip() if isinstance(value, str) else value))))
    except Exception:
        return DEFAULT_ORDER_AUDIT_BACKUP_COUNT


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
    max_bytes: object | None = None,
    backup_count: object | None = None,
) -> None:
    cfg = config if isinstance(config, Mapping) else {}
    env_disabled = coerce_bool(os.environ.get(ORDER_AUDIT_DISABLED_ENV), False)
    if enabled is None:
        enabled = coerce_bool(cfg.get("order_audit_enabled"), True)
    self._order_audit_enabled = bool(enabled) and not env_disabled
    self._order_audit_log_path = _configured_audit_path(path if path is not None else cfg.get("order_audit_log_path"))
    self._order_audit_max_bytes = _configured_audit_max_bytes(
        max_bytes if max_bytes is not None else cfg.get("order_audit_max_bytes")
    )
    self._order_audit_backup_count = _configured_audit_backup_count(
        backup_count if backup_count is not None else cfg.get("order_audit_backup_count")
    )
    self._order_audit_warned = False
    self._order_audit_last_write_error = None
    self._order_audit_last_write_error_at = ""
    self._order_audit_last_write_ok_at = ""


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
            payload["params"] = redact_value(dict(params))
        if computed:
            payload["computed"] = redact_value(dict(computed))
        if result:
            payload["result"] = redact_value(dict(result))
            order_id = _extract_order_id(result)
            if order_id is not None:
                payload["order_id"] = order_id
        if error is not None:
            payload["error"] = redact_text(error)
        if extra:
            payload["extra"] = redact_value(dict(extra))
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        incoming_bytes = len((line + "\n").encode("utf-8"))
        with _AUDIT_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            rotate_jsonl_if_needed(
                path,
                incoming_bytes,
                max_bytes=getattr(self, "_order_audit_max_bytes", DEFAULT_ORDER_AUDIT_MAX_BYTES),
                backup_count=getattr(
                    self,
                    "_order_audit_backup_count",
                    DEFAULT_ORDER_AUDIT_BACKUP_COUNT,
                ),
            )
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        self._order_audit_last_write_error = None
        self._order_audit_last_write_error_at = ""
        self._order_audit_last_write_ok_at = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        self._order_audit_last_write_error = {
            "message": redact_text(str(exc)),
            "path": redact_text(str(path)),
        }
        self._order_audit_last_write_error_at = datetime.now(timezone.utc).isoformat()
        if not getattr(self, "_order_audit_warned", False):
            self._order_audit_warned = True
            try:
                self._log(f"Order audit write failed: {redact_text(str(exc))}", lvl="warn")
            except Exception:
                pass


def get_order_audit_status(self) -> dict[str, object]:
    enabled = bool(getattr(self, "_order_audit_enabled", True))
    path = getattr(self, "_order_audit_log_path", None)
    if path is None:
        path = _configured_audit_path()
    last_error = getattr(self, "_order_audit_last_write_error", None)
    last_error_payload = redact_value(dict(last_error)) if isinstance(last_error, Mapping) else None
    payload = {
        "enabled": enabled,
        "state": "disabled" if not enabled else "write_failed" if last_error_payload else "ready",
        "path": redact_text(str(Path(path).expanduser())),
        "max_bytes": _configured_audit_max_bytes(
            getattr(self, "_order_audit_max_bytes", DEFAULT_ORDER_AUDIT_MAX_BYTES)
        ),
        "backup_count": _configured_audit_backup_count(
            getattr(self, "_order_audit_backup_count", DEFAULT_ORDER_AUDIT_BACKUP_COUNT)
        ),
        "write_ok": not bool(last_error_payload),
        "last_write_error": last_error_payload,
        "last_write_error_at": str(getattr(self, "_order_audit_last_write_error_at", "") or ""),
        "last_write_ok_at": str(getattr(self, "_order_audit_last_write_ok_at", "") or ""),
    }
    return redact_value({key: value for key, value in payload.items() if value not in (None, "", {})})


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
    wrapper_cls.get_order_audit_status = get_order_audit_status
