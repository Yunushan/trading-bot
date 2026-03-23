from __future__ import annotations

_previous_qt_message_handler = None


def _install_qt_warning_filter() -> None:
    """Suppress nuisance Qt warnings we cannot control."""
    from PyQt6 import QtCore

    target = "setHighDpiScaleFactorRoundingPolicy"

    def handler(mode, context, message):  # noqa: ANN001
        if target in message:
            return
        if _previous_qt_message_handler is not None:
            _previous_qt_message_handler(mode, context, message)

    handler.__name__ = "qt_warning_filter"
    global _previous_qt_message_handler
    _previous_qt_message_handler = QtCore.qInstallMessageHandler(handler)
