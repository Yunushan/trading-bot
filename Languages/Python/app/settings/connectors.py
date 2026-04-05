from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CONNECTOR_BACKEND = "binance-sdk-derivatives-trading-usds-futures"
DEFAULT_INDICATOR_SOURCE = "Binance futures"


@dataclass(frozen=True, slots=True)
class ConnectorSettings:
    connector_backend: str = DEFAULT_CONNECTOR_BACKEND
    indicator_source: str = DEFAULT_INDICATOR_SOURCE

    def to_config_dict(self) -> dict[str, str]:
        return {
            "connector_backend": self.connector_backend,
            "indicator_source": self.indicator_source,
        }
