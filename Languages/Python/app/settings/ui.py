from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CODE_LANGUAGE = "Python (PyQt)"
DEFAULT_SELECTED_EXCHANGE = "Binance"


@dataclass(frozen=True, slots=True)
class UserInterfaceSettings:
    code_language: str = DEFAULT_CODE_LANGUAGE
    selected_rust_framework: str = ""
    selected_exchange: str = DEFAULT_SELECTED_EXCHANGE
    selected_forex_broker: str | None = None

    def to_config_dict(self) -> dict[str, object]:
        return {
            "code_language": self.code_language,
            "selected_rust_framework": self.selected_rust_framework,
            "selected_exchange": self.selected_exchange,
            "selected_forex_broker": self.selected_forex_broker,
        }
