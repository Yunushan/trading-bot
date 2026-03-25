"""
Local standalone execution adapter for the service layer.

This keeps the service process capable of owning start/stop transitions before
the full trading engine is extracted out of the desktop stack.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from ..schemas.control import BotControlRequest


class LocalServiceExecutionAdapter:
    def __init__(self, runtime) -> None:  # noqa: ANN001
        self._runtime = runtime
        self._lock = threading.RLock()
        self._worker_thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._active_engine_count = 0
        self._current_session_id = ""
        self._current_started_at = ""
        self._tick_count = 0

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_running_unlocked(self) -> bool:
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _run_until_stopped(self, stop_event: threading.Event) -> None:
        try:
            while not stop_event.wait(0.5):
                with self._lock:
                    if self._stop_event is not stop_event:
                        break
                    self._tick_count += 1
                    tick_count = self._tick_count
                    active_jobs = self._active_engine_count
                    session_id = self._current_session_id
                    started_at = self._current_started_at
                heartbeat_at = self._utc_now_iso()
                self._runtime.set_execution_snapshot(
                    executor_kind="local-service-executor",
                    owner="service-process",
                    state="running",
                    workload_kind="service-runtime-session",
                    session_id=session_id,
                    requested_job_count=active_jobs,
                    active_engine_count=active_jobs,
                    progress_label="Open-ended standalone service session.",
                    progress_percent=None,
                    heartbeat_at=heartbeat_at,
                    tick_count=tick_count,
                    last_action="heartbeat",
                    last_message="Local service executor session is active.",
                    started_at=started_at,
                    source="service-local-executor",
                    notes=(
                        "Standalone service process currently owns the execution session.",
                        "Heartbeat updates confirm the local executor loop is still alive.",
                    ),
                )
        finally:
            with self._lock:
                if self._stop_event is stop_event:
                    self._worker_thread = None
                    self._stop_event = None

    def _start_local_session(self, request: BotControlRequest) -> dict[str, object]:
        requested_jobs = max(1, int(request.requested_job_count or 0))
        with self._lock:
            if self._is_running_unlocked():
                current_jobs = max(1, int(self._active_engine_count or requested_jobs))
                self._runtime.set_execution_snapshot(
                    executor_kind="local-service-executor",
                    owner="service-process",
                    state="running",
                    workload_kind="service-runtime-session",
                    session_id=self._current_session_id,
                    requested_job_count=current_jobs,
                    active_engine_count=current_jobs,
                    progress_label="Open-ended standalone service session.",
                    progress_percent=None,
                    heartbeat_at=self._utc_now_iso(),
                    tick_count=self._tick_count,
                    last_action="start-rejected",
                    last_message=f"Local service executor is already running with {current_jobs} engine(s).",
                    started_at=self._current_started_at,
                    source="service-local-executor",
                    notes=(
                        "Standalone service process currently owns the execution session.",
                        "The local executor is a transitional runtime until extracted trading services replace it.",
                    ),
                )
                self._runtime.set_runtime_state(
                    active=True,
                    active_engine_count=current_jobs,
                    source="service-local-executor",
                )
                return {
                    "accepted": False,
                    "message": f"Local service executor is already running with {current_jobs} engine(s).",
                }
            stop_event = threading.Event()
            worker = threading.Thread(
                target=self._run_until_stopped,
                args=(stop_event,),
                name="TradingBotServiceLocalExecutor",
                daemon=True,
            )
            self._stop_event = stop_event
            self._worker_thread = worker
            self._active_engine_count = requested_jobs
            self._current_session_id = uuid.uuid4().hex[:12]
            self._current_started_at = self._utc_now_iso()
            self._tick_count = 0
            worker.start()

        self._runtime.set_execution_snapshot(
            executor_kind="local-service-executor",
            owner="service-process",
            state="running",
            workload_kind="service-runtime-session",
            session_id=self._current_session_id,
            requested_job_count=requested_jobs,
            active_engine_count=requested_jobs,
            progress_label="Open-ended standalone service session.",
            progress_percent=None,
            heartbeat_at=self._current_started_at,
            tick_count=0,
            last_action="start",
            last_message=f"Local service executor started with {requested_jobs} engine(s).",
            started_at=self._current_started_at,
            source="service-local-executor",
            notes=(
                "Standalone service process currently owns the execution session.",
                "The local executor is a transitional runtime until extracted trading services replace it.",
            ),
        )
        self._runtime.record_log_event(
            f"Local service executor started with {requested_jobs} engine(s).",
            source="service-local-executor",
            level="info",
        )
        self._runtime.set_runtime_state(
            active=True,
            active_engine_count=requested_jobs,
            source="service-local-executor",
        )
        return {
            "accepted": True,
            "message": f"Local service executor started with {requested_jobs} engine(s).",
        }

    def _stop_local_session(self, request: BotControlRequest) -> dict[str, object]:
        with self._lock:
            worker = self._worker_thread
            stop_event = self._stop_event
            running = self._is_running_unlocked()
            active_jobs = max(0, int(self._active_engine_count or 0))
            session_id = self._current_session_id
            started_at = self._current_started_at
            tick_count = self._tick_count
            if stop_event is not None:
                stop_event.set()

        if worker is not None and running:
            worker.join(0.75)

        with self._lock:
            self._worker_thread = None
            self._stop_event = None
            self._active_engine_count = 0
            self._current_session_id = ""
            self._current_started_at = ""
            self._tick_count = 0

        if not running:
            self._runtime.set_execution_snapshot(
                executor_kind="local-service-executor",
                owner="service-process",
                state="idle",
                workload_kind="service-runtime-session",
                session_id=session_id,
                requested_job_count=0,
                active_engine_count=0,
                progress_label="No active standalone service session.",
                progress_percent=None,
                heartbeat_at=self._utc_now_iso(),
                tick_count=tick_count,
                last_action="stop-rejected",
                last_message="Local service executor is already idle.",
                started_at=started_at,
                source="service-local-executor",
                notes=(
                    "Standalone service process currently owns the execution session.",
                    "No active local session is running.",
                ),
            )
            self._runtime.set_runtime_state(
                active=False,
                active_engine_count=0,
                source="service-local-executor",
            )
            return {
                "accepted": False,
                "message": "Local service executor is already idle.",
            }

        suffix = " with close-positions intent." if request.close_positions else "."
        self._runtime.set_execution_snapshot(
            executor_kind="local-service-executor",
            owner="service-process",
            state="idle",
            workload_kind="service-runtime-session",
            session_id=session_id,
            requested_job_count=active_jobs,
            active_engine_count=0,
            progress_label="Latest standalone service session completed.",
            progress_percent=100.0,
            heartbeat_at=self._utc_now_iso(),
            tick_count=tick_count,
            last_action="stop",
            last_message=f"Local service executor stopped after {active_jobs} engine(s){suffix}",
            started_at=started_at,
            source="service-local-executor",
            notes=(
                "Standalone service process currently owns the execution session.",
                "The most recent local execution session has stopped.",
            ),
        )
        self._runtime.record_log_event(
            f"Local service executor stopped after {active_jobs} engine(s){suffix}",
            source="service-local-executor",
            level="info",
        )
        self._runtime.set_runtime_state(
            active=False,
            active_engine_count=0,
            source="service-local-executor",
        )
        return {
            "accepted": True,
            "message": f"Local service executor stopped after {active_jobs} engine(s){suffix}",
        }

    def handle_control_request(self, request: BotControlRequest) -> dict[str, object]:
        action = str(getattr(request, "action", "") or "").strip().lower()
        if action == "start":
            return self._start_local_session(request)
        if action == "stop":
            return self._stop_local_session(request)
        return {
            "accepted": False,
            "message": f"Unsupported local executor control action: {action or 'unknown'}.",
        }
