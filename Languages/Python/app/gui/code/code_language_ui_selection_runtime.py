from __future__ import annotations

from PyQt6 import QtWidgets

from .code_language_catalog import (
    CPP_CODE_LANGUAGE_KEY,
    CPP_SUPPORTED_EXCHANGE_KEY,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_PATHS,
)


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


__all__ = [
    "code_tab_select_exchange",
    "code_tab_select_forex",
    "code_tab_select_language",
    "code_tab_select_market",
    "code_tab_select_rust_framework",
]
