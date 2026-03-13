from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.gui.app_icon import load_app_icon
from app.gui.code_language_catalog import MUTED_TEXT


def _apply_window_icon(window) -> None:
    try:
        icon = load_app_icon()
    except Exception:
        icon = QtGui.QIcon()
    if icon.isNull():
        return
    try:
        window.setWindowIcon(icon)
    except Exception:
        pass
    try:
        QtGui.QGuiApplication.setWindowIcon(icon)
    except Exception:
        pass
    try:
        handle = window.windowHandle()
    except Exception:
        handle = None
    if handle is not None:
        try:
            handle.setIcon(icon)
        except Exception:
            pass


class _NumericItem(QtWidgets.QTableWidgetItem):
    def __init__(self, text: str, value: float = 0.0):
        super().__init__(text)
        try:
            self._numeric = float(value)
        except Exception:
            self._numeric = 0.0
        self.setTextAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

    def __lt__(self, other):
        if isinstance(other, _NumericItem):
            return self._numeric < other._numeric
        try:
            return self._numeric < float(other.text().replace("%", "").strip() or 0.0)
        except Exception:
            try:
                return float(self.text().replace("%", "").strip() or 0.0) < float(
                    other.text().replace("%", "").strip() or 0.0
                )
            except Exception:
                return super().__lt__(other)


class _StarterCard(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(str)

    def __init__(
        self,
        option_key: str,
        title: str,
        subtitle: str,
        accent_color: str,
        badge_text: str | None = None,
        *,
        disabled: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.option_key = option_key
        self._accent = accent_color
        self._selected = False
        self._disabled = bool(disabled)
        cursor_shape = (
            QtCore.Qt.CursorShape.ForbiddenCursor
            if self._disabled
            else QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.setCursor(cursor_shape)
        self.setObjectName(f"starter_card_{option_key.replace(' ', '_')}")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.accent_bar = QtWidgets.QFrame()
        self.accent_bar.setFixedHeight(4)
        root.addWidget(self.accent_bar)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(8)
        root.addWidget(body)

        self.badge_label = QtWidgets.QLabel(badge_text or "")
        self.badge_label.setStyleSheet(
            "padding: 2px 8px; border-radius: 7px; font-size: 10px; font-weight: 600;"
            "background-color: rgba(59, 130, 246, 0.15); color: #93c5fd;"
        )
        self.badge_label.setVisible(bool(badge_text))
        body_layout.addWidget(
            self.badge_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )

        self.title_label = QtWidgets.QLabel(title)
        body_layout.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        body_layout.addWidget(self.subtitle_label)
        body_layout.addStretch()

        self._refresh_style()

    def setSelected(self, selected: bool) -> None:
        if self._disabled:
            selected = False
        self._selected = bool(selected)
        self._refresh_style()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._disabled:
            event.ignore()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.option_key)
        super().mouseReleaseEvent(event)

    def is_disabled(self) -> bool:
        return self._disabled

    def _refresh_style(self) -> None:
        effective_selected = self._selected and not self._disabled
        if self._disabled:
            bg = "#10131d"
            border = "#1f2433"
        else:
            bg = "#1b2231" if effective_selected else "#151926"
            border = self._accent if effective_selected else "#242b3d"
        self.setStyleSheet(
            f"""
            QFrame#{self.objectName()} {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 16px;
            }}
            """
        )
        if self._disabled:
            bar_color = "#1f2433"
        else:
            bar_color = self._accent if effective_selected else "#1f2433"
        self.accent_bar.setStyleSheet(
            f"background-color: {bar_color}; border-top-left-radius: 16px; border-top-right-radius: 16px;"
        )
        title_color = "#6b7280" if self._disabled else "#f8fafc"
        subtitle_color = "#4b5565" if self._disabled else MUTED_TEXT
        self.title_label.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {title_color};"
        )
        self.subtitle_label.setStyleSheet(
            f"color: {subtitle_color}; font-size: 12px;"
        )
