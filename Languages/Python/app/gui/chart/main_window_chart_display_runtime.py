from __future__ import annotations

import copy
import time
from datetime import datetime, timezone

import pandas as pd
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

from app.indicators import (
    adx as adx_indicator,
    bollinger_bands as bollinger_bands_indicator,
    dmi as dmi_indicator,
    donchian_high as donchian_high_indicator,
    donchian_low as donchian_low_indicator,
    ema as ema_indicator,
    macd as macd_indicator,
    parabolic_sar as psar_indicator,
    rsi as rsi_indicator,
    sma as sma_indicator,
    stochastic as stochastic_indicator,
    stoch_rsi as stoch_rsi_indicator,
    supertrend as supertrend_indicator,
    ultimate_oscillator as uo_indicator,
    williams_r as williams_r_indicator,
)
from app.config import INDICATOR_DISPLAY_NAMES
from .chart_widgets import SimpleCandlestickWidget
from app.workers import CallWorker


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


def _build_lightweight_payload(
    self,
    df: pd.DataFrame,
    times: list[int],
    candles: list[dict],
    indicators_cfg: dict,
    theme_name: str,
) -> dict:
    theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"

    def _series_from_values(values) -> list[dict]:
        data = []
        for t_val, v_val in zip(times, values):
            try:
                if v_val is None or pd.isna(v_val):
                    continue
                data.append({"time": int(t_val), "value": float(v_val)})
            except Exception:
                continue
        return data

    def _add_overlay(key: str, label: str, data: list[dict], color: str, line_style: int = 0, line_width: int = 2):
        if not data:
            return
        overlays.append(
            {
                "key": key,
                "label": label,
                "type": "line",
                "data": data,
                "color": color,
                "lineStyle": int(line_style),
                "lineWidth": int(line_width),
            }
        )

    def _add_pane(key: str, label: str, series: list[dict], height: int = 80):
        if not series:
            return
        panes.append(
            {
                "key": key,
                "label": label,
                "height": int(height),
                "series": series,
            }
        )

    overlays: list[dict] = []
    panes: list[dict] = []

    volume_series = []
    try:
        opens = df["open"].tolist()
        closes = df["close"].tolist()
        volumes = df["volume"].tolist()
        for t_val, o_val, c_val, v_val in zip(times, opens, closes, volumes):
            if v_val is None or pd.isna(v_val):
                continue
            color = "#0ebb7a" if float(c_val) >= float(o_val) else "#f75467"
            volume_series.append({"time": int(t_val), "value": float(v_val), "color": color})
    except Exception:
        volume_series = []

    indicators_cfg = indicators_cfg or {}
    enabled_map = {
        str(k).strip().lower(): v
        for k, v in (indicators_cfg or {}).items()
        if isinstance(v, dict) and v.get("enabled")
    }

    if enabled_map.get("volume"):
        _add_pane(
            "volume",
            INDICATOR_DISPLAY_NAMES.get("volume", "Volume"),
            [
                {
                    "type": "histogram",
                    "data": volume_series,
                    "color": "#94a3b8",
                    "priceFormat": {"type": "volume"},
                }
            ],
            height=90,
        )

    if enabled_map.get("ma"):
        cfg = enabled_map.get("ma", {})
        length = int(cfg.get("length") or 20)
        ma_type = str(cfg.get("type") or "SMA").strip().upper()
        if ma_type == "EMA":
            series = ema_indicator(df["close"], length)
            label = f"EMA({length})"
            color = "#38bdf8"
        else:
            series = sma_indicator(df["close"], length)
            label = f"SMA({length})"
            color = "#f59e0b"
        _add_overlay("ma", label, _series_from_values(series.tolist()), color)

    if enabled_map.get("ema"):
        cfg = enabled_map.get("ema", {})
        length = int(cfg.get("length") or 20)
        series = ema_indicator(df["close"], length)
        _add_overlay("ema", f"EMA({length})", _series_from_values(series.tolist()), "#22c55e")

    if enabled_map.get("bb"):
        cfg = enabled_map.get("bb", {})
        length = int(cfg.get("length") or 20)
        std = float(cfg.get("std") or 2)
        upper, mid, lower = bollinger_bands_indicator(df, length=length, std=std)
        _add_overlay("bb_upper", f"BB Upper({length})", _series_from_values(upper.tolist()), "#60a5fa", line_style=2)
        _add_overlay("bb_mid", f"BB Mid({length})", _series_from_values(mid.tolist()), "#fbbf24")
        _add_overlay("bb_lower", f"BB Lower({length})", _series_from_values(lower.tolist()), "#60a5fa", line_style=2)

    if enabled_map.get("donchian"):
        cfg = enabled_map.get("donchian", {})
        length = int(cfg.get("length") or 20)
        high_series = donchian_high_indicator(df, length)
        low_series = donchian_low_indicator(df, length)
        _add_overlay("donchian_high", f"DC High({length})", _series_from_values(high_series.tolist()), "#f59e0b", line_style=2)
        _add_overlay("donchian_low", f"DC Low({length})", _series_from_values(low_series.tolist()), "#22c55e", line_style=2)

    if enabled_map.get("psar"):
        cfg = enabled_map.get("psar", {})
        af = float(cfg.get("af") or 0.02)
        max_af = float(cfg.get("max_af") or 0.2)
        psar_series = psar_indicator(df, af=af, max_af=max_af)
        _add_overlay("psar", "PSAR", _series_from_values(psar_series.tolist()), "#f472b6", line_style=1)

    if enabled_map.get("supertrend"):
        cfg = enabled_map.get("supertrend", {})
        atr_period = int(cfg.get("atr_period") or 10)
        multiplier = float(cfg.get("multiplier") or 3.0)
        st_delta = supertrend_indicator(df, atr_period=atr_period, multiplier=multiplier)
        try:
            st_line = df["close"] - st_delta
        except Exception:
            st_line = st_delta
        _add_overlay("supertrend", "SuperTrend", _series_from_values(st_line.tolist()), "#a855f7", line_style=2)

    if enabled_map.get("rsi"):
        cfg = enabled_map.get("rsi", {})
        length = int(cfg.get("length") or 14)
        series = rsi_indicator(df["close"], length=length)
        _add_pane(
            "rsi",
            INDICATOR_DISPLAY_NAMES.get("rsi", "RSI"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f97316"}],
        )

    if enabled_map.get("stoch_rsi"):
        cfg = enabled_map.get("stoch_rsi", {})
        length = int(cfg.get("length") or 14)
        smooth_k = int(cfg.get("smooth_k") or 3)
        smooth_d = int(cfg.get("smooth_d") or 3)
        k_series, d_series = stoch_rsi_indicator(df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
        _add_pane(
            "stoch_rsi",
            INDICATOR_DISPLAY_NAMES.get("stoch_rsi", "Stoch RSI"),
            [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ],
        )

    if enabled_map.get("willr"):
        cfg = enabled_map.get("willr", {})
        length = int(cfg.get("length") or 14)
        series = williams_r_indicator(df, length=length)
        _add_pane(
            "willr",
            INDICATOR_DISPLAY_NAMES.get("willr", "Williams %R"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#60a5fa"}],
        )

    if enabled_map.get("macd"):
        cfg = enabled_map.get("macd", {})
        fast = int(cfg.get("fast") or 12)
        slow = int(cfg.get("slow") or 26)
        signal = int(cfg.get("signal") or 9)
        macd_line, signal_line, hist = macd_indicator(df["close"], fast=fast, slow=slow, signal=signal)
        _add_pane(
            "macd",
            INDICATOR_DISPLAY_NAMES.get("macd", "MACD"),
            [
                {"type": "line", "data": _series_from_values(macd_line.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(signal_line.tolist()), "color": "#ef4444"},
                {"type": "histogram", "data": _series_from_values(hist.tolist()), "color": "#94a3b8"},
            ],
        )

    if enabled_map.get("uo"):
        cfg = enabled_map.get("uo", {})
        short = int(cfg.get("short") or 7)
        medium = int(cfg.get("medium") or 14)
        long = int(cfg.get("long") or 28)
        series = uo_indicator(df, short=short, medium=medium, long=long)
        _add_pane(
            "uo",
            INDICATOR_DISPLAY_NAMES.get("uo", "Ultimate Oscillator"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#8b5cf6"}],
        )

    if enabled_map.get("adx"):
        cfg = enabled_map.get("adx", {})
        length = int(cfg.get("length") or 14)
        series = adx_indicator(df, length=length)
        _add_pane(
            "adx",
            INDICATOR_DISPLAY_NAMES.get("adx", "ADX"),
            [{"type": "line", "data": _series_from_values(series.tolist()), "color": "#f59e0b"}],
        )

    if enabled_map.get("dmi"):
        cfg = enabled_map.get("dmi", {})
        length = int(cfg.get("length") or 14)
        plus_di, minus_di, adx_series = dmi_indicator(df, length=length)
        _add_pane(
            "dmi",
            INDICATOR_DISPLAY_NAMES.get("dmi", "DMI"),
            [
                {"type": "line", "data": _series_from_values(plus_di.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(minus_di.tolist()), "color": "#ef4444"},
                {"type": "line", "data": _series_from_values(adx_series.tolist()), "color": "#f59e0b"},
            ],
        )

    if enabled_map.get("stochastic"):
        cfg = enabled_map.get("stochastic", {})
        length = int(cfg.get("length") or 14)
        smooth_k = int(cfg.get("smooth_k") or 3)
        smooth_d = int(cfg.get("smooth_d") or 3)
        k_series, d_series = stochastic_indicator(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
        _add_pane(
            "stochastic",
            INDICATOR_DISPLAY_NAMES.get("stochastic", "Stochastic"),
            [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ],
        )

    return {
        "candles": candles,
        "volume": volume_series if enabled_map.get("volume") else [],
        "overlays": overlays,
        "panes": panes,
        "theme": theme_code,
    }


def _on_chart_theme_changed(self, *_args):
    if not getattr(self, "chart_enabled", False):
        return
    view = getattr(self, "chart_view", None)
    tv_view = getattr(self, "chart_tradingview", None)
    if tv_view is not None and view is tv_view:
        try:
            theme_name = (self.theme_combo.currentText() or "").strip()
        except Exception:
            theme_name = self.config.get("theme", "Dark")
        try:
            tv_view.apply_theme(theme_name)
        except Exception:
            pass
        return
    lw_view = getattr(self, "chart_lightweight", None)
    if lw_view is not None and view is lw_view:
        try:
            theme_name = (self.theme_combo.currentText() or "").strip()
        except Exception:
            theme_name = self.config.get("theme", "Dark")
        theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
        try:
            lw_view.set_chart_data({"theme": theme_code})
        except Exception:
            pass


def _on_dashboard_selection_for_chart(self):
    if self.chart_auto_follow:
        self._apply_dashboard_selection_to_chart(load=True)


def _is_chart_visible(self):
    if not getattr(self, "chart_enabled", False):
        return False
    try:
        tabs = getattr(self, "tabs", None)
        chart_tab = getattr(self, "chart_tab", None)
        if tabs is None or chart_tab is None:
            return False
        return tabs.currentWidget() is chart_tab
    except Exception:
        return False


def load_chart(self, auto: bool = False):
    if not getattr(self, "chart_enabled", False):
        return
    try:
        self._chart_debug_log(f"load_chart auto={int(bool(auto))}")
    except Exception:
        pass
    try:
        now_ts = time.monotonic()
        last_ts = float(getattr(self, "_last_chart_load_ts", 0.0) or 0.0)
        min_gap = 5.0 if auto else 0.0
        if auto and now_ts - last_ts < min_gap:
            return
    except Exception:
        pass
    view = getattr(self, "chart_view", None)
    if view is None:
        if not auto:
            self.log("Charts unavailable: install PyQt6-Charts for visualization.")
        self._show_chart_status("Charts unavailable.", color="#f75467")
        return
    try:
        symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
        interval_text = (self.chart_interval_combo.currentText() or "").strip()
    except Exception:
        if not auto:
            self.log("Chart: unable to read current selection.")
        return
    if not symbol_text:
        if not auto:
            self.log("Chart: please choose a symbol.")
        return
    if not interval_text:
        if not auto:
            self.log("Chart: please choose an interval.")
        return
    interval_code = self._map_chart_interval(interval_text)
    if not interval_code:
        if not auto:
            self.log(f"Chart: unsupported interval '{interval_text}'.")
        return
    market_text = self._normalize_chart_market(
        self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None
    )
    api_symbol = self._resolve_chart_symbol_for_api(symbol_text, market_text)

    existing_worker = getattr(self, "_chart_worker", None)
    if existing_worker and existing_worker.isRunning():
        try:
            existing_worker.requestInterruption()
        except Exception:
            pass
    self._chart_worker = None

    tv_view = getattr(self, "chart_tradingview", None)
    if tv_view is not None and view is tv_view:
        try:
            theme_name = (self.theme_combo.currentText() or "").strip()
        except Exception:
            theme_name = self.config.get("theme", "Dark")
        tv_symbol = self._format_chart_symbol(symbol_text, market_text)
        theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
        self._chart_pending_initial_load = False
        try:
            tv_view.set_chart(tv_symbol, interval_code, theme=theme_code, timezone="Etc/UTC")
            try:
                self._last_chart_load_ts = time.monotonic()
            except Exception:
                pass
            self.chart_config["symbol"] = symbol_text
            self.chart_config["interval"] = interval_text
            self.chart_config["market"] = market_text
            self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
            self._chart_needs_render = False
        except Exception as exc:
            self._chart_needs_render = True
            if not auto:
                self.log(f"Chart load failed: {exc}")
            try:
                tv_view.show_message("Failed to load TradingView chart.", color="#f75467")
            except Exception:
                pass
        return

    bw_view = getattr(self, "chart_binance", None)
    if bw_view is not None and view is bw_view:
        try:
            self._chart_pending_initial_load = False
            bw_view.set_chart(symbol_text, interval_text, market_text)
            try:
                self._last_chart_load_ts = time.monotonic()
            except Exception:
                pass
            self.chart_config["symbol"] = symbol_text
            self.chart_config["interval"] = interval_text
            self.chart_config["market"] = market_text
            self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
            self._chart_needs_render = False
        except Exception as exc:
            self._chart_needs_render = True
            if not auto:
                self.log(f"Chart load failed: {exc}")
            try:
                bw_view.show_message("Failed to load Binance chart.", color="#f75467")
            except Exception:
                pass
        return

    lw_view = getattr(self, "chart_lightweight", None)
    is_lightweight = lw_view is not None and view is lw_view

    if not is_lightweight and not QT_CHARTS_AVAILABLE and not isinstance(view, SimpleCandlestickWidget):
        if not auto:
            self.log("Charts unavailable: install PyQt6-Charts for visualization.")
        self._show_chart_status("Charts unavailable.", color="#f75467")
        return
    account_type = "Futures" if market_text == "Futures" else "Spot"
    api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
    api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
    mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"
    indicators_cfg = copy.deepcopy(self.config.get("indicators", {}) or {})
    try:
        theme_name = (self.theme_combo.currentText() or "").strip()
    except Exception:
        theme_name = self.config.get("theme", "Dark")

    def _do():
        thread = QtCore.QThread.currentThread()
        if thread.isInterruptionRequested():
            return None
        wrapper = self._create_binance_wrapper(
            api_key=api_key,
            api_secret=api_secret,
            mode=mode,
            account_type=account_type,
        )
        try:
            wrapper.indicator_source = self.ind_source_combo.currentText()
        except Exception:
            pass
        df = wrapper.get_klines(api_symbol, interval_text, limit=400)
        if df is None or df.empty:
            raise RuntimeError("no_kline_data")
        df = df.tail(400)
        candles = []
        times = []
        index_used = []
        for ts, row in df.iterrows():
            if thread.isInterruptionRequested():
                return None
            try:
                dt = ts.to_pydatetime()
            except Exception:
                dt = ts
            if not isinstance(dt, datetime):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            epoch = int(dt.timestamp())
            try:
                candles.append(
                    {
                        "time": epoch,
                        "open": float(row.get("open", 0.0)),
                        "high": float(row.get("high", 0.0)),
                        "low": float(row.get("low", 0.0)),
                        "close": float(row.get("close", 0.0)),
                    }
                )
                times.append(epoch)
                index_used.append(ts)
            except Exception:
                continue
        if thread.isInterruptionRequested():
            return None
        if not candles:
            raise RuntimeError("no_valid_candles")
        if is_lightweight:
            df_used = df.loc[index_used] if index_used else df
            payload = self._build_lightweight_payload(
                df_used,
                times,
                candles,
                indicators_cfg,
                theme_name,
            )
            return {"candles": candles, "payload": payload}
        return {"candles": candles}

    def _done(res, err, worker_ref=None):
        if worker_ref is not getattr(self, "_chart_worker", None):
            return
        self._chart_worker = None
        self._chart_pending_initial_load = False
        if err or not isinstance(res, dict):
            self._chart_needs_render = True
            if not auto and err:
                self.log(f"Chart load failed: {err}")
            self._show_chart_status("Failed to load chart data.", color="#f75467")
            return
        candles = res.get("candles") or []
        if is_lightweight and lw_view is not None:
            payload = res.get("payload") or {}
            try:
                if payload:
                    lw_view.set_chart_data(payload)
            except Exception as exc:
                if not auto:
                    self.log(f"Chart load failed: {exc}")
                self._show_chart_status("Failed to load lightweight chart.", color="#f75467")
                return
        else:
            self._render_candlestick_chart(symbol_text, interval_code, candles)
        try:
            self._last_chart_load_ts = time.monotonic()
        except Exception:
            pass
        self.chart_config["symbol"] = symbol_text
        self.chart_config["interval"] = interval_text
        self.chart_config["market"] = market_text
        self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
        self._chart_needs_render = False

    self._show_chart_status("Loading chart...", color="#d1d4dc")
    self._chart_needs_render = True
    worker = CallWorker(_do, parent=self)
    self._chart_worker = worker
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(lambda res, err, w=worker: _done(res, err, worker_ref=w))
    worker.start()


def bind_main_window_chart_display_runtime(MainWindow):
    MainWindow._show_chart_status = _show_chart_status
    MainWindow._render_candlestick_chart = _render_candlestick_chart
    MainWindow._build_lightweight_payload = _build_lightweight_payload
    MainWindow._on_chart_theme_changed = _on_chart_theme_changed
    MainWindow._on_dashboard_selection_for_chart = _on_dashboard_selection_for_chart
    MainWindow._is_chart_visible = _is_chart_visible
    MainWindow.load_chart = load_chart
