"""
Service-owned backtest execution adapter.

This is the first extracted workload that runs fully inside the headless
service process instead of depending on the desktop GUI thread.
"""

from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from ...core.backtest import BacktestEngine, BacktestRequest, IndicatorDefinition, PairOverride
from ...integrations.exchanges.binance import BinanceWrapper
from ...config import normalize_stop_loss_dict
from ..schemas.backtest import (
    ServiceBacktestCommandResult,
    build_backtest_error_record,
    build_backtest_run_record,
    build_backtest_snapshot,
    make_backtest_command_result,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value, default: str = "") -> str:  # noqa: ANN001
    text = str(value or "").strip()
    return text or default


def _string_list(value) -> list[str]:  # noqa: ANN001
    if not isinstance(value, (list, tuple)):
        return []
    items: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            items.append(text)
    return items


def _deep_merge(base: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged.get(key) or {}, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _coerce_number(value, default: float = 0.0) -> float:  # noqa: ANN001
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_datetime(value) -> datetime | None:  # noqa: ANN001
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _clean_text(value)
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = None
        try:
            parsed = datetime.fromisoformat(text)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except Exception:
                    continue
        if parsed is None:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _build_indicator_definitions(indicators_payload) -> list[IndicatorDefinition]:  # noqa: ANN001
    indicators: list[IndicatorDefinition] = []
    if isinstance(indicators_payload, dict):
        for key, params in indicators_payload.items():
            if not isinstance(params, dict) or not bool(params.get("enabled")):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=str(key), params=clean_params))
        return indicators
    if isinstance(indicators_payload, (list, tuple)):
        for item in indicators_payload:
            if not isinstance(item, dict):
                continue
            key = _clean_text(item.get("key"))
            if not key:
                continue
            params = copy.deepcopy(item.get("params") or {})
            indicators.append(IndicatorDefinition(key=key, params=params if isinstance(params, dict) else {}))
    return indicators


def _build_pair_overrides(overrides_payload) -> list[PairOverride] | None:  # noqa: ANN001
    if not isinstance(overrides_payload, (list, tuple)):
        return None
    overrides: list[PairOverride] = []
    seen: set[tuple[str, str]] = set()
    for item in overrides_payload:
        if not isinstance(item, dict):
            continue
        symbol = _clean_text(item.get("symbol")).upper()
        interval = _clean_text(item.get("interval"))
        if not symbol or not interval:
            continue
        key = (symbol, interval)
        if key in seen:
            continue
        seen.add(key)
        indicators = _string_list(item.get("indicators"))
        leverage = None
        try:
            raw_leverage = item.get("leverage")
            if raw_leverage is not None:
                leverage = int(float(raw_leverage))
        except Exception:
            leverage = None
        overrides.append(
            PairOverride(
                symbol=symbol,
                interval=interval,
                indicators=indicators or None,
                leverage=leverage,
            )
        )
    return overrides or None


def _estimate_run_count(
    symbols: list[str],
    intervals: list[str],
    indicator_count: int,
    logic: str,
    pair_overrides: list[PairOverride] | None,
) -> int:
    combos = len(pair_overrides) if pair_overrides else (len(symbols) * len(intervals))
    if combos <= 0:
        return 0
    if str(logic or "").upper() == "SEPARATE":
        return combos * max(1, indicator_count)
    return combos


def _sort_runs(records: list) -> list:  # noqa: ANN001
    return sorted(
        records,
        key=lambda item: (
            float(getattr(item, "roi_percent", 0.0) or 0.0),
            float(getattr(item, "roi_value", 0.0) or 0.0),
            -float(getattr(item, "max_drawdown_percent", 0.0) or 0.0),
            int(getattr(item, "trades", 0) or 0),
        ),
        reverse=True,
    )


class ServiceBacktestExecutionAdapter:
    def __init__(self, runtime, *, wrapper_factory: Callable[..., object] | None = None) -> None:  # noqa: ANN001
        self._runtime = runtime
        self._wrapper_factory = wrapper_factory or BinanceWrapper
        self._lock = threading.RLock()
        self._worker_thread: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._current_session_id = ""
        self._current_started_at = ""
        self._progress_tick_count = 0
        self._current_summary: dict[str, object] = {}

    def _is_running_unlocked(self) -> bool:
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _build_request(self, request_patch: dict | None) -> tuple[BacktestRequest, dict[str, object], dict[str, object]]:
        config = self._runtime.config
        patch = copy.deepcopy(request_patch) if isinstance(request_patch, dict) else {}
        backtest_cfg = copy.deepcopy(config.get("backtest") or {}) if isinstance(config.get("backtest"), dict) else {}
        if isinstance(patch.get("backtest"), dict):
            backtest_cfg = _deep_merge(backtest_cfg, patch.pop("backtest"))

        symbols = _string_list(patch.get("symbols", backtest_cfg.get("symbols", config.get("symbols"))))
        intervals = _string_list(patch.get("intervals", backtest_cfg.get("intervals", config.get("intervals"))))
        indicators = _build_indicator_definitions(
            patch.get("indicators", backtest_cfg.get("indicators", config.get("indicators")))
        )
        if not indicators:
            raise ValueError("At least one enabled indicator is required for backtesting.")

        logic = _clean_text(patch.get("logic", backtest_cfg.get("logic", "AND")), "AND").upper()
        symbol_source = _clean_text(patch.get("symbol_source", backtest_cfg.get("symbol_source", "Futures")), "Futures")
        capital = max(0.0, _coerce_number(patch.get("capital", backtest_cfg.get("capital", 0.0)), 0.0))
        if capital <= 0.0:
            raise ValueError("Backtest capital must be positive.")

        pair_overrides = _build_pair_overrides(
            patch.get("pair_overrides", config.get("backtest_symbol_interval_pairs"))
        )
        if pair_overrides:
            symbols = list(dict.fromkeys(item.symbol for item in pair_overrides))
            intervals = list(dict.fromkeys(item.interval for item in pair_overrides))

        if not symbols:
            raise ValueError("At least one symbol is required for backtesting.")
        if not intervals:
            raise ValueError("At least one interval is required for backtesting.")

        start_dt = _coerce_datetime(patch.get("start", backtest_cfg.get("start_date")))
        end_dt = _coerce_datetime(patch.get("end", backtest_cfg.get("end_date")))
        if end_dt is None:
            end_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        if start_dt is None:
            start_dt = end_dt - timedelta(days=30)
        if start_dt >= end_dt:
            raise ValueError("Backtest start must be earlier than backtest end.")

        stop_loss_cfg = normalize_stop_loss_dict(patch.get("stop_loss", backtest_cfg.get("stop_loss")))
        leverage = max(1.0, _coerce_number(patch.get("leverage", backtest_cfg.get("leverage", config.get("leverage", 1))), 1.0))
        margin_mode = _clean_text(
            patch.get("margin_mode", backtest_cfg.get("margin_mode", config.get("margin_mode", "Isolated"))),
            "Isolated",
        )
        position_mode = _clean_text(
            patch.get("position_mode", backtest_cfg.get("position_mode", config.get("position_mode", "Hedge"))),
            "Hedge",
        )
        assets_mode = _clean_text(
            patch.get("assets_mode", backtest_cfg.get("assets_mode", config.get("assets_mode", "Single-Asset"))),
            "Single-Asset",
        )
        account_mode = _clean_text(
            patch.get("account_mode", backtest_cfg.get("account_mode", config.get("account_mode", "Classic Trading"))),
            "Classic Trading",
        )
        side = _clean_text(patch.get("side", backtest_cfg.get("side", config.get("side", "BOTH"))), "BOTH")
        position_pct = max(
            0.0001,
            _coerce_number(patch.get("position_pct", backtest_cfg.get("position_pct", config.get("position_pct", 1.0))), 1.0),
        )
        position_pct_units = _clean_text(
            patch.get("position_pct_units", backtest_cfg.get("position_pct_units", "percent")),
            "percent",
        )
        mdd_logic = _clean_text(patch.get("mdd_logic", backtest_cfg.get("mdd_logic", "per_trade")), "per_trade")

        request = BacktestRequest(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            logic=logic,
            symbol_source=symbol_source,
            start=start_dt,
            end=end_dt,
            capital=capital,
            side=side,
            position_pct=position_pct,
            position_pct_units=position_pct_units,
            leverage=leverage,
            margin_mode=margin_mode,
            position_mode=position_mode,
            assets_mode=assets_mode,
            account_mode=account_mode,
            mdd_logic=mdd_logic,
            stop_loss_enabled=bool(stop_loss_cfg.get("enabled")),
            stop_loss_mode=_clean_text(stop_loss_cfg.get("mode"), "usdt"),
            stop_loss_usdt=_coerce_number(stop_loss_cfg.get("usdt"), 0.0),
            stop_loss_percent=_coerce_number(stop_loss_cfg.get("percent"), 0.0),
            stop_loss_scope=_clean_text(stop_loss_cfg.get("scope"), "per_trade"),
            pair_overrides=pair_overrides,
        )

        mode = _clean_text(patch.get("mode", config.get("mode", "Live")), "Live")
        account_type = _clean_text(
            patch.get(
                "account_type",
                "Spot" if symbol_source.lower().startswith("spot") else config.get("account_type", "Futures"),
            ),
            "Futures",
        )
        connector_backend = _clean_text(
            patch.get("connector_backend", backtest_cfg.get("connector_backend", config.get("connector_backend"))),
        )
        wrapper_kwargs = {
            "api_key": _clean_text(patch.get("api_key", config.get("api_key"))),
            "api_secret": _clean_text(patch.get("api_secret", config.get("api_secret"))),
            "mode": mode,
            "account_type": account_type,
            "default_leverage": int(max(1, round(leverage))),
            "default_margin_mode": margin_mode,
            "connector_backend": connector_backend or None,
        }
        summary = {
            "symbols": tuple(symbols),
            "intervals": tuple(intervals),
            "indicator_keys": tuple(ind.key for ind in indicators),
            "logic": logic,
            "symbol_source": symbol_source,
            "capital": capital,
            "estimated_run_count": _estimate_run_count(symbols, intervals, len(indicators), logic, pair_overrides),
        }
        return request, wrapper_kwargs, summary

    def _set_running_snapshots(
        self,
        *,
        session_id: str,
        started_at: str,
        summary: dict[str, object],
        message: str,
        action: str,
        progress_percent: float | None,
    ) -> None:
        updated_at = _utc_now_iso()
        self._runtime.set_execution_snapshot(
            executor_kind="service-backtest-executor",
            owner="service-process",
            state="running",
            workload_kind="backtest-run",
            session_id=session_id,
            requested_job_count=int(summary.get("estimated_run_count") or 0),
            active_engine_count=1,
            progress_label=message,
            progress_percent=progress_percent,
            heartbeat_at=updated_at,
            tick_count=self._progress_tick_count,
            last_action=action,
            last_message=message,
            started_at=started_at,
            source="service-backtest-executor",
            notes=(
                "Backtest execution is owned by the standalone service process.",
                "This workload reuses the shared BacktestEngine outside the PyQt GUI.",
            ),
        )
        self._runtime.set_backtest_snapshot(
            build_backtest_snapshot(
                session_id=session_id,
                state="running",
                status_message=message,
                symbols=summary.get("symbols"),
                intervals=summary.get("intervals"),
                indicator_keys=summary.get("indicator_keys"),
                logic=str(summary.get("logic") or ""),
                symbol_source=str(summary.get("symbol_source") or ""),
                capital=float(summary.get("capital") or 0.0),
                started_at=started_at,
                updated_at=updated_at,
                source="service-backtest-executor",
            )
        )

    def _finish_snapshots(
        self,
        *,
        session_id: str,
        started_at: str,
        summary: dict[str, object],
        state: str,
        message: str,
        cancelled: bool,
        run_records: list | None = None,  # noqa: ANN001
        error_records: list | None = None,  # noqa: ANN001
        progress_percent: float | None = None,
        action: str = "complete",
    ) -> None:
        updated_at = _utc_now_iso()
        sorted_runs = _sort_runs(run_records or [])
        run_payload = [build_backtest_run_record(item) for item in sorted_runs[:5]]
        error_payload = [build_backtest_error_record(item) for item in (error_records or [])[:10]]
        self._runtime.set_backtest_snapshot(
            build_backtest_snapshot(
                session_id=session_id,
                state=state,
                status_message=message,
                symbols=summary.get("symbols"),
                intervals=summary.get("intervals"),
                indicator_keys=summary.get("indicator_keys"),
                logic=str(summary.get("logic") or ""),
                symbol_source=str(summary.get("symbol_source") or ""),
                capital=float(summary.get("capital") or 0.0),
                run_count=len(run_records or []),
                error_count=len(error_records or []),
                cancelled=cancelled,
                started_at=started_at,
                completed_at=updated_at,
                updated_at=updated_at,
                source="service-backtest-executor",
                top_runs=run_payload,
                errors=error_payload,
            )
        )
        self._runtime.set_execution_snapshot(
            executor_kind="service-backtest-executor",
            owner="service-process",
            state="idle",
            workload_kind="backtest-run",
            session_id=session_id,
            requested_job_count=int(summary.get("estimated_run_count") or 0),
            active_engine_count=0,
            progress_label=message,
            progress_percent=progress_percent,
            heartbeat_at=updated_at,
            tick_count=self._progress_tick_count,
            last_action=action,
            last_message=message,
            started_at=started_at,
            source="service-backtest-executor",
            notes=(
                "Backtest execution is owned by the standalone service process.",
                "The latest service-owned backtest session has finished.",
            ),
        )

    def _run_backtest_thread(
        self,
        session_id: str,
        started_at: str,
        engine_request: BacktestRequest,
        wrapper_kwargs: dict[str, object],
        summary: dict[str, object],
    ) -> None:
        try:
            wrapper = self._wrapper_factory(**wrapper_kwargs)
            try:
                wrapper.indicator_source = (
                    "Binance spot" if str(summary.get("symbol_source") or "").lower().startswith("spot")
                    else "Binance futures"
                )
            except Exception:
                pass
            engine = BacktestEngine(wrapper)

            def _progress(message: str) -> None:
                with self._lock:
                    self._progress_tick_count += 1
                    estimated_runs = max(1, int(summary.get("estimated_run_count") or 1))
                    progress_percent = min(95.0, (self._progress_tick_count / estimated_runs) * 100.0)
                self._set_running_snapshots(
                    session_id=session_id,
                    started_at=started_at,
                    summary=summary,
                    message=_clean_text(message, "Backtest running."),
                    action="progress",
                    progress_percent=progress_percent,
                )

            result = engine.run(
                engine_request,
                progress=_progress,
                should_stop=lambda: bool(self._cancel_event and self._cancel_event.is_set()),
            )
            run_records = list(result.get("runs", []) or []) if isinstance(result, dict) else []
            error_records = list(result.get("errors", []) or []) if isinstance(result, dict) else []
            cancelled = bool(self._cancel_event and self._cancel_event.is_set())
            if cancelled:
                message = f"Backtest session cancelled after {len(run_records)} run(s)."
                self._finish_snapshots(
                    session_id=session_id,
                    started_at=started_at,
                    summary=summary,
                    state="cancelled",
                    message=message,
                    cancelled=True,
                    run_records=run_records,
                    error_records=error_records,
                    progress_percent=None,
                    action="cancel",
                )
                self._runtime.record_log_event(message, source="service-backtest-executor", level="warn")
                return
            message = (
                f"Backtest session completed with {len(run_records)} run(s)"
                f" and {len(error_records)} error(s)."
            )
            self._finish_snapshots(
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                state="completed",
                message=message,
                cancelled=False,
                run_records=run_records,
                error_records=error_records,
                progress_percent=100.0,
                action="complete",
            )
            self._runtime.record_log_event(message, source="service-backtest-executor", level="info")
        except Exception as exc:
            message = f"Backtest session failed: {exc}"
            self._finish_snapshots(
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                state="failed",
                message=message,
                cancelled=False,
                run_records=[],
                error_records=[{"error": str(exc)}],
                progress_percent=None,
                action="failed",
            )
            self._runtime.record_log_event(message, source="service-backtest-executor", level="error")
        finally:
            with self._lock:
                self._worker_thread = None
                self._cancel_event = None

    def submit_backtest(
        self,
        request_patch: dict | None = None,
        *,
        source: str = "service",
    ) -> ServiceBacktestCommandResult:
        with self._lock:
            if self._is_running_unlocked():
                snapshot = self._runtime.get_backtest_snapshot()
                return make_backtest_command_result(
                    accepted=False,
                    action="run",
                    session_id=snapshot.session_id,
                    state=snapshot.state,
                    status_message="A backtest session is already running.",
                    source=source,
                )
        status = self._runtime.get_status()
        if str(status.state or "").lower() == "running":
            return make_backtest_command_result(
                accepted=False,
                action="run",
                state="rejected",
                status_message="Stop the active runtime session before starting a service-owned backtest.",
                source=source,
            )
        try:
            engine_request, wrapper_kwargs, summary = self._build_request(request_patch)
        except Exception as exc:
            now = _utc_now_iso()
            self._runtime.set_backtest_snapshot(
                build_backtest_snapshot(
                    state="failed",
                    status_message=f"Backtest request validation failed: {exc}",
                    updated_at=now,
                    source="service-backtest-executor",
                )
            )
            return make_backtest_command_result(
                accepted=False,
                action="run",
                state="failed",
                status_message=f"Backtest request validation failed: {exc}",
                source=source,
            )

        session_id = uuid.uuid4().hex[:12]
        started_at = _utc_now_iso()
        with self._lock:
            self._progress_tick_count = 0
            self._current_session_id = session_id
            self._current_started_at = started_at
            self._current_summary = dict(summary)
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            worker = threading.Thread(
                target=self._run_backtest_thread,
                args=(session_id, started_at, engine_request, wrapper_kwargs, summary),
                name="TradingBotServiceBacktestExecutor",
                daemon=True,
            )
            self._worker_thread = worker
            self._set_running_snapshots(
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                message="Backtest session accepted. Preparing market data.",
                action="start",
                progress_percent=0.0,
            )
            worker.start()

        self._runtime.record_log_event(
            f"Backtest session {session_id} started for {len(summary.get('symbols') or [])} symbol(s).",
            source="service-backtest-executor",
            level="info",
        )
        return make_backtest_command_result(
            accepted=True,
            action="run",
            session_id=session_id,
            state="running",
            status_message="Backtest session accepted.",
            source=source,
        )

    def stop_backtest(self, *, source: str = "service") -> ServiceBacktestCommandResult:
        with self._lock:
            worker = self._worker_thread
            cancel_event = self._cancel_event
            session_id = self._current_session_id
            started_at = self._current_started_at
            summary = dict(self._current_summary)
            if not worker or not worker.is_alive() or cancel_event is None:
                snapshot = self._runtime.get_backtest_snapshot()
                return make_backtest_command_result(
                    accepted=False,
                    action="stop",
                    session_id=snapshot.session_id,
                    state=snapshot.state,
                    status_message="No backtest session is running.",
                    source=source,
                )
            cancel_event.set()
            self._set_running_snapshots(
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                message="Backtest cancellation requested.",
                action="cancel-request",
                progress_percent=None,
            )
        self._runtime.record_log_event(
            f"Backtest session {session_id} cancellation requested.",
            source="service-backtest-executor",
            level="warn",
        )
        return make_backtest_command_result(
            accepted=True,
            action="stop",
            session_id=session_id,
            state="cancelling",
            status_message="Backtest cancellation requested.",
            source=source,
        )
