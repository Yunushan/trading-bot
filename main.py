import sys

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# Ensure Windows taskbar uses our icon (AppUserModelID)
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Binance.TradingBot")
except Exception:
    pass

# Version banner
from app import preamble  # noqa: F401

from app.gui.main_window import MainWindow
from pathlib import Path as _P

def main():
    if QtGui.QGuiApplication.instance() is None:
        QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    try:
        app.setApplicationDisplayName("Binance Trading Bot")
        app.setWindowIcon(QtGui.QIcon(str(_P(__file__).resolve().parent / 'app' / 'assets' / 'binance_icon.ico')))
    except Exception:
        pass
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
