"""
Portfolio and positions snapshot schemas for the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _safe_bool(value) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def _side_label(side_key: str) -> str:
    norm = str(side_key or "").strip().upper()
    if norm == "L":
        return "Long"
    if norm == "S":
        return "Short"
    if norm == "SPOT":
        return "Spot"
    return norm or "Unknown"


@dataclass(frozen=True, slots=True)
class ServicePositionSnapshot:
    symbol: str
    side_key: str
    side_label: str
    interval: str
    quantity: float | None
    mark_price: float | None
    size_usdt: float | None
    margin_usdt: float | None
    pnl_value: float | None
    roi_percent: float | None
    leverage: int | None
    liquidation_price: float | None
    status: str
    stop_loss_enabled: bool
    open_time: str
    close_time: str

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "side_key": self.side_key,
            "side_label": self.side_label,
            "interval": self.interval,
            "quantity": self.quantity,
            "mark_price": self.mark_price,
            "size_usdt": self.size_usdt,
            "margin_usdt": self.margin_usdt,
            "pnl_value": self.pnl_value,
            "roi_percent": self.roi_percent,
            "leverage": self.leverage,
            "liquidation_price": self.liquidation_price,
            "status": self.status,
            "stop_loss_enabled": self.stop_loss_enabled,
            "open_time": self.open_time,
            "close_time": self.close_time,
        }


@dataclass(frozen=True, slots=True)
class ServicePortfolioSnapshot:
    account_type: str
    open_position_count: int
    closed_position_count: int
    active_pnl: float | None
    active_margin: float | None
    closed_pnl: float | None
    closed_margin: float | None
    total_balance: float | None
    available_balance: float | None
    positions: tuple[ServicePositionSnapshot, ...]
    source: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "account_type": self.account_type,
            "open_position_count": self.open_position_count,
            "closed_position_count": self.closed_position_count,
            "active_pnl": self.active_pnl,
            "active_margin": self.active_margin,
            "closed_pnl": self.closed_pnl,
            "closed_margin": self.closed_margin,
            "total_balance": self.total_balance,
            "available_balance": self.available_balance,
            "positions": [item.to_dict() for item in self.positions],
            "source": self.source,
            "generated_at": self.generated_at,
        }


def build_position_snapshot(record: dict | None) -> ServicePositionSnapshot:
    rec = record if isinstance(record, dict) else {}
    data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
    leverage_val = None
    try:
        raw_leverage = rec.get("leverage")
        if raw_leverage in (None, ""):
            raw_leverage = data.get("leverage")
        if raw_leverage not in (None, ""):
            leverage_val = int(float(raw_leverage))
            if leverage_val <= 0:
                leverage_val = None
    except Exception:
        leverage_val = None
    return ServicePositionSnapshot(
        symbol=str(rec.get("symbol") or data.get("symbol") or "").strip().upper() or "Unknown",
        side_key=str(rec.get("side_key") or data.get("side_key") or "").strip().upper() or "Unknown",
        side_label=_side_label(str(rec.get("side_key") or data.get("side_key") or "")),
        interval=(
            str(rec.get("entry_tf") or data.get("interval_display") or data.get("interval") or "-").strip()
            or "-"
        ),
        quantity=_safe_float_or_none(data.get("qty")),
        mark_price=_safe_float_or_none(data.get("mark")),
        size_usdt=_safe_float_or_none(data.get("size_usdt") or data.get("value")),
        margin_usdt=_safe_float_or_none(data.get("margin_usdt")),
        pnl_value=_safe_float_or_none(data.get("pnl_value")),
        roi_percent=_safe_float_or_none(data.get("roi_percent")),
        leverage=leverage_val,
        liquidation_price=_safe_float_or_none(rec.get("liquidation_price") or data.get("liquidation_price")),
        status=str(rec.get("status") or "Active").strip() or "Active",
        stop_loss_enabled=_safe_bool(rec.get("stop_loss_enabled")),
        open_time=str(rec.get("open_time") or data.get("open_time") or "-").strip() or "-",
        close_time=str(rec.get("close_time") or data.get("close_time") or "-").strip() or "-",
    )


def _compute_active_totals(open_position_records: dict | None) -> tuple[float | None, float | None]:
    records = open_position_records if isinstance(open_position_records, dict) else {}
    total_pnl = 0.0
    total_margin = 0.0
    pnl_found = False
    margin_found = False
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
        pnl_val = _safe_float_or_none(data.get("pnl_value"))
        margin_val = _safe_float_or_none(data.get("margin_usdt"))
        if pnl_val is not None:
            total_pnl += pnl_val
            pnl_found = True
        if margin_val is not None and margin_val > 0.0:
            total_margin += margin_val
            margin_found = True
    return (
        total_pnl if pnl_found else None,
        total_margin if margin_found and total_margin > 0.0 else None,
    )


def _compute_closed_totals(closed_trade_registry: dict | None) -> tuple[float | None, float | None]:
    registry = closed_trade_registry if isinstance(closed_trade_registry, dict) else {}
    total_pnl = 0.0
    total_margin = 0.0
    pnl_found = False
    margin_found = False
    for entry in registry.values():
        if not isinstance(entry, dict):
            continue
        pnl_val = _safe_float_or_none(entry.get("pnl_value"))
        margin_val = _safe_float_or_none(entry.get("margin_usdt"))
        if pnl_val is not None:
            total_pnl += pnl_val
            pnl_found = True
        if margin_val is not None and margin_val > 0.0:
            total_margin += margin_val
            margin_found = True
    return (
        total_pnl if pnl_found else None,
        total_margin if margin_found and total_margin > 0.0 else None,
    )


def build_portfolio_snapshot(
    *,
    config: dict | None,
    open_position_records: dict | None = None,
    closed_position_records: list | tuple | None = None,
    closed_trade_registry: dict | None = None,
    active_pnl=None,
    active_margin=None,
    closed_pnl=None,
    closed_margin=None,
    total_balance=None,
    available_balance=None,
    source: str = "service",
) -> ServicePortfolioSnapshot:
    cfg = config if isinstance(config, dict) else {}
    open_records = open_position_records if isinstance(open_position_records, dict) else {}
    closed_records = (
        [item for item in (closed_position_records or []) if isinstance(item, dict)]
        if isinstance(closed_position_records, (list, tuple))
        else []
    )
    positions = tuple(
        sorted(
            (build_position_snapshot(rec) for rec in open_records.values() if isinstance(rec, dict)),
            key=lambda item: (item.symbol, item.side_key, item.interval, item.open_time),
        )
    )
    if active_pnl is None or active_margin is None:
        computed_active_pnl, computed_active_margin = _compute_active_totals(open_records)
        if active_pnl is None:
            active_pnl = computed_active_pnl
        if active_margin is None:
            active_margin = computed_active_margin
    if closed_pnl is None or closed_margin is None:
        computed_closed_pnl, computed_closed_margin = _compute_closed_totals(closed_trade_registry)
        if closed_pnl is None:
            closed_pnl = computed_closed_pnl
        if closed_margin is None:
            closed_margin = computed_closed_margin
    closed_count = len(closed_records)
    if closed_count <= 0 and isinstance(closed_trade_registry, dict):
        closed_count = len(closed_trade_registry)
    return ServicePortfolioSnapshot(
        account_type=str(cfg.get("account_type") or "Unknown"),
        open_position_count=len(positions),
        closed_position_count=max(0, int(closed_count)),
        active_pnl=_safe_float_or_none(active_pnl),
        active_margin=_safe_float_or_none(active_margin),
        closed_pnl=_safe_float_or_none(closed_pnl),
        closed_margin=_safe_float_or_none(closed_margin),
        total_balance=_safe_float_or_none(total_balance),
        available_balance=_safe_float_or_none(available_balance),
        positions=positions,
        source=str(source or "service"),
        generated_at=_utc_now_iso(),
    )
