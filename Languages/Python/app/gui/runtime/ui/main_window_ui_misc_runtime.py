from __future__ import annotations

import sys

from PyQt6 import QtGui, QtWidgets


def bind_main_window_ui_misc_runtime(main_window_cls) -> None:
    main_window_cls._apply_initial_geometry = _apply_initial_geometry
    main_window_cls._on_indicator_toggled = _on_indicator_toggled
    main_window_cls._on_positions_view_changed = _on_positions_view_changed
    main_window_cls._on_positions_auto_resize_changed = _on_positions_auto_resize_changed
    main_window_cls._on_positions_auto_resize_columns_changed = _on_positions_auto_resize_columns_changed


def _apply_initial_geometry(self):
    """Ensure the window fits on the active screen on Linux desktops."""
    if not sys.platform.startswith("linux"):
        return
    try:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        if not avail or not avail.isValid():
            return
        min_w, min_h = 1024, 640
        target_w = min(max(min_w, int(avail.width() * 0.9)), avail.width())
        target_h = min(max(min_h, int(avail.height() * 0.9)), avail.height())
        self.setMinimumSize(min(min_w, avail.width()), min(min_h, avail.height()))
        self.resize(target_w, target_h)
        frame_geo = self.frameGeometry()
        frame_geo.moveCenter(avail.center())
        self.move(frame_geo.topLeft())
    except Exception:
        pass


def _on_indicator_toggled(self, key: str, checked: bool):
    try:
        indicators = self.config.setdefault("indicators", {})
        params = indicators.setdefault(key, {})
        params["enabled"] = bool(checked)
    except Exception:
        pass


def _on_positions_view_changed(self, index: int):
    try:
        text = self.positions_view_combo.itemText(index)
    except Exception:
        text = ""
    mode = "cumulative"
    if isinstance(text, str) and text.lower().startswith("per"):
        mode = "per_trade"
    self._positions_view_mode = mode
    try:
        self._render_positions_table()
    except Exception:
        pass


def _on_positions_auto_resize_changed(self, state: int):
    enabled = bool(state)
    self.config["positions_auto_resize_rows"] = enabled
    try:
        if enabled:
            self.pos_table.resizeRowsToContents()
        else:
            default_height = 44
            try:
                default_height = int(
                    self.pos_table.verticalHeader().defaultSectionSize() or default_height
                )
            except Exception:
                default_height = 44
            self.pos_table.verticalHeader().setDefaultSectionSize(default_height)
            for row in range(self.pos_table.rowCount()):
                try:
                    self.pos_table.setRowHeight(row, default_height)
                except Exception:
                    pass
    except Exception:
        pass


def _on_positions_auto_resize_columns_changed(self, state: int):
    enabled = bool(state)
    self.config["positions_auto_resize_columns"] = enabled
    try:
        if enabled:
            self.pos_table.resizeColumnsToContents()
        else:
            header = self.pos_table.horizontalHeader()
            try:
                header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
            except Exception:
                try:
                    header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
                except Exception:
                    pass
    except Exception:
        pass
