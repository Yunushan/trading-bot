from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from .code_language_catalog import (
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_PATHS,
    RUST_SHARED_PATHS,
    STARTER_CRYPTO_EXCHANGES,
)
from .code_language_ui_build_runtime import code_tab_auto_refresh_versions_enabled, ensure_rust_framework_cards


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
    if lang_key == RUST_CODE_LANGUAGE_KEY:
        ensure_rust_framework_cards(self)
        rust_framework_cards = getattr(self, "_starter_rust_framework_cards", {})
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
    if targets_changed:
        try:
            self._dep_version_auto_refresh_done = False
        except Exception:
            pass
    if targets_changed and self._code_tab_visible() and code_tab_auto_refresh_versions_enabled():
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


__all__ = [
    "code_tab_visible",
    "ensure_language_exchange_paths",
    "on_code_language_changed",
    "on_exchange_list_changed",
    "on_exchange_selection_changed",
    "on_forex_selection_changed",
    "refresh_code_tab_from_config",
    "sync_language_exchange_lists_from_config",
    "update_code_tab_market_sections",
    "update_code_tab_rust_sections",
]
