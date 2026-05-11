from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trading_core.orders import order_submit_intent_from_params, validate_order_submit_intent

from app.settings.live_safety import (
    LiveTradingSafetyError,
    is_live_trading_mode,
    validate_live_trading_safety,
)


def _int_value(value: object, default: int = 1) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _guard_config(self) -> Mapping[str, object]:
    config = getattr(self, "_live_safety_config", None)
    return config if isinstance(config, Mapping) else {}


def _order_health_errors(self) -> list[str]:
    getter = getattr(self, "get_connector_health_snapshot", None)
    if not callable(getter):
        return []
    try:
        snapshot = getter()
    except Exception as exc:
        return [f"connector health snapshot unavailable: {exc}"]
    if not isinstance(snapshot, Mapping):
        return []
    state = str(snapshot.get("state") or "").strip().lower()
    health = str(snapshot.get("health") or "").strip().lower()
    if state and state != "ready":
        return [f"connector health is {health or 'unknown'} / {state}"]
    if health and health not in {"ok", "unknown"}:
        return [f"connector health is {health}"]
    return []


def _guard_live_order_submit(
    self,
    *,
    market: str,
    params: Mapping[str, Any] | None = None,
    source: str = "order_submit",
    leverage: object | None = None,
    margin_mode: object | None = None,
    position_pct: object | None = None,
) -> None:
    """Fail closed immediately before a live exchange order is submitted."""
    mode = getattr(self, "mode", "")
    if not is_live_trading_mode(mode):
        return

    cfg = _guard_config(self)
    market_text = str(market or "").strip().lower()
    order_params: Mapping[str, Any] = params if isinstance(params, Mapping) else {}
    account_type = "FUTURES" if market_text == "futures" else "SPOT"
    leverage_value = leverage
    if leverage_value is None:
        leverage_value = order_params.get("leverage")
    if leverage_value is None:
        leverage_value = getattr(self, "_default_leverage", getattr(self, "futures_leverage", 1))
    margin_value = margin_mode
    if margin_value is None:
        margin_value = order_params.get("margin_mode") or order_params.get("marginMode")
    if margin_value is None:
        margin_value = getattr(self, "_default_margin_mode", None)

    pct_value = position_pct
    if pct_value is None:
        pct_value = cfg.get("position_pct")

    errors: list[str] = []
    try:
        validate_live_trading_safety(
            mode=mode,
            api_key=getattr(self, "api_key", ""),
            api_secret=getattr(self, "api_secret", ""),
            account_type=account_type,
            leverage=_int_value(leverage_value, 1),
            margin_mode=margin_value,
            position_pct=pct_value,
            config=cfg,
        )
    except LiveTradingSafetyError as exc:
        errors.append(str(exc))

    if not bool(getattr(self, "_order_audit_enabled", True)):
        errors.append("order audit is disabled")
    if getattr(self, "_order_audit_last_write_error", None):
        errors.append("order audit is not writable")

    errors.extend(_order_health_errors(self))
    intent = order_submit_intent_from_params(market_text, order_params)
    errors.extend(validate_order_submit_intent(intent))

    if not errors:
        return

    audit = getattr(self, "_audit_order_event", None)
    if callable(audit):
        try:
            audit(
                "live_order_blocked",
                symbol=order_params.get("symbol"),
                side=order_params.get("side"),
                market=market_text or account_type.lower(),
                params=order_params,
                error="; ".join(errors),
                source=source,
            )
        except Exception as exc:
            logger = getattr(self, "_log", None)
            if callable(logger):
                logger(f"Live order block audit write failed: {exc}", lvl="error")
    raise LiveTradingSafetyError(f"Live order submit blocked by {source}: {'; '.join(errors)}.")


def bind_binance_order_submit_guard_runtime(wrapper_cls) -> None:
    wrapper_cls._guard_live_order_submit = _guard_live_order_submit
