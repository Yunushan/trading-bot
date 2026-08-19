from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from dataclasses import fields as dataclass_fields
from pathlib import Path
from unittest.mock import patch


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import (  # noqa: E402
    INDICATOR_RUNTIME_OUTPUT_KEYS,
        NATIVE_PARITY_DOMAINS,
        native_python_source_contract_hash,
        native_python_source_contract_payload,
        native_python_source_contract_summary,
)
from app.service.api_contract import (  # noqa: E402
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SCHEMAS,
    SERVICE_API_ROUTE_SUFFIXES,
)
from app.integrations.llm.local_models import LocalModelStatus  # noqa: E402
from app.gui.runtime.composition.module_state_constants import (  # noqa: E402
    FUTURES_CONNECTOR_KEYS,
    SPOT_CONNECTOR_KEYS,
)
from app.settings.exchange_support import SUPPORTED_CONNECTOR_BACKENDS  # noqa: E402
from tools.generate_native_parity_contracts import (  # noqa: E402
    CPP_OUTPUT,
    CPP_PORTFOLIO_REFERENCE_OUTPUT,
    RUST_OUTPUT,
    RUST_PORTFOLIO_REFERENCE_OUTPUT,
    TAURI_BROWSER_OUTPUT,
    _cpp_string,
    _exchange_support_reference_payload,
    _indicator_reference_payload,
    _python_option_catalog_manifest,
    _python_option_catalog_json,
    _runtime_config_reference_cases,
    _rust_string,
    render_cpp_header,
    render_cpp_exchange_support_reference_header,
    render_rust_module,
    render_rust_exchange_support_reference_module,
    render_cpp_portfolio_reference_header,
    render_rust_portfolio_reference_module,
    render_tauri_browser_contract,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_repo_tool(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


class NativeGeneratedParityContractTests(unittest.TestCase):
    def test_local_model_status_contract_covers_python_dataclass(self):
        declared_fields = set(SERVICE_API_ROUTE_SCHEMAS["llm_local_model_status"]["response_fields"])
        python_fields = {field.name for field in dataclass_fields(LocalModelStatus)}
        self.assertEqual(
            python_fields,
            declared_fields,
            "local model response schema must expose every Python LocalModelStatus field",
        )

    maxDiff = None

    def test_runtime_config_reference_covers_every_python_choice_alias(self):
        cases = _runtime_config_reference_cases()
        names = {str(case["name"]) for case in cases}
        choice_maps = native_python_source_contract_summary()["config_choice_maps"]
        expected_names = {
            f"choice-{choice_name}-{alias}"
            for choice_name, choices in choice_maps.items()
            for alias in choices
        }
        expected_names.update(
            f"choice-llm_provider-{choice['key']}"
            for choice in native_python_source_contract_summary()["llm_provider_choices"]
            if choice["key"]
        )
        self.assertTrue(expected_names.issubset(names))
        self.assertIn("alias-rich-runtime", names)
        self.assertIn("canonical-runtime", names)

    def test_runtime_config_reference_covers_python_rejection_boundaries(self):
        cases = _runtime_config_reference_cases()
        invalid_cases = [case for case in cases if not bool(case["valid"])]
        self.assertGreaterEqual(len(invalid_cases), 30)
        self.assertEqual(
            {case["name"] for case in invalid_cases},
            {
                case["name"]
                for case in native_python_source_contract_summary()["runtime_config_invalid_reference"]
            },
        )
        for case in invalid_cases:
            self.assertTrue(str(case["expected_error"]).startswith("Invalid config:"))
            self.assertEqual(case["expected"], {})

    def test_strategy_controls_reference_covers_python_normalization_boundaries(self):
        cases = native_python_source_contract_summary()["strategy_controls_reference"]
        self.assertGreaterEqual(len(cases), 5)
        self.assertEqual(
            {
                "runtime-canonical",
                "runtime-python-truthiness-boundaries",
                "runtime-kind-is-case-sensitive",
                "backtest-canonical",
                "backtest-exact-logic-and-fuzzy-side",
            },
            {case["name"] for case in cases},
        )
        canonical_runtime = next(case for case in cases if case["name"] == "runtime-canonical")
        self.assertTrue(canonical_runtime["expected"]["add_only"])
        self.assertEqual(canonical_runtime["expected"]["position_pct_units"], "percent")
        canonical_backtest = next(case for case in cases if case["name"] == "backtest-canonical")
        self.assertNotIn("fee_bps", canonical_backtest["expected"])
        self.assertNotIn("slippage_bps", canonical_backtest["expected"])

    def test_strategy_risk_reference_covers_python_effective_defaults_and_bounds(self):
        cases = native_python_source_contract_summary()["strategy_risk_reference"]
        self.assertEqual(
            {
                "risk-defaults",
                "risk-canonical-all-controls",
                "risk-valid-lower-and-upper-bounds",
            },
            {case["name"] for case in cases},
        )
        defaults = next(case for case in cases if case["name"] == "risk-defaults")
        self.assertFalse(defaults["expected"]["indicator_use_live_values"])
        canonical = next(case for case in cases if case["name"] == "risk-canonical-all-controls")
        self.assertEqual(canonical["expected"]["indicator_flip_cooldown_bars"], 4)
        self.assertEqual(canonical["expected"]["stop_loss"]["scope"], "entire_account")
        bounds = next(case for case in cases if case["name"] == "risk-valid-lower-and-upper-bounds")
        self.assertEqual(bounds["expected"]["max_auto_bump_percent"], 100.0)
        self.assertEqual(bounds["expected"]["auto_bump_percent_multiplier"], 1000.0)

    def test_strategy_risk_loose_reference_covers_python_bool_coercion_boundaries(self):
        cases = native_python_source_contract_summary()["strategy_risk_loose_reference"]
        self.assertEqual(
            {
                "risk-loose-string-y",
                "risk-loose-unknown-string",
                "risk-loose-fractional-zero",
                "risk-loose-fractional-one",
                "risk-loose-negative-fractional-zero",
                "risk-loose-negative-fractional-one",
            },
            {case["name"] for case in cases},
        )
        loose_y = next(case for case in cases if case["name"] == "risk-loose-string-y")
        self.assertFalse(loose_y["expected"]["indicator_use_live_values"])
        self.assertTrue(loose_y["expected"]["allow_opposite_positions"])
        fractional_zero = next(case for case in cases if case["name"] == "risk-loose-fractional-zero")
        self.assertFalse(fractional_zero["expected"]["indicator_use_live_values"])
        fractional_one = next(case for case in cases if case["name"] == "risk-loose-fractional-one")
        self.assertTrue(fractional_one["expected"]["indicator_use_live_values"])

    def test_indicator_enabled_references_preserve_python_context_semantics(self):
        summary = native_python_source_contract_summary()
        strategy_cases = summary["indicator_enabled_reference"]
        backtest_cases = summary["backtest_indicator_enabled_reference"]
        self.assertEqual(len(strategy_cases), 23)
        self.assertEqual(len(backtest_cases), 23)
        strategy = {case["name"]: case["expected"] for case in strategy_cases}
        backtest = {case["name"]: case["expected"] for case in backtest_cases}
        self.assertFalse(strategy["indicator-enabled-string-y"])
        self.assertTrue(backtest["backtest-indicator-enabled-string-y"])
        self.assertFalse(strategy["indicator-enabled-fractional-zero"])
        self.assertTrue(backtest["backtest-indicator-enabled-fractional-zero"])
        self.assertTrue(strategy["indicator-enabled-fractional-one"])
        self.assertTrue(backtest["backtest-indicator-enabled-fractional-one"])
        self.assertFalse(strategy["indicator-enabled-unknown-string"])
        self.assertTrue(backtest["backtest-indicator-enabled-unknown-string"])
        self.assertFalse(strategy["indicator-enabled-string-disabled"])
        self.assertFalse(backtest["backtest-indicator-enabled-string-disabled"])
        self.assertFalse(strategy["indicator-enabled-string-none"])
        self.assertTrue(backtest["backtest-indicator-enabled-string-none"])
        self.assertFalse(strategy["indicator-enabled-string-null"])
        self.assertTrue(backtest["backtest-indicator-enabled-string-null"])
        self.assertFalse(strategy["indicator-enabled-string-numeric"])
        self.assertTrue(backtest["backtest-indicator-enabled-string-numeric"])
        self.assertFalse(strategy["indicator-enabled-null"])
        self.assertFalse(backtest["backtest-indicator-enabled-null"])

    def test_order_intent_reference_covers_python_boolean_boundaries(self):
        payload = native_python_source_contract_summary()["order_intent_reference"]
        self.assertEqual(payload["schema_version"], 1)
        cases = payload["cases"]
        self.assertEqual(
            {
                "canonical-close-position",
                "python-intent-y-is-false-filter-y-is-true",
                "canonical-aliases-and-conflicting-flags",
                "spot-rejects-futures-flags",
            },
            {case["name"] for case in cases},
        )
        y_boundary = next(
            case
            for case in cases
            if case["name"] == "python-intent-y-is-false-filter-y-is-true"
        )
        self.assertFalse(y_boundary["expected"]["intent"]["close_position"])
        self.assertEqual(y_boundary["expected"]["intent_errors"], [])
        self.assertEqual(y_boundary["expected"]["filter_errors"], [])
        spot_case = next(case for case in cases if case["name"] == "spot-rejects-futures-flags")
        self.assertIn("positionSide is only supported for futures", spot_case["expected"]["intent_errors"])
        self.assertIn("closePosition orders are only supported for futures", spot_case["expected"]["intent_errors"])
        self.assertIn("reduceOnly orders are only supported for futures", spot_case["expected"]["intent_errors"])

    def test_connector_health_reference_covers_python_fail_closed_boundaries(self):
        payload = native_python_source_contract_summary()["connector_health_reference"]
        self.assertEqual(payload["schema_version"], 1)
        cases = {case["name"]: case for case in payload["cases"]}
        self.assertEqual(
            {
                "missing-state",
                "missing-health",
                "not-ready",
                "degraded-health",
                "ready-ok",
                "ready-unknown",
            },
            set(cases),
        )
        self.assertEqual(cases["missing-state"]["expected_errors"], ["connector health snapshot missing state"])
        self.assertEqual(cases["missing-health"]["expected_errors"], ["connector health snapshot missing health"])
        self.assertEqual(cases["not-ready"]["expected_errors"], ["connector health is degraded / paused"])
        self.assertEqual(cases["degraded-health"]["expected_errors"], ["connector health is degraded"])
        self.assertEqual(cases["ready-ok"]["expected_errors"], [])
        self.assertEqual(cases["ready-unknown"]["expected_errors"], [])

    def test_live_safety_reference_covers_python_gate_boundaries(self):
        payload = native_python_source_contract_summary()["live_safety_reference"]
        self.assertEqual(payload["schema_version"], 1)
        cases = {case["name"]: case for case in payload["cases"]}
        self.assertEqual(
            {
                "demo-mode-bypasses-live-gates",
                "live-requires-confirmation",
                "live-safe-futures",
                "live-spot-position-cap",
                "live-invalid-caps-and-futures-controls",
                "live-rejects-placeholder-credentials",
            },
            set(cases),
        )
        self.assertEqual(cases["demo-mode-bypasses-live-gates"]["expected_errors"], [])
        self.assertEqual(cases["live-safe-futures"]["expected_errors"], [])
        self.assertIn(
            "set live_trading_enabled=true",
            cases["live-requires-confirmation"]["expected_errors"][0],
        )
        self.assertIn(
            "position_pct 4% exceeds live cap 3%",
            cases["live-spot-position-cap"]["expected_errors"],
        )
        self.assertIn(
            "provide non-placeholder Binance API credentials",
            cases["live-rejects-placeholder-credentials"]["expected_errors"],
        )

    def test_indicator_reference_contains_multiple_python_generated_scenarios(self):
        payload = _indicator_reference_payload()
        cases = payload["indicator_cases"]
        self.assertIsInstance(cases, list)
        self.assertGreaterEqual(len(cases), 3)
        self.assertEqual(
            payload["candles"],
            cases[0]["candles"],
        )
        self.assertEqual(
            payload["configs"],
            cases[0]["configs"],
        )
        self.assertEqual(
            payload["expected"],
            cases[0]["expected"],
        )
        self.assertEqual(
            {
                "baseline",
                "reversal-and-flat",
                "parameterized-longer-series",
                "short-warmup-series",
                "flat-price-series",
                "zero-volume-series",
                "threshold-zero-series",
                "mfi-threshold-series",
                "string-config-values",
            },
            {case["name"] for case in cases},
        )
        for case in cases:
            self.assertEqual(
                set(case["expected"]),
                {
                    output_key
                    for output_keys in INDICATOR_RUNTIME_OUTPUT_KEYS.values()
                    for output_key in output_keys
                },
            )

        backtest_cases = payload["backtest_cases"]
        self.assertGreaterEqual(len(backtest_cases), 27)
        self.assertEqual(
            {"baseline", "reversal-and-flat", "parameterized-longer-series"},
            {case["fixture_name"] for case in backtest_cases},
        )
        for case in backtest_cases:
            self.assertTrue(case["candles"])
            self.assertIn("expected", case)

        live_signal_cases = payload["live_signal_cases"]
        self.assertIsInstance(live_signal_cases, list)
        self.assertGreaterEqual(len(live_signal_cases), 44)
        self.assertEqual(
            {"BUY", "SELL", None},
            {case["expected"]["signal"] for case in live_signal_cases},
        )
        self.assertEqual(
            {"BOTH", "BUY", "SELL"},
            {case["side"] for case in live_signal_cases},
        )
        self.assertEqual(
            {"rsi-both-buy", "rsi-buy-blocked-by-sell-side", "rsi-sell-blocked-by-buy-side"},
            {
                case["name"]
                for case in live_signal_cases
                if case["expected"]["signal"] is None
                or case["side"] == "BOTH"
            },
        )
        self.assertIn(3, {case["expected"]["min_bars"] for case in live_signal_cases})
        self.assertEqual(
            {
                "rsi",
                "stoch_rsi",
                "willr",
                "natr",
                "mfi",
                "obv",
                "rvol",
                "cmf",
                "cci",
                "roc",
                "trix",
                "bbw",
                "ppo",
                "ao",
                "kst",
                "aroon",
                "chop",
                "ma",
                "ichimoku",
            },
            {source for case in live_signal_cases for source in case["expected"]["trigger_sources"]},
        )
        for case in live_signal_cases:
            self.assertTrue(case["candles"])
            self.assertIn("indicators", case)
            self.assertIn("expected", case)

    def test_generated_native_contracts_are_in_sync_with_python_source(self):
        self.assertEqual(render_rust_module(), _read(RUST_OUTPUT))
        self.assertEqual(render_cpp_header(), _read(CPP_OUTPUT))
        self.assertEqual(render_tauri_browser_contract(), _read(TAURI_BROWSER_OUTPUT))
        self.assertEqual(
            render_rust_portfolio_reference_module(),
            _read(RUST_PORTFOLIO_REFERENCE_OUTPUT),
        )
        self.assertEqual(
            render_cpp_portfolio_reference_header(),
            _read(CPP_PORTFOLIO_REFERENCE_OUTPUT),
        )

    def test_python_option_catalog_inventory_is_complete(self):
        option_catalogs = native_python_source_contract_payload()["ui_options"]
        entry_count = sum(
            len(value) if isinstance(value, (dict, list, tuple)) else 1
            for value in option_catalogs.values()
        )
        self.assertEqual(44, len(option_catalogs))
        self.assertEqual(255, entry_count)

    def test_every_python_option_catalog_is_manifested_in_native_and_browser_contracts(self):
        manifest = _python_option_catalog_manifest()
        option_catalog_json = _python_option_catalog_json()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)

        self.assertEqual(44, len(manifest))
        self.assertEqual(255, sum(entry_count for _, entry_count in manifest))
        self.assertIn(
            "pub const PYTHON_OPTION_CATALOG_MANIFEST: &[PythonOptionCatalogManifestEntry] = &[",
            rust_generated,
        )
        self.assertIn(
            "inline constexpr std::array<PythonOptionCatalogManifestEntry, 44> "
            "kPythonOptionCatalogManifest = {",
            cpp_generated,
        )
        self.assertIn('"optionCatalogManifest": [', tauri_generated)
        self.assertIn(
            "pub const PYTHON_OPTION_CATALOGS_JSON: &str = "
            f"{_rust_string(option_catalog_json)};",
            rust_generated,
        )
        self.assertIn(
            "inline constexpr std::string_view kPythonOptionCatalogsJson = "
            f"{_cpp_string(option_catalog_json)};",
            cpp_generated,
        )
        self.assertIn(
            f'"optionCatalogsJson": {json.dumps(option_catalog_json)}',
            tauri_generated,
        )
        for name, entry_count in manifest:
            with self.subTest(catalog=name):
                rust_name = _rust_string(name)
                cpp_name = _cpp_string(name)
                self.assertIn(
                    "PythonOptionCatalogManifestEntry {"
                    f" name: {rust_name}, entry_count: {entry_count} }},",
                    rust_generated,
                )
                self.assertIn(
                    "PythonOptionCatalogManifestEntry{"
                    f"{cpp_name}, {entry_count} }},",
                    cpp_generated,
                )
                self.assertIn(
                    f'"entryCount": {entry_count},\n      "name": {json.dumps(name)}',
                    tauri_generated,
                )

    def test_position_reconciliation_reference_covers_python_policy_paths(self):
        from app.native_parity import native_position_reconciliation_reference_cases

        cases = native_position_reconciliation_reference_cases()
        self.assertGreaterEqual(len(cases), 5)
        self.assertEqual(
            {
                "live-recovery-preserves-python-metadata",
                "threshold-autoclose-after-two-misses",
                "grace-period-waits-before-close",
                "autoclose-disabled-drops-record",
                "pending-close-bypasses-threshold-and-grace",
            },
            {case["name"] for case in cases},
        )
        for case in cases:
            self.assertEqual(len(case["steps"]), len(case["expected_steps"]))
            for step, expected in zip(case["steps"], case["expected_steps"]):
                self.assertEqual(
                    set(expected["summary"]),
                    {"closed_keys", "dropped_keys", "waiting_keys", "live_keys"},
                )
                self.assertIn("open_position_records", expected["state"])
                self.assertIn("closed_position_records", expected["state"])
                self.assertIn("positions_missing_threshold", step["policy"])

    def test_exchange_support_reference_covers_python_resolution_matrix(self):
        payload = _exchange_support_reference_payload()
        cases = payload["exchange_support_cases"]
        self.assertIsInstance(cases, list)
        self.assertGreaterEqual(len(cases), 60)
        self.assertEqual(payload["python_source_contract_hash"], native_python_source_contract_hash())
        names = {case["name"] for case in cases}
        self.assertIn("empty-input", names)
        self.assertIn("snapshot-takes-precedence", names)
        self.assertIn("ai-gold-alias", names)
        self.assertIn("unknown-exchange-backend-broker", names)
        for case in cases:
            self.assertEqual(set(case), {"name", "config", "snapshot", "expected"})
            self.assertEqual(
                set(case["config"]),
                {"selected_exchange", "connector_backend", "selected_forex_broker"},
            )
            self.assertEqual(
                set(case["expected"]),
                {
                    "selected_exchange",
                    "connector_backend",
                    "selected_forex_broker",
                    "ccxt_exchange_id",
                    "exchange_supported",
                    "connector_backend_supported",
                    "broker_supported",
                    "broker_market_scope",
                    "forex_order_routing_supported",
                    "market_data_supported",
                    "account_snapshot_supported",
                    "order_routing_supported",
                    "order_execution_supported",
                    "live_evidence_required",
                    "trading_supported",
                    "support_tier",
                    "capability_gaps",
                    "unsupported_reasons",
                    "supported_exchanges",
                    "supported_connector_backends",
                    "supported_brokers",
                    "supported_forex_brokers",
                    "ccxt_diagnostic_exchanges",
                    "ccxt_order_routing_exchanges",
                    "order_execution_exchanges",
                    "broker_order_routing_brokers",
                    "broker_order_routing_backends",
                },
            )

    def test_generated_exchange_support_reference_modules_are_in_sync(self):
        self.assertEqual(
            render_rust_exchange_support_reference_module(),
            _read(
                REPO_ROOT
                / "experiments"
                / "rust-shells"
                / "crates"
                / "core"
                / "src"
                / "generated_python_exchange_support_reference.rs"
            ),
        )
        self.assertEqual(
            render_cpp_exchange_support_reference_header(),
            _read(
                REPO_ROOT
                / "experiments"
                / "native-cpp"
                / "src"
                / "generated"
                / "PythonExchangeSupportReference.h"
            ),
        )

    def test_cpp_reference_literals_supply_explicit_lengths_for_gcc(self):
        generated_dir = REPO_ROOT / "experiments" / "native-cpp" / "src" / "generated"
        for name in (
            "PythonIndicatorReference.h",
            "PythonExchangeSupportReference.h",
            "PythonPortfolioReference.h",
        ):
            with self.subTest(name=name):
                source = _read(generated_dir / name)
                declaration = source.split(
                    "inline constexpr std::string_view kReferenceJson =", 1
                )[1].rsplit("};", 1)[0]
                self.assertIn("std::string_view{", declaration)
                length = declaration.rsplit(",", 1)[1].strip().rstrip("}")
                self.assertTrue(length.isdigit())

    def test_generated_rust_contract_is_stable_under_rustfmt(self):
        rust_generated = _read(RUST_OUTPUT)

        self.assertIn("#[rustfmt::skip]\nmod generated {", rust_generated)
        self.assertIn("pub use generated::*;", rust_generated)

    def test_generated_contract_exposes_python_source_boundaries(self):
        summary = native_python_source_contract_summary()
        domain_keys = [domain.key for domain in NATIVE_PARITY_DOMAINS]

        self.assertEqual(domain_keys, summary["domain_keys"])
        self.assertTrue(summary["cpp_contract_parity"])
        self.assertTrue(summary["rust_contract_parity"])
        self.assertFalse(summary["cpp_standalone_runtime_ready"])
        self.assertFalse(summary["rust_standalone_runtime_ready"])
        self.assertFalse(summary["cpp_full_parity"])
        self.assertFalse(summary["rust_full_parity"])
        ownership = summary["native_runtime_ownership"]
        direct_backends = set(ownership["direct_connector_backends"])
        connector_market_families = ownership["direct_connector_market_families"]
        expected_backends = FUTURES_CONNECTOR_KEYS | SPOT_CONNECTOR_KEYS
        expected_market_families = {
            (backend, "coin-m-futures")
            if backend == "binance-sdk-derivatives-trading-coin-futures"
            else (backend, "usd-m-futures")
            for backend in FUTURES_CONNECTOR_KEYS
        }
        expected_market_families.update(
            (backend, "spot") for backend in SPOT_CONNECTOR_KEYS
        )
        self.assertEqual(expected_backends, direct_backends)
        self.assertEqual(
            expected_market_families,
            {(mapping["key"], mapping["value"]) for mapping in connector_market_families},
        )
        self.assertEqual(
            direct_backends,
            {mapping["key"] for mapping in connector_market_families},
        )
        self.assertTrue(
            {"ccxt", "python-binance"}.issubset(direct_backends),
            "Python Binance connector aliases must remain in the native ownership contract",
        )
        for alias in ("ccxt", "python-binance"):
            with self.subTest(alias=alias):
                self.assertEqual(
                    {"spot", "usd-m-futures"},
                    {
                        mapping["value"]
                        for mapping in connector_market_families
                        if mapping["key"] == alias
                    },
                )
        self.assertTrue(connector_market_families)
        self.assertTrue(
            all(mapping["value"] in ownership["direct_market_families"] for mapping in connector_market_families)
        )
        self.assertEqual(
            summary["supported_brokers"],
            [mapping["broker"] for mapping in summary["broker_order_routing_backends"]],
        )
        self.assertEqual(
            ["Binance", "Bybit", "OKX", "Bitget", "Gate", "MEXC", "KuCoin", "HTX", "Crypto.com Exchange", "Kraken", "Bitfinex"],
            summary["supported_exchanges"],
        )
        self.assertEqual(list(SUPPORTED_CONNECTOR_BACKENDS), summary["supported_connector_backends"])
        self.assertEqual(summary["ccxt_diagnostic_exchanges"], summary["ccxt_order_routing_exchanges"])
        self.assertEqual(["Binance"], summary["order_execution_exchanges"])
        self.assertEqual("gateio", dict((item["key"], item["value"]) for item in summary["ccxt_exchange_ids"])["gate"])
        self.assertIn("Trading 212", summary["supported_brokers"])
        self.assertNotIn("Trading 212", summary["supported_forex_brokers"])
        self.assertIn("StoneX", summary["supported_brokers"])
        self.assertNotIn("StoneX", summary["supported_forex_brokers"])
        self.assertIn("AI Gold Securities", summary["supported_brokers"])
        self.assertNotIn("AI Gold Securities", summary["supported_forex_brokers"])
        broker_canonical_names = {
            mapping["identity"]: mapping["canonical"] for mapping in summary["broker_canonical_names"]
        }
        self.assertEqual("AI Gold Securities", broker_canonical_names["aigold"])
        self.assertEqual("PhillipCapital (Phillip Nova)", broker_canonical_names["phillipsecurities"])
        self.assertEqual("PhillipCapital (Phillip Nova)", broker_canonical_names["philipsecurities"])
        for broker in ("Trade Nation", "FXTF", "FOREX EXCHANGE"):
            self.assertIn(broker, summary["supported_forex_brokers"])
        self.assertIn("metatrader4-bridge", summary["connector_keys"])
        self.assertIn("CITIC Futures", summary["supported_brokers"])
        self.assertNotIn("CITIC Futures", summary["supported_forex_brokers"])
        self.assertEqual(12, len(summary["domain_keys"]))
        self.assertIn("service_api_contract", summary["domain_keys"])
        self.assertIn("backtest_engine", summary["domain_keys"])
        self.assertIn("order_execution_and_risk", summary["domain_keys"])
        self.assertFalse(summary["risk_defaults"]["indicator_use_live_values"])
        self.assertEqual(summary["risk_defaults"]["stop_loss"]["scope"], "per_trade")

    def test_rust_and_cpp_consume_generated_python_contracts(self):
        rust_core = _read(REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs")
        cpp_support_header = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.h")
        cpp_support_source = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp")
        cpp_window_header = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.h")
        cpp_dashboard_ui = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_ui.cpp")
        cpp_dashboard_overrides = _read(
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_overrides.cpp"
        )
        cpp_dashboard_theme = _read(
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.dashboard_theme.cpp"
        )
        cpp_chart_source = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.chart.cpp")
        tauri_html = _read(REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html")
        tauri_behavior = _read(
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "tauri-ui-behavior.js"
        )
        cmake = _read(REPO_ROOT / "experiments" / "native-cpp" / "CMakeLists.txt")

        self.assertIn("pub mod generated_python_parity", rust_core)
        self.assertIn("PythonParityDomain as NativePythonAppParityDomain", rust_core)
        self.assertIn("PythonServiceRoute as ServiceApiRoute", rust_core)
        self.assertIn("PythonServiceRouteSchema as ServiceApiRouteSchema", rust_core)
        self.assertIn("python_source_contract_hash", rust_core)
        self.assertIn("generated_python_parity::PYTHON_PARITY_DOMAINS", rust_core)
        self.assertIn("generated_python_parity::PYTHON_SERVICE_ROUTES", rust_core)
        self.assertIn("generated_python_parity::PYTHON_SERVICE_ROUTE_SCHEMAS", rust_core)
        self.assertIn("python_source_service_route_schemas", rust_core)
        self.assertIn("service_api_route_schema", rust_core)
        self.assertIn("python_source_backtest_run_request_fields", rust_core)
        self.assertIn("python_source_indicator_keys", rust_core)
        self.assertIn("python_source_indicator_catalog", rust_core)
        self.assertIn("python_source_llm_provider_keys", rust_core)
        self.assertIn("python_source_connector_keys", rust_core)
        self.assertIn("python_source_backtest_intervals", rust_core)
        self.assertIn("python_source_cpp_contract_parity_ready", rust_core)
        self.assertIn("python_source_rust_contract_parity_ready", rust_core)
        self.assertIn("python_source_cpp_standalone_runtime_ready", rust_core)
        self.assertIn("python_source_rust_standalone_runtime_ready", rust_core)
        cpp_generated = _read(CPP_OUTPUT)
        rust_generated = _read(
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "generated_python_parity.rs"
        )
        tauri_generated = _read(
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "generated-python-parity.js"
        )
        self.assertIn("pub const CPP_CONTRACT_PARITY_READY: bool = true;", rust_generated)
        self.assertIn("pub const RUST_CONTRACT_PARITY_READY: bool = true;", rust_generated)
        self.assertIn("pub const CPP_STANDALONE_RUNTIME_READY: bool = false;", rust_generated)
        self.assertIn("pub const RUST_STANDALONE_RUNTIME_READY: bool = false;", rust_generated)
        self.assertIn("pub const CPP_FULL_PARITY_READY: bool = false;", rust_generated)
        self.assertIn("pub const RUST_FULL_PARITY_READY: bool = false;", rust_generated)
        self.assertIn("PYTHON_RISK_DEFAULTS_JSON", rust_generated)
        self.assertIn("PYTHON_UI_DEFAULTS_JSON", rust_generated)
        self.assertIn("PYTHON_DEFAULT_EXECUTION_JSON", rust_generated)
        self.assertIn("PYTHON_DEFAULT_BACKTEST_JSON", rust_generated)
        self.assertIn("kPythonUiDefaultsJson", cpp_generated)
        self.assertIn("PYTHON_SUPPORTED_BROKERS", rust_generated)
        self.assertIn("PYTHON_SUPPORTED_FOREX_BROKERS", rust_generated)
        self.assertIn("PYTHON_BROKER_ORDER_ROUTING_BACKENDS", rust_generated)
        self.assertIn('"cppContractParityReady": true', tauri_generated)
        self.assertIn('"rustContractParityReady": true', tauri_generated)
        self.assertIn('"cppStandaloneRuntimeReady": false', tauri_generated)
        self.assertIn('"rustStandaloneRuntimeReady": false', tauri_generated)
        self.assertIn('"cppFullParityReady": false', tauri_generated)
        self.assertIn('"rustFullParityReady": false', tauri_generated)
        self.assertIn('"optionCatalogCount": 44', tauri_generated)
        self.assertIn('"optionCatalogEntryCount": 255', tauri_generated)
        self.assertIn('"riskDefaults"', tauri_generated)
        self.assertIn('"uiDefaults"', tauri_generated)
        self.assertIn('"supportedBrokers"', tauri_generated)
        self.assertIn('"supportedForexBrokers"', tauri_generated)
        self.assertIn('"brokerOrderRoutingBackends"', tauri_generated)
        self.assertIn("python_source_tradingview_interval_map", rust_core)
        self.assertIn("python_source_default_chart_symbols", rust_core)
        self.assertIn("python_source_default_execution_symbols", rust_core)
        self.assertIn("python_source_default_backtest_symbols", rust_core)
        self.assertIn("python_source_dashboard_loop_choices", rust_core)
        self.assertIn("python_source_lead_trader_options", rust_core)
        self.assertIn("python_source_llm_use_for_options", rust_core)
        self.assertIn("python_source_dashboard_strategy_templates", rust_core)
        self.assertIn("python_source_backtest_templates", rust_core)
        self.assertIn("python_source_side_options", rust_core)
        self.assertIn("python_source_config_mode_options", rust_core)
        self.assertIn("python_source_theme_options", rust_core)
        self.assertIn("python_source_design_options", rust_core)
        self.assertIn("python_source_indicator_source_options", rust_core)
        self.assertIn("python_source_indicator_ma_type_options", rust_core)
        self.assertIn("python_source_exchange_options", rust_core)
        self.assertIn("python_source_account_type_options", rust_core)
        self.assertIn("python_source_margin_mode_options", rust_core)
        self.assertIn("python_source_position_mode_options", rust_core)
        self.assertIn("python_source_assets_mode_options", rust_core)
        self.assertIn("python_source_time_in_force_options", rust_core)
        self.assertIn("python_source_signal_logic_options", rust_core)
        self.assertIn("python_source_mdd_logic_options", rust_core)
        self.assertIn("python_source_stop_loss_modes", rust_core)
        self.assertIn("python_source_chart_view_options", rust_core)
        self.assertIn("python_source_positions_view_options", rust_core)
        self.assertIn('include "generated/PythonParityContract.h"', cpp_support_source)
        self.assertIn("pythonSourceParityContractHash", cpp_support_header)
        self.assertIn("pythonSourceParityDomainTitle", cpp_support_header)
        self.assertIn("pythonSourceParityDomainCppStatus", cpp_support_source)
        self.assertIn("pythonSourceParityDomainRustStatus", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonParityDomains", cpp_support_source)
        self.assertIn("pythonSourceServiceRoutePath", cpp_support_header)
        self.assertIn("pythonSourceServiceRouteMethods", cpp_support_source)
        self.assertIn("pythonSourceServiceRouteQueryFields", cpp_support_header)
        self.assertIn("pythonSourceServiceRouteRequestFields", cpp_support_source)
        self.assertIn("pythonSourceServiceRouteResponseFields", cpp_support_source)
        self.assertIn("pythonSourceBacktestRunRequestFields", cpp_support_header)
        self.assertIn("pythonSourceIndicatorKeys", cpp_support_source)
        self.assertIn("pythonSourceIndicatorDisplayNames", cpp_support_header)
        self.assertIn("pythonSourceDefaultEnabledIndicatorKeys", cpp_support_source)
        self.assertIn("pythonSourceLlmProviderKeys", cpp_support_source)
        self.assertIn("pythonSourceLlmProviderLabels", cpp_support_header)
        self.assertIn("pythonSourceLlmProviderDefaultModels", cpp_support_source)
        self.assertIn("mergePythonLlmProviderSpec", cpp_support_header)
        self.assertIn("mergePythonLlmProviderSpec", cpp_support_source)
        self.assertIn('QStringLiteral("default_base_url")', cpp_support_source)
        self.assertIn('QStringLiteral("default_reasoning_effort")', cpp_support_source)
        self.assertIn('QStringLiteral("model_suggestions")', cpp_support_source)
        self.assertIn('QStringLiteral("reasoning_efforts")', cpp_support_source)
        self.assertIn("pythonSourceConnectorKeys", cpp_support_source)
        self.assertIn("pythonSourceConnectorLabels", cpp_support_header)
        self.assertIn("pythonSourceBacktestIntervals", cpp_support_source)
        self.assertIn("pythonSourceDefaultChartSymbols", cpp_support_header)
        self.assertIn("pythonSourceDefaultChartSymbols", cpp_chart_source)
        self.assertIn("pythonSourceTradingViewIntervalKeys", cpp_support_header)
        self.assertIn("pythonSourceTradingViewIntervalKeys", cpp_chart_source)
        self.assertIn("pythonSourceTradingViewIntervalCodes", cpp_support_source)
        self.assertIn("pythonSourceTradingViewIntervalCodes", cpp_chart_source)
        self.assertIn("pythonSourceDefaultExecutionSymbols", cpp_support_source)
        self.assertIn("pythonSourceDefaultBacktestSymbols", cpp_support_source)
        self.assertIn("pythonSourceDashboardLoopChoiceLabels", cpp_support_header)
        self.assertIn("pythonSourceLeadTraderOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceLlmUseForOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceDashboardStrategyTemplateKeys", cpp_support_source)
        self.assertIn("pythonSourceBacktestTemplateKeys", cpp_support_source)
        self.assertIn("pythonSourceSideOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceConfigModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceThemeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceDesignOptionLabels", cpp_support_source)
        self.assertIn("applyDashboardDesign", cpp_window_header)
        self.assertIn("dashboardDesignCombo_", cpp_window_header)
        self.assertIn("pythonSourceDesignOptionKeys", cpp_dashboard_ui)
        self.assertIn('addPair(0, col, "Design:", dashboardDesignCombo_)', cpp_dashboard_ui)
        self.assertIn('config.insert(QStringLiteral("design")', cpp_dashboard_overrides)
        self.assertIn('setComboValue(dashboardDesignCombo_', cpp_dashboard_overrides)
        self.assertIn("isWorkstationDesign", cpp_dashboard_theme)
        self.assertIn('setProperty("workstationLayout"', cpp_dashboard_theme)
        self.assertIn("workspaceNavigation_->setVisible(workstation)", cpp_dashboard_theme)
        self.assertIn("syncWorkspaceNavigation", cpp_dashboard_theme)
        self.assertIn("workspaceNavigation_", cpp_window_header)
        self.assertIn("workspaceNavigation_", _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindow.cpp"))
        cpp_main = _read(REPO_ROOT / "experiments" / "native-cpp" / "src" / "main.cpp")
        self.assertIn("pythonSourceThemeOptionLabels", cpp_main)
        self.assertIn("pythonSourceDesignOptionLabels", cpp_main)
        self.assertIn('findChild<QListWidget *>(QStringLiteral("workspaceNavigation"))', cpp_main)
        self.assertIn('findChild<QWidget *>(QStringLiteral("workspaceNavigationRail"))', cpp_main)
        self.assertIn('findData(QStringLiteral("Workstation"))', cpp_main)
        self.assertIn('findData(QStringLiteral("Classic"))', cpp_main)
        self.assertIn("currentData().toString()", cpp_main)
        self.assertIn('window.property("workstationLayout")', cpp_main)
        self.assertIn("pythonSourceIndicatorSourceOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceExchangeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceAccountTypeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceMarginModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourcePositionModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceAssetsModeOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceTimeInForceOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceSignalLogicOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceMddLogicOptionLabels", cpp_support_source)
        self.assertIn("pythonSourceStopLossModeLabels", cpp_support_source)
        self.assertIn("pythonSourceChartViewOptionLabels", cpp_support_source)
        self.assertIn("pythonSourcePositionsViewOptionLabels", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonServiceRoutes", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonIndicatorCatalog", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonLlmProviders", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonConnectorOptions", cpp_support_source)
        self.assertIn("PythonParityContract::kPythonBacktestTemplates", cpp_support_source)
        self.assertIn('src="generated-python-parity.js"', tauri_html)
        self.assertIn("window.PythonParityContract", _read(TAURI_BROWSER_OUTPUT))
        self.assertIn("pythonParityContract.indicatorCatalog", tauri_html)
        self.assertIn("pythonParityContract.llmProviders", tauri_html)
        self.assertIn("pythonParityContract.connectorOptions", tauri_html)
        self.assertIn("pythonParityContract.defaultExecution", tauri_html)
        self.assertIn("pythonParityContract.defaultBacktest", tauri_html)
        self.assertIn("pythonParityContract.riskDefaults", tauri_html)
        self.assertIn("pythonParityContract.defaultChartSymbols", tauri_html)
        self.assertIn("pythonParityContract.dashboardLoopChoices", tauri_html)
        self.assertIn("pythonParityContract.leadTraderOptions", tauri_html)
        self.assertIn("pythonParityContract.llmUseForOptions", tauri_html)
        self.assertIn("pythonParityContract.dashboardStrategyTemplates", tauri_html)
        self.assertIn("pythonParityContract.backtestTemplates", tauri_html)
        self.assertIn("pythonParityContract.tradingviewIntervalMap", tauri_html)
        self.assertIn("pythonParityContract.configModeOptions", tauri_html)
        self.assertIn("pythonParityContract.themeOptions", tauri_html)
        self.assertIn("pythonParityContract.designOptions", tauri_html)
        self.assertIn("applyDesignMode", tauri_html)
        self.assertIn("tauriUiBehavior.normalizeDesign", tauri_html)
        self.assertIn('body[data-design="Workstation"]', tauri_html)
        self.assertIn("normalizeDesign", tauri_behavior)
        self.assertIn("designModeClass", tauri_behavior)
        self.assertIn("pythonParityContract.indicatorSourceOptions", tauri_html)
        self.assertIn("pythonParityContract.exchangeOptions", tauri_html)
        self.assertIn("pythonParityContract.accountTypeOptions", tauri_html)
        self.assertIn("pythonParityContract.marginModeOptions", tauri_html)
        self.assertIn("pythonParityContract.positionModeOptions", tauri_html)
        self.assertIn("pythonParityContract.assetsModeOptions", tauri_html)
        self.assertIn("pythonParityContract.timeInForceOptions", tauri_html)
        self.assertIn("pythonParityContract.signalLogicOptions", tauri_html)
        self.assertIn("pythonParityContract.chartViewOptions", tauri_html)
        self.assertIn("pythonParityContract.positionsViewOptions", tauri_html)
        self.assertNotIn("const indicatorCatalog = [", tauri_html)
        self.assertNotIn("const chartDefaultSymbols = [", tauri_html)
        self.assertNotIn("const chartIntervalMap = {", tauri_html)
        self.assertNotIn("const modelSuggestions = {", tauri_html)
        self.assertIn('<input id="llm-model" list="llm-model-options"', tauri_html)
        self.assertIn('<datalist id="llm-model-options"></datalist>', tauri_html)
        self.assertIn("modelOptions.replaceChildren", tauri_html)
        self.assertIn('setValue("llm-model", llm.model)', tauri_html)
        self.assertIn('id="refresh-llm-catalog-btn"', tauri_html)
        self.assertIn('serviceRequest("llm_providers", "GET")', tauri_html)
        self.assertIn("mergeLlmProviderSpec", tauri_html)
        self.assertIn("customModelsPathEnv", tauri_html)
        self.assertIn("defaultReasoningEffort", tauri_html)
        self.assertIn("default_reasoning_effort", tauri_html)
        self.assertIn("preserveCurrent: true", tauri_html)
        self.assertNotIn("model.replaceChildren(...llm.model_suggestions", tauri_html)
        self.assertIn("pythonParityContract.serviceRoutePaths", tauri_html)
        self.assertIn("serviceRouteSupportsMethod", tauri_html)
        self.assertIn("NativeServiceApiContractTests.cpp", cmake)
        self.assertIn("src/generated/PythonParityContract.h", cmake)

    def test_contract_hash_is_embedded_in_native_destinations(self):
        contract_hash = native_python_source_contract_hash()

        self.assertIn(contract_hash, _read(RUST_OUTPUT))
        self.assertIn(contract_hash, _read(CPP_OUTPUT))
        self.assertIn(contract_hash, _read(TAURI_BROWSER_OUTPUT))

    def test_native_source_sync_audit_is_first_class_verification_gate(self):
        audit = _load_repo_tool(
            "audit_native_source_sync",
            REPO_ROOT / "tools" / "audit_native_source_sync.py",
        )
        report = audit.audit_native_source_sync()
        verify_all = _read(REPO_ROOT / "tools" / "verify_all.py")
        ci_workflow = _read(REPO_ROOT / ".github" / "workflows" / "ci.yml")
        hardening_checker = _read(REPO_ROOT / "tools" / "check_hardening_articles.py")
        evidence_gates = _read(REPO_ROOT / "docs" / "QUALITY_AND_EVIDENCE_GATES.md")

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(native_python_source_contract_hash(), report["contract_hash"])
        feature_option_contract = report["feature_option_contract"]
        self.assertTrue(feature_option_contract["ok"], feature_option_contract)
        self.assertEqual(12, feature_option_contract["feature_domain_count"])
        self.assertEqual(
            {"cpp": True, "rust": True},
            feature_option_contract["feature_domain_contract_parity"],
        )
        self.assertGreaterEqual(feature_option_contract["option_catalog_count"], 35)
        self.assertGreaterEqual(feature_option_contract["option_catalog_entry_count"], 100)
        self.assertEqual(
            {"cpp": True, "rust": True},
            feature_option_contract["generated_native_contracts_match_python"],
        )
        option_catalog_consumers = feature_option_contract["option_catalog_consumers"]
        self.assertTrue(option_catalog_consumers["ok"], option_catalog_consumers)
        self.assertEqual(44, option_catalog_consumers["catalog_count"])
        for target in ("cpp", "rust", "browser"):
            with self.subTest(option_catalog_consumer_target=target):
                target_report = option_catalog_consumers["targets"][target]
                self.assertTrue(target_report["ok"], target_report)
                self.assertEqual(44, target_report["catalog_count"])
                self.assertEqual(100.0, target_report["coverage_percent"])
                self.assertEqual(
                    target_report["applicable_count"],
                    target_report["covered_count"],
                )
        domain_evidence = report["domain_evidence_contract"]
        self.assertTrue(domain_evidence["ok"], domain_evidence)
        self.assertEqual(12, len(domain_evidence["domains"]))
        for domain in domain_evidence["domains"]:
            with self.subTest(domain=domain["key"]):
                for target in ("cpp", "rust"):
                    self.assertTrue(domain[target]["required"])
                    self.assertTrue(domain[target]["ok"])
        parity_percentages = report["parity_percentages"]
        for target in ("cpp", "rust"):
            self.assertEqual(100.0, parity_percentages[target]["feature_domains"])
            self.assertEqual(100.0, parity_percentages[target]["option_catalogs"])
            self.assertEqual(100.0, parity_percentages[target]["option_entries"])
            self.assertEqual(100.0, parity_percentages[target]["option_catalog_consumers"])
            self.assertEqual(100.0, parity_percentages[target]["config_keys"])
            self.assertEqual(100.0, parity_percentages[target]["generated_artifacts"])
            self.assertEqual(100.0, parity_percentages[target]["consumer_surfaces"])
            self.assertEqual(100.0, parity_percentages[target]["contract_surface_total"])
        self.assertEqual({"cpp": 0.0, "rust": 0.0}, parity_percentages["standalone_runtime"])
        self.assertEqual({"cpp": 0.0, "rust": 0.0}, parity_percentages["full_parity"])
        self.assertTrue(report["surface_contract"]["ok"], report["surface_contract"])
        self.assertEqual(
            list(audit.REQUIRED_GENERATED_ARTIFACT_NAMES),
            report["surface_contract"]["actual_generated_artifact_names"],
        )
        self.assertEqual(
            list(audit.REQUIRED_CONSUMER_SURFACE_NAMES),
            report["surface_contract"]["actual_consumer_surface_names"],
        )
        consumer_surfaces = report["surface_contract"]["consumer_surfaces_by_target"]
        for target in ("cpp", "rust"):
            with self.subTest(consumer_target=target):
                self.assertTrue(consumer_surfaces[target]["required"])
                self.assertEqual(
                    consumer_surfaces[target]["required"],
                    consumer_surfaces[target]["actual"],
                )
                self.assertEqual([], consumer_surfaces[target]["missing"])
                self.assertEqual([], consumer_surfaces[target]["extra"])
        for artifact in report["generated"]:
            self.assertEqual(report["contract_hash"], artifact["expected_contract_hash"])
            self.assertTrue(artifact["embeds_contract_hash"], artifact)
            self.assertEqual(artifact["expected_sha256"], artifact["actual_sha256"])
            self.assertEqual(64, len(artifact["actual_sha256"]))
        consumer_names = {str(consumer["name"]) for consumer in report["consumers"]}
        consumers = {str(consumer["name"]): consumer for consumer in report["consumers"]}
        self.assertIn("rust_native_account_runtime_is_present", consumer_names)
        self.assertIn("rust_strategy_runtime_uses_python_source_options", consumer_names)
        self.assertIn("rust_config_persistence_uses_python_source_options", consumer_names)
        self.assertIn("cpp_config_persistence_uses_python_source_options", consumer_names)
        self.assertIn("cpp_dashboard_uses_python_source_surface", consumer_names)
        self.assertIn("cpp_backtest_uses_python_source_surface", consumer_names)
        self.assertIn("cpp_backtest_service_api_uses_python_source_routes", consumer_names)
        self.assertIn("cpp_dashboard_llm_service_api_uses_python_source_routes", consumer_names)
        self.assertIn("cpp_llm_catalog_payload_fields_follow_python", consumer_names)
        self.assertIn("cpp_config_service_api_uses_python_source_routes", consumer_names)
        self.assertIn("cpp_chart_uses_python_source_surface", consumer_names)
        self.assertIn("cpp_native_chart_heatmap_uses_python_source_surface", consumer_names)
        self.assertIn("cpp_positions_uses_python_source_surface", consumer_names)
        self.assertIn("cpp_account_uses_python_service_api", consumer_names)
        self.assertIn("cpp_native_exchange_connectors_use_python_source_connectors", consumer_names)
        self.assertIn("cpp_native_strategy_runtime_uses_python_source_options", consumer_names)
        self.assertIn("cpp_dashboard_runtime_enforces_live_order_safety", consumer_names)
        self.assertIn("tauri_browser_consumes_generated_contract", consumer_names)
        self.assertIn("tauri_browser_service_api_uses_python_source_routes", consumer_names)
        self.assertIn("tauri_llm_catalog_uses_python_source_route", consumer_names)
        self.assertTrue(all(consumer["ok"] for consumer in report["consumers"]), report["consumers"])
        for consumer in report["consumers"]:
            self.assertEqual([], consumer["unknown_service_routes"], consumer)
            self.assertEqual([], consumer["unknown_route_extractors"], consumer)
        self.assertEqual(
            ["config", "backtest_run", "backtest", "backtest_stop"],
            consumers["cpp_backtest_service_api_uses_python_source_routes"]["extracted_service_route_names"],
        )
        self.assertEqual(
            [
                "llm_config",
                "llm_prompt",
                "llm_providers",
                "llm_local_model_status",
                "llm_local_model_start",
                "llm_local_model_pull",
                "llm_local_model_delete",
            ],
            consumers["cpp_dashboard_llm_service_api_uses_python_source_routes"]["extracted_service_route_names"],
        )
        self.assertIn(
            "control_start",
            consumers["tauri_browser_service_api_uses_python_source_routes"]["extracted_service_route_names"],
        )
        self.assertIn(
            "llm_prompt",
            consumers["tauri_browser_service_api_uses_python_source_routes"]["extracted_service_route_names"],
        )
        self.assertIn("native source sync audit", verify_all)
        self.assertIn("tools/audit_native_source_sync.py", verify_all)
        self.assertIn("Audit native source sync", ci_workflow)
        self.assertIn("tools/audit_native_source_sync.py", ci_workflow)
        self.assertIn("tools/audit_native_source_sync.py", hardening_checker)
        self.assertIn("Python-owned C++/Rust source synchronization", evidence_gates)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "native-source-sync-audit.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = audit.main(["--json", "--output", str(output_path)])

            self.assertEqual(0, exit_code)
            self.assertTrue(output_path.exists())
            self.assertEqual(json.loads(stdout.getvalue()), json.loads(output_path.read_text(encoding="utf-8")))

    def test_native_source_sync_audit_rejects_surface_contract_drift(self):
        audit = _load_repo_tool(
            "audit_native_source_sync",
            REPO_ROOT / "tools" / "audit_native_source_sync.py",
        )
        generated_artifacts = audit._generated_artifacts()
        consumer_requirements = audit._consumer_requirements()

        with patch.object(audit, "_generated_artifacts", return_value=generated_artifacts[:-1]):
            missing_artifact_report = audit.audit_native_source_sync()
        self.assertFalse(missing_artifact_report["ok"])
        self.assertIn(
            "missing required generated artifact(s): tauri_browser_generated_contract",
            missing_artifact_report["surface_contract"]["issues"],
        )

        with patch.object(audit, "_consumer_requirements", return_value=consumer_requirements[:-1]):
            missing_consumer_report = audit.audit_native_source_sync()
        expected_last_consumer_name = consumer_requirements[-1].name
        self.assertFalse(missing_consumer_report["ok"])
        self.assertIn(
            f"missing required consumer surface(s): {expected_last_consumer_name}",
            missing_consumer_report["surface_contract"]["issues"],
        )

        with patch.object(
            audit,
            "_consumer_requirements",
            return_value=(*consumer_requirements, consumer_requirements[-1]),
        ):
            duplicate_consumer_report = audit.audit_native_source_sync()
        self.assertFalse(duplicate_consumer_report["ok"])
        self.assertIn(
            f"duplicate consumer surface(s): {expected_last_consumer_name}",
            duplicate_consumer_report["surface_contract"]["issues"],
        )

        unexpected_consumer = audit.ConsumerRequirement(
            "unexpected_native_surface",
            consumer_requirements[0].path,
            consumer_requirements[0].required_text,
        )
        with patch.object(
            audit,
            "_consumer_requirements",
            return_value=(*consumer_requirements, unexpected_consumer),
        ):
            unexpected_consumer_report = audit.audit_native_source_sync()
        self.assertFalse(unexpected_consumer_report["ok"])
        self.assertIn(
            "unexpected consumer surface(s): unexpected_native_surface",
            unexpected_consumer_report["surface_contract"]["issues"],
        )

    def test_generated_parity_domains_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        source_domains = {domain.key: domain for domain in NATIVE_PARITY_DOMAINS}
        summary_domains = {str(domain["key"]): domain for domain in summary["domains"]}

        self.assertEqual(list(source_domains), list(summary_domains))
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        self.assertIn("pub struct PythonParityDomain", rust_generated)
        self.assertIn("pub const PYTHON_PARITY_DOMAINS", rust_generated)
        self.assertIn("struct PythonParityDomain", cpp_generated)
        self.assertIn("kPythonParityDomains", cpp_generated)
        self.assertNotIn('cpp_status: "C++ missing: "', rust_generated)
        self.assertNotIn('rust_status: "Rust missing: "', rust_generated)
        self.assertNotIn('"C++ missing: "', cpp_generated)
        self.assertNotIn('"Rust missing: "', cpp_generated)
        self.assertIn('key: "order_execution_and_risk"', rust_generated)
        self.assertIn('cpp_status: "Complete"', rust_generated)
        self.assertIn('rust_status: "Complete"', rust_generated)
        self.assertIn('required_before_full_parity: "C++: Complete | Rust: Complete"', rust_generated)
        self.assertIn('"order_execution_and_risk"', cpp_generated)
        self.assertIn('"Complete"', cpp_generated)

        for domain_key, source_domain in source_domains.items():
            summary_domain = summary_domains[domain_key]
            self.assertEqual(source_domain.title, summary_domain["title"])
            self.assertEqual(source_domain.python_surface, summary_domain["python_surface"])
            self.assertEqual(
                list(source_domain.cpp_required_before_full_parity),
                list(summary_domain["cpp_required_before_full_parity"]),
            )
            self.assertEqual(
                list(source_domain.rust_required_before_full_parity),
                list(summary_domain["rust_required_before_full_parity"]),
            )
            self.assertIn(f'key: "{domain_key}"', rust_generated)
            self.assertIn(f'PythonParityDomain{{"{domain_key}",', cpp_generated)

    def test_generated_service_routes_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        service_routes = {str(route["name"]): route for route in summary["service_routes"]}
        service_route_schemas = {str(schema["name"]): schema for schema in summary["service_route_schemas"]}

        self.assertEqual(list(SERVICE_API_ROUTE_SUFFIXES), list(service_routes))
        self.assertEqual(list(SERVICE_API_ROUTE_SUFFIXES), list(service_route_schemas))
        for route_name in SERVICE_API_ROUTE_SUFFIXES:
            self.assertEqual(SERVICE_API_ROUTE_PATHS[route_name], service_routes[route_name]["path"])
            self.assertEqual(
                list(SERVICE_API_ROUTE_METHODS[route_name]),
                service_routes[route_name]["methods"],
            )
            self.assertEqual(
                list(SERVICE_API_ROUTE_SCHEMAS[route_name]["query_fields"]),
                service_route_schemas[route_name]["query_fields"],
            )
            self.assertEqual(
                list(SERVICE_API_ROUTE_SCHEMAS[route_name]["request_fields"]),
                service_route_schemas[route_name]["request_fields"],
            )
            self.assertEqual(
                list(SERVICE_API_ROUTE_SCHEMAS[route_name]["response_fields"]),
                service_route_schemas[route_name]["response_fields"],
            )

        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)
        self.assertIn("pub struct PythonServiceRoute", rust_generated)
        self.assertIn("pub const PYTHON_SERVICE_ROUTES", rust_generated)
        self.assertIn("pub struct PythonServiceRouteSchema", rust_generated)
        self.assertIn("pub const PYTHON_SERVICE_ROUTE_SCHEMAS", rust_generated)
        self.assertIn("struct PythonServiceRoute", cpp_generated)
        self.assertIn("kPythonServiceRoutes", cpp_generated)
        self.assertIn("struct PythonServiceRouteSchema", cpp_generated)
        self.assertIn("kPythonServiceRouteSchemas", cpp_generated)
        self.assertIn('"serviceRoutePaths"', tauri_generated)
        self.assertIn('"serviceRouteMethods"', tauri_generated)
        self.assertIn('"serviceRouteSchemas"', tauri_generated)
        self.assertIn('"serviceRouteQueryFields"', tauri_generated)
        self.assertIn('"serviceRouteRequestFields"', tauri_generated)
        self.assertIn('"serviceRouteResponseFields"', tauri_generated)

        for route_name in SERVICE_API_ROUTE_SUFFIXES:
            route_path = SERVICE_API_ROUTE_PATHS[route_name]
            route_schema = SERVICE_API_ROUTE_SCHEMAS[route_name]
            rust_methods = ", ".join(f'"{method}"' for method in SERVICE_API_ROUTE_METHODS[route_name])
            rust_query_fields = ", ".join(json.dumps(str(field)) for field in route_schema["query_fields"])
            rust_request_fields = ", ".join(json.dumps(str(field)) for field in route_schema["request_fields"])
            rust_response_fields = ", ".join(json.dumps(str(field)) for field in route_schema["response_fields"])
            cpp_methods = ",".join(SERVICE_API_ROUTE_METHODS[route_name])
            cpp_query_fields = ",".join(route_schema["query_fields"])
            cpp_request_fields = ",".join(route_schema["request_fields"])
            cpp_response_fields = ",".join(route_schema["response_fields"])

            self.assertIn(f'name: "{route_name}"', rust_generated)
            self.assertIn(f'path: "{route_path}"', rust_generated)
            self.assertIn(f"methods: &[{rust_methods}]", rust_generated)
            self.assertIn(f"query_fields: &[{rust_query_fields}]", rust_generated)
            self.assertIn(f"request_fields: &[{rust_request_fields}]", rust_generated)
            self.assertIn(f"response_fields: &[{rust_response_fields}]", rust_generated)
            self.assertIn(
                f'PythonServiceRoute{{"{route_name}", "{route_path}", "{cpp_methods}"}}',
                cpp_generated,
            )
            self.assertIn(
                (
                    f'PythonServiceRouteSchema{{"{route_name}", "{cpp_query_fields}", '
                    f'"{cpp_request_fields}", "{cpp_response_fields}"}}'
                ),
                cpp_generated,
            )
            self.assertIn(f'"{route_name}": "{route_path}"', tauri_generated)
            for method in SERVICE_API_ROUTE_METHODS[route_name]:
                self.assertIn(f'"{method}"', tauri_generated)
            for fields in route_schema.values():
                for field in fields:
                    self.assertIn(json.dumps(str(field)), tauri_generated)

    def test_generated_indicator_catalog_matches_python_source_contract(self):
        summary = native_python_source_contract_summary()
        indicators = list(summary["indicators"])
        indicator_keys = [str(indicator["key"]) for indicator in indicators]

        self.assertEqual(list(summary["indicator_keys"]), indicator_keys)
        self.assertTrue(any(bool(indicator["default_enabled"]) for indicator in indicators))

        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)
        self.assertIn("pub struct PythonIndicator", rust_generated)
        self.assertIn("pub const PYTHON_INDICATOR_CATALOG", rust_generated)
        self.assertIn("struct PythonIndicator", cpp_generated)
        self.assertIn("kPythonIndicatorCatalog", cpp_generated)
        self.assertIn('"indicatorCatalog"', tauri_generated)

        for indicator in indicators:
            key = str(indicator["key"])
            display_name = str(indicator["display_name"])
            rust_enabled = str(bool(indicator["default_enabled"])).lower()
            cpp_enabled = rust_enabled
            js_key = json.dumps(key)
            js_name = json.dumps(display_name)
            cpp_runtime_config = _cpp_string(
                json.dumps(indicator["runtime_config"], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            )
            cpp_backtest_config = _cpp_string(
                json.dumps(indicator["backtest_config"], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            )
            cpp_runtime_output_keys = _cpp_string(",".join(str(value) for value in indicator["runtime_output_keys"]))

            self.assertIn(f"key: {js_key}", rust_generated)
            self.assertIn(f"display_name: {js_name}", rust_generated)
            self.assertIn(f"default_enabled: {rust_enabled}", rust_generated)
            self.assertIn(
                (
                    f"PythonIndicator{{{_cpp_string(key)}, {_cpp_string(display_name)}, {cpp_enabled}, "
                    f"{cpp_runtime_config}, {cpp_backtest_config}, {cpp_runtime_output_keys}}}"
                ),
                cpp_generated,
            )
            self.assertIn(f'"key": {js_key}', tauri_generated)
            self.assertIn(f'"name": {js_name}', tauri_generated)

    def test_generated_connector_and_llm_catalogs_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)

        self.assertIn("pub struct PythonConnectorOption", rust_generated)
        self.assertIn("pub const PYTHON_CONNECTOR_OPTIONS", rust_generated)
        self.assertIn("struct PythonConnectorOption", cpp_generated)
        self.assertIn("kPythonConnectorOptions", cpp_generated)
        self.assertIn('"connectorOptions"', tauri_generated)
        self.assertIn("pub struct PythonLlmProvider", rust_generated)
        self.assertIn("pub const PYTHON_LLM_PROVIDERS", rust_generated)
        self.assertIn("struct PythonLlmProvider", cpp_generated)
        self.assertIn("kPythonLlmProviders", cpp_generated)
        self.assertIn("pub const PYTHON_LLM_PROVIDER_CHOICES", rust_generated)
        self.assertIn("struct PythonLlmProviderChoice", cpp_generated)
        self.assertIn("kPythonLlmProviderChoices", cpp_generated)
        self.assertIn('"llmProviders"', tauri_generated)
        self.assertIn('"llmProviderChoices"', tauri_generated)
        self.assertIn('"configChoiceMaps"', tauri_generated)
        self.assertIn(
            f"PYTHON_LLM_PROVIDER_CATALOG_REVISION: &str = {_rust_string(summary['llm_catalog_revision'])}",
            rust_generated,
        )
        self.assertIn(
            f"kPythonLlmProviderCatalogRevision = {_cpp_string(summary['llm_catalog_revision'])}",
            cpp_generated,
        )
        self.assertIn(
            f"PYTHON_LLM_MODEL_CATALOG_PATH_ENV: &str = {_rust_string(summary['llm_model_catalog_path_env'])}",
            rust_generated,
        )
        self.assertIn(
            f"kPythonLlmModelCatalogPathEnv = {_cpp_string(summary['llm_model_catalog_path_env'])}",
            cpp_generated,
        )

        for connector in summary["connectors"]:
            key = json.dumps(str(connector["key"]))
            label = json.dumps(str(connector["label"]))
            rust_label = _rust_string(str(connector["label"]))
            self.assertIn(f"key: {key}", rust_generated)
            self.assertIn(f"label: {rust_label}", rust_generated)
            self.assertIn(f"PythonConnectorOption{{{key}, {label}}}", cpp_generated)
            self.assertIn(f'"key": {key}', tauri_generated)
            self.assertIn(f'"label": {label}', tauri_generated)

        for provider in summary["llm_providers"]:
            key = json.dumps(str(provider["key"]))
            label = json.dumps(str(provider["label"]))
            default_model = json.dumps(str(provider["default_model"]))
            api_key_env = json.dumps(str(provider["api_key_env"]))
            self.assertIn(f"key: {key}", rust_generated)
            self.assertIn(f"label: {label}", rust_generated)
            self.assertIn(f"default_model: {default_model}", rust_generated)
            self.assertIn(f"api_key_env: {api_key_env}", rust_generated)
            self.assertIn(
                f"catalog_revision: {_rust_string(str(provider['catalog_revision']))}",
                rust_generated,
            )
            self.assertIn(
                f"custom_models_env: {_rust_string(str(provider['custom_models_env']))}",
                rust_generated,
            )
            self.assertIn(
                f"custom_models_path_env: {_rust_string(str(provider['custom_models_path_env']))}",
                rust_generated,
            )
            for note in provider["notes"]:
                self.assertIn(_rust_string(str(note)), rust_generated)
            self.assertIn(f'"key": {key}', tauri_generated)
            self.assertIn(f'"label": {label}', tauri_generated)
            self.assertIn(f'"default_model": {default_model}', tauri_generated)
            self.assertIn(f'"api_key_env": {api_key_env}', tauri_generated)
            self.assertIn(
                f'"catalog_revision": {json.dumps(str(provider["catalog_revision"]))}',
                tauri_generated,
            )
            self.assertIn(
                f'"custom_models_env": {json.dumps(str(provider["custom_models_env"]))}',
                tauri_generated,
            )
            self.assertIn(
                f'"custom_models_path_env": {json.dumps(str(provider["custom_models_path_env"]))}',
                tauri_generated,
            )
            for note in provider["notes"]:
                self.assertIn(json.dumps(str(note)), tauri_generated)

        for choice in summary["llm_provider_choices"]:
            key = str(choice["key"])
            value = str(choice["value"])
            self.assertIn(
                f"({_rust_string(key)}, {_rust_string(value)}),",
                rust_generated,
            )
            self.assertIn(
                f"PythonLlmProviderChoice{{{_cpp_string(key)}, {_cpp_string(value)}}}",
                cpp_generated,
            )
            self.assertIn(f'"key": {json.dumps(key)}', tauri_generated)
            self.assertIn(f'"value": {json.dumps(value)}', tauri_generated)

        for name, choices in summary["config_choice_maps"].items():
            rust_name = f"PYTHON_{name.upper()}_CONFIG_CHOICES"
            cpp_suffix = "".join(part.capitalize() for part in name.split("_"))
            cpp_name = f"kPython{cpp_suffix}ConfigChoices"
            self.assertIn(f"pub const {rust_name}", rust_generated)
            self.assertIn(cpp_name, cpp_generated)
            for key, value in choices.items():
                self.assertIn(
                    f"({_rust_string(str(key))}, {_rust_string(str(value))}),",
                    rust_generated,
                )
                self.assertIn(
                    f"PythonConfigChoice{{{_cpp_string(str(key))}, {_cpp_string(str(value))}}}",
                    cpp_generated,
                )

    def test_generated_runtime_option_catalogs_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)

        simple_arrays = {
            "default_chart_symbols": (
                "PYTHON_DEFAULT_CHART_SYMBOLS",
                "kPythonDefaultChartSymbols",
                "defaultChartSymbols",
            ),
            "default_execution_symbols": (
                "PYTHON_DEFAULT_EXECUTION_SYMBOLS",
                "kPythonDefaultExecutionSymbols",
                "defaultExecutionSymbols",
            ),
            "default_execution_intervals": (
                "PYTHON_DEFAULT_EXECUTION_INTERVALS",
                "kPythonDefaultExecutionIntervals",
                "defaultExecutionIntervals",
            ),
            "default_backtest_symbols": (
                "PYTHON_DEFAULT_BACKTEST_SYMBOLS",
                "kPythonDefaultBacktestSymbols",
                "defaultBacktestSymbols",
            ),
            "default_backtest_intervals": (
                "PYTHON_DEFAULT_BACKTEST_INTERVALS",
                "kPythonDefaultBacktestIntervals",
                "defaultBacktestIntervals",
            ),
            "chart_market_options": (
                "PYTHON_CHART_MARKET_OPTIONS",
                "kPythonChartMarketOptions",
                "chartMarketOptions",
            ),
            "account_mode_options": (
                "PYTHON_ACCOUNT_MODE_OPTIONS",
                "kPythonAccountModeOptions",
                "accountModeOptions",
            ),
        }
        for summary_key, (rust_name, cpp_name, js_name) in simple_arrays.items():
            with self.subTest(summary_key=summary_key):
                self.assertIn(rust_name, rust_generated)
                self.assertIn(cpp_name, cpp_generated)
                self.assertIn(f'"{js_name}"', tauri_generated)
                for value in summary[summary_key]:
                    encoded = json.dumps(str(value))
                    self.assertIn(encoded, rust_generated)
                    self.assertIn(encoded, cpp_generated)
                    self.assertIn(encoded, tauri_generated)

        option_groups = {
            "dashboard_loop_choices": (
                "PYTHON_DASHBOARD_LOOP_CHOICES",
                "kPythonDashboardLoopChoices",
                "dashboardLoopChoices",
            ),
            "lead_trader_options": (
                "PYTHON_LEAD_TRADER_OPTIONS",
                "kPythonLeadTraderOptions",
                "leadTraderOptions",
            ),
            "llm_use_for_options": (
                "PYTHON_LLM_USE_FOR_OPTIONS",
                "kPythonLlmUseForOptions",
                "llmUseForOptions",
            ),
            "dashboard_strategy_templates": (
                "PYTHON_DASHBOARD_STRATEGY_TEMPLATES",
                "kPythonDashboardStrategyTemplates",
                "dashboardStrategyTemplates",
            ),
            "backtest_templates": (
                "PYTHON_BACKTEST_TEMPLATES",
                "kPythonBacktestTemplates",
                "backtestTemplates",
            ),
            "side_options": (
                "PYTHON_SIDE_OPTIONS",
                "kPythonSideOptions",
                "sideOptions",
            ),
            "config_mode_options": (
                "PYTHON_CONFIG_MODE_OPTIONS",
                "kPythonConfigModeOptions",
                "configModeOptions",
            ),
            "theme_options": (
                "PYTHON_THEME_OPTIONS",
                "kPythonThemeOptions",
                "themeOptions",
            ),
            "design_options": (
                "PYTHON_DESIGN_OPTIONS",
                "kPythonDesignOptions",
                "designOptions",
            ),
            "indicator_source_options": (
                "PYTHON_INDICATOR_SOURCE_OPTIONS",
                "kPythonIndicatorSourceOptions",
                "indicatorSourceOptions",
            ),
            "indicator_ma_type_options": (
                "PYTHON_INDICATOR_MA_TYPE_OPTIONS",
                "kPythonIndicatorMaTypeOptions",
                "indicatorMaTypeOptions",
            ),
            "exchange_options": (
                "PYTHON_EXCHANGE_OPTIONS",
                "kPythonExchangeOptions",
                "exchangeOptions",
            ),
            "account_type_options": (
                "PYTHON_ACCOUNT_TYPE_OPTIONS",
                "kPythonAccountTypeOptions",
                "accountTypeOptions",
            ),
            "margin_mode_options": (
                "PYTHON_MARGIN_MODE_OPTIONS",
                "kPythonMarginModeOptions",
                "marginModeOptions",
            ),
            "position_mode_options": (
                "PYTHON_POSITION_MODE_OPTIONS",
                "kPythonPositionModeOptions",
                "positionModeOptions",
            ),
            "assets_mode_options": (
                "PYTHON_ASSETS_MODE_OPTIONS",
                "kPythonAssetsModeOptions",
                "assetsModeOptions",
            ),
            "order_type_options": (
                "PYTHON_ORDER_TYPE_OPTIONS",
                "kPythonOrderTypeOptions",
                "orderTypeOptions",
            ),
            "time_in_force_options": (
                "PYTHON_TIME_IN_FORCE_OPTIONS",
                "kPythonTimeInForceOptions",
                "timeInForceOptions",
            ),
            "signal_logic_options": (
                "PYTHON_SIGNAL_LOGIC_OPTIONS",
                "kPythonSignalLogicOptions",
                "signalLogicOptions",
            ),
            "mdd_logic_options": (
                "PYTHON_MDD_LOGIC_OPTIONS",
                "kPythonMddLogicOptions",
                "mddLogicOptions",
            ),
            "stop_loss_modes": (
                "PYTHON_STOP_LOSS_MODES",
                "kPythonStopLossModes",
                "stopLossModes",
            ),
            "stop_loss_scopes": (
                "PYTHON_STOP_LOSS_SCOPES",
                "kPythonStopLossScopes",
                "stopLossScopes",
            ),
            "scan_scope_options": (
                "PYTHON_SCAN_SCOPE_OPTIONS",
                "kPythonScanScopeOptions",
                "scanScopeOptions",
            ),
            "optimizer_mode_options": (
                "PYTHON_OPTIMIZER_MODE_OPTIONS",
                "kPythonOptimizerModeOptions",
                "optimizerModeOptions",
            ),
            "optimizer_metric_options": (
                "PYTHON_OPTIMIZER_METRIC_OPTIONS",
                "kPythonOptimizerMetricOptions",
                "optimizerMetricOptions",
            ),
            "backtest_execution_backend_options": (
                "PYTHON_BACKTEST_EXECUTION_BACKEND_OPTIONS",
                "kPythonBacktestExecutionBackendOptions",
                "backtestExecutionBackendOptions",
            ),
            "chart_view_options": (
                "PYTHON_CHART_VIEW_OPTIONS",
                "kPythonChartViewOptions",
                "chartViewOptions",
            ),
            "positions_view_options": (
                "PYTHON_POSITIONS_VIEW_OPTIONS",
                "kPythonPositionsViewOptions",
                "positionsViewOptions",
            ),
        }
        self.assertIn("pub struct PythonUiOption", rust_generated)
        self.assertIn("struct PythonUiOption", cpp_generated)
        self.assertIn("disabled: bool", rust_generated)
        self.assertIn("bool disabled", cpp_generated)
        for summary_key, (rust_name, cpp_name, js_name) in option_groups.items():
            with self.subTest(summary_key=summary_key):
                self.assertIn(rust_name, rust_generated)
                self.assertIn(cpp_name, cpp_generated)
                self.assertIn(f'"{js_name}"', tauri_generated)
                for option in summary[summary_key]:
                    raw_key = option["key"] if "key" in option else option.get("value", "")
                    key = json.dumps(str(raw_key))
                    label = json.dumps(str(option["label"]))
                    disabled = str(bool(option.get("disabled", False))).lower()
                    rust_label = _rust_string(str(option["label"]))
                    self.assertIn(f"key: {key}", rust_generated)
                    self.assertIn(f"label: {rust_label}", rust_generated)
                    self.assertIn(f"disabled: {disabled}", rust_generated)
                    self.assertIn(f"PythonUiOption{{{key}, {label}, {disabled}}}", cpp_generated)
                    self.assertIn(f'"key": {key}', tauri_generated)
                    self.assertIn(f'"label": {label}', tauri_generated)
                    if "disabled" in option:
                        self.assertIn(f'"disabled": {disabled}', tauri_generated)

        self.assertIn("pub struct PythonTradingViewInterval", rust_generated)
        self.assertIn("kPythonTradingViewIntervalMap", cpp_generated)
        self.assertIn('"tradingviewIntervalMap"', tauri_generated)
        for interval, code in summary["tradingview_interval_map"].items():
            interval_json = json.dumps(str(interval))
            code_json = json.dumps(str(code))
            self.assertIn(f"interval: {interval_json}", rust_generated)
            self.assertIn(f"code: {code_json}", rust_generated)
            self.assertIn(f"PythonTradingViewInterval{{{interval_json}, {code_json}}}", cpp_generated)
            self.assertIn(f"{interval_json}: {code_json}", tauri_generated)

        self.assertIn('"defaultExecution"', tauri_generated)
        self.assertIn('"defaultBacktest"', tauri_generated)
        self.assertIn('"riskDefaults"', tauri_generated)
        self.assertIn('"uiDefaults"', tauri_generated)
        for key, value in summary["default_execution"].items():
            if isinstance(value, str):
                self.assertIn(f'"{key}": {json.dumps(value)}', tauri_generated)
        for key, value in summary["default_backtest"].items():
            if isinstance(value, str):
                self.assertIn(f'"{key}": {json.dumps(value)}', tauri_generated)
        for key, value in summary["ui_defaults"].items():
            self.assertIn(f'"{key}": {json.dumps(value)}', tauri_generated)

    def test_generated_starter_catalogs_match_python_source_contract(self):
        summary = native_python_source_contract_summary()
        rust_generated = _read(RUST_OUTPUT)
        cpp_generated = _read(CPP_OUTPUT)
        tauri_generated = _read(TAURI_BROWSER_OUTPUT)
        catalogs = {
            "code_language_options": (
                "PYTHON_CODE_LANGUAGE_OPTIONS",
                "kPythonCodeLanguageOptions",
                "codeLanguageOptions",
            ),
            "rust_framework_options": (
                "PYTHON_RUST_FRAMEWORK_OPTIONS",
                "kPythonRustFrameworkOptions",
                "rustFrameworkOptions",
            ),
            "starter_market_options": (
                "PYTHON_STARTER_MARKET_OPTIONS",
                "kPythonStarterMarketOptions",
                "starterMarketOptions",
            ),
        }
        self.assertIn("pub struct PythonStarterOption", rust_generated)
        self.assertIn("struct PythonStarterOption", cpp_generated)
        for summary_key, (rust_name, cpp_name, js_name) in catalogs.items():
            with self.subTest(summary_key=summary_key):
                self.assertIn(rust_name, rust_generated)
                self.assertIn(cpp_name, cpp_generated)
                self.assertIn(f'"{js_name}"', tauri_generated)
                for option in summary[summary_key]:
                    for field in ("key", "title", "subtitle", "accent", "badge"):
                        value = str(option[field])
                        self.assertIn(value, rust_generated)
                        self.assertIn(value, cpp_generated)
                        self.assertIn(json.dumps(value), tauri_generated)


if __name__ == "__main__":
    unittest.main()
