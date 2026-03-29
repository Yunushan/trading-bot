from __future__ import annotations

from PyQt6 import QtWidgets

from . import backtest_tab_context_runtime as tab_context_runtime


def build_backtest_indicator_group(self):
    indicator_group = QtWidgets.QGroupBox("Indicators")
    indicator_group.setMinimumWidth(220)
    indicator_group.setMaximumWidth(340)
    indicator_group.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )
    ind_layout = QtWidgets.QGridLayout(indicator_group)
    self.backtest_indicator_widgets.clear()
    row = 0
    for key, params in self.backtest_config.get("indicators", {}).items():
        label = tab_context_runtime._INDICATOR_DISPLAY_NAMES.get(key, key)
        cb = QtWidgets.QCheckBox(label)
        cb.setProperty("indicator_key", key)
        cb.setChecked(bool(params.get("enabled", False)))
        cb.toggled.connect(lambda checked, _key=key: self._backtest_toggle_indicator(_key, checked))
        btn = QtWidgets.QPushButton("Buy-Sell Values")
        btn.clicked.connect(lambda _=False, _key=key: self._open_backtest_params(_key))
        ind_layout.addWidget(cb, row, 0)
        ind_layout.addWidget(btn, row, 1)
        self.backtest_indicator_widgets[key] = (cb, btn)
        row += 1
    return indicator_group


__all__ = ["build_backtest_indicator_group"]
