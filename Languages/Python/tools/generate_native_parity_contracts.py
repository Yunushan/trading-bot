from __future__ import annotations

import json
from pathlib import Path
import sys


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import (  # noqa: E402
    INDICATOR_RUNTIME_OUTPUT_KEYS,
    native_python_source_contract_hash,
    native_python_source_contract_summary,
)
from app.core import indicators as indicator_math  # noqa: E402

import pandas as pd  # noqa: E402


RUST_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "crates"
    / "core"
    / "src"
    / "generated_python_parity.rs"
)
RUST_INDICATOR_REFERENCE_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "crates"
    / "core"
    / "src"
    / "generated_python_indicator_reference.rs"
)
CPP_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "native-cpp"
    / "src"
    / "generated"
    / "PythonParityContract.h"
)
TAURI_BROWSER_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "rust-shells"
    / "apps"
    / "tauri-desktop"
    / "ui"
    / "generated-python-parity.js"
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


def _rust_bool(value: object) -> str:
    return str(bool(value)).lower()


def _contract_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


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


def _indicator_reference_payload() -> dict[str, object]:
    closes = [100.0, 103.0, 101.0, 106.0, 104.0, 109.0, 105.0, 111.0, 108.0, 114.0, 110.0, 116.0]
    highs = [101.0, 104.5, 102.5, 107.5, 105.0, 110.5, 106.0, 112.5, 109.5, 115.0, 111.5, 117.0]
    lows = [98.5, 101.0, 99.0, 103.5, 102.0, 107.0, 103.0, 109.0, 106.0, 112.0, 108.0, 114.0]
    volumes = [18.0, 31.0, 24.0, 42.0, 29.0, 47.0, 35.0, 53.0, 38.0, 59.0, 44.0, 63.0]
    frame = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes})
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
        "kst": {"enabled": True, "roc1": 1, "roc2": 2, "roc3": 3, "roc4": 4, "sma1": 2, "sma2": 2, "sma3": 2, "sma4": 2, "signal": 2},
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
    bb_upper, bb_mid, bb_lower = indicator_math.bollinger_bands(frame, length=3, std=2.0)
    keltner_upper, keltner_mid, keltner_lower = indicator_math.keltner_channels(frame, length=3, atr_length=2, multiplier=2.0)
    ichimoku_tenkan, ichimoku_kijun, ichimoku_span_a, ichimoku_span_b, ichimoku_chikou = indicator_math.ichimoku_cloud(frame, conversion_length=2, base_length=3, span_b_length=4, displacement=2)
    ppo_line, ppo_signal, ppo_hist = indicator_math.ppo(frame["close"], fast=2, slow=3, signal=2)
    kst_line, kst_signal, kst_hist = indicator_math.kst(frame["close"], roc1=1, roc2=2, roc3=3, roc4=4, sma1=2, sma2=2, sma3=2, sma4=2, signal=2)
    aroon_up, aroon_down, aroon = indicator_math.aroon(frame, length=3)
    stoch_rsi, stoch_rsi_d = indicator_math.stoch_rsi(frame["close"], length=3, smooth_k=2, smooth_d=2)
    macd_line, macd_signal, _macd_hist = indicator_math.macd(frame["close"], fast=2, slow=3, signal=2)
    dmi_plus, dmi_minus, adx = indicator_math.dmi(frame, length=3)
    stochastic, stochastic_d = indicator_math.stochastic(frame, length=3, smooth_k=2, smooth_d=2)
    donchian_high = indicator_math.donchian_high(frame, 3)
    donchian_low = indicator_math.donchian_low(frame, 3)
    expected = {
        "ma": indicator_math.sma(frame["close"], 3),
        "donchian_high": donchian_high,
        "donchian_low": donchian_low,
        "donchian": (donchian_high + donchian_low) / 2.0,
        "psar": indicator_math.parabolic_sar(frame, af=0.02, max_af=0.2),
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "bbw": indicator_math.bollinger_band_width(frame, length=3, std=2.0),
        "keltner_upper": keltner_upper, "keltner_mid": keltner_mid, "keltner_lower": keltner_lower,
        "ichimoku_tenkan": ichimoku_tenkan, "ichimoku_kijun": ichimoku_kijun, "ichimoku_span_a": ichimoku_span_a, "ichimoku_span_b": ichimoku_span_b, "ichimoku_chikou": ichimoku_chikou,
        "ichimoku": ichimoku_tenkan - ichimoku_kijun,
        "rsi": indicator_math.rsi(frame["close"], length=3),
        "volume": frame["volume"], "obv": indicator_math.obv(frame), "rvol": indicator_math.relative_volume(frame, length=3),
        "cmf": indicator_math.chaikin_money_flow(frame, length=3), "cci": indicator_math.cci(frame, length=3, constant=0.015),
        "roc": indicator_math.roc(frame["close"], length=3), "trix": indicator_math.trix(frame["close"], length=3),
        "ppo": ppo_line, "ppo_signal": ppo_signal, "ppo_hist": ppo_hist,
        "ao": indicator_math.awesome_oscillator(frame, fast=2, slow=3),
        "kst": kst_line, "kst_signal": kst_signal, "kst_hist": kst_hist,
        "aroon_up": aroon_up, "aroon_down": aroon_down, "aroon": aroon,
        "chop": indicator_math.choppiness_index(frame, length=3),
        "atr": indicator_math.atr(frame, length=3), "natr": indicator_math.natr(frame, length=3),
        "vwap": indicator_math.vwap(frame, length=3), "mfi": indicator_math.mfi(frame, length=3),
        "stoch_rsi": stoch_rsi, "stoch_rsi_k": stoch_rsi, "stoch_rsi_d": stoch_rsi_d,
        "willr": indicator_math.williams_r(frame, length=3),
        "macd_line": macd_line, "macd_signal": macd_signal,
        "uo": indicator_math.ultimate_oscillator(frame, short=2, medium=3, long=4),
        "adx": adx, "dmi_plus": dmi_plus, "dmi_minus": dmi_minus, "dmi": dmi_plus - dmi_minus,
        "supertrend": indicator_math.supertrend(frame, atr_period=2, multiplier=3.0),
        "ema": indicator_math.ema(frame["close"], 3),
        "stochastic": stochastic, "stochastic_k": stochastic, "stochastic_d": stochastic_d,
    }
    declared_output_keys = {
        output_key
        for output_keys in INDICATOR_RUNTIME_OUTPUT_KEYS.values()
        for output_key in output_keys
    }
    expected_output_keys = set(expected)
    if declared_output_keys != expected_output_keys:
        missing = ", ".join(sorted(expected_output_keys - declared_output_keys))
        unexpected = ", ".join(sorted(declared_output_keys - expected_output_keys))
        raise RuntimeError(
            "INDICATOR_RUNTIME_OUTPUT_KEYS must exactly match the Python numerical "
            f"indicator fixture (missing: {missing or '-'}; unexpected: {unexpected or '-'})"
        )
    return {
        "python_source_contract_hash": native_python_source_contract_hash(),
        "candles": frame.to_dict(orient="records"),
        "configs": configs,
        "expected": {key: _json_series(series) for key, series in expected.items()},
    }


def render_rust_indicator_reference_module() -> str:
    payload = _contract_json(_indicator_reference_payload())
    return "\n".join([
        "// This file is generated from Python indicator implementations.",
        "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
        "#[rustfmt::skip]",
        f"pub const PYTHON_INDICATOR_REFERENCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
        "#[rustfmt::skip]",
        f"pub const PYTHON_INDICATOR_REFERENCE_JSON: &str = {_rust_string(payload)};",
        "",
    ])


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
    cpp_required = "; ".join(_domain_required_list(domain, "cpp_required_before_full_parity"))
    rust_required = "; ".join(_domain_required_list(domain, "rust_required_before_full_parity"))
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
                (
                    "        required_before_full_parity: "
                    f"{_rust_string(_domain_required_before_full_parity(domain))},"
                ),
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
        "    pub runtime_output_keys: &'static [&'static str],",
        "}",
        "",
        "pub const PYTHON_INDICATOR_CATALOG: &[PythonIndicator] = &[",
    ]
    for indicator in indicators:
        runtime_output_keys = ", ".join(
            _rust_string(str(key)) for key in indicator["runtime_output_keys"]
        )
        lines.extend(
            [
                "    PythonIndicator {",
                f"        key: {_rust_string(indicator['key'])},",
                f"        display_name: {_rust_string(indicator['display_name'])},",
                f"        default_enabled: {_rust_bool(indicator['default_enabled'])},",
                f"        runtime_config_json: {_rust_string(_contract_json(indicator['runtime_config']))},",
                f"        runtime_output_keys: &[{runtime_output_keys}],",
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
        "}",
        "",
        "pub const PYTHON_LLM_PROVIDERS: &[PythonLlmProvider] = &[",
    ]
    for provider in providers:
        models = ", ".join(_rust_string(model) for model in provider["model_suggestions"])
        efforts = ", ".join(_rust_string(effort) for effort in provider["reasoning_efforts"])
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
                "    },",
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def _ui_option_key(option: dict[str, object]) -> str:
    return str(option.get("key", option.get("value", "")))


def _rust_ui_option_catalogs(summary: dict[str, object]) -> str:
    option_groups = [
        ("PYTHON_DASHBOARD_LOOP_CHOICES", list(summary["dashboard_loop_choices"])),
        ("PYTHON_LEAD_TRADER_OPTIONS", list(summary["lead_trader_options"])),
        ("PYTHON_LLM_USE_FOR_OPTIONS", list(summary["llm_use_for_options"])),
        ("PYTHON_DASHBOARD_STRATEGY_TEMPLATES", list(summary["dashboard_strategy_templates"])),
        ("PYTHON_BACKTEST_TEMPLATES", list(summary["backtest_templates"])),
        ("PYTHON_SIDE_OPTIONS", list(summary["side_options"])),
        ("PYTHON_CONFIG_MODE_OPTIONS", list(summary["config_mode_options"])),
        ("PYTHON_THEME_OPTIONS", list(summary["theme_options"])),
        ("PYTHON_DESIGN_OPTIONS", list(summary["design_options"])),
        ("PYTHON_INDICATOR_SOURCE_OPTIONS", list(summary["indicator_source_options"])),
        ("PYTHON_EXCHANGE_OPTIONS", list(summary["exchange_options"])),
        ("PYTHON_ACCOUNT_TYPE_OPTIONS", list(summary["account_type_options"])),
        ("PYTHON_MARGIN_MODE_OPTIONS", list(summary["margin_mode_options"])),
        ("PYTHON_POSITION_MODE_OPTIONS", list(summary["position_mode_options"])),
        ("PYTHON_ASSETS_MODE_OPTIONS", list(summary["assets_mode_options"])),
        ("PYTHON_ORDER_TYPE_OPTIONS", list(summary["order_type_options"])),
        ("PYTHON_TIME_IN_FORCE_OPTIONS", list(summary["time_in_force_options"])),
        ("PYTHON_SIGNAL_LOGIC_OPTIONS", list(summary["signal_logic_options"])),
        ("PYTHON_MDD_LOGIC_OPTIONS", list(summary["mdd_logic_options"])),
        ("PYTHON_STOP_LOSS_MODES", list(summary["stop_loss_modes"])),
        ("PYTHON_STOP_LOSS_SCOPES", list(summary["stop_loss_scopes"])),
        ("PYTHON_SCAN_SCOPE_OPTIONS", list(summary["scan_scope_options"])),
        ("PYTHON_OPTIMIZER_MODE_OPTIONS", list(summary["optimizer_mode_options"])),
        ("PYTHON_OPTIMIZER_METRIC_OPTIONS", list(summary["optimizer_metric_options"])),
        (
            "PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS",
            list(summary["backtest_execution_backend_options"]),
        ),
        ("PYTHON_CHART_VIEW_OPTIONS", list(summary["chart_view_options"])),
        ("PYTHON_POSITIONS_VIEW_OPTIONS", list(summary["positions_view_options"])),
    ]
    lines = [
        "pub struct PythonUiOption {",
        "    pub key: &'static str,",
        "    pub label: &'static str,",
        "    pub disabled: bool,",
        "}",
    ]
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
        "    std::string_view runtimeOutputKeysCsv;",
        "};",
        "",
        f"inline constexpr std::array<PythonIndicator, {len(indicators)}> kPythonIndicatorCatalog = {{",
    ]
    for indicator in indicators:
        runtime_output_keys = ",".join(
            str(key) for key in indicator["runtime_output_keys"]
        )
        lines.append(
            "    PythonIndicator{"
            f"{_cpp_string(indicator['key'])}, "
            f"{_cpp_string(indicator['display_name'])}, "
            f"{str(bool(indicator['default_enabled'])).lower()}, "
            f"{_cpp_string(_contract_json(indicator['runtime_config']))}, "
            f"{_cpp_string(runtime_output_keys)}"
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
            "    PythonConnectorOption{"
            f"{_cpp_string(connector['key'])}, {_cpp_string(connector['label'])}"
            "},"
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
        "};",
        "",
        f"inline constexpr std::array<PythonLlmProvider, {len(providers)}> kPythonLlmProviders = {{",
    ]
    for provider in providers:
        models = ",".join(str(model) for model in provider["model_suggestions"])
        efforts = ",".join(str(effort) for effort in provider["reasoning_efforts"])
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
            f"{_cpp_string(provider['default_reasoning_effort'])}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def _cpp_ui_option_catalogs(summary: dict[str, object]) -> str:
    option_groups = [
        ("kPythonDashboardLoopChoices", list(summary["dashboard_loop_choices"])),
        ("kPythonLeadTraderOptions", list(summary["lead_trader_options"])),
        ("kPythonLlmUseForOptions", list(summary["llm_use_for_options"])),
        ("kPythonDashboardStrategyTemplates", list(summary["dashboard_strategy_templates"])),
        ("kPythonBacktestTemplates", list(summary["backtest_templates"])),
        ("kPythonSideOptions", list(summary["side_options"])),
        ("kPythonConfigModeOptions", list(summary["config_mode_options"])),
        ("kPythonThemeOptions", list(summary["theme_options"])),
        ("kPythonDesignOptions", list(summary["design_options"])),
        ("kPythonIndicatorSourceOptions", list(summary["indicator_source_options"])),
        ("kPythonExchangeOptions", list(summary["exchange_options"])),
        ("kPythonAccountTypeOptions", list(summary["account_type_options"])),
        ("kPythonMarginModeOptions", list(summary["margin_mode_options"])),
        ("kPythonPositionModeOptions", list(summary["position_mode_options"])),
        ("kPythonAssetsModeOptions", list(summary["assets_mode_options"])),
        ("kPythonOrderTypeOptions", list(summary["order_type_options"])),
        ("kPythonTimeInForceOptions", list(summary["time_in_force_options"])),
        ("kPythonSignalLogicOptions", list(summary["signal_logic_options"])),
        ("kPythonMddLogicOptions", list(summary["mdd_logic_options"])),
        ("kPythonStopLossModes", list(summary["stop_loss_modes"])),
        ("kPythonStopLossScopes", list(summary["stop_loss_scopes"])),
        ("kPythonScanScopeOptions", list(summary["scan_scope_options"])),
        ("kPythonOptimizerModeOptions", list(summary["optimizer_mode_options"])),
        ("kPythonOptimizerMetricOptions", list(summary["optimizer_metric_options"])),
        (
            "kPythonBacktestExecutionBackendOptions",
            list(summary["backtest_execution_backend_options"]),
        ),
        ("kPythonChartViewOptions", list(summary["chart_view_options"])),
        ("kPythonPositionsViewOptions", list(summary["positions_view_options"])),
    ]
    lines = [
        "struct PythonUiOption {",
        "    std::string_view key;",
        "    std::string_view label;",
        "    bool disabled;",
        "};",
    ]
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
        lines.append(
            "    PythonTradingViewInterval{"
            f"{_cpp_string(interval)}, {_cpp_string(code)}"
            "},"
        )
    lines.append("};")
    return "\n".join(lines)


def render_rust_module() -> str:
    summary = native_python_source_contract_summary()
    order_guard_behavior = dict(summary["order_guard_behavior"])
    parts = [
        f"pub const PYTHON_SOURCE: &str = {_rust_string(summary['source'])};",
        f"pub const PYTHON_SOURCE_SCHEMA_VERSION: u32 = {int(summary['schema_version'])};",
        f"pub const PYTHON_SOURCE_CONTRACT_HASH: &str = {_rust_string(native_python_source_contract_hash())};",
        f"pub const CPP_CONTRACT_PARITY_READY: bool = {_rust_bool(summary['cpp_contract_parity'])};",
        f"pub const RUST_CONTRACT_PARITY_READY: bool = {_rust_bool(summary['rust_contract_parity'])};",
        (
            "pub const CPP_STANDALONE_RUNTIME_READY: bool = "
            f"{_rust_bool(summary['cpp_standalone_runtime_ready'])};"
        ),
        (
            "pub const RUST_STANDALONE_RUNTIME_READY: bool = "
            f"{_rust_bool(summary['rust_standalone_runtime_ready'])};"
        ),
        f"pub const CPP_FULL_PARITY_READY: bool = {_rust_bool(summary['cpp_full_parity'])};",
        f"pub const RUST_FULL_PARITY_READY: bool = {_rust_bool(summary['rust_full_parity'])};",
        (
            "pub const PYTHON_ORDER_GUARD_BEHAVIOR_JSON: &str = "
            f"{_rust_string(_contract_json(order_guard_behavior))};"
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
        _rust_llm_providers(list(summary["llm_providers"])),
        "",
        _rust_array("PYTHON_CONNECTOR_KEYS", list(summary["connector_keys"])),
        "",
        _rust_connector_options(list(summary["connectors"])),
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
    parts = [
        "// This file is generated from Languages/Python/app/native_parity.py.",
        "// Do not edit manually; run Languages/Python/tools/generate_native_parity_contracts.py.",
        "#pragma once",
        "",
        "#include <array>",
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
            "inline constexpr std::string_view kPythonOrderGuardBehaviorJson = "
            f"{_cpp_string(_contract_json(order_guard_behavior))};"
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
        _cpp_llm_providers(list(summary["llm_providers"])),
        "",
        _cpp_array("kPythonConnectorKeys", list(summary["connector_keys"])),
        "",
        _cpp_connector_options(list(summary["connectors"])),
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
        "} // namespace PythonParityContract",
        "",
    ]
    return "\n".join(parts)


def render_tauri_browser_contract() -> str:
    summary = native_python_source_contract_summary()
    service_routes = list(summary["service_routes"])
    service_route_paths = {
        str(route["name"]): str(route["path"])
        for route in service_routes
    }
    service_route_methods = {
        str(route["name"]): [str(method) for method in route["methods"]]
        for route in service_routes
    }
    service_route_schemas = list(summary["service_route_schemas"])
    service_route_query_fields = {
        str(schema["name"]): [str(field) for field in schema["query_fields"]]
        for schema in service_route_schemas
    }
    service_route_request_fields = {
        str(schema["name"]): [str(field) for field in schema["request_fields"]]
        for schema in service_route_schemas
    }
    service_route_response_fields = {
        str(schema["name"]): [str(field) for field in schema["response_fields"]]
        for schema in service_route_schemas
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
        "orderGuardBehavior": dict(summary["order_guard_behavior"]),
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
        "backtestIntervals": list(summary["intervals"]),
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
        "dashboardStrategyTemplates": list(summary["dashboard_strategy_templates"]),
        "backtestTemplates": list(summary["backtest_templates"]),
        "sideOptions": list(summary["side_options"]),
        "configModeOptions": list(summary["config_mode_options"]),
        "themeOptions": list(summary["theme_options"]),
        "designOptions": list(summary["design_options"]),
        "indicatorSourceOptions": list(summary["indicator_source_options"]),
        "exchangeOptions": list(summary["exchange_options"]),
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
        "defaultExecution": dict(summary["default_execution"]),
        "defaultBacktest": dict(summary["default_backtest"]),
        "backtestRunRequestFields": list(summary["backtest_run_request_fields"]),
        "llmProviders": list(summary["llm_providers"]),
        "llmProviderKeys": list(summary["llm_provider_keys"]),
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
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    changed = [
        write_if_changed(RUST_OUTPUT, render_rust_module()),
        write_if_changed(RUST_INDICATOR_REFERENCE_OUTPUT, render_rust_indicator_reference_module()),
        write_if_changed(CPP_OUTPUT, render_cpp_header()),
        write_if_changed(TAURI_BROWSER_OUTPUT, render_tauri_browser_contract()),
    ]
    print(f"Native parity contracts generated. changed={any(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
