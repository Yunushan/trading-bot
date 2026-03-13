from __future__ import annotations


def _finalize_init_ui(self):
    self._refresh_symbol_interval_pairs("runtime")
    self._refresh_symbol_interval_pairs("backtest")
    self._initialize_backtest_ui_defaults()

    self.resize(1200, 900)
    self._apply_initial_geometry()
    self.apply_theme(self.theme_combo.currentText())
    self._ui_initialized = True
    self._setup_log_buffer()
    try:
        self.ind_source_combo.currentTextChanged.connect(
            lambda v: self.config.__setitem__("indicator_source", v)
        )
    except Exception:
        pass


def bind_main_window_init_finalize_runtime(MainWindow):
    MainWindow._finalize_init_ui = _finalize_init_ui
