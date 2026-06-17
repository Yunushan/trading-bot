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
        core_cargo = _read(rust_root / "crates" / "core" / "Cargo.toml")
        market_data = _read(rust_root / "crates" / "core" / "src" / "market_data.rs")
        tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")
        slint_ui = _read(rust_root / "apps" / "slint-desktop" / "ui" / "main.slint")
        rust_readme = _read(rust_root / "README.md")

        self.assertIn("pub struct NativePythonAppParityDomain", core)
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
            self.assertIn(f'key: "{key}"', core)
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

    def test_rust_route_catalog_matches_python_service_contract(self):
        rust_root = REPO_ROOT / "experiments" / "rust-shells"
        core = _read(rust_root / "crates" / "core" / "src" / "lib.rs")
        tauri_html = _read(rust_root / "apps" / "tauri-desktop" / "ui" / "index.html")

        for route_name, suffix in SERVICE_API_ROUTE_SUFFIXES.items():
            route_path = f"/api/v1{suffix}"
            self.assertIn(f'name: "{route_name}"', core)
            self.assertIn(f'path: "{route_path}"', core)
            self.assertIn(f'{route_name}: "{route_path}"', tauri_html)
            methods = ", ".join(f'"{method}"' for method in SERVICE_API_ROUTE_METHODS[route_name])
            self.assertRegex(
                core,
                rf'name: "{re.escape(route_name)}",\s*path: "{re.escape(route_path)}",\s*methods: &\[{re.escape(methods)}\]',
            )

    def test_cpp_full_parity_boundary_is_explicit(self):
        cpp_root = REPO_ROOT / "experiments" / "native-cpp"
        readme = _read(cpp_root / "README.md")
        backtest_source = _read(cpp_root / "src" / "TradingBotWindow.backtest.cpp")
        support_source = _read(cpp_root / "src" / "TradingBotWindowSupport.cpp")
        account_source = _read(cpp_root / "src" / "TradingBotWindow.account.cpp")

        self.assertIn("Full feature parity with Python app | Not complete", readme)
        self.assertIn("Full Python app parity audit", readme)
        self.assertIn("Service API contract", readme)
        self.assertIn("Order execution and risk", readme)
        self.assertIn("Backtest engine", readme)
        self.assertIn("current symbol scan path is simulated", readme)
        self.assertIn("Backtest symbol scan simulated", backtest_source)
        self.assertIn("Connector '%1' is not implemented in C++ yet", support_source)
        self.assertIn("placeholderSymbolsForExchange", support_source)
        self.assertIn("API symbol sync is coming soon", account_source)


if __name__ == "__main__":
    unittest.main()
