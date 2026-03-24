"""
Account snapshot schemas for the service layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float_or_none(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class ServiceAccountSnapshot:
    account_type: str
    mode: str
    selected_exchange: str
    connector_backend: str
    balance_currency: str
    total_balance: float | None
    available_balance: float | None
    source: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_account_snapshot(
    *,
    config: dict | None,
    total_balance=None,
    available_balance=None,
    source: str = "service",
) -> ServiceAccountSnapshot:
    cfg = config if isinstance(config, dict) else {}
    return ServiceAccountSnapshot(
        account_type=str(cfg.get("account_type") or "Unknown"),
        mode=str(cfg.get("mode") or "Unknown"),
        selected_exchange=str(cfg.get("selected_exchange") or "Unknown"),
        connector_backend=str(cfg.get("connector_backend") or "Unknown"),
        balance_currency="USDT",
        total_balance=_safe_float_or_none(total_balance),
        available_balance=_safe_float_or_none(available_balance),
        source=str(source or "service"),
        generated_at=_utc_now_iso(),
    )
