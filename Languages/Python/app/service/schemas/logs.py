"""
Log event schemas for the service layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ServiceLogEvent:
    sequence_id: int
    level: str
    message: str
    source: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def make_log_event(
    *,
    message: str,
    source: str = "service",
    level: str = "info",
    sequence_id: int = 0,
) -> ServiceLogEvent:
    try:
        seq = max(0, int(sequence_id))
    except Exception:
        seq = 0
    return ServiceLogEvent(
        sequence_id=seq,
        level=str(level or "info").strip().lower() or "info",
        message=str(message or ""),
        source=str(source or "service"),
        generated_at=_utc_now_iso(),
    )
