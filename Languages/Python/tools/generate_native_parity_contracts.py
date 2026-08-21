from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import (  # noqa: E402
    INDICATOR_RUNTIME_OUTPUT_KEYS,
    NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION,
    native_position_reconciliation_reference_cases,
    native_runtime_config_invalid_reference_cases,
    native_python_source_contract_hash,
    native_python_source_contract_payload,
    native_python_source_contract_summary,
)
from app.core import indicators as indicator_math  # noqa: E402
from app.core.backtest.engine import BacktestEngine  # noqa: E402
from app.core.backtest.models import BacktestRequest, IndicatorDefinition  # noqa: E402
from app.core.strategy.runtime.strategy_signal_generation import generate_signal  # noqa: E402
from app.gui.shared.helper_runtime import _normalize_connector_backend  # noqa: E402
from app.gui.runtime.composition.module_state_constants import _connector_options  # noqa: E402
from app.settings.connectors import DEFAULT_CONNECTOR_BACKEND  # noqa: E402
from app.settings.exchange_support import (  # noqa: E402
    BROKER_ORDER_ROUTING_BACKENDS,
    SUPPORTED_BROKERS,
    SUPPORTED_EXCHANGES,
    build_exchange_support_payload,
)
from app.settings.validation import validate_runtime_config  # noqa: E402

import pandas as pd  # noqa: E402


RUST_OUTPUT = REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "generated_python_parity.rs"
RUST_INDICATOR_REFERENCE_OUTPUT = (
    REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "generated_python_indicator_reference.rs"
)
RUST_EXCHANGE_SUPPORT_REFERENCE_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "crates"
    / "core"
    / "src"
    / "generated_python_exchange_support_reference.rs"
)
RUST_PORTFOLIO_REFERENCE_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "crates"
    / "core"
    / "src"
    / "generated_python_portfolio_reference.rs"
)
CPP_OUTPUT = REPO_ROOT / "experiments" / "native-cpp" / "src" / "generated" / "PythonParityContract.h"
CPP_INDICATOR_REFERENCE_OUTPUT = (
    REPO_ROOT / "experiments" / "native-cpp" / "src" / "generated" / "PythonIndicatorReference.h"
)
CPP_EXCHANGE_SUPPORT_REFERENCE_OUTPUT = (
    REPO_ROOT / "experiments" / "native-cpp" / "src" / "generated" / "PythonExchangeSupportReference.h"
)
CPP_PORTFOLIO_REFERENCE_OUTPUT = (
    REPO_ROOT / "experiments" / "native-cpp" / "src" / "generated" / "PythonPortfolioReference.h"
)
TAURI_BROWSER_OUTPUT = (
    REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "generated-python-parity.js"
)

INDICATOR_REFERENCE_DECIMAL_PLACES = 12


def _rust_string(value: object) -> str:
    escaped = []
    for char in str(value):
        codepoint = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif 32 <= codepoint <= 126:
            escaped.append(char)
        else:
            escaped.append(f"\\u{{{codepoint:x}}}")
    return '"' + "".join(escaped) + '"'


def _cpp_string(value: object) -> str:
    escaped = []
    for char in str(value):
        codepoint = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif 32 <= codepoint <= 126:
            escaped.append(char)
        elif codepoint <= 0xFFFF:
            escaped.append(f"\\u{codepoint:04x}")
        else:
            escaped.append(f"\\U{codepoint:08x}")
    return '"' + "".join(escaped) + '"'


def _cpp_string_chunks(value: object, chunk_size: int = 6000) -> str:
    text = str(value)
    if not text:
        return _cpp_string(text)
    return "\n    ".join(_cpp_string(text[offset : offset + chunk_size]) for offset in range(0, len(text), chunk_size))


def _cpp_string_view_literal(value: object) -> str:
    text = str(value)
    return f"std::string_view{{{_cpp_string_chunks(text)}, {len(text)}}}"


def _rust_array(name: str, values: list[str]) -> str:
    lines = [f"pub const {name}: &[&str] = &["]
    lines.extend(f"    {_rust_string(value)}," for value in values)
    lines.append("];")
    return "\n".join(lines)


def _cpp_array(name: str, values: list[str]) -> str:
    lines = [f"inline constexpr std::array<std::string_view, {len(values)}> {name} = {{"]
    lines.extend(f"    {_cpp_string(value)}," for value in values)
    lines.append("};")
    return "\n".join(lines)


def _rust_broker_order_routing_backends(values: list[dict[str, object]]) -> str:
    lines = ["pub const PYTHON_BROKER_ORDER_ROUTING_BACKENDS: &[(&str, &str, &str, bool)] = &["]
    for value in values:
        lines.append(
            "    ("
            f"{_rust_string(value['key'])}, {_rust_string(value['backend'])}, "
            f"{_rust_string(value['market_scope'])}, "
            f"{_rust_bool(value['forex_order_routing_supported'])}"
            "),"
        )
    lines.append("];")
    return "\n".join(lines)


def _cpp_broker_order_routing_backends(values: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonBrokerOrderRoutingBackend {",
        "    std::string_view broker;",
        "    std::string_view key;",
        "    std::string_view backend;",
        "    std::string_view marketScope;",
        "    bool forexOrderRoutingSupported;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonBrokerOrderRoutingBackend, "
            f"{len(values)}> kPythonBrokerOrderRoutingBackends = {{"
        ),
    ]
    for value in values:
        lines.append(
            "    PythonBrokerOrderRoutingBackend{"
            f"{_cpp_string(value['broker'])}, {_cpp_string(value['key'])}, "
            f"{_cpp_string(value['backend'])}, {_cpp_string(value['market_scope'])}, "
            f"{_rust_bool(value['forex_order_routing_supported'])}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _rust_broker_canonical_names(values: list[dict[str, object]]) -> str:
    lines = ["pub const PYTHON_BROKER_CANONICAL_NAMES: &[(&str, &str)] = &["]
    lines.extend(
        f"    ({_rust_string(value['identity'])}, {_rust_string(value['canonical'])}),"
        for value in values
    )
    lines.append("];")
    return "\n".join(lines)


def _cpp_broker_canonical_names(values: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonBrokerCanonicalName {",
        "    std::string_view identity;",
        "    std::string_view canonical;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonBrokerCanonicalName, "
            f"{len(values)}> kPythonBrokerCanonicalNames = {{"
        ),
    ]
    lines.extend(
        "    PythonBrokerCanonicalName{"
        f"{_cpp_string(value['identity'])}, {_cpp_string(value['canonical'])}"
        "},"
        for value in values
    )
    lines.append("};")
    return "\n".join(lines)


def _rust_string_pairs(name: str, values: list[dict[str, object]]) -> str:
    lines = [f"pub const {name}: &[(&str, &str)] = &["]
    lines.extend(
        f"    ({_rust_string(value['key'])}, {_rust_string(value['value'])}),"
        for value in values
    )
    lines.append("];")
    return "\n".join(lines)


def _cpp_string_pairs(
    name: str,
    values: list[dict[str, object]],
    *,
    include_struct: bool = True,
) -> str:
    lines = []
    if include_struct:
        lines.extend(
            [
                "struct PythonStringPair {",
                "    std::string_view key;",
                "    std::string_view value;",
                "};",
                "",
            ]
        )
    lines.append(f"inline constexpr std::array<PythonStringPair, {len(values)}> {name} = {{")
    lines.extend(
        "    PythonStringPair{"
        f"{_cpp_string(value['key'])}, {_cpp_string(value['value'])}"
        "},"
        for value in values
    )
    lines.append("};")
    return "\n".join(lines)


def _rust_bool(value: object) -> str:
    return str(bool(value)).lower()


def _contract_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _runtime_config_reference_cases() -> list[dict[str, object]]:
    """Return complete Python validation outputs for native configuration parity tests."""

    raw_cases: list[tuple[str, dict[str, object]]] = [
        (
            "alias-rich-runtime",
            {
                "symbols": ["ethusdt", "ETHUSDT"],
                "intervals": ["1M", "2 hours"],
                "mode": "live",
                "account_type": "futures",
                "margin_mode": "cross",
                "position_mode": "oneway",
                "assets_mode": "multi-asset",
                "account_mode": "portfolio margin",
                "side": "sell",
                "position_pct": "2.5",
                "order_type": "limit",
                "tif": "ioc",
                "live_trading_enabled": "false",
                "live_allow_auto_bump_to_min_order": "yes",
                "live_trading_max_leverage": 20,
                "live_trading_max_position_pct": "4.0",
                "live_trading_max_session_orders": "25",
                "order_audit_enabled": "no",
                "loop_interval_override": "1 hour",
                "connector_backend": "CCXT (Unified)",
                "indicator_source": "binance futures",
                "theme": "green",
                "design": "workstation",
                "selected_exchange": "kucoin",
                "llm_enabled": "true",
                "llm_provider": "chatgpt",
                "llm_use_for": "risk_review",
                "llm_reasoning_effort": "extra-high",
                "llm_model": "local-model",
                "llm_base_url": "http://127.0.0.1:11434/v1",
                "llm_allow_public_network": "false",
                "stop_loss": {
                    "mode": "percent",
                    "scope": "entire_account",
                },
                "chart": {
                    "market": "spot",
                    "view_mode": "TradingView Lightweight",
                    "symbol": "ethusdt",
                    "interval": "1M",
                    "auto_follow": "yes",
                },
                "backtest": {
                    "symbols": ["btcusdt", "BTCUSDT"],
                    "intervals": ["15 minutes", "1M"],
                    "capital": "1000",
                    "execution_backend": "desktop-local",
                    "logic": "or",
                    "symbol_source": "futures",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "position_pct": "2.0",
                    "side": "both",
                    "margin_mode": "isolated",
                    "position_mode": "hedge",
                    "assets_mode": "single-asset mode",
                    "account_mode": "classic trading",
                    "connector_backend": "binance-sdk-spot",
                    "leverage": 20,
                    "mdd_logic": "per_trade",
                    "scan_scope": "top_n",
                    "scan_top_n": 200,
                    "scan_mdd_limit": 20,
                    "scan_auto_apply": "false",
                    "optimizer_mode": "pairs",
                    "optimizer_metric": "roi-percent-mdd",
                    "optimizer_combo_size": 2,
                    "optimizer_max_duration_seconds": 7200,
                    "optimizer_min_trades": 1,
                    "fee_bps": 5.0,
                    "slippage_bps": 2.0,
                    "template": {},
                    "indicators": {},
                    "stop_loss": {
                        "mode": "percent",
                        "scope": "entire_account",
                    },
                },
                "runtime_symbol_interval_pairs": [
                    {
                        "symbol": "btcusdt",
                        "interval": "15 minutes",
                        "strategy_controls": {
                            "side": "buy",
                            "leverage": 20,
                            "loop_interval_override": "1 hour",
                            "stop_loss": {"scope": "bad-scope"},
                        },
                    }
                ],
                "backtest_symbol_interval_pairs": None,
            },
        ),
        (
            "canonical-runtime",
            {
                "symbols": ["BTCUSDT"],
                "intervals": ["15m"],
                "mode": "paper",
                "position_pct": 1.5,
                "side": "BUY",
                "order_type": "MARKET",
                "tif": "GTC",
                "loop_interval_override": "5m",
                "chart": {
                    "market": "Spot",
                    "view_mode": "lightweight",
                    "symbol": "BTCUSDT",
                    "interval": "15m",
                    "auto_follow": True,
                },
            },
        ),
    ]

    generated_cases = [
        {
            "name": name,
            "input": config,
            "valid": True,
            "expected": validate_runtime_config(config),
            "expected_error": "",
        }
        for name, config in raw_cases
    ]
    generated_cases.extend(native_runtime_config_invalid_reference_cases())
    generated_cases.extend(native_python_source_contract_summary()["runtime_config_choice_reference"])
    return generated_cases


def _connector_normalization_reference_cases() -> list[dict[str, str]]:
    """Return Python-owned connector aliases and fallback expectations."""

    labels_by_key = {key: label for label, key in _connector_options()}
    raw_cases = [
        ("empty", ""),
        ("usds-key", "binance-sdk-derivatives-trading-usds-futures"),
        ("usds-underscore-key", "binance_sdk_derivatives_trading_usds_futures"),
        ("usds-label", labels_by_key["binance-sdk-derivatives-trading-usds-futures"]),
        ("coin-key", "binance-sdk-derivatives-trading-coin-futures"),
        ("coin-label", labels_by_key["binance-sdk-derivatives-trading-coin-futures"]),
        ("spot-label", labels_by_key["binance-sdk-spot"]),
        ("connector-label", labels_by_key["binance-connector"]),
        ("ccxt-label", labels_by_key["ccxt"]),
        ("python-binance-label", labels_by_key["python-binance"]),
        ("official-connector-alias", "Binance Official REST connector"),
        ("unrelated-option-falls-back", labels_by_key["oanda-rest"]),
        ("legacy-gateway-falls-back", "gateway"),
        ("legacy-custom-falls-back", "custom"),
        ("url-value-falls-back", "https://connector.example.test/api"),
        ("unknown-falls-back", "unknown backend"),
    ]
    return [
        {
            "name": name,
            "input": input_value,
            "expected": _normalize_connector_backend(input_value),
        }
        for name, input_value in raw_cases
    ]


def _json_series(series: object) -> list[float | None]:
    values = series.tolist() if hasattr(series, "tolist") else list(series)
    normalized: list[float | None] = []
    for value in values:
        if pd.isna(value):
            normalized.append(None)
            continue

        rounded = round(float(value), INDICATOR_REFERENCE_DECIMAL_PLACES)
        normalized.append(0.0 if rounded == 0.0 else rounded)
    return normalized


def _json_backtest_result(result: object) -> dict[str, object]:
    payload = asdict(result)
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        elif isinstance(value, float):
            rounded = round(value, INDICATOR_REFERENCE_DECIMAL_PLACES)
            normalized[key] = 0.0 if rounded == 0.0 else rounded
        else:
            normalized[key] = value
    return normalized


def _backtest_reference_cases(
    frame: pd.DataFrame,
    fixture_name: str = "baseline",
) -> list[dict[str, object]]:
    indexed = frame.copy()
    start = datetime(2024, 1, 1, 0, 0, 0)
    indexed.index = [start + timedelta(minutes=offset) for offset in range(len(indexed))]
    end = indexed.index[-1].to_pydatetime()
    engine = BacktestEngine(wrapper=None)
    cases: list[dict[str, object]] = [
        {
            "name": "rsi-per-trade-both",
            "logic": "OR",
            "side": "BOTH",
            "capital": 1000.0,
            "position_pct": 25.0,
            "position_pct_units": "percent",
            "leverage": 1.0,
            "margin_mode": "Isolated",
            "mdd_logic": "per_trade",
            "stop_loss": {"enabled": False, "mode": "usdt", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "rsi": {"enabled": True, "length": 3, "buy_value": 45.0, "sell_value": 55.0},
            },
        },
        {
            "name": "rsi-fee-slippage-stress",
            "logic": "OR",
            "side": "BOTH",
            "capital": 1000.0,
            "position_pct": 25.0,
            "position_pct_units": "percent",
            "leverage": 2.0,
            "margin_mode": "Cross",
            "mdd_logic": "per_trade",
            "fee_bps": 25.0,
            "slippage_bps": 15.0,
            "stop_loss": {"enabled": False, "mode": "usdt", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "rsi": {"enabled": True, "length": 3, "buy_value": 45.0, "sell_value": 55.0},
            },
        },
        {
            "name": "ma-cross-cumulative-long",
            "logic": "AND",
            "side": "BUY",
            "capital": 750.0,
            "position_pct": 0.4,
            "position_pct_units": "fraction",
            "leverage": 2.0,
            "margin_mode": "Cross",
            "mdd_logic": "cumulative",
            "stop_loss": {"enabled": False, "mode": "percent", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "ma": {
                    "enabled": True,
                    "length": 3,
                    "type": "SMA",
                    "signal_mode": "price_cross",
                    "buy_value": 0.0,
                    "sell_value": 0.0,
                },
            },
        },
        {
            "name": "rsi-entire-account-stop",
            "logic": "OR",
            "side": "BOTH",
            "capital": 1200.0,
            "position_pct": 50.0,
            "position_pct_units": "percent",
            "leverage": 4.0,
            "margin_mode": "Isolated",
            "mdd_logic": "entire_account",
            "stop_loss": {"enabled": True, "mode": "percent", "usdt": 0.0, "percent": 2.0, "scope": "per_trade"},
            "configs": {
                "rsi": {"enabled": True, "length": 3, "buy_value": 45.0, "sell_value": 55.0},
            },
        },
        {
            "name": "rsi-with-rvol-filter-short",
            "logic": "OR",
            "side": "SELL",
            "capital": 900.0,
            "position_pct": 30.0,
            "position_pct_units": "percent",
            "leverage": 3.0,
            "margin_mode": "Cross",
            "mdd_logic": "per_trade",
            "stop_loss": {"enabled": True, "mode": "both", "usdt": 30.0, "percent": 5.0, "scope": "cumulative"},
            "configs": {
                "rsi": {"enabled": True, "length": 3, "buy_value": 45.0, "sell_value": 55.0},
                "rvol": {
                    "enabled": True,
                    "length": 3,
                    "signal_role": "filter",
                    "filter_operator": "gte",
                    "filter_value": 0.8,
                    "buy_value": 0.8,
                },
            },
        },
        {
            "name": "donchian-band-position-both",
            "logic": "OR",
            "side": "BOTH",
            "capital": 1100.0,
            "position_pct": 35.0,
            "position_pct_units": "percent",
            "leverage": 2.0,
            "margin_mode": "Isolated",
            "mdd_logic": "per_trade",
            "stop_loss": {"enabled": False, "mode": "percent", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "donchian": {
                    "enabled": True,
                    "length": 3,
                    "signal_mode": "band_position",
                    "buy_value": 20.0,
                    "sell_value": 80.0,
                },
            },
        },
        {
            "name": "volume-relative-between-filter",
            "logic": "OR",
            "side": "BUY",
            "capital": 1000.0,
            "position_pct": 25.0,
            "position_pct_units": "percent",
            "leverage": 1.0,
            "margin_mode": "Cross",
            "mdd_logic": "cumulative",
            "stop_loss": {"enabled": False, "mode": "usdt", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "rsi": {"enabled": True, "length": 3, "buy_value": 45.0, "sell_value": 55.0},
                "volume": {
                    "enabled": True,
                    "length": 3,
                    "signal_mode": "relative_to_sma",
                    "signal_role": "filter",
                    "filter_operator": "between",
                    "buy_value": 0.8,
                    "sell_value": 1.2,
                },
            },
        },
        {
            "name": "obv-slope-short",
            "logic": "OR",
            "side": "SELL",
            "capital": 950.0,
            "position_pct": 30.0,
            "position_pct_units": "percent",
            "leverage": 3.0,
            "margin_mode": "Isolated",
            "mdd_logic": "entire_account",
            "stop_loss": {"enabled": True, "mode": "usdt", "usdt": 20.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "obv": {
                    "enabled": True,
                    "length": 3,
                    "signal_mode": "slope",
                    "buy_value": 0.0,
                    "sell_value": 0.0,
                },
            },
        },
        {
            "name": "atr-percent-of-close-long",
            "logic": "OR",
            "side": "BUY",
            "capital": 1050.0,
            "position_pct": 40.0,
            "position_pct_units": "percent",
            "leverage": 2.0,
            "margin_mode": "Cross",
            "mdd_logic": "per_trade",
            "stop_loss": {"enabled": True, "mode": "percent", "usdt": 0.0, "percent": 3.0, "scope": "cumulative"},
            "configs": {
                "atr": {
                    "enabled": True,
                    "length": 3,
                    "signal_mode": "percent_of_close",
                    "buy_value": 1.0,
                    "sell_value": 2.0,
                },
            },
        },
        {
            "name": "macd-histogram-both",
            "logic": "AND",
            "side": "BOTH",
            "capital": 875.0,
            "position_pct": 0.5,
            "position_pct_units": "fraction",
            "leverage": 2.0,
            "margin_mode": "Isolated",
            "mdd_logic": "cumulative",
            "stop_loss": {"enabled": False, "mode": "percent", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "macd": {
                    "enabled": True,
                    "fast": 2,
                    "slow": 3,
                    "signal": 2,
                    "buy_value": 0.0,
                    "sell_value": 0.0,
                },
            },
        },
        {
            "name": "volume-window-signal-reset",
            "logic": "OR",
            "side": "BUY",
            "capital": 1000.0,
            "position_pct": 1.0,
            "position_pct_units": "fraction",
            "leverage": 1.0,
            "margin_mode": "Isolated",
            "mdd_logic": "per_trade",
            "execution_start_offset": 1,
            "stop_loss": {"enabled": False, "mode": "usdt", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            "configs": {
                "volume": {
                    "enabled": True,
                    "buy_value": 10.0,
                },
            },
        },
    ]

    rendered: list[dict[str, object]] = []
    for case in cases:
        execution_start_offset = max(0, min(int(case.get("execution_start_offset", 0)), len(indexed) - 1))
        execution_start = indexed.index[execution_start_offset].to_pydatetime()
        execution_frame = indexed.iloc[execution_start_offset:]
        configs = case["configs"]
        assert isinstance(configs, dict)
        indicators = []
        for key, raw_config in configs.items():
            config = dict(raw_config)
            config.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=key, params=config))
        stop_loss = case["stop_loss"]
        assert isinstance(stop_loss, dict)
        request = BacktestRequest(
            symbols=["FIXTUREUSDT"],
            intervals=["1m"],
            indicators=indicators,
            logic=str(case["logic"]),
            symbol_source="Futures",
            start=execution_start,
            end=end,
            capital=float(case["capital"]),
            side=str(case["side"]),
            position_pct=float(case["position_pct"]),
            position_pct_units=str(case["position_pct_units"]),
            leverage=float(case["leverage"]),
            margin_mode=str(case["margin_mode"]),
            position_mode="Hedge",
            assets_mode="Single-Asset",
            account_mode="Classic Trading",
            mdd_logic=str(case["mdd_logic"]),
            fee_bps=float(case.get("fee_bps", 5.0)),
            slippage_bps=float(case.get("slippage_bps", 2.0)),
            stop_loss_enabled=bool(stop_loss["enabled"]),
            stop_loss_mode=str(stop_loss["mode"]),
            stop_loss_usdt=float(stop_loss["usdt"]),
            stop_loss_percent=float(stop_loss["percent"]),
            stop_loss_scope=str(stop_loss["scope"]),
        )
        result = engine._simulate(
            "FIXTUREUSDT",
            "1m",
            indexed,
            indicators,
            request,
            work_df=execution_frame,
        )
        if result is None:
            raise RuntimeError(f"Python backtest fixture case produced no result: {case['name']}")
        rendered.append(
            {
                **case,
                "fixture_name": fixture_name,
                "candles": frame.to_dict(orient="records"),
                "expected": _json_backtest_result(result),
            }
        )
    return rendered


def _indicator_configs(variant: str = "baseline") -> dict[str, dict[str, object]]:
    configs: dict[str, dict[str, object]] = {
        "ma": {"enabled": True, "length": 3, "type": "SMA"},
        "donchian": {"enabled": True, "length": 3},
        "psar": {"enabled": True, "af": 0.02, "max_af": 0.2},
        "bb": {"enabled": True, "length": 3, "std": 2.0},
        "bbw": {"enabled": True, "length": 3, "std": 2.0},
        "keltner": {"enabled": True, "length": 3, "atr_length": 2, "multiplier": 2.0},
        "ichimoku": {"enabled": True, "conversion_length": 2, "base_length": 3, "span_b_length": 4, "displacement": 2},
        "rsi": {"enabled": True, "length": 3},
        "volume": {"enabled": True},
        "obv": {"enabled": True},
        "rvol": {"enabled": True, "length": 3},
        "cmf": {"enabled": True, "length": 3},
        "cci": {"enabled": True, "length": 3, "constant": 0.015},
        "roc": {"enabled": True, "length": 3},
        "trix": {"enabled": True, "length": 3},
        "ppo": {"enabled": True, "fast": 2, "slow": 3, "signal": 2},
        "ao": {"enabled": True, "fast": 2, "slow": 3},
        "kst": {
            "enabled": True,
            "roc1": 1,
            "roc2": 2,
            "roc3": 3,
            "roc4": 4,
            "sma1": 2,
            "sma2": 2,
            "sma3": 2,
            "sma4": 2,
            "signal": 2,
        },
        "aroon": {"enabled": True, "length": 3},
        "chop": {"enabled": True, "length": 3},
        "atr": {"enabled": True, "length": 3},
        "natr": {"enabled": True, "length": 3},
        "vwap": {"enabled": True, "length": 3},
        "mfi": {"enabled": True, "length": 3},
        "stoch_rsi": {"enabled": True, "length": 3, "smooth_k": 2, "smooth_d": 2},
        "willr": {"enabled": True, "length": 3},
        "macd": {"enabled": True, "fast": 2, "slow": 3, "signal": 2},
        "uo": {"enabled": True, "short": 2, "medium": 3, "long": 4},
        "adx": {"enabled": True, "length": 3},
        "dmi": {"enabled": True, "length": 3},
        "supertrend": {"enabled": True, "atr_period": 2, "multiplier": 3.0},
        "ema": {"enabled": True, "length": 3},
        "stochastic": {"enabled": True, "length": 3, "smooth_k": 2, "smooth_d": 2},
    }
    if variant == "parameterized":
        configs.update(
            {
                "ma": {"enabled": True, "length": 4, "type": "EMA"},
                "donchian": {"enabled": True, "length": 4},
                "psar": {"enabled": True, "af": 0.04, "max_af": 0.4},
                "bb": {"enabled": True, "length": 4, "std": 1.5},
                "bbw": {"enabled": True, "length": 4, "std": 1.5},
                "keltner": {"enabled": True, "length": 4, "atr_length": 3, "multiplier": 1.5},
                "ichimoku": {"enabled": True, "conversion_length": 3, "base_length": 4, "span_b_length": 5, "displacement": 3},
                "rsi": {"enabled": True, "length": 5},
                "rvol": {"enabled": True, "length": 4},
                "cmf": {"enabled": True, "length": 4},
                "cci": {"enabled": True, "length": 4, "constant": 0.02},
                "roc": {"enabled": True, "length": 4},
                "trix": {"enabled": True, "length": 4},
                "ppo": {"enabled": True, "fast": 3, "slow": 5, "signal": 3},
                "ao": {"enabled": True, "fast": 3, "slow": 5},
                "kst": {
                    "enabled": True,
                    "roc1": 2,
                    "roc2": 3,
                    "roc3": 4,
                    "roc4": 5,
                    "sma1": 3,
                    "sma2": 3,
                    "sma3": 3,
                    "sma4": 3,
                    "signal": 3,
                },
                "aroon": {"enabled": True, "length": 4},
                "chop": {"enabled": True, "length": 4},
                "atr": {"enabled": True, "length": 4},
                "natr": {"enabled": True, "length": 4},
                "vwap": {"enabled": True, "length": 4},
                "mfi": {"enabled": True, "length": 4},
                "stoch_rsi": {"enabled": True, "length": 5, "smooth_k": 3, "smooth_d": 3},
                "willr": {"enabled": True, "length": 4},
                "macd": {"enabled": True, "fast": 3, "slow": 5, "signal": 3},
                "uo": {"enabled": True, "short": 3, "medium": 4, "long": 6},
                "adx": {"enabled": True, "length": 4},
                "dmi": {"enabled": True, "length": 4},
                "supertrend": {"enabled": True, "atr_period": 4, "multiplier": 2.5},
                "ema": {"enabled": True, "length": 4},
                "stochastic": {"enabled": True, "length": 4, "smooth_k": 3, "smooth_d": 3},
            }
        )
    elif variant != "baseline":
        raise ValueError(f"Unknown indicator fixture variant: {variant}")
    return configs


def _indicator_config_int(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    return int(default if value is None else value)


def _indicator_config_float(config: dict[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    return float(default if value is None else value)


def _indicator_expected(
    frame: pd.DataFrame,
    configs: dict[str, dict[str, object]],
) -> dict[str, object]:
    ma_config = configs["ma"]
    ma_length = _indicator_config_int(ma_config, "length", 20)
    ma = (
        indicator_math.ema(frame["close"], ma_length)
        if str(ma_config.get("type", "SMA")).upper() == "EMA"
        else indicator_math.sma(frame["close"], ma_length)
    )
    donchian_config = configs["donchian"]
    donchian_length = _indicator_config_int(donchian_config, "length", 20)
    donchian_high = indicator_math.donchian_high(frame, donchian_length)
    donchian_low = indicator_math.donchian_low(frame, donchian_length)
    psar_config = configs["psar"]
    bb_config = configs["bb"]
    bb_upper, bb_mid, bb_lower = indicator_math.bollinger_bands(
        frame,
        length=_indicator_config_int(bb_config, "length", 20),
        std=_indicator_config_float(bb_config, "std", 2.0),
    )
    bbw_config = configs["bbw"]
    keltner_config = configs["keltner"]
    keltner_upper, keltner_mid, keltner_lower = indicator_math.keltner_channels(
        frame,
        length=_indicator_config_int(keltner_config, "length", 20),
        atr_length=_indicator_config_int(keltner_config, "atr_length", 10),
        multiplier=_indicator_config_float(keltner_config, "multiplier", 2.0),
    )
    ichimoku_config = configs["ichimoku"]
    ichimoku_tenkan, ichimoku_kijun, ichimoku_span_a, ichimoku_span_b, ichimoku_chikou = indicator_math.ichimoku_cloud(
        frame,
        conversion_length=_indicator_config_int(ichimoku_config, "conversion_length", 9),
        base_length=_indicator_config_int(ichimoku_config, "base_length", 26),
        span_b_length=_indicator_config_int(ichimoku_config, "span_b_length", 52),
        displacement=_indicator_config_int(ichimoku_config, "displacement", 26),
    )
    rsi_config = configs["rsi"]
    rvol_config = configs["rvol"]
    cmf_config = configs["cmf"]
    cci_config = configs["cci"]
    roc_config = configs["roc"]
    trix_config = configs["trix"]
    ppo_config = configs["ppo"]
    ppo_line, ppo_signal, ppo_hist = indicator_math.ppo(
        frame["close"],
        fast=_indicator_config_int(ppo_config, "fast", 12),
        slow=_indicator_config_int(ppo_config, "slow", 26),
        signal=_indicator_config_int(ppo_config, "signal", 9),
    )
    ao_config = configs["ao"]
    kst_config = configs["kst"]
    kst_line, kst_signal, kst_hist = indicator_math.kst(
        frame["close"],
        roc1=_indicator_config_int(kst_config, "roc1", 10),
        roc2=_indicator_config_int(kst_config, "roc2", 15),
        roc3=_indicator_config_int(kst_config, "roc3", 20),
        roc4=_indicator_config_int(kst_config, "roc4", 30),
        sma1=_indicator_config_int(kst_config, "sma1", 10),
        sma2=_indicator_config_int(kst_config, "sma2", 10),
        sma3=_indicator_config_int(kst_config, "sma3", 10),
        sma4=_indicator_config_int(kst_config, "sma4", 15),
        signal=_indicator_config_int(kst_config, "signal", 9),
    )
    aroon_config = configs["aroon"]
    stoch_rsi_config = configs["stoch_rsi"]
    stoch_rsi, stoch_rsi_d = indicator_math.stoch_rsi(
        frame["close"],
        length=_indicator_config_int(stoch_rsi_config, "length", 14),
        smooth_k=_indicator_config_int(stoch_rsi_config, "smooth_k", 3),
        smooth_d=_indicator_config_int(stoch_rsi_config, "smooth_d", 3),
    )
    macd_config = configs["macd"]
    macd_line, macd_signal, _macd_hist = indicator_math.macd(
        frame["close"],
        fast=_indicator_config_int(macd_config, "fast", 12),
        slow=_indicator_config_int(macd_config, "slow", 26),
        signal=_indicator_config_int(macd_config, "signal", 9),
    )
    dmi_config = configs["dmi"]
    dmi_plus, dmi_minus, adx = indicator_math.dmi(
        frame,
        length=_indicator_config_int(dmi_config, "length", 14),
    )
    stochastic_config = configs["stochastic"]
    stochastic, stochastic_d = indicator_math.stochastic(
        frame,
        length=_indicator_config_int(stochastic_config, "length", 14),
        smooth_k=_indicator_config_int(stochastic_config, "smooth_k", 3),
        smooth_d=_indicator_config_int(stochastic_config, "smooth_d", 3),
    )
    aroon_up, aroon_down, aroon = indicator_math.aroon(
        frame,
        length=_indicator_config_int(aroon_config, "length", 25),
    )
    expected = {
        "ma": ma,
        "donchian_high": donchian_high,
        "donchian_low": donchian_low,
        "donchian": (donchian_high + donchian_low) / 2.0,
        "psar": indicator_math.parabolic_sar(
            frame,
            af=_indicator_config_float(psar_config, "af", 0.02),
            max_af=_indicator_config_float(psar_config, "max_af", 0.2),
        ),
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
        "bbw": indicator_math.bollinger_band_width(
            frame,
            length=_indicator_config_int(bbw_config, "length", 20),
            std=_indicator_config_float(bbw_config, "std", 2.0),
        ),
        "keltner_upper": keltner_upper,
        "keltner_mid": keltner_mid,
        "keltner_lower": keltner_lower,
        "ichimoku_tenkan": ichimoku_tenkan,
        "ichimoku_kijun": ichimoku_kijun,
        "ichimoku_span_a": ichimoku_span_a,
        "ichimoku_span_b": ichimoku_span_b,
        "ichimoku_chikou": ichimoku_chikou,
        "ichimoku": ichimoku_tenkan - ichimoku_kijun,
        "rsi": indicator_math.rsi(
            frame["close"], length=_indicator_config_int(rsi_config, "length", 14)
        ),
        "volume": frame["volume"],
        "obv": indicator_math.obv(frame),
        "rvol": indicator_math.relative_volume(
            frame, length=_indicator_config_int(rvol_config, "length", 20)
        ),
        "cmf": indicator_math.chaikin_money_flow(
            frame, length=_indicator_config_int(cmf_config, "length", 20)
        ),
        "cci": indicator_math.cci(
            frame,
            length=_indicator_config_int(cci_config, "length", 20),
            constant=_indicator_config_float(cci_config, "constant", 0.015),
        ),
        "roc": indicator_math.roc(
            frame["close"], length=_indicator_config_int(roc_config, "length", 12)
        ),
        "trix": indicator_math.trix(
            frame["close"], length=_indicator_config_int(trix_config, "length", 15)
        ),
        "ppo": ppo_line,
        "ppo_signal": ppo_signal,
        "ppo_hist": ppo_hist,
        "ao": indicator_math.awesome_oscillator(
            frame,
            fast=_indicator_config_int(ao_config, "fast", 5),
            slow=_indicator_config_int(ao_config, "slow", 34),
        ),
        "kst": kst_line,
        "kst_signal": kst_signal,
        "kst_hist": kst_hist,
        "aroon_up": aroon_up,
        "aroon_down": aroon_down,
        "aroon": aroon,
        "chop": indicator_math.choppiness_index(
            frame, length=_indicator_config_int(configs["chop"], "length", 14)
        ),
        "atr": indicator_math.atr(
            frame, length=_indicator_config_int(configs["atr"], "length", 14)
        ),
        "natr": indicator_math.natr(
            frame, length=_indicator_config_int(configs["natr"], "length", 14)
        ),
        "vwap": indicator_math.vwap(
            frame, length=_indicator_config_int(configs["vwap"], "length", 20)
        ),
        "mfi": indicator_math.mfi(
            frame, length=_indicator_config_int(configs["mfi"], "length", 14)
        ),
        "stoch_rsi": stoch_rsi,
        "stoch_rsi_k": stoch_rsi,
        "stoch_rsi_d": stoch_rsi_d,
        "willr": indicator_math.williams_r(
            frame, length=_indicator_config_int(configs["willr"], "length", 14)
        ),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "uo": indicator_math.ultimate_oscillator(
            frame,
            short=_indicator_config_int(configs["uo"], "short", 7),
            medium=_indicator_config_int(configs["uo"], "medium", 14),
            long=_indicator_config_int(configs["uo"], "long", 28),
        ),
        "adx": adx,
        "dmi_plus": dmi_plus,
        "dmi_minus": dmi_minus,
        "dmi": dmi_plus - dmi_minus,
        "supertrend": indicator_math.supertrend(
            frame,
            atr_period=_indicator_config_int(configs["supertrend"], "atr_period", 10),
            multiplier=_indicator_config_float(configs["supertrend"], "multiplier", 3.0),
        ),
        "ema": indicator_math.ema(
            frame["close"], _indicator_config_int(configs["ema"], "length", 20)
        ),
        "stochastic": stochastic,
        "stochastic_k": stochastic,
        "stochastic_d": stochastic_d,
    }
    declared_output_keys = {
        output_key for output_keys in INDICATOR_RUNTIME_OUTPUT_KEYS.values() for output_key in output_keys
    }
    expected_output_keys = set(expected)
    if declared_output_keys != expected_output_keys:
        missing = ", ".join(sorted(expected_output_keys - declared_output_keys))
        unexpected = ", ".join(sorted(declared_output_keys - expected_output_keys))
        raise RuntimeError(
            "INDICATOR_RUNTIME_OUTPUT_KEYS must exactly match the Python numerical "
            f"indicator fixture (missing: {missing or '-'}; unexpected: {unexpected or '-'})"
        )
    return expected


def _indicator_case_payload(
    name: str,
    frame: pd.DataFrame,
    configs: dict[str, dict[str, object]],
) -> dict[str, object]:
    expected = _indicator_expected(frame, configs)
    return {
        "name": name,
        "candles": frame.to_dict(orient="records"),
        "configs": configs,
        "expected": {key: _json_series(series) for key, series in expected.items()},
    }


class _LiveSignalFixtureStrategy:
    """Small adapter that executes the Python signal function without starting the app."""

    def __init__(self, config: dict[str, object], use_live_values: bool) -> None:
        self.config = config
        self._indicator_use_live_values = use_live_values

    def _indicator_prev_live_signal_values(self, series: object) -> tuple[float, float, float]:
        data = series.dropna()
        if data.empty:
            raise ValueError("indicator series empty")
        live = float(data.iloc[-1])
        previous = float(data.iloc[-2]) if len(data) >= 2 else live
        selected = live if self._indicator_use_live_values else previous
        return previous, live, selected


def _json_number(value: object) -> float | None:
    if value is None:
        return None
    rounded = round(float(value), INDICATOR_REFERENCE_DECIMAL_PLACES)
    return 0.0 if rounded == 0.0 else rounded


def _live_signal_case_payload(
    name: str,
    frame: pd.DataFrame,
    indicator_key: str,
    thresholds: dict[str, float],
    *,
    side: str = "BUY",
    use_live_values: bool = True,
) -> dict[str, object]:
    configs = {key: dict(value) for key, value in _indicator_configs().items()}
    for config in configs.values():
        config["enabled"] = False
    configs[indicator_key].update({"enabled": True, **thresholds})
    expected_series = _indicator_expected(frame, configs)
    strategy = _LiveSignalFixtureStrategy(
        {"side": side, "indicators": configs},
        use_live_values,
    )
    signal, description, trigger_price, trigger_sources, trigger_actions = generate_signal(
        strategy,
        frame,
        expected_series,
    )
    return {
        "name": name,
        "candles": frame.to_dict(orient="records"),
        "configs": configs,
        "indicators": {key: _json_series(series) for key, series in expected_series.items()},
        "side": side,
        "use_live_values": use_live_values,
        "expected": {
            "signal": signal,
            "description": description,
            "trigger_price": _json_number(trigger_price),
            "trigger_sources": trigger_sources,
            "trigger_actions": trigger_actions,
            "min_bars": 2 if use_live_values else 3,
            "signal_index_from_end": 1 if use_live_values else 2,
        },
    }


def _exchange_support_input(
    *,
    selected_exchange: str = "",
    connector_backend: str = "",
    selected_forex_broker: str = "",
) -> dict[str, str]:
    return {
        "selected_exchange": selected_exchange,
        "connector_backend": connector_backend,
        "selected_forex_broker": selected_forex_broker,
    }


def _exchange_support_case(
    name: str,
    config: dict[str, str],
    snapshot: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "config": config,
        "snapshot": snapshot,
        "expected": build_exchange_support_payload(config=config, snapshot=snapshot),
    }


def _exchange_support_reference_payload() -> dict[str, object]:
    cases: list[dict[str, object]] = []

    cases.append(_exchange_support_case("empty-input", _exchange_support_input()))
    cases.append(
        _exchange_support_case(
            "binance-default",
            _exchange_support_input(
                selected_exchange="Binance",
                connector_backend=DEFAULT_CONNECTOR_BACKEND,
            ),
        )
    )

    for index, exchange in enumerate(SUPPORTED_EXCHANGES):
        backend = DEFAULT_CONNECTOR_BACKEND if exchange == "Binance" else "ccxt"
        cases.append(
            _exchange_support_case(
                f"supported-exchange-{index:02d}-{exchange}",
                _exchange_support_input(
                    selected_exchange=exchange,
                    connector_backend=backend,
                ),
            )
        )

    for index, broker in enumerate(SUPPORTED_BROKERS):
        broker_key = broker.lower().replace("_", "-")
        backend = BROKER_ORDER_ROUTING_BACKENDS.get(broker_key)
        if not backend:
            raise RuntimeError(f"Missing generated broker backend for Python broker {broker!r}")
        cases.append(
            _exchange_support_case(
                f"supported-broker-{index:02d}-{broker}",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend=backend,
                    selected_forex_broker=broker,
                ),
            )
        )

    cases.extend(
        (
            _exchange_support_case(
                "snapshot-takes-precedence",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend=DEFAULT_CONNECTOR_BACKEND,
                    selected_forex_broker="OANDA",
                ),
                _exchange_support_input(
                    selected_exchange="Bybit",
                    connector_backend="ccxt",
                    selected_forex_broker="",
                ),
            ),
            _exchange_support_case(
                "snapshot-partial-broker-alias",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend=DEFAULT_CONNECTOR_BACKEND,
                    selected_forex_broker="OANDA",
                ),
                _exchange_support_input(
                    selected_exchange="",
                    connector_backend="",
                    selected_forex_broker="AI Gold",
                ),
            ),
            _exchange_support_case(
                "ccxt-case-normalization",
                _exchange_support_input(selected_exchange="gate", connector_backend="CCXT"),
            ),
            _exchange_support_case(
                "ai-gold-alias",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend="metatrader5",
                    selected_forex_broker=" AI Gold ",
                ),
            ),
            _exchange_support_case(
                "phillip-alias",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend="metatrader5",
                    selected_forex_broker="Philip Securities",
                ),
            ),
            _exchange_support_case(
                "wrong-broker-backend",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend="ccxt",
                    selected_forex_broker="IG",
                ),
            ),
            _exchange_support_case(
                "blocked-broker",
                _exchange_support_input(
                    selected_exchange="Binance",
                    connector_backend="ccxt",
                    selected_forex_broker="Mitrade",
                ),
            ),
            _exchange_support_case(
                "unknown-exchange-backend-broker",
                _exchange_support_input(
                    selected_exchange="Unlisted",
                    connector_backend="custom-native",
                    selected_forex_broker="Unknown Broker",
                ),
            ),
        )
    )
    return {
        "python_source_contract_hash": native_python_source_contract_hash(),
        "exchange_support_cases": cases,
    }


def _portfolio_reference_payload() -> dict[str, object]:
    return {
        "python_source_contract_hash": native_python_source_contract_hash(),
        "schema_version": NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION,
        "position_reconciliation_cases": native_position_reconciliation_reference_cases(),
    }


def _indicator_reference_payload() -> dict[str, object]:
    baseline_closes = [100.0, 103.0, 101.0, 106.0, 104.0, 109.0, 105.0, 111.0, 108.0, 114.0, 110.0, 116.0]
    baseline_highs = [101.0, 104.5, 102.5, 107.5, 105.0, 110.5, 106.0, 112.5, 109.5, 115.0, 111.5, 117.0]
    baseline_lows = [98.5, 101.0, 99.0, 103.5, 102.0, 107.0, 103.0, 109.0, 106.0, 112.0, 108.0, 114.0]
    baseline_volumes = [18.0, 31.0, 24.0, 42.0, 29.0, 47.0, 35.0, 53.0, 38.0, 59.0, 44.0, 63.0]
    baseline_frame = pd.DataFrame(
        {
            "open": baseline_closes,
            "high": baseline_highs,
            "low": baseline_lows,
            "close": baseline_closes,
            "volume": baseline_volumes,
        }
    )

    reversal_closes = [
        100.0,
        100.0,
        101.5,
        99.5,
        103.0,
        98.0,
        102.0,
        97.5,
        104.0,
        96.0,
        101.0,
        99.0,
        105.0,
        98.5,
        103.5,
        97.0,
        106.0,
        95.5,
        102.5,
        100.0,
        107.0,
        96.5,
        104.5,
        98.0,
    ]
    reversal_frame = pd.DataFrame(
        {
            "open": reversal_closes,
            "high": [close + 1.0 + (index % 3) * 0.5 for index, close in enumerate(reversal_closes)],
            "low": [close - 1.5 - (index % 2) * 0.25 for index, close in enumerate(reversal_closes)],
            "close": reversal_closes,
            "volume": [10.0 + (index % 5) * 17.0 + (index * 3.0) for index in range(len(reversal_closes))],
        }
    )

    parameterized_closes = [
        200.0,
        198.0,
        201.0,
        205.0,
        202.0,
        207.0,
        204.0,
        209.0,
        203.0,
        211.0,
        206.0,
        214.0,
        210.0,
        216.0,
        208.0,
        219.0,
        212.0,
        221.0,
        215.0,
        223.0,
        217.0,
        225.0,
        220.0,
        228.0,
    ]
    parameterized_frame = pd.DataFrame(
        {
            "open": parameterized_closes,
            "high": [close + 1.2 + (index % 4) * 0.35 for index, close in enumerate(parameterized_closes)],
            "low": [close - 1.1 - (index % 3) * 0.4 for index, close in enumerate(parameterized_closes)],
            "close": parameterized_closes,
            "volume": [25.0 + ((index * 11) % 70) for index in range(len(parameterized_closes))],
        }
    )

    short_warmup_frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [10.0, 10.0],
        }
    )
    flat_price_frame = pd.DataFrame(
        {
            "open": [100.0] * 16,
            "high": [101.0] * 16,
            "low": [99.0] * 16,
            "close": [100.0] * 16,
            "volume": [10.0] * 16,
        }
    )
    zero_volume_frame = pd.DataFrame(
        {
            "open": [100.0 + index for index in range(16)],
            "high": [101.0 + index for index in range(16)],
            "low": [99.0 + index for index in range(16)],
            "close": [100.0 + index for index in range(16)],
            "volume": [0.0] * 16,
        }
    )
    threshold_zero_frame = pd.DataFrame(
        {
            "open": [
                100.0,
                97.0,
                97.0,
                96.0,
                96.0,
                93.0,
                92.0,
                89.0,
                88.0,
                87.0,
                86.0,
                83.0,
                83.0,
                84.0,
                83.0,
                82.0,
            ],
            "high": [101.0, 98.0, 98.0, 97.0, 97.0, 94.0, 93.0, 90.0, 89.0, 88.0, 87.0, 84.0, 84.0, 85.0, 84.0, 83.0],
            "low": [99.0, 96.0, 96.0, 95.0, 95.0, 92.0, 91.0, 88.0, 87.0, 86.0, 85.0, 82.0, 82.0, 83.0, 82.0, 81.0],
            "close": [
                100.0,
                97.0,
                97.0,
                96.0,
                96.0,
                93.0,
                92.0,
                89.0,
                88.0,
                87.0,
                86.0,
                83.0,
                83.0,
                84.0,
                83.0,
                82.0,
            ],
            "volume": [20.0] * 16,
        }
    )
    mfi_threshold_frame = pd.DataFrame(
        {
            "open": [100.0 + index for index in range(16)],
            "high": [101.0 + index for index in range(16)],
            "low": [99.0 + index for index in range(16)],
            "close": [100.0 + index for index in range(16)],
            "volume": [20.0] * 16,
        }
    )
    string_config_values = _indicator_configs()
    for config in string_config_values.values():
        for key, value in list(config.items()):
            if key == "enabled":
                config[key] = "true"
            elif key != "type" and isinstance(value, (int, float)):
                config[key] = str(value)

    cases = [
        _indicator_case_payload("baseline", baseline_frame, _indicator_configs()),
        _indicator_case_payload("reversal-and-flat", reversal_frame, _indicator_configs()),
        _indicator_case_payload(
            "parameterized-longer-series",
            parameterized_frame,
            _indicator_configs("parameterized"),
        ),
        _indicator_case_payload("short-warmup-series", short_warmup_frame, _indicator_configs()),
        _indicator_case_payload("flat-price-series", flat_price_frame, _indicator_configs()),
        _indicator_case_payload("zero-volume-series", zero_volume_frame, _indicator_configs()),
        _indicator_case_payload("threshold-zero-series", threshold_zero_frame, _indicator_configs()),
        _indicator_case_payload("mfi-threshold-series", mfi_threshold_frame, _indicator_configs()),
        _indicator_case_payload("string-config-values", parameterized_frame, string_config_values),
    ]
    primary = cases[0]
    backtest_cases: list[dict[str, object]] = []
    for fixture_name, frame in (
        ("baseline", baseline_frame),
        ("reversal-and-flat", reversal_frame),
        ("parameterized-longer-series", parameterized_frame),
    ):
        backtest_cases.extend(_backtest_reference_cases(frame, fixture_name))
    live_signal_cases = [
        _live_signal_case_payload("rsi-buy", baseline_frame, "rsi", {"buy_value": 1_000_000.0}),
        _live_signal_case_payload(
            "rsi-both-buy",
            baseline_frame,
            "rsi",
            {"buy_value": 1_000_000.0},
            side="BOTH",
        ),
        _live_signal_case_payload(
            "rsi-buy-blocked-by-sell-side",
            baseline_frame,
            "rsi",
            {"buy_value": 1_000_000.0, "sell_value": 1_000_000.0},
            side="SELL",
        ),
        _live_signal_case_payload(
            "rsi-sell-blocked-by-buy-side",
            baseline_frame,
            "rsi",
            {"buy_value": -1_000_000.0, "sell_value": -1_000_000.0},
            side="BUY",
        ),
        _live_signal_case_payload(
            "rsi-zero-threshold-uses-python-default",
            threshold_zero_frame,
            "rsi",
            {"buy_value": 0.0, "sell_value": 1_000_000.0},
        ),
        _live_signal_case_payload(
            "stoch-rsi-buy", baseline_frame, "stoch_rsi", {"buy_value": 1_000_000.0}
        ),
        _live_signal_case_payload("willr-buy", baseline_frame, "willr", {"buy_value": 0.0}),
        _live_signal_case_payload("natr-buy", baseline_frame, "natr", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("mfi-buy", baseline_frame, "mfi", {"buy_value": 1_000_000.0}),
        _live_signal_case_payload(
            "mfi-zero-threshold-uses-python-default",
            mfi_threshold_frame,
            "mfi",
            {"buy_value": -1_000_000.0, "sell_value": 0.0},
            side="SELL",
        ),
        _live_signal_case_payload("obv-buy", baseline_frame, "obv", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("rvol-buy", baseline_frame, "rvol", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("cmf-buy", baseline_frame, "cmf", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("cci-buy", baseline_frame, "cci", {"buy_value": 1_000_000.0}),
        _live_signal_case_payload("roc-buy", baseline_frame, "roc", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("trix-buy", baseline_frame, "trix", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("bbw-buy", baseline_frame, "bbw", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("ppo-buy", baseline_frame, "ppo", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("ao-buy", baseline_frame, "ao", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("kst-buy", baseline_frame, "kst", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("aroon-buy", baseline_frame, "aroon", {"buy_value": -1_000_000.0}),
        _live_signal_case_payload("chop-buy", baseline_frame, "chop", {"buy_value": 1_000_000.0}),
        _live_signal_case_payload("ma-buy", baseline_frame, "ma", {}),
        _live_signal_case_payload(
            "ichimoku-buy", baseline_frame, "ichimoku", {"buy_value": -1_000_000.0}
        ),
        _live_signal_case_payload("rsi-sell", baseline_frame, "rsi", {"sell_value": -1_000_000.0}, side="SELL"),
        _live_signal_case_payload(
            "stoch-rsi-sell", baseline_frame, "stoch_rsi", {"sell_value": -1_000_000.0}, side="SELL"
        ),
        _live_signal_case_payload("willr-sell", baseline_frame, "willr", {"sell_value": -100.0}, side="SELL"),
        _live_signal_case_payload("natr-sell", baseline_frame, "natr", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("mfi-sell", baseline_frame, "mfi", {"sell_value": -1_000_000.0}, side="SELL"),
        _live_signal_case_payload("obv-sell", baseline_frame, "obv", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("rvol-sell", baseline_frame, "rvol", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("cmf-sell", baseline_frame, "cmf", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("cci-sell", baseline_frame, "cci", {"sell_value": -1_000_000.0}, side="SELL"),
        _live_signal_case_payload("roc-sell", baseline_frame, "roc", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("trix-sell", baseline_frame, "trix", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("bbw-sell", baseline_frame, "bbw", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("ppo-sell", baseline_frame, "ppo", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("ao-sell", baseline_frame, "ao", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("kst-sell", baseline_frame, "kst", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("aroon-sell", baseline_frame, "aroon", {"sell_value": 1_000_000.0}, side="SELL"),
        _live_signal_case_payload("chop-sell", baseline_frame, "chop", {"sell_value": -1_000_000.0}, side="SELL"),
        _live_signal_case_payload("ma-sell", reversal_frame, "ma", {}, side="SELL"),
        _live_signal_case_payload(
            "ichimoku-sell", baseline_frame, "ichimoku", {"sell_value": 1_000_000.0}, side="SELL"
        ),
        _live_signal_case_payload(
            "rsi-buy-closed", baseline_frame, "rsi", {"buy_value": 1_000_000.0}, use_live_values=False
        ),
        _live_signal_case_payload(
            "natr-buy-closed", baseline_frame, "natr", {"buy_value": -1_000_000.0}, use_live_values=False
        ),
    ]
    return {
        "python_source_contract_hash": native_python_source_contract_hash(),
        "candles": primary["candles"],
        "configs": primary["configs"],
        "expected": primary["expected"],
        "indicator_cases": cases,
        "backtest_cases": backtest_cases,
        "live_signal_cases": live_signal_cases,
    }


def render_rust_indicator_reference_module() -> str:
    payload = _contract_json(_indicator_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python indicator implementations.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#[rustfmt::skip]",
            f"pub const PYTHON_INDICATOR_REFERENCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
            "#[rustfmt::skip]",
            f"pub const PYTHON_INDICATOR_REFERENCE_JSON: &str = {_rust_string(payload)};",
            "",
        ]
    )


def render_cpp_indicator_reference_header() -> str:
    payload = _contract_json(_indicator_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python indicator implementations.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#pragma once",
            "",
            "#include <string_view>",
            "",
            "namespace PythonIndicatorReference {",
            "",
            (
                "inline constexpr std::string_view kPythonSourceContractHash = "
                f"{_cpp_string(native_python_source_contract_hash())};"
            ),
            "inline constexpr std::string_view kReferenceJson =",
            f"    {_cpp_string_view_literal(payload)};",
            "",
            "} // namespace PythonIndicatorReference",
            "",
        ]
    )


def render_rust_exchange_support_reference_module() -> str:
    payload = _contract_json(_exchange_support_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python exchange support resolution.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#[rustfmt::skip]",
            f"pub const PYTHON_EXCHANGE_SUPPORT_REFERENCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
            "#[rustfmt::skip]",
            f"pub const PYTHON_EXCHANGE_SUPPORT_REFERENCE_JSON: &str = {_rust_string(payload)};",
            "",
        ]
    )


def render_cpp_exchange_support_reference_header() -> str:
    payload = _contract_json(_exchange_support_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python exchange support resolution.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#pragma once",
            "",
            "#include <string_view>",
            "",
            "namespace PythonExchangeSupportReference {",
            "",
            (
                "inline constexpr std::string_view kPythonSourceContractHash = "
                f"{_cpp_string(native_python_source_contract_hash())};"
            ),
            "inline constexpr std::string_view kReferenceJson =",
            f"    {_cpp_string_view_literal(payload)};",
            "",
            "} // namespace PythonExchangeSupportReference",
            "",
        ]
    )


def render_rust_portfolio_reference_module() -> str:
    payload = _contract_json(_portfolio_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python position reconciliation behavior.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#[rustfmt::skip]",
            f"pub const PYTHON_PORTFOLIO_REFERENCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
            "#[rustfmt::skip]",
            f"pub const PYTHON_PORTFOLIO_REFERENCE_JSON: &str = {_rust_string(payload)};",
            "",
        ]
    )


def render_cpp_portfolio_reference_header() -> str:
    payload = _contract_json(_portfolio_reference_payload())
    return "\n".join(
        [
            "// This file is generated from Python position reconciliation behavior.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "#pragma once",
            "",
            "#include <string_view>",
            "",
            "namespace PythonPortfolioReference {",
            "",
            (
                "inline constexpr std::string_view kPythonSourceContractHash = "
                f"{_cpp_string(native_python_source_contract_hash())};"
            ),
            "inline constexpr std::string_view kReferenceJson =",
            f"    {_cpp_string_view_literal(payload)};",
            "",
            "} // namespace PythonPortfolioReference",
            "",
        ]
    )


def _domain_required_list(domain: dict[str, object], key: str) -> list[str]:
    return [str(item) for item in domain.get(key, [])]


def _domain_cpp_status(domain: dict[str, object]) -> str:
    required = _domain_required_list(domain, "cpp_required_before_full_parity")
    if bool(domain["cpp_full_parity"]) or not required:
        return "Complete"
    return "C++ missing: " + "; ".join(required)


def _domain_rust_status(domain: dict[str, object]) -> str:
    required = _domain_required_list(domain, "rust_required_before_full_parity")
    if bool(domain["rust_full_parity"]) or not required:
        return "Complete"
    return "Rust missing: " + "; ".join(required)


def _domain_required_before_full_parity(domain: dict[str, object]) -> str:
    cpp_required = (
        "Complete"
        if bool(domain["cpp_full_parity"])
        else "; ".join(_domain_required_list(domain, "cpp_required_before_full_parity"))
    )
    rust_required = (
        "Complete"
        if bool(domain["rust_full_parity"])
        else "; ".join(_domain_required_list(domain, "rust_required_before_full_parity"))
    )
    return f"C++: {cpp_required or 'Complete'} | Rust: {rust_required or 'Complete'}"


def _rust_parity_domains(domains: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonParityDomain {",
        "    pub key: &'static str,",
        "    pub title: &'static str,",
        "    pub python_surface: &'static str,",
        "    pub cpp_status: &'static str,",
        "    pub rust_status: &'static str,",
        "    pub required_before_full_parity: &'static str,",
        "    pub cpp_full_parity: bool,",
        "    pub rust_full_parity: bool,",
        "}",
        "",
        "pub const PYTHON_PARITY_DOMAINS: &[PythonParityDomain] = &[",
    ]
    for domain in domains:
        lines.extend(
            [
                "    PythonParityDomain {",
                f"        key: {_rust_string(domain['key'])},",
                f"        title: {_rust_string(domain['title'])},",
                f"        python_surface: {_rust_string(domain['python_surface'])},",
                f"        cpp_status: {_rust_string(_domain_cpp_status(domain))},",
                f"        rust_status: {_rust_string(_domain_rust_status(domain))},",
                (f"        required_before_full_parity: {_rust_string(_domain_required_before_full_parity(domain))},"),
                f"        cpp_full_parity: {_rust_bool(domain['cpp_full_parity'])},",
                f"        rust_full_parity: {_rust_bool(domain['rust_full_parity'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _cpp_parity_domains(domains: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonParityDomain {",
        "    std::string_view key;",
        "    std::string_view title;",
        "    std::string_view pythonSurface;",
        "    std::string_view cppStatus;",
        "    std::string_view rustStatus;",
        "    std::string_view requiredBeforeFullParity;",
        "    bool cppFullParity;",
        "    bool rustFullParity;",
        "};",
        "",
        f"inline constexpr std::array<PythonParityDomain, {len(domains)}> kPythonParityDomains = {{",
    ]
    for domain in domains:
        lines.append(
            "    PythonParityDomain{"
            f"{_cpp_string(domain['key'])}, "
            f"{_cpp_string(domain['title'])}, "
            f"{_cpp_string(domain['python_surface'])}, "
            f"{_cpp_string(_domain_cpp_status(domain))}, "
            f"{_cpp_string(_domain_rust_status(domain))}, "
            f"{_cpp_string(_domain_required_before_full_parity(domain))}, "
            f"{str(bool(domain['cpp_full_parity'])).lower()}, "
            f"{str(bool(domain['rust_full_parity'])).lower()}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _rust_service_routes(routes: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonServiceRoute {",
        "    pub name: &'static str,",
        "    pub path: &'static str,",
        "    pub methods: &'static [&'static str],",
        "}",
        "",
        "pub const PYTHON_SERVICE_ROUTES: &[PythonServiceRoute] = &[",
    ]
    for route in routes:
        methods = ", ".join(_rust_string(method) for method in route["methods"])
        lines.extend(
            [
                "    PythonServiceRoute {",
                f"        name: {_rust_string(route['name'])},",
                f"        path: {_rust_string(route['path'])},",
                f"        methods: &[{methods}],",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_service_route_schemas(schemas: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonServiceRouteSchema {",
        "    pub name: &'static str,",
        "    pub query_fields: &'static [&'static str],",
        "    pub request_fields: &'static [&'static str],",
        "    pub response_fields: &'static [&'static str],",
        "}",
        "",
        "pub const PYTHON_SERVICE_ROUTE_SCHEMAS: &[PythonServiceRouteSchema] = &[",
    ]
    for schema in schemas:
        query_fields = ", ".join(_rust_string(field) for field in schema["query_fields"])
        request_fields = ", ".join(_rust_string(field) for field in schema["request_fields"])
        response_fields = ", ".join(_rust_string(field) for field in schema["response_fields"])
        lines.extend(
            [
                "    PythonServiceRouteSchema {",
                f"        name: {_rust_string(schema['name'])},",
                f"        query_fields: &[{query_fields}],",
                f"        request_fields: &[{request_fields}],",
                f"        response_fields: &[{response_fields}],",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_indicator_catalog(indicators: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonIndicator {",
        "    pub key: &'static str,",
        "    pub display_name: &'static str,",
        "    pub default_enabled: bool,",
        "    pub runtime_config_json: &'static str,",
        "    pub backtest_config_json: &'static str,",
        "    pub runtime_output_keys: &'static [&'static str],",
        "}",
        "",
        "pub const PYTHON_INDICATOR_CATALOG: &[PythonIndicator] = &[",
    ]
    for indicator in indicators:
        runtime_output_keys = ", ".join(_rust_string(str(key)) for key in indicator["runtime_output_keys"])
        lines.extend(
            [
                "    PythonIndicator {",
                f"        key: {_rust_string(indicator['key'])},",
                f"        display_name: {_rust_string(indicator['display_name'])},",
                f"        default_enabled: {_rust_bool(indicator['default_enabled'])},",
                f"        runtime_config_json: {_rust_string(_contract_json(indicator['runtime_config']))},",
                f"        backtest_config_json: {_rust_string(_contract_json(indicator['backtest_config']))},",
                f"        runtime_output_keys: &[{runtime_output_keys}],",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_runtime_config_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonRuntimeConfigReferenceCase {",
        "    pub name: &'static str,",
        "    pub input_json: &'static str,",
        "    pub expected_json: &'static str,",
        "    pub valid: bool,",
        "    pub expected_error: &'static str,",
        "}",
        "",
        "pub const PYTHON_RUNTIME_CONFIG_REFERENCE_CASES: &[PythonRuntimeConfigReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonRuntimeConfigReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input_json: {_rust_string(_contract_json(case['input']))},",
                f"        expected_json: {_rust_string(_contract_json(case['expected']))},",
                f"        valid: {_rust_bool(bool(case['valid']))},",
                f"        expected_error: {_rust_string(case['expected_error'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_strategy_controls_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonStrategyControlsReferenceCase {",
        "    pub name: &'static str,",
        "    pub kind: &'static str,",
        "    pub input_json: &'static str,",
        "    pub expected_json: &'static str,",
        "}",
        "",
        "pub const PYTHON_STRATEGY_CONTROLS_REFERENCE_CASES: &[PythonStrategyControlsReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonStrategyControlsReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        kind: {_rust_string(case['kind'])},",
                f"        input_json: {_rust_string(_contract_json(case['input']))},",
                f"        expected_json: {_rust_string(_contract_json(case['expected']))},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_strategy_risk_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonStrategyRiskReferenceCase {",
        "    pub name: &'static str,",
        "    pub input_json: &'static str,",
        "    pub expected_json: &'static str,",
        "}",
        "",
        "pub const PYTHON_STRATEGY_RISK_REFERENCE_CASES: &[PythonStrategyRiskReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonStrategyRiskReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input_json: {_rust_string(_contract_json(case['input']))},",
                f"        expected_json: {_rust_string(_contract_json(case['expected']))},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_strategy_risk_loose_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "pub const PYTHON_STRATEGY_RISK_LOOSE_REFERENCE_CASES: &[PythonStrategyRiskReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonStrategyRiskReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input_json: {_rust_string(_contract_json(case['input']))},",
                f"        expected_json: {_rust_string(_contract_json(case['expected']))},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_connector_normalization_reference_cases(cases: list[dict[str, str]]) -> str:
    lines = [
        "pub struct PythonConnectorNormalizationReferenceCase {",
        "    pub name: &'static str,",
        "    pub input: &'static str,",
        "    pub expected: &'static str,",
        "}",
        "",
        "pub const PYTHON_CONNECTOR_NORMALIZATION_REFERENCE_CASES: &[PythonConnectorNormalizationReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonConnectorNormalizationReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input: {_rust_string(case['input'])},",
                f"        expected: {_rust_string(case['expected'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_native_runtime_connector_ownership_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "pub struct PythonNativeRuntimeConnectorOwnershipReferenceCase {",
        "    pub name: &'static str,",
        "    pub input: &'static str,",
        "    pub expected_owned: bool,",
        "}",
        "",
        "pub const PYTHON_NATIVE_RUNTIME_CONNECTOR_OWNERSHIP_REFERENCE_CASES: &[PythonNativeRuntimeConnectorOwnershipReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonNativeRuntimeConnectorOwnershipReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input: {_rust_string(case['input'])},",
                f"        expected_owned: {_rust_bool(case['expected_owned'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_native_runtime_routing_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "pub struct PythonNativeRuntimeRoutingReferenceCase {",
        "    pub name: &'static str,",
        "    pub selected_exchange: &'static str,",
        "    pub connector_backend: &'static str,",
        "    pub indicator_source: &'static str,",
        "    pub expected_owned: bool,",
        "}",
        "",
        "pub const PYTHON_NATIVE_RUNTIME_ROUTING_REFERENCE_CASES: &[PythonNativeRuntimeRoutingReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonNativeRuntimeRoutingReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        selected_exchange: {_rust_string(case['selected_exchange'])},",
                f"        connector_backend: {_rust_string(case['connector_backend'])},",
                f"        indicator_source: {_rust_string(case['indicator_source'])},",
                f"        expected_owned: {_rust_bool(case['expected_owned'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_native_runtime_mode_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "pub struct PythonNativeRuntimeModeReferenceCase {",
        "    pub name: &'static str,",
        "    pub input: &'static str,",
        "    pub expected_testnet: bool,",
        "}",
        "",
        "pub const PYTHON_NATIVE_RUNTIME_MODE_REFERENCE_CASES: &[PythonNativeRuntimeModeReferenceCase] = &[",
    ]
    for case in cases:
        lines.extend(
            [
                "    PythonNativeRuntimeModeReferenceCase {",
                f"        name: {_rust_string(case['name'])},",
                f"        input: {_rust_string(case['input'])},",
                f"        expected_testnet: {_rust_bool(case['expected_testnet'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_connector_options(connectors: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonConnectorOption {",
        "    pub key: &'static str,",
        "    pub label: &'static str,",
        "}",
        "",
        "pub const PYTHON_CONNECTOR_OPTIONS: &[PythonConnectorOption] = &[",
    ]
    for connector in connectors:
        lines.extend(
            [
                "    PythonConnectorOption {",
                f"        key: {_rust_string(connector['key'])},",
                f"        label: {_rust_string(connector['label'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_environment_dependencies(dependencies: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonRustEnvironmentDependency {",
        "    pub key: &'static str,",
        "    pub label: &'static str,",
        "    pub kind: &'static str,",
        "    pub path: &'static str,",
        "    pub latest: &'static str,",
        "    pub usage: &'static str,",
        "}",
        "",
        "pub const PYTHON_RUST_ENVIRONMENT_DEPENDENCIES: &[PythonRustEnvironmentDependency] = &[",
    ]
    for dependency in dependencies:
        lines.extend(
            [
                "    PythonRustEnvironmentDependency {",
                f"        key: {_rust_string(dependency['key'])},",
                f"        label: {_rust_string(dependency['label'])},",
                f"        kind: {_rust_string(dependency['kind'])},",
                f"        path: {_rust_string(dependency['path'])},",
                f"        latest: {_rust_string(dependency['latest'])},",
                f"        usage: {_rust_string(dependency['usage'])},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_llm_providers(providers: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonLlmProvider {",
        "    pub key: &'static str,",
        "    pub label: &'static str,",
        "    pub mode: &'static str,",
        "    pub protocol: &'static str,",
        "    pub default_base_url: &'static str,",
        "    pub default_model: &'static str,",
        "    pub api_key_env: &'static str,",
        "    pub model_suggestions: &'static [&'static str],",
        "    pub reasoning_efforts: &'static [&'static str],",
        "    pub default_reasoning_effort: &'static str,",
        "    pub catalog_revision: &'static str,",
        "    pub custom_models_env: &'static str,",
        "    pub custom_models_path_env: &'static str,",
        "    pub notes: &'static [&'static str],",
        "}",
        "",
        "pub const PYTHON_LLM_PROVIDERS: &[PythonLlmProvider] = &[",
    ]
    for provider in providers:
        models = ", ".join(_rust_string(model) for model in provider["model_suggestions"])
        efforts = ", ".join(_rust_string(effort) for effort in provider["reasoning_efforts"])
        notes = ", ".join(_rust_string(note) for note in provider.get("notes", []))
        lines.extend(
            [
                "    PythonLlmProvider {",
                f"        key: {_rust_string(provider['key'])},",
                f"        label: {_rust_string(provider['label'])},",
                f"        mode: {_rust_string(provider['mode'])},",
                f"        protocol: {_rust_string(provider['protocol'])},",
                f"        default_base_url: {_rust_string(provider['default_base_url'])},",
                f"        default_model: {_rust_string(provider['default_model'])},",
                f"        api_key_env: {_rust_string(provider['api_key_env'])},",
                f"        model_suggestions: &[{models}],",
                f"        reasoning_efforts: &[{efforts}],",
                f"        default_reasoning_effort: {_rust_string(provider['default_reasoning_effort'])},",
                f"        catalog_revision: {_rust_string(provider['catalog_revision'])},",
                f"        custom_models_env: {_rust_string(provider['custom_models_env'])},",
                f"        custom_models_path_env: {_rust_string(provider['custom_models_path_env'])},",
                f"        notes: &[{notes}],",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _rust_ollama_model_size_hints(hints: list[dict[str, object]]) -> str:
    lines = [
        "pub struct PythonOllamaModelSizeHint {",
        "    pub model: &'static str,",
        "    pub label: &'static str,",
        "    pub size_gb: Option<f64>,",
        "}",
        "",
        "pub const PYTHON_OLLAMA_MODEL_SIZE_HINTS: &[PythonOllamaModelSizeHint] = &[",
    ]
    for hint in hints:
        size_gb = hint.get("size_gb")
        if size_gb is None:
            rust_size = "None"
        else:
            numeric_size = f"{float(size_gb):.12g}"
            if "." not in numeric_size and "e" not in numeric_size.lower():
                numeric_size += ".0"
            rust_size = f"Some({numeric_size})"
        lines.extend(
            [
                "    PythonOllamaModelSizeHint {",
                f"        model: {_rust_string(hint['model'])},",
                f"        label: {_rust_string(hint['label'])},",
                f"        size_gb: {rust_size},",
                "    },",
            ]
        )
    lines.append("];" )
    return "\n".join(lines)


def _rust_llm_provider_choices(choices: list[dict[str, object]]) -> str:
    lines = ["pub const PYTHON_LLM_PROVIDER_CHOICES: &[(&str, &str)] = &["]
    lines.extend(
        f"    ({_rust_string(choice['key'])}, {_rust_string(choice['value'])}),"
        for choice in choices
    )
    lines.append("];")
    return "\n".join(lines)


def _config_choice_suffix(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _rust_config_choice_maps(choice_maps: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []
    for name, choices in choice_maps.items():
        constant = f"PYTHON_{name.upper()}_CONFIG_CHOICES"
        lines.extend(
            [
                f"pub const {constant}: &[(&str, &str)] = &[",
                *(
                    f"    ({_rust_string(key)}, {_rust_string(value)}),"
                    for key, value in choices.items()
                ),
                "];",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _ui_option_key(option: dict[str, object]) -> str:
    return str(option.get("key", option.get("value", "")))


def _python_option_catalog_counts() -> tuple[int, int]:
    option_catalogs = dict(native_python_source_contract_payload()["ui_options"])
    return len(option_catalogs), sum(
        len(value) if isinstance(value, (dict, list, tuple)) else 1
        for value in option_catalogs.values()
    )


def _python_option_catalog_manifest() -> list[tuple[str, int]]:
    """Return every Python option catalog name with its source entry count."""
    option_catalogs = dict(native_python_source_contract_payload()["ui_options"])
    return [
        (
            str(name),
            len(value) if isinstance(value, (dict, list, tuple)) else 1,
        )
        for name, value in option_catalogs.items()
    ]


def _python_option_catalog_json() -> str:
    """Return the canonical serialized Python option-catalog payload."""
    return _contract_json(dict(native_python_source_contract_payload()["ui_options"]))


def _ui_option_catalog_specs(summary: dict[str, object]) -> list[tuple[str, str, str, list[dict[str, object]]]]:
    return [
        ("dashboard loop", "PYTHON_DASHBOARD_LOOP_CHOICES", "kPythonDashboardLoopChoices", list(summary["dashboard_loop_choices"])),
        ("lead trader", "PYTHON_LEAD_TRADER_OPTIONS", "kPythonLeadTraderOptions", list(summary["lead_trader_options"])),
        ("LLM use-for", "PYTHON_LLM_USE_FOR_OPTIONS", "kPythonLlmUseForOptions", list(summary["llm_use_for_options"])),
        (
            "LLM reasoning effort",
            "PYTHON_LLM_REASONING_EFFORT_OPTIONS",
            "kPythonLlmReasoningEffortOptions",
            list(summary["llm_reasoning_effort_options"]),
        ),
        (
            "position percentage units",
            "PYTHON_POSITION_PCT_UNITS_OPTIONS",
            "kPythonPositionPctUnitsOptions",
            list(summary["position_pct_units_options"]),
        ),
        (
            "dashboard strategy templates",
            "PYTHON_DASHBOARD_STRATEGY_TEMPLATES",
            "kPythonDashboardStrategyTemplates",
            list(summary["dashboard_strategy_templates"]),
        ),
        ("backtest templates", "PYTHON_BACKTEST_TEMPLATES", "kPythonBacktestTemplates", list(summary["backtest_templates"])),
        ("side", "PYTHON_SIDE_OPTIONS", "kPythonSideOptions", list(summary["side_options"])),
        ("config mode", "PYTHON_CONFIG_MODE_OPTIONS", "kPythonConfigModeOptions", list(summary["config_mode_options"])),
        ("theme", "PYTHON_THEME_OPTIONS", "kPythonThemeOptions", list(summary["theme_options"])),
        ("design", "PYTHON_DESIGN_OPTIONS", "kPythonDesignOptions", list(summary["design_options"])),
        (
            "indicator source",
            "PYTHON_INDICATOR_SOURCE_OPTIONS",
            "kPythonIndicatorSourceOptions",
            list(summary["indicator_source_options"]),
        ),
        (
            "moving average type",
            "PYTHON_INDICATOR_MA_TYPE_OPTIONS",
            "kPythonIndicatorMaTypeOptions",
            list(summary["indicator_ma_type_options"]),
        ),
        ("exchange", "PYTHON_EXCHANGE_OPTIONS", "kPythonExchangeOptions", list(summary["exchange_options"])),
        ("account type", "PYTHON_ACCOUNT_TYPE_OPTIONS", "kPythonAccountTypeOptions", list(summary["account_type_options"])),
        ("margin mode", "PYTHON_MARGIN_MODE_OPTIONS", "kPythonMarginModeOptions", list(summary["margin_mode_options"])),
        ("position mode", "PYTHON_POSITION_MODE_OPTIONS", "kPythonPositionModeOptions", list(summary["position_mode_options"])),
        ("assets mode", "PYTHON_ASSETS_MODE_OPTIONS", "kPythonAssetsModeOptions", list(summary["assets_mode_options"])),
        ("order type", "PYTHON_ORDER_TYPE_OPTIONS", "kPythonOrderTypeOptions", list(summary["order_type_options"])),
        (
            "time in force",
            "PYTHON_TIME_IN_FORCE_OPTIONS",
            "kPythonTimeInForceOptions",
            list(summary["time_in_force_options"]),
        ),
        ("signal logic", "PYTHON_SIGNAL_LOGIC_OPTIONS", "kPythonSignalLogicOptions", list(summary["signal_logic_options"])),
        ("MDD logic", "PYTHON_MDD_LOGIC_OPTIONS", "kPythonMddLogicOptions", list(summary["mdd_logic_options"])),
        ("stop-loss modes", "PYTHON_STOP_LOSS_MODES", "kPythonStopLossModes", list(summary["stop_loss_modes"])),
        ("stop-loss scopes", "PYTHON_STOP_LOSS_SCOPES", "kPythonStopLossScopes", list(summary["stop_loss_scopes"])),
        ("scan scope", "PYTHON_SCAN_SCOPE_OPTIONS", "kPythonScanScopeOptions", list(summary["scan_scope_options"])),
        ("optimizer mode", "PYTHON_OPTIMIZER_MODE_OPTIONS", "kPythonOptimizerModeOptions", list(summary["optimizer_mode_options"])),
        (
            "optimizer metric",
            "PYTHON_OPTIMIZER_METRIC_OPTIONS",
            "kPythonOptimizerMetricOptions",
            list(summary["optimizer_metric_options"]),
        ),
        (
            "backtest execution backend",
            "PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS",
            "kPythonBacktestExecutionBackendOptions",
            list(summary["backtest_execution_backend_options"]),
        ),
        ("chart view", "PYTHON_CHART_VIEW_OPTIONS", "kPythonChartViewOptions", list(summary["chart_view_options"])),
        ("positions view", "PYTHON_POSITIONS_VIEW_OPTIONS", "kPythonPositionsViewOptions", list(summary["positions_view_options"])),
    ]


def _rust_ui_option_catalogs(summary: dict[str, object]) -> str:
    specs = _ui_option_catalog_specs(summary)
    option_catalog_manifest = _python_option_catalog_manifest()
    option_catalog_count = len(option_catalog_manifest)
    option_catalog_entry_count = sum(entry_count for _, entry_count in option_catalog_manifest)
    ui_option_entry_count = sum(len(options) for _, _, _, options in specs)
    option_groups = [(rust_name, options) for _, rust_name, _, options in specs]
    lines = [
        f"pub const PYTHON_OPTION_CATALOG_COUNT: usize = {option_catalog_count};",
        f"pub const PYTHON_OPTION_CATALOG_ENTRY_COUNT: usize = {option_catalog_entry_count};",
        f"pub const PYTHON_UI_OPTION_CATALOG_COUNT: usize = {len(specs)};",
        f"pub const PYTHON_UI_OPTION_ENTRY_COUNT: usize = {ui_option_entry_count};",
        "",
        "pub struct PythonOptionCatalogManifestEntry {",
        "    pub name: &'static str,",
        "    pub entry_count: usize,",
        "}",
        "",
        "pub const PYTHON_OPTION_CATALOG_MANIFEST: &[PythonOptionCatalogManifestEntry] = &[",
    ]
    lines.extend(
        "    PythonOptionCatalogManifestEntry {"
        f" name: {_rust_string(name)}, entry_count: {entry_count} }},"
        for name, entry_count in option_catalog_manifest
    )
    lines.extend(
        [
            "];",
            "",
            "pub struct PythonUiOption {",
            "    pub key: &'static str,",
            "    pub label: &'static str,",
            "    pub disabled: bool,",
            "}",
        ]
    )
    for name, options in option_groups:
        lines.extend(["", f"pub const {name}: &[PythonUiOption] = &["])
        for option in options:
            lines.extend(
                [
                    "    PythonUiOption {",
                    f"        key: {_rust_string(_ui_option_key(option))},",
                    f"        label: {_rust_string(option['label'])},",
                    f"        disabled: {_rust_bool(bool(option.get('disabled', False)))},",
                    "    },",
                ]
            )
        lines.append("];")
    lines.extend(
        [
            "",
            "pub struct PythonUiOptionCatalog {",
            "    pub name: &'static str,",
            "    pub options: &'static [PythonUiOption],",
            "}",
            "",
            "pub const PYTHON_UI_OPTION_CATALOGS: &[PythonUiOptionCatalog] = &[",
        ]
    )
    lines.extend(
        f'    PythonUiOptionCatalog {{ name: {_rust_string(label)}, options: {rust_name} }},'
        for label, rust_name, _, _ in specs
    )
    lines.append("];" )
    return "\n".join(lines)


def _rust_starter_catalogs(summary: dict[str, object]) -> str:
    option_groups = [
        ("PYTHON_CODE_LANGUAGE_OPTIONS", list(summary["code_language_options"])),
        ("PYTHON_RUST_FRAMEWORK_OPTIONS", list(summary["rust_framework_options"])),
        ("PYTHON_STARTER_MARKET_OPTIONS", list(summary["starter_market_options"])),
    ]
    lines = [
        "pub struct PythonStarterOption {",
        "    pub key: &'static str,",
        "    pub title: &'static str,",
        "    pub subtitle: &'static str,",
        "    pub accent: &'static str,",
        "    pub badge: &'static str,",
        "    pub disabled: bool,",
        "    pub operational: bool,",
        "    pub operational_status: &'static str,",
        "    pub launch_note: &'static str,",
        "}",
    ]
    for name, options in option_groups:
        lines.extend(["", f"pub const {name}: &[PythonStarterOption] = &["])
        for option in options:
            lines.extend(
                [
                    "    PythonStarterOption {",
                    f"        key: {_rust_string(option['key'])},",
                    f"        title: {_rust_string(option['title'])},",
                    f"        subtitle: {_rust_string(option['subtitle'])},",
                    f"        accent: {_rust_string(option['accent'])},",
                    f"        badge: {_rust_string(option['badge'])},",
                    f"        disabled: {_rust_bool(option['disabled'])},",
                    f"        operational: {_rust_bool(option['operational'])},",
                    f"        operational_status: {_rust_string(option['operational_status'])},",
                    f"        launch_note: {_rust_string(option['launch_note'])},",
                    "    },",
                ]
            )
        lines.append("];")
    return "\n".join(lines)


def _rust_tradingview_interval_map(interval_map: dict[str, object]) -> str:
    lines = [
        "pub struct PythonTradingViewInterval {",
        "    pub interval: &'static str,",
        "    pub code: &'static str,",
        "}",
        "",
        "pub const PYTHON_TRADINGVIEW_INTERVAL_MAP: &[PythonTradingViewInterval] = &[",
    ]
    for interval, code in interval_map.items():
        lines.extend(
            [
                "    PythonTradingViewInterval {",
                f"        interval: {_rust_string(interval)},",
                f"        code: {_rust_string(code)},",
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _cpp_service_routes(routes: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonServiceRoute {",
        "    std::string_view name;",
        "    std::string_view path;",
        "    std::string_view methods;",
        "};",
        "",
        f"inline constexpr std::array<PythonServiceRoute, {len(routes)}> kPythonServiceRoutes = {{",
    ]
    for route in routes:
        methods = ",".join(str(method) for method in route["methods"])
        lines.append(
            "    PythonServiceRoute{"
            f"{_cpp_string(route['name'])}, {_cpp_string(route['path'])}, {_cpp_string(methods)}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_service_route_schemas(schemas: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonServiceRouteSchema {",
        "    std::string_view name;",
        "    std::string_view queryFields;",
        "    std::string_view requestFields;",
        "    std::string_view responseFields;",
        "};",
        "",
        f"inline constexpr std::array<PythonServiceRouteSchema, {len(schemas)}> kPythonServiceRouteSchemas = {{",
    ]
    for schema in schemas:
        query_fields = ",".join(str(field) for field in schema["query_fields"])
        request_fields = ",".join(str(field) for field in schema["request_fields"])
        response_fields = ",".join(str(field) for field in schema["response_fields"])
        lines.append(
            "    PythonServiceRouteSchema{"
            f"{_cpp_string(schema['name'])}, "
            f"{_cpp_string(query_fields)}, "
            f"{_cpp_string(request_fields)}, "
            f"{_cpp_string(response_fields)}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_indicator_catalog(indicators: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonIndicator {",
        "    std::string_view key;",
        "    std::string_view displayName;",
        "    bool defaultEnabled;",
        "    std::string_view runtimeConfigJson;",
        "    std::string_view backtestConfigJson;",
        "    std::string_view runtimeOutputKeysCsv;",
        "};",
        "",
        f"inline constexpr std::array<PythonIndicator, {len(indicators)}> kPythonIndicatorCatalog = {{",
    ]
    for indicator in indicators:
        runtime_output_keys = ",".join(str(key) for key in indicator["runtime_output_keys"])
        lines.append(
            "    PythonIndicator{"
            f"{_cpp_string(indicator['key'])}, "
            f"{_cpp_string(indicator['display_name'])}, "
            f"{str(bool(indicator['default_enabled'])).lower()}, "
            f"{_cpp_string(_contract_json(indicator['runtime_config']))}, "
            f"{_cpp_string(_contract_json(indicator['backtest_config']))}, "
            f"{_cpp_string(runtime_output_keys)}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_runtime_config_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonRuntimeConfigReferenceCase {",
        "    std::string_view name;",
        "    std::string_view inputJson;",
        "    std::string_view expectedJson;",
        "    bool valid;",
        "    std::string_view expectedError;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonRuntimeConfigReferenceCase, "
            f"{len(cases)}> kPythonRuntimeConfigReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonRuntimeConfigReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(_contract_json(case['input']))}, "
            f"{_cpp_string(_contract_json(case['expected']))}, "
            f"{str(bool(case['valid'])).lower()}, "
            f"{_cpp_string(case['expected_error'])}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_strategy_controls_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonStrategyControlsReferenceCase {",
        "    std::string_view name;",
        "    std::string_view kind;",
        "    std::string_view inputJson;",
        "    std::string_view expectedJson;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonStrategyControlsReferenceCase, "
            f"{len(cases)}> kPythonStrategyControlsReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonStrategyControlsReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(case['kind'])}, "
            f"{_cpp_string(_contract_json(case['input']))}, "
            f"{_cpp_string(_contract_json(case['expected']))}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_strategy_risk_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonStrategyRiskReferenceCase {",
        "    std::string_view name;",
        "    std::string_view inputJson;",
        "    std::string_view expectedJson;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonStrategyRiskReferenceCase, "
            f"{len(cases)}> kPythonStrategyRiskReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonStrategyRiskReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(_contract_json(case['input']))}, "
            f"{_cpp_string(_contract_json(case['expected']))}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_strategy_risk_loose_reference_cases(cases: list[dict[str, object]]) -> str:
    lines = [
        (
            "inline constexpr std::array<PythonStrategyRiskReferenceCase, "
            f"{len(cases)}> kPythonStrategyRiskLooseReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonStrategyRiskReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(_contract_json(case['input']))}, "
            f"{_cpp_string(_contract_json(case['expected']))}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_connector_normalization_reference_cases(cases: list[dict[str, str]]) -> str:
    lines = [
        "struct PythonConnectorNormalizationReferenceCase {",
        "    std::string_view name;",
        "    std::string_view input;",
        "    std::string_view expected;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonConnectorNormalizationReferenceCase, "
            f"{len(cases)}> kPythonConnectorNormalizationReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonConnectorNormalizationReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(case['input'])}, "
            f"{_cpp_string(case['expected'])}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_native_runtime_connector_ownership_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "struct PythonNativeRuntimeConnectorOwnershipReferenceCase {",
        "    std::string_view name;",
        "    std::string_view input;",
        "    bool expectedOwned;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonNativeRuntimeConnectorOwnershipReferenceCase, "
            f"{len(cases)}> kPythonNativeRuntimeConnectorOwnershipReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonNativeRuntimeConnectorOwnershipReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(case['input'])}, "
            f"{str(bool(case['expected_owned'])).lower()}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_native_runtime_routing_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "struct PythonNativeRuntimeRoutingReferenceCase {",
        "    std::string_view name;",
        "    std::string_view selectedExchange;",
        "    std::string_view connectorBackend;",
        "    std::string_view indicatorSource;",
        "    bool expectedOwned;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonNativeRuntimeRoutingReferenceCase, "
            f"{len(cases)}> kPythonNativeRuntimeRoutingReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonNativeRuntimeRoutingReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(case['selected_exchange'])}, "
            f"{_cpp_string(case['connector_backend'])}, "
            f"{_cpp_string(case['indicator_source'])}, "
            f"{str(bool(case['expected_owned'])).lower()}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_native_runtime_mode_reference_cases(
    cases: list[dict[str, object]],
) -> str:
    lines = [
        "struct PythonNativeRuntimeModeReferenceCase {",
        "    std::string_view name;",
        "    std::string_view input;",
        "    bool expectedTestnet;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonNativeRuntimeModeReferenceCase, "
            f"{len(cases)}> kPythonNativeRuntimeModeReferenceCases = {{"
        ),
    ]
    for case in cases:
        lines.append(
            "    PythonNativeRuntimeModeReferenceCase{"
            f"{_cpp_string(case['name'])}, "
            f"{_cpp_string(case['input'])}, "
            f"{str(bool(case['expected_testnet'])).lower()}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_connector_options(connectors: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonConnectorOption {",
        "    std::string_view key;",
        "    std::string_view label;",
        "};",
        "",
        f"inline constexpr std::array<PythonConnectorOption, {len(connectors)}> kPythonConnectorOptions = {{",
    ]
    for connector in connectors:
        lines.append(
            f"    PythonConnectorOption{{{_cpp_string(connector['key'])}, {_cpp_string(connector['label'])}}},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_llm_providers(providers: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonLlmProvider {",
        "    std::string_view key;",
        "    std::string_view label;",
        "    std::string_view mode;",
        "    std::string_view protocol;",
        "    std::string_view defaultBaseUrl;",
        "    std::string_view defaultModel;",
        "    std::string_view apiKeyEnv;",
        "    std::string_view modelSuggestions;",
        "    std::string_view reasoningEfforts;",
        "    std::string_view defaultReasoningEffort;",
        "    std::string_view catalogRevision;",
        "    std::string_view customModelsEnv;",
        "    std::string_view customModelsPathEnv;",
        "    std::string_view notes;",
        "};",
        "",
        f"inline constexpr std::array<PythonLlmProvider, {len(providers)}> kPythonLlmProviders = {{",
    ]
    for provider in providers:
        models = ",".join(str(model) for model in provider["model_suggestions"])
        efforts = ",".join(str(effort) for effort in provider["reasoning_efforts"])
        notes = "\n".join(str(note) for note in provider.get("notes", []))
        lines.append(
            "    PythonLlmProvider{"
            f"{_cpp_string(provider['key'])}, "
            f"{_cpp_string(provider['label'])}, "
            f"{_cpp_string(provider['mode'])}, "
            f"{_cpp_string(provider['protocol'])}, "
            f"{_cpp_string(provider['default_base_url'])}, "
            f"{_cpp_string(provider['default_model'])}, "
            f"{_cpp_string(provider['api_key_env'])}, "
            f"{_cpp_string(models)}, "
            f"{_cpp_string(efforts)}, "
            f"{_cpp_string(provider['default_reasoning_effort'])}, "
            f"{_cpp_string(provider['catalog_revision'])}, "
            f"{_cpp_string(provider['custom_models_env'])}, "
            f"{_cpp_string(provider['custom_models_path_env'])}, "
            f"{_cpp_string(notes)}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_ollama_model_size_hints(hints: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonOllamaModelSizeHint {",
        "    std::string_view model;",
        "    std::string_view label;",
        "    double sizeGb;",
        "    bool hasSizeGb;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonOllamaModelSizeHint, "
            f"{len(hints)}> kPythonOllamaModelSizeHints = {{"
        ),
    ]
    for hint in hints:
        size_gb = hint.get("size_gb")
        cpp_size = "0.0" if size_gb is None else f"{float(size_gb):.12g}"
        has_size = "false" if size_gb is None else "true"
        lines.append(
            "    PythonOllamaModelSizeHint{"
            f"{_cpp_string(hint['model'])}, "
            f"{_cpp_string(hint['label'])}, {cpp_size}, {has_size}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_llm_provider_choices(choices: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonLlmProviderChoice {",
        "    std::string_view key;",
        "    std::string_view value;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonLlmProviderChoice, "
            f"{len(choices)}> kPythonLlmProviderChoices = {{"
        ),
    ]
    lines.extend(
        f"    PythonLlmProviderChoice{{{_cpp_string(choice['key'])}, {_cpp_string(choice['value'])}}},"
        for choice in choices
    )
    lines.append("};")
    return "\n".join(lines)


def _cpp_config_choice_maps(choice_maps: dict[str, dict[str, str]]) -> str:
    lines = [
        "struct PythonConfigChoice {",
        "    std::string_view key;",
        "    std::string_view value;",
        "};",
        "",
    ]
    for name, choices in choice_maps.items():
        constant = f"kPython{_config_choice_suffix(name)}ConfigChoices"
        lines.append(
            f"inline constexpr std::array<PythonConfigChoice, {len(choices)}> {constant} = {{"
        )
        lines.extend(
            f"    PythonConfigChoice{{{_cpp_string(key)}, {_cpp_string(value)}}},"
            for key, value in choices.items()
        )
        lines.extend(["};", ""])
    return "\n".join(lines).rstrip()


def _cpp_ui_option_catalogs(summary: dict[str, object]) -> str:
    specs = _ui_option_catalog_specs(summary)
    option_catalog_manifest = _python_option_catalog_manifest()
    option_catalog_count = len(option_catalog_manifest)
    option_catalog_entry_count = sum(entry_count for _, entry_count in option_catalog_manifest)
    ui_option_entry_count = sum(len(options) for _, _, _, options in specs)
    option_groups = [(cpp_name, options) for _, _, cpp_name, options in specs]
    lines = [
        f"inline constexpr std::size_t kPythonOptionCatalogCount = {option_catalog_count};",
        f"inline constexpr std::size_t kPythonOptionCatalogEntryCount = {option_catalog_entry_count};",
        f"inline constexpr std::size_t kPythonUiOptionCatalogCount = {len(specs)};",
        f"inline constexpr std::size_t kPythonUiOptionEntryCount = {ui_option_entry_count};",
        "",
        "struct PythonOptionCatalogManifestEntry {",
        "    std::string_view name;",
        "    std::size_t entryCount;",
        "};",
        "",
        "inline constexpr std::array<PythonOptionCatalogManifestEntry, "
        f"{len(option_catalog_manifest)}> kPythonOptionCatalogManifest = {{",
    ]
    lines.extend(
        "    PythonOptionCatalogManifestEntry{"
        f"{_cpp_string(name)}, {entry_count} }},"
        for name, entry_count in option_catalog_manifest
    )
    lines.extend(
        [
            "};",
            "",
            "struct PythonUiOption {",
            "    std::string_view key;",
            "    std::string_view label;",
            "    bool disabled;",
            "};",
        ]
    )
    for name, options in option_groups:
        lines.extend(["", f"inline constexpr std::array<PythonUiOption, {len(options)}> {name} = {{"])
        for option in options:
            lines.append(
                "    PythonUiOption{"
                f"{_cpp_string(_ui_option_key(option))}, {_cpp_string(option['label'])}, "
                f"{str(bool(option.get('disabled', False))).lower()}"
                "},"
            )
        lines.append("};")
    lines.extend(
        [
            "",
            "struct PythonUiOptionCatalog {",
            "    std::string_view name;",
            "    const PythonUiOption *options;",
            "    std::size_t size;",
            "};",
            "",
            "inline constexpr std::array<PythonUiOptionCatalog, "
            f"{len(specs)}> kPythonUiOptionCatalogs = {{",
        ]
    )
    lines.extend(
        "    PythonUiOptionCatalog{"
        f"{_cpp_string(label)}, {cpp_name}.data(), {cpp_name}.size()"
        "},"
        for label, _, cpp_name, _ in specs
    )
    lines.append("};")
    return "\n".join(lines)


def _cpp_starter_catalogs(summary: dict[str, object]) -> str:
    option_groups = [
        ("kPythonCodeLanguageOptions", list(summary["code_language_options"])),
        ("kPythonRustFrameworkOptions", list(summary["rust_framework_options"])),
        ("kPythonStarterMarketOptions", list(summary["starter_market_options"])),
    ]
    lines = [
        "struct PythonStarterOption {",
        "    std::string_view key;",
        "    std::string_view title;",
        "    std::string_view subtitle;",
        "    std::string_view accent;",
        "    std::string_view badge;",
        "    bool disabled;",
        "    bool operational;",
        "    std::string_view operationalStatus;",
        "    std::string_view launchNote;",
        "};",
    ]
    for name, options in option_groups:
        lines.extend(
            [
                "",
                f"inline constexpr std::array<PythonStarterOption, {len(options)}> {name} = {{",
            ]
        )
        for option in options:
            lines.append(
                "    PythonStarterOption{"
                f"{_cpp_string(option['key'])}, {_cpp_string(option['title'])}, "
                f"{_cpp_string(option['subtitle'])}, {_cpp_string(option['accent'])}, "
                f"{_cpp_string(option['badge'])}, {_rust_bool(option['disabled'])}, "
                f"{_rust_bool(option['operational'])}, {_cpp_string(option['operational_status'])}, "
                f"{_cpp_string(option['launch_note'])}"
                "},"
            )
        lines.append("};")
    return "\n".join(lines)


def _cpp_environment_dependencies(dependencies: list[dict[str, object]]) -> str:
    lines = [
        "struct PythonRustEnvironmentDependency {",
        "    std::string_view key;",
        "    std::string_view label;",
        "    std::string_view kind;",
        "    std::string_view path;",
        "    std::string_view latest;",
        "    std::string_view usage;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonRustEnvironmentDependency, "
            f"{len(dependencies)}> kPythonRustEnvironmentDependencies = {{"
        ),
    ]
    for dependency in dependencies:
        lines.append(
            "    PythonRustEnvironmentDependency{"
            f"{_cpp_string(dependency['key'])}, {_cpp_string(dependency['label'])}, "
            f"{_cpp_string(dependency['kind'])}, {_cpp_string(dependency['path'])}, "
            f"{_cpp_string(dependency['latest'])}, {_cpp_string(dependency['usage'])}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_tradingview_interval_map(interval_map: dict[str, object]) -> str:
    lines = [
        "struct PythonTradingViewInterval {",
        "    std::string_view interval;",
        "    std::string_view code;",
        "};",
        "",
        (
            "inline constexpr std::array<PythonTradingViewInterval, "
            f"{len(interval_map)}> kPythonTradingViewIntervalMap = {{"
        ),
    ]
    for interval, code in interval_map.items():
        lines.append(f"    PythonTradingViewInterval{{{_cpp_string(interval)}, {_cpp_string(code)}}},")
    lines.append("};")
    return "\n".join(lines)


def render_rust_module() -> str:
    summary = native_python_source_contract_summary()
    order_guard_behavior = dict(summary["order_guard_behavior"])
    live_safety_environment = dict(order_guard_behavior["live_safety_environment"])
    environment_bool_true_values = list(order_guard_behavior["environment_bool_true_values"])
    native_runtime_ownership = dict(summary["native_runtime_ownership"])
    indicator_source_market_families = list(native_runtime_ownership["indicator_source_market_families"])
    connector_market_families = list(native_runtime_ownership["direct_connector_market_families"])
    runtime_config_cases = _runtime_config_reference_cases()
    strategy_controls_cases = list(summary["strategy_controls_reference"])
    strategy_risk_cases = list(summary["strategy_risk_reference"])
    strategy_risk_loose_cases = list(summary["strategy_risk_loose_reference"])
    indicator_enabled_reference = list(summary["indicator_enabled_reference"])
    backtest_indicator_enabled_reference = list(summary["backtest_indicator_enabled_reference"])
    interval_seconds_reference = list(summary["interval_seconds_reference"])
    backtest_interval_seconds_reference = list(summary["backtest_interval_seconds_reference"])
    stop_intent_reference = dict(summary["stop_intent_reference"])
    stop_intent_loose_reference = dict(summary["stop_intent_loose_reference"])
    order_intent_reference = dict(summary["order_intent_reference"])
    live_safety_reference = dict(summary["live_safety_reference"])
    connector_health_reference = dict(summary["connector_health_reference"])
    llm_output_policy_reference = dict(summary["llm_output_policy_reference"])
    llm_chat_request_reference = dict(summary["llm_chat_request_reference"])
    connector_normalization_cases = _connector_normalization_reference_cases()
    connector_ownership_cases = list(summary["native_runtime_connector_ownership_reference"])
    routing_cases = list(summary["native_runtime_routing_reference"])
    routing_json_coercion_cases = list(summary["native_runtime_routing_json_coercion_reference"])
    mode_policy = dict(summary["native_runtime_mode_policy"])
    mode_reference_cases = list(summary["native_runtime_mode_reference"])
    option_catalog_json = _python_option_catalog_json()
    parts = [
        f"pub const PYTHON_SOURCE: &str = {_rust_string(summary['source'])};",
        f"pub const PYTHON_SOURCE_SCHEMA_VERSION: u32 = {int(summary['schema_version'])};",
        (
            "pub const PYTHON_RISK_DEFAULTS_JSON: &str = "
            f"{_rust_string(_contract_json(dict(summary['risk_defaults'])))};"
        ),
        (
            "pub const PYTHON_UI_DEFAULTS_JSON: &str = "
            f"{_rust_string(_contract_json(dict(summary['ui_defaults'])))};"
        ),
        (
            "pub const PYTHON_DEFAULT_EXECUTION_JSON: &str = "
            f"{_rust_string(_contract_json(dict(summary['default_execution'])))};"
        ),
        (
            "pub const PYTHON_DEFAULT_BACKTEST_JSON: &str = "
            f"{_rust_string(_contract_json(dict(summary['default_backtest'])))};"
        ),
        (
            "pub const PYTHON_OPTION_CATALOGS_JSON: &str = "
            f"{_rust_string(option_catalog_json)};"
        ),
        "",
        _rust_runtime_config_reference_cases(runtime_config_cases),
        "",
        _rust_strategy_controls_reference_cases(strategy_controls_cases),
        "",
        _rust_strategy_risk_reference_cases(strategy_risk_cases),
        "",
        _rust_strategy_risk_loose_reference_cases(strategy_risk_loose_cases),
        (
            "pub const PYTHON_INDICATOR_ENABLED_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(indicator_enabled_reference))};"
        ),
        (
            "pub const PYTHON_BACKTEST_INDICATOR_ENABLED_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(backtest_indicator_enabled_reference))};"
        ),
        (
            "pub const PYTHON_INTERVAL_SECONDS_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(interval_seconds_reference))};"
        ),
        (
            "pub const PYTHON_BACKTEST_INTERVAL_SECONDS_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(backtest_interval_seconds_reference))};"
        ),
        (
            "pub const PYTHON_STOP_INTENT_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(stop_intent_reference))};"
        ),
        (
            "pub const PYTHON_STOP_INTENT_LOOSE_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(stop_intent_loose_reference))};"
        ),
        "",
        _rust_connector_normalization_reference_cases(connector_normalization_cases),
        "",
        _rust_native_runtime_connector_ownership_reference_cases(connector_ownership_cases),
        "",
        _rust_native_runtime_routing_reference_cases(routing_cases),
        (
            "pub const PYTHON_NATIVE_RUNTIME_ROUTING_JSON_COERCION_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(routing_json_coercion_cases))};"
        ),
        "",
        _rust_native_runtime_mode_reference_cases(mode_reference_cases),
        (
            "pub const PYTHON_ORDER_SIZING_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(dict(summary['order_sizing_reference'])))};"
        ),
        (
            "pub const PYTHON_ORDER_INTENT_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(order_intent_reference))};"
        ),
        (
            "pub const PYTHON_LIVE_SAFETY_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(live_safety_reference))};"
        ),
        (
            "pub const PYTHON_CONNECTOR_HEALTH_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(connector_health_reference))};"
        ),
        (
            "pub const PYTHON_LLM_OUTPUT_POLICY_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(llm_output_policy_reference))};"
        ),
        (
            "pub const PYTHON_LLM_CHAT_REQUEST_REFERENCE_JSON: &str = "
            f"{_rust_string(_contract_json(llm_chat_request_reference))};"
        ),
        f"pub const PYTHON_SOURCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
        f"pub const CPP_CONTRACT_PARITY_READY: bool = {_rust_bool(summary['cpp_contract_parity'])};",
        f"pub const RUST_CONTRACT_PARITY_READY: bool = {_rust_bool(summary['rust_contract_parity'])};",
        (f"pub const CPP_STANDALONE_RUNTIME_READY: bool = {_rust_bool(summary['cpp_standalone_runtime_ready'])};"),
        (f"pub const RUST_STANDALONE_RUNTIME_READY: bool = {_rust_bool(summary['rust_standalone_runtime_ready'])};"),
        f"pub const CPP_FULL_PARITY_READY: bool = {_rust_bool(summary['cpp_full_parity'])};",
        f"pub const RUST_FULL_PARITY_READY: bool = {_rust_bool(summary['rust_full_parity'])};",
        (f"pub const PYTHON_ORDER_GUARD_BEHAVIOR_JSON: &str = {_rust_string(_contract_json(order_guard_behavior))};"),
        (
            "pub const PYTHON_LIVE_TRADING_ENABLED_ENV: &str = "
            f"{_rust_string(live_safety_environment['enabled'])};"
        ),
        (
            "pub const PYTHON_LIVE_TRADING_ACK_ENV: &str = "
            f"{_rust_string(live_safety_environment['acknowledgement'])};"
        ),
        (
            "pub const PYTHON_LIVE_TRADING_ACK_ENV_LEGACY: &str = "
            f"{_rust_string(live_safety_environment['legacy_acknowledgement'])};"
        ),
        (
            "pub const PYTHON_LIVE_TRADING_MAX_LEVERAGE_ENV: &str = "
            f"{_rust_string(live_safety_environment['max_leverage'])};"
        ),
        (
            "pub const PYTHON_LIVE_TRADING_MAX_POSITION_PCT_ENV: &str = "
            f"{_rust_string(live_safety_environment['max_position_pct'])};"
        ),
        (
            "pub const PYTHON_LIVE_TRADING_MAX_SESSION_ORDERS_ENV: &str = "
            f"{_rust_string(live_safety_environment['max_session_orders'])};"
        ),
        _rust_array("PYTHON_LIVE_SAFETY_ENV_TRUE_VALUES", environment_bool_true_values),
        _rust_array(
            "PYTHON_NATIVE_RUNTIME_EXCHANGES",
            list(native_runtime_ownership["direct_exchanges"]),
        ),
        _rust_array(
            "PYTHON_NATIVE_RUNTIME_CONNECTOR_BACKENDS",
            list(native_runtime_ownership["direct_connector_backends"]),
        ),
        _rust_array(
            "PYTHON_NATIVE_RUNTIME_MARKET_FAMILIES",
            list(native_runtime_ownership["direct_market_families"]),
        ),
        (
            "pub const PYTHON_NATIVE_RUNTIME_EXECUTION_SCOPE: &str = "
            f"{_rust_string(native_runtime_ownership['native_execution_scope'])};"
        ),
        (
            "pub const PYTHON_NATIVE_RUNTIME_EXECUTION_CAPABILITY: bool = "
            f"{_rust_bool(native_runtime_ownership['native_execution_capability'])};"
        ),
        _rust_string_pairs(
            "PYTHON_NATIVE_RUNTIME_CONNECTOR_MARKET_FAMILIES",
            connector_market_families,
        ),
        _rust_string_pairs(
            "PYTHON_NATIVE_RUNTIME_INDICATOR_SOURCE_MARKET_FAMILIES",
            indicator_source_market_families,
        ),
        _rust_array(
            "PYTHON_NATIVE_RUNTIME_TESTNET_MODE_MARKERS",
            list(mode_policy["testnet_markers"]),
        ),
        (
            "pub const PYTHON_NATIVE_RUNTIME_DELEGATED_OWNER: &str = "
            f"{_rust_string(native_runtime_ownership['delegated_owner'])};"
        ),
        (
            "pub const PYTHON_ORDER_GUARD_VALIDATE_INTENT_ALL_MODES: bool = "
            f"{_rust_bool(order_guard_behavior['validate_intent_all_modes'])};"
        ),
        (
            "pub const PYTHON_ORDER_GUARD_VALIDATE_EXCHANGE_FILTERS_ALL_MODES: bool = "
            f"{_rust_bool(order_guard_behavior['validate_exchange_filters_all_modes'])};"
        ),
        (
            "pub const PYTHON_ORDER_GUARD_VALIDATE_CONNECTOR_HEALTH_ALL_MODES: bool = "
            f"{_rust_bool(order_guard_behavior['validate_connector_health_all_modes'])};"
        ),
        (
            "pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_ENABLED_ALL_MODES: bool = "
            f"{_rust_bool(order_guard_behavior['validate_audit_enabled_all_modes'])};"
        ),
        (
            "pub const PYTHON_ORDER_GUARD_VALIDATE_AUDIT_WRITABLE_ALL_MODES: bool = "
            f"{_rust_bool(order_guard_behavior['validate_audit_writable_all_modes'])};"
        ),
        _rust_array(
            "PYTHON_ORDER_GUARD_LIVE_ONLY_REQUIREMENTS",
            list(order_guard_behavior["live_only_requirements"]),
        ),
        "",
        _rust_parity_domains(list(summary["domains"])),
        "",
        _rust_array("PYTHON_PARITY_DOMAIN_KEYS", list(summary["domain_keys"])),
        "",
        _rust_array(
            "PYTHON_REMOTE_SERVICE_CONFIG_PROTECTED_FIELDS",
            list(summary["remote_service_config_protected_fields"]),
        ),
        "",
        _rust_array("PYTHON_SERVICE_ROUTE_NAMES", list(summary["route_names"])),
        "",
        _rust_service_routes(list(summary["service_routes"])),
        "",
        _rust_service_route_schemas(list(summary["service_route_schemas"])),
        "",
        _rust_array("PYTHON_BACKTEST_RUN_REQUEST_FIELDS", list(summary["backtest_run_request_fields"])),
        "",
        _rust_array("PYTHON_INDICATOR_KEYS", list(summary["indicator_keys"])),
        "",
        _rust_indicator_catalog(list(summary["indicators"])),
        "",
        _rust_array("PYTHON_LLM_PROVIDER_KEYS", list(summary["llm_provider_keys"])),
        "",
        f"pub const PYTHON_LLM_PROVIDER_CATALOG_REVISION: &str = {_rust_string(summary['llm_catalog_revision'])};",
        f"pub const PYTHON_LLM_MODEL_CATALOG_PATH_ENV: &str = {_rust_string(summary['llm_model_catalog_path_env'])};",
        "",
        _rust_llm_providers(list(summary["llm_providers"])),
        "",
        _rust_ollama_model_size_hints(list(summary["ollama_model_size_hints"])),
        "",
        _rust_llm_provider_choices(list(summary["llm_provider_choices"])),
        "",
        _rust_config_choice_maps(dict(summary["config_choice_maps"])),
        "",
        _rust_array("PYTHON_CONNECTOR_KEYS", list(summary["connector_keys"])),
        "",
        _rust_connector_options(list(summary["connectors"])),
        "",
        _rust_environment_dependencies(list(summary["rust_environment_dependencies"])),
        "",
        _rust_array("PYTHON_SUPPORTED_BROKERS", list(summary["supported_brokers"])),
        "",
        _rust_array("PYTHON_SUPPORTED_FOREX_BROKERS", list(summary["supported_forex_brokers"])),
        "",
        _rust_broker_order_routing_backends(list(summary["broker_order_routing_backends"])),
        "",
        _rust_broker_canonical_names(list(summary["broker_canonical_names"])),
        "",
        _rust_array("PYTHON_SUPPORTED_EXCHANGES", list(summary["supported_exchanges"])),
        "",
        _rust_array(
            "PYTHON_SUPPORTED_CONNECTOR_BACKENDS",
            list(summary["supported_connector_backends"]),
        ),
        "",
        _rust_array("PYTHON_CCXT_DIAGNOSTIC_EXCHANGES", list(summary["ccxt_diagnostic_exchanges"])),
        "",
        _rust_array("PYTHON_CCXT_ORDER_ROUTING_EXCHANGES", list(summary["ccxt_order_routing_exchanges"])),
        "",
        _rust_array("PYTHON_ORDER_EXECUTION_EXCHANGES", list(summary["order_execution_exchanges"])),
        "",
        _rust_string_pairs("PYTHON_CCXT_EXCHANGE_IDS", list(summary["ccxt_exchange_ids"])),
        "",
        _rust_array("PYTHON_BACKTEST_INTERVALS", list(summary["intervals"])),
        "",
        _rust_tradingview_interval_map(dict(summary["tradingview_interval_map"])),
        "",
        _rust_array("PYTHON_DEFAULT_CHART_SYMBOLS", list(summary["default_chart_symbols"])),
        "",
        _rust_array("PYTHON_DEFAULT_EXECUTION_SYMBOLS", list(summary["default_execution_symbols"])),
        "",
        _rust_array("PYTHON_DEFAULT_EXECUTION_INTERVALS", list(summary["default_execution_intervals"])),
        "",
        _rust_array("PYTHON_DEFAULT_BACKTEST_SYMBOLS", list(summary["default_backtest_symbols"])),
        "",
        _rust_array("PYTHON_DEFAULT_BACKTEST_INTERVALS", list(summary["default_backtest_intervals"])),
        "",
        _rust_array("PYTHON_CHART_MARKET_OPTIONS", list(summary["chart_market_options"])),
        "",
        _rust_array("PYTHON_ACCOUNT_MODE_OPTIONS", list(summary["account_mode_options"])),
        "",
        _rust_ui_option_catalogs(summary),
        "",
        _rust_starter_catalogs(summary),
        "",
    ]
    body = [f"    {line}" if line else "" for line in parts]
    return "\n".join(
        [
            "// This file is generated from Languages/Python/app/native_parity.py.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "",
            "#[rustfmt::skip]",
            "mod generated {",
            *body,
            "}",
            "",
            "pub use generated::*;",
            "",
        ]
    )


def render_cpp_header() -> str:
    summary = native_python_source_contract_summary()
    order_guard_behavior = dict(summary["order_guard_behavior"])
    live_safety_environment = dict(order_guard_behavior["live_safety_environment"])
    environment_bool_true_values = list(order_guard_behavior["environment_bool_true_values"])
    native_runtime_ownership = dict(summary["native_runtime_ownership"])
    indicator_source_market_families = list(native_runtime_ownership["indicator_source_market_families"])
    connector_market_families = list(native_runtime_ownership["direct_connector_market_families"])
    runtime_config_cases = _runtime_config_reference_cases()
    strategy_controls_cases = list(summary["strategy_controls_reference"])
    strategy_risk_cases = list(summary["strategy_risk_reference"])
    strategy_risk_loose_cases = list(summary["strategy_risk_loose_reference"])
    indicator_enabled_reference = list(summary["indicator_enabled_reference"])
    backtest_indicator_enabled_reference = list(summary["backtest_indicator_enabled_reference"])
    interval_seconds_reference = list(summary["interval_seconds_reference"])
    backtest_interval_seconds_reference = list(summary["backtest_interval_seconds_reference"])
    stop_intent_reference = dict(summary["stop_intent_reference"])
    stop_intent_loose_reference = dict(summary["stop_intent_loose_reference"])
    order_intent_reference = dict(summary["order_intent_reference"])
    live_safety_reference = dict(summary["live_safety_reference"])
    connector_health_reference = dict(summary["connector_health_reference"])
    llm_output_policy_reference = dict(summary["llm_output_policy_reference"])
    llm_chat_request_reference = dict(summary["llm_chat_request_reference"])
    connector_normalization_cases = _connector_normalization_reference_cases()
    connector_ownership_cases = list(summary["native_runtime_connector_ownership_reference"])
    routing_cases = list(summary["native_runtime_routing_reference"])
    routing_json_coercion_cases = list(summary["native_runtime_routing_json_coercion_reference"])
    mode_policy = dict(summary["native_runtime_mode_policy"])
    mode_reference_cases = list(summary["native_runtime_mode_reference"])
    option_catalog_json = _python_option_catalog_json()
    parts = [
        "// This file is generated from Languages/Python/app/native_parity.py.",
        "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
        "#pragma once",
        "",
        "#include <array>",
        "#include <cstddef>",
        "#include <string_view>",
        "",
        "namespace PythonParityContract {",
        "",
        f"inline constexpr std::string_view kPythonSource = {_cpp_string(summary['source'])};",
        f"inline constexpr unsigned kPythonSourceSchemaVersion = {int(summary['schema_version'])};",
        f"inline constexpr std::string_view kPythonSourceContractHash = {_cpp_string(native_python_source_contract_hash())};",
        f"inline constexpr bool kCppContractParityReady = {str(bool(summary['cpp_contract_parity'])).lower()};",
        f"inline constexpr bool kRustContractParityReady = {str(bool(summary['rust_contract_parity'])).lower()};",
        (
            "inline constexpr bool kCppStandaloneRuntimeReady = "
            f"{str(bool(summary['cpp_standalone_runtime_ready'])).lower()};"
        ),
        (
            "inline constexpr bool kRustStandaloneRuntimeReady = "
            f"{str(bool(summary['rust_standalone_runtime_ready'])).lower()};"
        ),
        f"inline constexpr bool kCppFullParityReady = {str(bool(summary['cpp_full_parity'])).lower()};",
        f"inline constexpr bool kRustFullParityReady = {str(bool(summary['rust_full_parity'])).lower()};",
        (
            "inline constexpr std::string_view kPythonDefaultExecutionJson = "
            f"{_cpp_string(_contract_json(dict(summary['default_execution'])))};"
        ),
        (
            "inline constexpr std::string_view kPythonDefaultBacktestJson = "
            f"{_cpp_string(_contract_json(dict(summary['default_backtest'])))};"
        ),
        (
            "inline constexpr std::string_view kPythonOptionCatalogsJson = "
            f"{_cpp_string(option_catalog_json)};"
        ),
        "",
        _cpp_runtime_config_reference_cases(runtime_config_cases),
        "",
        _cpp_strategy_controls_reference_cases(strategy_controls_cases),
        "",
        _cpp_strategy_risk_reference_cases(strategy_risk_cases),
        "",
        _cpp_strategy_risk_loose_reference_cases(strategy_risk_loose_cases),
        (
            "inline constexpr std::string_view kPythonIndicatorEnabledReferenceJson = "
            f"{_cpp_string(_contract_json(indicator_enabled_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonBacktestIndicatorEnabledReferenceJson = "
            f"{_cpp_string(_contract_json(backtest_indicator_enabled_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonIntervalSecondsReferenceJson = "
            f"{_cpp_string(_contract_json(interval_seconds_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonBacktestIntervalSecondsReferenceJson = "
            f"{_cpp_string(_contract_json(backtest_interval_seconds_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonStopIntentReferenceJson = "
            f"{_cpp_string(_contract_json(stop_intent_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonStopIntentLooseReferenceJson = "
            f"{_cpp_string(_contract_json(stop_intent_loose_reference))};"
        ),
        "",
        _cpp_connector_normalization_reference_cases(connector_normalization_cases),
        "",
        _cpp_native_runtime_connector_ownership_reference_cases(connector_ownership_cases),
        "",
        _cpp_native_runtime_routing_reference_cases(routing_cases),
        (
            "inline constexpr std::string_view kPythonNativeRuntimeRoutingJsonCoercionReferenceJson = "
            f"{_cpp_string(_contract_json(routing_json_coercion_cases))};"
        ),
        "",
        _cpp_native_runtime_mode_reference_cases(mode_reference_cases),
        (
            "inline constexpr std::string_view kPythonOrderSizingReferenceJson = "
            f"{_cpp_string(_contract_json(dict(summary['order_sizing_reference'])))};"
        ),
        (
            "inline constexpr std::string_view kPythonOrderIntentReferenceJson = "
            f"{_cpp_string(_contract_json(order_intent_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveSafetyReferenceJson = "
            f"{_cpp_string(_contract_json(live_safety_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonConnectorHealthReferenceJson = "
            f"{_cpp_string(_contract_json(connector_health_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonLlmOutputPolicyReferenceJson = "
            f"{_cpp_string(_contract_json(llm_output_policy_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonLlmChatRequestReferenceJson = "
            f"{_cpp_string(_contract_json(llm_chat_request_reference))};"
        ),
        (
            "inline constexpr std::string_view kPythonRiskDefaultsJson = "
            f"{_cpp_string(_contract_json(dict(summary['risk_defaults'])))};"
        ),
        (
            "inline constexpr std::string_view kPythonUiDefaultsJson = "
            f"{_cpp_string(_contract_json(dict(summary['ui_defaults'])))};"
        ),
        (
            "inline constexpr std::string_view kPythonOrderGuardBehaviorJson = "
            f"{_cpp_string(_contract_json(order_guard_behavior))};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingEnabledEnv = "
            f"{_cpp_string(live_safety_environment['enabled'])};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingAckEnv = "
            f"{_cpp_string(live_safety_environment['acknowledgement'])};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingAckEnvLegacy = "
            f"{_cpp_string(live_safety_environment['legacy_acknowledgement'])};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingMaxLeverageEnv = "
            f"{_cpp_string(live_safety_environment['max_leverage'])};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingMaxPositionPctEnv = "
            f"{_cpp_string(live_safety_environment['max_position_pct'])};"
        ),
        (
            "inline constexpr std::string_view kPythonLiveTradingMaxSessionOrdersEnv = "
            f"{_cpp_string(live_safety_environment['max_session_orders'])};"
        ),
        _cpp_array("kPythonLiveSafetyEnvironmentTrueValues", environment_bool_true_values),
        _cpp_array(
            "kPythonNativeRuntimeExchanges",
            list(native_runtime_ownership["direct_exchanges"]),
        ),
        _cpp_array(
            "kPythonNativeRuntimeConnectorBackends",
            list(native_runtime_ownership["direct_connector_backends"]),
        ),
        _cpp_array(
            "kPythonNativeRuntimeMarketFamilies",
            list(native_runtime_ownership["direct_market_families"]),
        ),
        (
            "inline constexpr std::string_view kPythonNativeRuntimeExecutionScope = "
            f"{_cpp_string(native_runtime_ownership['native_execution_scope'])};"
        ),
        (
            "inline constexpr bool kPythonNativeRuntimeExecutionCapability = "
            f"{str(bool(native_runtime_ownership['native_execution_capability'])).lower()};"
        ),
        _cpp_string_pairs(
            "kPythonNativeRuntimeConnectorMarketFamilies",
            connector_market_families,
        ),
        _cpp_array(
            "kPythonNativeRuntimeTestnetModeMarkers",
            list(mode_policy["testnet_markers"]),
        ),
        (
            "inline constexpr std::string_view kPythonNativeRuntimeDelegatedOwner = "
            f"{_cpp_string(native_runtime_ownership['delegated_owner'])};"
        ),
        (
            "inline constexpr bool kPythonOrderGuardValidateIntentAllModes = "
            f"{_rust_bool(order_guard_behavior['validate_intent_all_modes'])};"
        ),
        (
            "inline constexpr bool kPythonOrderGuardValidateExchangeFiltersAllModes = "
            f"{_rust_bool(order_guard_behavior['validate_exchange_filters_all_modes'])};"
        ),
        (
            "inline constexpr bool kPythonOrderGuardValidateConnectorHealthAllModes = "
            f"{_rust_bool(order_guard_behavior['validate_connector_health_all_modes'])};"
        ),
        (
            "inline constexpr bool kPythonOrderGuardValidateAuditEnabledAllModes = "
            f"{_rust_bool(order_guard_behavior['validate_audit_enabled_all_modes'])};"
        ),
        (
            "inline constexpr bool kPythonOrderGuardValidateAuditWritableAllModes = "
            f"{_rust_bool(order_guard_behavior['validate_audit_writable_all_modes'])};"
        ),
        _cpp_array(
            "kPythonOrderGuardLiveOnlyRequirements",
            list(order_guard_behavior["live_only_requirements"]),
        ),
        "",
        _cpp_parity_domains(list(summary["domains"])),
        "",
        _cpp_array("kPythonParityDomainKeys", list(summary["domain_keys"])),
        "",
        _cpp_array(
            "kPythonRemoteServiceConfigProtectedFields",
            list(summary["remote_service_config_protected_fields"]),
        ),
        "",
        _cpp_array("kPythonServiceRouteNames", list(summary["route_names"])),
        "",
        _cpp_service_routes(list(summary["service_routes"])),
        "",
        _cpp_service_route_schemas(list(summary["service_route_schemas"])),
        "",
        _cpp_array("kPythonBacktestRunRequestFields", list(summary["backtest_run_request_fields"])),
        "",
        _cpp_array("kPythonIndicatorKeys", list(summary["indicator_keys"])),
        "",
        _cpp_indicator_catalog(list(summary["indicators"])),
        "",
        _cpp_array("kPythonLlmProviderKeys", list(summary["llm_provider_keys"])),
        "",
        f"inline constexpr std::string_view kPythonLlmProviderCatalogRevision = {_cpp_string(summary['llm_catalog_revision'])};",
        f"inline constexpr std::string_view kPythonLlmModelCatalogPathEnv = {_cpp_string(summary['llm_model_catalog_path_env'])};",
        "",
        _cpp_llm_providers(list(summary["llm_providers"])),
        "",
        _cpp_ollama_model_size_hints(list(summary["ollama_model_size_hints"])),
        "",
        _cpp_llm_provider_choices(list(summary["llm_provider_choices"])),
        "",
        _cpp_config_choice_maps(dict(summary["config_choice_maps"])),
        "",
        _cpp_array("kPythonConnectorKeys", list(summary["connector_keys"])),
        "",
        _cpp_connector_options(list(summary["connectors"])),
        "",
        _cpp_environment_dependencies(list(summary["rust_environment_dependencies"])),
        "",
        _cpp_array("kPythonSupportedBrokers", list(summary["supported_brokers"])),
        "",
        _cpp_array("kPythonSupportedForexBrokers", list(summary["supported_forex_brokers"])),
        "",
        _cpp_broker_order_routing_backends(list(summary["broker_order_routing_backends"])),
        "",
        _cpp_broker_canonical_names(list(summary["broker_canonical_names"])),
        "",
        _cpp_array("kPythonSupportedExchanges", list(summary["supported_exchanges"])),
        "",
        _cpp_array(
            "kPythonSupportedConnectorBackends",
            list(summary["supported_connector_backends"]),
        ),
        "",
        _cpp_array("kPythonCcxtDiagnosticExchanges", list(summary["ccxt_diagnostic_exchanges"])),
        "",
        _cpp_array("kPythonCcxtOrderRoutingExchanges", list(summary["ccxt_order_routing_exchanges"])),
        "",
        _cpp_array("kPythonOrderExecutionExchanges", list(summary["order_execution_exchanges"])),
        "",
        _cpp_string_pairs(
            "kPythonCcxtExchangeIds",
            list(summary["ccxt_exchange_ids"]),
            include_struct=False,
        ),
        "",
        _cpp_string_pairs(
            "kPythonNativeRuntimeIndicatorSourceMarketFamilies",
            indicator_source_market_families,
            include_struct=False,
        ),
        "",
        _cpp_array("kPythonBacktestIntervals", list(summary["intervals"])),
        "",
        _cpp_tradingview_interval_map(dict(summary["tradingview_interval_map"])),
        "",
        _cpp_array("kPythonDefaultChartSymbols", list(summary["default_chart_symbols"])),
        "",
        _cpp_array("kPythonDefaultExecutionSymbols", list(summary["default_execution_symbols"])),
        "",
        _cpp_array("kPythonDefaultExecutionIntervals", list(summary["default_execution_intervals"])),
        "",
        _cpp_array("kPythonDefaultBacktestSymbols", list(summary["default_backtest_symbols"])),
        "",
        _cpp_array("kPythonDefaultBacktestIntervals", list(summary["default_backtest_intervals"])),
        "",
        _cpp_array("kPythonChartMarketOptions", list(summary["chart_market_options"])),
        "",
        _cpp_array("kPythonAccountModeOptions", list(summary["account_mode_options"])),
        "",
        _cpp_ui_option_catalogs(summary),
        "",
        _cpp_starter_catalogs(summary),
        "",
        "} // namespace PythonParityContract",
        "",
    ]
    return "\n".join(parts)


def render_tauri_browser_contract() -> str:
    summary = native_python_source_contract_summary()
    option_catalog_manifest = _python_option_catalog_manifest()
    option_catalog_json = _python_option_catalog_json()
    option_catalog_count = len(option_catalog_manifest)
    option_catalog_entry_count = sum(entry_count for _, entry_count in option_catalog_manifest)
    connector_normalization_cases = _connector_normalization_reference_cases()
    connector_ownership_cases = list(summary["native_runtime_connector_ownership_reference"])
    routing_cases = list(summary["native_runtime_routing_reference"])
    routing_json_coercion_cases = list(summary["native_runtime_routing_json_coercion_reference"])
    mode_policy = dict(summary["native_runtime_mode_policy"])
    mode_reference_cases = list(summary["native_runtime_mode_reference"])
    service_routes = list(summary["service_routes"])
    service_route_paths = {str(route["name"]): str(route["path"]) for route in service_routes}
    service_route_methods = {
        str(route["name"]): [str(method) for method in route["methods"]] for route in service_routes
    }
    service_route_schemas = list(summary["service_route_schemas"])
    service_route_query_fields = {
        str(schema["name"]): [str(field) for field in schema["query_fields"]] for schema in service_route_schemas
    }
    service_route_request_fields = {
        str(schema["name"]): [str(field) for field in schema["request_fields"]] for schema in service_route_schemas
    }
    service_route_response_fields = {
        str(schema["name"]): [str(field) for field in schema["response_fields"]] for schema in service_route_schemas
    }
    payload = {
        "source": summary["source"],
        "schemaVersion": int(summary["schema_version"]),
        "contractHash": native_python_source_contract_hash(),
        "cppContractParityReady": bool(summary["cpp_contract_parity"]),
        "rustContractParityReady": bool(summary["rust_contract_parity"]),
        "cppStandaloneRuntimeReady": bool(summary["cpp_standalone_runtime_ready"]),
        "rustStandaloneRuntimeReady": bool(summary["rust_standalone_runtime_ready"]),
        "cppFullParityReady": bool(summary["cpp_full_parity"]),
        "rustFullParityReady": bool(summary["rust_full_parity"]),
        "optionCatalogCount": option_catalog_count,
        "optionCatalogEntryCount": option_catalog_entry_count,
        "optionCatalogsJson": option_catalog_json,
        "optionCatalogManifest": [
            {"name": name, "entryCount": entry_count}
            for name, entry_count in option_catalog_manifest
        ],
        "orderGuardBehavior": dict(summary["order_guard_behavior"]),
        "nativeRuntimeOwnership": dict(summary["native_runtime_ownership"]),
        "indicatorCatalog": [
            {
                "key": str(indicator["key"]),
                "name": str(indicator["display_name"]),
                "displayName": str(indicator["display_name"]),
                "defaultEnabled": bool(indicator["default_enabled"]),
                "runtimeOutputKeys": list(indicator["runtime_output_keys"]),
            }
            for indicator in summary["indicators"]
        ],
        "indicatorKeys": list(summary["indicator_keys"]),
        "connectorOptions": list(summary["connectors"]),
        "connectorNormalizationReference": connector_normalization_cases,
        "nativeRuntimeConnectorOwnershipReference": connector_ownership_cases,
        "nativeRuntimeRoutingReference": routing_cases,
        "nativeRuntimeRoutingJsonCoercionReference": routing_json_coercion_cases,
        "nativeRuntimeModePolicy": mode_policy,
        "nativeRuntimeModeReference": mode_reference_cases,
        "supportedBrokers": list(summary["supported_brokers"]),
        "supportedForexBrokers": list(summary["supported_forex_brokers"]),
        "brokerOrderRoutingBackends": list(summary["broker_order_routing_backends"]),
        "backtestIntervals": list(summary["intervals"]),
        "intervalSecondsReference": list(summary["interval_seconds_reference"]),
        "tradingviewIntervalMap": dict(summary["tradingview_interval_map"]),
        "defaultChartSymbols": list(summary["default_chart_symbols"]),
        "defaultExecutionSymbols": list(summary["default_execution_symbols"]),
        "defaultExecutionIntervals": list(summary["default_execution_intervals"]),
        "defaultBacktestSymbols": list(summary["default_backtest_symbols"]),
        "defaultBacktestIntervals": list(summary["default_backtest_intervals"]),
        "chartMarketOptions": list(summary["chart_market_options"]),
        "accountModeOptions": list(summary["account_mode_options"]),
        "dashboardLoopChoices": list(summary["dashboard_loop_choices"]),
        "leadTraderOptions": list(summary["lead_trader_options"]),
        "llmUseForOptions": list(summary["llm_use_for_options"]),
        "llmReasoningEffortOptions": list(summary["llm_reasoning_effort_options"]),
        "positionPctUnitsOptions": list(summary["position_pct_units_options"]),
        "dashboardStrategyTemplates": list(summary["dashboard_strategy_templates"]),
        "backtestTemplates": list(summary["backtest_templates"]),
        "sideOptions": list(summary["side_options"]),
        "configModeOptions": list(summary["config_mode_options"]),
        "themeOptions": list(summary["theme_options"]),
        "designOptions": list(summary["design_options"]),
        "indicatorSourceOptions": list(summary["indicator_source_options"]),
        "indicatorMaTypeOptions": list(summary["indicator_ma_type_options"]),
        "exchangeOptions": list(summary["exchange_options"]),
        "codeLanguageOptions": list(summary["code_language_options"]),
        "rustFrameworkOptions": list(summary["rust_framework_options"]),
        "starterMarketOptions": list(summary["starter_market_options"]),
        "accountTypeOptions": list(summary["account_type_options"]),
        "marginModeOptions": list(summary["margin_mode_options"]),
        "positionModeOptions": list(summary["position_mode_options"]),
        "assetsModeOptions": list(summary["assets_mode_options"]),
        "orderTypeOptions": list(summary["order_type_options"]),
        "timeInForceOptions": list(summary["time_in_force_options"]),
        "signalLogicOptions": list(summary["signal_logic_options"]),
        "mddLogicOptions": list(summary["mdd_logic_options"]),
        "stopLossModes": list(summary["stop_loss_modes"]),
        "stopLossScopes": list(summary["stop_loss_scopes"]),
        "scanScopeOptions": list(summary["scan_scope_options"]),
        "optimizerModeOptions": list(summary["optimizer_mode_options"]),
        "optimizerMetricOptions": list(summary["optimizer_metric_options"]),
        "backtestExecutionBackendOptions": list(summary["backtest_execution_backend_options"]),
        "chartViewOptions": list(summary["chart_view_options"]),
        "positionsViewOptions": list(summary["positions_view_options"]),
        "chartViewKeys": list(summary["chart_view_keys"]),
        "rustEnvironmentDependencies": list(summary["rust_environment_dependencies"]),
        "defaultExecution": dict(summary["default_execution"]),
        "defaultBacktest": dict(summary["default_backtest"]),
        "riskDefaults": dict(summary["risk_defaults"]),
        "uiDefaults": dict(summary["ui_defaults"]),
        "backtestRunRequestFields": list(summary["backtest_run_request_fields"]),
        "llmProviders": list(summary["llm_providers"]),
        "llmProviderKeys": list(summary["llm_provider_keys"]),
        "llmProviderChoices": list(summary["llm_provider_choices"]),
        "ollamaModelSizeHints": list(summary["ollama_model_size_hints"]),
        "configChoiceMaps": {
            name: dict(values) for name, values in summary["config_choice_maps"].items()
        },
        "connectorKeys": list(summary["connector_keys"]),
        "serviceRouteNames": list(summary["route_names"]),
        "serviceRoutePaths": service_route_paths,
        "serviceRouteMethods": service_route_methods,
        "serviceRouteQueryFields": service_route_query_fields,
        "serviceRouteRequestFields": service_route_request_fields,
        "serviceRouteResponseFields": service_route_response_fields,
        "serviceRouteSchemas": service_route_schemas,
        "serviceRoutes": service_routes,
    }
    body = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2)
    return "\n".join(
        [
            "// This file is generated from Languages/Python/app/native_parity.py.",
            "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
            "(function () {",
            f"  window.PythonParityContract = Object.freeze({body});",
            "}());",
            "",
        ]
    )


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``newline=""`` preserves generated LF bytes on Windows and remains
    # accepted by the Python 3.14 pathlib implementation.
    path.write_text(content, encoding="utf-8", newline="")
    return True


def main() -> int:
    changed = [
        write_if_changed(RUST_OUTPUT, render_rust_module()),
        write_if_changed(RUST_INDICATOR_REFERENCE_OUTPUT, render_rust_indicator_reference_module()),
        write_if_changed(
            RUST_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
            render_rust_exchange_support_reference_module(),
        ),
        write_if_changed(RUST_PORTFOLIO_REFERENCE_OUTPUT, render_rust_portfolio_reference_module()),
        write_if_changed(CPP_OUTPUT, render_cpp_header()),
        write_if_changed(CPP_INDICATOR_REFERENCE_OUTPUT, render_cpp_indicator_reference_header()),
        write_if_changed(
            CPP_EXCHANGE_SUPPORT_REFERENCE_OUTPUT,
            render_cpp_exchange_support_reference_header(),
        ),
        write_if_changed(CPP_PORTFOLIO_REFERENCE_OUTPUT, render_cpp_portfolio_reference_header()),
        write_if_changed(TAURI_BROWSER_OUTPUT, render_tauri_browser_contract()),
    ]
    print(f"Native parity contracts generated. changed={any(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
