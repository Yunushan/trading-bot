from __future__ import annotations

import copy

from PyQt6 import QtCore


def start_strategy(
    self,
    *,
    strategy_engine_cls=None,
    make_engine_key=None,
    coerce_bool=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
) -> None:
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

    def _make_engine_key(symbol: str, interval: str, indicators: list[str] | None = None) -> str:
        if callable(make_engine_key):
            try:
                return str(make_engine_key(symbol, interval, indicators))
            except Exception:
                pass
        base = f"{symbol}:{interval}"
        if indicators:
            return f"{base}|{','.join(indicators)}"
        return base

    def _coerce_bool(value, default=False):
        if callable(coerce_bool):
            try:
                return coerce_bool(value, default)
            except Exception:
                pass
        return bool(default)

    def _normalize_stop_loss(value):
        if callable(normalize_stop_loss_dict):
            try:
                return normalize_stop_loss_dict(value)
            except Exception:
                pass
        return value

    def _format_indicator_list(keys) -> str:
        if callable(format_indicator_list):
            try:
                return str(format_indicator_list(keys))
            except Exception:
                pass
        try:
            return ", ".join(str(key).strip() for key in (keys or []) if str(key).strip())
        except Exception:
            return ""

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
            self._sync_service_config_snapshot()
        except Exception:
            pass
        try:
            self._service_request_start(
                requested_job_count=len(combos),
                source="desktop-start",
            )
        except Exception:
            pass

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
                    allow_opposite_cfg = _coerce_bool(
                        self.config.get("allow_opposite_positions"), True
                    )
                    if hasattr(guard_obj, "allow_opposite"):
                        guard_obj.allow_opposite = dual_enabled and allow_opposite_cfg
                    if hasattr(guard_obj, "strict_symbol_side"):
                        guard_obj.strict_symbol_side = False
                    if dual_enabled and not allow_opposite_cfg:
                        self.log(
                            "Hedge mode detected on Binance account; opposite-side entries are disabled so the bot will close existing positions before flipping."
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
            key = _make_engine_key(sym, iv, indicator_list)
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
                    cfg["stop_loss"] = _normalize_stop_loss(copy.deepcopy(stop_loss_override))
                else:
                    cfg["stop_loss"] = _normalize_stop_loss(self.config.get("stop_loss"))
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
                    indicator_note = f" (Indicators: {_format_indicator_list(active_indicators)})"
                strat_summary = self._format_strategy_controls_summary("runtime", controls)
                summary_note = f" | {strat_summary}" if strat_summary and strat_summary != "-" else ""
                self.log(f"Loop start for {key}{indicator_note}{summary_note}.")
                started += 1
            except Exception as exc:
                self.log(f"Failed to start engine for {key}: {exc}")

        if started == 0:
            self.log("No new engines started (already running?)")
            try:
                self._service_mark_start_failed(
                    reason="No new engines started.",
                    source="desktop-start",
                )
            except Exception:
                pass
    except Exception as exc:
        try:
            self.log(f"Start error: {exc}")
        except Exception:
            pass
        try:
            self._service_mark_start_failed(
                reason=f"Start error: {exc}",
                source="desktop-start",
            )
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass
