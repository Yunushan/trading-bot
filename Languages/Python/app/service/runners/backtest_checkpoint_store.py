"""Durable, credential-free checkpoints for time-bounded optimizer runs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from ...core.backtest.models import BacktestRequest, IndicatorDefinition, PairOverride

BACKTEST_CHECKPOINT_FILE_KIND = "trading-bot-backtest-checkpoint"
BACKTEST_CHECKPOINT_FORMAT_VERSION = 1


def resolve_backtest_checkpoint_path(snapshot_path: str | Path) -> Path:
    path = Path(snapshot_path).expanduser().resolve()
    return path.with_name(f"{path.stem}.checkpoint.json")


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _pair_override_payload(value: object) -> dict[str, object]:
    if isinstance(value, PairOverride):
        return {
            "symbol": value.symbol,
            "interval": value.interval,
            "indicators": list(value.indicators or []),
            "leverage": value.leverage,
            "strategy_controls": _json_value(value.strategy_controls or {}),
        }
    if isinstance(value, Mapping):
        return {
            "symbol": str(value.get("symbol") or ""),
            "interval": str(value.get("interval") or ""),
            "indicators": _json_value(value.get("indicators") or []),
            "leverage": value.get("leverage"),
            "strategy_controls": _json_value(value.get("strategy_controls") or {}),
        }
    return {}


def serialize_backtest_request(request: BacktestRequest) -> dict[str, object]:
    return {
        "symbols": list(request.symbols),
        "intervals": list(request.intervals),
        "indicators": [
            {"key": indicator.key, "params": _json_value(indicator.params)}
            for indicator in request.indicators
        ],
        "logic": request.logic,
        "symbol_source": request.symbol_source,
        "start": _iso(request.start),
        "end": _iso(request.end),
        "capital": request.capital,
        "side": request.side,
        "position_pct": request.position_pct,
        "position_pct_units": request.position_pct_units,
        "leverage": request.leverage,
        "margin_mode": request.margin_mode,
        "position_mode": request.position_mode,
        "assets_mode": request.assets_mode,
        "account_mode": request.account_mode,
        "mdd_logic": request.mdd_logic,
        "stop_loss_enabled": request.stop_loss_enabled,
        "stop_loss_mode": request.stop_loss_mode,
        "stop_loss_usdt": request.stop_loss_usdt,
        "stop_loss_percent": request.stop_loss_percent,
        "stop_loss_scope": request.stop_loss_scope,
        "fee_bps": request.fee_bps,
        "slippage_bps": request.slippage_bps,
        "pair_overrides": [_pair_override_payload(item) for item in (request.pair_overrides or [])],
        "optimizer_max_duration_seconds": request.optimizer_max_duration_seconds,
        "optimizer_result_limit": getattr(request, "optimizer_result_limit", 0),
        "optimizer_metric": getattr(request, "optimizer_metric", "roi_percent"),
        "optimizer_mdd_limit": getattr(request, "optimizer_mdd_limit", 0.0),
        "optimizer_min_trades": getattr(request, "optimizer_min_trades", 0),
        "optimizer_mode": getattr(request, "optimizer_mode", ""),
        "optimizer_scope": getattr(request, "optimizer_scope", ""),
        "optimizer_run_count": getattr(request, "optimizer_run_count", 0),
    }


def _parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value or ""))
    return parsed


def deserialize_backtest_request(payload: Mapping[str, object]) -> BacktestRequest:
    indicators = [
        IndicatorDefinition(key=str(item.get("key") or ""), params=dict(item.get("params") or {}))
        for item in payload.get("indicators", [])
        if isinstance(item, Mapping) and str(item.get("key") or "").strip()
    ]
    overrides = [
        PairOverride(
            symbol=str(item.get("symbol") or "").strip().upper(),
            interval=str(item.get("interval") or "").strip(),
            indicators=[str(key) for key in item.get("indicators", []) if str(key).strip()] or None,
            leverage=int(item["leverage"]) if item.get("leverage") not in (None, "") else None,
            strategy_controls=dict(item.get("strategy_controls") or {}) or None,
        )
        for item in payload.get("pair_overrides", [])
        if isinstance(item, Mapping) and str(item.get("symbol") or "").strip() and str(item.get("interval") or "").strip()
    ]
    request = BacktestRequest(
        symbols=[str(item) for item in payload.get("symbols", []) if str(item).strip()],
        intervals=[str(item) for item in payload.get("intervals", []) if str(item).strip()],
        indicators=indicators,
        logic=str(payload.get("logic") or "AND"),
        symbol_source=str(payload.get("symbol_source") or "Futures"),
        start=_parse_datetime(payload.get("start")),
        end=_parse_datetime(payload.get("end")),
        capital=float(payload.get("capital") or 0.0),
        side=str(payload.get("side") or "BOTH"),
        position_pct=float(payload.get("position_pct") or 1.0),
        position_pct_units=str(payload.get("position_pct_units") or ""),
        leverage=float(payload.get("leverage") or 1.0),
        margin_mode=str(payload.get("margin_mode") or "Isolated"),
        position_mode=str(payload.get("position_mode") or "Hedge"),
        assets_mode=str(payload.get("assets_mode") or "Single-Asset"),
        account_mode=str(payload.get("account_mode") or "Classic Trading"),
        mdd_logic=str(payload.get("mdd_logic") or "Per Trade MDD"),
        stop_loss_enabled=bool(payload.get("stop_loss_enabled")),
        stop_loss_mode=str(payload.get("stop_loss_mode") or "usdt"),
        stop_loss_usdt=float(payload.get("stop_loss_usdt") or 0.0),
        stop_loss_percent=float(payload.get("stop_loss_percent") or 0.0),
        stop_loss_scope=str(payload.get("stop_loss_scope") or "per_trade"),
        fee_bps=float(payload.get("fee_bps") or 0.0),
        slippage_bps=float(payload.get("slippage_bps") or 0.0),
        pair_overrides=overrides or None,
        optimizer_max_duration_seconds=int(payload.get("optimizer_max_duration_seconds") or 0),
    )
    for key in (
        "optimizer_result_limit",
        "optimizer_metric",
        "optimizer_mdd_limit",
        "optimizer_min_trades",
        "optimizer_mode",
        "optimizer_scope",
        "optimizer_run_count",
    ):
        setattr(request, key, payload.get(key))
    return request


def write_backtest_checkpoint_file(
    *,
    path: str | Path,
    session_id: str,
    request: BacktestRequest,
    wrapper_options: Mapping[str, object],
    summary: Mapping[str, object],
    completed_combo_count: int,
    previous_runs: list[Mapping[str, object]],
    previous_errors: list[Mapping[str, object]],
) -> dict[str, object]:
    resolved = Path(path).expanduser().resolve()
    payload = {
        "kind": BACKTEST_CHECKPOINT_FILE_KIND,
        "format_version": BACKTEST_CHECKPOINT_FORMAT_VERSION,
        "session_id": str(session_id),
        "request": serialize_backtest_request(request),
        "wrapper_options": {
            key: _json_value(value)
            for key, value in wrapper_options.items()
            if key not in {"api_key", "api_secret", "token", "password"}
        },
        "summary": _json_value(summary),
        "completed_combo_count": max(0, int(completed_combo_count or 0)),
        "previous_runs": _json_value(previous_runs),
        "previous_errors": _json_value(previous_errors),
    }
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(resolved)
    try:
        directory_fd = os.open(resolved.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        # Windows and some network filesystems do not support directory fsync.
        pass
    try:
        os.chmod(resolved, 0o600)
    except OSError:
        pass
    return {"path": str(resolved), "completed_combo_count": payload["completed_combo_count"]}


def load_backtest_checkpoint_file(path: str | Path) -> dict[str, object] | None:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        return None
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") != BACKTEST_CHECKPOINT_FILE_KIND:
        return None
    if int(payload.get("format_version") or 0) != BACKTEST_CHECKPOINT_FORMAT_VERSION:
        return None
    if not isinstance(payload.get("request"), Mapping) or not isinstance(payload.get("summary"), Mapping):
        return None
    return payload


def delete_backtest_checkpoint_file(path: str | Path) -> None:
    try:
        Path(path).expanduser().resolve().unlink(missing_ok=True)
    except OSError:
        pass
