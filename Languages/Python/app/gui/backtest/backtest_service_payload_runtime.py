from __future__ import annotations

import copy
from datetime import datetime

from app.core.backtest import BacktestRequest, IndicatorDefinition, PairOverride


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _datetime_payload(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _clean_text(value)


def _read_field(value: object, field_name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def _put_if_present(payload: dict[str, object], key: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    payload[key] = copy.deepcopy(value)


def _indicator_payload(indicator: IndicatorDefinition | dict) -> dict[str, object] | None:
    if isinstance(indicator, dict):
        key = _clean_text(indicator.get("key")).lower()
        params = indicator.get("params")
    else:
        key = _clean_text(indicator.key).lower()
        params = indicator.params
    if not key:
        return None
    return {
        "key": key,
        "params": copy.deepcopy(params) if isinstance(params, dict) else {},
    }


def _pair_override_payload(pair_override: PairOverride | dict) -> dict[str, object] | None:
    symbol = _clean_text(_read_field(pair_override, "symbol")).upper()
    interval = _clean_text(_read_field(pair_override, "interval"))
    if not symbol or not interval:
        return None
    payload: dict[str, object] = {
        "symbol": symbol,
        "interval": interval,
    }
    indicators = _read_field(pair_override, "indicators")
    if isinstance(indicators, (list, tuple)):
        indicator_values = [_clean_text(item).lower() for item in indicators if _clean_text(item)]
        if indicator_values:
            payload["indicators"] = indicator_values
    strategy_controls = _read_field(pair_override, "strategy_controls")
    if isinstance(strategy_controls, dict) and strategy_controls:
        payload["strategy_controls"] = copy.deepcopy(strategy_controls)
    for field_name in (
        "logic",
        "capital",
        "side",
        "position_pct",
        "position_pct_units",
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
        "mdd_logic",
        "leverage",
        "stop_loss_enabled",
        "stop_loss_mode",
        "stop_loss_usdt",
        "stop_loss_percent",
        "stop_loss_scope",
    ):
        _put_if_present(payload, field_name, _read_field(pair_override, field_name))
    stop_loss = _read_field(pair_override, "stop_loss")
    if isinstance(stop_loss, dict):
        payload["stop_loss"] = copy.deepcopy(stop_loss)
    return payload


def _pair_override_payloads(pair_overrides: object) -> list[dict[str, object]]:
    if not isinstance(pair_overrides, (list, tuple)):
        return []
    payloads: list[dict[str, object]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for item in pair_overrides:
        if not isinstance(item, (dict, PairOverride)):
            continue
        payload = _pair_override_payload(item)
        if not payload:
            continue
        indicator_key = tuple(sorted(str(key) for key in payload.get("indicators", []) or []))
        dedupe_key = (str(payload["symbol"]), str(payload["interval"]), indicator_key)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        payloads.append(payload)
    return payloads


def build_service_backtest_request_payload(
    request: BacktestRequest,
    *,
    api_key: str = "",
    api_secret: str = "",
    mode: str = "",
    account_type: str = "",
    connector_backend: str | None = None,
    optimizer_mode: str | None = None,
    optimizer_metric: str | None = None,
    optimizer_combo_size: int | None = None,
    optimizer_min_trades: int | None = None,
    optimizer_max_duration_seconds: int | None = None,
    scan_scope: str | None = None,
    scan_top_n: int | None = None,
    scan_mdd_limit: float | None = None,
    include_pair_overrides: bool = True,
) -> dict[str, object]:
    if not isinstance(request, BacktestRequest):
        raise TypeError("Expected a BacktestRequest.")

    indicators: list[dict[str, object]] = []
    for indicator in request.indicators or []:
        payload = _indicator_payload(indicator)
        if payload:
            indicators.append(payload)

    payload: dict[str, object] = {
        "symbols": list(request.symbols or []),
        "intervals": list(request.intervals or []),
        "indicators": indicators,
        "logic": _clean_text(request.logic) or "AND",
        "symbol_source": _clean_text(request.symbol_source) or "Futures",
        "start": _datetime_payload(request.start),
        "end": _datetime_payload(request.end),
        "capital": float(request.capital),
        "side": _clean_text(request.side) or "BOTH",
        "position_pct": float(request.position_pct),
        "position_pct_units": _clean_text(request.position_pct_units) or "percent",
        "leverage": float(request.leverage),
        "margin_mode": _clean_text(request.margin_mode) or "Isolated",
        "position_mode": _clean_text(request.position_mode) or "Hedge",
        "assets_mode": _clean_text(request.assets_mode) or "Single-Asset",
        "account_mode": _clean_text(request.account_mode) or "Classic Trading",
        "mdd_logic": _clean_text(request.mdd_logic),
        "fee_bps": float(request.fee_bps or 0.0),
        "slippage_bps": float(request.slippage_bps or 0.0),
        "stop_loss": {
            "enabled": bool(request.stop_loss_enabled),
            "mode": _clean_text(request.stop_loss_mode) or "usdt",
            "usdt": float(request.stop_loss_usdt or 0.0),
            "percent": float(request.stop_loss_percent or 0.0),
            "scope": _clean_text(request.stop_loss_scope) or "per_trade",
        },
    }

    if include_pair_overrides:
        pair_overrides = _pair_override_payloads(request.pair_overrides)
        if pair_overrides:
            payload["pair_overrides"] = pair_overrides

    for key, value in (
        ("api_key", api_key),
        ("api_secret", api_secret),
        ("mode", mode),
        ("account_type", account_type),
        ("connector_backend", connector_backend),
        ("optimizer_mode", optimizer_mode),
        ("optimizer_metric", optimizer_metric),
        ("optimizer_combo_size", optimizer_combo_size),
        ("optimizer_min_trades", optimizer_min_trades),
        ("optimizer_max_duration_seconds", optimizer_max_duration_seconds),
        ("scan_scope", scan_scope),
        ("scan_top_n", scan_top_n),
        ("scan_mdd_limit", scan_mdd_limit),
    ):
        _put_if_present(payload, key, value)
    return payload


__all__ = ["build_service_backtest_request_payload"]
