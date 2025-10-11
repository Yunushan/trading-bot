import sys

# Version banner / environment setup must run before importing PyQt modules
from app import preamble  # noqa: F401

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# Ensure Windows taskbar uses our icon (AppUserModelID)
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Binance.TradingBot")
except Exception:
    pass

from app.gui.main_window import MainWindow
from app.gui.app_icon import load_app_icon


_previous_qt_message_handler = None


def _install_qt_warning_filter():
    """Suppress nuisance Qt warnings we cannot control."""
    target = "setHighDpiScaleFactorRoundingPolicy"

    def handler(mode, context, message):
        if target in message:
            return
        if _previous_qt_message_handler is not None:
            _previous_qt_message_handler(mode, context, message)

    handler.__name__ = "qt_warning_filter"
    global _previous_qt_message_handler
    _previous_qt_message_handler = QtCore.qInstallMessageHandler(handler)

def main():
    _install_qt_warning_filter()
    app = QApplication(sys.argv)
    icon = QtGui.QIcon()
    try:
        app.setApplicationDisplayName("Binance Trading Bot")
        icon = load_app_icon()
        if not icon.isNull():
            app.setApplicationName("Binance Trading Bot")
            app.setWindowIcon(icon)
            QtGui.QGuiApplication.setWindowIcon(icon)
    except Exception:
        icon = QtGui.QIcon()
    win = MainWindow()
    try:
        if not icon.isNull():
            win.setWindowIcon(icon)
    except Exception:
        pass
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
