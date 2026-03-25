"""
Execution session schemas for the service layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ServiceExecutionSnapshot:
    executor_kind: str
    owner: str
    state: str
    workload_kind: str
    session_id: str
    requested_job_count: int
    active_engine_count: int
    progress_label: str
    progress_percent: float | None
    heartbeat_at: str
    tick_count: int
    last_action: str
    last_message: str
    started_at: str
    updated_at: str
    source: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        return payload


def build_execution_snapshot(
    *,
    executor_kind: str = "unbound",
    owner: str = "service-runtime",
    state: str = "idle",
    workload_kind: str = "unbound",
    session_id: str = "",
    requested_job_count: int = 0,
    active_engine_count: int = 0,
    progress_label: str = "",
    progress_percent: float | None = None,
    heartbeat_at: str | None = None,
    tick_count: int = 0,
    last_action: str = "",
    last_message: str = "",
    started_at: str | None = None,
    updated_at: str | None = None,
    source: str = "service",
    notes: tuple[str, ...] | list[str] | None = None,
) -> ServiceExecutionSnapshot:
    normalized_notes = tuple(str(item or "").strip() for item in (notes or ()) if str(item or "").strip())
    return ServiceExecutionSnapshot(
        executor_kind=str(executor_kind or "unbound"),
        owner=str(owner or "service-runtime"),
        state=str(state or "idle"),
        workload_kind=str(workload_kind or "unbound"),
        session_id=str(session_id or ""),
        requested_job_count=max(0, int(requested_job_count or 0)),
        active_engine_count=max(0, int(active_engine_count or 0)),
        progress_label=str(progress_label or ""),
        progress_percent=None if progress_percent is None else float(progress_percent),
        heartbeat_at=str(heartbeat_at or ""),
        tick_count=max(0, int(tick_count or 0)),
        last_action=str(last_action or ""),
        last_message=str(last_message or ""),
        started_at=str(started_at or ""),
        updated_at=str(updated_at or _utc_now_iso()),
        source=str(source or "service"),
        notes=normalized_notes,
    )
