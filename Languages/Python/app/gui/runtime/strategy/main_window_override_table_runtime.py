from __future__ import annotations

import copy

from PyQt6 import QtCore, QtWidgets

from . import main_window_override_shared_runtime as shared


def _refresh_symbol_interval_pairs(self, kind: str = "runtime", _depth: int = 0):
    current_depth = getattr(self, "_override_refresh_depth", 0)
    setattr(self, "_override_refresh_depth", current_depth + 1)
    try:
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        self._log_override_debug(kind, "Refreshing symbol/interval table start.")
        column_map = ctx.get("column_map") or {}
        symbol_col = column_map.get("Symbol", 0)
        interval_col = column_map.get("Interval", 1)
        indicator_col = column_map.get("Indicators")
        loop_col = column_map.get("Loop")
        leverage_col = column_map.get("Leverage")
        strategy_col = column_map.get("Strategy Controls")
        connector_col = column_map.get("Connector")
        stoploss_col = column_map.get("Stop-Loss")
        header = table.horizontalHeader()
        try:
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            if sort_column is None or sort_column < 0:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
        except Exception:
            sort_column = 0
            sort_order = QtCore.Qt.SortOrder.AscendingOrder
        table.setSortingEnabled(False)
        pairs_cfg = self._override_config_list(kind) or []
        self._log_override_debug(kind, "Refresh loaded config list.", payload={"count": len(pairs_cfg)})
        snapshot_pairs = []
        try:
            snapshot_pairs = [copy.deepcopy(entry) for entry in pairs_cfg if isinstance(entry, dict)]
        except Exception:
            snapshot_pairs = [dict(entry) for entry in pairs_cfg if isinstance(entry, dict)]
        table.setRowCount(0)
        seen = set()
        cleaned = []
        for entry in pairs_cfg:
            self._log_override_debug(kind, "Processing existing override entry.", payload={"entry": entry})
            entry_clean, indicator_values, leverage_val, controls = shared._build_clean_override_entry(
                self,
                kind,
                entry,
            )
            if not entry_clean:
                self._log_override_debug(kind, "Skipping entry: missing symbol or interval.", payload={"entry": entry})
                continue
            key = (
                entry_clean["symbol"],
                entry_clean["interval"],
                tuple(indicator_values),
                leverage_val,
            )
            if key in seen:
                self._log_override_debug(kind, "Skipping duplicate entry.", payload={"key": key})
                continue
            seen.add(key)
            self._log_override_debug(
                kind,
                "Normalized controls for entry.",
                payload={
                    "symbol": entry_clean["symbol"],
                    "interval": entry_clean["interval"],
                    "controls": controls,
                },
            )
            cleaned.append(entry_clean)
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, symbol_col, QtWidgets.QTableWidgetItem(entry_clean["symbol"]))
            table.setItem(row, interval_col, QtWidgets.QTableWidgetItem(entry_clean["interval"]))
            if indicator_col is not None:
                table.setItem(
                    row,
                    indicator_col,
                    QtWidgets.QTableWidgetItem(shared._format_indicator_list_text(indicator_values)),
                )
            if loop_col is not None:
                loop_display = entry_clean.get("loop_interval_override") or "-"
                table.setItem(row, loop_col, QtWidgets.QTableWidgetItem(loop_display))
            if leverage_col is not None:
                leverage_display = f"{leverage_val}x" if leverage_val is not None else "-"
                table.setItem(row, leverage_col, QtWidgets.QTableWidgetItem(leverage_display))
            if strategy_col is not None:
                summary = self._format_strategy_controls_summary(kind, controls)
                table.setItem(row, strategy_col, QtWidgets.QTableWidgetItem(summary))
            if connector_col is not None:
                backend_val = None
                if isinstance(controls, dict):
                    backend_val = controls.get("connector_backend")
                if not backend_val:
                    if kind == "runtime":
                        backend_val = self._runtime_connector_backend(suppress_refresh=True)
                    else:
                        if current_depth > 0:
                            backend_val = shared._normalize_connector_backend_value(
                                (self.backtest_config or {}).get("connector_backend")
                                or self.config.get("backtest", {}).get("connector_backend")
                            )
                        else:
                            backend_val = self._backtest_connector_backend()
                connector_display = self._connector_label_text(backend_val) if backend_val else "-"
                table.setItem(row, connector_col, QtWidgets.QTableWidgetItem(connector_display))
            if stoploss_col is not None:
                stop_label = "No"
                stop_cfg_display = None
                if isinstance(controls, dict):
                    stop_cfg_display = controls.get("stop_loss")
                if stop_cfg_display is None:
                    stop_cfg_display = entry_clean.get("stop_loss")
                if isinstance(stop_cfg_display, dict) and stop_cfg_display.get("enabled"):
                    scope_txt = str(stop_cfg_display.get("scope") or "").replace("_", "-")
                    stop_label = f"Yes ({scope_txt or 'per-trade'})"
                table.setItem(row, stoploss_col, QtWidgets.QTableWidgetItem(stop_label))
            try:
                table.item(row, symbol_col).setData(QtCore.Qt.ItemDataRole.UserRole, entry_clean)
            except Exception:
                pass
            self._log_override_debug(kind, "Row populated.", payload={"row": row, "entry_clean": entry_clean})
        cfg_key = ctx.get("config_key")
        if cfg_key and not cleaned and snapshot_pairs and _depth == 0:
            self._log_override_debug(
                kind,
                "Refresh produced no rows; retrying with snapshot fallback.",
                payload={"snapshot_len": len(snapshot_pairs)},
            )
            try:
                self.config[cfg_key] = snapshot_pairs
            except Exception:
                self.config[cfg_key] = list(snapshot_pairs)
            return self._refresh_symbol_interval_pairs(kind, _depth=_depth + 1)
        if cfg_key:
            self.config[cfg_key] = cleaned
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = list(cleaned)
                except Exception:
                    pass
        self._log_override_debug(kind, "Refresh completed.", payload={"cleaned_count": len(cleaned)})
        table.setSortingEnabled(True)
        try:
            if sort_column is not None and sort_column >= 0:
                table.sortItems(sort_column, sort_order)
        except Exception:
            pass
    finally:
        setattr(self, "_override_refresh_depth", current_depth)
