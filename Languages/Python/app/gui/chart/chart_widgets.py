from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtCharts import QChartView
except Exception:
    QChartView = None


class SimpleCandlestickWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._candles: list[dict] = []
        self._message: str | None = "Charts unavailable."
        self._message_color: str = "#f75467"
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._view_start = 0
        self._view_end = 0
        self._min_visible = 10
        self._manual_view = False
        self._pan_active = False
        self._pan_last_pos: QtCore.QPointF | None = None
        self._fib_start: float | None = None
        self._fib_end: float | None = None
        self._fib_dragging = False
        self._show_hint = True

    def set_message(self, message: str, color: str = "#d1d4dc") -> None:
        self._candles = []
        self._message = message
        self._message_color = color
        self._fib_start = None
        self._fib_end = None
        self._reset_view()
        self.update()

    def set_candles(self, candles: list[dict]) -> None:
        self._candles = candles or []
        if not self._candles:
            self._message = "No data available."
            self._message_color = "#f75467"
            self._fib_start = None
            self._fib_end = None
            self._reset_view()
        else:
            self._message = None
            if self._manual_view:
                self._clamp_view()
            else:
                self._reset_view()
        self.update()

    def _reset_view(self) -> None:
        self._view_start = 0
        self._view_end = len(self._candles)
        self._manual_view = False

    def _clamp_view(self) -> None:
        total = len(self._candles)
        if total <= 0:
            self._view_start = 0
            self._view_end = 0
            return
        start = int(self._view_start)
        end = int(self._view_end) if self._view_end else total
        start = max(0, min(start, total - 1))
        end = max(start + 1, min(end, total))
        self._view_start = start
        self._view_end = end

    def _get_visible_range(self) -> tuple[int, int]:
        if not self._candles:
            return 0, 0
        self._clamp_view()
        return self._view_start, self._view_end

    def _chart_rect(self) -> QtCore.QRect:
        rect = self.rect()
        margin_x = max(int(rect.width() * 0.05), 40)
        margin_y = max(int(rect.height() * 0.1), 30)
        return rect.adjusted(margin_x, margin_y, -margin_x, -margin_y)

    def _visible_min_max(self, candles: list[dict]) -> tuple[float, float] | None:
        highs = [float(c.get("high", 0.0)) for c in candles]
        lows = [float(c.get("low", 0.0)) for c in candles]
        if not highs or not lows:
            return None
        max_high = max(highs)
        min_low = min(lows)
        if max_high <= min_low:
            max_high = min_low + 1.0
        return min_low, max_high

    def _pos_to_price(self, pos: QtCore.QPointF) -> float | None:
        if not self._candles:
            return None
        start, end = self._get_visible_range()
        visible = self._candles[start:end]
        if not visible:
            return None
        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return None
        min_max = self._visible_min_max(visible)
        if min_max is None:
            return None
        min_low, max_high = min_max
        y = min(max(pos.y(), chart_rect.top()), chart_rect.bottom())
        ratio = (chart_rect.bottom() - y) / chart_rect.height()
        return min_low + ratio * (max_high - min_low)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor("#0b0e11"))

        if not self._candles:
            if self._message:
                painter.setPen(QtGui.QColor(self._message_color))
                painter.drawText(
                    rect,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    self._message,
                )
            return

        start, end = self._get_visible_range()
        visible = self._candles[start:end]
        if not visible:
            return
        min_max = self._visible_min_max(visible)
        if min_max is None:
            return
        min_low, max_high = min_max

        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return

        painter.setPen(QtGui.QColor("#1f2326"))
        painter.drawRect(chart_rect)

        count = len(visible)
        spacing = chart_rect.width() / max(count, 1)
        body_width = max(4.0, spacing * 0.6)

        def price_to_y(price: float) -> float:
            ratio = (price - min_low) / (max_high - min_low)
            return chart_rect.bottom() - ratio * chart_rect.height()

        for idx, candle in enumerate(visible):
            try:
                open_ = float(candle.get("open", 0.0))
                close = float(candle.get("close", 0.0))
                high = float(candle.get("high", 0.0))
                low = float(candle.get("low", 0.0))
            except Exception:
                continue

            x_center = chart_rect.left() + (idx + 0.5) * spacing
            color = QtGui.QColor("#0ebb7a" if close >= open_ else "#f75467")
            painter.setPen(QtGui.QPen(color, 1.0))

            y_high = price_to_y(high)
            y_low = price_to_y(low)
            painter.drawLine(QtCore.QPointF(x_center, y_high), QtCore.QPointF(x_center, y_low))

            body_top = price_to_y(max(open_, close))
            body_bottom = price_to_y(min(open_, close))
            rect_body = QtCore.QRectF(
                x_center - body_width / 2.0,
                body_top,
                body_width,
                max(1.0, body_bottom - body_top),
            )
            painter.fillRect(rect_body, QtGui.QBrush(color))

        painter.setPen(QtGui.QColor("#3b434a"))
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
            f"High: {max_high:.4f}",
        )
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight,
            f"Low: {min_low:.4f}",
        )
        if self._fib_start is not None and self._fib_end is not None:
            self._draw_fib_levels(painter, chart_rect, price_to_y)
        if self._show_hint:
            painter.setPen(QtGui.QColor("#3b434a"))
            hint = "Wheel: zoom | Drag: pan | Shift+Drag: fib | Double-click: reset"
            painter.drawText(
                chart_rect.adjusted(4, 4, -4, -4),
                QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignLeft,
                hint,
            )

    def _draw_fib_levels(
        self,
        painter: QtGui.QPainter,
        chart_rect: QtCore.QRect,
        price_to_y,
    ) -> None:
        start_price = self._fib_start
        end_price = self._fib_end
        if start_price is None or end_price is None:
            return
        if abs(end_price - start_price) <= 0:
            return
        levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        line_pen = QtGui.QPen(QtGui.QColor("#3b82f6"))
        line_pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        line_pen.setWidthF(1.0)
        text_pen = QtGui.QPen(QtGui.QColor("#7dd3fc"))
        span = end_price - start_price
        for level in levels:
            price = start_price + span * level
            y = price_to_y(price)
            if y < chart_rect.top() - 1 or y > chart_rect.bottom() + 1:
                continue
            painter.setPen(line_pen)
            painter.drawLine(
                QtCore.QPointF(chart_rect.left(), y),
                QtCore.QPointF(chart_rect.right(), y),
            )
            label = f"{level:.3f}  {price:.4f}"
            painter.setPen(text_pen)
            painter.drawText(
                QtCore.QRectF(chart_rect.left() + 4, y - 9, chart_rect.width() - 8, 18),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
        if not self._candles:
            return super().wheelEvent(event)
        angle = event.angleDelta().y()
        if angle == 0:
            return super().wheelEvent(event)
        steps = angle / 120.0
        start, end = self._get_visible_range()
        total = len(self._candles)
        current_count = max(1, end - start)
        min_visible = min(self._min_visible, total) if total > 0 else 1
        scale = 1.2 ** steps
        new_count = int(round(current_count / scale))
        new_count = max(min_visible, min(total, new_count))
        if new_count == current_count:
            return super().wheelEvent(event)
        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0:
            return super().wheelEvent(event)
        pos = event.position()
        ratio = (pos.x() - chart_rect.left()) / chart_rect.width()
        ratio = max(0.0, min(1.0, ratio))
        center = start + ratio * current_count
        new_start = int(round(center - ratio * new_count))
        new_start = max(0, min(new_start, total - new_count))
        self._view_start = new_start
        self._view_end = new_start + new_count
        self._manual_view = True
        self._show_hint = False
        self.update()
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass
            chart_rect = self._chart_rect()
            if chart_rect.contains(event.position().toPoint()):
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    price = self._pos_to_price(event.position())
                    if price is not None:
                        self._fib_start = price
                        self._fib_end = price
                        self._fib_dragging = True
                        self._show_hint = False
                        self.update()
                    event.accept()
                    return
                self._pan_active = True
                self._pan_last_pos = event.position()
                try:
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                except Exception:
                    pass
                self._show_hint = False
                event.accept()
                return
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            if self._fib_start is not None or self._fib_end is not None:
                self._fib_start = None
                self._fib_end = None
                self._fib_dragging = False
                self._show_hint = False
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._pan_active and self._pan_last_pos is not None:
            start, end = self._get_visible_range()
            count = max(1, end - start)
            chart_rect = self._chart_rect()
            spacing = chart_rect.width() / max(count, 1)
            if spacing > 0:
                delta_x = event.position().x() - self._pan_last_pos.x()
                delta_candles = int(round(delta_x / spacing))
                if delta_candles != 0:
                    total = len(self._candles)
                    new_start = start - delta_candles
                    new_start = max(0, min(new_start, total - count))
                    self._view_start = new_start
                    self._view_end = new_start + count
                    self._manual_view = True
                    self.update()
            self._pan_last_pos = event.position()
            event.accept()
            return
        if self._fib_dragging:
            price = self._pos_to_price(event.position())
            if price is not None:
                self._fib_end = price
                self._show_hint = False
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._pan_active:
                self._pan_active = False
                self._pan_last_pos = None
                try:
                    self.unsetCursor()
                except Exception:
                    pass
                event.accept()
                return
            if self._fib_dragging:
                self._fib_dragging = False
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._reset_view()
            self._show_hint = False
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            QtCore.Qt.Key.Key_Escape,
            QtCore.Qt.Key.Key_Delete,
            QtCore.Qt.Key.Key_Backspace,
        ):
            if self._fib_start is not None or self._fib_end is not None:
                self._fib_start = None
                self._fib_end = None
                self._fib_dragging = False
                self._show_hint = False
                self.update()
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_R:
            self._reset_view()
            self._show_hint = False
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)


if QChartView is not None:
    class InteractiveChartView(QChartView):
        """QChartView with scroll/zoom conveniences for the 'Original' chart view."""

        def __init__(self, parent=None):
            super().__init__(parent)
            try:
                self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            except Exception:
                pass
            try:
                self.setRubberBand(QChartView.RubberBand.RectangleRubberBand)
            except Exception:
                pass
            try:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            except Exception:
                pass
            self.setMouseTracking(True)
            self._panning = False
            self._pan_start: QtCore.QPoint | None = None

        def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
            chart = self.chart()
            if chart is None:
                return super().wheelEvent(event)
            angle = event.angleDelta().y()
            if angle == 0:
                return super().wheelEvent(event)
            factor = 1.15 if angle > 0 else 1 / 1.15
            try:
                chart.zoom(factor)
            except Exception:
                pass
            event.accept()

        def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self._panning = True
                self._pan_start = event.position().toPoint()
                try:
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                except Exception:
                    pass
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if self._panning and self._pan_start is not None:
                delta = event.position().toPoint() - self._pan_start
                self._pan_start = event.position().toPoint()
                chart = self.chart()
                if chart is not None:
                    try:
                        chart.scroll(-delta.x(), delta.y())
                    except Exception:
                        pass
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self._panning = False
                self._pan_start = None
                try:
                    self.unsetCursor()
                except Exception:
                    pass
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            chart = self.chart()
            if chart is not None:
                try:
                    chart.zoomReset()
                except Exception:
                    pass
            super().mouseDoubleClickEvent(event)
else:
    class InteractiveChartView(QtWidgets.QWidget):
        """Fallback placeholder when PyQt6-Charts is unavailable."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt6-Charts is not installed; Original chart view is unavailable.")
