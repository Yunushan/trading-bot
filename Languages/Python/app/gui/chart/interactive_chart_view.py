from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtCharts import QChartView
except Exception:
    QChartView = None


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
