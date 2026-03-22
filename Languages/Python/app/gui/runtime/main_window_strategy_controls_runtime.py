from __future__ import annotations

import copy

_NORMALIZE_STOP_LOSS_DICT = None
_NORMALIZE_CONNECTOR_BACKEND = None
_SIDE_LABELS: dict[str, str] = {}


def bind_main_window_strategy_controls_runtime(
    main_window_cls,
    *,
    side_labels=None,
    normalize_stop_loss_dict=None,
    normalize_connector_backend=None,
) -> None:
    global _NORMALIZE_STOP_LOSS_DICT
    global _NORMALIZE_CONNECTOR_BACKEND
    global _SIDE_LABELS

    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _SIDE_LABELS = dict(side_labels or {})

    main_window_cls._collect_strategy_controls = _collect_strategy_controls
    main_window_cls._prepare_controls_snapshot = _prepare_controls_snapshot
    main_window_cls._override_debug_enabled = _override_debug_enabled
    main_window_cls._log_override_debug = _log_override_debug
    main_window_cls._normalize_strategy_controls = _normalize_strategy_controls
    main_window_cls._format_strategy_controls_summary = _format_strategy_controls_summary
    main_window_cls._normalize_position_pct_units = staticmethod(_normalize_position_pct_units)


def _normalize_stop_loss(payload):
    func = _NORMALIZE_STOP_LOSS_DICT
    if callable(func):
        try:
            return func(payload)
        except Exception:
            pass
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _normalize_connector_backend_value(value):
    func = _NORMALIZE_CONNECTOR_BACKEND
    if callable(func):
        try:
            return func(value)
        except Exception:
            pass
    return value


def _collect_strategy_controls(self, kind: str) -> dict:
    try:
        if kind == "runtime":
            stop_cfg = _normalize_stop_loss(copy.deepcopy(self.config.get("stop_loss")))
            controls = {
                "side": self._resolve_dashboard_side(),
                "position_pct": float(self.pospct_spin.value()) if hasattr(self, "pospct_spin") else None,
                "position_pct_units": "percent" if hasattr(self, "pospct_spin") else None,
                "loop_interval_override": self._loop_choice_value(getattr(self, "loop_combo", None)),
                "add_only": bool(self.cb_add_only.isChecked()) if hasattr(self, "cb_add_only") else None,
                "stop_loss": stop_cfg,
                "connector_backend": self._runtime_connector_backend(suppress_refresh=True),
            }
            leverage_val = None
            if hasattr(self, "leverage_spin"):
                try:
                    leverage_val = int(self.leverage_spin.value())
                except Exception:
                    leverage_val = None
            acct_text = str(self.config.get("account_type") or "")
            if not acct_text.strip().upper().startswith("FUT"):
                leverage_val = 1
            if leverage_val is not None:
                controls["leverage"] = leverage_val
            account_mode_val = None
            try:
                account_mode_val = self.account_mode_combo.currentData()
            except Exception:
                account_mode_val = None
            if not account_mode_val and hasattr(self, "account_mode_combo"):
                try:
                    account_mode_val = self.account_mode_combo.currentText()
                except Exception:
                    account_mode_val = None
            if account_mode_val:
                controls["account_mode"] = self._normalize_account_mode(account_mode_val)
            return self._normalize_strategy_controls("runtime", controls)
        if kind == "backtest":
            stop_cfg = _normalize_stop_loss(copy.deepcopy(self.backtest_config.get("stop_loss")))
            assets_mode_val = None
            try:
                assets_mode_val = self.backtest_assets_mode_combo.currentData()
            except Exception:
                assets_mode_val = None
            if not assets_mode_val and hasattr(self, "backtest_assets_mode_combo"):
                try:
                    assets_mode_val = self.backtest_assets_mode_combo.currentText()
                except Exception:
                    assets_mode_val = None
            account_mode_val = None
            try:
                account_mode_val = self.backtest_account_mode_combo.currentData()
            except Exception:
                account_mode_val = None
            if not account_mode_val and hasattr(self, "backtest_account_mode_combo"):
                try:
                    account_mode_val = self.backtest_account_mode_combo.currentText()
                except Exception:
                    account_mode_val = None
            controls = {
                "logic": self.backtest_logic_combo.currentText() if hasattr(self, "backtest_logic_combo") else None,
                "capital": float(self.backtest_capital_spin.value()) if hasattr(self, "backtest_capital_spin") else None,
                "position_pct": float(self.backtest_pospct_spin.value()) if hasattr(self, "backtest_pospct_spin") else None,
                "position_pct_units": "percent" if hasattr(self, "backtest_pospct_spin") else None,
                "side": self.backtest_side_combo.currentText() if hasattr(self, "backtest_side_combo") else None,
                "margin_mode": self.backtest_margin_mode_combo.currentText() if hasattr(self, "backtest_margin_mode_combo") else None,
                "position_mode": self.backtest_position_mode_combo.currentText() if hasattr(self, "backtest_position_mode_combo") else None,
                "assets_mode": assets_mode_val,
                "loop_interval_override": self._loop_choice_value(getattr(self, "backtest_loop_combo", None)),
                "leverage": int(self.backtest_leverage_spin.value()) if hasattr(self, "backtest_leverage_spin") else None,
                "stop_loss": stop_cfg,
                "connector_backend": self._backtest_connector_backend(),
            }
            if account_mode_val:
                controls["account_mode"] = self._normalize_account_mode(account_mode_val)
            return self._normalize_strategy_controls("backtest", controls)
    except Exception:
        pass
    return {}


def _prepare_controls_snapshot(self, kind: str, snapshot) -> dict:
    prepared: dict[str, object] = {}
    if isinstance(snapshot, dict):
        try:
            prepared = copy.deepcopy(snapshot)
        except Exception:
            prepared = dict(snapshot)
    else:
        prepared = {}

    def _runtime_default(name: str, getter, fallback=None):
        if name in prepared and prepared.get(name) not in (None, ""):
            return prepared[name]
        try:
            value = getter()
            if value not in (None, ""):
                prepared[name] = value
                return value
        except Exception:
            pass
        if fallback not in (None, ""):
            prepared[name] = fallback
            return fallback
        return prepared.get(name)

    if kind == "runtime":
        _runtime_default(
            "side",
            lambda: self._resolve_dashboard_side() if hasattr(self, "_resolve_dashboard_side") else self.config.get("side"),
            fallback=str(self.config.get("side") or "BOTH").upper(),
        )
        _runtime_default(
            "position_pct",
            lambda: float(self.pospct_spin.value()) if hasattr(self, "pospct_spin") else float(self.config.get("position_pct", 0.0)),
            fallback=float(self.config.get("position_pct", 0.0)),
        )
        units_val = prepared.get("position_pct_units") or self.config.get("position_pct_units") or "percent"
        try:
            prepared["position_pct_units"] = self._normalize_position_pct_units(units_val)
        except Exception:
            prepared["position_pct_units"] = "percent"
        loop_val = prepared.get("loop_interval_override")
        if not loop_val and hasattr(self, "loop_combo"):
            loop_val = self._loop_choice_value(getattr(self, "loop_combo", None))
        loop_val = self._normalize_loop_override(loop_val)
        if loop_val:
            prepared["loop_interval_override"] = loop_val
        _runtime_default(
            "add_only",
            lambda: bool(self.cb_add_only.isChecked()) if hasattr(self, "cb_add_only") else self.config.get("add_only", False),
            fallback=bool(self.config.get("add_only", False)),
        )
        _runtime_default(
            "leverage",
            lambda: int(self.leverage_spin.value()) if hasattr(self, "leverage_spin") else int(self.config.get("leverage", 1)),
            fallback=int(self.config.get("leverage", 1)),
        )
        account_mode_val = prepared.get("account_mode")
        if not account_mode_val and hasattr(self, "account_mode_combo"):
            try:
                account_mode_val = self.account_mode_combo.currentData() or self.account_mode_combo.currentText()
            except Exception:
                account_mode_val = None
        if not account_mode_val:
            account_mode_val = self.config.get("account_mode")
        if account_mode_val:
            try:
                prepared["account_mode"] = self._normalize_account_mode(account_mode_val)
            except Exception:
                prepared["account_mode"] = self.config.get("account_mode")
        stop_cfg = prepared.get("stop_loss")
        if not isinstance(stop_cfg, dict):
            prepared["stop_loss"] = _normalize_stop_loss(self.config.get("stop_loss"))
        connector_val = prepared.get("connector_backend")
        if not connector_val:
            try:
                connector_val = self._runtime_connector_backend(suppress_refresh=True)
            except Exception:
                connector_val = self.config.get("connector_backend")
        prepared["connector_backend"] = _normalize_connector_backend_value(connector_val)
    elif kind == "backtest":
        back_cfg = self.backtest_config if isinstance(getattr(self, "backtest_config", None), dict) else {}
        _runtime_default(
            "logic",
            lambda: self.backtest_logic_combo.currentText() if hasattr(self, "backtest_logic_combo") else back_cfg.get("logic"),
            fallback=back_cfg.get("logic"),
        )
        _runtime_default(
            "capital",
            lambda: float(self.backtest_capital_spin.value()) if hasattr(self, "backtest_capital_spin") else float(back_cfg.get("capital", 0.0)),
            fallback=float(back_cfg.get("capital", 0.0)),
        )
        _runtime_default(
            "position_pct",
            lambda: float(self.backtest_pospct_spin.value()) if hasattr(self, "backtest_pospct_spin") else float(back_cfg.get("position_pct", 0.0)),
            fallback=float(back_cfg.get("position_pct", 0.0)),
        )
        units_val = prepared.get("position_pct_units") or back_cfg.get("position_pct_units") or "percent"
        try:
            prepared["position_pct_units"] = self._normalize_position_pct_units(units_val)
        except Exception:
            prepared["position_pct_units"] = "percent"
        _runtime_default(
            "side",
            lambda: self.backtest_side_combo.currentText() if hasattr(self, "backtest_side_combo") else back_cfg.get("side"),
            fallback=back_cfg.get("side"),
        )
        _runtime_default(
            "margin_mode",
            lambda: self.backtest_margin_mode_combo.currentText() if hasattr(self, "backtest_margin_mode_combo") else back_cfg.get("margin_mode"),
            fallback=back_cfg.get("margin_mode"),
        )
        _runtime_default(
            "position_mode",
            lambda: self.backtest_position_mode_combo.currentText() if hasattr(self, "backtest_position_mode_combo") else back_cfg.get("position_mode"),
            fallback=back_cfg.get("position_mode"),
        )
        _runtime_default(
            "assets_mode",
            lambda: self.backtest_assets_mode_combo.currentData() if hasattr(self, "backtest_assets_mode_combo") else back_cfg.get("assets_mode"),
            fallback=back_cfg.get("assets_mode"),
        )
        account_mode_val = prepared.get("account_mode")
        if not account_mode_val and hasattr(self, "backtest_account_mode_combo"):
            try:
                account_mode_val = self.backtest_account_mode_combo.currentData() or self.backtest_account_mode_combo.currentText()
            except Exception:
                account_mode_val = None
        if not account_mode_val:
            account_mode_val = back_cfg.get("account_mode")
        if account_mode_val:
            try:
                prepared["account_mode"] = self._normalize_account_mode(account_mode_val)
            except Exception:
                prepared["account_mode"] = account_mode_val
        loop_val = prepared.get("loop_interval_override")
        if not loop_val and hasattr(self, "backtest_loop_combo"):
            loop_val = self._loop_choice_value(getattr(self, "backtest_loop_combo", None))
        loop_val = self._normalize_loop_override(loop_val)
        if loop_val:
            prepared["loop_interval_override"] = loop_val
        _runtime_default(
            "leverage",
            lambda: int(self.backtest_leverage_spin.value()) if hasattr(self, "backtest_leverage_spin") else int(back_cfg.get("leverage", 1)),
            fallback=int(back_cfg.get("leverage", 1)),
        )
        stop_cfg = prepared.get("stop_loss")
        if not isinstance(stop_cfg, dict):
            prepared["stop_loss"] = _normalize_stop_loss(back_cfg.get("stop_loss"))
        connector_val = prepared.get("connector_backend")
        if not connector_val:
            try:
                connector_val = self._backtest_connector_backend()
            except Exception:
                connector_val = back_cfg.get("connector_backend")
        prepared["connector_backend"] = _normalize_connector_backend_value(connector_val)
    return prepared


def _override_debug_enabled(self) -> bool:
    return bool(getattr(self, "_override_debug_verbose", False) or self.config.get("debug_override_verbose", False))


def _log_override_debug(self, kind: str, message: str, *, payload: dict | None = None) -> None:
    if not self._override_debug_enabled():
        return
    try:
        suffix = ""
        if payload:
            try:
                import json

                suffix = f" :: {json.dumps(payload, default=str, ensure_ascii=False)}"
            except Exception:
                suffix = f" :: {payload}"
        self.log(f"[Override-{kind}] {message}{suffix}")
    except Exception:
        pass


def _normalize_position_pct_units(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"percent", "%", "perc", "percentage"}:
        return "percent"
    if text in {"fraction", "decimal", "ratio"}:
        return "fraction"
    return ""


def _normalize_strategy_controls(self, kind: str, controls) -> dict:
    if not isinstance(controls, dict):
        return {}
    normalized: dict[str, object] = {}
    if kind == "runtime":
        side_raw = str(controls.get("side") or "").upper()
        if side_raw in _SIDE_LABELS:
            normalized["side"] = side_raw
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                normalized["position_pct"] = float(pos_pct)
            except Exception:
                pass
        units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
        units_norm = self._normalize_position_pct_units(units_val)
        if units_norm:
            normalized["position_pct_units"] = units_norm
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                lev_val = int(leverage)
                if lev_val >= 1:
                    normalized["leverage"] = lev_val
            except Exception:
                pass
        loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
        if loop_override:
            normalized["loop_interval_override"] = loop_override
        add_only = controls.get("add_only")
        if add_only is not None:
            normalized["add_only"] = bool(add_only)
        account_mode = controls.get("account_mode")
        if account_mode:
            normalized["account_mode"] = self._normalize_account_mode(account_mode)
        stop_loss_raw = controls.get("stop_loss")
        if isinstance(stop_loss_raw, dict):
            normalized["stop_loss"] = _normalize_stop_loss(stop_loss_raw)
        backend_val = controls.get("connector_backend")
        if backend_val:
            normalized["connector_backend"] = _normalize_connector_backend_value(backend_val)
    elif kind == "backtest":
        logic_raw = str(controls.get("logic") or "").upper()
        if logic_raw in {"AND", "OR", "SEPARATE"}:
            normalized["logic"] = logic_raw
        capital = controls.get("capital")
        if capital is not None:
            try:
                normalized["capital"] = float(capital)
            except Exception:
                pass
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                normalized["position_pct"] = float(pos_pct)
            except Exception:
                pass
        units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
        units_norm = self._normalize_position_pct_units(units_val)
        if units_norm:
            normalized["position_pct_units"] = units_norm
        side_val = controls.get("side")
        if side_val:
            side_code = str(side_val).upper()
            if side_code not in _SIDE_LABELS:
                side_code = self._canonical_side_from_text(str(side_val))
            if side_code in _SIDE_LABELS:
                normalized["side"] = side_code
        margin_mode = controls.get("margin_mode")
        if margin_mode:
            normalized["margin_mode"] = str(margin_mode)
        position_mode = controls.get("position_mode")
        if position_mode:
            normalized["position_mode"] = str(position_mode)
        assets_mode = controls.get("assets_mode")
        if assets_mode:
            normalized["assets_mode"] = self._normalize_assets_mode(assets_mode)
        account_mode = controls.get("account_mode")
        if account_mode:
            normalized["account_mode"] = self._normalize_account_mode(account_mode)
        loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
        if loop_override:
            normalized["loop_interval_override"] = loop_override
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                normalized["leverage"] = int(leverage)
            except Exception:
                pass
        stop_loss_raw = controls.get("stop_loss")
        if isinstance(stop_loss_raw, dict):
            normalized["stop_loss"] = _normalize_stop_loss(stop_loss_raw)
        backend_val = controls.get("connector_backend")
        if backend_val:
            normalized["connector_backend"] = _normalize_connector_backend_value(backend_val)
    return normalized


def _format_strategy_controls_summary(self, kind: str, controls: dict) -> str:
    if not controls:
        return "-"
    parts: list[str] = []
    if kind == "runtime":
        side = controls.get("side")
        if side:
            parts.append(f"Side={side}")
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                pct_value = float(pos_pct)
                units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                if units_norm == "fraction":
                    pct_value *= 100.0
                parts.append(f"Pos={pct_value:.2f}%")
            except Exception:
                pass
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                parts.append(f"Lev={int(leverage)}x")
            except Exception:
                pass
        loop = controls.get("loop_interval_override") or "auto"
        parts.append(f"Loop={loop}")
        add_only = controls.get("add_only")
        if add_only is not None:
            parts.append(f"AddOnly={'Y' if add_only else 'N'}")
        account_mode = controls.get("account_mode")
        if account_mode:
            parts.append(f"AcctMode={account_mode}")
        stop_loss = controls.get("stop_loss")
        if isinstance(stop_loss, dict):
            if stop_loss.get("enabled"):
                mode = str(stop_loss.get("mode") or "usdt")
                summary_bits = []
                scope_val = str(stop_loss.get("scope") or "per_trade")
                summary_bits.append(f"scope={scope_val}")
                summary_bits.append(f"mode={mode}")
                if mode == "usdt" and stop_loss.get("usdt"):
                    summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                elif mode == "percent" and stop_loss.get("percent"):
                    summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                elif mode == "both":
                    if stop_loss.get("usdt") is not None:
                        summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                    if stop_loss.get("percent") is not None:
                        summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                parts.append(f"SL=On({'; '.join(summary_bits)})")
            else:
                parts.append("SL=Off")
    elif kind == "backtest":
        logic = controls.get("logic")
        if logic:
            parts.append(f"Logic={logic}")
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                pct_value = float(pos_pct)
                units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                if units_norm == "fraction":
                    pct_value *= 100.0
                parts.append(f"Pos={pct_value:.2f}%")
            except Exception:
                pass
        capital = controls.get("capital")
        if capital is not None:
            try:
                parts.append(f"Cap={float(capital):.0f}")
            except Exception:
                pass
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                parts.append(f"Lev={int(leverage)}")
            except Exception:
                pass
        side = controls.get("side")
        if side:
            parts.append(f"Side={side}")
        margin_mode = controls.get("margin_mode")
        if margin_mode:
            parts.append(f"Margin={margin_mode}")
        assets_mode = controls.get("assets_mode")
        if assets_mode:
            parts.append(f"Assets={assets_mode}")
        account_mode = controls.get("account_mode")
        if account_mode:
            parts.append(f"AcctMode={account_mode}")
        stop_loss = controls.get("stop_loss")
        if isinstance(stop_loss, dict):
            if stop_loss.get("enabled"):
                mode = str(stop_loss.get("mode") or "usdt")
                scope_val = str(stop_loss.get("scope") or "per_trade")
                details = []
                details.append(f"mode={mode}")
                details.append(f"scope={scope_val}")
                if stop_loss.get("usdt") not in (None, ""):
                    details.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                if stop_loss.get("percent") not in (None, ""):
                    details.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                parts.append(f"SL=On({'; '.join(details)})")
            else:
                parts.append("SL=Off")
    return ", ".join(parts) if parts else "-"
