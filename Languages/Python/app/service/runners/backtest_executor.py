"""
Service-owned backtest execution adapter.

This is the first extracted workload that runs fully inside the headless
service process instead of depending on the desktop GUI thread.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Callable

from ...integrations.exchanges.binance import BinanceWrapper
from ..schemas.backtest import ServiceBacktestCommandResult, build_backtest_snapshot, make_backtest_command_result
from .backtest_executor_request_runtime import build_request, utc_now_iso
from .backtest_executor_snapshot_runtime import set_running_snapshots
from .backtest_checkpoint_store import (
    delete_backtest_checkpoint_file,
    deserialize_backtest_request,
    load_backtest_checkpoint_file,
    resolve_backtest_checkpoint_path,
    write_backtest_checkpoint_file,
)
from .backtest_snapshot_store import load_backtest_snapshot_file, write_backtest_snapshot_file
from .backtest_executor_worker_runtime import run_backtest_thread

MAX_PENDING_BACKTEST_JOBS = 2


class ServiceBacktestExecutionAdapter:
    def __init__(
        self,
        runtime,
        *,
        wrapper_factory: Callable[..., object] | None = None,
        snapshot_path: str | Path | None = None,
    ) -> None:  # noqa: ANN001
        self._runtime = runtime
        self._wrapper_factory = wrapper_factory or BinanceWrapper
        self._lock = threading.RLock()
        self._worker_thread: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._current_session_id = ""
        self._current_started_at = ""
        self._progress_tick_count = 0
        self._current_summary: dict[str, object] = {}
        self._pending_jobs: list[dict[str, object]] = []
        self._snapshot_path = Path(snapshot_path).expanduser().resolve() if snapshot_path else None
        self._checkpoint_path = (
            resolve_backtest_checkpoint_path(self._snapshot_path) if self._snapshot_path is not None else None
        )
        self._resume_checkpoint: dict[str, object] | None = (
            load_backtest_checkpoint_file(self._checkpoint_path) if self._checkpoint_path is not None else None
        )
        if self._snapshot_path is not None:
            recovered = load_backtest_snapshot_file(self._snapshot_path)
            if recovered is not None:
                self._runtime.set_backtest_snapshot(recovered)
                if recovered.state == "interrupted":
                    self._runtime.record_log_event(
                        f"Backtest session {recovered.session_id} was recovered as interrupted after a service restart.",
                        source="service-backtest-recovery",
                        level="warn",
                    )

    def _persist_optimizer_checkpoint(
        self,
        *,
        session_id: str,
        engine_request,
        wrapper_kwargs: dict[str, object],
        summary: dict[str, object],
        completed_combo_count: int,
        run_records: list[dict[str, object]],
        error_records: list[dict[str, object]],
    ) -> None:
        if self._checkpoint_path is None:
            return
        try:
            write_backtest_checkpoint_file(
                path=self._checkpoint_path,
                session_id=session_id,
                request=engine_request,
                wrapper_options=wrapper_kwargs,
                summary=summary,
                completed_combo_count=completed_combo_count,
                previous_runs=run_records,
                previous_errors=error_records,
            )
            self._resume_checkpoint = load_backtest_checkpoint_file(self._checkpoint_path)
        except (OSError, TypeError, ValueError) as exc:
            self._runtime.record_log_event(
                f"Could not persist the backtest optimizer checkpoint: {exc}",
                source="service-backtest-executor",
                level="warn",
            )

    def _clear_optimizer_checkpoint(self) -> None:
        if self._checkpoint_path is not None:
            delete_backtest_checkpoint_file(self._checkpoint_path)
        self._resume_checkpoint = None

    def _resume_workload(self) -> tuple[object, dict[str, object], dict[str, object]]:
        checkpoint = self._resume_checkpoint
        if checkpoint is None and self._checkpoint_path is not None:
            checkpoint = load_backtest_checkpoint_file(self._checkpoint_path)
        if checkpoint is None:
            raise ValueError("No resumable optimizer checkpoint is available.")
        request_payload = checkpoint.get("request")
        summary_payload = checkpoint.get("summary")
        if not isinstance(request_payload, dict) or not isinstance(summary_payload, dict):
            raise ValueError("The optimizer checkpoint is malformed.")
        engine_request = deserialize_backtest_request(request_payload)
        wrapper_kwargs = dict(checkpoint.get("wrapper_options") or {})
        config = self._runtime.config if isinstance(self._runtime.config, dict) else {}
        for key in ("api_key", "api_secret"):
            value = str(config.get(key) or "").strip()
            if value:
                wrapper_kwargs[key] = value
        summary = dict(summary_payload)
        summary["resume_checkpoint"] = True
        summary["resume_combo_offset"] = max(0, int(checkpoint.get("completed_combo_count") or 0))
        summary["resume_prior_runs"] = list(checkpoint.get("previous_runs") or [])
        summary["resume_prior_errors"] = list(checkpoint.get("previous_errors") or [])
        return engine_request, wrapper_kwargs, summary

    def _persist_backtest_snapshot(self) -> None:
        if self._snapshot_path is None:
            return
        try:
            write_backtest_snapshot_file(self._runtime.get_backtest_snapshot(), path=self._snapshot_path)
        except OSError as exc:
            self._runtime.record_log_event(
                f"Could not persist the latest backtest snapshot: {exc}",
                source="service-backtest-executor",
                level="warn",
            )

    def _is_running_unlocked(self) -> bool:
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _build_request(self, request_patch: dict | None) -> tuple[object, dict[str, object], dict[str, object]]:
        return build_request(self._runtime, request_patch)

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
        set_running_snapshots(
            self,
            session_id=session_id,
            started_at=started_at,
            summary=summary,
            message=message,
            action=action,
            progress_percent=progress_percent,
        )

    def _run_backtest_thread(
        self,
        session_id: str,
        started_at: str,
        engine_request,
        wrapper_kwargs: dict[str, object],
        summary: dict[str, object],
    ) -> None:
        run_backtest_thread(self, session_id, started_at, engine_request, wrapper_kwargs, summary)

    def _start_backtest_unlocked(
        self,
        *,
        session_id: str,
        started_at: str,
        engine_request: object,
        wrapper_kwargs: dict[str, object],
        summary: dict[str, object],
        message: str,
        action: str,
    ) -> None:
        self._progress_tick_count = 0
        self._current_session_id = session_id
        self._current_started_at = started_at
        self._current_summary = dict(summary)
        self._cancel_event = threading.Event()
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
            message=message,
            action=action,
            progress_percent=0.0,
        )
        worker.start()

    def _start_next_queued_backtest(self) -> str:
        with self._lock:
            self._worker_thread = None
            self._cancel_event = None
            if not self._pending_jobs:
                return ""
            job = self._pending_jobs.pop(0)
            session_id = str(job["session_id"])
            summary = dict(job["summary"])
            self._start_backtest_unlocked(
                session_id=session_id,
                started_at=str(job["started_at"]),
                engine_request=job["engine_request"],
                wrapper_kwargs=dict(job["wrapper_kwargs"]),
                summary=summary,
                message="Queued backtest session started. Preparing market data.",
                action="queue-dispatch",
            )
            return session_id

    def submit_backtest(
        self,
        request_patch: dict | None = None,
        *,
        source: str = "service",
    ) -> ServiceBacktestCommandResult:
        queue_if_busy = bool(isinstance(request_patch, dict) and request_patch.get("queue_if_busy"))
        resume_checkpoint = bool(isinstance(request_patch, dict) and request_patch.get("resume_checkpoint"))
        with self._lock:
            running = self._is_running_unlocked()
            if resume_checkpoint and running:
                snapshot = self._runtime.get_backtest_snapshot()
                return make_backtest_command_result(
                    accepted=False,
                    action="resume",
                    session_id=snapshot.session_id,
                    state=snapshot.state,
                    status_message="Stop the active backtest before resuming an optimizer checkpoint.",
                    source=source,
                )
            if running and not queue_if_busy:
                snapshot = self._runtime.get_backtest_snapshot()
                return make_backtest_command_result(
                    accepted=False,
                    action="run",
                    session_id=snapshot.session_id,
                    state=snapshot.state,
                    status_message="A backtest session is already running. Set queue_if_busy=true to queue up to two validated jobs.",
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
            if resume_checkpoint:
                engine_request, wrapper_kwargs, summary = self._resume_workload()
            else:
                engine_request, wrapper_kwargs, summary = self._build_request(request_patch)
        except Exception as exc:
            now = utc_now_iso()
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
        started_at = utc_now_iso()
        with self._lock:
            if self._is_running_unlocked():
                if len(self._pending_jobs) >= MAX_PENDING_BACKTEST_JOBS:
                    return make_backtest_command_result(
                        accepted=False,
                        action="queue",
                        state="rejected",
                        status_message=(
                            f"Backtest queue is full ({MAX_PENDING_BACKTEST_JOBS} pending jobs). "
                            "Wait for a job to finish or cancel queued work."
                        ),
                        source=source,
                    )
                self._pending_jobs.append(
                    {
                        "session_id": session_id,
                        "started_at": started_at,
                        "engine_request": engine_request,
                        "wrapper_kwargs": dict(wrapper_kwargs),
                        "summary": dict(summary),
                    }
                )
                queue_position = len(self._pending_jobs)
                self._runtime.record_log_event(
                    f"Backtest session {session_id} queued at position {queue_position} of {MAX_PENDING_BACKTEST_JOBS}.",
                    source="service-backtest-executor",
                    level="info",
                )
                return make_backtest_command_result(
                    accepted=True,
                    action="queue",
                    session_id=session_id,
                    state="queued",
                    status_message=f"Backtest session queued at position {queue_position}.",
                    source=source,
                )
            self._start_backtest_unlocked(
                session_id=session_id,
                started_at=started_at,
                engine_request=engine_request,
                wrapper_kwargs=wrapper_kwargs,
                summary=summary,
                message=(
                    "Resuming backtest optimizer checkpoint. Preparing remaining market data."
                    if resume_checkpoint
                    else "Backtest session accepted. Preparing market data."
                ),
                action="resume" if resume_checkpoint else "start",
            )

        self._runtime.record_log_event(
            f"Backtest session {session_id} started for {len(summary.get('symbols') or [])} symbol(s).",
            source="service-backtest-executor",
            level="info",
        )
        return make_backtest_command_result(
            accepted=True,
            action="resume" if resume_checkpoint else "run",
            session_id=session_id,
            state="running",
            status_message=("Backtest optimizer checkpoint resumed." if resume_checkpoint else "Backtest session accepted."),
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
                if self._pending_jobs:
                    queued_count = len(self._pending_jobs)
                    self._pending_jobs.clear()
                    message = f"Cancelled {queued_count} pending backtest job(s)."
                    self._runtime.record_log_event(message, source="service-backtest-executor", level="warn")
                    return make_backtest_command_result(
                        accepted=True,
                        action="clear-queue",
                        state="idle",
                        status_message=message,
                        source=source,
                    )
                snapshot = self._runtime.get_backtest_snapshot()
                return make_backtest_command_result(
                    accepted=False,
                    action="stop",
                    session_id=snapshot.session_id,
                    state=snapshot.state,
                    status_message="No backtest session is running.",
                    source=source,
                )
            queued_count = len(self._pending_jobs)
            self._pending_jobs.clear()
            cancel_event.set()
            message = "Backtest cancellation requested."
            if queued_count:
                message = f"{message} Cancelled {queued_count} pending backtest job(s)."
            self._set_running_snapshots(
                session_id=session_id,
                started_at=started_at,
                summary=summary,
                message=message,
                action="cancel-request",
                progress_percent=None,
            )
        self._runtime.record_log_event(
            f"Backtest session {session_id} cancellation requested"
            f"; cleared {queued_count} pending backtest job(s).",
            source="service-backtest-executor",
            level="warn",
        )
        return make_backtest_command_result(
            accepted=True,
            action="stop",
            session_id=session_id,
            state="cancelling",
            status_message=message,
            source=source,
        )
