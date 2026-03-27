from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .main_window_strategy_ui_shared_runtime import _default_account_mode_option


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
    self._apply_runtime_account_mode_constraints(
        self.config.get("account_mode", _default_account_mode_option())
    )
