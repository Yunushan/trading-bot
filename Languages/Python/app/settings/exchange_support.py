from __future__ import annotations

from collections.abc import Mapping

from .connectors import DEFAULT_CONNECTOR_BACKEND


def _broker_identity_key(value: object) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


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
DIRECT_FOREX_BROKER_OFFICIAL_SOURCES = {
    "OANDA": "https://developer.oanda.com/rest-live-v20/introduction/",
    "FXCM": "https://www.fxcm.com/markets/algorithmic-trading/compare-api/",
    "IG": "https://labs.ig.com/rest-trading-api-reference.html",
}
METATRADER5_BROKER_OFFICIAL_SOURCES = {
    "AvaTrade": "https://www.avatrade.com/trading-platforms/metatrader-5",
    "EC Markets": "https://www.ecmarkets.com/metatrader-5/",
    "GTCFX": "https://www.gtcfx.com/trading/mt5-platform",
    "Finalto": "https://www.finalto.com/wp-content/uploads/2025/04/Finalto_Brochure_2025.pdf",
    "ATFX": "https://www.atfx.com/en-ae/trading-platforms/metatrader-5",
    "Vantage": "https://www.vantagemarkets.com/academy/metatrader-5/",
    "STARTRADER": "https://www.startrader.com/mt5/",
    "XM": "https://www.xm.com/mt5",
    "TMGM": "https://www.tmgm.com/en-in/platform/metatrader-5",
    "Capital.com": "https://capital.com/en-int/trading-platforms/mt5",
    "IC Markets Global": "https://www.icmarkets.com/global/en/forex-trading-platform-metatrader/metatrader-5",
    "Hantec Financial": "https://www.hantecfinancial.com/en/",
    "GO Markets": "https://www.gomarkets.com/en-au/platforms/metatrader-5",
    "VT Markets": "https://www.vtmarkets.com/en-eu/faq/a-complete-faq-on-vt-markets-metatrader-4-and-metatrader-5/",
    "Neex": "https://neex.com/my/platforms/meta-trader5",
    "ACY Securities": "https://acy.com/en/",
    "Fortune Prime Global": "https://id.fortuneprime.com/platform/metatrader-5/",
    "DecodeFX": "https://decodefx.com/platforms/metatrader-5/",
    "CPT Markets": "https://www.cptmarkets.com/en/platform/metatrader5",
    "PU Prime": "https://www.puprime.com/mt5/",
    "AIMS": "https://aimsfx.com/metatrader5/",
    "ETO Markets": "https://blog.etomarkets.com/company-news/eto-markets-unveils-powerful-mt5-platform-for-enhanced-forex-trading",
    "D Prime": "https://www.dooprime.com/metatrader-5",
    "Fusion Markets": "https://fusionmarkets.com/Platforms/Metatrader-5",
    "Exness": "https://www.exness.com/metatrader-5/",
    "Valetax": "https://valetax.com/trading-platforms/",
    "CXM": "https://www.cxm.com/en/platforms/metatrader-5/",
    "DBG Markets": "https://www.dbgmarket.org/en/platforms",
    "FXT": "https://fxtrading.com/en/",
    "Plotio": "https://www.plotioglobal.com/mt5-for-mobile",
    "FOREX.com": "https://www.forex.com/en-us/trading-platforms/metatrader-5/",
    "CMC Markets": "https://www.cmcmarkets.com/en/trading-platforms",
    "StoneX": "https://futures.stonex.com/",
    "SBCFX": "https://www.sbcfx.com/zh/service/metatrader",
    "PhillipCapital (Phillip Nova)": "https://www.phillip.com.sg/sg/forex/",
    "AI Gold Securities": "https://www.aigold.co.jp/mtcx/gaiyou/",
}
METATRADER5_NON_FOREX_BROKER_MARKET_SCOPES = {
    "StoneX": "futures-and-options-on-futures",
    "AI Gold Securities": "otc-commodity-derivatives",
}
METATRADER5_BROKER_ALIASES = {
    "AI Gold": "AI Gold Securities",
    "Phillip Securities": "PhillipCapital (Phillip Nova)",
    "Philip Securities": "PhillipCapital (Phillip Nova)",
}
METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES = {
    "Trade Nation": "https://tradenation.com/metatrader-4/",
    "FXTF": "https://www.fxtrade.co.jp/lp/lp39/cg_D025LL_P011YL_1912mt4.html",
    "FOREX EXCHANGE": "https://www.forex-exchange.co.jp/",
}
METATRADER4_BRIDGE_BROKERS: tuple[str, ...] = tuple(METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES)
METATRADER5_BROKERS: tuple[str, ...] = tuple(METATRADER5_BROKER_OFFICIAL_SOURCES)
METATRADER5_FOREX_BROKERS: tuple[str, ...] = tuple(
    broker for broker in METATRADER5_BROKERS if broker not in METATRADER5_NON_FOREX_BROKER_MARKET_SCOPES
)
CITIC_FUTURES_BROKER_OFFICIAL_SOURCE = "https://www.citicsf.com/e-futures/csc/app/external_access"
TRADING212_BROKER_OFFICIAL_SOURCE = "https://docs.trading212.com/api"
MOOMOO_BROKER_OFFICIAL_SOURCE = "https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html"
BROKER_INTEGRATION_DISPOSITIONS: dict[str, dict[str, str]] = {
    "Mitrade": {
        "status": "blocked-proprietary-platform-no-public-api",
        "integration_path": "proprietary-web-desktop-mobile-platform",
        "market_scope": "forex-and-cfds",
        "official_source": "https://www.mitrade.com/en/trading-platforms",
        "required_next_step": "Mitrade must publish or authorize an order API contract.",
    },
    "AXPM": {
        "status": "blocked-proprietary-platform-no-public-api",
        "integration_path": "proprietary-web-desktop-mobile-platform",
        "market_scope": "forex-and-cfds",
        "official_source": "https://www.axpmtech.com/",
        "required_next_step": "AXPM must publish or authorize an order API contract.",
    },
    "Spreadex": {
        "status": "blocked-proprietary-platform-no-public-api",
        "integration_path": "proprietary-web-and-mobile-platform",
        "market_scope": "forex-spread-bets-and-cfds",
        "official_source": "https://www.spreadex.com/financials/education-hub/our-platforms/",
        "required_next_step": "Spreadex must publish or authorize an order API contract.",
    },
    "Jefferies": {
        "status": "blocked-private-client-contract-required",
        "integration_path": "client-onboarded-fix",
        "market_scope": "institutional-electronic-trading",
        "official_source": "https://www.jefferies.com/CMSFiles/Jefferies.com/files/Policies/JEG_Terms_of_Business.pdf",
        "required_next_step": "An onboarded Jefferies client must provide the authorized FIX contract and test session.",
    },
    "Marex": {
        "status": "blocked-private-client-contract-required",
        "integration_path": "client-onboarded-api-or-fix",
        "market_scope": "institutional-cross-asset-markets",
        "official_source": "https://www.marex.com/technology",
        "required_next_step": "An onboarded Marex client must provide the authorized API or FIX contract and test session.",
    },
}
REQUESTED_BROKER_TARGETS: dict[str, str] = {
    "avatrade": "AvaTrade",
    "fxcm": "FXCM",
    "ec markets": "EC Markets",
    "gtcfx": "GTCFX",
    "finalto": "Finalto",
    "atfx": "ATFX",
    "vantage": "Vantage",
    "startrader": "STARTRADER",
    "xm": "XM",
    "tmgm": "TMGM",
    "capital.com": "Capital.com",
    "ic markets global": "IC Markets Global",
    "trade nation": "Trade Nation",
    "hantec financial": "Hantec Financial",
    "go markets": "GO Markets",
    "trading 212": "Trading 212",
    "dbg markets": "DBG Markets",
    "sbcfx": "SBCFX",
    "vt markets": "VT Markets",
    "fxt": "FXT",
    "neex": "Neex",
    "acy securities": "ACY Securities",
    "mitrade": "Mitrade",
    "fortune prime global": "Fortune Prime Global",
    "decodefx": "DecodeFX",
    "cpt markets": "CPT Markets",
    "pu prime": "PU Prime",
    "aims": "AIMS",
    "eto markets": "ETO Markets",
    "d prime": "D Prime",
    "axpm": "AXPM",
    "jefferies": "Jefferies",
    "fxtf": "FXTF",
    "philipsecurities": "PhillipCapital (Phillip Nova)",
    "marex": "Marex",
    "fusion markets": "Fusion Markets",
    "exness": "Exness",
    "citic futures": "CITIC Futures",
    "forex exchange": "FOREX EXCHANGE",
    "IG": "IG",
    "moomoo": "moomoo",
    "plotio": "Plotio",
    "ai gold": "AI Gold Securities",
    "forex.com": "FOREX.com",
    "valetax": "Valetax",
    "cmc markes": "CMC Markets",
    "spreadex": "Spreadex",
    "cxm": "CXM",
    "stonex": "StoneX",
}
BROKER_OFFICIAL_SOURCES = {
    **DIRECT_FOREX_BROKER_OFFICIAL_SOURCES,
    **METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES,
    **METATRADER5_BROKER_OFFICIAL_SOURCES,
    "CITIC Futures": CITIC_FUTURES_BROKER_OFFICIAL_SOURCE,
    "Trading 212": TRADING212_BROKER_OFFICIAL_SOURCE,
    "moomoo": MOOMOO_BROKER_OFFICIAL_SOURCE,
}
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
    "citic-ctp",
    "metatrader4-bridge",
    "metatrader5",
    "trading212-public-api",
    "moomoo-opend",
)
SUPPORTED_FOREX_BROKERS: tuple[str, ...] = (
    "OANDA",
    "FXCM",
    "IG",
    *METATRADER4_BRIDGE_BROKERS,
    *METATRADER5_FOREX_BROKERS,
)
SUPPORTED_BROKERS: tuple[str, ...] = (
    "OANDA",
    "FXCM",
    "IG",
    *METATRADER4_BRIDGE_BROKERS,
    *METATRADER5_BROKERS,
    "CITIC Futures",
    "Trading 212",
    "moomoo",
)
_BROKER_CANONICAL_NAMES_BY_IDENTITY = {
    **{_broker_identity_key(broker): broker for broker in SUPPORTED_BROKERS},
    **{_broker_identity_key(broker): broker for broker in BROKER_INTEGRATION_DISPOSITIONS},
    **{_broker_identity_key(alias): canonical for alias, canonical in METATRADER5_BROKER_ALIASES.items()},
    **{_broker_identity_key(requested): canonical for requested, canonical in REQUESTED_BROKER_TARGETS.items()},
}
BROKER_ORDER_ROUTING_BACKENDS = {
    "oanda": "oanda-rest",
    "fxcm": "fxcmpy",
    "ig": "ig-rest",
    **{broker.lower().replace("_", "-"): "metatrader4-bridge" for broker in METATRADER4_BRIDGE_BROKERS},
    **{broker.lower().replace("_", "-"): "metatrader5" for broker in METATRADER5_BROKERS},
    "citic futures": "citic-ctp",
    "trading 212": "trading212-public-api",
    "moomoo": "moomoo-opend",
}
BROKER_ORDER_ROUTING_BROKERS = SUPPORTED_BROKERS
BROKER_MARKET_SCOPES = {
    **{
        broker.lower().replace("_", "-"): "forex-and-provider-configured-cfd-markets"
        for broker in SUPPORTED_FOREX_BROKERS
    },
    **{broker.lower().replace("_", "-"): scope for broker, scope in METATRADER5_NON_FOREX_BROKER_MARKET_SCOPES.items()},
    "citic futures": "china-futures-and-options",
    "trading 212": "invest-and-stocks-isa-equities-only",
    "moomoo": "stocks-etfs-options-futures-funds-and-supported-crypto",
}
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


def canonical_broker_name(value: object) -> str:
    text = str(value or "").strip()
    return _BROKER_CANONICAL_NAMES_BY_IDENTITY.get(_broker_identity_key(text), text)


def _first_non_empty(*values: object, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def ccxt_exchange_id_for(exchange: object) -> str:
    return CCXT_EXCHANGE_IDS.get(_support_key(exchange), "")


def broker_integration_coverage(value: object) -> dict[str, object]:
    """Describe an implemented route or the exact external prerequisite blocking it."""

    requested_name = str(value or "").strip()
    canonical_name = canonical_broker_name(requested_name)
    if canonical_name in SUPPORTED_BROKERS:
        forex_supported = canonical_name in SUPPORTED_FOREX_BROKERS
        return {
            "requested_name": requested_name,
            "canonical_name": canonical_name,
            "implemented": True,
            "forex_order_routing_supported": forex_supported,
            "backend": BROKER_ORDER_ROUTING_BACKENDS.get(_support_key(canonical_name), ""),
            "market_scope": BROKER_MARKET_SCOPES.get(_support_key(canonical_name), ""),
            "status": (
                "forex-order-routing-implemented-evidence-required"
                if forex_supported
                else "non-forex-order-routing-implemented-evidence-required"
            ),
            "official_source": BROKER_OFFICIAL_SOURCES.get(canonical_name, ""),
            "live_evidence_required": True,
            "blocking_requirement": "official-live-evidence",
        }

    disposition = BROKER_INTEGRATION_DISPOSITIONS.get(canonical_name)
    if disposition is not None:
        return {
            "requested_name": requested_name,
            "canonical_name": canonical_name,
            "implemented": False,
            "forex_order_routing_supported": False,
            "backend": "",
            "market_scope": disposition["market_scope"],
            "status": disposition["status"],
            "official_source": disposition["official_source"],
            "live_evidence_required": False,
            "blocking_requirement": disposition["required_next_step"],
        }

    return {
        "requested_name": requested_name,
        "canonical_name": canonical_name,
        "implemented": False,
        "forex_order_routing_supported": False,
        "backend": "",
        "market_scope": "",
        "status": "unknown-broker-request",
        "official_source": "",
        "live_evidence_required": False,
        "blocking_requirement": "An official order API or supported terminal route must be identified.",
    }


def build_requested_broker_coverage() -> list[dict[str, object]]:
    return [broker_integration_coverage(requested_name) for requested_name in REQUESTED_BROKER_TARGETS]


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
    selected_forex_broker = canonical_broker_name(
        _first_non_empty(
            raw.get("selected_forex_broker"),
            cfg.get("selected_forex_broker"),
        )
    )

    exchange_key = _support_key(selected_exchange)
    backend_key = _support_key(connector_backend)
    ccxt_exchange_id = ccxt_exchange_id_for(selected_exchange)
    exchange_supported = exchange_key in {_support_key(item) for item in SUPPORTED_EXCHANGES}
    backend_supported = _support_key(connector_backend) in {_support_key(item) for item in SUPPORTED_CONNECTOR_BACKENDS}
    broker_supported = not selected_forex_broker or _support_key(selected_forex_broker) in {
        _support_key(item) for item in SUPPORTED_BROKERS
    }
    uses_broker = bool(selected_forex_broker)
    uses_ccxt_diagnostics = bool(ccxt_exchange_id and backend_key == "ccxt")
    uses_ccxt_order_routing = uses_ccxt_diagnostics and exchange_key in {
        _support_key(item) for item in CCXT_ORDER_ROUTING_EXCHANGES
    }
    expected_broker_backend = BROKER_ORDER_ROUTING_BACKENDS.get(_support_key(selected_forex_broker), "")
    uses_broker_order_routing = bool(expected_broker_backend and backend_key == expected_broker_backend)
    broker_market_scope = BROKER_MARKET_SCOPES.get(_support_key(selected_forex_broker), "")
    forex_order_routing_supported = uses_broker_order_routing and _support_key(selected_forex_broker) in {
        _support_key(item) for item in SUPPORTED_FOREX_BROKERS
    }
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
        not uses_broker and exchange_supported and broker_supported and order_routing_supported
    ) or (uses_broker and broker_supported and order_routing_supported)
    live_evidence_required = order_execution_supported and (uses_broker or not is_order_execution_exchange)

    reasons: list[str] = []
    capability_gaps: list[str] = []
    if not uses_broker and not exchange_supported:
        reasons.append(f"Exchange '{selected_exchange}' is not implemented by this runtime.")
    if not backend_supported:
        reasons.append(f"Connector backend '{connector_backend}' is not implemented by this runtime.")
    if not broker_supported:
        reasons.append(f"Broker '{selected_forex_broker}' is not implemented by this runtime.")
    if uses_broker and broker_supported and backend_supported and not uses_broker_order_routing:
        if expected_broker_backend:
            capability_gaps.append(
                f"Broker '{selected_forex_broker}' order routing requires connector backend "
                f"'{expected_broker_backend}'."
            )
        else:
            capability_gaps.append(f"Broker '{selected_forex_broker}' order routing requires a provider connector.")
    if (
        not uses_broker
        and exchange_supported
        and backend_supported
        and broker_supported
        and not order_execution_supported
    ):
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
    if uses_broker_order_routing and not forex_order_routing_supported:
        capability_gaps.append(
            f"Broker '{selected_forex_broker}' connector is scoped to {broker_market_scope}; "
            "forex/CFD order routing is not exposed or claimed by this connector."
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
        "broker_market_scope": broker_market_scope,
        "forex_order_routing_supported": forex_order_routing_supported,
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
        "supported_brokers": list(SUPPORTED_BROKERS),
        "supported_forex_brokers": list(SUPPORTED_FOREX_BROKERS),
        "ccxt_diagnostic_exchanges": list(CCXT_DIAGNOSTIC_EXCHANGES),
        "ccxt_order_routing_exchanges": list(CCXT_ORDER_ROUTING_EXCHANGES),
        "order_execution_exchanges": list(ORDER_EXECUTION_EXCHANGES),
        "broker_order_routing_brokers": list(BROKER_ORDER_ROUTING_BROKERS),
        "broker_order_routing_backends": dict(BROKER_ORDER_ROUTING_BACKENDS),
    }


__all__ = [
    "BROKER_INTEGRATION_DISPOSITIONS",
    "BROKER_OFFICIAL_SOURCES",
    "CCXT_DIAGNOSTIC_EXCHANGES",
    "CCXT_EXCHANGE_IDS",
    "CCXT_ORDER_ROUTING_EXCHANGES",
    "CITIC_FUTURES_BROKER_OFFICIAL_SOURCE",
    "DIRECT_FOREX_BROKER_OFFICIAL_SOURCES",
    "BROKER_ORDER_ROUTING_BACKENDS",
    "BROKER_ORDER_ROUTING_BROKERS",
    "BROKER_MARKET_SCOPES",
    "ORDER_EXECUTION_EXCHANGES",
    "METATRADER4_BRIDGE_BROKERS",
    "METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES",
    "METATRADER5_BROKERS",
    "METATRADER5_BROKER_ALIASES",
    "METATRADER5_BROKER_OFFICIAL_SOURCES",
    "METATRADER5_FOREX_BROKERS",
    "METATRADER5_NON_FOREX_BROKER_MARKET_SCOPES",
    "MOOMOO_BROKER_OFFICIAL_SOURCE",
    "REQUESTED_BROKER_TARGETS",
    "SUPPORTED_BROKERS",
    "SUPPORTED_CONNECTOR_BACKENDS",
    "SUPPORTED_EXCHANGES",
    "SUPPORTED_FOREX_BROKERS",
    "TRADING212_BROKER_OFFICIAL_SOURCE",
    "broker_integration_coverage",
    "build_exchange_support_payload",
    "build_requested_broker_coverage",
    "canonical_broker_name",
    "ccxt_exchange_id_for",
]
