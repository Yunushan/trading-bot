from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .code_language_catalog import (
    CPP_CODE_LANGUAGE_KEY,
    CPP_SUPPORTED_EXCHANGE_KEY,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_PATHS,
)


def _queue_code_tab_selection(self, callback) -> None:
    if getattr(self, "_code_tab_selection_pending", False):
        return
    self._code_tab_selection_pending = True

    def _run() -> None:
        self._code_tab_selection_pending = False
        if getattr(self, "_code_tab_selection_dialog_open", False):
            return
        try:
            callback()
        except Exception:
            pass

    QtCore.QTimer.singleShot(0, _run)

def _clear_code_tab_confirmation(self) -> None:
    overlay = getattr(self, "_code_tab_confirmation_overlay", None)
    title_label = getattr(self, "_code_tab_confirmation_title_label", None)
    body_label = getattr(self, "_code_tab_confirmation_body_label", None)
    try:
        if title_label is not None:
            title_label.setText("")
    except Exception:
        pass
    try:
        if body_label is not None:
            body_label.setText("")
    except Exception:
        pass
    try:
        if overlay is not None:
            overlay.hide()
    except Exception:
        pass


def _finish_code_tab_confirmation(self, accepted: bool) -> None:
    on_accept = getattr(self, "_code_tab_confirmation_on_accept", None)
    on_reject = getattr(self, "_code_tab_confirmation_on_reject", None)
    self._code_tab_confirmation_on_accept = None
    self._code_tab_confirmation_on_reject = None
    self._code_tab_selection_dialog_open = False
    _clear_code_tab_confirmation(self)
    callback = on_accept if accepted else on_reject
    if callable(callback):
        QtCore.QTimer.singleShot(0, callback)


def _show_code_tab_confirmation(
    self,
    title: str,
    text: str,
    *,
    on_accept=None,
    on_reject=None,
) -> bool:
    overlay = getattr(self, "_code_tab_confirmation_overlay", None)
    panel = getattr(self, "_code_tab_confirmation_panel", None)
    title_label = getattr(self, "_code_tab_confirmation_title_label", None)
    body_label = getattr(self, "_code_tab_confirmation_body_label", None)
    no_btn = getattr(self, "_code_tab_confirmation_no_btn", None)
    yes_btn = getattr(self, "_code_tab_confirmation_yes_btn", None)
    if overlay is None or panel is None or title_label is None or body_label is None:
        return False

    _clear_code_tab_confirmation(self)
    self._code_tab_selection_dialog_open = True
    self._code_tab_confirmation_on_accept = on_accept
    self._code_tab_confirmation_on_reject = on_reject
    title_label.setText(str(title or "").strip())
    body_label.setText(str(text or "").strip())
    try:
        parent_widget = overlay.parentWidget()
    except Exception:
        parent_widget = None
    if parent_widget is not None:
        try:
            overlay.setGeometry(parent_widget.rect())
        except Exception:
            pass
    overlay.show()
    try:
        overlay.raise_()
    except Exception:
        pass
    try:
        panel.raise_()
    except Exception:
        pass
    try:
        self.raise_()
        self.activateWindow()
    except Exception:
        pass
    try:
        overlay.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
    except Exception:
        pass
    try:
        no_btn.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
    except Exception:
        pass
    return True


def _apply_code_tab_select_language(self, config_key: str, *, launch_cpp_from_code_tab) -> None:
    if config_key not in LANGUAGE_PATHS:
        return
    card = getattr(self, "_starter_language_cards", {}).get(config_key)
    if card is not None and card.is_disabled():
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


def _perform_code_tab_select_language(self, config_key: str, *, launch_cpp_from_code_tab) -> None:
    if config_key not in LANGUAGE_PATHS:
        return
    card = getattr(self, "_starter_language_cards", {}).get(config_key)
    if card is not None and card.is_disabled():
        return
    if config_key == CPP_CODE_LANGUAGE_KEY:
        shown = _show_code_tab_confirmation(
            self,
            "Switch to C++?",
            (
                "This will close the current Python trading bot window completely "
                "and open the C++ trading bot instead.\n\n"
                "Do you want to continue?"
            ),
            on_accept=lambda: _apply_code_tab_select_language(
                self,
                config_key,
                launch_cpp_from_code_tab=launch_cpp_from_code_tab,
            ),
        )
        if shown:
            return
    _apply_code_tab_select_language(
        self,
        config_key,
        launch_cpp_from_code_tab=launch_cpp_from_code_tab,
    )


def code_tab_select_language(self, config_key: str, *, launch_cpp_from_code_tab) -> None:
    if config_key not in LANGUAGE_PATHS:
        return
    if getattr(self, "_code_tab_selection_dialog_open", False):
        return
    _queue_code_tab_selection(
        self,
        lambda: _perform_code_tab_select_language(
            self,
            config_key,
            launch_cpp_from_code_tab=launch_cpp_from_code_tab,
        ),
    )


def _apply_code_tab_select_rust_framework(self, framework_key: str, *, launch_rust_from_code_tab) -> None:
    if framework_key not in RUST_FRAMEWORK_PATHS:
        return
    card = getattr(self, "_starter_rust_framework_cards", {}).get(framework_key)
    if card is not None and card.is_disabled():
        return
    self.config["code_language"] = RUST_CODE_LANGUAGE_KEY
    self.config["selected_rust_framework"] = framework_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()
    launch_rust_from_code_tab(self, trigger="framework-card")


def _perform_code_tab_select_rust_framework(self, framework_key: str, *, launch_rust_from_code_tab) -> None:
    if framework_key not in RUST_FRAMEWORK_PATHS:
        return
    card = getattr(self, "_starter_rust_framework_cards", {}).get(framework_key)
    if card is not None and card.is_disabled():
        return
    shown = _show_code_tab_confirmation(
        self,
        f"Switch to Rust {framework_key}?",
        (
            "This will close the current Python trading bot window completely "
            f"and open the Rust {framework_key} trading bot instead.\n\n"
            "Do you want to continue?"
        ),
        on_accept=lambda: _apply_code_tab_select_rust_framework(
            self,
            framework_key,
            launch_rust_from_code_tab=launch_rust_from_code_tab,
        ),
    )
    if shown:
        return
    _apply_code_tab_select_rust_framework(
        self,
        framework_key,
        launch_rust_from_code_tab=launch_rust_from_code_tab,
    )


def code_tab_select_rust_framework(self, framework_key: str, *, launch_rust_from_code_tab) -> None:
    if framework_key not in RUST_FRAMEWORK_PATHS:
        return
    if getattr(self, "_code_tab_selection_dialog_open", False):
        return
    _queue_code_tab_selection(
        self,
        lambda: _perform_code_tab_select_rust_framework(
            self,
            framework_key,
            launch_rust_from_code_tab=launch_rust_from_code_tab,
        ),
    )


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


__all__ = [
    "code_tab_select_exchange",
    "code_tab_select_forex",
    "code_tab_select_language",
    "code_tab_select_market",
    "code_tab_select_rust_framework",
]
