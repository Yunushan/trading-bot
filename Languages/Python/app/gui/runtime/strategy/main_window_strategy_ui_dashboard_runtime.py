from __future__ import annotations

from PyQt6 import QtCore

from .main_window_strategy_ui_shared_runtime import _default_stop_loss_scope_option


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
                    idx_scope = scope_combo.findData(_default_stop_loss_scope_option())
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
