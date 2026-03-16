from __future__ import annotations

import copy
import traceback

from PyQt6 import QtCore, QtWidgets

_FORMAT_INDICATOR_LIST = None
_NORMALIZE_CONNECTOR_BACKEND = None
_NORMALIZE_INDICATOR_VALUES = None
_NORMALIZE_STOP_LOSS_DICT = None


def bind_main_window_override_runtime(
    main_window_cls,
    *,
    format_indicator_list=None,
    normalize_connector_backend=None,
    normalize_indicator_values=None,
    normalize_stop_loss_dict=None,
) -> None:
    global _FORMAT_INDICATOR_LIST
    global _NORMALIZE_CONNECTOR_BACKEND
    global _NORMALIZE_INDICATOR_VALUES
    global _NORMALIZE_STOP_LOSS_DICT

    _FORMAT_INDICATOR_LIST = format_indicator_list
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict

    main_window_cls._override_ctx = _override_ctx
    main_window_cls._override_config_list = _override_config_list
    main_window_cls._get_selected_indicator_keys = _get_selected_indicator_keys
    main_window_cls._refresh_symbol_interval_pairs = _refresh_symbol_interval_pairs
    main_window_cls._add_selected_symbol_interval_pairs = _add_selected_symbol_interval_pairs
    main_window_cls._remove_selected_symbol_interval_pairs = _remove_selected_symbol_interval_pairs
    main_window_cls._clear_symbol_interval_pairs = _clear_symbol_interval_pairs
    main_window_cls._create_override_group = _create_override_group


def _normalize_stop_loss(payload):
    func = _NORMALIZE_STOP_LOSS_DICT
    if callable(func):
        try:
            return func(payload)
        except Exception:
            pass
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _normalize_indicator_values_list(payload):
    func = _NORMALIZE_INDICATOR_VALUES
    if callable(func):
        try:
            return func(payload)
        except Exception:
            pass
    if isinstance(payload, (list, tuple, set)):
        values = []
        for value in payload:
            text = str(value or "").strip()
            if text:
                values.append(text)
        return values
    return []


def _format_indicator_list_text(values) -> str:
    func = _FORMAT_INDICATOR_LIST
    if callable(func):
        try:
            return func(values)
        except Exception:
            pass
    return ", ".join(str(value) for value in values if str(value).strip())


def _normalize_connector_backend_value(value):
    func = _NORMALIZE_CONNECTOR_BACKEND
    if callable(func):
        try:
            return func(value)
        except Exception:
            pass
    return value


def _override_ctx(self, kind: str) -> dict:
    return getattr(self, "override_contexts", {}).get(kind, {})


def _override_config_list(self, kind: str) -> list:
    ctx = self._override_ctx(kind)
    cfg_key = ctx.get("config_key")
    if not cfg_key:
        return []
    lst = self.config.setdefault(cfg_key, [])
    if not isinstance(lst, list):
        if isinstance(lst, (tuple, set)):
            lst = list(lst)
        elif isinstance(lst, dict):
            lst = [dict(lst)]
        else:
            lst = []
        self.config[cfg_key] = lst
    if kind == "backtest":
        try:
            self.backtest_config[cfg_key] = list(lst)
        except Exception:
            pass
    return lst


def _get_selected_indicator_keys(self, kind: str) -> list[str]:
    try:
        if kind == "runtime":
            widgets = getattr(self, "indicator_widgets", {}) or {}
        else:
            widgets = getattr(self, "backtest_indicator_widgets", {}) or {}
        keys: list[str] = []
        for key, control in widgets.items():
            cb = control[0] if isinstance(control, (tuple, list)) and control else None
            if cb and cb.isChecked():
                keys.append(str(key))
        if keys:
            return keys
    except Exception:
        pass
    try:
        cfg = self.config if kind == "runtime" else self.backtest_config
        indicators_cfg = (cfg or {}).get("indicators", {}) or {}
        return [key for key, params in indicators_cfg.items() if params.get("enabled")]
    except Exception:
        return []


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
            sym = str((entry or {}).get("symbol") or "").strip().upper()
            iv = str((entry or {}).get("interval") or "").strip()
            if not sym or not iv:
                self._log_override_debug(kind, "Skipping entry: missing symbol or interval.", payload={"entry": entry})
                continue
            indicators_raw = entry.get("indicators")
            indicator_values = _normalize_indicator_values_list(indicators_raw)
            leverage_val = None
            if isinstance(entry.get("strategy_controls"), dict):
                lev_ctrl = entry["strategy_controls"].get("leverage")
                if lev_ctrl is not None:
                    try:
                        leverage_val = max(1, int(lev_ctrl))
                    except Exception:
                        leverage_val = None
            if leverage_val is None:
                lev_entry_raw = entry.get("leverage")
                if lev_entry_raw is not None:
                    try:
                        leverage_val = max(1, int(lev_entry_raw))
                    except Exception:
                        leverage_val = None
            key = (sym, iv, tuple(indicator_values), leverage_val)
            if key in seen:
                self._log_override_debug(kind, "Skipping duplicate entry.", payload={"key": key})
                continue
            seen.add(key)
            controls = self._normalize_strategy_controls(kind, entry.get("strategy_controls"))
            self._log_override_debug(
                kind,
                "Normalized controls for entry.",
                payload={"symbol": sym, "interval": iv, "controls": controls},
            )
            entry_clean = {"symbol": sym, "interval": iv}
            if indicator_values:
                entry_clean["indicators"] = list(indicator_values)
            loop_val = entry.get("loop_interval_override")
            if not loop_val and isinstance(controls, dict):
                loop_val = controls.get("loop_interval_override")
            loop_val = self._normalize_loop_override(loop_val)
            if loop_val:
                entry_clean["loop_interval_override"] = loop_val
            if controls:
                entry_clean["strategy_controls"] = controls
                stop_cfg = controls.get("stop_loss")
                if isinstance(stop_cfg, dict):
                    entry_clean["stop_loss"] = _normalize_stop_loss(stop_cfg)
                backend_ctrl = controls.get("connector_backend")
                if backend_ctrl:
                    entry_clean["connector_backend"] = backend_ctrl
            if leverage_val is not None:
                entry_clean["leverage"] = leverage_val
                if isinstance(controls, dict):
                    controls["leverage"] = leverage_val
            if "stop_loss" not in entry_clean and entry.get("stop_loss"):
                entry_clean["stop_loss"] = _normalize_stop_loss(entry.get("stop_loss"))
            cleaned.append(entry_clean)
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, symbol_col, QtWidgets.QTableWidgetItem(sym))
            table.setItem(row, interval_col, QtWidgets.QTableWidgetItem(iv))
            if indicator_col is not None:
                table.setItem(row, indicator_col, QtWidgets.QTableWidgetItem(_format_indicator_list_text(indicator_values)))
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
                            backend_val = _normalize_connector_backend_value(
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


def _add_selected_symbol_interval_pairs(self, kind: str = "runtime"):
    if kind == "runtime" and getattr(self, "_bot_active", False):
        try:
            self.log("Stop the bot before modifying runtime overrides.")
        except Exception:
            pass
        return
    ctx = self._override_ctx(kind)
    symbol_list = ctx.get("symbol_list")
    interval_list = ctx.get("interval_list")
    if symbol_list is None or interval_list is None:
        self._log_override_debug(kind, "Add-selected aborted: missing list widgets.", payload={"ctx_keys": list(ctx.keys())})
        return
    try:
        self._log_override_debug(kind, "Add-selected triggered.")
        symbol_items = []
        try:
            symbol_items = [item for item in symbol_list.selectedItems() if item]
            self._log_override_debug(kind, "Collected selected symbol items via selectedItems().", payload={"count": len(symbol_items)})
        except Exception:
            symbol_items = []
        if not symbol_items:
            for i in range(symbol_list.count()):
                item = symbol_list.item(i)
                if item and item.isSelected():
                    symbol_items.append(item)
            self._log_override_debug(kind, "Fallback symbol scan after selectedItems() empty.", payload={"count": len(symbol_items)})
        symbols = []
        for item in symbol_items:
            try:
                text = item.text()
            except Exception:
                text = ""
            text_norm = str(text or "").strip().upper()
            if text_norm:
                symbols.append(text_norm)
        self._log_override_debug(kind, "Normalized symbols.", payload={"symbols": symbols})

        interval_items = []
        try:
            interval_items = [item for item in interval_list.selectedItems() if item]
            self._log_override_debug(
                kind,
                "Collected selected interval items via selectedItems().",
                payload={"count": len(interval_items)},
            )
        except Exception:
            interval_items = []
        if not interval_items:
            for i in range(interval_list.count()):
                item = interval_list.item(i)
                if item and item.isSelected():
                    interval_items.append(item)
            self._log_override_debug(
                kind,
                "Fallback interval scan after selectedItems() empty.",
                payload={"count": len(interval_items)},
            )
        intervals = []
        for item in interval_items:
            try:
                text = item.text()
            except Exception:
                text = ""
            text_norm = str(text or "").strip()
            if text_norm:
                intervals.append(text_norm)
        self._log_override_debug(kind, "Normalized intervals.", payload={"intervals": intervals})

        if symbols:
            symbols = list(dict.fromkeys(symbols))
        if intervals:
            intervals = list(dict.fromkeys(intervals))
        if not symbols or not intervals:
            self._log_override_debug(
                kind,
                "Add-selected aborted: missing symbols or intervals.",
                payload={"symbols": symbols, "intervals": intervals},
            )
            try:
                self.log("Select at least one symbol and interval before adding overrides.")
            except Exception:
                pass
            return
        pairs_cfg = self._override_config_list(kind)
        existing_keys = {}
        for entry in pairs_cfg:
            sym_existing = str(entry.get("symbol") or "").strip().upper()
            iv_existing = str(entry.get("interval") or "").strip()
            if not (sym_existing and iv_existing):
                self._log_override_debug(kind, "Skipping existing entry missing symbol/interval.", payload={"entry": entry})
                continue
            indicators_existing = entry.get("indicators")
            if isinstance(indicators_existing, (list, tuple)):
                indicators_existing = sorted({str(k).strip() for k in indicators_existing if str(k).strip()})
            else:
                indicators_existing = []
            key = (sym_existing, iv_existing, tuple(indicators_existing))
            existing_keys[key] = entry
        self._log_override_debug(kind, "Prepared existing key map.", payload={"existing_count": len(existing_keys)})
        controls_snapshot_raw = self._collect_strategy_controls(kind)
        self._log_override_debug(kind, "Raw strategy controls collected.", payload={"raw": controls_snapshot_raw})
        controls_snapshot = self._prepare_controls_snapshot(kind, controls_snapshot_raw)
        self._log_override_debug(kind, "Prepared strategy controls snapshot.", payload={"prepared": controls_snapshot})
        changed = False
        sel_indicators = self._get_selected_indicator_keys(kind)
        indicators_value = sorted({str(k).strip() for k in sel_indicators if str(k).strip()}) if sel_indicators else []
        indicators_tuple = tuple(indicators_value)
        for sym in symbols:
            if not sym:
                self._log_override_debug(kind, "Skipping empty symbol after normalization.")
                continue
            for iv in intervals:
                if not iv:
                    self._log_override_debug(kind, "Skipping empty interval after normalization.", payload={"symbol": sym})
                    continue
                key = (sym, iv, indicators_tuple)
                if key in existing_keys:
                    entry = existing_keys[key]
                    if indicators_value:
                        entry["indicators"] = list(indicators_value)
                    else:
                        entry.pop("indicators", None)
                    if controls_snapshot:
                        entry["strategy_controls"] = copy.deepcopy(controls_snapshot)
                    else:
                        entry.pop("strategy_controls", None)
                    changed = True
                    self._log_override_debug(
                        kind,
                        "Updated existing override entry.",
                        payload={"symbol": sym, "interval": iv, "indicators": indicators_value},
                    )
                    continue
                new_entry = {"symbol": sym, "interval": iv}
                if indicators_value:
                    new_entry["indicators"] = list(indicators_value)
                if controls_snapshot:
                    new_entry["strategy_controls"] = copy.deepcopy(controls_snapshot)
                pairs_cfg.append(new_entry)
                existing_keys[key] = new_entry
                changed = True
                self._log_override_debug(
                    kind,
                    "Appended new override entry.",
                    payload={"symbol": sym, "interval": iv, "indicators": indicators_value},
                )
        if changed:
            self._log_override_debug(kind, "Changes detected, refreshing table.", payload={"total_entries": len(pairs_cfg)})
            self._refresh_symbol_interval_pairs(kind)
        for widget in (symbol_list, interval_list):
            try:
                for i in range(widget.count()):
                    item = widget.item(i)
                    if item:
                        item.setSelected(False)
            except Exception:
                pass
        self._log_override_debug(
            kind,
            "Add-selected completed.",
            payload={"final_entries": len(self.config.get(ctx.get("config_key"), []))},
        )
    except Exception:
        try:
            tb_text = traceback.format_exc()
            self._log_override_debug(kind, "Exception while adding overrides.", payload={"traceback": tb_text})
            self.log(f"Failed to add symbol/interval override: {tb_text}")
        except Exception:
            pass


def _remove_selected_symbol_interval_pairs(self, kind: str = "runtime"):
    if kind == "runtime" and getattr(self, "_bot_active", False):
        try:
            self.log("Stop the bot before modifying runtime overrides.")
        except Exception:
            pass
        return
    ctx = self._override_ctx(kind)
    table = ctx.get("table")
    if table is None:
        return
    column_map = ctx.get("column_map") or {}
    symbol_col = column_map.get("Symbol", 0)
    interval_col = column_map.get("Interval", 1)
    try:
        rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            return
        pairs_cfg = self._override_config_list(kind)
        updated = []
        remove_set = set()
        for row in rows:
            sym_item = table.item(row, symbol_col)
            iv_item = table.item(row, interval_col)
            sym = sym_item.text().strip().upper() if sym_item else ""
            iv = iv_item.text().strip() if iv_item else ""
            if not (sym and iv):
                continue
            indicators_raw = None
            exact_match = True
            try:
                entry_data = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
            except Exception:
                entry_data = None
            if isinstance(entry_data, dict):
                indicators_raw = entry_data.get("indicators")
            else:
                exact_match = False
            indicators_norm = _normalize_indicator_values_list(indicators_raw)
            if exact_match:
                remove_set.add((sym, iv, tuple(indicators_norm)))
            else:
                remove_set.add((sym, iv, None))
        for entry in pairs_cfg:
            if not isinstance(entry, dict):
                continue
            sym = str(entry.get("symbol") or "").strip().upper()
            iv = str(entry.get("interval") or "").strip()
            indicators_raw = entry.get("indicators")
            indicators_norm = _normalize_indicator_values_list(indicators_raw)
            key = (sym, iv, tuple(indicators_norm))
            if key in remove_set or (sym, iv, None) in remove_set:
                continue
            new_entry = {"symbol": sym, "interval": iv}
            if indicators_norm:
                new_entry["indicators"] = list(indicators_norm)
            updated.append(new_entry)
        cfg_key = ctx.get("config_key")
        if cfg_key:
            self.config[cfg_key] = updated
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = list(updated)
                except Exception:
                    pass
        self._refresh_symbol_interval_pairs(kind)
    except Exception:
        pass


def _clear_symbol_interval_pairs(self, kind: str = "runtime"):
    if kind == "runtime" and getattr(self, "_bot_active", False):
        try:
            self.log("Stop the bot before modifying runtime overrides.")
        except Exception:
            pass
        return
    ctx = self._override_ctx(kind)
    cfg_key = ctx.get("config_key")
    if not cfg_key:
        return
    try:
        self.config[cfg_key] = []
        if kind == "backtest":
            try:
                self.backtest_config[cfg_key] = []
            except Exception:
                pass
        self._refresh_symbol_interval_pairs(kind)
    except Exception:
        pass


def _create_override_group(self, kind: str, symbol_list, interval_list) -> QtWidgets.QGroupBox:
    group = QtWidgets.QGroupBox("Symbol / Interval Overrides")
    layout = QtWidgets.QVBoxLayout(group)
    columns = ["Symbol", "Interval"]
    show_indicators = kind in ("runtime", "backtest")
    if show_indicators:
        columns.append("Indicators")
    include_loop = kind in ("runtime", "backtest")
    include_leverage = kind in ("runtime", "backtest")
    if include_loop:
        columns.append("Loop")
    if include_leverage:
        columns.append("Leverage")
    columns.append("Connector")
    columns.append("Strategy Controls")
    columns.append("Stop-Loss")
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    column_map = {name: idx for idx, name in enumerate(columns)}
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    try:
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    except Exception:
        pass
    try:
        header.setSectionsMovable(True)
    except Exception:
        pass
    table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setMinimumHeight(180)
    try:
        table.verticalHeader().setDefaultSectionSize(28)
    except Exception:
        pass
    try:
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    except Exception:
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
    table.setSortingEnabled(True)
    layout.addWidget(table)

    btn_layout = QtWidgets.QHBoxLayout()
    add_btn = QtWidgets.QPushButton("Add Selected")
    add_btn.clicked.connect(lambda _, k=kind: self._add_selected_symbol_interval_pairs(k))
    btn_layout.addWidget(add_btn)
    remove_btn = QtWidgets.QPushButton("Remove Selected")
    remove_btn.clicked.connect(lambda _, k=kind: self._remove_selected_symbol_interval_pairs(k))
    btn_layout.addWidget(remove_btn)
    clear_btn = QtWidgets.QPushButton("Clear All")
    clear_btn.clicked.connect(lambda _, k=kind: self._clear_symbol_interval_pairs(k))
    btn_layout.addWidget(clear_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)
    config_key = "runtime_symbol_interval_pairs" if kind == "runtime" else "backtest_symbol_interval_pairs"
    self.override_contexts[kind] = {
        "table": table,
        "symbol_list": symbol_list,
        "interval_list": interval_list,
        "config_key": config_key,
        "add_btn": add_btn,
        "remove_btn": remove_btn,
        "clear_btn": clear_btn,
        "column_map": column_map,
    }
    if kind == "runtime":
        self.pair_add_btn = add_btn
        self.pair_remove_btn = remove_btn
        self.pair_clear_btn = clear_btn
    lock_widgets = getattr(self, "_runtime_lock_widgets", None)
    if isinstance(lock_widgets, list):
        for widget in (table, add_btn, remove_btn, clear_btn):
            if widget and widget not in lock_widgets:
                lock_widgets.append(widget)
    self._refresh_symbol_interval_pairs(kind)
    return group
