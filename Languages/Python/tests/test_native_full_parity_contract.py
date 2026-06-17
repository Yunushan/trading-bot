import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api_contract import (  # noqa: E402
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_SUFFIXES,
    SERVICE_BACKTEST_RUN_REQUEST_FIELDS,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class NativeFullParityContractTests(unittest.TestCase):
    def test_rust_core_tracks_entire_python_app_parity_boundaries(self):
        rust_root = REPO_ROOT / "experiments" / "rust-shells"
        core = _read(rust_root / "crates" / "core" / "src" / "lib.rs")
        generated = _read(rust_root / "crates" / "core" / "src" / "generated_python_parity.rs")
        core_cargo = _read(rust_root / "crates" / "core" / "Cargo.toml")
        market_data = _read(rust_root / "crates" / "core" / "src" / "market_data.rs")
        tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")
        slint_ui = _read(rust_root / "apps" / "slint-desktop" / "ui" / "main.slint")
        rust_readme = _read(rust_root / "README.md")

        self.assertIn("PythonParityDomain as NativePythonAppParityDomain", core)
        self.assertIn("pub struct PythonParityDomain", generated)
        self.assertIn("pub const PYTHON_PARITY_DOMAINS", generated)
        self.assertIn("pub fn native_python_app_parity_domains", core)
        self.assertIn("pub fn native_full_python_app_parity_ready", core)
        self.assertIn("pub fn cpp_entire_python_app_parity_ready", core)
        self.assertIn("pub fn rust_entire_python_app_parity_ready", core)
        self.assertIn("Native Rust trading runtime ready: false", tauri_html)
        self.assertIn("Entire Python app parity ready: false", tauri_html)
        self.assertIn("C++ entire Python app parity ready: false", tauri_html)
        self.assertIn("Rust entire Python app parity ready: false", tauri_html)
        self.assertIn("Full Python App Parity Audit", tauri_html)
        self.assertIn("Full Python App Parity Audit", slint_ui)
        self.assertIn("native_full_python_app_parity_ready() == false", rust_readme)
        self.assertIn("pub mod market_data", core)
        self.assertIn("reqwest.workspace = true", core_cargo)
        self.assertIn("pub struct BinanceRestMarketDataClient", market_data)
        self.assertIn("pub fn fetch_usdt_symbols", market_data)
        self.assertIn("pub fn fetch_klines", market_data)
        self.assertIn("pub fn fetch_ticker_price", market_data)
        self.assertIn("parse_usdt_symbols", market_data)
        self.assertIn("sort_symbols_by_quote_volume", market_data)
        self.assertIn("parse_klines", market_data)
        self.assertIn("parse_ticker_price", market_data)
        self.assertIn("BinanceRestMarketDataClient", core)
        self.assertIn("BinanceRestMarketDataClient", tauri_html)
        self.assertIn("BinanceRestMarketDataClient", slint_ui)
        self.assertIn("BinanceRestMarketDataClient", rust_readme)

        domain_keys = (
            "desktop_shell_and_tabs",
            "service_api_contract",
            "config_persistence",
            "strategy_runtime",
            "exchange_connectors",
            "account_portfolio_positions",
            "order_execution_and_risk",
            "backtest_engine",
            "charts_and_heatmaps",
            "logs_terminal_diagnostics",
            "llm_advisory",
            "startup_packaging_platform",
        )
        for key in domain_keys:
            self.assertIn(f'key: "{key}"', generated)
            self.assertIn(key, tauri_html)
            self.assertIn(key, slint_ui)

        for renderer in (
            rust_root / "apps" / "egui-desktop" / "src" / "main.rs",
            rust_root / "apps" / "iced-desktop" / "src" / "main.rs",
            rust_root / "apps" / "dioxus-desktop" / "src" / "main.rs",
            rust_root / "src" / "main.rs",
        ):
            source = _read(renderer)
            self.assertIn("native_python_app_parity_domains", source, renderer)
            self.assertIn("native_full_python_app_parity_ready", source, renderer)

    def test_tauri_backtest_request_includes_canonical_python_fields(self):
        tauri_html = _read(
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html"
        )
        for control_id in (
            "backtest-scan-scope",
            "backtest-optimizer-mode",
            "backtest-optimizer-metric",
            "backtest-optimizer-combo-size",
            "backtest-optimizer-min-trades",
        ):
            self.assertIn(f'id="{control_id}"', tauri_html)
        self.assertIn("const scanScopeOptions = optionArray(pythonParityContract.scanScopeOptions)", tauri_html)
        self.assertIn("const optimizerModeOptions = optionArray(pythonParityContract.optimizerModeOptions)", tauri_html)
        self.assertIn("const optimizerMetricOptions = optionArray(pythonParityContract.optimizerMetricOptions)", tauri_html)
        match = re.search(
            r"const buildBacktestRequest = \(\) => \{(?P<body>.*?)\n    \};\n    const addCustomIntervals",
            tauri_html,
            flags=re.S,
        )
        self.assertIsNotNone(match, "buildBacktestRequest body should be discoverable")
        body = match.group("body")

        for field in SERVICE_BACKTEST_RUN_REQUEST_FIELDS:
            self.assertRegex(
                body,
                rf"\b{re.escape(field)}\s*:",
                f"Tauri backtest request is missing canonical Python field {field!r}",
            )
        self.assertIn('selectedValue("backtest-scan-scope")', body)
        self.assertIn('selectedValue("backtest-optimizer-mode")', body)
        self.assertIn('selectedValue("backtest-optimizer-metric")', body)
        self.assertIn('numberFrom("backtest-optimizer-combo-size", 2)', body)
        self.assertIn('numberFrom("backtest-optimizer-min-trades", 1)', body)
        self.assertIn('const snapshot = await pollBacktestUntilIdle("Run backtest")', tauri_html)
        self.assertIn('setText("backtest-scan-status-text", "Backtest cancellation requested...")', tauri_html)

    def test_rust_route_catalog_matches_python_service_contract(self):
        rust_root = REPO_ROOT / "experiments" / "rust-shells"
        core = _read(rust_root / "crates" / "core" / "src" / "lib.rs")
        generated = _read(rust_root / "crates" / "core" / "src" / "generated_python_parity.rs")
        tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")
        tauri_generated = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "generated-python-parity.js")

        self.assertIn("generated_python_parity::PYTHON_SERVICE_ROUTES", core)
        self.assertIn('src="generated-python-parity.js"', tauri_html)
        self.assertIn("pythonParityContract.serviceRoutePaths", tauri_html)
        self.assertIn("serviceRouteSupportsMethod", tauri_html)
        for route_name, suffix in SERVICE_API_ROUTE_SUFFIXES.items():
            route_path = f"/api/v1{suffix}"
            self.assertIn(f'name: "{route_name}"', generated)
            self.assertIn(f'path: "{route_path}"', generated)
            self.assertIn(f'"{route_name}": "{route_path}"', tauri_generated)
            methods = ", ".join(f'"{method}"' for method in SERVICE_API_ROUTE_METHODS[route_name])
            self.assertRegex(
                generated,
                rf'name: "{re.escape(route_name)}",\s*path: "{re.escape(route_path)}",\s*methods: &\[{re.escape(methods)}\]',
            )
            for method in SERVICE_API_ROUTE_METHODS[route_name]:
                self.assertIn(f'"{method}"', tauri_generated)

    def test_cpp_full_parity_boundary_is_explicit(self):
        cpp_root = REPO_ROOT / "experiments" / "native-cpp"
        readme = _read(cpp_root / "README.md")
        backtest_source = _read(cpp_root / "src" / "TradingBotWindow.backtest.cpp")
        dashboard_source = _read(cpp_root / "src" / "TradingBotWindow.dashboard_ui.cpp")
        support_source = _read(cpp_root / "src" / "TradingBotWindowSupport.cpp")
        account_source = _read(cpp_root / "src" / "TradingBotWindow.account.cpp")

        self.assertIn("Full feature parity with Python app | Not complete", readme)
        self.assertIn("Full Python app parity audit", readme)
        self.assertIn("Service API contract", readme)
        self.assertIn("Order execution and risk", readme)
        self.assertIn("Backtest engine", readme)
        self.assertIn("delegates run/stop to the Python Service API", readme)
        self.assertIn("ServiceApiJsonResult serviceApiRequestJson", support_source)
        self.assertIn("TradingBotWindowSupport::serviceApiRequestJson", backtest_source)
        self.assertIn('QStringLiteral("backtest_run")', backtest_source)
        self.assertIn('QStringLiteral("backtest_stop")', backtest_source)
        self.assertIn("appendBacktestRows(resultsTable_", backtest_source)
        self.assertIn("backtestScanScopeCombo_", backtest_source)
        self.assertIn("backtestOptimizerModeCombo_", backtest_source)
        self.assertIn("backtestOptimizerMetricCombo_", backtest_source)
        self.assertIn("backtestOptimizerComboSizeSpin_", backtest_source)
        self.assertIn('request.insert(QStringLiteral("scan_scope"), comboValue(backtestScanScopeCombo_', backtest_source)
        self.assertIn('request.insert(QStringLiteral("optimizer_mode"), comboValue(backtestOptimizerModeCombo_', backtest_source)
        self.assertIn('request.insert(QStringLiteral("optimizer_metric"), comboValue(backtestOptimizerMetricCombo_', backtest_source)
        self.assertIn("backtestSnapshotCancelled", backtest_source)
        self.assertIn('jsonNumber(snapshot, QStringLiteral("progress_percent")', backtest_source)
        self.assertIn("Python Service API backtest cancelled", backtest_source)
        self.assertIn("TradingBotWindowSupport::serviceApiRequestJson", dashboard_source)
        self.assertIn('QStringLiteral("PATCH")', dashboard_source)
        self.assertIn('QStringLiteral("llm_config")', dashboard_source)
        self.assertIn('QStringLiteral("POST")', dashboard_source)
        self.assertIn('QStringLiteral("llm_prompt")', dashboard_source)
        self.assertIn('QStringLiteral("llm_enabled")', dashboard_source)
        self.assertIn('QStringLiteral("dry_run")', dashboard_source)
        self.assertIn('QStringLiteral("llm_local_model_status")', dashboard_source)
        self.assertIn('QStringLiteral("llm_local_model_start")', dashboard_source)
        self.assertIn('QStringLiteral("llm_local_model_pull")', dashboard_source)
        self.assertIn('QStringLiteral("llm_local_model_delete")', dashboard_source)
        self.assertIn("Connector '%1' is not implemented in C++ yet", support_source)
        self.assertIn("placeholderSymbolsForExchange", support_source)
        self.assertIn("API symbol sync is coming soon", account_source)


if __name__ == "__main__":
    unittest.main()
