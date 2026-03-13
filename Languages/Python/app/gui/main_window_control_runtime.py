from __future__ import annotations

import copy
import time

from PyQt6 import QtCore

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
    from ..workers import CallWorker as _CallWorker

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
    from ..workers import CallWorker as _CallWorker

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
    strategy_engine_cls = _STRATEGY_ENGINE_CLS
    if strategy_engine_cls is None:
        try:
            self.log("Strategy runtime is not available.")
        except Exception:
            pass
        return
    if getattr(self, "_is_stopping_engines", False):
        self.log("Stop in progress; cannot start new engines.")
        return
    shared = getattr(self, "shared_binance", None)
    if shared is not None and getattr(shared, "_emergency_close_requested", False):
        self.log("Emergency close-all in progress; wait for it to finish before starting.")
        return
    try:
        strategy_engine_cls.resume_trading()
    except Exception:
        pass
    started = 0
    try:
        default_loop_override = self._loop_choice_value(getattr(self, "loop_combo", None))
        runtime_ctx = self._override_ctx("runtime")
        account_type_text = (self.account_combo.currentText() or "Futures").strip()
        is_futures_account = account_type_text.upper().startswith("FUT")
        pair_entries: list[dict] = []
        table = runtime_ctx.get("table") if runtime_ctx else None
        if table is not None:
            try:
                selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
            except Exception:
                selected_rows = []
            if selected_rows:
                for row in selected_rows:
                    sym_item = table.item(row, 0)
                    iv_item = table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ""
                    iv_raw = iv_item.text().strip() if iv_item else ""
                    iv_canonical = self._canonicalize_interval(iv_raw)
                    if sym and iv_canonical:
                        entry_obj = None
                        try:
                            entry_obj = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                        except Exception:
                            entry_obj = None
                        indicators = None
                        controls = None
                        if isinstance(entry_obj, dict):
                            indicators = entry_obj.get("indicators")
                            controls = entry_obj.get("strategy_controls")
                            if isinstance(indicators, (list, tuple)):
                                indicators = sorted(
                                    {str(k).strip() for k in indicators if str(k).strip()}
                                )
                            else:
                                indicators = None
                        pair_entries.append(
                            {
                                "symbol": sym,
                                "interval": iv_canonical,
                                "indicators": list(indicators) if indicators else None,
                                "strategy_controls": self._normalize_strategy_controls(
                                    "runtime", controls
                                ),
                            }
                        )
                    elif sym and iv_raw:
                        self.log(
                            f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}."
                        )
        if not pair_entries:
            for entry in self.config.get("runtime_symbol_interval_pairs", []) or []:
                sym = str((entry or {}).get("symbol") or "").strip().upper()
                interval_val = str((entry or {}).get("interval") or "").strip()
                iv_canonical = self._canonicalize_interval(interval_val)
                if not (sym and iv_canonical):
                    if sym and interval_val:
                        self.log(
                            f"Skipping unsupported interval '{interval_val}' for {account_type_text} {sym}."
                        )
                    continue
                indicators = entry.get("indicators")
                if isinstance(indicators, (list, tuple)):
                    indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
                else:
                    indicators = None
                controls = self._normalize_strategy_controls(
                    "runtime", entry.get("strategy_controls")
                )
                pair_entries.append(
                    {
                        "symbol": sym,
                        "interval": iv_canonical,
                        "indicators": list(indicators) if indicators else None,
                        "strategy_controls": controls,
                    }
                )
        if not pair_entries:
            self.log("No symbol/interval overrides configured. Add entries before starting.")
            return

        combos_map: dict[tuple[str, str], dict] = {}
        for entry in pair_entries:
            sym = str(entry.get("symbol") or "").strip().upper()
            iv_raw = str(entry.get("interval") or "").strip()
            iv = self._canonicalize_interval(iv_raw)
            if not sym or not iv:
                if sym and iv_raw:
                    self.log(
                        f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}."
                    )
                continue
            indicators = entry.get("indicators")
            if isinstance(indicators, (list, tuple)):
                indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
            else:
                indicators = []
            controls = entry.get("strategy_controls")
            key = (sym, iv)
            item = combos_map.setdefault(
                key,
                {"symbol": sym, "interval": iv, "indicators": [], "strategy_controls": {}},
            )
            if indicators:
                try:
                    ind_set = set(item.get("indicators") or [])
                    ind_set.update(indicators)
                    item["indicators"] = sorted(ind_set)
                except Exception:
                    item["indicators"] = indicators
            if isinstance(controls, dict):
                try:
                    ctrl = item.setdefault("strategy_controls", {})
                    for key_name, val in controls.items():
                        if val is not None:
                            ctrl[key_name] = val
                except Exception:
                    item["strategy_controls"] = controls

        combos = list(combos_map.values())
        if not combos:
            self.log("No valid symbol/interval overrides found.")
            return

        connector_name = self._connector_label_text(
            self._runtime_connector_backend(suppress_refresh=True)
        )
        self.log(
            f"Starting strategy with {len(combos)} symbol/interval loops. Connector: {connector_name}."
        )

        try:
            self.config["position_pct_units"] = "percent"
        except Exception:
            pass

        total_jobs = len(combos)
        concurrency = strategy_engine_cls.concurrent_limit(total_jobs)
        if total_jobs > concurrency:
            self.log(
                f"{total_jobs} symbol/interval loops requested; limiting concurrent execution to {concurrency} to keep the UI responsive."
            )

        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = self._create_binance_wrapper(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
            )

        if not hasattr(self, "strategy_engines"):
            self.strategy_engines = {}

        try:
            if self.shared_binance is not None:
                self.shared_binance.account_type = account_type_text.upper()
                indicator_source_text = (self.ind_source_combo.currentText() or "").strip()
                if indicator_source_text:
                    self.shared_binance.indicator_source = indicator_source_text
        except Exception:
            pass

        guard_obj = getattr(self, "guard", None)
        guard_can_open = getattr(guard_obj, "can_open", None) if guard_obj else None
        if guard_obj:
            try:
                if self.shared_binance is not None and hasattr(guard_obj, "attach_wrapper"):
                    guard_obj.attach_wrapper(self.shared_binance)
            except Exception as guard_attach_err:
                self.log(f"Guard attach error: {guard_attach_err}")
            if is_futures_account:
                try:
                    dual_enabled = False
                    if self.shared_binance is not None and hasattr(
                        self.shared_binance, "get_futures_dual_side"
                    ):
                        dual_enabled = bool(self.shared_binance.get_futures_dual_side())
                    allow_opposite_cfg = _coerce_bool_safe(
                        self.config.get("allow_opposite_positions"), True
                    )
                    if hasattr(guard_obj, "allow_opposite"):
                        guard_obj.allow_opposite = dual_enabled and allow_opposite_cfg
                    if hasattr(guard_obj, "strict_symbol_side"):
                        guard_obj.strict_symbol_side = False
                    if dual_enabled and not allow_opposite_cfg:
                        self.log(
                            "Hedge mode detected on Binance account; opposite-side entries are disabled so the bot will close "
                            "existing positions before flipping."
                        )
                except Exception:
                    pass
            else:
                try:
                    if hasattr(guard_obj, "allow_opposite"):
                        guard_obj.allow_opposite = True
                except Exception:
                    pass
            try:
                if hasattr(guard_obj, "reset"):
                    guard_obj.reset()
            except Exception as guard_reset_err:
                self.log(f"Guard reset error: {guard_reset_err}")
            guard_jobs = [
                {"symbol": combo.get("symbol"), "interval": combo.get("interval")}
                for combo in combos
                if combo.get("symbol") and combo.get("interval")
            ]
            try:
                if hasattr(guard_obj, "reconcile_with_exchange"):
                    guard_account_type = str(
                        getattr(self.shared_binance, "account_type", account_type_text)
                        or account_type_text
                    ).upper()
                    guard_obj.reconcile_with_exchange(
                        self.shared_binance,
                        guard_jobs,
                        account_type=guard_account_type,
                    )
            except Exception as guard_reconcile_err:
                self.log(f"Guard reconcile warning: {guard_reconcile_err}")

        for combo in combos:
            sym = combo.get("symbol")
            iv = combo.get("interval")
            if not sym or not iv:
                continue
            indicator_override = combo.get("indicators")
            indicator_list = []
            if isinstance(indicator_override, (list, tuple)):
                indicator_list = [str(k).strip() for k in indicator_override if str(k).strip()]
            elif indicator_override:
                indicator_list = [str(indicator_override).strip()]
            key = _make_engine_key_safe(sym, iv, indicator_list)
            try:
                if key in self.strategy_engines and getattr(
                    self.strategy_engines[key], "is_alive", lambda: False
                )():
                    self.log(f"Engine already running for {key}, skipping.")
                    continue

                controls = dict(combo.get("strategy_controls") or {})
                units_override = self._normalize_position_pct_units(
                    controls.get("position_pct_units")
                )
                cfg = copy.deepcopy(self.config)
                cfg["symbol"] = sym
                cfg["interval"] = iv
                position_pct_override = controls.get("position_pct")
                if position_pct_override is not None:
                    try:
                        cfg["position_pct"] = float(position_pct_override)
                        if units_override:
                            cfg["position_pct_units"] = units_override
                        else:
                            cfg.pop("position_pct_units", None)
                    except Exception:
                        cfg["position_pct"] = float(
                            self.pospct_spin.value() or self.config.get("position_pct", 100.0)
                        )
                        cfg["position_pct_units"] = "percent"
                else:
                    cfg["position_pct"] = float(
                        self.pospct_spin.value() or self.config.get("position_pct", 100.0)
                    )
                    cfg["position_pct_units"] = "percent"
                side_override = controls.get("side") or self._resolve_dashboard_side()
                cfg["side"] = side_override
                leverage_override = controls.get("leverage")
                if leverage_override is not None:
                    try:
                        cfg["leverage"] = max(1, int(leverage_override))
                    except Exception:
                        pass
                stop_loss_override = controls.get("stop_loss")
                if isinstance(stop_loss_override, dict):
                    cfg["stop_loss"] = _normalize_stop_loss_dict_safe(
                        copy.deepcopy(stop_loss_override)
                    )
                else:
                    cfg["stop_loss"] = _normalize_stop_loss_dict_safe(
                        self.config.get("stop_loss")
                    )
                account_mode_override = controls.get("account_mode")
                if account_mode_override:
                    cfg["account_mode"] = self._normalize_account_mode(account_mode_override)
                cfg["add_only"] = bool(controls.get("add_only", self.config.get("add_only", False)))
                loop_override_entry = controls.get("loop_interval_override") or default_loop_override
                loop_override_entry = self._normalize_loop_override(loop_override_entry)
                if loop_override_entry:
                    cfg["loop_interval_override"] = loop_override_entry
                else:
                    cfg.pop("loop_interval_override", None)

                indicators_cfg = cfg.get("indicators", {}) or {}
                if indicator_list:
                    indicator_set = set(indicator_list)
                    if isinstance(indicators_cfg, dict):
                        for ind_key, params in indicators_cfg.items():
                            try:
                                params["enabled"] = ind_key in indicator_set
                            except Exception:
                                try:
                                    indicators_cfg[ind_key] = dict(params)
                                    indicators_cfg[ind_key]["enabled"] = ind_key in indicator_set
                                except Exception:
                                    pass
                active_indicators = []
                try:
                    active_indicators = [
                        ind_key
                        for ind_key, params in indicators_cfg.items()
                        if isinstance(params, dict) and params.get("enabled")
                    ]
                except Exception:
                    active_indicators = []
                if not active_indicators:
                    if indicator_list:
                        active_indicators = list(indicator_list)
                    else:
                        active_indicators = self._get_selected_indicator_keys("runtime")
                active_indicators = sorted(
                    {str(k).strip() for k in (active_indicators or []) if str(k).strip()}
                )
                override_indicators = sorted(
                    {str(k).strip() for k in (indicator_list or []) if str(k).strip()}
                )

                eng = strategy_engine_cls(
                    self.shared_binance,
                    cfg,
                    log_callback=self.log,
                    trade_callback=self._on_trade_signal,
                    loop_interval_override=loop_override_entry,
                    can_open_callback=guard_can_open,
                )
                if guard_obj and hasattr(eng, "set_guard"):
                    try:
                        eng.set_guard(guard_obj)
                    except Exception:
                        pass
                eng.start()
                self.strategy_engines[key] = eng
                try:
                    self._engine_indicator_map[key] = {
                        "symbol": sym,
                        "interval": iv,
                        "side": cfg.get("side", "BOTH"),
                        "override_indicators": override_indicators,
                        "configured_indicators": active_indicators,
                        "stop_loss_enabled": bool(cfg.get("stop_loss", {}).get("enabled")),
                    }
                except Exception:
                    pass
                indicator_note = ""
                if active_indicators:
                    indicator_note = (
                        f" (Indicators: {_format_indicator_list_safe(active_indicators)})"
                    )
                strat_summary = self._format_strategy_controls_summary("runtime", controls)
                summary_note = f" | {strat_summary}" if strat_summary and strat_summary != "-" else ""
                self.log(f"Loop start for {key}{indicator_note}{summary_note}.")
                started += 1
            except Exception as exc:
                self.log(f"Failed to start engine for {key}: {exc}")

        if started == 0:
            self.log("No new engines started (already running?)")
    except Exception as exc:
        try:
            self.log(f"Start error: {exc}")
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass


def _stop_strategy_sync(self, close_positions: bool = True, auth: dict | None = None) -> dict:
    """Synchronous helper to stop engines and optionally close all positions."""
    result: dict = {"ok": True}
    try:
        try:
            self._is_stopping_engines = True
        except Exception:
            pass
        try:
            strategy_engine_cls = _STRATEGY_ENGINE_CLS
            if strategy_engine_cls is not None:
                strategy_engine_cls.pause_trading()
        except Exception:
            pass
        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "pause_new"):
                guard_obj.pause_new()
        except Exception:
            pass
        engines = {}
        if hasattr(self, "strategy_engines") and isinstance(self.strategy_engines, dict):
            engines = dict(self.strategy_engines)

        if engines:
            self._is_stopping_engines = True
            stop_deadline = time.time() + 2.5
            for _, eng in engines.items():
                try:
                    if hasattr(eng, "stop"):
                        eng.stop()
                except Exception:
                    pass
            for _, eng in engines.items():
                try:
                    remaining = max(0.0, stop_deadline - time.time())
                    if remaining <= 0.0:
                        break
                    eng.join(timeout=min(0.25, remaining))
                except Exception:
                    continue
            still_alive: list[str] = []
            for key, eng in engines.items():
                try:
                    alive = bool(getattr(eng, "is_alive", lambda: False)())
                except Exception:
                    alive = False
                if alive:
                    still_alive.append(str(key))
            try:
                self.strategy_engines.clear()
            except Exception:
                pass
            try:
                self._engine_indicator_map.clear()
            except Exception:
                pass
            if still_alive:
                self.log(
                    f"Signaled loops to stop but {len(still_alive)} engine(s) are still shutting down: {', '.join(still_alive)}"
                )
            else:
                self.log("Stopped all strategy engines.")
        else:
            self.log("No engines to stop.")

        close_result = None
        if close_positions:
            try:
                if auth is None:
                    auth = self._snapshot_auth_state()
                fast_close = False
                try:
                    mode_txt = str(auth.get("mode") or "").lower()
                    fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
                except Exception:
                    fast_close = False
                self.shared_binance = self._build_wrapper_from_values(auth)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_result"] = cancel_res
                except Exception as cancel_exc:
                    self.log(f"Cancel open orders failed: {cancel_exc}")
                close_result = self._close_all_positions_blocking(auth=auth, fast=fast_close)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_after_close"] = cancel_res
                except Exception:
                    pass
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
                self.log(f"Failed to trigger close-all: {exc}")
            result["close_all_result"] = close_result
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        try:
            self.log(f"Stop error: {exc}")
        except Exception:
            pass
    finally:
        try:
            self._is_stopping_engines = False
        except Exception:
            pass
        result["_sync_runtime_state"] = True
    return result


def stop_strategy_async(self, close_positions: bool = False, blocking: bool = False):
    """Stop all StrategyEngine threads without auto-closing positions unless explicitly requested."""
    auth_snapshot = self._snapshot_auth_state() if close_positions else None

    def _process_stop_result(res):
        if not isinstance(res, dict):
            return res
        if not res.get("ok", True):
            try:
                self.log(f"Stop warning: {res.get('error')}")
            except Exception:
                pass
        close_details = res.get("close_all_result", None)
        if close_details is not None:
            try:
                self._handle_close_all_result(close_details)
            except Exception:
                pass
        if res.get("_sync_runtime_state"):
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return res

    if blocking:
        return _process_stop_result(
            _stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot)
        )

    try:
        from ..workers import CallWorker as _CallWorker
    except Exception:
        return _process_stop_result(
            _stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot)
        )

    def _do():
        return _stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot)

    def _done(res, err):
        if err:
            try:
                self.log(f"Stop error: {err}")
            except Exception:
                pass
            return
        _process_stop_result(res)

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

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
