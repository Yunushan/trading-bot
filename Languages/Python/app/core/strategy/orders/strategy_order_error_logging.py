from __future__ import annotations

from collections.abc import Mapping
import traceback
from typing import Any

from app.security.redaction import REDACTED_TEXT, is_sensitive_key, redact_text


def _safe_repr(value: Any, *, max_len: int = 180, depth: int = 0) -> str:
    if depth > 2:
        return "..."
    if isinstance(value, Mapping):
        items: list[str] = []
        for idx, (key, item_value) in enumerate(value.items()):
            if idx >= 10:
                items.append("...")
                break
            key_text = str(key)
            if is_sensitive_key(key_text):
                rendered = REDACTED_TEXT
            else:
                rendered = _safe_repr(item_value, max_len=80, depth=depth + 1)
            items.append(f"{key_text}: {rendered}")
        text = "{" + ", ".join(items) + "}"
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
        rendered_values = [
            _safe_repr(item_value, max_len=60, depth=depth + 1)
            for item_value in values[:8]
        ]
        if len(values) > 8:
            rendered_values.append("...")
        if isinstance(value, tuple):
            text = "(" + ", ".join(rendered_values) + ")"
        else:
            text = "[" + ", ".join(rendered_values) + "]"
    elif value is None:
        text = "None"
    elif isinstance(value, str):
        text = redact_text(value)
    else:
        try:
            text = redact_text(repr(value))
        except Exception:
            text = f"<{type(value).__name__}>"
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _format_exception(exc: BaseException | None) -> str | None:
    if exc is None:
        return None
    return f"{type(exc).__name__}: {_safe_repr(redact_text(str(exc)), max_len=240)}"


def _format_traceback(exc: BaseException | None) -> str | None:
    if exc is None or exc.__traceback__ is None:
        return None
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    compact = " | ".join(line.strip() for line in lines if line.strip())
    return _safe_repr(redact_text(compact), max_len=1200)


def build_order_error_context(
    strategy,
    *,
    cw: Mapping[str, Any] | None = None,
    side: str | None = None,
    account_type: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cw_map = cw if isinstance(cw, Mapping) else {}
    wrapper = getattr(strategy, "binance", None)
    config = getattr(strategy, "config", {}) or {}
    if not isinstance(config, Mapping):
        config = {}

    resolved_account_type = (
        account_type
        or cw_map.get("account_type")
        or config.get("account_type")
        or getattr(wrapper, "account_type", None)
    )
    context: dict[str, Any] = {
        "symbol": str(cw_map.get("symbol") or config.get("symbol") or "").upper(),
        "interval": cw_map.get("interval") or config.get("interval"),
        "account_type": str(resolved_account_type or "").upper(),
        "side": str(side or "").upper(),
        "backend": getattr(wrapper, "_connector_backend", None),
        "mode": getattr(wrapper, "mode", None),
    }
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            context[str(key)] = value
    return {key: value for key, value in context.items() if value not in (None, "", [], {}, ())}


def _format_context(context: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key, value in context.items():
        if is_sensitive_key(key):
            rendered = REDACTED_TEXT
        else:
            rendered = _safe_repr(value)
        parts.append(f"{key}={rendered}")
    return " ".join(parts)


def safe_strategy_log(strategy, message: str, *, level: str = "error") -> None:
    log_fn = getattr(strategy, "log", None)
    if not callable(log_fn):
        return
    try:
        log_fn(message, lvl=level)
        return
    except TypeError:
        pass
    except Exception:
        return
    try:
        log_fn(message)
    except Exception:
        pass


def log_order_error(
    strategy,
    message: str,
    *,
    cw: Mapping[str, Any] | None = None,
    side: str | None = None,
    account_type: str | None = None,
    exc: BaseException | None = None,
    extra: Mapping[str, Any] | None = None,
    level: str = "error",
    include_traceback: bool = False,
) -> None:
    context = build_order_error_context(
        strategy,
        cw=cw,
        side=side,
        account_type=account_type,
        extra=extra,
    )
    exc_text = _format_exception(exc)
    if exc_text:
        context["exception"] = exc_text
    if include_traceback:
        tb_text = _format_traceback(exc)
        if tb_text:
            context["traceback"] = tb_text
    detail = _format_context(context)
    safe_strategy_log(strategy, f"{message} | {detail}" if detail else message, level=level)
