from __future__ import annotations

from . import control_shared_runtime


def on_leverage_changed(self, value):
    try:
        value_int = int(value)
    except Exception:
        value_int = 0
    try:
        self.config["leverage"] = value_int
    except Exception:
        pass
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        for eng in engines.values():
            try:
                conf = getattr(eng, "config", None)
                if isinstance(conf, dict):
                    conf["leverage"] = value_int
            except Exception:
                pass
    except Exception:
        pass
    try:
        if (
            value_int > 0
            and hasattr(self, "shared_binance")
            and self.shared_binance
            and (self.account_combo.currentText() or "").upper().startswith("FUT")
        ):
            self.shared_binance.set_futures_leverage(value_int)
    except Exception:
        pass


def refresh_symbols(self):
    from app.gui.runtime.background_workers import CallWorker as _CallWorker

    self.refresh_symbols_btn.setEnabled(False)
    self.refresh_symbols_btn.setText("Refreshing...")

    def _do():
        tmp_wrapper = self._create_binance_wrapper(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
        )
        return tmp_wrapper.fetch_symbols(
            sort_by_volume=True,
            top_n=control_shared_runtime._get_symbol_fetch_top_n(),
        )

    def _done(res, err):
        try:
            if err or not res:
                self.log(f"Failed to refresh symbols: {err or 'no symbols'}")
                return
            self.symbol_list.clear()
            all_symbols = []
            filtered = []
            seen = set()
            for sym in res or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm or sym_norm in seen:
                    continue
                seen.add(sym_norm)
                all_symbols.append(sym_norm)
                if sym_norm.endswith("USDT"):
                    filtered.append(sym_norm)
            if filtered:
                self.symbol_list.addItems(filtered)
            if all_symbols:
                self.chart_symbol_cache["Futures"] = all_symbols
            current_market = self._normalize_chart_market(
                getattr(self, "chart_market_combo", None).currentText()
                if hasattr(self, "chart_market_combo")
                else None
            )
            if current_market == "Futures":
                self._update_chart_symbol_options(all_symbols if all_symbols else filtered)
                self._chart_needs_render = True
                if self.chart_auto_follow and not self._chart_manual_override:
                    self._apply_dashboard_selection_to_chart(load=True)
                elif self._chart_pending_initial_load or self._is_chart_visible():
                    self.load_chart(auto=True)
            self.log(
                f"Loaded {self.symbol_list.count()} USDT-pair symbols for {self.account_combo.currentText()}."
            )
        finally:
            self.refresh_symbols_btn.setEnabled(True)
            self.refresh_symbols_btn.setText("Refresh Symbols")

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.start()


def apply_futures_modes(self):
    from app.gui.runtime.background_workers import CallWorker as _CallWorker

    mm = self.margin_mode_combo.currentText().upper()
    pos_mode = self.position_mode_combo.currentText()
    hedge = pos_mode.strip().lower() == "hedge"
    assets_mode_value = self.assets_mode_combo.currentData() or self.assets_mode_combo.currentText()
    assets_mode_norm = self._normalize_assets_mode(assets_mode_value)
    multi = assets_mode_norm == "Multi-Assets"
    tif = self.tif_combo.currentText()
    gtdm = int(self.gtd_minutes_spin.value())

    def _do():
        try:
            self.shared_binance.set_position_mode(hedge)
        except Exception:
            pass
        try:
            self.shared_binance.set_multi_assets_mode(multi)
        except Exception:
            pass
        return True

    def _done(res, err):
        if err:
            self.log(f"Apply futures modes error: {err}")
            return
        self.config["margin_mode"] = "Isolated" if mm == "ISOLATED" else "Cross"
        self.config["position_mode"] = "Hedge" if hedge else "One-way"
        self.config["assets_mode"] = "Multi-Assets" if multi else "Single-Asset"
        self.config["tif"] = tif
        self.config["gtd_minutes"] = gtdm

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.start()
