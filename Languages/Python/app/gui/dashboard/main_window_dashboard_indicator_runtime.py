from __future__ import annotations

from PyQt6 import QtWidgets

_INDICATOR_DISPLAY_NAMES = {}
_ParamDialog = None


def _create_dashboard_indicator_section(self, scroll_layout):
    ind_group = QtWidgets.QGroupBox("Indicators")
    layout = QtWidgets.QGridLayout(ind_group)

    self._indicator_runtime_controls = []
    row = 0
    for key, params in self.config["indicators"].items():
        label = _INDICATOR_DISPLAY_NAMES.get(key, key)
        cb = QtWidgets.QCheckBox(label)
        cb.setProperty("indicator_key", key)
        cb.setChecked(bool(params.get("enabled", False)))

        def make_toggle_handler(_key=key):
            def _toggle(checked):
                self._on_indicator_toggled(_key, checked)

            return _toggle

        cb.toggled.connect(make_toggle_handler())
        btn = QtWidgets.QPushButton("Buy-Sell Values")

        def make_handler(_key=key, _params=params):
            def handler():
                dlg = _ParamDialog(
                    _key,
                    _params,
                    self,
                    display_name=_INDICATOR_DISPLAY_NAMES.get(_key, _key),
                )
                if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                    self.config["indicators"][_key].update(dlg.get_params())
                    self.indicator_widgets[_key][0].setChecked(
                        bool(self.config["indicators"][_key].get("enabled", False))
                    )

            return handler

        btn.clicked.connect(make_handler())
        layout.addWidget(cb, row, 0)
        layout.addWidget(btn, row, 1)
        self.indicator_widgets[key] = (cb, btn)
        self._indicator_runtime_controls.extend([cb, btn])
        row += 1

    scroll_layout.addWidget(ind_group)


def bind_main_window_dashboard_indicator_runtime(
    MainWindow,
    *,
    indicator_display_names,
    param_dialog_cls,
):
    global _INDICATOR_DISPLAY_NAMES
    global _ParamDialog

    _INDICATOR_DISPLAY_NAMES = dict(indicator_display_names)
    _ParamDialog = param_dialog_cls

    MainWindow._create_dashboard_indicator_section = _create_dashboard_indicator_section
