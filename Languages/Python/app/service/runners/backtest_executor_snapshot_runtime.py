from __future__ import annotations

from ..schemas.backtest import (
    build_backtest_error_record,
    build_backtest_run_record,
    build_backtest_snapshot,
)
from .backtest_executor_request_runtime import sort_runs, utc_now_iso


def set_running_snapshots(
    adapter,
    *,
    session_id: str,
    started_at: str,
    summary: dict[str, object],
    message: str,
    action: str,
    progress_percent: float | None,
) -> None:
    updated_at = utc_now_iso()
    adapter._runtime.set_execution_snapshot(
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
        tick_count=adapter._progress_tick_count,
        last_action=action,
        last_message=message,
        started_at=started_at,
        source="service-backtest-executor",
        notes=(
            "Backtest execution is owned by the standalone service process.",
            "This workload reuses the shared BacktestEngine outside the PyQt GUI.",
        ),
    )
    adapter._runtime.set_backtest_snapshot(
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


def finish_snapshots(
    adapter,
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
    updated_at = utc_now_iso()
    sorted_runs = sort_runs(run_records or [])
    run_payload = [build_backtest_run_record(item) for item in sorted_runs[:5]]
    error_payload = [build_backtest_error_record(item) for item in (error_records or [])[:10]]
    adapter._runtime.set_backtest_snapshot(
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
    adapter._runtime.set_execution_snapshot(
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
        tick_count=adapter._progress_tick_count,
        last_action=action,
        last_message=message,
        started_at=started_at,
        source="service-backtest-executor",
        notes=(
            "Backtest execution is owned by the standalone service process.",
            "The latest service-owned backtest session has finished.",
        ),
    )
