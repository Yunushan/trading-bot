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

# CRITICAL: On Windows, use ctypes to hide ALL windows from this process
# This must happen BEFORE any Qt imports or window creation
if sys.platform == "win32":
    try:
        import ctypes
        import ctypes.wintypes
        
        # Get console window handle (if any) and hide it
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        
        # GetConsoleWindow returns the window handle of the console
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            # SW_HIDE = 0
            user32.ShowWindow(hwnd, 0)
        
        # Also try to hide the main window handle for this process
        # Get current process ID
        pid = kernel32.GetCurrentProcessId()
        
        # EnumWindows callback to hide windows belonging to this process
        def enum_callback(hwnd, lParam):
            out_pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(out_pid))
            if out_pid.value == pid:
                # Hide any window belonging to this process
                user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
        
        # Define callback type
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        enum_windows_proc = EnumWindowsProc(enum_callback)
        
        # Enumerate and hide all windows
        user32.EnumWindows(enum_windows_proc, 0)
    except Exception:
        pass  # Silently ignore if this fails

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
    
    # Check if we should skip taskbar metadata (set by launcher to prevent flashing)
    disable_taskbar = os.getenv("BOT_DISABLE_TASKBAR", "").strip() == "1"
    
    # Only set app user model ID if taskbar metadata is enabled
    if not disable_taskbar:
        ensure_app_user_model_id(APP_USER_MODEL_ID)
    
    # CRITICAL: Set attributes BEFORE creating QApplication
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    # Prevent windows from auto-showing
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Prevent app from quitting when windows are hidden
    app.setQuitOnLastWindowClosed(True)
    
    icon = QtGui.QIcon()
    if not disable_taskbar:
        try:
            app.setApplicationDisplayName("Binance Trading Bot")
            icon = load_app_icon()
            if not icon.isNull():
                app.setApplicationName("Binance Trading Bot")
                app.setWindowIcon(icon)
                QtGui.QGuiApplication.setWindowIcon(icon)
        except Exception:
            icon = QtGui.QIcon()
    
    # Create window - it will be constructed hidden
    win = MainWindow()
    
    # CRITICAL: Set as Tool window to prevent taskbar/Alt-Tab appearance during init
    win.setWindowFlags(win.windowFlags() | QtCore.Qt.WindowType.Tool)
    
    # CRITICAL: Force hidden state immediately after construction
    win.setVisible(False)
    win.setWindowState(QtCore.Qt.WindowState.WindowMaximized)
    
    if not disable_taskbar:
        try:
            if not icon.isNull():
                win.setWindowIcon(icon)
        except Exception:
            pass
    
    # Get window ID (creates native window handle but stays hidden)
    win.winId()
    
    if not disable_taskbar:
        if not icon.isNull():
            QtCore.QTimer.singleShot(0, lambda: win.setWindowIcon(icon))
        
        if sys.platform == "win32":
            icon_path = find_primary_icon_file()
            relaunch_cmd = build_relaunch_command()
            def _apply_taskbar(attempts: int = 1) -> None:
                if attempts <= 0:
                    return
                success = apply_taskbar_metadata(
                    win,
                    app_id=APP_USER_MODEL_ID,
                    display_name="Binance Trading Bot",
                    icon_path=icon_path,
                    relaunch_command=relaunch_cmd,
                )
                if not success and attempts > 0:
                    QtCore.QTimer.singleShot(300, lambda: _apply_taskbar(attempts - 1))

            QtCore.QTimer.singleShot(500, _apply_taskbar)
    
    # Show window only after complete initialization
    def _show_window():
        # Remove Tool flag before showing
        win.setWindowFlags(win.windowFlags() & ~QtCore.Qt.WindowType.Tool)
        win.setVisible(True)
        win.raise_()
        win.activateWindow()
    
    # Longer delay to ensure everything is ready
    QtCore.QTimer.singleShot(300, _show_window)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
