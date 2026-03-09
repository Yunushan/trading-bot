from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.gui.code_language_catalog import (
    CPP_CODE_LANGUAGE_KEY,
    CPP_SUPPORTED_EXCHANGE_KEY,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_OPTIONS,
    RUST_FRAMEWORK_PATHS,
    RUST_SHARED_PATHS,
    STARTER_CRYPTO_EXCHANGES,
    STARTER_LANGUAGE_OPTIONS,
)


def init_code_language_tab(self, *, starter_card_cls, resolve_dependency_targets_for_config):
    tab = QtWidgets.QWidget()
    outer_layout = QtWidgets.QVBoxLayout(tab)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    outer_layout.addWidget(scroll)

    content = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(12)
    scroll.setWidget(content)

    description = QtWidgets.QLabel(
        "Select your preferred code language. "
        "Folders for each language are created automatically inside the project so you can keep related assets organized."
    )
    description.setWordWrap(True)
    layout.addWidget(description)

    self._starter_language_cards = {}
    self._starter_language_base_subtitles = {}
    self._starter_rust_framework_cards = {}
    self._starter_rust_framework_base_subtitles = {}
    self._starter_market_cards = {}
    self._starter_crypto_cards = {}
    self._starter_forex_cards = {}

    lang_label = QtWidgets.QLabel("Choose your language")
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
        )
        card.clicked.connect(self._code_tab_select_language)
        card.setMinimumWidth(180)
        lang_row.addWidget(card, 1)
        self._starter_language_cards[opt["config_key"]] = card
        self._starter_language_base_subtitles[opt["config_key"]] = str(opt.get("subtitle") or "").strip()
    lang_row.addStretch()
    layout.addLayout(lang_row)

    rust_framework_label = QtWidgets.QLabel("Choose your Rust framework")
    rust_framework_label.setStyleSheet("font-size: 18px; font-weight: 600;")
    layout.addWidget(rust_framework_label)
    self._rust_framework_section_label = rust_framework_label

    rust_framework_widget = QtWidgets.QWidget()
    rust_framework_row = QtWidgets.QHBoxLayout(rust_framework_widget)
    rust_framework_row.setContentsMargins(0, 0, 0, 0)
    rust_framework_row.setSpacing(12)
    for opt in RUST_FRAMEWORK_OPTIONS:
        card = starter_card_cls(
            opt["key"],
            opt["title"],
            opt["subtitle"],
            opt["accent"],
            opt.get("badge"),
            disabled=opt.get("disabled", False),
        )
        card.clicked.connect(self._code_tab_select_rust_framework)
        card.setMinimumWidth(170)
        rust_framework_row.addWidget(card, 1)
        self._starter_rust_framework_cards[opt["key"]] = card
        self._starter_rust_framework_base_subtitles[opt["key"]] = str(opt.get("subtitle") or "").strip()
    rust_framework_row.addStretch()
    layout.addWidget(rust_framework_widget)
    self._rust_framework_cards_widget = rust_framework_widget

    status_widget = QtWidgets.QWidget()
    status_layout = QtWidgets.QHBoxLayout(status_widget)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(12)
    self.pnl_active_label_code_tab = QtWidgets.QLabel()
    self.pnl_closed_label_code_tab = QtWidgets.QLabel()
    self.bot_status_label_code_tab = QtWidgets.QLabel()
    self.bot_time_label_code_tab = QtWidgets.QLabel("Bot Active Time: --")
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
    self._dep_version_targets = resolve_dependency_targets_for_config(self.config)
    versions_group = QtWidgets.QGroupBox("Environment Versions")
    versions_group.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    )
    versions_group_layout = QtWidgets.QVBoxLayout(versions_group)
    versions_group_layout.setContentsMargins(8, 12, 8, 8)
    versions_group_layout.setSpacing(6)

    versions_container = QtWidgets.QWidget()
    versions_layout = QtWidgets.QGridLayout(versions_container)
    versions_layout.setContentsMargins(6, 6, 6, 6)
    versions_layout.setColumnStretch(0, 0)
    versions_layout.setColumnStretch(1, 0)
    versions_layout.setColumnStretch(2, 0)
    versions_layout.setColumnStretch(3, 0)
    versions_layout.setColumnStretch(4, 0)
    versions_layout.setColumnStretch(5, 1)
    versions_layout.setVerticalSpacing(8)
    versions_layout.setHorizontalSpacing(6)
    versions_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)

    versions_scroll = QtWidgets.QScrollArea()
    versions_scroll.setWidgetResizable(True)
    versions_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    versions_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    versions_scroll.setWidget(versions_container)
    versions_scroll.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    )

    self._dep_versions_container = versions_container
    self._dep_versions_layout = versions_layout
    self._dep_versions_scroll = versions_scroll
    self._dep_versions_group = versions_group
    self._rebuild_dependency_version_rows(self._dep_version_targets)

    versions_group_layout.addWidget(versions_scroll, 1)
    layout.addWidget(versions_group, 1)
    version_btn_row = QtWidgets.QHBoxLayout()
    version_btn_row.addStretch()
    self._version_refresh_btn = QtWidgets.QPushButton("Check Versions")
    self._version_refresh_btn.clicked.connect(self._refresh_dependency_versions)
    version_btn_row.addWidget(self._version_refresh_btn)
    layout.addLayout(version_btn_row)

    self._sync_language_exchange_lists_from_config()
    self._update_bot_status()
    self._refresh_code_tab_from_config()
    try:
        self._ensure_cpp_process_watchdog()
    except Exception:
        pass
    try:
        self._ensure_rust_process_watchdog()
    except Exception:
        pass
    return tab


def code_tab_select_language(self, config_key: str, *, launch_cpp_from_code_tab) -> None:
    if config_key not in LANGUAGE_PATHS:
        return
    card = getattr(self, "_starter_language_cards", {}).get(config_key)
    if card is not None and card.is_disabled():
        return
    if config_key == CPP_CODE_LANGUAGE_KEY:
        try:
            answer = QtWidgets.QMessageBox.question(
                self,
                "Switch to C++?",
                (
                    "This will close the current Python trading bot window completely "
                    "and open the C++ trading bot instead.\n\n"
                    "Do you want to continue?"
                ),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
        except Exception:
            return
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
    self.config["code_language"] = config_key
    if config_key == RUST_CODE_LANGUAGE_KEY:
        self.config["selected_rust_framework"] = ""
    if config_key == CPP_CODE_LANGUAGE_KEY and self.config.get("selected_exchange") != CPP_SUPPORTED_EXCHANGE_KEY:
        self.config["selected_exchange"] = CPP_SUPPORTED_EXCHANGE_KEY
        self.log("C++ preview supports Binance only. Switched exchange to Binance.")
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()
    if config_key == CPP_CODE_LANGUAGE_KEY:
        launch_cpp_from_code_tab(self, trigger="language-card")


def code_tab_select_rust_framework(self, framework_key: str, *, launch_rust_from_code_tab) -> None:
    if framework_key not in RUST_FRAMEWORK_PATHS:
        return
    card = getattr(self, "_starter_rust_framework_cards", {}).get(framework_key)
    if card is not None and card.is_disabled():
        return
    try:
        answer = QtWidgets.QMessageBox.question(
            self,
            f"Switch to Rust {framework_key}?",
            (
                "This will close the current Python trading bot window completely "
                f"and open the Rust {framework_key} trading bot instead.\n\n"
                "Do you want to continue?"
            ),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
    except Exception:
        return
    if answer != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    self.config["code_language"] = RUST_CODE_LANGUAGE_KEY
    self.config["selected_rust_framework"] = framework_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()
    launch_rust_from_code_tab(self, trigger="framework-card")


def code_tab_select_market(self, market_key: str) -> None:
    if market_key not in {"crypto", "forex"}:
        return
    card = getattr(self, "_starter_market_cards", {}).get(market_key)
    if card is not None and card.is_disabled():
        return
    self.config["code_market"] = market_key
    self._code_tab_selected_market = market_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def code_tab_select_exchange(self, exchange_key: str) -> None:
    if exchange_key not in EXCHANGE_PATHS:
        return
    card = getattr(self, "_starter_crypto_cards", {}).get(exchange_key)
    if card is not None and card.is_disabled():
        return
    self.config["selected_exchange"] = exchange_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def code_tab_select_forex(self, broker_key: str) -> None:
    if broker_key not in FOREX_BROKER_PATHS:
        return
    card = getattr(self, "_starter_forex_cards", {}).get(broker_key)
    if card is not None and card.is_disabled():
        return
    self.config["selected_forex_broker"] = broker_key
    self._code_tab_selected_market = "forex"
    self.config["code_market"] = "forex"
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def refresh_code_tab_from_config(
    self,
    *,
    resolve_dependency_targets_for_config,
    refresh_code_language_card_release_labels,
    refresh_dependency_usage_labels,
) -> None:
    lang_cards = getattr(self, "_starter_language_cards", {})
    lang_key = self.config.get("code_language")
    if not lang_key or lang_key not in lang_cards or lang_cards[lang_key].is_disabled():
        lang_key = next((key for key, card in lang_cards.items() if not card.is_disabled()), None)
        if lang_key:
            self.config["code_language"] = lang_key
    for key, card in lang_cards.items():
        card.setSelected(bool(lang_key) and key == lang_key)

    rust_framework_cards = getattr(self, "_starter_rust_framework_cards", {})
    rust_framework_key = str(self.config.get("selected_rust_framework") or "").strip()
    if rust_framework_key and rust_framework_key not in rust_framework_cards:
        rust_framework_key = ""
        self.config["selected_rust_framework"] = ""
    for key, card in rust_framework_cards.items():
        card.setSelected(
            bool(lang_key)
            and lang_key == RUST_CODE_LANGUAGE_KEY
            and bool(rust_framework_key)
            and key == rust_framework_key
        )

    self._update_code_tab_rust_sections()
    refresh_code_language_card_release_labels(self)
    targets_changed = False
    try:
        resolved_targets = resolve_dependency_targets_for_config(self.config)
    except Exception:
        resolved_targets = list(getattr(self, "_dep_version_targets", []) or [])
    if resolved_targets and resolved_targets != getattr(self, "_dep_version_targets", None):
        self._rebuild_dependency_version_rows(resolved_targets)
        targets_changed = True
    elif not resolved_targets:
        resolved_targets = list(getattr(self, "_dep_version_targets", []) or [])
    if targets_changed and self._code_tab_visible():
        QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
    refresh_dependency_usage_labels(self, resolved_targets)


def code_tab_visible(self) -> bool:
    try:
        tabs = getattr(self, "tabs", None)
        code_tab = getattr(self, "code_tab", None)
        if tabs is None or code_tab is None:
            return False
        return tabs.currentWidget() is code_tab
    except Exception:
        return False


def update_code_tab_market_sections(self) -> None:
    market = getattr(self, "_code_tab_selected_market", None)
    show_crypto = market == "crypto"
    show_forex = market == "forex"
    for widget in (getattr(self, "_crypto_section_label", None), getattr(self, "_crypto_cards_widget", None)):
        if widget is not None:
            widget.setVisible(show_crypto)
    for widget in (getattr(self, "_forex_section_label", None), getattr(self, "_forex_cards_widget", None)):
        if widget is not None:
            widget.setVisible(show_forex)


def update_code_tab_rust_sections(self) -> None:
    show_rust = str(self.config.get("code_language") or "").strip() == RUST_CODE_LANGUAGE_KEY
    for widget in (getattr(self, "_rust_framework_section_label", None), getattr(self, "_rust_framework_cards_widget", None)):
        if widget is not None:
            widget.setVisible(show_rust)


def sync_language_exchange_lists_from_config(self) -> None:
    selections = [
        ("code_language", self.language_combo, LANGUAGE_PATHS),
        ("selected_exchange", self.exchange_combo, EXCHANGE_PATHS),
        ("selected_forex_broker", self.forex_combo, FOREX_BROKER_PATHS),
    ]
    for key, widget, options_map in selections:
        if widget is None:
            continue
        desired = self.config.get(key)
        if not desired:
            try:
                blocker = QtCore.QSignalBlocker(widget)
            except Exception:
                blocker = None
            try:
                widget.setCurrentIndex(-1)
                if widget.isEditable():
                    widget.clearEditText()
            except Exception:
                pass
            if blocker is not None:
                del blocker
            continue
        if desired not in options_map and options_map:
            desired = next(iter(options_map))
            self.config[key] = desired
        with QtCore.QSignalBlocker(widget):
            idx = widget.findData(desired)
            if idx < 0:
                idx = widget.findText(desired, QtCore.Qt.MatchFlag.MatchExactly)
            if idx >= 0:
                try:
                    item = widget.model().item(idx)
                except Exception:
                    item = None
                if item is not None and not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
                    idx = -1
            if idx < 0 and widget.count() > 0:
                fallback_idx = -1
                fallback_value = None
                for i in range(widget.count()):
                    try:
                        item = widget.model().item(i)
                    except Exception:
                        item = None
                    if item is not None and not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
                        continue
                    data_value = widget.itemData(i)
                    text_value = widget.itemText(i)
                    if data_value in options_map:
                        fallback_idx = i
                        fallback_value = data_value
                        break
                    if text_value in options_map:
                        fallback_idx = i
                        fallback_value = text_value
                        break
                if fallback_idx >= 0:
                    idx = fallback_idx
                    desired = fallback_value
                    self.config[key] = desired
            if idx >= 0:
                widget.setCurrentIndex(idx)
    self._ensure_language_exchange_paths()
    self._refresh_code_tab_from_config()
    if self.exchange_list is not None:
        desired_exchange = self.config.get("selected_exchange")
        item = self._exchange_list_items.get(desired_exchange)
        if item is None or not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
            desired_exchange = None
            for opt in STARTER_CRYPTO_EXCHANGES:
                if opt.get("disabled", False):
                    continue
                desired_exchange = opt["key"]
                break
            if desired_exchange:
                self.config["selected_exchange"] = desired_exchange
                item = self._exchange_list_items.get(desired_exchange)
        if item is not None:
            with QtCore.QSignalBlocker(self.exchange_list):
                self.exchange_list.setCurrentItem(item)


def ensure_language_exchange_paths(self, *, base_project_path: Path) -> None:
    created_paths = []

    def _prepare_path(path: Path | None):
        if path is None:
            return
        try:
            is_new = not path.exists()
            path.mkdir(parents=True, exist_ok=True)
            if is_new:
                created_paths.append(path)
        except Exception as exc:
            try:
                self.log(f"Failed to prepare {path}: {exc}")
            except Exception:
                pass

    language_rel = LANGUAGE_PATHS.get(self.config.get("code_language"))
    language_root = (base_project_path / language_rel).resolve() if language_rel else None
    _prepare_path(language_root)

    if self.config.get("code_language") == RUST_CODE_LANGUAGE_KEY:
        for shared_rel in RUST_SHARED_PATHS:
            _prepare_path((base_project_path / shared_rel).resolve())
        rust_framework_rel = RUST_FRAMEWORK_PATHS.get(self.config.get("selected_rust_framework"))
        _prepare_path((base_project_path / rust_framework_rel).resolve() if rust_framework_rel else None)

    base_path = base_project_path if language_root is None else language_root
    exchange_rel = EXCHANGE_PATHS.get(self.config.get("selected_exchange"))
    forex_rel = FOREX_BROKER_PATHS.get(self.config.get("selected_forex_broker"))
    _prepare_path((base_path / exchange_rel).resolve() if exchange_rel else None)
    _prepare_path((base_path / forex_rel).resolve() if forex_rel else None)

    if created_paths:
        try:
            created_text = ", ".join(str(path) for path in created_paths)
            self.log(f"Ensured directories: {created_text}")
        except Exception:
            pass


def on_code_language_changed(self, text: str) -> None:
    if not text or text not in LANGUAGE_PATHS:
        return
    self.config["code_language"] = text
    self._ensure_language_exchange_paths()


def on_exchange_selection_changed(self, text: str) -> None:
    exchange_key = str(text).strip() if text is not None else ""
    if exchange_key not in EXCHANGE_PATHS:
        combo = getattr(self, "exchange_combo", None)
        if combo is not None:
            data_key = combo.currentData()
            if data_key in EXCHANGE_PATHS:
                exchange_key = data_key
            else:
                text_key = combo.currentText()
                if text_key in EXCHANGE_PATHS:
                    exchange_key = text_key
    if not exchange_key or exchange_key not in EXCHANGE_PATHS:
        return
    self.config["selected_exchange"] = exchange_key
    self._ensure_language_exchange_paths()


def on_exchange_list_changed(
    self,
    current: QtWidgets.QListWidgetItem | None,
    _previous: QtWidgets.QListWidgetItem | None = None,
) -> None:
    if current is None:
        return
    exchange_key = current.data(QtCore.Qt.ItemDataRole.UserRole) or current.text()
    if not exchange_key or exchange_key not in EXCHANGE_PATHS:
        return
    self.config["selected_exchange"] = exchange_key
    self._ensure_language_exchange_paths()


def on_forex_selection_changed(self, text: str) -> None:
    if not text or text not in FOREX_BROKER_PATHS:
        return
    self.config["selected_forex_broker"] = text
    self._ensure_language_exchange_paths()
