from __future__ import annotations

import copy

from . import main_window_strategy_controls_shared_runtime as shared


def _collect_strategy_controls(self, kind: str) -> dict:
    try:
        if kind == "runtime":
            stop_cfg = shared._normalize_stop_loss(copy.deepcopy(self.config.get("stop_loss")))
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
            stop_cfg = shared._normalize_stop_loss(copy.deepcopy(self.backtest_config.get("stop_loss")))
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
            prepared["stop_loss"] = shared._normalize_stop_loss(self.config.get("stop_loss"))
        connector_val = prepared.get("connector_backend")
        if not connector_val:
            try:
                connector_val = self._runtime_connector_backend(suppress_refresh=True)
            except Exception:
                connector_val = self.config.get("connector_backend")
        prepared["connector_backend"] = shared._normalize_connector_backend_value(connector_val)
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
            prepared["stop_loss"] = shared._normalize_stop_loss(back_cfg.get("stop_loss"))
        connector_val = prepared.get("connector_backend")
        if not connector_val:
            try:
                connector_val = self._backtest_connector_backend()
            except Exception:
                connector_val = back_cfg.get("connector_backend")
        prepared["connector_backend"] = shared._normalize_connector_backend_value(connector_val)
    return prepared
