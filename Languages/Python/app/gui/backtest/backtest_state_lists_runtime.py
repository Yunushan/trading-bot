from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .backtest_state_context_runtime import (
    get_backtest_interval_order,
    normalize_backtest_interval_value,
    normalize_backtest_interval_values,
)


def populate_backtest_lists(self):
    try:
        if not self.backtest_symbols_all:
            fallback_ordered: list[str] = []

            def _extend_unique(seq):
                for sym in seq or []:
                    sym_up = str(sym).strip().upper()
                    if not sym_up:
                        continue
                    if sym_up not in fallback_ordered:
                        fallback_ordered.append(sym_up)

            _extend_unique(self.backtest_config.get("symbols"))
            _extend_unique(self.config.get("symbols"))
            try:
                if hasattr(self, "symbol_list"):
                    for i in range(self.symbol_list.count()):
                        item = self.symbol_list.item(i)
                        if item:
                            _extend_unique([item.text()])
            except Exception:
                pass
            if not fallback_ordered:
                fallback_ordered.append("BTCUSDT")
            self.backtest_symbols_all = list(fallback_ordered)
        self._update_backtest_symbol_list(self.backtest_symbols_all)
    except Exception:
        pass

    interval_candidates: list[str] = []

    def _extend_interval(seq):
        for iv_norm in normalize_backtest_interval_values(seq):
            if not iv_norm:
                continue
            if iv_norm not in interval_candidates:
                interval_candidates.append(iv_norm)

    _extend_interval(self.backtest_config.get("intervals"))
    try:
        if hasattr(self, "interval_list"):
            for i in range(self.interval_list.count()):
                item = self.interval_list.item(i)
                if item:
                    _extend_interval([item.text()])
    except Exception:
        pass
    _extend_interval(get_backtest_interval_order())
    if not interval_candidates:
        interval_candidates.append("1h")

    interval_order = get_backtest_interval_order()
    ordered_intervals = [iv for iv in interval_order if iv in interval_candidates]
    extras = [iv for iv in interval_candidates if iv not in interval_order]
    full_order = ordered_intervals + extras

    selected_intervals = [iv for iv in normalize_backtest_interval_values(self.backtest_config.get("intervals")) if iv in full_order]
    if not selected_intervals and full_order:
        selected_intervals = [full_order[0]]
    with QtCore.QSignalBlocker(self.backtest_interval_list):
        self.backtest_interval_list.clear()
        for iv in full_order:
            item = QtWidgets.QListWidgetItem(iv)
            self.backtest_interval_list.addItem(item)
            item.setSelected(iv in selected_intervals)
    self.backtest_config["intervals"] = list(selected_intervals)
    cfg = self.config.setdefault("backtest", {})
    cfg["intervals"] = list(selected_intervals)
    self._backtest_store_intervals()


def set_backtest_symbol_selection(self, symbols):
    symbols_upper = {str(s).upper() for s in (symbols or []) if s}
    with QtCore.QSignalBlocker(self.backtest_symbol_list):
        for i in range(self.backtest_symbol_list.count()):
            item = self.backtest_symbol_list.item(i)
            if not item:
                continue
            item.setSelected(item.text().upper() in symbols_upper)
    self._backtest_store_symbols()


def apply_backtest_symbol_selection_rule(self, rule: dict | None) -> bool:
    if not rule:
        return True
    rule_type = str(rule.get("type") or "").lower()
    if rule_type == "top_volume":
        try:
            count = int(rule.get("count", 0) or 0)
        except Exception:
            count = 0
        if count <= 0:
            return True
        symbols_pool = list(self.backtest_symbols_all or [])
        if len(symbols_pool) < count:
            return False
        selection = [sym.upper() for sym in symbols_pool[:count]]
        self._set_backtest_symbol_selection(selection)
        try:
            self.backtest_symbol_list.scrollToTop()
        except Exception:
            pass
        try:
            self.backtest_status_label.setText(
                f"Template applied: selected top {count} volume symbols."
            )
        except Exception:
            pass
        return True
    return False


def set_backtest_interval_selection(self, intervals):
    intervals_norm = set(normalize_backtest_interval_values(intervals))
    with QtCore.QSignalBlocker(self.backtest_interval_list):
        for i in range(self.backtest_interval_list.count()):
            item = self.backtest_interval_list.item(i)
            if not item:
                continue
            item.setSelected(item.text() in intervals_norm)
    self._backtest_store_intervals()


def update_backtest_symbol_list(self, candidates):
    try:
        candidates = [str(sym).upper() for sym in (candidates or []) if sym]
        unique_candidates: list[str] = []
        seen = set()
        for sym in candidates:
            if sym and sym not in seen:
                seen.add(sym)
                unique_candidates.append(sym)
        selected_cfg = [
            str(s).upper()
            for s in (self.backtest_config.get("symbols") or [])
            if s
        ]
        selected = [s for s in selected_cfg if s in unique_candidates]
        if not unique_candidates and selected_cfg:
            unique_candidates = []
            seen.clear()
            for sym in selected_cfg:
                if sym and sym not in seen:
                    seen.add(sym)
                    unique_candidates.append(sym)
            selected = list(unique_candidates)
        if not selected and unique_candidates:
            selected = [unique_candidates[0]]
        selected_set = {str(sym).upper() for sym in (selected or []) if sym}
        try:
            self.backtest_symbol_list.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            with QtCore.QSignalBlocker(self.backtest_symbol_list):
                self.backtest_symbol_list.clear()
                if unique_candidates:
                    self.backtest_symbol_list.addItems(unique_candidates)
                    if selected_set:
                        for i in range(self.backtest_symbol_list.count()):
                            item = self.backtest_symbol_list.item(i)
                            if item and item.text().upper() in selected_set:
                                item.setSelected(True)
        finally:
            try:
                self.backtest_symbol_list.setUpdatesEnabled(True)
            except Exception:
                pass
        self.backtest_symbols_all = list(unique_candidates)
        self.backtest_config["symbols"] = list(selected)
        cfg = self.config.setdefault("backtest", {})
        cfg["symbols"] = list(selected)
        if unique_candidates and not selected and self.backtest_symbol_list.count():
            self.backtest_symbol_list.item(0).setSelected(True)
        self._backtest_store_symbols()
    except Exception:
        pass


def backtest_store_symbols(self):
    try:
        symbols = []
        for i in range(self.backtest_symbol_list.count()):
            item = self.backtest_symbol_list.item(i)
            if item and item.isSelected():
                symbols.append(item.text().upper())
        self.backtest_config["symbols"] = symbols
        cfg = self.config.setdefault("backtest", {})
        cfg["symbols"] = list(symbols)
    except Exception:
        pass


def backtest_store_intervals(self):
    try:
        intervals = []
        for i in range(self.backtest_interval_list.count()):
            item = self.backtest_interval_list.item(i)
            if item and item.isSelected():
                interval_text = normalize_backtest_interval_value(item.text())
                if interval_text and interval_text not in intervals:
                    intervals.append(interval_text)
        self.backtest_config["intervals"] = intervals
        cfg = self.config.setdefault("backtest", {})
        cfg["intervals"] = list(intervals)
    except Exception:
        pass


def apply_backtest_intervals_to_dashboard(self):
    try:
        intervals = normalize_backtest_interval_values(self.backtest_config.get("intervals"))
    except Exception:
        intervals = []
    if not intervals:
        intervals = list(get_backtest_interval_order())
    existing = {
        normalize_backtest_interval_value(self.interval_list.item(i).text())
        for i in range(self.interval_list.count())
        if self.interval_list.item(i) is not None
    }
    for iv in intervals:
        if iv not in existing:
            self.interval_list.addItem(QtWidgets.QListWidgetItem(iv))
    with QtCore.QSignalBlocker(self.interval_list):
        for i in range(self.interval_list.count()):
            item = self.interval_list.item(i)
            if item is None:
                continue
            item.setSelected(item.text() in intervals)
    try:
        self.config["intervals"] = list(intervals)
    except Exception:
        pass
    try:
        self._reconfigure_positions_worker()
    except Exception:
        pass
