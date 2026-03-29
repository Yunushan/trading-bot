from __future__ import annotations

import copy

from .start_shared_runtime import (
    _coerce_bool,
    _format_indicator_list,
    _make_engine_key,
    _normalize_indicator_keys,
    _normalize_stop_loss,
)


def _prepare_strategy_runtime_start(
    self,
    *,
    combos: list[dict],
    account_type_text: str,
    is_futures_account: bool,
    strategy_engine_cls=None,
    coerce_bool=None,
):
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
                    self.shared_binance,
                    "get_futures_dual_side",
                ):
                    dual_enabled = bool(self.shared_binance.get_futures_dual_side())
                allow_opposite_cfg = _coerce_bool(
                    self.config.get("allow_opposite_positions"),
                    True,
                    coerce_bool=coerce_bool,
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

    return guard_obj, guard_can_open


def _start_strategy_engines(
    self,
    *,
    combos: list[dict],
    default_loop_override,
    strategy_engine_cls=None,
    make_engine_key=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
    guard_obj=None,
    guard_can_open=None,
) -> int:
    started = 0
    for combo in combos:
        sym = combo.get("symbol")
        iv = combo.get("interval")
        if not sym or not iv:
            continue

        indicator_list = _coerce_indicator_override(combo.get("indicators"))
        key = _make_engine_key(sym, iv, indicator_list, make_engine_key=make_engine_key)
        try:
            if key in self.strategy_engines and getattr(
                self.strategy_engines[key],
                "is_alive",
                lambda: False,
            )():
                self.log(f"Engine already running for {key}, skipping.")
                continue

            controls = dict(combo.get("strategy_controls") or {})
            cfg, active_indicators, override_indicators, loop_override_entry = (
                _build_engine_config(
                    self,
                    sym=sym,
                    iv=iv,
                    controls=controls,
                    default_loop_override=default_loop_override,
                    indicator_list=indicator_list,
                    normalize_stop_loss_dict=normalize_stop_loss_dict,
                )
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
                    " (Indicators: "
                    + _format_indicator_list(
                        active_indicators,
                        format_indicator_list=format_indicator_list,
                    )
                    + ")"
                )
            strat_summary = self._format_strategy_controls_summary("runtime", controls)
            summary_note = f" | {strat_summary}" if strat_summary and strat_summary != "-" else ""
            self.log(f"Loop start for {key}{indicator_note}{summary_note}.")
            started += 1
        except Exception as exc:
            self.log(f"Failed to start engine for {key}: {exc}")

    return started


def _coerce_indicator_override(value) -> list[str]:
    indicators = _normalize_indicator_keys(value)
    if indicators:
        return indicators
    if value and not isinstance(value, (list, tuple, set)):
        value_text = str(value).strip()
        if value_text:
            return [value_text]
    return []


def _build_engine_config(
    self,
    *,
    sym: str,
    iv: str,
    controls: dict,
    default_loop_override,
    indicator_list: list[str],
    normalize_stop_loss_dict=None,
) -> tuple[dict, list[str], list[str], str]:
    units_override = self._normalize_position_pct_units(controls.get("position_pct_units"))
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
        cfg["stop_loss"] = _normalize_stop_loss(
            copy.deepcopy(stop_loss_override),
            normalize_stop_loss_dict=normalize_stop_loss_dict,
        )
    else:
        cfg["stop_loss"] = _normalize_stop_loss(
            self.config.get("stop_loss"),
            normalize_stop_loss_dict=normalize_stop_loss_dict,
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

    active_indicators = _resolve_active_indicators(self, cfg, indicator_list)
    override_indicators = _normalize_indicator_keys(indicator_list)
    return cfg, active_indicators, override_indicators, loop_override_entry


def _resolve_active_indicators(self, cfg: dict, indicator_list: list[str]) -> list[str]:
    indicators_cfg = cfg.get("indicators", {}) or {}
    if indicator_list:
        indicator_set = set(indicator_list)
        if isinstance(indicators_cfg, dict):
            for indicator_key, params in indicators_cfg.items():
                try:
                    params["enabled"] = indicator_key in indicator_set
                except Exception:
                    try:
                        indicators_cfg[indicator_key] = dict(params)
                        indicators_cfg[indicator_key]["enabled"] = (
                            indicator_key in indicator_set
                        )
                    except Exception:
                        pass

    active_indicators: list[str] = []
    try:
        active_indicators = [
            indicator_key
            for indicator_key, params in indicators_cfg.items()
            if isinstance(params, dict) and params.get("enabled")
        ]
    except Exception:
        active_indicators = []

    if not active_indicators:
        if indicator_list:
            active_indicators = list(indicator_list)
        else:
            active_indicators = self._get_selected_indicator_keys("runtime")

    return _normalize_indicator_keys(active_indicators)
