from __future__ import annotations

from PyQt6 import QtWidgets


def _update_positions_balance_labels(
    self,
    total_balance: float | None,
    available_balance: float | None,
) -> None:
    try:
        snapshot = getattr(self, "_positions_balance_snapshot", None)
    except Exception:
        snapshot = None
    if total_balance is None and available_balance is None and isinstance(snapshot, dict):
        total_balance = snapshot.get("total")
        available_balance = snapshot.get("available")
    else:
        try:
            self._positions_balance_snapshot = {"total": total_balance, "available": available_balance}
        except Exception:
            pass

    def _set_label(label: QtWidgets.QLabel | None, prefix: str, value: float | None) -> None:
        if label is None:
            return
        if value is None:
            label.setText(f"{prefix}: --")
        else:
            try:
                label.setText(f"{prefix}: {float(value):.3f} USDT")
            except Exception:
                label.setText(f"{prefix}: --")

    _set_label(getattr(self, "positions_total_balance_label", None), "Total Balance", total_balance)
    _set_label(getattr(self, "positions_available_balance_label", None), "Available Balance", available_balance)
    try:
        self._sync_service_account_snapshot(
            total_balance=total_balance,
            available_balance=available_balance,
            source="desktop-balance",
        )
    except Exception:
        pass
    try:
        self._sync_service_portfolio_snapshot(source="desktop-balance")
    except Exception:
        pass


def _compute_global_pnl_totals(
    self,
) -> tuple[float | None, float | None, float | None, float | None]:
    def _safe_float(value) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    open_records = getattr(self, "_open_position_records", {}) or {}
    active_total_pnl = 0.0
    active_total_margin = 0.0
    active_pnl_found = False
    active_margin_found = False
    for rec in open_records.values():
        if not isinstance(rec, dict):
            continue
        data = rec.get("data") if isinstance(rec, dict) else {}
        pnl_val = _safe_float((data or {}).get("pnl_value"))
        if pnl_val is None:
            pnl_val = _safe_float(rec.get("pnl_value"))
        if pnl_val is not None:
            active_total_pnl += pnl_val
            active_pnl_found = True
        margin_val = _safe_float((data or {}).get("margin_usdt"))
        if margin_val is None or margin_val <= 0.0:
            margin_val = _safe_float((data or {}).get("margin_balance"))
        if margin_val is None or margin_val <= 0.0:
            allocs = (data or {}).get("allocations") or rec.get("allocations")
            if isinstance(allocs, list):
                alloc_margin = 0.0
                for alloc in allocs:
                    alloc_margin += _safe_float((alloc or {}).get("margin_usdt")) or 0.0
                if alloc_margin > 0.0:
                    margin_val = alloc_margin
        if margin_val is not None and margin_val > 0.0:
            active_total_margin += margin_val
            active_margin_found = True

    closed_registry = getattr(self, "_closed_trade_registry", {}) or {}
    closed_total_pnl = 0.0
    closed_total_margin = 0.0
    closed_pnl_found = False
    closed_margin_found = False
    for entry in closed_registry.values():
        if not isinstance(entry, dict):
            continue
        pnl_val = _safe_float(entry.get("pnl_value"))
        if pnl_val is not None:
            closed_total_pnl += pnl_val
            closed_pnl_found = True
        margin_val = _safe_float(entry.get("margin_usdt"))
        if margin_val is not None and margin_val > 0.0:
            closed_total_margin += margin_val
            closed_margin_found = True

    active_pnl = active_total_pnl if active_pnl_found else None
    active_margin = active_total_margin if active_margin_found and active_total_margin > 0.0 else None
    closed_pnl = closed_total_pnl if closed_pnl_found else None
    closed_margin = closed_total_margin if closed_margin_found and closed_total_margin > 0.0 else None
    return active_pnl, active_margin, closed_pnl, closed_margin
