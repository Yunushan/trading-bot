import os
import sys

# Ensure Qt uses pass-through DPI rounding even when the helper is unavailable.
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

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
    app = QApplication(sys.argv)
    try:
        app.setApplicationDisplayName("Binance Trading Bot")
        assets_dir = _P(__file__).resolve().parent / 'app' / 'assets'
        icon = QtGui.QIcon(str(assets_dir / 'binance_icon.ico'))
        if icon.isNull():
            icon = QtGui.QIcon(str(assets_dir / 'binance_icon.png'))
        if not icon.isNull():
            app.setWindowIcon(icon)
    except Exception:
        pass
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
