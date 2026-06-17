from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS  # noqa: E402
from app.gui.runtime.composition.module_state_constants import (  # noqa: E402
    BACKTEST_INTERVAL_ORDER,
    DASHBOARD_LOOP_CHOICES,
    DEFAULT_CHART_SYMBOLS,
    _connector_options,
)
from app.integrations.llm.providers import _PROVIDER_SPECS  # noqa: E402
from app.settings.indicators import INDICATOR_CATALOG  # noqa: E402


CPP_SRC = REPO_ROOT / "experiments" / "native-cpp" / "src"
RUST_CORE = REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs"
RUST_TAURI_HTML = REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html"
RUST_SLINT_UI = REPO_ROOT / "experiments" / "rust-shells" / "apps" / "slint-desktop" / "ui" / "main.slint"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_cpp_sources() -> str:
    return "\n".join(_read(path) for path in sorted(CPP_SRC.glob("TradingBotWindow*.cpp")))


def _connector_native_label(label: str) -> str:
    return (
        label.replace("USD\u24c8", "USD-S")
        .replace(" (Official Recommended)", "")
        .replace(" (Unified)", "")
        .replace(" (Community)", "")
    )


class NativeOptionParityTests(unittest.TestCase):
    maxDiff = None

    def assert_all_present(self, text: str, values: list[str], context: str) -> None:
        missing = [value for value in values if value not in text]
        self.assertEqual([], missing, f"{context} missing: {missing}")

    def test_cpp_surfaces_expose_python_intervals_symbols_and_indicators(self):
        indicator_names = [definition.display_name for definition in INDICATOR_CATALOG]
        option_files = {
            "dashboard": CPP_SRC / "TradingBotWindow.dashboard_ui.cpp",
            "backtest": CPP_SRC / "TradingBotWindow.backtest.cpp",
            "chart": CPP_SRC / "TradingBotWindow.chart.cpp",
        }

        for context, path in option_files.items():
            with self.subTest(context=context):
                text = _read(path)
                self.assert_all_present(text, BACKTEST_INTERVAL_ORDER, f"C++ {context} intervals")

        self.assert_all_present(
            _read(CPP_SRC / "TradingBotWindow.dashboard_ui.cpp"),
            DEFAULT_CHART_SYMBOLS,
            "C++ dashboard default symbols",
        )

        for context, path in {
            "dashboard": CPP_SRC / "TradingBotWindow.dashboard_ui.cpp",
            "backtest": CPP_SRC / "TradingBotWindow.backtest.cpp",
        }.items():
            with self.subTest(context=context):
                self.assert_all_present(_read(path), indicator_names, f"C++ {context} indicators")

    def test_cpp_supports_python_option_values_and_llm_catalog(self):
        text = _read_cpp_sources()
        connector_keys = [value for _, value in _connector_options()]
        connector_labels = [label for label, _ in _connector_options()]
        backtest_template_labels = [
            str(template["label"]) for template in BACKTEST_TEMPLATE_DEFINITIONS.values()
        ]

        self.assert_all_present(
            text,
            [
                "Demo",
                "Testnet",
                "Portfolio Margin",
                "Single-Asset Mode",
                "Multi-Assets Mode",
                "Time-in-Force",
                "GTD minutes",
                "GTC",
                "IOC",
                "FOK",
                "GTD",
            ],
            "C++ account/order options",
        )
        self.assert_all_present(text, [label for label, _ in DASHBOARD_LOOP_CHOICES], "C++ loop options")
        self.assert_all_present(text, connector_keys, "C++ connector keys")
        self.assert_all_present(text, connector_labels, "C++ connector labels")
        self.assert_all_present(text, backtest_template_labels, "C++ backtest template labels")

        for provider in _PROVIDER_SPECS:
            with self.subTest(provider=provider.key):
                self.assert_all_present(
                    text,
                    [
                        provider.label,
                        provider.default_base_url,
                        provider.default_model,
                        provider.api_key_env,
                        *provider.model_suggestions,
                    ],
                    f"C++ LLM provider {provider.key}",
                )

    def test_cpp_indicator_runtime_knows_python_indicator_keys(self):
        runtime_text = _read(CPP_SRC / "TradingBotWindow.dashboard_runtime_shared.cpp")
        dialog_text = _read(CPP_SRC / "TradingBotWindow.dashboard_indicator_dialog.cpp")
        indicator_keys = [definition.key for definition in INDICATOR_CATALOG]

        self.assert_all_present(runtime_text, indicator_keys, "C++ indicator normalization keys")
        self.assert_all_present(dialog_text + runtime_text, indicator_keys, "C++ indicator dialog keys")

    def test_rust_surfaces_expose_python_intervals_symbols_and_indicators(self):
        indicator_names = [definition.display_name for definition in INDICATOR_CATALOG]
        rust_surfaces = {
            "core": _read(RUST_CORE),
            "tauri": _read(RUST_TAURI_HTML),
            "slint": _read(RUST_SLINT_UI),
        }

        for context, text in rust_surfaces.items():
            with self.subTest(context=context):
                self.assert_all_present(text, BACKTEST_INTERVAL_ORDER, f"Rust {context} intervals")
                self.assert_all_present(text, DEFAULT_CHART_SYMBOLS, f"Rust {context} symbols")
                self.assert_all_present(text, indicator_names, f"Rust {context} indicators")

    def test_rust_surfaces_expose_python_connectors_loops_and_templates(self):
        connector_keys = [value for _, value in _connector_options()]
        connector_labels = [_connector_native_label(label) for label, _ in _connector_options()]
        loop_labels = [label for label, _ in DASHBOARD_LOOP_CHOICES]
        loop_values = [value for _, value in DASHBOARD_LOOP_CHOICES]
        template_keys = list(BACKTEST_TEMPLATE_DEFINITIONS.keys())
        template_labels = [str(template["label"]) for template in BACKTEST_TEMPLATE_DEFINITIONS.values()]

        tauri_text = _read(RUST_TAURI_HTML)
        rust_summary_text = _read(RUST_CORE) + "\n" + _read(RUST_SLINT_UI)

        self.assert_all_present(tauri_text, connector_keys, "Rust Tauri connector keys")
        self.assertNotIn("binance-connector-python", tauri_text)
        self.assert_all_present(tauri_text, loop_values, "Rust Tauri loop values")
        self.assert_all_present(tauri_text, template_keys, "Rust Tauri template keys")

        for context, text in {"tauri": tauri_text, "summary": rust_summary_text}.items():
            with self.subTest(context=context):
                self.assert_all_present(text, connector_labels, f"Rust {context} connector labels")
                self.assert_all_present(text, loop_labels, f"Rust {context} loop labels")
                self.assert_all_present(text, template_labels, f"Rust {context} template labels")


if __name__ == "__main__":
    unittest.main()
