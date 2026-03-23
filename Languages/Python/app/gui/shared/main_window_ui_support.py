from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from .app_icon import load_app_icon
from ..code.code_language_catalog import MUTED_TEXT


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
        self._background_color = QtGui.QColor("#151926")
        self._border_color = QtGui.QColor("#242b3d")
        self._accent_bar_color = QtGui.QColor("#1f2433")
        cursor_shape = (
            QtCore.Qt.CursorShape.ForbiddenCursor
            if self._disabled
            else QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.setCursor(cursor_shape)
        self.setObjectName(f"starter_card_{option_key.replace(' ', '_')}")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(8)

        self.badge_label = QtWidgets.QLabel(badge_text or "")
        self.badge_label.setContentsMargins(0, 0, 0, 0)
        self.badge_label.setVisible(bool(badge_text))
        root.addWidget(
            self.badge_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )

        self.title_label = QtWidgets.QLabel(title)
        root.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        root.addWidget(self.subtitle_label)
        root.addStretch()

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
            background_color = QtGui.QColor("#10131d")
            border_color = QtGui.QColor("#1f2433")
            accent_bar_color = QtGui.QColor("#1f2433")
        else:
            background_color = QtGui.QColor("#1b2231" if effective_selected else "#151926")
            border_color = QtGui.QColor(self._accent if effective_selected else "#242b3d")
            accent_bar_color = QtGui.QColor(self._accent if effective_selected else "#1f2433")

        self._background_color = background_color
        self._border_color = border_color
        self._accent_bar_color = accent_bar_color

        title_color = QtGui.QColor("#6b7280" if self._disabled else "#f8fafc")
        subtitle_color = QtGui.QColor("#4b5565" if self._disabled else MUTED_TEXT)
        badge_color = QtGui.QColor("#6b7280" if self._disabled else "#93c5fd")

        title_font = QtGui.QFont(self.title_label.font())
        title_font.setPixelSize(20)
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        self.title_label.setFont(title_font)

        subtitle_font = QtGui.QFont(self.subtitle_label.font())
        subtitle_font.setPixelSize(12)
        self.subtitle_label.setFont(subtitle_font)

        badge_font = QtGui.QFont(self.badge_label.font())
        badge_font.setPixelSize(10)
        badge_font.setWeight(QtGui.QFont.Weight.DemiBold)
        self.badge_label.setFont(badge_font)

        title_palette = self.title_label.palette()
        title_palette.setColor(QtGui.QPalette.ColorRole.WindowText, title_color)
        self.title_label.setPalette(title_palette)

        subtitle_palette = self.subtitle_label.palette()
        subtitle_palette.setColor(QtGui.QPalette.ColorRole.WindowText, subtitle_color)
        self.subtitle_label.setPalette(subtitle_palette)

        badge_palette = self.badge_label.palette()
        badge_palette.setColor(QtGui.QPalette.ColorRole.WindowText, badge_color)
        self.badge_label.setPalette(badge_palette)

        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            rect = self.rect().adjusted(1, 1, -1, -1)
            path = QtGui.QPainterPath()
            path.addRoundedRect(QtCore.QRectF(rect), 16.0, 16.0)
            painter.fillPath(path, self._background_color)

            border_pen = QtGui.QPen(self._border_color)
            border_pen.setWidth(2)
            painter.setPen(border_pen)
            painter.drawPath(path)

            painter.save()
            painter.setClipRect(QtCore.QRectF(rect.x(), rect.y(), rect.width(), 12.0))
            accent_path = QtGui.QPainterPath()
            accent_path.addRoundedRect(QtCore.QRectF(rect.x(), rect.y(), rect.width(), 8.0), 14.0, 14.0)
            painter.fillPath(accent_path, self._accent_bar_color)
            painter.restore()
        finally:
            painter.end()
        super().paintEvent(event)
