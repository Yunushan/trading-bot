from __future__ import annotations

from collections.abc import Mapping

from .connectors import DEFAULT_CONNECTOR_BACKEND


CCXT_DIAGNOSTIC_EXCHANGES = (
    "Bybit",
    "OKX",
    "Bitget",
    "Gate",
    "MEXC",
    "KuCoin",
    "HTX",
    "Crypto.com Exchange",
    "Kraken",
    "Bitfinex",
)
CCXT_ORDER_ROUTING_EXCHANGES = CCXT_DIAGNOSTIC_EXCHANGES
SUPPORTED_EXCHANGES = ("Binance", *CCXT_DIAGNOSTIC_EXCHANGES)
SUPPORTED_CONNECTOR_BACKENDS = (
    DEFAULT_CONNECTOR_BACKEND,
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
    "binance-connector",
    "python-binance",
    "ccxt",
    "oanda-rest",
    "fxcmpy",
    "ig-rest",
)
SUPPORTED_FOREX_BROKERS: tuple[str, ...] = ("OANDA", "FXCM", "IG")
BROKER_ORDER_ROUTING_BACKENDS = {
    "oanda": "oanda-rest",
    "fxcm": "fxcmpy",
    "ig": "ig-rest",
}
BROKER_ORDER_ROUTING_BROKERS = SUPPORTED_FOREX_BROKERS
CCXT_EXCHANGE_IDS = {
    "bybit": "bybit",
    "okx": "okx",
    "bitget": "bitget",
    "gate": "gateio",
    "gate.io": "gateio",
    "gateio": "gateio",
    "mexc": "mexc",
    "kucoin": "kucoin",
    "htx": "htx",
    "crypto.com": "cryptocom",
    "crypto.com exchange": "cryptocom",
    "cryptocom": "cryptocom",
    "kraken": "kraken",
    "bitfinex": "bitfinex",
}
ORDER_EXECUTION_EXCHANGES = ("Binance",)


def _support_key(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _first_non_empty(*values: object, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def ccxt_exchange_id_for(exchange: object) -> str:
    return CCXT_EXCHANGE_IDS.get(_support_key(exchange), "")


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

    exchange_key = _support_key(selected_exchange)
    backend_key = _support_key(connector_backend)
    ccxt_exchange_id = ccxt_exchange_id_for(selected_exchange)
    exchange_supported = exchange_key in {_support_key(item) for item in SUPPORTED_EXCHANGES}
    backend_supported = _support_key(connector_backend) in {
        _support_key(item) for item in SUPPORTED_CONNECTOR_BACKENDS
    }
    broker_supported = not selected_forex_broker or _support_key(selected_forex_broker) in {
        _support_key(item) for item in SUPPORTED_FOREX_BROKERS
    }
    uses_broker = bool(selected_forex_broker)
    uses_ccxt_diagnostics = bool(ccxt_exchange_id and backend_key == "ccxt")
    uses_ccxt_order_routing = uses_ccxt_diagnostics and exchange_key in {
        _support_key(item) for item in CCXT_ORDER_ROUTING_EXCHANGES
    }
    expected_broker_backend = BROKER_ORDER_ROUTING_BACKENDS.get(_support_key(selected_forex_broker), "")
    uses_broker_order_routing = bool(expected_broker_backend and backend_key == expected_broker_backend)
    is_order_execution_exchange = exchange_key in {_support_key(item) for item in ORDER_EXECUTION_EXCHANGES}
    market_data_supported = backend_supported and (
        (not uses_broker and broker_supported and (is_order_execution_exchange or uses_ccxt_diagnostics))
        or (uses_broker and uses_broker_order_routing)
    )
    account_snapshot_supported = market_data_supported
    order_routing_supported = backend_supported and (
        (not uses_broker and broker_supported and (is_order_execution_exchange or uses_ccxt_order_routing))
        or (uses_broker and uses_broker_order_routing)
    )
    order_execution_supported = (
        (not uses_broker and exchange_supported and broker_supported and order_routing_supported)
        or (uses_broker and broker_supported and order_routing_supported)
    )
    live_evidence_required = order_execution_supported and (uses_broker or not is_order_execution_exchange)

    reasons: list[str] = []
    capability_gaps: list[str] = []
    if not uses_broker and not exchange_supported:
        reasons.append(f"Exchange '{selected_exchange}' is not implemented by this runtime.")
    if not backend_supported:
        reasons.append(f"Connector backend '{connector_backend}' is not implemented by this runtime.")
    if not broker_supported:
        reasons.append(f"Forex broker '{selected_forex_broker}' is not implemented by this runtime.")
    if uses_broker and broker_supported and backend_supported and not uses_broker_order_routing:
        if expected_broker_backend:
            capability_gaps.append(
                f"Broker '{selected_forex_broker}' order routing requires connector backend "
                f"'{expected_broker_backend}'."
            )
        else:
            capability_gaps.append(
                f"Broker '{selected_forex_broker}' order routing requires a provider connector."
            )
    if (not uses_broker and exchange_supported and backend_supported and broker_supported and not order_execution_supported):
        capability_gaps.append(
            f"Order routing for exchange '{selected_exchange}' requires a provider connector backend."
        )
    if live_evidence_required:
        if uses_broker:
            capability_gaps.append(
                f"Official live support for broker '{selected_forex_broker}' requires a passed connector evidence artifact."
            )
        else:
            capability_gaps.append(
                f"Official live support for exchange '{selected_exchange}' requires a passed connector evidence artifact."
            )

    trading_supported = order_execution_supported
    support_tier = "unsupported"
    if order_execution_supported:
        support_tier = "full-trading" if not live_evidence_required else "order-routing-evidence-required"
    elif market_data_supported or account_snapshot_supported:
        support_tier = "diagnostics-only"

    return {
        "selected_exchange": selected_exchange,
        "connector_backend": connector_backend,
        "selected_forex_broker": selected_forex_broker,
        "ccxt_exchange_id": ccxt_exchange_id,
        "exchange_supported": exchange_supported,
        "connector_backend_supported": backend_supported,
        "broker_supported": broker_supported,
        "market_data_supported": market_data_supported,
        "account_snapshot_supported": account_snapshot_supported,
        "order_routing_supported": order_routing_supported,
        "order_execution_supported": order_execution_supported,
        "live_evidence_required": live_evidence_required,
        "trading_supported": trading_supported,
        "support_tier": support_tier,
        "capability_gaps": capability_gaps,
        "unsupported_reasons": reasons,
        "supported_exchanges": list(SUPPORTED_EXCHANGES),
        "supported_connector_backends": list(SUPPORTED_CONNECTOR_BACKENDS),
        "supported_forex_brokers": list(SUPPORTED_FOREX_BROKERS),
        "ccxt_diagnostic_exchanges": list(CCXT_DIAGNOSTIC_EXCHANGES),
        "ccxt_order_routing_exchanges": list(CCXT_ORDER_ROUTING_EXCHANGES),
        "order_execution_exchanges": list(ORDER_EXECUTION_EXCHANGES),
        "broker_order_routing_brokers": list(BROKER_ORDER_ROUTING_BROKERS),
        "broker_order_routing_backends": dict(BROKER_ORDER_ROUTING_BACKENDS),
    }


__all__ = [
    "CCXT_DIAGNOSTIC_EXCHANGES",
    "CCXT_EXCHANGE_IDS",
    "CCXT_ORDER_ROUTING_EXCHANGES",
    "BROKER_ORDER_ROUTING_BACKENDS",
    "BROKER_ORDER_ROUTING_BROKERS",
    "ORDER_EXECUTION_EXCHANGES",
    "SUPPORTED_CONNECTOR_BACKENDS",
    "SUPPORTED_EXCHANGES",
    "SUPPORTED_FOREX_BROKERS",
    "build_exchange_support_payload",
    "ccxt_exchange_id_for",
]
