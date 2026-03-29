from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtCharts import (
        QChart,
        QChartView,
        QCandlestickSeries,
        QCandlestickSet,
        QDateTimeAxis,
        QValueAxis,
    )

    QT_CHARTS_AVAILABLE = True
except Exception:
    QT_CHARTS_AVAILABLE = False
    QChart = QChartView = QCandlestickSeries = QCandlestickSet = QDateTimeAxis = QValueAxis = None

from .chart_widgets import SimpleCandlestickWidget


def _show_chart_status(self, message: str, color: str = "#d1d4dc"):
    if not getattr(self, "chart_enabled", False):
        return
    view = getattr(self, "chart_view", None)
    if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
        chart = QChart()
        chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
        try:
            chart.legend().hide()
        except Exception:
            pass
        try:
            text_item = QtWidgets.QGraphicsSimpleTextItem(str(message), chart)
            text_item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
            text_item.setPos(12, 12)
        except Exception:
            try:
                chart.setTitle(str(message))
                chart.setTitleBrush(QtGui.QBrush(QtGui.QColor(color)))
            except Exception:
                pass
        view.setChart(chart)
        return
    bw_view = getattr(self, "chart_binance", None)
    if bw_view is not None and view is bw_view:
        try:
            bw_view.show_message(message, color=color)
        except Exception:
            pass
        return
    lw_view = getattr(self, "chart_lightweight", None)
    if lw_view is not None and view is lw_view:
        try:
            lw_view.show_message(message, color=color)
        except Exception:
            pass
        return
    tv_view = getattr(self, "chart_tradingview", None)
    if tv_view is not None and view is tv_view:
        try:
            tv_view.show_message(message, color=color)
        except Exception:
            pass
    elif isinstance(view, SimpleCandlestickWidget):
        view.set_message(message, color=color)


def _render_candlestick_chart(self, symbol: str, interval_code: str, candles: list[dict]):
    if not getattr(self, "chart_enabled", False):
        return
    view = getattr(self, "chart_view", None)
    if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
        if not candles:
            self._show_chart_status("No data available.", color="#f75467")
            return
        chart = QChart()
        chart.setTitle(f"{symbol} - {interval_code}")
        chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        try:
            chart.legend().hide()
        except Exception:
            pass

        series = QCandlestickSeries()
        try:
            series.setIncreasingColor(QtGui.QColor("#0ebb7a"))
            series.setDecreasingColor(QtGui.QColor("#f75467"))
        except Exception:
            pass

        lows: list[float] = []
        highs: list[float] = []
        for candle in candles:
            try:
                open_ = float(candle.get("open", 0.0))
                high = float(candle.get("high", 0.0))
                low = float(candle.get("low", 0.0))
                close = float(candle.get("close", 0.0))
                timestamp = float(candle.get("time", 0.0)) * 1000.0
            except Exception:
                continue
            set_item = QCandlestickSet(open_, high, low, close, timestamp)
            series.append(set_item)
            lows.append(low)
            highs.append(high)

        if not lows or not highs:
            self._show_chart_status("No data available.", color="#f75467")
            return

        chart.addSeries(series)

        axis_x = QDateTimeAxis()
        axis_x.setFormat("dd.MM HH:mm")
        axis_x.setLabelsColor(QtGui.QColor("#d1d4dc"))
        axis_x.setTitleText("Time")
        chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        try:
            axis_x.setRange(
                QtCore.QDateTime.fromSecsSinceEpoch(int(candles[0]["time"])),
                QtCore.QDateTime.fromSecsSinceEpoch(int(candles[-1]["time"])),
            )
        except Exception:
            pass

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%.2f")
        axis_y.setTitleText("Price")
        axis_y.setLabelsColor(QtGui.QColor("#d1d4dc"))
        chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        try:
            axis_y.setRange(min(lows), max(highs))
        except Exception:
            pass

        chart.setMargins(QtCore.QMargins(8, 8, 8, 8))
        view.setChart(chart)
    elif isinstance(view, SimpleCandlestickWidget):
        if not candles:
            view.set_message("No data available.", color="#f75467")
        else:
            view.set_candles(candles)
