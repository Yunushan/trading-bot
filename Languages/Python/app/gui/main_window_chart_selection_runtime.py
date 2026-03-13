from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.workers import CallWorker

_DEFAULT_CHART_SYMBOLS = ()
_SYMBOL_FETCH_TOP_N = 0
_TRADINGVIEW_SYMBOL_PREFIX = "BINANCE:"
_TRADINGVIEW_INTERVAL_MAP = {}


def _futures_display_symbol(self, symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if not sym:
        return sym
    if sym.endswith(".P"):
        return sym
    if sym.endswith("USDT") and not sym.endswith("BUSD"):
        return f"{sym}.P"
    return sym


def _resolve_chart_symbol_for_api(self, symbol: str, market: str | None = None) -> str:
    sym = (symbol or "").strip().upper()
    cfg_market = market
    if cfg_market is None:
        try:
            cfg_market = self.chart_config.get("market")
        except Exception:
            cfg_market = None
    market_norm = self._normalize_chart_market(cfg_market)
    if market_norm == "Futures":
        alias_map = {}
        mapping = getattr(self, "_chart_symbol_alias_map", {})
        if isinstance(mapping, dict):
            alias_map = mapping.get(market_norm, {}) or {}
        if sym in alias_map:
            return alias_map[sym]
        if sym.endswith(".P"):
            return sym[:-2]
    return sym


def _current_dashboard_symbols(self):
    symbols = []
    if hasattr(self, "symbol_list") and isinstance(self.symbol_list, QtWidgets.QListWidget):
        try:
            for idx in range(self.symbol_list.count()):
                item = self.symbol_list.item(idx)
                if item:
                    sym = item.text().strip().upper()
                    if sym:
                        symbols.append(sym)
        except Exception:
            return symbols
    return symbols


def _on_chart_controls_changed(self, *_args):
    if not getattr(self, "chart_enabled", False):
        return
    if not hasattr(self, "chart_config"):
        return
    try:
        symbol = (self.chart_symbol_combo.currentText() or "").strip().upper()
        interval = (self.chart_interval_combo.currentText() or "").strip()
    except Exception:
        return
    changed = False
    symbol_changed = False
    if symbol:
        if self.chart_config.get("symbol") != symbol:
            changed = True
            symbol_changed = True
        self.chart_config["symbol"] = symbol
    if interval:
        if self.chart_config.get("interval") != interval:
            changed = True
        self.chart_config["interval"] = interval
    if self._chart_updating:
        return
    market = self._normalize_chart_market(self.chart_config.get("market"))
    if market == "Futures" and symbol_changed:
        self._chart_manual_override = True
        self.chart_auto_follow = False
        self.chart_config["auto_follow"] = False
    if changed:
        self._chart_needs_render = True
        if self._is_chart_visible():
            self.load_chart(auto=True)


def _chart_account_type(self, market: str) -> str:
    normalized = self._normalize_chart_market(market)
    return "Spot" if normalized == "Spot" else "Futures"


def _on_chart_market_changed(self, text: str):
    if not getattr(self, "chart_enabled", False):
        return
    market = self._normalize_chart_market(text)
    self.chart_config["market"] = market
    self._chart_manual_override = False
    self.chart_auto_follow = market == "Futures"
    self.chart_config["auto_follow"] = self.chart_auto_follow
    cache = list(self.chart_symbol_cache.get(market) or [])
    if not cache:
        cache = list(_DEFAULT_CHART_SYMBOLS)
        self.chart_symbol_cache[market] = cache
    self._update_chart_symbol_options(cache)
    self._chart_needs_render = True
    if cache:
        preferred_cfg = self.chart_config.get("symbol")
        preferred_actual = self._resolve_chart_symbol_for_api(preferred_cfg, market) if preferred_cfg else None
        if not preferred_actual or preferred_actual not in cache:
            preferred_actual = cache[0]
        preferred_display = self._futures_display_symbol(preferred_actual) if market == "Futures" else preferred_actual
        changed = self._set_chart_symbol(
            preferred_display,
            ensure_option=True,
            from_follow=self.chart_auto_follow,
        )
        if self.chart_auto_follow and market == "Futures":
            if changed or self._chart_needs_render:
                self._apply_dashboard_selection_to_chart(load=False)
        elif self._is_chart_visible():
            self.load_chart(auto=True)
    self._load_chart_symbols_async(market)


def _load_chart_symbols_async(self, market: str):
    if not getattr(self, "chart_enabled", False):
        return
    market_key = self._normalize_chart_market(market)
    if market_key in self._chart_symbol_loading:
        return
    self._chart_symbol_loading.add(market_key)
    api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
    api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
    mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"
    account_type = self._chart_account_type(market_key)

    def _do():
        tmp_wrapper = self._create_binance_wrapper(
            api_key=api_key,
            api_secret=api_secret,
            mode=mode,
            account_type=account_type,
        )
        syms = tmp_wrapper.fetch_symbols(sort_by_volume=True, top_n=_SYMBOL_FETCH_TOP_N)
        cleaned = []
        seen_local = set()
        for sym in syms or []:
            sym_norm = str(sym or "").strip().upper()
            if not sym_norm:
                continue
            if sym_norm in seen_local:
                continue
            seen_local.add(sym_norm)
            cleaned.append(sym_norm)
        return cleaned

    def _chart_should_render():
        try:
            return bool(self._chart_pending_initial_load or self._is_chart_visible())
        except Exception:
            return False

    def _done(res, err):
        try:
            symbols = []
            if isinstance(res, list) and res:
                symbols = [str(sym or "").strip().upper() for sym in res if str(sym or "").strip()]
            if err or not symbols:
                try:
                    self.log(
                        f"Chart symbol load error for {market_key}: {err or 'no symbols returned'}; using defaults."
                    )
                except Exception:
                    pass
                symbols = list(_DEFAULT_CHART_SYMBOLS)
            self.chart_symbol_cache[market_key] = symbols
            self._chart_needs_render = True
            current_market = self._normalize_chart_market(
                getattr(self, "chart_market_combo", None).currentText()
                if hasattr(self, "chart_market_combo")
                else None
            )
            if current_market == market_key:
                self._update_chart_symbol_options(symbols)
                if symbols:
                    preferred_cfg = self.chart_config.get("symbol")
                    preferred_actual = (
                        self._resolve_chart_symbol_for_api(preferred_cfg, market_key)
                        if preferred_cfg
                        else None
                    )
                    if not preferred_actual or preferred_actual not in symbols:
                        preferred_actual = symbols[0]
                    preferred_display = (
                        self._futures_display_symbol(preferred_actual)
                        if market_key == "Futures"
                        else preferred_actual
                    )
                    from_follow = (market_key == "Futures") and not self._chart_manual_override
                    changed = self._set_chart_symbol(
                        preferred_display,
                        ensure_option=True,
                        from_follow=from_follow,
                    )
                    if from_follow:
                        if changed:
                            self._apply_dashboard_selection_to_chart(load=True)
                    elif changed and _chart_should_render():
                        self.load_chart(auto=True)
                elif _chart_should_render():
                    self.load_chart(auto=True)
        finally:
            self._chart_symbol_loading.discard(market_key)

    worker = CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    worker.finished.connect(_cleanup)
    worker.start()


def _apply_dashboard_selection_to_chart(self, load: bool = False):
    if not getattr(self, "chart_enabled", False):
        return
    should_render = self._chart_pending_initial_load or self._is_chart_visible()
    if not self.chart_auto_follow:
        if load and should_render:
            self.load_chart(auto=True)
        return
    current_market = self._normalize_chart_market(
        getattr(self, "chart_market_combo", None).currentText()
        if hasattr(self, "chart_market_combo")
        else None
    )
    if current_market != "Futures":
        if load and should_render:
            self.load_chart(auto=True)
        return
    changed = False
    symbol = self._selected_dashboard_symbol()
    interval = self._selected_dashboard_interval()
    if symbol:
        display_symbol = self._futures_display_symbol(symbol) if current_market == "Futures" else symbol
        changed = self._set_chart_symbol(display_symbol, ensure_option=True, from_follow=True) or changed
    if interval:
        changed = self._set_chart_interval(interval) or changed
    if (changed and should_render) or (load and should_render):
        self.load_chart(auto=True)


def _selected_dashboard_symbol(self):
    if not getattr(self, "chart_enabled", False):
        return ""
    if not hasattr(self, "symbol_list"):
        return ""
    selected = []
    try:
        for idx in range(self.symbol_list.count()):
            item = self.symbol_list.item(idx)
            if item and item.isSelected():
                sym = item.text().strip().upper()
                if sym:
                    selected.append(sym)
    except Exception:
        return ""
    if selected:
        return selected[0]
    if self.symbol_list.count():
        first_item = self.symbol_list.item(0)
        if first_item:
            return first_item.text().strip().upper()
    return self.chart_config.get("symbol", "")


def _selected_dashboard_interval(self):
    if not getattr(self, "chart_enabled", False):
        return ""
    if not hasattr(self, "interval_list"):
        return ""
    selected = []
    try:
        for idx in range(self.interval_list.count()):
            item = self.interval_list.item(idx)
            if item and item.isSelected():
                iv = item.text().strip()
                if iv:
                    selected.append(iv)
    except Exception:
        return ""
    if selected:
        return selected[0]
    if self.interval_list.count():
        first_item = self.interval_list.item(0)
        if first_item:
            return first_item.text().strip()
    return self.chart_config.get("interval", "")


def _set_chart_symbol(self, symbol: str, ensure_option: bool = False, from_follow: bool = False) -> bool:
    if not getattr(self, "chart_enabled", False):
        return False
    if not hasattr(self, "chart_symbol_combo"):
        return False
    combo = self.chart_symbol_combo
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return False
    before = combo.currentText().strip().upper()
    self._chart_updating = True
    changed = False
    try:
        try:
            with QtCore.QSignalBlocker(combo):
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                elif ensure_option:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
                else:
                    combo.setEditText(normalized)
        except Exception:
            idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif ensure_option:
                combo.addItem(normalized)
                combo.setCurrentIndex(combo.count() - 1)
            else:
                combo.setEditText(normalized)
        after = combo.currentText().strip().upper()
        changed = before != after
        if after:
            self.chart_config["symbol"] = after
    finally:
        self._chart_updating = False
    if changed:
        self._chart_needs_render = True
    if from_follow:
        self._chart_manual_override = False
        self.chart_auto_follow = True
        self.chart_config["auto_follow"] = True
    return changed


def _set_chart_interval(self, interval: str) -> bool:
    if not getattr(self, "chart_enabled", False):
        return False
    if not hasattr(self, "chart_interval_combo"):
        return False
    combo = self.chart_interval_combo
    normalized = str(interval or "").strip()
    if not normalized:
        return False
    before = combo.currentText().strip()
    self._chart_updating = True
    changed = False
    try:
        try:
            with QtCore.QSignalBlocker(combo):
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
        except Exception:
            idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(normalized)
                combo.setCurrentIndex(combo.count() - 1)
        after = combo.currentText().strip()
        changed = before != after
        if after:
            self.chart_config["interval"] = after
    finally:
        self._chart_updating = False
    if changed:
        self._chart_needs_render = True
    return changed


def _map_chart_interval(self, interval: str) -> str | None:
    key = str(interval or "").strip().lower()
    if not key:
        return None
    mapped = _TRADINGVIEW_INTERVAL_MAP.get(key)
    if mapped:
        return mapped
    if key.endswith("m"):
        try:
            minutes = int(float(key[:-1]))
            if minutes > 0:
                return str(minutes)
        except Exception:
            return None
    if key.endswith("h"):
        try:
            hours = float(key[:-1])
            minutes = int(hours * 60)
            if minutes > 0:
                return str(minutes)
        except Exception:
            return None
    if key.endswith("d"):
        try:
            days = int(float(key[:-1]))
            if days > 0:
                return f"{days}D"
        except Exception:
            return None
    if key.endswith("w"):
        try:
            weeks = int(float(key[:-1]))
            if weeks > 0:
                return f"{weeks}W"
        except Exception:
            return None
    if key.endswith("mo") or key.endswith("month") or key.endswith("months"):
        digits = "".join(ch for ch in key if ch.isdigit())
        try:
            qty = int(digits) if digits else 1
        except Exception:
            qty = 1
        if qty > 0:
            return f"{qty}M"
    if key.endswith("y") or key.endswith("year") or key.endswith("years"):
        digits = "".join(ch for ch in key if ch.isdigit())
        try:
            qty = int(digits) if digits else 1
        except Exception:
            qty = 1
        if qty > 0:
            return f"{qty * 12}M"
    return None


def _format_chart_symbol(self, symbol: str, market: str | None = None) -> str:
    raw = str(symbol or "").strip().upper().replace("/", "")
    if ":" in raw:
        return raw
    self._normalize_chart_market(market)
    prefix = _TRADINGVIEW_SYMBOL_PREFIX
    try:
        account_text = (self.account_combo.currentText() or "").strip().lower()
        if "bybit" in account_text:
            prefix = "BYBIT:"
        elif "spot" in account_text:
            prefix = "BINANCE:"
        elif "future" in account_text:
            prefix = "BINANCE:"
    except Exception:
        prefix = _TRADINGVIEW_SYMBOL_PREFIX
    return f"{prefix}{raw}"


def bind_main_window_chart_selection_runtime(
    MainWindow,
    *,
    default_chart_symbols,
    symbol_fetch_top_n,
    tradingview_symbol_prefix,
    tradingview_interval_map,
):
    global _DEFAULT_CHART_SYMBOLS
    global _SYMBOL_FETCH_TOP_N
    global _TRADINGVIEW_SYMBOL_PREFIX
    global _TRADINGVIEW_INTERVAL_MAP

    _DEFAULT_CHART_SYMBOLS = tuple(default_chart_symbols)
    _SYMBOL_FETCH_TOP_N = int(symbol_fetch_top_n)
    _TRADINGVIEW_SYMBOL_PREFIX = str(tradingview_symbol_prefix)
    _TRADINGVIEW_INTERVAL_MAP = dict(tradingview_interval_map)

    MainWindow._futures_display_symbol = _futures_display_symbol
    MainWindow._resolve_chart_symbol_for_api = _resolve_chart_symbol_for_api
    MainWindow._current_dashboard_symbols = _current_dashboard_symbols
    MainWindow._on_chart_controls_changed = _on_chart_controls_changed
    MainWindow._chart_account_type = _chart_account_type
    MainWindow._on_chart_market_changed = _on_chart_market_changed
    MainWindow._load_chart_symbols_async = _load_chart_symbols_async
    MainWindow._apply_dashboard_selection_to_chart = _apply_dashboard_selection_to_chart
    MainWindow._selected_dashboard_symbol = _selected_dashboard_symbol
    MainWindow._selected_dashboard_interval = _selected_dashboard_interval
    MainWindow._set_chart_symbol = _set_chart_symbol
    MainWindow._set_chart_interval = _set_chart_interval
    MainWindow._map_chart_interval = _map_chart_interval
    MainWindow._format_chart_symbol = _format_chart_symbol
