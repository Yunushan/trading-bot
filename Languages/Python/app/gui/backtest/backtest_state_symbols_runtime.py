from __future__ import annotations

from app.gui.runtime.background_workers import CallWorker

from .backtest_state_context_runtime import get_symbol_fetch_top_n


def update_backtest_futures_controls(self):
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


def backtest_symbol_source_changed(self, text: str):
    self._update_backtest_config("symbol_source", text)
    self._update_backtest_futures_controls()
    self._refresh_backtest_connector_options(text, force_default=True)
    self._refresh_backtest_symbols()


def refresh_backtest_symbols(self):
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
            top_n=get_symbol_fetch_top_n(),
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


def on_backtest_symbols_ready(self, result, error, source_label):
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

