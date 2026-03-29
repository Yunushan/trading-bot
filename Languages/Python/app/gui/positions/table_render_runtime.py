from __future__ import annotations

from PyQt6 import QtCore

from . import (
    table_render_prepare_runtime,
    table_render_rows_runtime,
    table_render_state_runtime,
)

configure_main_window_positions_render_runtime = (
    table_render_state_runtime.configure_main_window_positions_render_runtime
)
_coerce_bool = table_render_state_runtime._coerce_bool
_format_indicator_list = table_render_state_runtime._format_indicator_list
_collect_record_indicator_keys = table_render_state_runtime._collect_record_indicator_keys
_collect_indicator_value_strings = table_render_state_runtime._collect_indicator_value_strings
_collect_current_indicator_live_strings = (
    table_render_state_runtime._collect_current_indicator_live_strings
)
_dedupe_indicator_entries_normalized = (
    table_render_state_runtime._dedupe_indicator_entries_normalized
)
_filter_indicator_entries = table_render_state_runtime._filter_indicator_entries
_indicator_entry_signature = table_render_state_runtime._indicator_entry_signature
_indicator_short_label = table_render_state_runtime._indicator_short_label
_normalize_indicator_values = table_render_state_runtime._normalize_indicator_values
_positions_records_cumulative = table_render_state_runtime._positions_records_cumulative


def __getattr__(name: str):
    if name in {
        "POS_CLOSE_COLUMN",
        "POS_CURRENT_VALUE_COLUMN",
        "POS_STATUS_COLUMN",
        "POS_STOP_LOSS_COLUMN",
        "POS_TRIGGERED_VALUE_COLUMN",
    }:
        return getattr(table_render_state_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _restore_scrollbar(bar, value) -> None:
    try:
        if bar is None or value is None:
            return
        value_clamped = max(bar.minimum(), min(value, bar.maximum()))
        bar.setValue(value_clamped)
    except Exception:
        pass


def _mw_render_positions_table(self):
    table = None
    updates_prev = None
    signals_prev = None
    vbar = None
    vbar_val = None
    hbar = None
    hbar_val = None
    sort_column = 0
    sort_order = QtCore.Qt.SortOrder.AscendingOrder
    snapshot_key = None
    snapshot_totals = None
    try:
        table = self.pos_table
        try:
            updates_prev = table.updatesEnabled()
            table.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(table, "blockSignals"):
                signals_prev = table.blockSignals(True)
        except Exception:
            pass
        try:
            vbar = table.verticalScrollBar()
            vbar_val = vbar.value()
        except Exception:
            vbar = None
            vbar_val = None
        try:
            hbar = table.horizontalScrollBar()
            hbar_val = hbar.value()
        except Exception:
            hbar = None
            hbar_val = None

        render_state = table_render_prepare_runtime.prepare_positions_table_render(self)
        snapshot_key = render_state["snapshot_key"]
        if (
            render_state["view_mode"] == "per_trade"
            and render_state["prev_snapshot"] == snapshot_key
        ):
            snapshot_totals = getattr(self, "_last_positions_table_totals", None)
            if isinstance(snapshot_totals, tuple) and len(snapshot_totals) == 2:
                self._update_positions_pnl_summary(*snapshot_totals)
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            return

        try:
            header = table.horizontalHeader()
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            if sort_column is None or sort_column < 0:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
        except Exception:
            sort_column = 0
            sort_order = QtCore.Qt.SortOrder.AscendingOrder

        table.setSortingEnabled(False)
        table.setRowCount(0)
        totals = table_render_rows_runtime.populate_positions_table(
            self,
            display_records=render_state["display_records"],
            view_mode=render_state["view_mode"],
            acct_is_futures=render_state["acct_is_futures"],
            live_value_cache=render_state["live_value_cache"],
        )

        try:
            if _coerce_bool(self.config.get("positions_auto_resize_rows", True), True):
                table.resizeRowsToContents()
        except Exception:
            pass
        try:
            if _coerce_bool(self.config.get("positions_auto_resize_columns", True), True):
                table.resizeColumnsToContents()
        except Exception:
            pass

        summary_margin = totals["summary_margin"]
        total_pnl = totals["total_pnl"] if totals["pnl_has_value"] else None
        snapshot_totals = (total_pnl, summary_margin)
        self._update_positions_pnl_summary(total_pnl, summary_margin)
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
        try:
            if (
                getattr(self, "chart_enabled", False)
                and getattr(self, "chart_auto_follow", False)
                and not getattr(self, "_chart_manual_override", False)
                and self._is_chart_visible()
            ):
                self._sync_chart_to_active_positions()
        except Exception:
            pass
    except Exception as exc:
        try:
            self.log(f"Positions table update failed: {exc}")
        except Exception:
            pass
    finally:
        try:
            if table is not None:
                table.setSortingEnabled(True)
                if sort_column is not None and sort_column >= 0:
                    table.sortItems(sort_column, sort_order)
        except Exception:
            pass
        try:
            if vbar is not None and vbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(vbar, vbar_val))
        except Exception:
            pass
        try:
            if hbar is not None and hbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(hbar, hbar_val))
        except Exception:
            pass
        try:
            self._last_positions_table_snapshot = snapshot_key
            if snapshot_totals is not None:
                self._last_positions_table_totals = snapshot_totals
        except Exception:
            pass
        try:
            if table is not None and hasattr(table, "blockSignals"):
                table.blockSignals(signals_prev if signals_prev is not None else False)
        except Exception:
            pass
        try:
            if table is not None and updates_prev is not None:
                table.setUpdatesEnabled(updates_prev)
        except Exception:
            pass


__all__ = [
    "POS_CLOSE_COLUMN",
    "POS_CURRENT_VALUE_COLUMN",
    "POS_STATUS_COLUMN",
    "POS_STOP_LOSS_COLUMN",
    "POS_TRIGGERED_VALUE_COLUMN",
    "_coerce_bool",
    "_collect_current_indicator_live_strings",
    "_collect_indicator_value_strings",
    "_collect_record_indicator_keys",
    "_dedupe_indicator_entries_normalized",
    "_filter_indicator_entries",
    "_format_indicator_list",
    "_indicator_entry_signature",
    "_indicator_short_label",
    "_mw_render_positions_table",
    "_normalize_indicator_values",
    "_positions_records_cumulative",
    "configure_main_window_positions_render_runtime",
]
