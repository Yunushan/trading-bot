from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.gui.chart_embed import (
    _binance_unavailable_reason,
    _chart_safe_mode_enabled,
    _lightweight_unavailable_reason,
    _load_tradingview_widget,
    _tradingview_external_preferred,
    _tradingview_unavailable_reason,
)

_CHART_INTERVAL_OPTIONS = ()
_CHART_MARKET_OPTIONS = ()


def _on_tradingview_ready(self):
    if not getattr(self, "_pending_tradingview_switch", False):
        return
    desired_mode = str(self.chart_config.get("view_mode") or "").strip().lower()
    if desired_mode != "tradingview":
        self._pending_tradingview_switch = False
        return
    widget = getattr(self, "chart_tradingview", None)
    if widget is None:
        self._pending_tradingview_switch = False
        return
    try:
        if hasattr(widget, "is_ready") and not widget.is_ready():
            return
    except Exception:
        pass
    if not self._is_chart_visible():
        return
    self._pending_tradingview_switch = False
    self.chart_view = widget
    try:
        with QtCore.QSignalBlocker(self.chart_view_mode_combo):
            idx = self.chart_view_mode_combo.findData("tradingview")
            if idx >= 0:
                self.chart_view_mode_combo.setCurrentIndex(idx)
    except Exception:
        pass
    try:
        index = self.chart_view_stack.indexOf(widget)
        if index >= 0:
            self.chart_view_stack.setCurrentIndex(index)
    except Exception:
        pass
    try:
        self._on_chart_theme_changed()
    except Exception:
        pass
    self._chart_needs_render = True
    self._tradingview_first_switch_done = True
    self._hide_chart_switch_overlay(delay_ms=200)
    self._stop_tradingview_visibility_guard()
    if self._is_chart_visible():
        self.load_chart(auto=True)


def eventFilter(self, obj, event):  # noqa: N802
    try:
        if obj is getattr(self, "chart_view_stack", None):
            ev_type = event.type()
            if ev_type in {QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show}:
                self._update_chart_overlay_geometry()
    except Exception:
        pass
    return QtWidgets.QWidget.eventFilter(self, obj, event)


def _apply_chart_view_mode(
    self,
    mode: str,
    initial: bool = False,
    *,
    allow_tradingview_init: bool = True,
):
    if not getattr(self, "chart_enabled", False):
        return
    requested_mode = str(mode or "").strip().lower()
    if requested_mode not in {"tradingview", "original", "lightweight"}:
        requested_mode = "original"
    self._pending_webengine_mode = None
    try:
        self._chart_debug_log(
            f"apply_chart_view_mode requested={requested_mode} initial={int(bool(initial))} "
            f"allow_tv_init={int(bool(allow_tradingview_init))}"
        )
    except Exception:
        pass
    actual_mode = requested_mode
    widget = None
    defer_switch = False
    external_opened = False
    if requested_mode == "tradingview" and _tradingview_external_preferred():
        if not initial:
            try:
                external_opened = self._open_tradingview_external()
            except Exception:
                external_opened = False
        requested_mode = "original"
        actual_mode = "original"
    if requested_mode == "tradingview":
        if not self._chart_view_tradingview_available:
            actual_mode = "original"
        elif allow_tradingview_init:
            self._start_tradingview_close_guard()
            self._start_tradingview_visibility_watchdog()
            if not getattr(self, "_tradingview_first_switch_done", False):
                if self._is_chart_visible():
                    self._show_chart_switch_overlay()
                self._start_tradingview_window_suppression()
                self._start_tradingview_visibility_guard()
            widget = self._ensure_tradingview_widget()
            if widget is None:
                actual_mode = "original"
            else:
                self._bind_tradingview_ready(widget)
                try:
                    if hasattr(widget, "is_ready") and not widget.is_ready():
                        defer_switch = True
                except Exception:
                    pass
        else:
            self._pending_tradingview_mode = True
            actual_mode = "original"
    elif requested_mode == "lightweight":
        self._pending_tradingview_mode = False
        self._pending_tradingview_switch = False
        if not allow_tradingview_init and not self._is_chart_visible():
            self._pending_webengine_mode = "lightweight"
            actual_mode = "legacy"
        else:
            widget = self._ensure_lightweight_widget()
            if widget is None:
                actual_mode = "original"
    elif requested_mode == "original":
        self._pending_tradingview_mode = False
        self._pending_tradingview_switch = False
        if not allow_tradingview_init and not self._is_chart_visible():
            self._pending_webengine_mode = "original"
            actual_mode = "legacy"
        else:
            widget = self._ensure_binance_widget()
            if widget is None:
                actual_mode = "legacy"
    else:
        self._pending_tradingview_mode = False
        actual_mode = "legacy"
        self._pending_tradingview_switch = False
    if actual_mode != "tradingview":
        self._pending_tradingview_switch = False
        self._hide_chart_switch_overlay()
        self._stop_tradingview_visibility_guard()
        self._stop_tradingview_visibility_watchdog()
        self._tv_close_guard_active = False

    fallback_reason = None
    config_mode = requested_mode or actual_mode
    if requested_mode == "tradingview" and actual_mode != "tradingview" and not defer_switch:
        if not getattr(self, "_pending_tradingview_mode", False):
            fallback_reason = _tradingview_unavailable_reason()
            config_mode = "original"
    elif requested_mode == "lightweight" and actual_mode != "lightweight":
        if getattr(self, "_pending_webengine_mode", None) != "lightweight":
            fallback_reason = _lightweight_unavailable_reason()
            config_mode = "original"
    elif requested_mode == "original" and actual_mode != "original":
        if getattr(self, "_pending_webengine_mode", None) != "original":
            fallback_reason = _binance_unavailable_reason()
            config_mode = "original"

    if widget is None and actual_mode == "original":
        widget = self._ensure_binance_widget()
        if widget is None:
            actual_mode = "legacy"
    if widget is None:
        widget = self._chart_view_widgets.get(actual_mode)
    if widget is None:
        return
    combo_mode = "tradingview" if defer_switch else actual_mode
    if combo_mode == "legacy":
        combo_mode = "original"
    if defer_switch:
        self._pending_tradingview_mode = False
        self._pending_tradingview_switch = True
        if not getattr(self, "_tradingview_first_switch_done", False):
            self._show_chart_switch_overlay()
        try:
            with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                idx = self.chart_view_mode_combo.findData(combo_mode)
                if idx >= 0:
                    self.chart_view_mode_combo.setCurrentIndex(idx)
        except Exception:
            pass
        self.chart_config["view_mode"] = config_mode
        self._chart_needs_render = True
        self._prime_tradingview_chart(widget)
        return

    self._pending_tradingview_switch = False
    self.chart_view = widget
    try:
        with QtCore.QSignalBlocker(self.chart_view_mode_combo):
            idx = self.chart_view_mode_combo.findData(combo_mode)
            if idx >= 0:
                self.chart_view_mode_combo.setCurrentIndex(idx)
    except Exception:
        pass
    try:
        index = self.chart_view_stack.indexOf(widget)
        if index >= 0:
            self.chart_view_stack.setCurrentIndex(index)
    except Exception:
        pass
    self.chart_config["view_mode"] = config_mode
    if actual_mode == "tradingview":
        self._pending_tradingview_mode = False
        tv_class, _ = _load_tradingview_widget()
        if tv_class is not None and isinstance(widget, tv_class):
            try:
                self._on_chart_theme_changed()
            except Exception:
                pass
    self._chart_needs_render = True
    if fallback_reason and not initial:
        if requested_mode == "tradingview":
            opened = False
            try:
                opened = self._open_tradingview_external()
            except Exception:
                opened = False
            if opened:
                try:
                    self._show_chart_status("TradingView opened in your browser.", color="#94a3b8")
                except Exception:
                    pass
            else:
                try:
                    self._show_chart_status(fallback_reason, color="#f59e0b")
                except Exception:
                    pass
        else:
            try:
                self._show_chart_status(fallback_reason, color="#f59e0b")
            except Exception:
                pass
    status_text = "Chart view ready."
    if initial:
        self._show_chart_status(status_text, color="#d1d4dc")
        return
    if self._is_chart_visible():
        self.load_chart(auto=True)
    else:
        self._show_chart_status(status_text, color="#d1d4dc")
    if external_opened:
        try:
            self._show_chart_status("TradingView opened in your browser.", color="#94a3b8")
        except Exception:
            pass
    if actual_mode == "tradingview" and not defer_switch and not getattr(
        self, "_tradingview_first_switch_done", False
    ):
        self._tradingview_first_switch_done = True
        self._hide_chart_switch_overlay(delay_ms=200)
    try:
        self._chart_debug_log(
            f"apply_chart_view_mode done actual={actual_mode} defer={int(bool(defer_switch))} "
            f"fallback={str(fallback_reason or '')}"
        )
    except Exception:
        pass


def _on_chart_view_mode_changed(self, index: int):
    try:
        mode = self.chart_view_mode_combo.itemData(index)
    except Exception:
        mode = None
    if not mode:
        mode = self.chart_view_mode_combo.currentText()
    try:
        self._chart_debug_log(f"chart_view_mode_changed mode={str(mode or '').strip().lower()}")
    except Exception:
        pass
    mode_norm = str(mode or "").strip().lower()
    if _chart_safe_mode_enabled() and mode_norm in {"tradingview", "original", "lightweight"}:
        try:
            self._chart_debug_log(f"chart_view_mode_safe_blocked mode={mode_norm}")
        except Exception:
            pass
        if mode_norm == "tradingview":
            opened = False
            try:
                opened = self._open_tradingview_external()
            except Exception:
                opened = False
            if opened:
                self._show_chart_status(
                    "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.",
                    color="#94a3b8",
                )
            else:
                self._show_chart_status(
                    "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.",
                    color="#f59e0b",
                )
        else:
            self._show_chart_status(
                "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.",
                color="#f59e0b",
            )
        legacy = self._chart_view_widgets.get("legacy")
        if legacy is not None:
            try:
                self.chart_view = legacy
                idx = self.chart_view_stack.indexOf(legacy)
                if idx >= 0:
                    self.chart_view_stack.setCurrentIndex(idx)
            except Exception:
                pass
        try:
            with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                fallback_idx = self.chart_view_mode_combo.findData("original")
                if fallback_idx >= 0:
                    self.chart_view_mode_combo.setCurrentIndex(fallback_idx)
        except Exception:
            pass
        try:
            self.chart_config["view_mode"] = "original"
        except Exception:
            pass
        if self._is_chart_visible():
            self.load_chart(auto=True)
        return
    self._apply_chart_view_mode(mode)


def _restore_chart_controls_from_config(self):
    if not getattr(self, "chart_enabled", False):
        return
    market_cfg = self._normalize_chart_market(self.chart_config.get("market"))
    auto_follow_cfg = self.chart_config.get("auto_follow")
    self._chart_manual_override = False
    if auto_follow_cfg is None:
        self.chart_auto_follow = market_cfg == "Futures"
    else:
        self.chart_auto_follow = bool(auto_follow_cfg) and market_cfg == "Futures"
    market_combo = getattr(self, "chart_market_combo", None)
    if market_combo is not None:
        try:
            with QtCore.QSignalBlocker(market_combo):
                idx = market_combo.findText(market_cfg, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.setCurrentText(market_cfg)
        except Exception:
            market_combo.setCurrentText(market_cfg)
    self.chart_config["market"] = market_cfg
    self.chart_config["auto_follow"] = self.chart_auto_follow
    symbol_cfg = str(self.chart_config.get("symbol") or "").strip().upper()
    interval_cfg = str(self.chart_config.get("interval") or "").strip()
    if symbol_cfg:
        self._set_chart_symbol(symbol_cfg, ensure_option=True)
    if interval_cfg:
        self._set_chart_interval(interval_cfg)
    elif _CHART_INTERVAL_OPTIONS:
        self._set_chart_interval(_CHART_INTERVAL_OPTIONS[0])
    view_mode_cfg = str(self.chart_config.get("view_mode") or "").strip().lower()
    if view_mode_cfg:
        self._apply_chart_view_mode(view_mode_cfg, initial=True, allow_tradingview_init=False)


def _update_chart_symbol_options(self, symbols=None):
    if not getattr(self, "chart_enabled", False):
        return
    if not hasattr(self, "chart_symbol_combo"):
        return
    combo = self.chart_symbol_combo
    current = combo.currentText().strip().upper()
    market = self._normalize_chart_market(
        getattr(self, "chart_market_combo", None).currentText()
        if hasattr(self, "chart_market_combo")
        else None
    )
    if symbols is None:
        symbols = list(self.chart_symbol_cache.get(market) or [])
        if not symbols and market == "Futures":
            symbols = self._current_dashboard_symbols()
            if symbols:
                self.chart_symbol_cache[market] = list(symbols)
    uniques = []
    seen = set()
    for sym in symbols or []:
        sym_norm = str(sym or "").strip().upper()
        if sym_norm and sym_norm not in seen:
            seen.add(sym_norm)
            uniques.append(sym_norm)
    self.chart_symbol_cache[market] = list(uniques)
    display_symbols = list(uniques)
    alias_map = {}
    if market == "Futures":
        display_symbols = []
        for sym in uniques:
            disp = self._futures_display_symbol(sym)
            alias_map[disp] = sym
            if disp not in display_symbols:
                display_symbols.append(disp)
        preferred_disp = self._futures_display_symbol("BTCUSDT")
        if "BTCUSDT" in uniques:
            if preferred_disp in display_symbols:
                display_symbols.remove(preferred_disp)
            display_symbols.insert(0, preferred_disp)
            alias_map[preferred_disp] = "BTCUSDT"
    if not isinstance(getattr(self, "_chart_symbol_alias_map", None), dict):
        self._chart_symbol_alias_map = {}
    self._chart_symbol_alias_map[market] = alias_map
    if market == "Futures" and current:
        if current not in alias_map:
            reverse_map = {v: k for k, v in alias_map.items()}
            if current in reverse_map:
                current = reverse_map[current]
            else:
                current = self._futures_display_symbol(current)
    elif market != "Futures":
        alias_map = {}
    try:
        with QtCore.QSignalBlocker(combo):
            combo.clear()
            if display_symbols:
                combo.addItems(display_symbols)
    except Exception:
        combo.clear()
        if display_symbols:
            combo.addItems(display_symbols)
    if current:
        if combo.findText(current, QtCore.Qt.MatchFlag.MatchFixedString) >= 0:
            combo.setCurrentText(current)
        else:
            combo.setEditText(current)
    elif display_symbols:
        combo.setCurrentIndex(0)


def _chart_debug_log(self, message: str) -> None:
    try:
        ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    except Exception:
        ts = "unknown-time"
    try:
        path = getattr(self, "_chart_debug_log_path", None)
        if path is None:
            path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
            self._chart_debug_log_path = path
        with open(path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        return


def _normalize_chart_market(market):
    text = str(market or "").strip().lower()
    for opt in _CHART_MARKET_OPTIONS:
        if text.startswith(opt.lower()):
            return opt
    return "Futures"


def bind_main_window_chart_view_runtime(
    MainWindow,
    *,
    chart_interval_options,
    chart_market_options,
):
    global _CHART_INTERVAL_OPTIONS
    global _CHART_MARKET_OPTIONS

    _CHART_INTERVAL_OPTIONS = tuple(chart_interval_options)
    _CHART_MARKET_OPTIONS = tuple(chart_market_options)

    MainWindow._on_tradingview_ready = _on_tradingview_ready
    MainWindow.eventFilter = eventFilter
    MainWindow._apply_chart_view_mode = _apply_chart_view_mode
    MainWindow._on_chart_view_mode_changed = _on_chart_view_mode_changed
    MainWindow._restore_chart_controls_from_config = _restore_chart_controls_from_config
    MainWindow._update_chart_symbol_options = _update_chart_symbol_options
    MainWindow._chart_debug_log = _chart_debug_log
    MainWindow._normalize_chart_market = staticmethod(_normalize_chart_market)
