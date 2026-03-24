"""
Status schemas for the service facade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class BotStatusSnapshot:
    state: str
    lifecycle_phase: str
    requested_action: str
    close_positions_requested: bool
    status_message: str
    last_transition_at: str
    service_mode: str
    generated_at: str
    api_enabled: bool
    docker_required: bool
    runtime_source: str
    active_engine_count: int
    account_type: str
    mode: str
    selected_exchange: str
    connector_backend: str
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        return payload


def make_initial_status(
    *,
    state: str = "idle",
    lifecycle_phase: str = "idle",
    requested_action: str = "",
    close_positions_requested: bool = False,
    status_message: str = "Service initialized.",
    last_transition_at: str | None = None,
    runtime_source: str = "service",
    active_engine_count: int = 0,
    account_type: str,
    mode: str,
    selected_exchange: str,
    connector_backend: str,
) -> BotStatusSnapshot:
    return BotStatusSnapshot(
        state=str(state or "idle"),
        lifecycle_phase=str(lifecycle_phase or "idle"),
        requested_action=str(requested_action or ""),
        close_positions_requested=bool(close_positions_requested),
        status_message=str(status_message or "Service initialized."),
        last_transition_at=str(last_transition_at or _utc_now_iso()),
        service_mode="local-headless",
        generated_at=_utc_now_iso(),
        api_enabled=False,
        docker_required=False,
        runtime_source=str(runtime_source or "service"),
        active_engine_count=max(0, int(active_engine_count or 0)),
        account_type=str(account_type or "").strip() or "Unknown",
        mode=str(mode or "").strip() or "Unknown",
        selected_exchange=str(selected_exchange or "").strip() or "Unknown",
        connector_backend=str(connector_backend or "").strip() or "Unknown",
        notes=(
            "Service state is available to embedded desktop clients and the optional HTTP API.",
            "Desktop mode remains the primary user path while the service layer grows.",
        ),
    )
