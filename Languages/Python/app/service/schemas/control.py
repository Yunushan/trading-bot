"""
Control schemas for service lifecycle requests/results.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ...security.redaction import redact_text, redact_value


_POSITION_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._:/-]{0,63}$")
_POSITION_SIDE_ALIASES = {
    "B": "L",
    "BUY": "L",
    "L": "L",
    "LONG": "L",
    "S": "S",
    "SELL": "S",
    "SHORT": "S",
}


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


@dataclass(frozen=True, slots=True)
class PositionCloseRequest:
    action: str
    symbol: str
    side_key: str
    interval: str
    quantity: float
    target_identity: dict[str, object]
    confirm_close: bool
    source: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PositionCloseResult:
    accepted: bool
    action: str
    symbol: str
    side_key: str
    interval: str
    quantity: float
    target_identity: dict[str, object]
    source: str
    status_message: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _safe_target_identity(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    redacted = redact_value(dict(value))
    if not isinstance(redacted, Mapping):
        return {}
    result: dict[str, object] = {}
    for raw_key, raw_value in redacted.items():
        key = str(raw_key or "").strip()[:64]
        if not key or not isinstance(raw_value, (str, int, float, bool)):
            continue
        if isinstance(raw_value, float) and not math.isfinite(raw_value):
            continue
        result[key] = str(raw_value)[:256] if isinstance(raw_value, str) else raw_value
    return result


def make_position_close_request(
    *,
    symbol: str,
    side_key: str,
    quantity: Any,
    interval: str = "",
    target_identity: object = None,
    confirm_close: bool = False,
    source: str = "service",
) -> PositionCloseRequest:
    if not bool(confirm_close):
        raise ValueError("position close requires confirm_close=true")
    normalized_symbol = str(symbol or "").strip().upper()
    if not _POSITION_SYMBOL_RE.fullmatch(normalized_symbol):
        raise ValueError("position close requires a valid symbol")
    normalized_side = _POSITION_SIDE_ALIASES.get(str(side_key or "").strip().upper(), "")
    if normalized_side not in {"L", "S"}:
        raise ValueError("position close side must be long or short")
    try:
        normalized_quantity = float(quantity)
    except (TypeError, ValueError) as exc:
        raise ValueError("position close quantity must be a finite positive number") from exc
    if not math.isfinite(normalized_quantity) or normalized_quantity <= 0.0:
        raise ValueError("position close quantity must be a finite positive number")
    return PositionCloseRequest(
        action="position_close",
        symbol=normalized_symbol,
        side_key=normalized_side,
        interval=redact_text(str(interval or "").strip()),
        quantity=normalized_quantity,
        target_identity=_safe_target_identity(target_identity),
        confirm_close=True,
        source=redact_text(source or "service"),
        generated_at=_utc_now_iso(),
    )


def make_position_close_result(
    request: PositionCloseRequest,
    *,
    accepted: bool,
    status_message: str,
) -> PositionCloseResult:
    return PositionCloseResult(
        accepted=bool(accepted),
        action=request.action,
        symbol=request.symbol,
        side_key=request.side_key,
        interval=request.interval,
        quantity=request.quantity,
        target_identity=dict(request.target_identity),
        source=request.source,
        status_message=redact_text(status_message or ""),
        generated_at=_utc_now_iso(),
    )


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
        source=redact_text(source or "service"),
        reason=redact_text(reason or ""),
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
        source=redact_text(source or "service"),
        reason=redact_text(reason or ""),
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
        source=redact_text(source or "service"),
        status_message=redact_text(status_message or ""),
        generated_at=_utc_now_iso(),
    )
