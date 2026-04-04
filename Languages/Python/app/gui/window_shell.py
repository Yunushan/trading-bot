from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal

try:
    import PyQt6.QtCharts  # noqa: F401

    QT_CHARTS_AVAILABLE = True
except Exception:
    QT_CHARTS_AVAILABLE = False


ENABLE_CHART_TAB = True

_THIS_FILE = Path(__file__).resolve()

if __package__ in (None, ""):
    sys.path.append(str(_THIS_FILE.parents[2]))

from app.gui.runtime.composition import (
    bindings_runtime as main_window_bindings_runtime,
    module_state_runtime as main_window_module_state_runtime,
)
from app.gui.runtime.ui import theme_styles as main_window_theme_styles
from app.gui.runtime.window import init_ui_runtime as main_window_init_ui_runtime, startup_runtime as main_window_startup_runtime


main_window_module_state_runtime.install_main_window_module_state(
    globals(),
    this_file=_THIS_FILE,
)


class MainWindow(QtWidgets.QWidget):
    log_signal = pyqtSignal(str)
    trade_signal = pyqtSignal(dict)

    # thread-safe control signals for positions worker
    req_pos_start = QtCore.pyqtSignal(int)
    req_pos_stop = QtCore.pyqtSignal()
    req_pos_set_interval = QtCore.pyqtSignal(int)

    def _on_trade_signal(self, order_info: dict):
        from app.gui.trade import trade_runtime as main_window_trade_runtime

        return main_window_trade_runtime._mw_on_trade_signal(self, order_info)

    LIGHT_THEME = main_window_theme_styles.LIGHT_THEME
    DARK_THEME = main_window_theme_styles.DARK_THEME

    def __init__(self):
        super().__init__()
        try:
            self.setWindowTitle("Trading Bot")
        except Exception:
            pass
        try:
            _apply_window_icon(self)
        except Exception:
            pass
        main_window_startup_runtime.apply_standard_window_flags(self)
        if sys.platform == "win32":
            try:
                self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
            except Exception:
                pass
            try:
                self.winId()
            except Exception:
                pass
        self._initialize_main_window_state()

    def init_ui(self):
        self.setWindowTitle("Trading Bot")
        # Allow smaller manual resize on compact screens.
        self.setMinimumSize(640, 420)
        try:
            _apply_window_icon(self)
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                delay_raw = os.environ.get("BOT_WINDOW_ICON_RETRY_MS")
                delay_ms = int(delay_raw) if delay_raw is not None else 0
            except Exception:
                delay_ms = 0
            if delay_ms > 0:
                QtCore.QTimer.singleShot(delay_ms, lambda w=self: _apply_window_icon(w))
        global MAX_CLOSED_HISTORY
        MAX_CLOSED_HISTORY = main_window_init_ui_runtime.build_main_window_tabs_ui(
            self,
            current_max_closed_history=MAX_CLOSED_HISTORY,
        )


main_window_bindings_runtime.bind_main_window_class(
    MainWindow,
    module_globals=globals(),
)
