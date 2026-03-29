"""
Bot runtime coordinator for the service layer.

This owns config snapshots and lifecycle intent so future HTTP/web/mobile
clients can call a stable backend contract without depending on PyQt.
"""

from __future__ import annotations

import copy
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.config import DEFAULT_CONFIG
    from app.service.runners.bot_runtime_control import BotRuntimeControlMixin
    from app.service.runners.bot_runtime_state import BotRuntimeStateMixin
    from app.service.schemas.account import build_account_snapshot
    from app.service.schemas.backtest import build_backtest_snapshot
    from app.service.schemas.control import BotControlRequest
    from app.service.schemas.execution import build_execution_snapshot
    from app.service.schemas.logs import ServiceLogEvent
    from app.service.schemas.positions import build_portfolio_snapshot
else:
    from ...config import DEFAULT_CONFIG
    from .bot_runtime_control import BotRuntimeControlMixin
    from .bot_runtime_state import BotRuntimeStateMixin
    from ..schemas.account import build_account_snapshot
    from ..schemas.backtest import build_backtest_snapshot
    from ..schemas.control import BotControlRequest
    from ..schemas.execution import build_execution_snapshot
    from ..schemas.logs import ServiceLogEvent
    from ..schemas.positions import build_portfolio_snapshot


class BotRuntimeCoordinator(BotRuntimeStateMixin, BotRuntimeControlMixin):
    def __init__(self, config: dict | None = None) -> None:
        self._lock = threading.RLock()
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        if isinstance(config, dict):
            self._config.update(copy.deepcopy(config))
        self._runtime_active = False
        self._active_engine_count = 0
        self._runtime_source = "service"
        self._lifecycle_phase = "idle"
        self._requested_action = ""
        self._close_positions_requested = False
        self._status_message = "Service initialized."
        self._last_transition_at = self._now_iso()
        self._log_sequence = 0
        self._recent_logs: deque[ServiceLogEvent] = deque(maxlen=250)
        self._account_total_balance = None
        self._account_available_balance = None
        self._open_position_records: dict = {}
        self._closed_position_records: list[dict] = []
        self._closed_trade_registry: dict = {}
        self._active_pnl = None
        self._active_margin = None
        self._closed_pnl = None
        self._closed_margin = None
        self._account_snapshot = build_account_snapshot(config=self._config, source="service-bootstrap")
        self._portfolio_snapshot = build_portfolio_snapshot(config=self._config, source="service-bootstrap")
        self._control_request_handler: Callable[[BotControlRequest], object] | None = None
        self._control_plane_mode = "intent-only"
        self._control_plane_owner = "service-runtime"
        self._control_plane_start_supported = False
        self._control_plane_stop_supported = False
        self._control_plane_notes = (
            "Control requests are recorded as service intent until an execution adapter is attached.",
        )
        self._execution_executor_kind = "unbound"
        self._execution_owner = "service-runtime"
        self._execution_state = "idle"
        self._execution_workload_kind = "unbound"
        self._execution_session_id = ""
        self._execution_requested_job_count = 0
        self._execution_active_engine_count = 0
        self._execution_progress_label = ""
        self._execution_progress_percent = None
        self._execution_heartbeat_at = ""
        self._execution_tick_count = 0
        self._execution_last_action = ""
        self._execution_last_message = "No execution adapter attached."
        self._execution_started_at = ""
        self._execution_source = "service-bootstrap"
        self._execution_notes = (
            "Execution state is idle until a service-owned or delegated executor attaches.",
        )
        self._execution_snapshot = build_execution_snapshot(
            executor_kind=self._execution_executor_kind,
            owner=self._execution_owner,
            state=self._execution_state,
            workload_kind=self._execution_workload_kind,
            session_id=self._execution_session_id,
            requested_job_count=self._execution_requested_job_count,
            active_engine_count=self._execution_active_engine_count,
            progress_label=self._execution_progress_label,
            progress_percent=self._execution_progress_percent,
            heartbeat_at=self._execution_heartbeat_at,
            tick_count=self._execution_tick_count,
            last_action=self._execution_last_action,
            last_message=self._execution_last_message,
            started_at=self._execution_started_at,
            source=self._execution_source,
            notes=self._execution_notes,
        )
        self._backtest_snapshot = build_backtest_snapshot(
            source="service-bootstrap",
            updated_at=self._now_iso(),
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
