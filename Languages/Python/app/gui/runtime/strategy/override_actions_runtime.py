from __future__ import annotations

import copy
import traceback

from PyQt6 import QtCore

from . import override_shared_runtime as shared


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
        invalid_intervals = []
        for item in interval_items:
            try:
                text = item.text()
            except Exception:
                text = ""
            text_norm = shared._canonicalize_override_interval(self, text, kind)
            if text_norm:
                intervals.append(text_norm)
            elif str(text or "").strip():
                invalid_intervals.append(str(text).strip())
        self._log_override_debug(kind, "Normalized intervals.", payload={"intervals": intervals})
        for invalid_interval in invalid_intervals:
            try:
                self.log(f"Skipping unsupported interval '{invalid_interval}' while adding overrides.")
            except Exception:
                pass

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
            iv_existing = shared._canonicalize_override_interval(self, entry.get("interval"), kind)
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
                new_entry: dict[str, object] = {"symbol": sym, "interval": iv}
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
            payload={"final_entries": len(self.config.get(ctx.get('config_key'), []))},
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
        remove_set: set[tuple[str, str, tuple[str, ...] | None]] = set()
        for row in rows:
            sym_item = table.item(row, symbol_col)
            iv_item = table.item(row, interval_col)
            sym = sym_item.text().strip().upper() if sym_item else ""
            iv_raw = iv_item.text().strip() if iv_item else ""
            iv = shared._canonicalize_override_interval(self, iv_raw, kind) or iv_raw
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
            indicators_norm = shared._normalize_indicator_values_list(indicators_raw)
            if exact_match:
                remove_set.add((sym, iv, tuple(indicators_norm)))
            else:
                remove_set.add((sym, iv, None))
        for entry in pairs_cfg:
            if not isinstance(entry, dict):
                continue
            entry_clean, indicators_norm, _, _ = shared._build_clean_override_entry(self, kind, entry)
            if not entry_clean:
                continue
            key = (
                entry_clean["symbol"],
                entry_clean["interval"],
                tuple(indicators_norm),
            )
            if key in remove_set or (entry_clean["symbol"], entry_clean["interval"], None) in remove_set:
                continue
            updated.append(entry_clean)
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
