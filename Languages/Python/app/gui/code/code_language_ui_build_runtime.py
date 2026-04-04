from __future__ import annotations

import os

from PyQt6 import QtCore, QtWidgets

from .code_language_catalog import (
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_OPTIONS,
    STARTER_LANGUAGE_OPTIONS,
)


def code_tab_auto_refresh_versions_enabled() -> bool:
    default_flag = "1"
    raw_value = str(os.environ.get("BOT_CODE_TAB_AUTO_CHECK_VERSIONS", default_flag) or default_flag).strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def ensure_rust_framework_cards(self) -> None:
    if getattr(self, "_starter_rust_framework_cards", None):
        return

    starter_card_cls = getattr(self, "_code_tab_starter_card_cls", None)
    rust_framework_row = getattr(self, "_rust_framework_cards_row", None)
    rust_framework_parent = getattr(self, "_rust_framework_cards_widget", None)
    if starter_card_cls is None or rust_framework_row is None:
        return

    self._starter_rust_framework_cards = {}
    self._starter_rust_framework_base_subtitles = {}

    for opt in RUST_FRAMEWORK_OPTIONS:
        card = starter_card_cls(
            opt["key"],
            opt["title"],
            opt["subtitle"],
            opt["accent"],
            opt.get("badge"),
            disabled=opt.get("disabled", False),
            parent=rust_framework_parent,
        )
        card.clicked.connect(self._code_tab_select_rust_framework)
        card.setMinimumWidth(170)
        rust_framework_row.addWidget(card, 1)
        self._starter_rust_framework_cards[opt["key"]] = card
        self._starter_rust_framework_base_subtitles[opt["key"]] = str(opt.get("subtitle") or "").strip()
    rust_framework_row.addStretch()


def init_code_language_tab(
    self,
    *,
    starter_card_cls,
    resolve_dependency_targets_for_config,
    parent: QtWidgets.QWidget | None = None,
):
    tab = QtWidgets.QWidget(parent)
    outer_layout = QtWidgets.QVBoxLayout(tab)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    scroll = QtWidgets.QScrollArea(tab)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    outer_layout.addWidget(scroll)

    content = QtWidgets.QWidget(scroll)
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(12)
    scroll.setWidget(content)

    description = QtWidgets.QLabel(
        "Select your preferred code language. "
        "Folders for each language are created automatically inside the project so you can keep related assets organized.",
        content,
    )
    description.setWordWrap(True)
    layout.addWidget(description)

    self._starter_language_cards = {}
    self._starter_language_base_subtitles = {}
    self._starter_rust_framework_cards = {}
    self._starter_rust_framework_base_subtitles = {}
    self._code_tab_starter_card_cls = starter_card_cls
    self._starter_market_cards = {}
    self._starter_crypto_cards = {}
    self._starter_forex_cards = {}

    lang_label = QtWidgets.QLabel("Choose your language", content)
    lang_label.setStyleSheet("font-size: 20px; font-weight: 600;")
    layout.addWidget(lang_label)
    lang_row = QtWidgets.QHBoxLayout()
    lang_row.setSpacing(12)
    for opt in STARTER_LANGUAGE_OPTIONS:
        card = starter_card_cls(
            opt["config_key"],
            opt["title"],
            opt["subtitle"],
            opt["accent"],
            opt.get("badge"),
            disabled=opt.get("disabled", False),
            parent=content,
        )
        card.clicked.connect(self._code_tab_select_language)
        card.setMinimumWidth(180)
        lang_row.addWidget(card, 1)
        self._starter_language_cards[opt["config_key"]] = card
        self._starter_language_base_subtitles[opt["config_key"]] = str(opt.get("subtitle") or "").strip()
    lang_row.addStretch()
    layout.addLayout(lang_row)

    rust_framework_label = QtWidgets.QLabel("Choose your Rust framework", content)
    rust_framework_label.setStyleSheet("font-size: 18px; font-weight: 600;")
    layout.addWidget(rust_framework_label)
    self._rust_framework_section_label = rust_framework_label

    rust_framework_widget = QtWidgets.QWidget(content)
    rust_framework_row = QtWidgets.QHBoxLayout(rust_framework_widget)
    rust_framework_row.setContentsMargins(0, 0, 0, 0)
    rust_framework_row.setSpacing(12)
    self._rust_framework_cards_row = rust_framework_row
    layout.addWidget(rust_framework_widget)
    self._rust_framework_cards_widget = rust_framework_widget

    status_widget = QtWidgets.QWidget(content)
    status_layout = QtWidgets.QHBoxLayout(status_widget)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(12)
    self.pnl_active_label_code_tab = QtWidgets.QLabel(status_widget)
    self.pnl_closed_label_code_tab = QtWidgets.QLabel(status_widget)
    self.bot_status_label_code_tab = QtWidgets.QLabel(status_widget)
    self.bot_time_label_code_tab = QtWidgets.QLabel("Bot Active Time: --", status_widget)
    for lbl in (self.pnl_active_label_code_tab, self.pnl_closed_label_code_tab):
        if lbl is not None:
            lbl.setStyleSheet("font-weight: 600;")
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(lbl)
    status_layout.addStretch()
    for lbl in (self.bot_status_label_code_tab, self.bot_time_label_code_tab):
        if lbl is not None:
            lbl.setStyleSheet("font-weight: 600;")
            status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_code_tab, self.pnl_closed_label_code_tab)
    layout.addWidget(status_widget)

    self._dep_version_labels = {}
    self._dep_version_targets = []
    self._dep_version_checkboxes = {}
    versions_group = QtWidgets.QGroupBox("Environment Versions", content)
    versions_group.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    )
    versions_group_layout = QtWidgets.QVBoxLayout(versions_group)
    versions_group_layout.setContentsMargins(8, 12, 8, 8)
    versions_group_layout.setSpacing(6)

    versions_container = QtWidgets.QWidget(versions_group)
    versions_layout = QtWidgets.QGridLayout(versions_container)
    versions_layout.setContentsMargins(6, 6, 6, 6)
    versions_layout.setColumnStretch(0, 0)
    versions_layout.setColumnStretch(1, 0)
    versions_layout.setColumnStretch(2, 0)
    versions_layout.setColumnStretch(3, 0)
    versions_layout.setColumnStretch(4, 0)
    versions_layout.setColumnStretch(5, 0)
    versions_layout.setColumnStretch(6, 1)
    versions_layout.setVerticalSpacing(8)
    versions_layout.setHorizontalSpacing(12)
    versions_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)

    versions_scroll = QtWidgets.QScrollArea(versions_group)
    versions_scroll.setWidgetResizable(True)
    versions_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    versions_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    versions_scroll.setWidget(versions_container)
    versions_scroll.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    )
    versions_scroll.setMinimumHeight(240)
    versions_scroll.setMaximumHeight(420)

    self._dep_versions_container = versions_container
    self._dep_versions_layout = versions_layout
    self._dep_versions_scroll = versions_scroll
    self._dep_versions_group = versions_group

    version_btn_row = QtWidgets.QHBoxLayout()
    self._dependency_selection_status_label = QtWidgets.QLabel("0 selected", content)
    self._dependency_selection_status_label.setStyleSheet("color: #94a3b8; font-weight: 600;")
    version_btn_row.addWidget(self._dependency_selection_status_label)
    version_btn_row.addStretch()
    self._version_update_selected_btn = QtWidgets.QPushButton("Update Selected", content)
    self._version_update_selected_btn.clicked.connect(self._update_selected_dependency_versions)
    version_btn_row.addWidget(self._version_update_selected_btn)
    self._version_update_all_btn = QtWidgets.QPushButton("Update All", content)
    self._version_update_all_btn.clicked.connect(self._update_all_dependency_versions)
    version_btn_row.addWidget(self._version_update_all_btn)
    self._version_refresh_btn = QtWidgets.QPushButton("Check Versions", content)
    self._version_refresh_btn.clicked.connect(self._refresh_dependency_versions)
    version_btn_row.addWidget(self._version_refresh_btn)
    versions_group_layout.addLayout(version_btn_row)
    versions_group_layout.addWidget(versions_scroll, 1)
    layout.addWidget(versions_group, 0)

    self._update_bot_status()
    try:
        self._ensure_language_exchange_paths()
    except Exception:
        pass
    self._refresh_code_tab_from_config()
    try:
        self._ensure_cpp_process_watchdog()
    except Exception:
        pass
    try:
        self._ensure_rust_process_watchdog()
    except Exception:
        pass
    try:
        self._update_dependency_action_buttons()
    except Exception:
        pass
    return tab


__all__ = [
    "code_tab_auto_refresh_versions_enabled",
    "ensure_rust_framework_cards",
    "init_code_language_tab",
]
