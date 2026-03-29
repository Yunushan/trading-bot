from __future__ import annotations

from datetime import datetime

from PyQt6 import QtCore, QtWidgets

from app.gui.runtime.background_workers import CallWorker

_BACKTEST_INTERVAL_ORDER: tuple[str, ...] = ()
_SIDE_LABELS: dict[str, str] = {}
_SYMBOL_FETCH_TOP_N = 200


def _coerce_qdate(value):
    if isinstance(value, QtCore.QDate):
        return value
    if isinstance(value, datetime):
        return QtCore.QDate(value.year, value.month, value.day)
    if isinstance(value, str):
        for fmt in ("yyyy-MM-dd", "yyyy/MM/dd", "dd.MM.yyyy"):
            qd = QtCore.QDate.fromString(value, fmt)
            if qd.isValid():
                return qd
        try:
            dt = datetime.fromisoformat(value)
            return QtCore.QDate(dt.year, dt.month, dt.day)
        except Exception:
            pass
    return QtCore.QDate.currentDate()


def _coerce_qdatetime(value):
    if isinstance(value, QtCore.QDateTime):
        return value
    if isinstance(value, datetime):
        return QtCore.QDateTime(value)
    if isinstance(value, str):
        from datetime import datetime as _dt

        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                dt = _dt.strptime(value, fmt)
                return QtCore.QDateTime(
                    QtCore.QDate(dt.year, dt.month, dt.day),
                    QtCore.QTime(dt.hour, dt.minute),
                )
            except Exception:
                continue
        try:
            dt = _dt.fromisoformat(value)
            return QtCore.QDateTime(
                QtCore.QDate(dt.year, dt.month, dt.day),
                QtCore.QTime(dt.hour, dt.minute),
            )
        except Exception:
            pass
    return QtCore.QDateTime.currentDateTime()


def _initialize_backtest_ui_defaults(self):
    fetch_triggered = False
    try:
        source = self.backtest_config.get("symbol_source") or "Futures"
        idx = self.backtest_symbol_source_combo.findText(source)
        if (
            idx is not None
            and idx >= 0
            and self.backtest_symbol_source_combo.currentIndex() != idx
        ):
            self.backtest_symbol_source_combo.setCurrentIndex(idx)
            fetch_triggered = True
    except Exception:
        pass
    try:
        self._populate_backtest_lists()
    except Exception:
        pass
    try:
        if self.backtest_stop_btn is not None:
            self.backtest_stop_btn.setEnabled(False)
    except Exception:
        pass
    try:
        logic = (self.backtest_config.get("logic") or "AND").upper()

        def _set_combo(combo: QtWidgets.QComboBox, value: str):
            if combo is None:
                return
            try:
                target = (value or "").strip().lower()
                for i in range(combo.count()):
                    if combo.itemText(i).strip().lower() == target:
                        combo.setCurrentIndex(i)
                        return
            except Exception:
                pass

        _set_combo(self.backtest_logic_combo, logic)
        capital = float(self.backtest_config.get("capital", 1000.0))
        self.backtest_capital_spin.setValue(capital)
        pct_cfg = float(self.backtest_config.get("position_pct", 2.0) or 0.0)
        if pct_cfg <= 1.0:
            pct_disp = pct_cfg * 100.0
            self.backtest_pospct_spin.setValue(pct_disp)
            self._update_backtest_config("position_pct", pct_disp)
        else:
            self.backtest_pospct_spin.setValue(pct_cfg)
        side_cfg = (self.backtest_config.get("side") or "BOTH").upper()
        side_label = _SIDE_LABELS.get(side_cfg, _SIDE_LABELS["BOTH"])
        try:
            idx_side = self.backtest_side_combo.findText(
                side_label,
                QtCore.Qt.MatchFlag.MatchFixedString,
            )
        except Exception:
            idx_side = self.backtest_side_combo.findText(side_label)
        if idx_side is not None and idx_side >= 0:
            self.backtest_side_combo.setCurrentIndex(idx_side)
        margin_mode_cfg = self.backtest_config.get("margin_mode") or "Isolated"
        _set_combo(self.backtest_margin_mode_combo, margin_mode_cfg)
        position_mode_cfg = self.backtest_config.get("position_mode") or "Hedge"
        _set_combo(self.backtest_position_mode_combo, position_mode_cfg)
        assets_mode_cfg = self._normalize_assets_mode(
            self.backtest_config.get("assets_mode")
        )
        idx_assets = self.backtest_assets_mode_combo.findData(assets_mode_cfg)
        if idx_assets is not None and idx_assets >= 0:
            with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                self.backtest_assets_mode_combo.setCurrentIndex(idx_assets)
        account_mode_cfg = self._normalize_account_mode(
            self.backtest_config.get("account_mode")
        )
        idx_account_mode = self.backtest_account_mode_combo.findData(account_mode_cfg)
        if idx_account_mode is not None and idx_account_mode >= 0:
            with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                self.backtest_account_mode_combo.setCurrentIndex(idx_account_mode)
        leverage_cfg = int(self.backtest_config.get("leverage", 5) or 1)
        self.backtest_leverage_spin.setValue(leverage_cfg)
        loop_cfg = (
            self._normalize_loop_override(
                self.backtest_config.get("loop_interval_override")
            )
            or ""
        )
        if hasattr(self, "backtest_loop_combo"):
            self._set_loop_combo_value(self.backtest_loop_combo, loop_cfg)
        self.backtest_config["loop_interval_override"] = loop_cfg
        now_dt = QtCore.QDateTime.currentDateTime()
        start_cfg = self.backtest_config.get("start_date")
        end_cfg = self.backtest_config.get("end_date")
        end_qdt = self._coerce_qdatetime(end_cfg) if end_cfg else now_dt
        if not end_qdt.isValid():
            end_qdt = now_dt
        start_qdt = self._coerce_qdatetime(start_cfg) if start_cfg else end_qdt.addMonths(-3)
        if not start_qdt.isValid() or start_qdt > end_qdt:
            start_qdt = end_qdt.addMonths(-3)
        self.backtest_start_edit.setDateTime(start_qdt)
        self.backtest_end_edit.setDateTime(end_qdt)
    except Exception:
        pass
    try:
        self._update_backtest_stop_loss_widgets()
    except Exception:
        pass
    self._update_backtest_futures_controls()
    if not fetch_triggered:
        self._refresh_backtest_symbols()


def _populate_backtest_lists(self):
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
        for iv in seq or []:
            iv_norm = str(iv).strip()
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
    _extend_interval(_BACKTEST_INTERVAL_ORDER)
    if not interval_candidates:
        interval_candidates.append("1h")

    ordered_intervals = [iv for iv in _BACKTEST_INTERVAL_ORDER if iv in interval_candidates]
    extras = [iv for iv in interval_candidates if iv not in _BACKTEST_INTERVAL_ORDER]
    full_order = ordered_intervals + extras

    selected_intervals = [
        iv
        for iv in (self.backtest_config.get("intervals") or [])
        if iv in full_order
    ]
    if not selected_intervals and full_order:
        selected_intervals = [full_order[0]]
    with QtCore.QSignalBlocker(self.backtest_interval_list):
        self.backtest_interval_list.clear()
        for iv in full_order:
            item = QtWidgets.QListWidgetItem(iv)
            item.setSelected(iv in selected_intervals)
            self.backtest_interval_list.addItem(item)
    self.backtest_config["intervals"] = list(selected_intervals)
    cfg = self.config.setdefault("backtest", {})
    cfg["intervals"] = list(selected_intervals)
    self._backtest_store_intervals()


def _set_backtest_symbol_selection(self, symbols):
    symbols_upper = {str(s).upper() for s in (symbols or []) if s}
    with QtCore.QSignalBlocker(self.backtest_symbol_list):
        for i in range(self.backtest_symbol_list.count()):
            item = self.backtest_symbol_list.item(i)
            if not item:
                continue
            item.setSelected(item.text().upper() in symbols_upper)
    self._backtest_store_symbols()


def _apply_backtest_symbol_selection_rule(self, rule: dict | None) -> bool:
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


def _set_backtest_interval_selection(self, intervals):
    intervals_norm = {str(iv) for iv in (intervals or []) if iv}
    with QtCore.QSignalBlocker(self.backtest_interval_list):
        for i in range(self.backtest_interval_list.count()):
            item = self.backtest_interval_list.item(i)
            if not item:
                continue
            item.setSelected(item.text() in intervals_norm)
    self._backtest_store_intervals()


def _update_backtest_symbol_list(self, candidates):
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


def _backtest_store_symbols(self):
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


def _backtest_store_intervals(self):
    try:
        intervals = []
        for i in range(self.backtest_interval_list.count()):
            item = self.backtest_interval_list.item(i)
            if item and item.isSelected():
                intervals.append(item.text())
        self.backtest_config["intervals"] = intervals
        cfg = self.config.setdefault("backtest", {})
        cfg["intervals"] = list(intervals)
    except Exception:
        pass


def _apply_backtest_intervals_to_dashboard(self):
    try:
        intervals = [
            str(iv).strip()
            for iv in (self.backtest_config.get("intervals") or [])
            if str(iv).strip()
        ]
    except Exception:
        intervals = []
    if not intervals:
        intervals = list(_BACKTEST_INTERVAL_ORDER)
    existing = {self.interval_list.item(i).text() for i in range(self.interval_list.count())}
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


def _update_backtest_futures_controls(self):
    try:
        source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip().lower()
        is_futures = source.startswith("fut")
    except Exception:
        is_futures = True
    for widget in getattr(self, "_backtest_futures_widgets", []):
        if widget is None:
            continue
        try:
            widget.setVisible(is_futures)
            widget.setEnabled(is_futures)
        except Exception:
            pass


def _backtest_symbol_source_changed(self, text: str):
    self._update_backtest_config("symbol_source", text)
    self._update_backtest_futures_controls()
    self._refresh_backtest_connector_options(text, force_default=True)
    self._refresh_backtest_symbols()


def _refresh_backtest_symbols(self):
    try:
        worker = getattr(self, "_backtest_symbol_worker", None)
        if worker is not None and worker.isRunning():
            return
    except Exception:
        pass
    if not hasattr(self, "backtest_refresh_symbols_btn"):
        return
    self.backtest_refresh_symbols_btn.setEnabled(False)
    self.backtest_refresh_symbols_btn.setText("Refreshing...")
    source_text = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
    source_lower = source_text.lower()
    acct = "Spot" if source_lower.startswith("spot") else "Futures"
    api_key = self.api_key_edit.text().strip()
    api_secret = self.api_secret_edit.text().strip()
    mode = self.mode_combo.currentText()

    def _do():
        wrapper = self._create_binance_wrapper(
            api_key=api_key,
            api_secret=api_secret,
            mode=mode,
            account_type=acct,
            connector_backend=self._backtest_connector_backend(),
        )
        return wrapper.fetch_symbols(
            sort_by_volume=True,
            top_n=_SYMBOL_FETCH_TOP_N,
        )

    worker = CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(lambda res, err, src=acct: self._on_backtest_symbols_ready(res, err, src))
    self._backtest_symbol_worker = worker
    try:
        self.backtest_status_label.setText(f"Refreshing {acct.upper()} symbols...")
    except Exception:
        pass
    worker.start()


def _on_backtest_symbols_ready(self, result, error, source_label):
    try:
        self.backtest_refresh_symbols_btn.setEnabled(True)
        self.backtest_refresh_symbols_btn.setText("Refresh")
    except Exception:
        pass
    self._backtest_symbol_worker = None
    if error or not result:
        msg = f"Backtest symbol refresh failed: {error or 'no symbols returned'}"
        self.log(msg)
        try:
            self.backtest_status_label.setText(msg)
        except Exception:
            pass
        return
    symbols = [str(sym).upper() for sym in (result or []) if sym]
    self.backtest_symbols_all = symbols
    self._update_backtest_symbol_list(symbols)
    if self._backtest_pending_symbol_selection:
        if self._apply_backtest_symbol_selection_rule(
            self._backtest_pending_symbol_selection
        ):
            self._backtest_pending_symbol_selection = None
    msg = f"Loaded {len(symbols)} {source_label.upper()} symbols for backtest."
    self.log(msg)
    try:
        self.backtest_status_label.setText(msg)
    except Exception:
        pass


def _backtest_dates_changed(self):
    try:
        start_dt = self.backtest_start_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
        end_dt = self.backtest_end_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
        self.backtest_config["start_date"] = start_dt
        self.backtest_config["end_date"] = end_dt
        cfg = self.config.setdefault("backtest", {})
        cfg["start_date"] = start_dt
        cfg["end_date"] = end_dt
    except Exception:
        pass


def bind_main_window_backtest_state_runtime(
    main_window_cls,
    *,
    backtest_interval_order,
    side_labels: dict[str, str],
    symbol_fetch_top_n: int,
) -> None:
    global _BACKTEST_INTERVAL_ORDER
    global _SIDE_LABELS
    global _SYMBOL_FETCH_TOP_N

    _BACKTEST_INTERVAL_ORDER = tuple(str(iv) for iv in (backtest_interval_order or ()))
    _SIDE_LABELS = dict(side_labels or {})
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))

    main_window_cls._coerce_qdate = staticmethod(_coerce_qdate)
    main_window_cls._coerce_qdatetime = staticmethod(_coerce_qdatetime)
    main_window_cls._initialize_backtest_ui_defaults = _initialize_backtest_ui_defaults
    main_window_cls._populate_backtest_lists = _populate_backtest_lists
    main_window_cls._set_backtest_symbol_selection = _set_backtest_symbol_selection
    main_window_cls._apply_backtest_symbol_selection_rule = (
        _apply_backtest_symbol_selection_rule
    )
    main_window_cls._set_backtest_interval_selection = _set_backtest_interval_selection
    main_window_cls._update_backtest_symbol_list = _update_backtest_symbol_list
    main_window_cls._backtest_store_symbols = _backtest_store_symbols
    main_window_cls._backtest_store_intervals = _backtest_store_intervals
    main_window_cls._apply_backtest_intervals_to_dashboard = (
        _apply_backtest_intervals_to_dashboard
    )
    main_window_cls._update_backtest_futures_controls = (
        _update_backtest_futures_controls
    )
    main_window_cls._backtest_symbol_source_changed = _backtest_symbol_source_changed
    main_window_cls._refresh_backtest_symbols = _refresh_backtest_symbols
    main_window_cls._on_backtest_symbols_ready = _on_backtest_symbols_ready
    main_window_cls._backtest_dates_changed = _backtest_dates_changed
