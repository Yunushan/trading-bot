import sys
from pathlib import Path

# Ensure repo root is importable so shared helpers can be used when launched directly.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

BINANCE_DIR = Path(__file__).resolve().parent
BINANCE_DIR_STR = str(BINANCE_DIR)
if BINANCE_DIR_STR not in sys.path:
    sys.path.insert(0, BINANCE_DIR_STR)

# Version banner / environment setup must run before importing PyQt modules
from app import preamble  # noqa: F401

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.gui.app_icon import find_primary_icon_file, load_app_icon
import os
from windows_taskbar import apply_taskbar_metadata, build_relaunch_command, ensure_app_user_model_id

APP_USER_MODEL_ID = "Binance.TradingBot"


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
    ensure_app_user_model_id(APP_USER_MODEL_ID)
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
    try: # Set window icon after it's created
        if not icon.isNull():
            win.setWindowIcon(icon)
    except Exception:
        pass
    win.showMaximized()
    win.winId()
    if not icon.isNull():
        QtCore.QTimer.singleShot(0, lambda: win.setWindowIcon(icon))
    disable_taskbar = os.getenv("BOT_DISABLE_TASKBAR", "").strip() == "1"
    if sys.platform == "win32" and not disable_taskbar:
        icon_path = find_primary_icon_file()
        relaunch_cmd = build_relaunch_command()
        def _apply_taskbar(attempts: int = 4) -> None:
            if attempts <= 0:
                return
            success = apply_taskbar_metadata(
                win,
                app_id=APP_USER_MODEL_ID,
                display_name="Binance Trading Bot",
                icon_path=icon_path,
                relaunch_command=relaunch_cmd,
            )
            if not success:
                QtCore.QTimer.singleShot(120, lambda: _apply_taskbar(attempts - 1))

        QtCore.QTimer.singleShot(0, _apply_taskbar)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
