from __future__ import annotations

from ...core.backtest import BacktestEngine
from .backtest_executor_request_runtime import clean_text
from .backtest_executor_snapshot_runtime import finish_snapshots, set_running_snapshots


def run_backtest_thread(
    adapter,
    session_id: str,
    started_at: str,
    engine_request,
    wrapper_kwargs: dict[str, object],
    summary: dict[str, object],
) -> None:
    try:
        wrapper = adapter._wrapper_factory(**wrapper_kwargs)
        try:
            wrapper.indicator_source = (
                "Binance spot" if str(summary.get("symbol_source") or "").lower().startswith("spot")
                else "Binance futures"
            )
        except Exception:
            pass
        engine = BacktestEngine(wrapper)

        def _progress(message: str) -> None:
            with adapter._lock:
                adapter._progress_tick_count += 1
                estimated_runs = max(1, int(summary.get("estimated_run_count") or 1))
                progress_percent = min(95.0, (adapter._progress_tick_count / estimated_runs) * 100.0)
            set_running_snapshots(
                adapter,
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                message=clean_text(message, "Backtest running."),
                action="progress",
                progress_percent=progress_percent,
            )

        result = engine.run(
            engine_request,
            progress=_progress,
            should_stop=lambda: bool(adapter._cancel_event and adapter._cancel_event.is_set()),
        )
        run_records = list(result.get("runs", []) or []) if isinstance(result, dict) else []
        error_records = list(result.get("errors", []) or []) if isinstance(result, dict) else []
        cancelled = bool(adapter._cancel_event and adapter._cancel_event.is_set())
        if cancelled:
            message = f"Backtest session cancelled after {len(run_records)} run(s)."
            finish_snapshots(
                adapter,
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
            adapter._runtime.record_log_event(message, source="service-backtest-executor", level="warn")
            return
        message = (
            f"Backtest session completed with {len(run_records)} run(s)"
            f" and {len(error_records)} error(s)."
        )
        finish_snapshots(
            adapter,
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
        adapter._runtime.record_log_event(message, source="service-backtest-executor", level="info")
    except Exception as exc:
        message = f"Backtest session failed: {exc}"
        finish_snapshots(
            adapter,
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
        adapter._runtime.record_log_event(message, source="service-backtest-executor", level="error")
    finally:
        with adapter._lock:
            adapter._worker_thread = None
            adapter._cancel_event = None
