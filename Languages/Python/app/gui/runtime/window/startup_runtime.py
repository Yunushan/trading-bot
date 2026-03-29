from __future__ import annotations

from PyQt6 import QtCore


def apply_standard_window_flags(window) -> None:
    try:
        current_flags = window.windowFlags()
        desired_flags = (
            current_flags
            | QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
            | QtCore.Qt.WindowType.WindowTitleHint
            | QtCore.Qt.WindowType.WindowSystemMenuHint
            | QtCore.Qt.WindowType.WindowCloseButtonHint
        )
        desired_flags &= ~QtCore.Qt.WindowType.FramelessWindowHint
        desired_flags &= ~QtCore.Qt.WindowType.Tool
        if desired_flags != current_flags:
            window.setWindowFlags(desired_flags)
    except Exception:
        pass
