from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from trading_core.orders import order_submit_intent_from_params, validate_order_submit_intent

from app.native_parity import ORDER_GUARD_BEHAVIOR
from app.settings.live_safety import (
    LiveTradingSafetyError,
    is_live_trading_mode,
    resolve_live_session_order_cap,
    validate_live_trading_safety,
)


def _int_value(value: object, default: int = 1) -> int:
    try:
        return int(float(value))
    except (OverflowError, TypeError, ValueError):
        return int(default)


def _decimal_value(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _positive_filter(value: object) -> Decimal:
    parsed = _decimal_value(value)
    return parsed if parsed is not None and parsed > 0 else Decimal("0")


def _aligned_to_step(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return True
    try:
        return value.remainder_near(step) == 0 or value % step == 0
    except (InvalidOperation, ZeroDivisionError):
        return False


def _truthy_param(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _guard_config(self) -> Mapping[str, object]:
    config = getattr(self, "_live_safety_config", None)
    return config if isinstance(config, Mapping) else {}


def _live_submit_attempt_count(self) -> int:
    return max(0, _int_value(getattr(self, "_live_order_submit_attempt_count", 0), 0))


def _policy_applies_to_mode(rule: str, *, live_mode: bool) -> bool:
    return live_mode or bool(ORDER_GUARD_BEHAVIOR.get(rule, False))


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


def _order_filter_errors(self, market_text: str, order_params: Mapping[str, Any]) -> list[str]:
    symbol = str(order_params.get("symbol") or "").strip().upper()
    if not symbol:
        return []

    if market_text == "spot":
        getter = getattr(self, "get_spot_symbol_filters", None)
    elif market_text == "futures":
        getter = getattr(self, "get_futures_symbol_filters", None)
    else:
        return []
    if not callable(getter):
        return [f"{market_text} symbol filters unavailable for {symbol}"]

    try:
        filters = getter(symbol) or {}
    except Exception as exc:
        return [f"{market_text} symbol filters unavailable for {symbol}: {exc}"]
    if not isinstance(filters, Mapping):
        return [f"{market_text} symbol filters invalid for {symbol}"]

    raw_quantity = order_params.get("quantity")
    quantity = _decimal_value(raw_quantity)
    if quantity is None:
        if raw_quantity not in (None, ""):
            return [f"order quantity must be a finite number for {symbol}"]
        return []

    errors: list[str] = []
    filter_values: dict[str, Decimal] = {}
    for name in ("stepSize", "minQty", "minNotional", "tickSize"):
        raw_value = filters.get(name)
        parsed = _decimal_value(raw_value)
        if raw_value not in (None, "") and parsed is None:
            errors.append(f"{symbol} {name} must be a finite number")
        filter_values[name] = parsed if parsed is not None and parsed > 0 else Decimal("0")
    step_size = filter_values["stepSize"]
    min_qty = filter_values["minQty"]
    min_notional = filter_values["minNotional"]
    tick_size = filter_values["tickSize"]
    is_risk_reducing_exit = market_text == "futures" and (
        _truthy_param(order_params.get("reduceOnly")) or _truthy_param(order_params.get("closePosition"))
    )

    if min_qty > 0 and quantity < min_qty and not is_risk_reducing_exit:
        errors.append(f"order quantity {quantity} is below {symbol} minQty {min_qty}")
    if step_size > 0 and not _aligned_to_step(quantity, step_size):
        errors.append(f"order quantity {quantity} is not aligned to {symbol} stepSize {step_size}")

    raw_price = order_params.get("price")
    price = _decimal_value(raw_price)
    if raw_price not in (None, "") and price is None:
        errors.append(f"order price must be a finite number for {symbol}")
    if price is None:
        last_price = getattr(self, "get_last_price", None)
        if callable(last_price):
            try:
                price = _decimal_value(last_price(symbol))
            except Exception:
                price = None
    if tick_size > 0 and price is not None and price > 0 and not _aligned_to_step(price, tick_size):
        errors.append(f"order price {price} is not aligned to {symbol} tickSize {tick_size}")
    if min_notional > 0 and not is_risk_reducing_exit:
        if price is None or price <= 0:
            errors.append(f"last price unavailable for {symbol} minNotional validation")
        elif quantity * price < min_notional:
            errors.append(f"order notional {quantity * price} is below {symbol} minNotional {min_notional}")

    return errors


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
    """Validate every exchange order; apply credential/session gates only in live mode."""
    mode = getattr(self, "mode", "")
    live_mode = is_live_trading_mode(mode)

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
    if live_mode:
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

    if _policy_applies_to_mode("validate_audit_enabled_all_modes", live_mode=live_mode):
        if not bool(getattr(self, "_order_audit_enabled", True)):
            errors.append("order audit is disabled")
    if _policy_applies_to_mode("validate_audit_writable_all_modes", live_mode=live_mode):
        if getattr(self, "_order_audit_last_write_error", None):
            errors.append("order audit is not writable")

    if _policy_applies_to_mode("validate_connector_health_all_modes", live_mode=live_mode):
        errors.extend(_order_health_errors(self))
    intent = order_submit_intent_from_params(market_text, order_params)
    if _policy_applies_to_mode("validate_intent_all_modes", live_mode=live_mode):
        errors.extend(validate_order_submit_intent(intent))
    if _policy_applies_to_mode("validate_exchange_filters_all_modes", live_mode=live_mode):
        errors.extend(_order_filter_errors(self, market_text, order_params))
    submit_attempt_count = _live_submit_attempt_count(self)
    if live_mode:
        max_session_orders = resolve_live_session_order_cap(cfg)
        if submit_attempt_count >= max_session_orders:
            errors.append(f"live session order cap {max_session_orders} reached")

    if not errors:
        if live_mode:
            setattr(self, "_live_order_submit_attempt_count", submit_attempt_count + 1)
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
    label = "Live order" if live_mode else "Order"
    raise LiveTradingSafetyError(f"{label} submit blocked by {source}: {'; '.join(errors)}.")


def bind_binance_order_submit_guard_runtime(wrapper_cls) -> None:
    wrapper_cls._guard_live_order_submit = _guard_live_order_submit
