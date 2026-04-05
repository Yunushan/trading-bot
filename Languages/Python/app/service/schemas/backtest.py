"""
Backtest schemas for the service facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...core.backtest import normalize_backtest_interval, normalize_backtest_intervals


def _clean_text(value, default: str = "") -> str:  # noqa: ANN001
    text = str(value or "").strip()
    return text or default


def _coerce_float(value, default: float = 0.0) -> float:  # noqa: ANN001
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_int(value, default: int = 0) -> int:  # noqa: ANN001
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_iso(value) -> str:  # noqa: ANN001
    if isinstance(value, datetime):
        return value.isoformat()
    return _clean_text(value)


def _normalize_string_tuple(value) -> tuple[str, ...]:  # noqa: ANN001
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            items.append(text)
    return tuple(items)


def _normalize_interval_text(value) -> str:  # noqa: ANN001
    return normalize_backtest_interval(_clean_text(value))


def _normalize_interval_tuple(value) -> tuple[str, ...]:  # noqa: ANN001
    return tuple(normalize_backtest_intervals(value))


@dataclass(frozen=True, slots=True)
class ServiceBacktestRunRecord:
    symbol: str
    interval: str
    indicator_keys: tuple[str, ...]
    trades: int
    roi_value: float
    roi_percent: float
    final_equity: float
    max_drawdown_value: float
    max_drawdown_percent: float
    leverage: float
    logic: str
    mdd_logic: str
    start: str
    end: str

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "indicator_keys": list(self.indicator_keys),
            "trades": self.trades,
            "roi_value": self.roi_value,
            "roi_percent": self.roi_percent,
            "final_equity": self.final_equity,
            "max_drawdown_value": self.max_drawdown_value,
            "max_drawdown_percent": self.max_drawdown_percent,
            "leverage": self.leverage,
            "logic": self.logic,
            "mdd_logic": self.mdd_logic,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True, slots=True)
class ServiceBacktestErrorRecord:
    symbol: str
    interval: str
    error: str

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ServiceBacktestCommandResult:
    accepted: bool
    action: str
    session_id: str
    state: str
    status_message: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "action": self.action,
            "session_id": self.session_id,
            "state": self.state,
            "status_message": self.status_message,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ServiceBacktestSnapshot:
    session_id: str
    state: str
    workload_kind: str
    status_message: str
    symbols: tuple[str, ...] = field(default_factory=tuple)
    intervals: tuple[str, ...] = field(default_factory=tuple)
    indicator_keys: tuple[str, ...] = field(default_factory=tuple)
    logic: str = ""
    symbol_source: str = ""
    capital: float = 0.0
    run_count: int = 0
    error_count: int = 0
    cancelled: bool = False
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""
    source: str = "service"
    top_run: ServiceBacktestRunRecord | None = None
    top_runs: tuple[ServiceBacktestRunRecord, ...] = field(default_factory=tuple)
    errors: tuple[ServiceBacktestErrorRecord, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "workload_kind": self.workload_kind,
            "status_message": self.status_message,
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "indicator_keys": list(self.indicator_keys),
            "logic": self.logic,
            "symbol_source": self.symbol_source,
            "capital": self.capital,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "cancelled": self.cancelled,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "updated_at": self.updated_at,
            "source": self.source,
            "top_run": self.top_run.to_dict() if self.top_run else None,
            "top_runs": [item.to_dict() for item in self.top_runs],
            "errors": [item.to_dict() for item in self.errors],
        }


def build_backtest_run_record(run) -> ServiceBacktestRunRecord:  # noqa: ANN001
    indicator_keys = getattr(run, "indicator_keys", ())
    return ServiceBacktestRunRecord(
        symbol=_clean_text(getattr(run, "symbol", "")),
        interval=_normalize_interval_text(getattr(run, "interval", "")),
        indicator_keys=_normalize_string_tuple(indicator_keys),
        trades=max(0, _coerce_int(getattr(run, "trades", 0), 0)),
        roi_value=_coerce_float(getattr(run, "roi_value", 0.0), 0.0),
        roi_percent=_coerce_float(getattr(run, "roi_percent", 0.0), 0.0),
        final_equity=_coerce_float(getattr(run, "final_equity", 0.0), 0.0),
        max_drawdown_value=_coerce_float(getattr(run, "max_drawdown_value", 0.0), 0.0),
        max_drawdown_percent=_coerce_float(getattr(run, "max_drawdown_percent", 0.0), 0.0),
        leverage=_coerce_float(getattr(run, "leverage", 0.0), 0.0),
        logic=_clean_text(getattr(run, "logic", "")),
        mdd_logic=_clean_text(getattr(run, "mdd_logic", "")),
        start=_normalize_iso(getattr(run, "start", "")),
        end=_normalize_iso(getattr(run, "end", "")),
    )


def build_backtest_error_record(error) -> ServiceBacktestErrorRecord:  # noqa: ANN001
    payload = error if isinstance(error, dict) else {}
    return ServiceBacktestErrorRecord(
        symbol=_clean_text(payload.get("symbol")),
        interval=_normalize_interval_text(payload.get("interval")),
        error=_clean_text(payload.get("error"), "Unknown backtest error."),
    )


def build_backtest_snapshot(
    *,
    session_id: str = "",
    state: str = "idle",
    workload_kind: str = "backtest-run",
    status_message: str = "No backtest submitted yet.",
    symbols=None,  # noqa: ANN001
    intervals=None,  # noqa: ANN001
    indicator_keys=None,  # noqa: ANN001
    logic: str = "",
    symbol_source: str = "",
    capital=0.0,  # noqa: ANN001
    run_count=0,  # noqa: ANN001
    error_count=0,  # noqa: ANN001
    cancelled=False,  # noqa: ANN001
    started_at="",  # noqa: ANN001
    completed_at="",  # noqa: ANN001
    updated_at="",  # noqa: ANN001
    source: str = "service",
    top_run: ServiceBacktestRunRecord | None = None,
    top_runs=None,  # noqa: ANN001
    errors=None,  # noqa: ANN001
) -> ServiceBacktestSnapshot:
    normalized_runs: list[ServiceBacktestRunRecord] = []
    if isinstance(top_runs, (list, tuple)):
        for item in top_runs:
            if isinstance(item, ServiceBacktestRunRecord):
                normalized_runs.append(item)
            else:
                normalized_runs.append(build_backtest_run_record(item))
    normalized_errors: list[ServiceBacktestErrorRecord] = []
    if isinstance(errors, (list, tuple)):
        for item in errors:
            if isinstance(item, ServiceBacktestErrorRecord):
                normalized_errors.append(item)
            else:
                normalized_errors.append(build_backtest_error_record(item))
    if top_run is None and normalized_runs:
        top_run = normalized_runs[0]
    elif top_run is not None and not isinstance(top_run, ServiceBacktestRunRecord):
        top_run = build_backtest_run_record(top_run)
    return ServiceBacktestSnapshot(
        session_id=_clean_text(session_id),
        state=_clean_text(state, "idle"),
        workload_kind=_clean_text(workload_kind, "backtest-run"),
        status_message=_clean_text(status_message, "No backtest submitted yet."),
        symbols=_normalize_string_tuple(symbols),
        intervals=_normalize_interval_tuple(intervals),
        indicator_keys=_normalize_string_tuple(indicator_keys),
        logic=_clean_text(logic),
        symbol_source=_clean_text(symbol_source),
        capital=_coerce_float(capital, 0.0),
        run_count=max(0, _coerce_int(run_count, 0)),
        error_count=max(0, _coerce_int(error_count, 0)),
        cancelled=bool(cancelled),
        started_at=_normalize_iso(started_at),
        completed_at=_normalize_iso(completed_at),
        updated_at=_normalize_iso(updated_at),
        source=_clean_text(source, "service"),
        top_run=top_run,
        top_runs=tuple(normalized_runs),
        errors=tuple(normalized_errors),
    )


def make_backtest_command_result(
    *,
    accepted,  # noqa: ANN001
    action: str,
    session_id: str = "",
    state: str = "idle",
    status_message: str = "",
    source: str = "service",
) -> ServiceBacktestCommandResult:
    return ServiceBacktestCommandResult(
        accepted=bool(accepted),
        action=_clean_text(action),
        session_id=_clean_text(session_id),
        state=_clean_text(state, "idle"),
        status_message=_clean_text(status_message),
        source=_clean_text(source, "service"),
    )
