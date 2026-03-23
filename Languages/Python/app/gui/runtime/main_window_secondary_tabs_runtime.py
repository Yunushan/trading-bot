from __future__ import annotations

import os
import sys

from PyQt6 import QtCore, QtWidgets

_LAZY_SECONDARY_TAB_PROPERTY = "_bot_lazy_secondary_tab_key"
_LAZY_SECONDARY_TAB_PREWARM_KEYS = ("code", "backtest")


def _create_lazy_secondary_tab_placeholder(key: str, message: str) -> QtWidgets.QWidget:
    tab = QtWidgets.QWidget()
    tab.setProperty(_LAZY_SECONDARY_TAB_PROPERTY, key)

    layout = QtWidgets.QVBoxLayout(tab)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.addStretch()

    label = QtWidgets.QLabel(message)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setStyleSheet("color: #94a3b8; font-size: 14px;")
    layout.addWidget(label)

    layout.addStretch()
    return tab


def _register_lazy_secondary_tab(self, key: str, title: str, message: str) -> QtWidgets.QWidget:
    placeholder = _create_lazy_secondary_tab_placeholder(key, message)
    self._lazy_secondary_tabs[key] = {
        "title": title,
        "placeholder": placeholder,
        "widget": None,
        "loading": False,
        "loaded": False,
    }
    self.tabs.addTab(placeholder, title)
    return placeholder


def _mount_lazy_secondary_tab_content(container: QtWidgets.QWidget, content: QtWidgets.QWidget) -> None:
    layout = container.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(container)
    while layout.count():
        item = layout.takeAt(0)
        child_widget = item.widget()
        if child_widget is not None:
            child_widget.setParent(None)
            child_widget.deleteLater()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    content.setParent(container)
    layout.addWidget(content)


def _load_lazy_secondary_tab(self, key: str):
    meta = (getattr(self, "_lazy_secondary_tabs", None) or {}).get(key)
    if not meta:
        return None
    if meta.get("loaded"):
        return meta.get("widget")
    if meta.get("loading"):
        return None

    placeholder = meta.get("placeholder")
    if placeholder is None:
        return meta.get("widget")

    meta["loading"] = True
    created_widget = None
    try:
        if key == "backtest":
            created_widget = self._create_backtest_tab(add_to_tabs=False)
            if created_widget is not None:
                self.backtest_tab = placeholder
                _mount_lazy_secondary_tab_content(placeholder, created_widget)
                try:
                    self._refresh_symbol_interval_pairs("backtest")
                except Exception:
                    pass
                try:
                    self._initialize_backtest_ui_defaults()
                except Exception:
                    pass
                try:
                    self._update_connector_labels()
                except Exception:
                    pass
        elif key == "code":
            created_widget = self._init_code_language_tab()
            if created_widget is not None:
                self.code_tab = placeholder
                _mount_lazy_secondary_tab_content(placeholder, created_widget)

        if created_widget is None:
            return None

        meta["loaded"] = True
        meta["widget"] = placeholder
        meta["content"] = created_widget
        placeholder.setProperty(_LAZY_SECONDARY_TAB_PROPERTY, "")
        QtCore.QTimer.singleShot(
            0,
            lambda window=self, tabs=getattr(self, "tabs", None): (
                window._on_tab_changed(tabs.currentIndex())
                if tabs is not None and tabs.currentIndex() >= 0
                else None
            ),
        )
        return placeholder
    finally:
        meta["loading"] = False


def _lazy_secondary_tab_prewarm_enabled() -> bool:
    if sys.platform != "win32":
        return False
    flag = str(os.environ.get("BOT_PRELOAD_LAZY_SECONDARY_TABS", "1")).strip().lower()
    return flag not in {"0", "false", "no", "off"}


def _lazy_secondary_tab_prewarm_ready(self) -> bool:
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    try:
        if app is not None and app.applicationState() != QtCore.Qt.ApplicationState.ApplicationActive:
            return False
    except Exception:
        return False
    try:
        if not self.isVisible():
            return False
    except Exception:
        return False
    try:
        if self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
            return False
    except Exception:
        return False
    try:
        tabs = getattr(self, "tabs", None)
        if tabs is not None and tabs.currentIndex() != 0:
            return False
    except Exception:
        return False
    return True


def _continue_lazy_secondary_tab_prewarm(self):
    if not _lazy_secondary_tab_prewarm_enabled():
        return
    queue = list(getattr(self, "_lazy_secondary_tab_prewarm_queue", []) or [])
    if not queue:
        self._lazy_secondary_tab_prewarm_done = True
        return
    if not _lazy_secondary_tab_prewarm_ready(self):
        QtCore.QTimer.singleShot(350, lambda window=self: window._continue_lazy_secondary_tab_prewarm())
        return
    next_key = str(queue.pop(0) or "").strip().lower()
    self._lazy_secondary_tab_prewarm_queue = queue
    if next_key:
        try:
            self._load_lazy_secondary_tab(next_key)
        except Exception:
            pass
    if queue:
        QtCore.QTimer.singleShot(220, lambda window=self: window._continue_lazy_secondary_tab_prewarm())
    else:
        self._lazy_secondary_tab_prewarm_done = True


def _schedule_lazy_secondary_tab_prewarm(self):
    if not _lazy_secondary_tab_prewarm_enabled():
        return
    if getattr(self, "_lazy_secondary_tab_prewarm_started", False):
        return
    lazy_tabs = getattr(self, "_lazy_secondary_tabs", None)
    if not isinstance(lazy_tabs, dict) or not lazy_tabs:
        return
    queue = [
        key
        for key in _LAZY_SECONDARY_TAB_PREWARM_KEYS
        if key in lazy_tabs and not bool((lazy_tabs.get(key) or {}).get("loaded"))
    ]
    if not queue:
        self._lazy_secondary_tab_prewarm_done = True
        return
    self._lazy_secondary_tab_prewarm_started = True
    self._lazy_secondary_tab_prewarm_queue = queue
    QtCore.QTimer.singleShot(250, lambda window=self: window._continue_lazy_secondary_tab_prewarm())


def _initialize_secondary_tabs(self):
    self._lazy_secondary_tabs = {}
    self._lazy_secondary_tab_prewarm_started = False
    self._lazy_secondary_tab_prewarm_done = False
    self._lazy_secondary_tab_prewarm_queue = []
    self._create_positions_tab()
    _register_lazy_secondary_tab(
        self,
        "backtest",
        "Backtest",
        "Backtest tools load the first time you open this tab.",
    )

    liquidation_tab = self._init_liquidation_heatmap_tab()
    if liquidation_tab is not None:
        self.liquidation_tab = liquidation_tab
        self.tabs.addTab(liquidation_tab, "Liquidation Heatmap")

    _register_lazy_secondary_tab(
        self,
        "code",
        "Code Languages",
        "Code language tools load the first time you open this tab.",
    )


def bind_main_window_secondary_tabs_runtime(MainWindow):
    MainWindow._initialize_secondary_tabs = _initialize_secondary_tabs
    MainWindow._load_lazy_secondary_tab = _load_lazy_secondary_tab
    MainWindow._schedule_lazy_secondary_tab_prewarm = _schedule_lazy_secondary_tab_prewarm
    MainWindow._continue_lazy_secondary_tab_prewarm = _continue_lazy_secondary_tab_prewarm
