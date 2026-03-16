from __future__ import annotations

import re

from PyQt6 import QtCore, QtWidgets

_ACCOUNT_MODE_OPTIONS: tuple[str, ...] = ("Classic Trading",)
_STOP_LOSS_SCOPE_OPTIONS: tuple[str, ...] = ("per_trade",)


def bind_main_window_strategy_ui_runtime(
    main_window_cls,
    *,
    account_mode_options=None,
    stop_loss_scope_options=None,
) -> None:
    global _ACCOUNT_MODE_OPTIONS
    global _STOP_LOSS_SCOPE_OPTIONS

    _ACCOUNT_MODE_OPTIONS = tuple(account_mode_options or ("Classic Trading",))
    _STOP_LOSS_SCOPE_OPTIONS = tuple(stop_loss_scope_options or ("per_trade",))

    main_window_cls._register_runtime_active_exemption = _register_runtime_active_exemption
    main_window_cls._loop_choice_value = _loop_choice_value
    main_window_cls._set_loop_combo_value = _set_loop_combo_value
    main_window_cls._on_dashboard_template_changed = _on_dashboard_template_changed
    main_window_cls._on_runtime_loop_changed = _on_runtime_loop_changed
    main_window_cls._on_allow_opposite_changed = _on_allow_opposite_changed
    main_window_cls._on_backtest_loop_changed = _on_backtest_loop_changed
    main_window_cls._on_runtime_account_mode_changed = _on_runtime_account_mode_changed
    main_window_cls._on_backtest_account_mode_changed = _on_backtest_account_mode_changed
    main_window_cls._apply_runtime_account_mode_constraints = _apply_runtime_account_mode_constraints
    main_window_cls._apply_backtest_account_mode_constraints = _apply_backtest_account_mode_constraints
    main_window_cls._enforce_portfolio_margin_constraints = _enforce_portfolio_margin_constraints
    main_window_cls._on_lead_trader_toggled = _on_lead_trader_toggled
    main_window_cls._on_lead_trader_option_changed = _on_lead_trader_option_changed
    main_window_cls._apply_lead_trader_state = _apply_lead_trader_state
    main_window_cls._normalize_loop_override = staticmethod(_normalize_loop_override)


def _register_runtime_active_exemption(self, widget):
    if widget is None:
        return
    try:
        exemptions = getattr(self, "_runtime_active_exemptions", None)
        if isinstance(exemptions, set):
            exemptions.add(widget)
    except Exception:
        pass


def _normalize_loop_override(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"\s+", "", text.lower())
    if re.match(r"^\d+(s|m|h|d|w)?$", cleaned):
        return cleaned
    return None


def _loop_choice_value(self, combo: QtWidgets.QComboBox | None) -> str:
    if combo is None:
        return ""
    try:
        data = combo.currentData()
    except Exception:
        data = ""
    if data is None:
        data = ""
    normalized = self._normalize_loop_override(data)
    if normalized:
        return normalized
    return ""


def _set_loop_combo_value(self, combo: QtWidgets.QComboBox | None, value: str | None) -> None:
    if combo is None:
        return
    target = self._normalize_loop_override(value)
    if not target:
        target = ""
    idx = combo.findData(target)
    if idx < 0 and target:
        combo.addItem(target, target)
        idx = combo.count() - 1
    try:
        blocker = QtCore.QSignalBlocker(combo)
    except Exception:
        blocker = None
    if idx < 0:
        idx = 0
    combo.setCurrentIndex(idx)
    if blocker is not None:
        del blocker


def _on_dashboard_template_changed(self):
    if not hasattr(self, "template_combo"):
        return
    key = self.template_combo.currentData()
    if key is None:
        return
    key = str(key or "")
    self.config["dashboard_template"] = key
    if not key:
        return
    template = self._dashboard_templates.get(key)
    if not template:
        return

    pct_value = float(template.get("position_pct", self.config.get("position_pct", 2.0)))
    self.config["position_pct"] = pct_value
    self.config["position_pct_units"] = "percent"
    display_pct = pct_value if pct_value > 1.0 else pct_value * 100.0
    if hasattr(self, "pospct_spin"):
        self.pospct_spin.blockSignals(True)
        self.pospct_spin.setValue(display_pct)
        self.pospct_spin.blockSignals(False)

    leverage_value = int(template.get("leverage", self.config.get("leverage", 5)))
    self.config["leverage"] = leverage_value
    if hasattr(self, "leverage_spin"):
        self.leverage_spin.setValue(leverage_value)

    margin_mode = template.get("margin_mode")
    if margin_mode:
        self.config["margin_mode"] = margin_mode
        if hasattr(self, "margin_mode_combo"):
            combo = self.margin_mode_combo
            combo.blockSignals(True)
            if hasattr(QtCore.Qt, "MatchFlag"):
                idx = combo.findText(margin_mode, QtCore.Qt.MatchFlag.MatchFixedString)
            else:
                idx = combo.findText(margin_mode)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    if key == "top10":
        updated_sl = self._runtime_stop_loss_update(
            enabled=True,
            mode="percent",
            percent=20.0,
            scope="per_trade",
        )
        checkbox = getattr(self, "stop_loss_enable_cb", None)
        if checkbox is not None:
            with QtCore.QSignalBlocker(checkbox):
                checkbox.setChecked(True)
        mode_combo = getattr(self, "stop_loss_mode_combo", None)
        if mode_combo is not None:
            with QtCore.QSignalBlocker(mode_combo):
                idx_mode = mode_combo.findData("percent")
                if idx_mode < 0:
                    idx_mode = 0
                mode_combo.setCurrentIndex(idx_mode)
        percent_spin = getattr(self, "stop_loss_percent_spin", None)
        if percent_spin is not None:
            with QtCore.QSignalBlocker(percent_spin):
                percent_spin.setValue(20.0)
        scope_combo = getattr(self, "stop_loss_scope_combo", None)
        if scope_combo is not None:
            with QtCore.QSignalBlocker(scope_combo):
                idx_scope = scope_combo.findData("per_trade")
                if idx_scope < 0:
                    idx_scope = scope_combo.findData(_STOP_LOSS_SCOPE_OPTIONS[0])
                if idx_scope is not None and idx_scope >= 0:
                    scope_combo.setCurrentIndex(idx_scope)
        self.config["stop_loss"] = updated_sl
        self._update_runtime_stop_loss_widgets()

    indicators = template.get("indicators", {})
    for ind_key, params in indicators.items():
        cfg = self.config["indicators"].setdefault(ind_key, {})
        cfg.update(params)
        cfg["enabled"] = True
        widgets = self.indicator_widgets.get(ind_key) if hasattr(self, "indicator_widgets") else None
        if widgets:
            cb, _btn = widgets
            if not cb.isChecked():
                cb.setChecked(True)
            else:
                self.config["indicators"][ind_key] = cfg


def _on_runtime_loop_changed(self, *_args):
    value = self._loop_choice_value(getattr(self, "loop_combo", None))
    self.config["loop_interval_override"] = value


def _on_allow_opposite_changed(self, state: int) -> None:
    allow = state == QtCore.Qt.CheckState.Checked
    self.config["allow_opposite_positions"] = allow
    guard_obj = getattr(self, "guard", None)
    if guard_obj and hasattr(guard_obj, "allow_opposite"):
        dual_enabled = False
        try:
            if self.shared_binance is not None and hasattr(self.shared_binance, "get_futures_dual_side"):
                dual_enabled = bool(self.shared_binance.get_futures_dual_side())
        except Exception:
            dual_enabled = False
        try:
            guard_obj.allow_opposite = allow and dual_enabled
        except Exception:
            pass


def _on_backtest_loop_changed(self, *_args):
    value = self._loop_choice_value(getattr(self, "backtest_loop_combo", None))
    self._update_backtest_config("loop_interval_override", value)


def _on_runtime_account_mode_changed(self, index: int) -> None:
    combo = getattr(self, "account_mode_combo", None)
    if combo is None:
        return
    if index is None or index < 0:
        index = combo.currentIndex()
    try:
        data = combo.itemData(index)
    except Exception:
        data = None
    if data is None:
        data = combo.itemText(index)
    normalized = self._normalize_account_mode(data)
    self.config["account_mode"] = normalized
    self._apply_runtime_account_mode_constraints(normalized)


def _on_backtest_account_mode_changed(self, index: int) -> None:
    combo = getattr(self, "backtest_account_mode_combo", None)
    if combo is None:
        return
    if index is None or index < 0:
        index = combo.currentIndex()
    try:
        data = combo.itemData(index)
    except Exception:
        data = None
    if data is None:
        data = combo.itemText(index)
    normalized = self._normalize_account_mode(data)
    self._update_backtest_config("account_mode", normalized)
    self._apply_backtest_account_mode_constraints(normalized)


def _apply_runtime_account_mode_constraints(self, normalized_mode: str) -> None:
    self._enforce_portfolio_margin_constraints(
        normalized_mode,
        getattr(self, "margin_mode_combo", None),
        runtime=True,
    )


def _apply_backtest_account_mode_constraints(self, normalized_mode: str) -> None:
    self._enforce_portfolio_margin_constraints(
        normalized_mode,
        getattr(self, "backtest_margin_mode_combo", None),
        runtime=False,
    )


def _enforce_portfolio_margin_constraints(
    self,
    normalized_mode: str,
    combo: QtWidgets.QComboBox | None,
    *,
    runtime: bool,
) -> None:
    if combo is None:
        return
    is_portfolio = normalized_mode == "Portfolio Margin"
    blocker = None
    try:
        blocker = QtCore.QSignalBlocker(combo)
    except Exception:
        blocker = None
    if is_portfolio:
        idx_cross = -1
        try:
            idx_cross = combo.findText("Cross", QtCore.Qt.MatchFlag.MatchFixedString)
        except Exception:
            try:
                idx_cross = combo.findText("Cross")
            except Exception:
                idx_cross = -1
        if idx_cross < 0:
            for pos in range(combo.count()):
                text = str(combo.itemText(pos)).strip().lower()
                if text == "cross":
                    idx_cross = pos
                    break
        if idx_cross >= 0:
            combo.setCurrentIndex(idx_cross)
    if blocker is not None:
        del blocker
    combo.setEnabled(not is_portfolio)
    if is_portfolio:
        if runtime:
            self.config["margin_mode"] = "Cross"
        else:
            self.backtest_config["margin_mode"] = "Cross"
            self.config.setdefault("backtest", {})["margin_mode"] = "Cross"


def _on_lead_trader_toggled(self, checked: bool) -> None:
    enabled = bool(checked)
    self.config["lead_trader_enabled"] = enabled
    self._apply_lead_trader_state(enabled)


def _on_lead_trader_option_changed(self, index: int) -> None:
    combo = getattr(self, "lead_trader_combo", None)
    if combo is None:
        return
    if index is None or index < 0:
        index = combo.currentIndex()
    try:
        value = combo.itemData(index)
    except Exception:
        value = None
    if value is None:
        value = combo.itemText(index)
    self.config["lead_trader_profile"] = str(value)


def _apply_lead_trader_state(self, enabled: bool) -> None:
    combo = getattr(self, "lead_trader_combo", None)
    if combo is not None:
        combo.setEnabled(bool(enabled))
    self._apply_runtime_account_mode_constraints(self.config.get("account_mode", _ACCOUNT_MODE_OPTIONS[0]))
