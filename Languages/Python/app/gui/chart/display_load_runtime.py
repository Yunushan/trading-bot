from __future__ import annotations

import copy
import time
from datetime import datetime, timezone

from PyQt6 import QtCore

from app.gui.runtime.background_workers import CallWorker

from . import display_render_runtime
from .chart_widgets import SimpleCandlestickWidget


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
    try:
        interval_text = self._canonicalize_chart_interval(interval_text) or interval_text
    except Exception:
        pass
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

    if not is_lightweight and not display_render_runtime.QT_CHARTS_AVAILABLE and not isinstance(view, SimpleCandlestickWidget):
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
        if thread is not None and thread.isInterruptionRequested():
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
            if thread is not None and thread.isInterruptionRequested():
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
        if thread is not None and thread.isInterruptionRequested():
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
