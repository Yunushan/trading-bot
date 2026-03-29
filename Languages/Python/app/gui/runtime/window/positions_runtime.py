from __future__ import annotations

import time

from PyQt6 import QtCore, QtWidgets


_NUMERIC_ITEM_CLS = None
_WAITING_POSITION_LATE_THRESHOLD = 45.0


def configure_main_window_positions_runtime(
    *,
    numeric_item_cls=None,
    waiting_position_late_threshold: float = 45.0,
) -> None:
    global _NUMERIC_ITEM_CLS
    global _WAITING_POSITION_LATE_THRESHOLD

    _NUMERIC_ITEM_CLS = numeric_item_cls
    _WAITING_POSITION_LATE_THRESHOLD = float(waiting_position_late_threshold)


def _mw_reconfigure_positions_worker(self, symbols=None):
    try:
        worker = getattr(self, "_pos_worker", None)
        if worker is None:
            return

        selected_symbols: list[str] = []
        try:
            symbol_list = getattr(self, "symbol_list", None)
            if symbol_list is not None:
                for idx in range(symbol_list.count()):
                    item = symbol_list.item(idx)
                    if item is None or not item.isSelected():
                        continue
                    text = str(item.text() or "").strip().upper()
                    if text:
                        selected_symbols.append(text)
        except Exception:
            selected_symbols = []

        extra_symbols: list[str] = []
        if symbols:
            for sym in symbols:
                try:
                    text = str(sym or "").strip().upper()
                except Exception:
                    text = ""
                if text:
                    extra_symbols.append(text)

        def _dedupe(seq: list[str]) -> list[str]:
            return list(dict.fromkeys(seq))

        selected_symbols = _dedupe(selected_symbols)
        extra_symbols = _dedupe(extra_symbols)

        if selected_symbols:
            target_symbols = _dedupe(selected_symbols + extra_symbols)
        else:
            target_symbols = None

        worker.configure(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
            symbols=target_symbols or None,
            connector_backend=self._runtime_connector_backend(suppress_refresh=True),
        )
        setattr(self, "_pos_symbol_filter", target_symbols)
    except Exception:
        pass


def _mw_collect_strategy_intervals(self, symbol: str, side_key: str):
    intervals = set()
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        sym_upper = (symbol or "").upper()
        side_key_upper = (side_key or "").upper()
        for eng in engines.values():
            cfg = getattr(eng, "config", {}) or {}
            cfg_sym = str(cfg.get("symbol") or "").upper()
            if not cfg_sym or cfg_sym != sym_upper:
                continue
            interval = str(cfg.get("interval") or "").strip()
            if not interval:
                continue
            side_pref = str(cfg.get("side") or "BOTH").upper()
            if side_pref in ("BUY", "LONG"):
                allowed = {"L"}
            elif side_pref in ("SELL", "SHORT"):
                allowed = {"S"}
            else:
                allowed = {"L", "S"}
            if side_key_upper in allowed:
                intervals.add(interval)
    except Exception:
        pass
    return intervals


def _mw_refresh_waiting_positions_tab(self):
    table = getattr(self, "waiting_pos_table", None)
    if table is None:
        return
    history = getattr(self, "_waiting_positions_history", None)
    if not isinstance(history, list):
        history = []
        self._waiting_positions_history = history
    last_snapshot = getattr(self, "_waiting_positions_last_snapshot", None)
    if not isinstance(last_snapshot, dict):
        last_snapshot = {}
        self._waiting_positions_last_snapshot = last_snapshot
    history_max = getattr(self, "_waiting_positions_history_max", None)
    try:
        history_max = int(history_max)
    except Exception:
        history_max = 500
    if history_max <= 0:
        history_max = 500
    self._waiting_positions_history_max = history_max
    try:
        guard = getattr(self, "guard", None)
    except Exception:
        guard = None
    snapshot = []
    snapshot_ok = False
    if guard is not None and hasattr(guard, "snapshot_pending_attempts"):
        try:
            raw = guard.snapshot_pending_attempts() or []
            snapshot = [item for item in raw if isinstance(item, dict)]
            snapshot_ok = True
        except Exception:
            snapshot = []
            snapshot_ok = False
    current_entries = []
    current_keys = set()
    for item in snapshot:
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        age_seconds = max(0, int(age_val))
        state = "Late" if age_val >= _WAITING_POSITION_LATE_THRESHOLD else "Queued"
        key = (symbol, interval, side, context)
        current_entries.append(
            {
                "symbol": symbol,
                "interval": interval,
                "side": side,
                "context": context,
                "age": age_val,
                "age_seconds": age_seconds,
                "state": state,
                "key": key,
            }
        )
        current_keys.add(key)
    if snapshot_ok:
        ended_keys = set(last_snapshot.keys()) - current_keys
        if ended_keys:
            now = time.time()
            for key in ended_keys:
                ended_entry = last_snapshot.get(key)
                if not isinstance(ended_entry, dict):
                    continue
                ended_copy = dict(ended_entry)
                ended_copy["state"] = "Ended"
                ended_copy["ended_at"] = now
                history.append(ended_copy)
        if len(history) > history_max:
            history = history[-history_max:]
            self._waiting_positions_history = history
        self._waiting_positions_last_snapshot = {entry["key"]: entry for entry in current_entries}
    combined_entries = current_entries + history
    table.setSortingEnabled(False)
    table.setRowCount(len(combined_entries))
    if not combined_entries:
        table.clearContents()
        table.setSortingEnabled(True)
        return
    try:
        combined_entries.sort(
            key=lambda item: (
                1 if str(item.get("state") or "").lower() == "ended" else 0,
                -float(str(item.get("age") or 0.0)),
                str(item.get("symbol") or ""),
            )
        )
    except Exception:
        pass
    for row, item in enumerate(combined_entries):
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        try:
            age_seconds = int(item.get("age_seconds"))
        except Exception:
            age_seconds = max(0, int(age_val))
        state = str(item.get("state") or "")
        if not state:
            state = "Late" if age_val >= _WAITING_POSITION_LATE_THRESHOLD else "Queued"

        symbol_item = QtWidgets.QTableWidgetItem(symbol)
        symbol_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, symbol_item)

        interval_item = QtWidgets.QTableWidgetItem(interval)
        interval_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 1, interval_item)

        side_item = QtWidgets.QTableWidgetItem(side.title() if side not in ("-", "") else "-")
        side_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 2, side_item)

        context_item = QtWidgets.QTableWidgetItem(context or "-")
        table.setItem(row, 3, context_item)

        state_item = QtWidgets.QTableWidgetItem(state)
        state_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 4, state_item)

        try:
            age_item = _NUMERIC_ITEM_CLS(f"{age_seconds}", age_val)
        except Exception:
            age_item = QtWidgets.QTableWidgetItem(f"{age_seconds}")
        table.setItem(row, 5, age_item)
    table.setSortingEnabled(True)
