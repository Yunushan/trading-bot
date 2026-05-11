from __future__ import annotations

from collections.abc import Mapping

from .connectors import DEFAULT_CONNECTOR_BACKEND


SUPPORTED_EXCHANGES = ("Binance",)
SUPPORTED_CONNECTOR_BACKENDS = (
    DEFAULT_CONNECTOR_BACKEND,
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "python-binance",
    "ccxt",
)
SUPPORTED_FOREX_BROKERS: tuple[str, ...] = ()


def _support_key(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _first_non_empty(*values: object, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def build_exchange_support_payload(
    *,
    config: Mapping[str, object] | None = None,
    snapshot: Mapping[str, object] | None = None,
) -> dict[str, object]:
    cfg = dict(config) if isinstance(config, Mapping) else {}
    raw = dict(snapshot) if isinstance(snapshot, Mapping) else {}
    selected_exchange = _first_non_empty(
        raw.get("selected_exchange"),
        cfg.get("selected_exchange"),
        default="Unknown",
    )
    connector_backend = _first_non_empty(
        raw.get("connector_backend"),
        cfg.get("connector_backend"),
        default="Unknown",
    )
    selected_forex_broker = _first_non_empty(
        raw.get("selected_forex_broker"),
        cfg.get("selected_forex_broker"),
    )

    exchange_supported = _support_key(selected_exchange) in {_support_key(item) for item in SUPPORTED_EXCHANGES}
    backend_supported = _support_key(connector_backend) in {
        _support_key(item) for item in SUPPORTED_CONNECTOR_BACKENDS
    }
    broker_supported = not selected_forex_broker or _support_key(selected_forex_broker) in {
        _support_key(item) for item in SUPPORTED_FOREX_BROKERS
    }
    reasons: list[str] = []
    if not exchange_supported:
        reasons.append(f"Exchange '{selected_exchange}' is not implemented by this runtime.")
    if not backend_supported:
        reasons.append(f"Connector backend '{connector_backend}' is not implemented by this runtime.")
    if not broker_supported:
        reasons.append(f"Forex broker '{selected_forex_broker}' is not implemented by this runtime.")

    trading_supported = exchange_supported and backend_supported and broker_supported
    return {
        "selected_exchange": selected_exchange,
        "connector_backend": connector_backend,
        "selected_forex_broker": selected_forex_broker,
        "exchange_supported": exchange_supported,
        "connector_backend_supported": backend_supported,
        "broker_supported": broker_supported,
        "trading_supported": trading_supported,
        "unsupported_reasons": reasons,
        "supported_exchanges": list(SUPPORTED_EXCHANGES),
        "supported_connector_backends": list(SUPPORTED_CONNECTOR_BACKENDS),
        "supported_forex_brokers": list(SUPPORTED_FOREX_BROKERS),
    }


__all__ = [
    "SUPPORTED_CONNECTOR_BACKENDS",
    "SUPPORTED_EXCHANGES",
    "SUPPORTED_FOREX_BROKERS",
    "build_exchange_support_payload",
]
