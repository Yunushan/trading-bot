from __future__ import annotations

from . import main_window_start_strategy_runtime
from . import main_window_stop_strategy_runtime

_STRATEGY_ENGINE_CLS = None
_MAKE_ENGINE_KEY = None
_COERCE_BOOL = None
_NORMALIZE_STOP_LOSS_DICT = None
_FORMAT_INDICATOR_LIST = None
_SYMBOL_FETCH_TOP_N = 200


def _make_engine_key_safe(symbol: str, interval: str, indicators: list[str] | None = None) -> str:
    func = _MAKE_ENGINE_KEY
    if not callable(func):
        base = f"{symbol}:{interval}"
        if indicators:
            return f"{base}|{','.join(indicators)}"
        return base
    try:
        return str(func(symbol, interval, indicators))
    except Exception:
        base = f"{symbol}:{interval}"
        if indicators:
            return f"{base}|{','.join(indicators)}"
        return base


def _coerce_bool_safe(value, default=False):
    func = _COERCE_BOOL
    if not callable(func):
        return bool(default)
    try:
        return func(value, default)
    except Exception:
        return bool(default)


def _normalize_stop_loss_dict_safe(value):
    func = _NORMALIZE_STOP_LOSS_DICT
    if not callable(func):
        return value
    try:
        return func(value)
    except Exception:
        return value


def _format_indicator_list_safe(keys) -> str:
    func = _FORMAT_INDICATOR_LIST
    if not callable(func):
        try:
            return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
        except Exception:
            return ""
    try:
        return str(func(keys))
    except Exception:
        return ""


def bind_main_window_control_runtime(
    main_window_cls,
    *,
    strategy_engine_cls=None,
    make_engine_key=None,
    coerce_bool=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
    symbol_fetch_top_n: int = 200,
) -> None:
    global _STRATEGY_ENGINE_CLS
    global _MAKE_ENGINE_KEY
    global _COERCE_BOOL
    global _NORMALIZE_STOP_LOSS_DICT
    global _FORMAT_INDICATOR_LIST
    global _SYMBOL_FETCH_TOP_N

    _STRATEGY_ENGINE_CLS = strategy_engine_cls
    _MAKE_ENGINE_KEY = make_engine_key
    _COERCE_BOOL = coerce_bool
    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _FORMAT_INDICATOR_LIST = format_indicator_list
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))

    main_window_cls.on_leverage_changed = on_leverage_changed
    main_window_cls.refresh_symbols = refresh_symbols
    main_window_cls.apply_futures_modes = apply_futures_modes
    main_window_cls.start_strategy = start_strategy
    main_window_cls._stop_strategy_sync = _stop_strategy_sync
    main_window_cls.stop_strategy_async = stop_strategy_async


def on_leverage_changed(self, value):
    try:
        value_int = int(value)
    except Exception:
        value_int = 0
    try:
        self.config["leverage"] = value_int
    except Exception:
        pass
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        for eng in engines.values():
            try:
                conf = getattr(eng, "config", None)
                if isinstance(conf, dict):
                    conf["leverage"] = value_int
            except Exception:
                pass
    except Exception:
        pass
    try:
        if (
            value_int > 0
            and hasattr(self, "shared_binance")
            and self.shared_binance
            and (self.account_combo.currentText() or "").upper().startswith("FUT")
        ):
            self.shared_binance.set_futures_leverage(value_int)
    except Exception:
        pass


def refresh_symbols(self):
    from ...workers import CallWorker as _CallWorker

    self.refresh_symbols_btn.setEnabled(False)
    self.refresh_symbols_btn.setText("Refreshing...")

    def _do():
        tmp_wrapper = self._create_binance_wrapper(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
        )
        syms = tmp_wrapper.fetch_symbols(sort_by_volume=True, top_n=_SYMBOL_FETCH_TOP_N)
        return syms

    def _done(res, err):
        try:
            if err or not res:
                self.log(f"Failed to refresh symbols: {err or 'no symbols'}")
                return
            self.symbol_list.clear()
            all_symbols = []
            filtered = []
            seen = set()
            for sym in res or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm or sym_norm in seen:
                    continue
                seen.add(sym_norm)
                all_symbols.append(sym_norm)
                if sym_norm.endswith("USDT"):
                    filtered.append(sym_norm)
            if filtered:
                self.symbol_list.addItems(filtered)
            if all_symbols:
                self.chart_symbol_cache["Futures"] = all_symbols
            current_market = self._normalize_chart_market(
                getattr(self, "chart_market_combo", None).currentText()
                if hasattr(self, "chart_market_combo")
                else None
            )
            if current_market == "Futures":
                self._update_chart_symbol_options(all_symbols if all_symbols else filtered)
                self._chart_needs_render = True
                if self.chart_auto_follow and not self._chart_manual_override:
                    self._apply_dashboard_selection_to_chart(load=True)
                elif self._chart_pending_initial_load or self._is_chart_visible():
                    self.load_chart(auto=True)
            self.log(
                f"Loaded {self.symbol_list.count()} USDT-pair symbols for {self.account_combo.currentText()}."
            )
        finally:
            self.refresh_symbols_btn.setEnabled(True)
            self.refresh_symbols_btn.setText("Refresh Symbols")

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.start()


def apply_futures_modes(self):
    from ...workers import CallWorker as _CallWorker

    mm = self.margin_mode_combo.currentText().upper()
    pos_mode = self.position_mode_combo.currentText()
    hedge = pos_mode.strip().lower() == "hedge"
    assets_mode_value = self.assets_mode_combo.currentData() or self.assets_mode_combo.currentText()
    assets_mode_norm = self._normalize_assets_mode(assets_mode_value)
    multi = assets_mode_norm == "Multi-Assets"
    tif = self.tif_combo.currentText()
    gtdm = int(self.gtd_minutes_spin.value())

    def _do():
        try:
            self.shared_binance.set_position_mode(hedge)
        except Exception:
            pass
        try:
            self.shared_binance.set_multi_assets_mode(multi)
        except Exception:
            pass
        return True

    def _done(res, err):
        if err:
            self.log(f"Apply futures modes error: {err}")
            return
        self.config["margin_mode"] = "Isolated" if mm == "ISOLATED" else "Cross"
        self.config["position_mode"] = "Hedge" if hedge else "One-way"
        self.config["assets_mode"] = "Multi-Assets" if multi else "Single-Asset"
        self.config["tif"] = tif
        self.config["gtd_minutes"] = gtdm

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.start()


def start_strategy(self):
    return main_window_start_strategy_runtime.start_strategy(
        self,
        strategy_engine_cls=_STRATEGY_ENGINE_CLS,
        make_engine_key=_make_engine_key_safe,
        coerce_bool=_coerce_bool_safe,
        normalize_stop_loss_dict=_normalize_stop_loss_dict_safe,
        format_indicator_list=_format_indicator_list_safe,
    )


def _stop_strategy_sync(self, close_positions: bool = True, auth: dict | None = None) -> dict:
    return main_window_stop_strategy_runtime.stop_strategy_sync(
        self,
        close_positions=close_positions,
        auth=auth,
        strategy_engine_cls=_STRATEGY_ENGINE_CLS,
    )


def stop_strategy_async(self, close_positions: bool = False, blocking: bool = False):
    return main_window_stop_strategy_runtime.stop_strategy_async(
        self,
        close_positions=close_positions,
        blocking=blocking,
        stop_strategy_sync_fn=lambda **kwargs: _stop_strategy_sync(self, **kwargs),
    )

