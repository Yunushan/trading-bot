"""
Control schemas for service lifecycle requests/results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class BotControlRequest:
    action: str
    requested_job_count: int
    close_positions: bool
    source: str
    reason: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BotControlResult:
    accepted: bool
    action: str
    lifecycle_phase: str
    runtime_active: bool
    active_engine_count: int
    requested_job_count: int
    close_positions_requested: bool
    source: str
    status_message: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def make_start_request(
    *,
    requested_job_count: int = 0,
    source: str = "service",
    reason: str = "",
) -> BotControlRequest:
    try:
        job_count = max(0, int(requested_job_count))
    except Exception:
        job_count = 0
    return BotControlRequest(
        action="start",
        requested_job_count=job_count,
        close_positions=False,
        source=str(source or "service"),
        reason=str(reason or ""),
        generated_at=_utc_now_iso(),
    )


def make_stop_request(
    *,
    close_positions: bool = False,
    source: str = "service",
    reason: str = "",
) -> BotControlRequest:
    return BotControlRequest(
        action="stop",
        requested_job_count=0,
        close_positions=bool(close_positions),
        source=str(source or "service"),
        reason=str(reason or ""),
        generated_at=_utc_now_iso(),
    )


def make_control_result(
    *,
    accepted: bool,
    action: str,
    lifecycle_phase: str,
    runtime_active: bool,
    active_engine_count: int,
    requested_job_count: int = 0,
    close_positions_requested: bool = False,
    source: str = "service",
    status_message: str = "",
) -> BotControlResult:
    try:
        engine_count = max(0, int(active_engine_count))
    except Exception:
        engine_count = 0
    try:
        job_count = max(0, int(requested_job_count))
    except Exception:
        job_count = 0
    return BotControlResult(
        accepted=bool(accepted),
        action=str(action or ""),
        lifecycle_phase=str(lifecycle_phase or "idle"),
        runtime_active=bool(runtime_active),
        active_engine_count=engine_count,
        requested_job_count=job_count,
        close_positions_requested=bool(close_positions_requested),
        source=str(source or "service"),
        status_message=str(status_message or ""),
        generated_at=_utc_now_iso(),
    )
