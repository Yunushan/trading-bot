from __future__ import annotations

import copy
import time
from datetime import datetime

from PyQt6 import QtWidgets

from .actions_context_runtime import closed_history_max, get_pos_status_column


def clear_positions_selected(self):
    try:
        table = getattr(self, "pos_table", None)
        if table is None:
            return
        sel_model = table.selectionModel()
        if sel_model is None:
            return
        rows = sorted({index.row() for index in sel_model.selectedRows()}, reverse=True)
        if not rows:
            return
        closed_records = list(getattr(self, "_closed_position_records", []) or [])
        changed = False
        skipped_active = False
        pos_status_column = get_pos_status_column()
        for row in rows:
            status_item = table.item(row, pos_status_column)
            status = (status_item.text().strip().upper() if status_item else "")
            if status != "CLOSED":
                skipped_active = True
                continue
            symbol_item = table.item(row, 0)
            side_item = table.item(row, 9)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            side_txt = (side_item.text().strip().upper() if side_item else "")
            side_key = None
            if "LONG" in side_txt or side_txt == "BUY":
                side_key = "L"
            elif "SHORT" in side_txt or side_txt == "SELL":
                side_key = "S"
            remove_idx = None
            for idx, rec in enumerate(closed_records):
                rec_sym = str(rec.get("symbol") or "").strip().upper()
                rec_side = str(rec.get("side_key") or "").strip().upper()
                if rec_sym == symbol and (side_key is None or not rec_side or rec_side == side_key):
                    remove_idx = idx
                    break
            if remove_idx is not None:
                closed_records.pop(remove_idx)
                changed = True
        if changed:
            self._closed_position_records = closed_records
            self._render_positions_table()
        if skipped_active:
            try:
                self.log("Positions: only closed history rows can be cleared.")
            except Exception:
                pass
    except Exception:
        pass


def clear_positions_all(self):
    try:
        if QtWidgets.QMessageBox.question(
            self,
            "Clear Closed History",
            "Clear ALL closed position history? (Active positions remain untouched.)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._closed_position_records = []
        self._closed_trade_registry = {}
        self._render_positions_table()
    except Exception:
        pass


def snapshot_closed_position(self, symbol: str, side_key: str) -> bool:
    try:
        if not symbol or side_key not in ("L", "S"):
            return False
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        open_records = getattr(self, "_open_position_records", {}) or {}
        rec = open_records.get((symbol, side_key))
        if not rec:
            return False
        snap = copy.deepcopy(rec)
        snap["status"] = "Closed"
        snap["close_time"] = self._format_display_time(datetime.now().astimezone())
        self._closed_position_records.insert(0, snap)
        max_history = closed_history_max(self)
        if len(self._closed_position_records) > max_history:
            self._closed_position_records = self._closed_position_records[:max_history]
        try:
            registry = getattr(self, "_closed_trade_registry", None)
            if registry is None:
                registry = {}
                self._closed_trade_registry = registry
            key = f"{symbol}-{side_key}-{int(time.time() * 1000)}"
            data = snap.get("data") if isinstance(snap, dict) else {}

            def _safe_float_local(value):
                try:
                    return float(value)
                except Exception:
                    return None

            registry[key] = {
                "pnl_value": _safe_float_local((data or {}).get("pnl_value")),
                "margin_usdt": _safe_float_local((data or {}).get("margin_usdt")),
                "roi_percent": _safe_float_local((data or {}).get("roi_percent")),
            }
            if len(registry) > max_history:
                excess = len(registry) - max_history
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        except Exception:
            pass
        try:
            open_records.pop((symbol, side_key), None)
        except Exception:
            pass
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
        return True
    except Exception:
        return False
