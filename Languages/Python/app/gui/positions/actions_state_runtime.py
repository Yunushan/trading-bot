from __future__ import annotations

from PyQt6 import QtCore

from .actions_context_runtime import get_save_position_allocations


def clear_local_position_state(
    self,
    symbol: str,
    side_key: str,
    *,
    interval: str | None = None,
    reason: str | None = None,
) -> bool:
    """Remove a stale local position/allocations snapshot for a single futures side."""
    try:
        sym_upper = str(symbol or "").strip().upper()
        side_norm = str(side_key or "").strip().upper()
        if not sym_upper or side_norm not in ("L", "S"):
            return False
        key = (sym_upper, side_norm)
        changed = False

        try:
            changed = bool(self._snapshot_closed_position(sym_upper, side_norm)) or changed
        except Exception:
            pass

        try:
            open_records = getattr(self, "_open_position_records", None)
            if isinstance(open_records, dict) and key in open_records:
                open_records.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            alloc_map = getattr(self, "_entry_allocations", None)
            if isinstance(alloc_map, dict) and key in alloc_map:
                alloc_map.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            pending_close = getattr(self, "_pending_close_times", None)
            if isinstance(pending_close, dict):
                pending_close.pop(key, None)
        except Exception:
            pass

        try:
            missing_counts = getattr(self, "_position_missing_counts", None)
            if isinstance(missing_counts, dict):
                missing_counts.pop(key, None)
        except Exception:
            pass

        try:
            entry_times = getattr(self, "_entry_times", None)
            if isinstance(entry_times, dict):
                entry_times.pop(key, None)
        except Exception:
            pass

        intervals_to_close: list[str] = []
        try:
            entry_intervals = getattr(self, "_entry_intervals", None)
            if isinstance(entry_intervals, dict):
                side_map = entry_intervals.get(sym_upper)
                if isinstance(side_map, dict):
                    bucket = side_map.get(side_norm)
                    if isinstance(bucket, set):
                        intervals_to_close.extend([str(iv).strip() for iv in bucket if str(iv).strip()])
        except Exception:
            pass
        if interval:
            iv = str(interval).strip()
            if iv and iv not in intervals_to_close:
                intervals_to_close.append(iv)
        if intervals_to_close and hasattr(self, "_track_interval_close"):
            for iv in intervals_to_close:
                try:
                    self._track_interval_close(sym_upper, side_norm, iv)
                except Exception:
                    continue

        try:
            iv_times = getattr(self, "_entry_times_by_iv", None)
            if isinstance(iv_times, dict):
                for iv_key in list(iv_times.keys()):
                    try:
                        sym_key, side_key_key, _iv = iv_key
                    except Exception:
                        continue
                    if str(sym_key or "").strip().upper() == sym_upper and str(side_key_key or "").strip().upper() == side_norm:
                        iv_times.pop(iv_key, None)
        except Exception:
            pass

        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed"):
                guard_side = "BUY" if side_norm == "L" else "SELL"
                guard_obj.mark_closed(sym_upper, interval, guard_side)
        except Exception:
            pass

        if changed:
            saver = get_save_position_allocations()
            if callable(saver):
                try:
                    mode_value = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                    saver(
                        getattr(self, "_entry_allocations", {}),
                        getattr(self, "_open_position_records", {}),
                        mode=mode_value,
                    )
                except Exception:
                    pass
            try:
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            except Exception:
                pass
            try:
                self._render_positions_table()
            except Exception:
                pass
            if reason:
                try:
                    self.log(f"{sym_upper} {side_norm}: cleared stale local position ({reason}).")
                except Exception:
                    pass
        return changed
    except Exception:
        return False


def sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get("status", "Active")).upper() != "ACTIVE":
                    continue
                sym = str(rec.get("symbol") or "").strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass
