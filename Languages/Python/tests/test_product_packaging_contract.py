import json
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api_contract import (  # noqa: E402
    SERVICE_API_DASHBOARD_ROUTE_NAMES,
    SERVICE_API_MOBILE_ROUTE_NAMES,
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_SUFFIXES,
    service_api_contract_payload,
)
from tools.service_test_manifest import SERVICE_TEST_MODULES, render_markdown_section  # noqa: E402


class _ElementIdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)


def _html_ids(markup: str) -> set[str]:
    parser = _ElementIdParser()
    parser.feed(markup)
    return parser.ids


def _run_service_api_contract_checker(checker_path: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [sys.executable, str(checker_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError as exc:
        if sys.platform != "win32" or getattr(exc, "winerror", None) not in {6, 50}:
            raise
        # Some embedded Windows runners fail while duplicating subprocess capture
        # handles. Keep this test covering the checker by invoking the same entry
        # point in-process for that runner failure only.
        from tools.check_service_api_contracts import main as check_service_api_contracts_main

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = check_service_api_contracts_main([])
        return subprocess.CompletedProcess(
            [sys.executable, str(checker_path)],
            returncode,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        )


class ProductPackagingContractTests(unittest.TestCase):
    def test_pyright_config_resolves_app_imports_for_repo_wrappers(self):
        config = json.loads((REPO_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))

        self.assertIn("Languages/Python", config["extraPaths"])
        self.assertIn("apps/desktop-pyqt", config["include"])
        self.assertIn("apps/service-api", config["include"])
        self.assertIn("Languages/Python/app", config["include"])
        self.assertEqual("3.14", config["pythonVersion"])

    def test_windows_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("apps\\\\desktop-pyqt\\\\main.py", script)
        self.assertIn('"--paths", $repoRoot', script)
        self.assertIn('"--paths", $pythonRoot', script)
        self.assertIn('$env:BOT_DISABLE_PYTHONW_RELAUNCH = "1"', script)
        self.assertIn('$env:BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH = "1"', script)
        self.assertIn("PyInstaller failed with exit code", script)
        self.assertIn("Resolve-Path -LiteralPath $Python", script)
        self.assertIn('"--distpath", $distRoot', script)
        self.assertIn('"--workpath", $workRoot', script)
        self.assertIn('Join-Path $workRoot "release-info.json"', script)
        self.assertIn('Join-Path $distRoot "$Name.exe"', script)
        self.assertIn("& $pythonCommand @pyInstallerArgs", script)
        self.assertIn('-ArgumentList "--smoke"', script)
        self.assertIn("Packaged executable smoke failed with exit code", script)

    def test_windows_cpp_dependency_installer_passes_bootstrap_args_separately(self):
        script = (REPO_ROOT / "experiments" / "native-cpp" / "tools" / "install_cpp_dependencies.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('$PSStyle.OutputRendering = "PlainText"', script)
        self.assertIn("function Assert-QtKitInstalled", script)
        self.assertIn("Qt6WebEngineWidgetsConfig.cmake", script)
        self.assertIn("Qt6WebSocketsConfig.cmake", script)
        self.assertIn(
            'Invoke-Checked -Label "Bootstrapping vcpkg" -Command @((Join-Path $localVcpkg "bootstrap-vcpkg.bat"), "-disableMetrics")',
            script,
        )
        self.assertNotIn('Join-Path $localVcpkg "bootstrap-vcpkg.bat", "-disableMetrics"', script)

    def test_rust_desktop_shells_surface_full_trading_tabs(self):
        rust_root = REPO_ROOT / "experiments" / "rust-shells"
        core = (rust_root / "crates" / "core" / "src" / "lib.rs").read_text(encoding="utf-8")
        generated_core = (rust_root / "crates" / "core" / "src" / "generated_python_parity.rs").read_text(
            encoding="utf-8"
        )
        generated_tauri = (rust_root / "apps" / "tauri-desktop" / "ui" / "generated-python-parity.js").read_text(
            encoding="utf-8"
        )
        tab_labels = (
            "Dashboard",
            "Chart",
            "Positions",
            "Backtest",
            "Liquidation Heatmap",
            "Code Languages",
        )
        mirrored_dashboard_controls = (
            "Account & Status",
            "AI / LLM Settings",
            "Exchange",
            "Markets & Intervals",
            "Strategy Controls",
            "Indicators",
            "Symbol / Interval Overrides",
            "Desktop Service API",
            "All Logs",
            "Position Trigger Logs",
            "Waiting Positions (Queue)",
            "Refresh Logs",
            "Advisory Prompt",
            "System Prompt",
            "Prepare Advisory Request",
            "Run Advisory",
            "LLM advisory result",
        )
        mirrored_table_columns = (
            "Triggered Indicator Value",
            "Current Indicator Value",
            "Stop-Loss Options",
            "Max Drawdown During Position (USDT)",
            "Usage Change Counter",
        )

        self.assertIn("pub fn trading_app_tabs", core)
        self.assertIn("pub fn service_api_routes", core)
        self.assertIn("pub fn service_api_capabilities", core)
        self.assertIn("pub fn rust_execution_modes", core)
        self.assertIn("pub fn rust_shell_framework_parity", core)
        self.assertIn("pub fn rust_native_runtime_capabilities", core)
        self.assertIn("pub fn rust_native_trading_runtime_ready", core)
        self.assertIn("pub fn rust_trading_execution_supported", core)
        self.assertIn("Native Rust trading engine", core)
        self.assertIn("trading_execution_supported: false", core)
        self.assertIn("Native Runtime Gap", core)
        self.assertIn("REST market data", core)
        self.assertIn("WebSocket market stream", core)
        self.assertIn("Account, balance, and positions", core)
        self.assertIn("Order submission", core)
        self.assertIn("Runtime lifecycle loop", core)
        self.assertIn("Risk and shutdown guards", core)
        self.assertIn("BinanceRestClient", core)
        self.assertIn("BinanceWsClient", core)
        self.assertIn("generated_python_parity::PYTHON_SERVICE_ROUTES", core)
        self.assertIn('name: "control_start"', generated_core)
        self.assertIn('path: "/api/v1/control/start"', generated_core)
        self.assertIn('name: "llm_local_model_pull"', generated_core)
        self.assertIn('path: "/api/v1/llm/local-model/pull"', generated_core)
        self.assertIn("Managed Local Service API", core)
        self.assertIn("Backtest Scanner & Dashboard Import", core)
        self.assertIn("LLM Advisory & Local Lifecycle", core)
        self.assertIn("Operational Service API client", core)
        self.assertIn("only user-selectable Rust desktop shell", core)
        self.assertIn("Execution Boundary", core)
        self.assertIn("default_model", core)
        self.assertIn("qwen3:8b", core)
        for parity_text in (
            "Alibaba Qwen / DashScope",
            "Bybit (ccxt order routing)",
            "PYTHON_BACKTEST_INTERVALS",
            "Open In Browser URL",
            "Max MDD Scanner Top N",
            "Max MDD Scanner Max MDD %",
            "Remove Selected",
        ):
            self.assertIn(parity_text, core + "\n" + generated_core)
        for label in (*tab_labels, *mirrored_dashboard_controls, *mirrored_table_columns):
            self.assertIn(label, core)

        tauri_html = (rust_root / "apps" / "tauri-desktop" / "ui" / "index.html").read_text(encoding="utf-8")
        tauri_browser_surface = tauri_html + "\n" + generated_tauri
        tauri_main = (rust_root / "apps" / "tauri-desktop" / "src" / "main.rs").read_text(encoding="utf-8")
        tauri_config = tomllib.loads((rust_root / "apps" / "tauri-desktop" / "Cargo.toml").read_text(encoding="utf-8"))
        tauri_app_config = json.loads((rust_root / "apps" / "tauri-desktop" / "tauri.conf.json").read_text(encoding="utf-8"))
        tauri_behavior = (
            rust_root / "apps" / "tauri-desktop" / "ui" / "tauri-ui-behavior.js"
        ).read_text(encoding="utf-8")
        tauri_behavior_test = (
            rust_root / "apps" / "tauri-desktop" / "ui" / "tauri-ui-behavior.test.cjs"
        ).read_text(encoding="utf-8")
        rust_cli = (rust_root / "src" / "main.rs").read_text(encoding="utf-8")
        code_catalog = (REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "code" / "code_language_catalog.py").read_text(
            encoding="utf-8"
        )
        rust_selection = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "code" / "code_language_ui_selection_runtime.py"
        ).read_text(encoding="utf-8")
        rust_launcher = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "code" / "code_language_rust_launcher_runtime.py"
        ).read_text(encoding="utf-8")
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        runtime_ready_match = re.search(
            r"pub fn rust_native_trading_runtime_ready\(\) -> bool \{\s*(true|false)\s*\}",
            core,
        )
        self.assertIsNotNone(runtime_ready_match)
        runtime_ready_label = runtime_ready_match.group(1) if runtime_ready_match else ""
        self.assertIn("defaultModels", tauri_html)
        self.assertIn('src="generated-python-parity.js"', tauri_html)
        self.assertIn('src="tauri-ui-behavior.js"', tauri_html)
        for code_language in ("Python", "C++", "Rust"):
            self.assertIn(f'data-code-language="{code_language}"', tauri_html)
        self.assertIn("selectCodeLanguage", tauri_html)
        self.assertIn("Open Python desktop?", tauri_html)
        self.assertIn("Open C++ desktop?", tauri_html)
        self.assertIn('invoke("launch_desktop_language"', tauri_html)
        self.assertIn("code-language-status-text", tauri_html)
        self.assertIn('id="rust-framework-panel"', tauri_html)
        self.assertIn('data-rust-framework="Tauri"', tauri_html)
        self.assertIn("window.PythonParityContract", generated_tauri)
        self.assertIn('"connectorOptions"', generated_tauri)
        self.assertIn('"llmProviders"', generated_tauri)
        self.assertIn('"defaultChartSymbols"', generated_tauri)
        self.assertIn('"defaultExecution"', generated_tauri)
        self.assertIn('"defaultBacktest"', generated_tauri)
        self.assertIn('"dashboardLoopChoices"', generated_tauri)
        self.assertIn('"leadTraderOptions"', generated_tauri)
        self.assertIn('"llmUseForOptions"', generated_tauri)
        self.assertIn('"dashboardStrategyTemplates"', generated_tauri)
        self.assertIn('"backtestTemplates"', generated_tauri)
        self.assertIn('"configModeOptions"', generated_tauri)
        self.assertIn('"themeOptions"', generated_tauri)
        self.assertIn('"designOptions"', generated_tauri)
        self.assertIn('"indicatorSourceOptions"', generated_tauri)
        self.assertIn('"exchangeOptions"', generated_tauri)
        self.assertIn('"accountTypeOptions"', generated_tauri)
        self.assertIn('"marginModeOptions"', generated_tauri)
        self.assertIn('"positionModeOptions"', generated_tauri)
        self.assertIn('"assetsModeOptions"', generated_tauri)
        self.assertIn('"timeInForceOptions"', generated_tauri)
        self.assertIn('"signalLogicOptions"', generated_tauri)
        self.assertIn('"chartViewOptions"', generated_tauri)
        self.assertIn('"positionsViewOptions"', generated_tauri)
        self.assertIn("pythonParityContract.serviceRoutePaths", tauri_html)
        self.assertIn("pythonParityContract.connectorOptions", tauri_html)
        self.assertIn("pythonParityContract.llmProviders", tauri_html)
        self.assertIn("pythonParityContract.defaultChartSymbols", tauri_html)
        self.assertIn("pythonParityContract.defaultExecution", tauri_html)
        self.assertIn("pythonParityContract.defaultBacktest", tauri_html)
        self.assertIn("pythonParityContract.dashboardLoopChoices", tauri_html)
        self.assertIn("pythonParityContract.leadTraderOptions", tauri_html)
        self.assertIn("pythonParityContract.llmUseForOptions", tauri_html)
        self.assertIn("pythonParityContract.dashboardStrategyTemplates", tauri_html)
        self.assertIn("pythonParityContract.backtestTemplates", tauri_html)
        self.assertIn("pythonParityContract.configModeOptions", tauri_html)
        self.assertIn("pythonParityContract.themeOptions", tauri_html)
        self.assertIn("pythonParityContract.designOptions", tauri_html)
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
        self.assertIn("serviceRouteSupportsMethod", tauri_html)
        self.assertIn("const tauriUiBehavior = window.TauriUiBehavior", tauri_html)
        self.assertIn("tauriUiBehavior.importBacktestRowsToDashboard", tauri_html)
        self.assertIn("tauriUiBehavior.selectBacktestScanBest", tauri_html)
        self.assertIn("tauriUiBehavior.describeLocalModelStatus", tauri_html)
        self.assertIn("tauriUiBehavior.mergeUniqueLines", tauri_html)
        self.assertIn("tauriUiBehavior.describeConfigPersistence", tauri_html)
        self.assertIn("tauriUiBehavior.formatPreflightLabel", tauri_html)
        self.assertIn("tauriUiBehavior.preflightStartBlocked", tauri_html)
        for behavior_hook in (
            "selectBacktestScanBest",
            "importBacktestRowsToDashboard",
            "backtestRunsFromPayload",
            "describeConfigPersistence",
            "describeOperationalPreflight",
            "describeOrderCircuit",
            "describeLastCircuitIncident",
            "describeCircuitIncidentCount",
            "describeLocalModelStatus",
            "overrideImportKey",
            "formatPreflightLabel",
            "preflightFreshnessAges",
            "preflightStartBlocked",
            "preflightStartDetail",
            "serviceLogItemsFromPayload",
            "formatServiceLogLine",
            "formatServiceLogs",
            "formatLlmPromptResult",
        ):
            self.assertIn(behavior_hook, tauri_behavior)
            self.assertIn(behavior_hook, tauri_behavior_test)
        self.assertIn("node experiments/rust-shells/apps/tauri-desktop/ui/tauri-ui-behavior.test.cjs", workflow)
        for llm_text in (
            "Mistral AI",
            "gpt-5.5-pro-2026-04-23",
            "gpt-4.1-nano",
            "claude-opus-4-5-20251101",
            "gemini-3.1-pro-preview",
            "grok-4.3",
            "qwen3.6-plus",
            "qwen3-coder-plus",
            "qwen3:0.6b",
            "deepseek-r1:8b",
            "gemma3:4b",
        ):
            self.assertIn(llm_text, core)
            self.assertIn(llm_text, tauri_browser_surface)
        for source in (tauri_html,):
            for label in (*tab_labels, *mirrored_dashboard_controls, *mirrored_table_columns):
                self.assertIn(label, source)
            self.assertIn("Bot Status", source)
            self.assertIn("Native Rust Runtime Gap", source)
            self.assertIn(f"Native Rust trading runtime ready: {runtime_ready_label}", source)
            self.assertIn("BinanceRestClient", source)
            self.assertIn("BinanceWsClient", source)
        for tauri_parity_text in (
            "Alibaba Qwen / DashScope",
            "Bybit (ccxt order routing)",
            "Remove Selected",
            "Max MDD Scanner",
        ):
            self.assertIn(tauri_parity_text, tauri_browser_surface)
        for operational_text in (
            "Operational Service API client",
            "operational_status",
            '"usage": "Active"',
        ):
            self.assertIn(operational_text, code_catalog)
        for removed_framework in ("Slint", "egui", "Iced", "Dioxus Desktop"):
            self.assertNotIn(removed_framework, code_catalog)
        self.assertNotIn("evaluation-only", rust_selection)
        self.assertIn("This is the only Rust shell with interactive Service API client behavior today.", rust_selection)
        self.assertIn("Rust desktop shell", rust_launcher)
        self.assertTrue(tauri_app_config["app"]["withGlobalTauri"])
        self.assertIn("reqwest", tauri_config["dependencies"])
        self.assertIn("launch_desktop_language", tauri_main)
        self.assertIn("service_api_request", tauri_main)
        self.assertIn("start_service_api", tauri_main)
        self.assertIn("stop_service_api", tauri_main)
        self.assertIn("service_process_status", tauri_main)
        self.assertIn("ServiceProcessState", tauri_main)
        self.assertIn("desktop-pyqt", tauri_main)
        self.assertIn("Trading-Bot-C++", tauri_main)
        self.assertIn('join("apps").join("service-api").join("main.py")', tauri_main)
        self.assertIn('arg("--serve")', tauri_main)
        self.assertIn('arg("--load-config")', tauri_main)
        self.assertIn("service_api_route_path", tauri_main)
        for route_name, suffix in SERVICE_API_ROUTE_SUFFIXES.items():
            route_path = f"/api/v1{suffix}"
            self.assertIn(f'name: "{route_name}"', generated_core)
            self.assertIn(f'path: "{route_path}"', generated_core)
            self.assertIn(f'"{route_name}": "{route_path}"', generated_tauri)
            methods = ", ".join(f'"{method}"' for method in SERVICE_API_ROUTE_METHODS[route_name])
            self.assertRegex(
                generated_core,
                rf'name: "{re.escape(route_name)}",\s*path: "{re.escape(route_path)}",\s*methods: &\[{re.escape(methods)}\]',
            )
            for method in SERVICE_API_ROUTE_METHODS[route_name]:
                self.assertIn(f'"{method}"', generated_tauri)
        for element_id in (
            "start-bot-btn",
            "stop-bot-btn",
            "save-config-btn",
            "load-config-btn",
            "service-connect-btn",
            "service-stop-btn",
            "service-preflight-btn",
            "service-preflight-start",
            "service-preflight-orders",
            "service-preflight-mode",
            "service-preflight-critical",
            "service-preflight-ages",
            "service-preflight-message",
            "connector-order-circuit",
            "connector-incidents-count",
            "connector-last-incident",
            "connector-message",
            "reset-connector-circuit-btn",
            "apply-llm-btn",
            "run-backtest-btn",
            "refresh-positions-btn",
            "api-key-input",
            "api-secret-input",
            "config-persistence-state",
            "config-persistence-path",
            "account-available-balance",
            "account-source",
            "account-updated",
            "portfolio-source",
            "portfolio-open",
            "portfolio-closed",
            "exchange-connector-health",
            "exchange-connector-state",
            "exchange-connector-backend",
            "exchange-connector-updated",
            "refresh-logs-btn",
            "llm-prompt-input",
            "llm-system-prompt-input",
            "run-llm-dry-run-btn",
            "send-llm-advisory-btn",
            "llm-result-status",
            "llm-result-output",
            "config-account-mode",
            "config-design",
            "config-gtd-minutes",
            "refresh-balance-btn",
            "check-local-model-btn",
            "remove-local-model-btn",
            "custom-interval-input",
            "add-custom-interval-btn",
            "refresh-symbols-btn",
            "lead-trader-enabled",
            "lead-trader-profile",
            "indicator-live-values",
            "add-only-net-direction",
            "allow-opposite-positions",
            "stop-without-closing-positions",
            "close-on-window-close",
            "chart-refresh-btn",
            "chart-open-browser-btn",
            "chart-market-select",
            "chart-symbol-select",
            "chart-interval-select",
            "chart-view-select",
            "chart-tradingview-state",
            "chart-original-state",
            "chart-lightweight-state",
            "chart-status-text",
            "chart-open-url-text",
            "market-close-all-positions-btn",
            "positions-view-select",
            "positions-auto-row-height",
            "positions-auto-column-width",
            "positions-total-balance",
            "positions-available-balance",
            "positions-bot-status",
            "positions-active-time",
            "positions-clear-selected-btn",
            "positions-clear-all-btn",
            "runtime-overrides-table",
            "runtime-override-add-selected-btn",
            "runtime-override-remove-selected-btn",
            "runtime-override-clear-btn",
            "backtest-overrides-table",
            "backtest-override-add-selected-btn",
            "backtest-override-remove-selected-btn",
            "backtest-override-clear-btn",
            "backtest-add-selected-dashboard-btn",
            "backtest-add-all-dashboard-btn",
            "backtest-refresh-symbols-btn",
            "backtest-custom-interval-input",
            "backtest-add-custom-interval-btn",
            "backtest-start-date",
            "backtest-end-date",
            "backtest-mdd-logic",
            "backtest-position-pct",
            "backtest-loop-interval",
            "backtest-stop-loss-enabled",
            "backtest-stop-loss-mode",
            "backtest-stop-loss-scope",
            "backtest-stop-loss-usdt",
            "backtest-stop-loss-percent",
            "backtest-side",
            "backtest-margin-mode",
            "backtest-position-mode",
            "backtest-assets-mode",
            "backtest-account-mode",
            "backtest-connector",
            "backtest-leverage",
            "backtest-template-enabled",
            "backtest-template-name",
            "backtest-scan-top-n",
            "backtest-scan-mdd-limit",
            "backtest-scan-symbols-btn",
            "backtest-scan-status-text",
            "backtest-scan-best-text",
            "local-model-status-text",
            "rust-native-runtime-gap",
        ):
            self.assertIn(f'id="{element_id}"', tauri_html)
        for tauri_command in (
            'invoke("launch_desktop_language"',
            'invoke("start_service_api"',
            'invoke("stop_service_api"',
            'invoke("service_api_request"',
        ):
            self.assertIn(tauri_command, tauri_html)
        self.assertIn(
            'setChecked("stop-without-closing-positions", config.stop_without_close)',
            tauri_html,
        )
        self.assertIn(
            'stop_without_close: Boolean($("stop-without-closing-positions")?.checked)',
            tauri_html,
        )
        for hydration_hook in (
            "hydrateConfigControls",
            "hydrateLlmControls",
            "hydrateBacktestControls",
            "hydrateFromDashboard",
            "llm_reasoning_effort",
            "llm_allow_public_network",
            "llm_local_model_status",
            "llm_local_model_start",
            "llm_local_model_pull",
            "llm_local_model_delete",
            "checkOrDownloadLocalModel",
            "removeLocalModel",
            "refreshLocalModelStatus",
            "ensureLocalModelServer",
            "localModelStorageText",
            "buildLlmPromptPayload",
            "renderLlmPromptResult",
            "runLlmPrompt",
            "llm_prompt",
            "dry_run: Boolean",
            "Prepare LLM advisory",
            "Run LLM advisory",
            "account_mode",
            "tif",
            "gtd_minutes",
            "indicator_source",
            "loop_interval_override",
            "lead_trader_enabled",
            "lead_trader_profile",
            "indicator_use_live_values",
            "add_only",
            "allow_opposite_positions",
            "stop_without_close",
            "close_on_exit",
            "close_positions: !Boolean",
            "start_date",
            "end_date",
            "mdd_logic",
            "scan_top_n",
            "scan_mdd_limit",
            "scan: true",
            "stop_loss",
            "template",
            "indicatorCatalog",
            "pythonParityContract.indicatorCatalog",
            "indicatorKeyByName",
            "data-indicator-key",
            "selectedIndicatorKeysForKind",
            "selectedIndicatorsConfigForKind",
            "overrideRowsForRequest",
            "hydrateChartControls",
            "renderChartState",
            "buildChartConfigPatch",
            "chartUrl",
            "chartDefaultSymbols",
            "chartDefaultIntervals",
            "chartIntervalMap",
            "renderPositionsTableRows",
            "normalizePositionRows",
            "collapsePositionRows",
            "syncPositionsTableOptions",
            "positions_auto_resize_rows",
            "positions_auto_resize_columns",
            "runtime_symbol_interval_pairs",
            "backtest_symbol_interval_pairs",
            "pair_overrides",
            "renderOverrideRows",
            "addSymbolIntervalOverrides",
            "removeSelectedOverrides",
            "clearOverrides",
            "strategyControlsForKind",
            "lastBacktestRows",
            "backtestRunsFromPayload",
            "renderBacktestResultsTable",
            "backtestResultToDashboardOverride",
            "addBacktestRowsToDashboard",
            "buildBacktestScanRequest",
            "selectBacktestScanBest",
            "selectBacktestResultRow",
            "pollBacktestUntilIdle",
            "runBacktestScan",
            "mergeTextareaLines",
            "overrideImportKey",
            "refreshOperationalPreflight",
            "setPreflightSnapshot",
            "Start blocked by preflight",
            "Start bot rejected",
            "renderPreflightDetails",
            "renderConnectorCircuit",
            "refreshConnectorCircuit",
            "renderAccountSnapshot",
            "renderPortfolioSnapshot",
            "renderExchangeConnectorSnapshot",
            "refreshOperationalSnapshots",
            "connector_order_circuit_breaker",
            "connector_order_circuit_breaker_reset",
            "connector_order_circuit_incidents",
            "Refresh account",
            "Refresh portfolio",
            "Refresh exchange connector",
            "renderServiceLogs",
            "refreshServiceLogs",
            "Refresh logs",
            "renderConfigPersistence",
            "refreshConfigPersistence",
            "config_persistence",
        ):
            self.assertIn(hydration_hook, tauri_html)
        for chart_text in ("DOGEUSDT", "AVAXUSDT", "1month", "2y"):
            self.assertIn(chart_text, tauri_browser_surface)
        self.assertIn('symbol.endsWith("USDT") && !symbol.endsWith(".P")', tauri_html)
        self.assertIn("symbol = `${symbol}.P`", tauri_html)
        self.assertIn("`BINANCE:${symbol}`", tauri_html)

        self.assertIn("rust_native_runtime_capabilities", rust_cli)
        self.assertIn("rust_native_trading_runtime_ready", rust_cli)
        self.assertFalse((rust_root / "apps" / "slint-desktop").exists())
        self.assertFalse((rust_root / "apps" / "egui-desktop").exists())
        self.assertFalse((rust_root / "apps" / "iced-desktop").exists())
        self.assertFalse((rust_root / "apps" / "dioxus-desktop").exists())

    def test_unix_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_binary.sh").read_text(encoding="utf-8")
        self.assertIn('DESKTOP_ENTRY_SCRIPT="${REPO_ROOT}/apps/desktop-pyqt/main.py"', script)
        self.assertIn('--paths "${REPO_ROOT}"', script)
        self.assertIn('--paths "${PYTHON_ROOT}"', script)
        self.assertIn(
            'BOT_DISABLE_PYTHONW_RELAUNCH=1 BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH=1 "${PYTHON_BIN}" "${pyinstaller_args[@]}"',
            script,
        )
        self.assertIn('QT_QPA_PLATFORM=offscreen "${binary_path}" --smoke', script)
        self.assertIn("Packaged executable smoke passed.", script)

    def test_docker_backend_uses_canonical_service_wrapper_and_dashboard_assets(self):
        dockerfile = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "FROM cgr.dev/chainguard/python:latest-dev@sha256:31d318170df60ddec4b04ed595cbe79c33eeb2cf94f9676db6f9eaf46542e6be AS builder",
            dockerfile,
        )
        self.assertIn(
            "FROM cgr.dev/chainguard/python:latest@sha256:2c6a2e8bdeb1336cd8545d3586d1c1e5b4f7564ef00924b0447ebfbe57a549ee",
            dockerfile,
        )
        self.assertIn("COPY --chown=65532:65532 apps/service-api /app/apps/service-api", dockerfile)
        self.assertIn("COPY --chown=65532:65532 apps/web-dashboard /app/apps/web-dashboard", dockerfile)
        self.assertIn("COPY Languages/Python/pyproject.toml Languages/Python/README.md", dockerfile)
        self.assertIn("COPY --chown=65532:65532 Languages/Python/app /app/Languages/Python/app", dockerfile)
        self.assertIn("COPY --chown=65532:65532 Languages/Python/trading_core /app/Languages/Python/trading_core", dockerfile)
        self.assertNotIn("COPY Languages/Python /app/Languages/Python", dockerfile)
        self.assertIn("# syntax=docker/dockerfile:1.7", dockerfile)
        self.assertIn("--mount=type=secret,id=pip_ca,required=false", dockerfile)
        self.assertIn("PIP_CERT=/run/secrets/pip_ca", dockerfile)
        self.assertIn('python -m pip install --upgrade "pip==26.1.2"', dockerfile)
        self.assertIn('ENTRYPOINT ["/opt/venv/bin/python"]', dockerfile)
        self.assertIn('CMD ["apps/service-api/main.py"', dockerfile)
        self.assertIn("USER 65532", dockerfile)
        self.assertIn("apk add --no-cache build-base linux-headers", dockerfile)
        self.assertIn("Build and health-check Python 3.14 service container", ci_workflow)
        self.assertIn("docker build --pull --file docker/backend.Dockerfile", ci_workflow)
        self.assertIn("http://127.0.0.1:18000/readyz", ci_workflow)
        self.assertIn("BOT_SERVICE_API_TRUST_LOOPBACK_PROXY=1", ci_workflow)
        self.assertIn("BOT_SERVICE_API_TOKEN=ci-service-token-for-nonloopback-smoke-0123456789", ci_workflow)
        self.assertIn("--read-only", ci_workflow)
        self.assertIn("--tmpfs /tmp:mode=1777", ci_workflow)
        self.assertIn("--security-opt no-new-privileges:true", ci_workflow)
        self.assertIn("--cap-drop ALL", ci_workflow)
        compose = (REPO_ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:8000:8000"', compose)
        self.assertIn('BOT_SERVICE_API_TRUST_LOOPBACK_PROXY: "1"', compose)
        self.assertIn('user: "10001:10001"', compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertIn("cap_drop:", compose)
        self.assertIn("- ALL", compose)
        self.assertIn("trading-bot-service-data:/home/tradingbot/.trading-bot", compose)
        dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("# Allowlist only the runtime files", dockerignore)
        self.assertIn("!Languages/Python/app/**", dockerignore)
        self.assertIn("!Languages/Python/trading_core/**", dockerignore)
        self.assertNotIn("!Languages/Python/tests/**", dockerignore)

    def test_web_dashboard_surfaces_exchange_connector_health(self):
        dashboard_dir = REPO_ROOT / "apps" / "web-dashboard"
        index = (dashboard_dir / "index.html").read_text(encoding="utf-8")
        state = (dashboard_dir / "modules" / "state.js").read_text(encoding="utf-8")
        render = (dashboard_dir / "modules" / "render.js").read_text(encoding="utf-8")
        app = (dashboard_dir / "app.js").read_text(encoding="utf-8")

        for element_id in (
            "status-operational",
            "connector-health",
            "connector-state",
            "connector-backend",
            "connector-rate-limit",
            "connector-network",
            "connector-updated",
            "connector-last-error",
            "connector-message",
            "connector-incident-log",
            "connector-last-incident",
            "connector-incidents-count",
            "connector-incidents-empty",
            "connector-incidents-list",
            "config-order-audit-max-bytes",
            "config-order-audit-backup-count",
            "config-incident-log-max-bytes",
            "config-incident-log-backup-count",
            "config-connector-stale-seconds",
            "config-execution-heartbeat-stale-seconds",
            "config-account-stale-seconds",
            "config-portfolio-stale-seconds",
            "config-live-start-gate-enabled",
            "config-live-order-gate-enabled",
            "config-persistence-state",
            "config-persistence-path",
            "save-config-file-button",
            "load-config-file-button",
            "runtime-lifecycle-mode",
            "runtime-execution-scope",
            "runtime-trading-execution",
            "preflight-state",
            "preflight-start",
            "preflight-orders",
            "preflight-mode",
            "preflight-critical",
            "preflight-ages",
            "preflight-recheck-button",
            "preflight-message",
            "preflight-remediation-count",
            "preflight-remediation-empty",
            "preflight-remediation-list",
            "start-gate-state",
            "control-lifecycle-mode",
            "control-execution-scope",
            "control-trading-execution",
        ):
            self.assertIn(f'id="{element_id}"', index)

        self.assertIn("runtimeLifecycleMode: document.getElementById(\"runtime-lifecycle-mode\")", state)
        self.assertIn("runtimeExecutionScope: document.getElementById(\"runtime-execution-scope\")", state)
        self.assertIn("runtimeTradingExecution: document.getElementById(\"runtime-trading-execution\")", state)
        self.assertIn("controlLifecycleMode: document.getElementById(\"control-lifecycle-mode\")", state)
        self.assertIn("controlExecutionScope: document.getElementById(\"control-execution-scope\")", state)
        self.assertIn("controlTradingExecution: document.getElementById(\"control-trading-execution\")", state)
        self.assertIn("connectorHealth: document.getElementById(\"connector-health\")", state)
        self.assertIn("statusOperational: document.getElementById(\"status-operational\")", state)
        self.assertIn("connectorIncidentLog: document.getElementById(\"connector-incident-log\")", state)
        self.assertIn("connectorLastIncident: document.getElementById(\"connector-last-incident\")", state)
        self.assertIn(
            "configOrderAuditMaxBytes: document.getElementById(\"config-order-audit-max-bytes\")",
            state,
        )
        self.assertIn(
            "configIncidentLogBackupCount: document.getElementById(\"config-incident-log-backup-count\")",
            state,
        )
        self.assertIn(
            "configConnectorStaleSeconds: document.getElementById(\"config-connector-stale-seconds\")",
            state,
        )
        self.assertIn(
            "configPortfolioStaleSeconds: document.getElementById(\"config-portfolio-stale-seconds\")",
            state,
        )
        self.assertIn(
            "configLiveStartGateEnabled: document.getElementById(\"config-live-start-gate-enabled\")",
            state,
        )
        self.assertIn(
            "configLiveOrderGateEnabled: document.getElementById(\"config-live-order-gate-enabled\")",
            state,
        )
        self.assertIn(
            "configPersistenceState: document.getElementById(\"config-persistence-state\")",
            state,
        )
        self.assertIn(
            "configPersistencePath: document.getElementById(\"config-persistence-path\")",
            state,
        )
        self.assertIn("saveConfigFileButton: document.getElementById(\"save-config-file-button\")", state)
        self.assertIn("loadConfigFileButton: document.getElementById(\"load-config-file-button\")", state)
        self.assertIn("preflightState: document.getElementById(\"preflight-state\")", state)
        self.assertIn("preflightOrders: document.getElementById(\"preflight-orders\")", state)
        self.assertIn("preflightAges: document.getElementById(\"preflight-ages\")", state)
        self.assertIn(
            "preflightRecheckButton: document.getElementById(\"preflight-recheck-button\")",
            state,
        )
        self.assertIn(
            "preflightRemediationCount: document.getElementById(\"preflight-remediation-count\")",
            state,
        )
        self.assertIn(
            "preflightRemediationEmpty: document.getElementById(\"preflight-remediation-empty\")",
            state,
        )
        self.assertIn(
            "preflightRemediationList: document.getElementById(\"preflight-remediation-list\")",
            state,
        )
        self.assertIn("startGateState: document.getElementById(\"start-gate-state\")", state)
        self.assertIn("function renderExchangeConnector", render)
        self.assertIn("function controlPlaneLifecycleSummary", render)
        self.assertIn("Desktop Forwarded", render)
        self.assertIn("Heartbeat Only", render)
        self.assertIn("Intent Only", render)
        self.assertIn("elements.controlModeHint.textContent = lifecycle.summary", render)
        self.assertIn("export function renderPreflight", render)
        self.assertIn("function preflightFreshnessAges", render)
        self.assertIn("function preflightFreshnessRemediations", render)
        self.assertIn("function renderPreflightRemediations", render)
        self.assertIn("Execution heartbeat", render)
        self.assertIn("elements.preflightAges.textContent", render)
        self.assertIn("elements.preflightRemediationEmpty.style.display", render)
        self.assertIn("elements.preflightRemediationList.innerHTML", render)
        self.assertIn("function updateStartControlFromPreflight", render)
        self.assertIn("requestStartButton.disabled = blocked", render)
        self.assertIn("Lifecycle Start Blocked", render)
        self.assertIn("function renderCircuitIncidentLog", render)
        self.assertIn("function renderLastCircuitIncident", render)
        self.assertIn("function renderConnectorIncidents", render)
        self.assertIn("payload.operational?.preflight", render)
        self.assertIn('serviceApiRoute("operational_preflight")', app)
        self.assertIn("function recheckPreflight", app)
        self.assertIn("preflightRecheckButton.addEventListener", app)
        self.assertIn("payload.operational?.exchange_connector", render)
        self.assertIn("payload.operational?.connector_order_circuit_incident_log", render)
        self.assertIn("payload.connector_order_circuit_incidents", render)
        self.assertIn("payload.status?.exchange_connector", render)
        self.assertIn("status.connector_health", render)
        self.assertIn("config.order_audit_max_bytes", render)
        self.assertIn("config.connector_order_circuit_incident_log_backup_count", render)
        self.assertIn("config.operational_connector_snapshot_stale_seconds", render)
        self.assertIn("config.operational_portfolio_snapshot_stale_seconds", render)
        self.assertIn("config.operational_live_start_gate_enabled", render)
        self.assertIn("config.operational_live_order_gate_enabled", render)
        self.assertIn("export function renderConfigPersistence", render)
        self.assertIn("payload.config_persistence", render)
        self.assertIn('serviceApiRoute("config_persistence")', app)
        self.assertIn('serviceApiRoute("config_save")', app)
        self.assertIn('serviceApiRoute("config_load")', app)
        self.assertIn("payload.last_write_error?.message", render)
        self.assertIn("Request Lifecycle Start", index)
        self.assertIn("Request Lifecycle Stop", index)
        self.assertIn("Lifecycle start request recorded.", app)
        self.assertIn("Lifecycle stop request recorded.", app)
        self.assertNotIn(">Request Start<", index)
        self.assertNotIn(">Request Stop<", index)
        self.assertNotIn('"Request Start"', render)

    def test_web_dashboard_dom_bindings_have_matching_elements(self):
        dashboard_dir = REPO_ROOT / "apps" / "web-dashboard"
        index = (dashboard_dir / "index.html").read_text(encoding="utf-8")
        state = (dashboard_dir / "modules" / "state.js").read_text(encoding="utf-8")

        html_ids = _html_ids(index)
        bound_ids = set(re.findall(r'document\.getElementById\("([^"]+)"\)', state))

        self.assertTrue(bound_ids)
        self.assertEqual([], sorted(bound_ids - html_ids))
        for required_id in (
            "config-order-audit-max-bytes",
            "config-order-audit-backup-count",
            "config-incident-log-max-bytes",
            "config-incident-log-backup-count",
            "config-connector-stale-seconds",
            "config-execution-heartbeat-stale-seconds",
            "config-account-stale-seconds",
            "config-portfolio-stale-seconds",
            "config-live-start-gate-enabled",
            "config-live-order-gate-enabled",
            "config-persistence-state",
            "config-persistence-path",
            "save-config-file-button",
            "load-config-file-button",
            "runtime-lifecycle-mode",
            "runtime-execution-scope",
            "runtime-trading-execution",
            "control-lifecycle-mode",
            "control-execution-scope",
            "control-trading-execution",
        ):
            self.assertIn(required_id, bound_ids)

    def test_web_dashboard_preflight_renderer_behavior_test_is_packaged(self):
        dashboard_dir = REPO_ROOT / "apps" / "web-dashboard"
        package_json = (dashboard_dir / "package.json").read_text(encoding="utf-8")
        test_script = (dashboard_dir / "tests" / "render-preflight.test.mjs").read_text(encoding="utf-8")
        auth_test_script = (dashboard_dir / "tests" / "auth-storage-stream.test.mjs").read_text(encoding="utf-8")
        service_contract_test_script = (
            dashboard_dir / "tests" / "service-contract.test.mjs"
        ).read_text(encoding="utf-8")

        self.assertIn("node tests/render-preflight.test.mjs", package_json)
        self.assertIn("node tests/auth-storage-stream.test.mjs", package_json)
        self.assertIn("node tests/service-contract.test.mjs", package_json)
        self.assertIn("await import(\"../modules/render.js\")", test_script)
        self.assertIn("blocked start disables the Request Lifecycle Start button", test_script)
        self.assertIn("idle live preflight keeps Request Lifecycle Start ready", test_script)
        self.assertIn("warning preflight leaves Request Lifecycle Start clickable", test_script)
        self.assertIn(
            "control-plane lifecycle summaries distinguish desktop, heartbeat-only, and intent-only modes",
            test_script,
        )
        self.assertIn("request-start-button", test_script)
        self.assertIn("preflight-remediation-list", test_script)
        self.assertIn("dashboard token migrates out of localStorage into sessionStorage", auth_test_script)
        self.assertIn("dashboard stream helper sends auth header without query token", auth_test_script)
        self.assertIn("serviceApiRoute", service_contract_test_script)
        self.assertIn("Unknown service API route", service_contract_test_script)

    def test_service_api_contract_artifact_matches_python_constants(self):
        contract_path = REPO_ROOT / "apps" / "service-api" / "contracts" / "service-api-contract.json"
        runtime_sample_path = REPO_ROOT / "apps" / "service-api" / "contracts" / "runtime.sample.json"
        checker_path = REPO_ROOT / "Languages" / "Python" / "tools" / "check_service_api_contracts.py"
        artifact = json.loads(contract_path.read_text(encoding="utf-8"))
        runtime_sample = json.loads(runtime_sample_path.read_text(encoding="utf-8"))

        self.assertEqual(service_api_contract_payload(), artifact)
        self.assertEqual("trading-bot-service", runtime_sample["service_name"])
        self.assertEqual("apps/service-api/main.py", runtime_sample["python_entrypoint"])
        self.assertEqual("apps/desktop-pyqt/main.py", runtime_sample["desktop_entrypoint"])
        self.assertEqual("local-service-executor", runtime_sample["control_plane"]["mode"])
        self.assertEqual("service-lifecycle-heartbeat", runtime_sample["control_plane"]["execution_scope"])
        self.assertFalse(runtime_sample["control_plane"]["trading_execution_supported"])
        self.assertFalse(runtime_sample["capabilities"]["standalone_trading_execution"])
        self.assertTrue(runtime_sample["capabilities"]["desktop_trading_execution"])
        checker = _run_service_api_contract_checker(checker_path)
        self.assertEqual(0, checker.returncode, checker.stdout + checker.stderr)
        self.assertIn("service API contract artifacts checked", checker.stdout)

    def test_web_dashboard_uses_canonical_service_api_contract(self):
        dashboard_dir = REPO_ROOT / "apps" / "web-dashboard"
        dashboard_contract = (dashboard_dir / "modules" / "service-contract.js").read_text(encoding="utf-8")
        app = (dashboard_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('export const SERVICE_API_BASE_PATH = "/api/v1";', dashboard_contract)
        self.assertNotIn('const API_BASE_PATH = "/api/v1"', app)
        self.assertNotIn("function apiPath", app)
        self.assertNotIn('apiPath("', app)
        self.assertIn('serviceApiRoute("dashboard")', app)
        self.assertIn('serviceApiRoute("stream_dashboard")', app)

        for route_name, suffix in SERVICE_API_ROUTE_SUFFIXES.items():
            self.assertIn(f'{route_name}: "{suffix}"', dashboard_contract)

        for route_name in SERVICE_API_DASHBOARD_ROUTE_NAMES:
            self.assertIn(f'"{route_name}"', dashboard_contract)
            self.assertIn(f'serviceApiRoute("{route_name}")', app)

    def test_web_dashboard_readme_documents_preflight_operator_safety(self):
        readme = (REPO_ROOT / "apps" / "web-dashboard" / "README.md").read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())

        for phrase in (
            "## Preflight And Live Safety",
            "mirrors backend operational live safety checks",
            "Start shows whether live start is allowed, blocked, or warning",
            "A blocked Start disables Request Lifecycle Start",
            "Warnings, demo mode, and disabled gates keep Request Lifecycle Start clickable",
            "request service lifecycle heartbeat start/stop through the service API",
            "Orders shows whether live order submission is allowed, blocked, or warning",
            "Ages lists exchange connector, execution heartbeat, account snapshot",
            "A missing idle execution heartbeat is not a live-start blocker",
            "stale running execution heartbeat is",
            "Attention lists stale inputs and remediation hints",
            "## Lifecycle Control Modes",
            "The Control Plane card also interprets backend control-plane metadata",
            "Desktop Forwarded means lifecycle requests are queued into the desktop GUI",
            "Heartbeat Only means standalone service start/stop only maintains a lifecycle heartbeat",
            "Intent Only means lifecycle requests are recorded until an execution adapter attaches",
            "Trading Execution shows whether the attached owner reports strategy and order execution support",
            "`/runtime/operational-preflight`",
        ):
            self.assertIn(phrase, normalized_readme)

    def test_mobile_client_surfaces_operational_preflight_start_gate(self):
        mobile_dir = REPO_ROOT / "apps" / "mobile-client"
        app = (mobile_dir / "App.js").read_text(encoding="utf-8")
        logic = (mobile_dir / "app-logic.js").read_text(encoding="utf-8")
        readme = (mobile_dir / "README.md").read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())

        for phrase in (
            'require("./app-logic")',
            "currentPreflight(dashboard)",
            "isPreflightStartBlocked(preflight)",
            "preflightFreshnessAges(preflight)",
            "preflightFreshnessRemediations(preflight)",
            "const recheckPreflight = async",
            'serviceApiRoute("operational_preflight")',
            'Card title="Preflight"',
            'Card title="Lifecycle Controls" tone={lifecycleModeInfo}',
            "controlPlaneLifecycleSummary(controlPlane)",
            "Lifecycle Mode",
            "Trading Execution",
            "Preflight Start Gate",
            "disabled={preflightStartBlocked}",
            "Live start blocked by preflight",
            "Request Lifecycle Start",
            "Request Lifecycle Stop",
        ):
            self.assertIn(phrase, app)
        self.assertNotIn(">Request Start<", app)
        self.assertNotIn(">Request Stop<", app)

        for phrase in (
            "function currentPreflight",
            "dashboard?.operational?.preflight",
            "function isPreflightStartBlocked",
            "function preflightFreshnessAges",
            "function preflightFreshnessRemediations",
            "function controlPlaneLifecycleSummary",
            "Preflight Blocked",
            "Desktop Forwarded",
            "Heartbeat Only",
            "Intent Only",
        ):
            self.assertIn(phrase, logic)

        for phrase in (
            "## Preflight Safety",
            "same operational preflight payload as the web dashboard",
            "Start, Orders, Mode, Critical, Ages",
            "`/api/v1/runtime/operational-preflight`",
            "Request Lifecycle Start is disabled only when the backend preflight reports",
            "The Lifecycle Controls card also interprets the backend control-plane metadata",
            "heartbeat-only mode means standalone service start/stop only keeps a lifecycle heartbeat alive",
            "`start.allowed === false`",
            "docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md",
        ):
            self.assertIn(phrase, normalized_readme)
        self.assertNotIn("request bot start/stop", normalized_readme)

    def test_mobile_client_uses_canonical_service_api_contract(self):
        mobile_dir = REPO_ROOT / "apps" / "mobile-client"
        contract = (mobile_dir / "service-contract.js").read_text(encoding="utf-8")
        app = (mobile_dir / "App.js").read_text(encoding="utf-8")
        package_json = (mobile_dir / "package.json").read_text(encoding="utf-8")
        service_contract_test_script = (
            mobile_dir / "tests" / "service-contract.test.cjs"
        ).read_text(encoding="utf-8")
        app_logic_test_script = (
            mobile_dir / "tests" / "app-logic.test.cjs"
        ).read_text(encoding="utf-8")

        self.assertIn('const SERVICE_API_BASE_PATH = "/api/v1";', contract)
        self.assertIn('const { serviceApiRoute } = require("./service-contract");', app)
        self.assertIn('require("./app-logic")', app)
        self.assertNotIn('const API_BASE_PATH = "/api/v1"', app)
        self.assertNotIn("function apiPath", app)
        self.assertNotIn('apiPath("', app)
        self.assertIn("node tests/service-contract.test.cjs", package_json)
        self.assertIn("node tests/app-logic.test.cjs", package_json)
        self.assertIn("MOBILE_REQUIRED_ROUTE_NAMES", service_contract_test_script)
        self.assertIn("Unknown service API route", service_contract_test_script)
        self.assertIn("preflight helpers block only explicit start disallow states", app_logic_test_script)
        self.assertIn("control-plane summaries distinguish desktop, heartbeat-only, and intent-only modes", app_logic_test_script)
        self.assertIn("config persistence helpers distinguish runtime-only", app_logic_test_script)
        self.assertIn("LLM hydration maps service config without reusing token values", app_logic_test_script)

        for route_name, suffix in SERVICE_API_ROUTE_SUFFIXES.items():
            self.assertIn(f'{route_name}: "{suffix}"', contract)

        for route_name in SERVICE_API_MOBILE_ROUTE_NAMES:
            self.assertIn(f'"{route_name}"', contract)
            self.assertIn(f'serviceApiRoute("{route_name}")', app)

    def test_mobile_client_surfaces_config_persistence_controls(self):
        mobile_dir = REPO_ROOT / "apps" / "mobile-client"
        app = (mobile_dir / "App.js").read_text(encoding="utf-8")
        readme = (mobile_dir / "README.md").read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())

        for phrase in (
            "formatConfigPersistenceState(configPersistenceInfo)",
            "configPersistenceTone(configPersistenceInfo)",
            "const [configPersistence, setConfigPersistence] = useState(null)",
            "const refreshConfigPersistence = async",
            "const saveConfigFile = async",
            "const loadConfigFile = async",
            'serviceApiRoute("config_persistence")',
            'serviceApiRoute("config_save")',
            'serviceApiRoute("config_load")',
            'Card title="Config File"',
            "Runtime changes are not durable until Save File completes.",
            "Save File",
            "Load File",
            "Refresh Status",
            "LLM settings saved to runtime. Save Config File to persist.",
        ):
            self.assertIn(phrase, app)

        for phrase in (
            "inspect config persistence status and trigger service config file save/load",
            "## Config Persistence",
            "LLM and runtime config edits are runtime-only until the service config file is saved",
            "`GET /api/v1/config/persistence`",
            "`POST /api/v1/config/save`",
            "`POST /api/v1/config/load`",
            "Load File replaces the current runtime config",
        ):
            self.assertIn(phrase, normalized_readme)

    def test_desktop_client_surfaces_and_enforces_operational_preflight_start_gate(self):
        desktop_client = (
            REPO_ROOT / "Languages" / "Python" / "app" / "desktop" / "adapters" / "service_client.py"
        ).read_text(encoding="utf-8")
        bridge = (REPO_ROOT / "Languages" / "Python" / "app" / "desktop" / "service_bridge.py").read_text(
            encoding="utf-8"
        )
        snapshot_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "desktop" / "service_bridge_snapshot_runtime.py"
        ).read_text(encoding="utf-8")
        control_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "desktop" / "service_bridge_control_runtime.py"
        ).read_text(encoding="utf-8")
        actions_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "dashboard" / "actions_runtime.py"
        ).read_text(encoding="utf-8")
        service_api_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "runtime" / "service" / "service_api_runtime.py"
        ).read_text(encoding="utf-8")
        session_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "runtime" / "service" / "session_runtime.py"
        ).read_text(encoding="utf-8")
        status_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "runtime" / "service" / "status_runtime.py"
        ).read_text(encoding="utf-8")
        start_engine_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "runtime" / "strategy" / "start_engine_runtime.py"
        ).read_text(encoding="utf-8")
        start_runtime = (
            REPO_ROOT / "Languages" / "Python" / "app" / "gui" / "runtime" / "strategy" / "start_runtime.py"
        ).read_text(encoding="utf-8")

        for phrase in (
            "def get_operational_preflight",
            'service_api_route("operational_preflight")',
        ):
            self.assertIn(phrase, desktop_client)
        self.assertIn("_get_service_operational_preflight", bridge)
        self.assertIn("def _get_service_operational_preflight", snapshot_runtime)
        self.assertIn("def _service_request_start", control_runtime)
        self.assertIn("def _service_submit_backtest", control_runtime)
        self.assertIn("def _service_stop_backtest", control_runtime)
        self.assertIn("def _get_service_backtest_snapshot", snapshot_runtime)
        self.assertIn("_coerce_service_control_payload(result)", control_runtime)
        self.assertIn('mode="desktop-gui-dispatch"', control_runtime)
        self.assertIn('owner="desktop-gui"', control_runtime)
        self.assertIn('execution_scope="desktop-trading-runtime"', control_runtime)
        self.assertIn("trading_execution_supported=True", control_runtime)
        self.assertIn("desktop_service_preflight_label", actions_runtime)
        self.assertIn("desktop_service_preflight_recheck_btn", actions_runtime)
        self.assertIn("Recheck Preflight", actions_runtime)
        self.assertIn("Preflight: start blocked", service_api_runtime)
        self.assertIn("_apply_desktop_service_start_gate", service_api_runtime)
        self.assertIn("_recheck_desktop_service_preflight", service_api_runtime)
        self.assertIn("Start Blocked", service_api_runtime)
        self.assertIn("start_btn.setEnabled(False)", service_api_runtime)
        self.assertIn("_apply_desktop_service_start_gate", session_runtime)
        self.assertIn("_apply_desktop_service_start_gate", status_runtime)
        self.assertIn("ServiceStartRejected", start_engine_runtime)
        self.assertIn("Start blocked by service control plane", start_engine_runtime)
        self.assertIn("except ServiceStartRejected", start_runtime)
        self.assertIn("service_start_rejected", start_runtime)

    def test_operational_preflight_runbook_is_packaged_and_linked(self):
        runbook = (REPO_ROOT / "docs" / "OPERATIONAL_PREFLIGHT_RUNBOOK.md").read_text(encoding="utf-8")
        root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        user_guide = (REPO_ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        service_guide = (REPO_ROOT / "docs" / "SERVICE_API.md").read_text(encoding="utf-8")
        service_readme = (REPO_ROOT / "apps" / "service-api" / "README.md").read_text(encoding="utf-8")
        dashboard_readme = (REPO_ROOT / "apps" / "web-dashboard" / "README.md").read_text(encoding="utf-8")
        mobile_readme = (REPO_ROOT / "apps" / "mobile-client" / "README.md").read_text(encoding="utf-8")

        for phrase in (
            "# Operational Preflight Runbook",
            "GET /api/v1/runtime/operational-preflight",
            "## Lifecycle Mode Check",
            "runtime.control_plane",
            "Desktop Forwarded",
            "Heartbeat Only",
            "Intent Only",
            "trading_execution_supported",
            "critical_stale.start",
            "freshness.exchange_connector",
            "Exchange Connector",
            "Account Snapshot",
            "Portfolio Snapshot",
            "Execution Heartbeat",
            "operational_live_start_gate_enabled",
            "operational_live_order_gate_enabled",
            "start.allowed",
            "orders.allowed",
            "Before Restarting Live",
        ):
            self.assertIn(phrase, runbook)

        for phrase in (
            "### Runtime control-plane descriptor",
            "`runtime.control_plane`",
            "`apps/service-api/contracts/runtime.sample.json`",
            "`local-service-executor`",
            "`service-lifecycle-heartbeat`",
            "`desktop-gui-dispatch`",
            "`desktop-trading-runtime`",
            "`trading_execution_supported`",
            "Preflight and control-plane state answer different questions",
            "`max_events` for bounded diagnostics and contract tests",
            "python Languages/Python/tools/check_service_api_contracts.py",
        ):
            self.assertIn(phrase, service_guide)

        for phrase in (
            "`contracts/runtime.sample.json`",
            "`runtime.control_plane`",
            "`trading_execution_supported`",
            "standalone lifecycle heartbeat sessions",
            "desktop-forwarded trading runtime control",
            "python Languages/Python/tools/check_service_api_contracts.py",
        ):
            self.assertIn(phrase, service_readme)

        for docs_text in (
            root_readme,
            user_guide,
            service_guide,
            service_readme,
            dashboard_readme,
            mobile_readme,
        ):
            self.assertIn("OPERATIONAL_PREFLIGHT_RUNBOOK.md", docs_text)

    def test_windows_11_release_runner_setup_helper_is_guarded(self):
        helper = (REPO_ROOT / "tools" / "Setup-Windows11ReleaseRunner.ps1").read_text(encoding="utf-8")
        for fragment in (
            "SupportsShouldProcess",
            "Assert-Windows11X64",
            "Windows Server and Windows 10 are not accepted",
            "tb-release-platform,windows-11-x64",
            "Runner directory is not empty",
            "Get-RunnerAssetUrl",
            "No runner configuration was performed.",
            "InstallService requires an elevated PowerShell session.",
        ):
            self.assertIn(fragment, helper)

    def test_ci_smoke_uses_canonical_service_wrapper(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        native_cpp_checker = (REPO_ROOT / "tools" / "check_native_cpp.py").read_text(encoding="utf-8")
        verify_all = (REPO_ROOT / "tools" / "verify_all.py").read_text(encoding="utf-8")
        self.assertIn("python apps/service-api/main.py --healthcheck", workflow)
        self.assertIn("python Languages/Python/tools/check_service_api_contracts.py", workflow)
        self.assertIn("Check Rust native runtime evidence contract", workflow)
        self.assertIn("python tools/check_rust_native_runtime_evidence.py --schema-only", workflow)
        self.assertIn("Audit Rust native evidence importer", workflow)
        self.assertIn("python tools/import_rust_native_evidence_artifacts.py", workflow)
        self.assertIn("artifacts/native-source-sync", workflow)
        self.assertIn("--require-native-source-sync-audit", workflow)
        self.assertIn('"artifacts/native-source-sync"', verify_all)
        self.assertIn('"--require-native-source-sync-audit"', verify_all)
        self.assertIn("Run focused service API tests", workflow)
        self.assertIn("Clean generated Python install artifacts", workflow)
        self.assertIn("python tools/clean_workspace_artifacts.py --apply", workflow)
        self.assertIn("Native C++ Smoke", workflow)
        self.assertIn("python tools/check_native_cpp.py", workflow)
        self.assertIn('"desktop release smoke"', native_cpp_checker)
        self.assertIn('"--smoke"', native_cpp_checker)
        self.assertIn('env.setdefault("QT_QPA_PLATFORM", "offscreen")', native_cpp_checker)
        self.assertIn('f"-DCMAKE_BUILD_TYPE={config}"', native_cpp_checker)
        self.assertIn("--no-require-webengine", workflow)
        self.assertIn("--no-enable-qt-deploy-script", workflow)
        self.assertIn("--smoke-targets-only", workflow)
        self.assertIn("--qt-version 6.4.0", workflow)
        self.assertIn('"--no-require-webengine"', verify_all)
        self.assertIn('"--no-enable-qt-deploy-script"', verify_all)
        self.assertIn('"--smoke-targets-only"', verify_all)
        self.assertIn('"6.4.0"', verify_all)
        self.assertLess(
            workflow.index("Install Python dependencies"),
            workflow.index("Clean generated Python install artifacts"),
        )
        self.assertLess(
            workflow.index("Clean generated Python install artifacts"),
            workflow.index("Check workspace artifact hygiene"),
        )
        self.assertIn("python tools/run_service_tests.py --check-list", workflow)
        self.assertIn("python tools/run_service_tests.py --check-docs", workflow)
        self.assertIn("python tools/run_service_tests.py", workflow)
        self.assertIn("apps/desktop-pyqt/main.py", workflow)
        self.assertIn("apps/service-api/main.py", workflow)
        self.assertIn("python tools/check_python_sources_compile.py", workflow)
        self.assertIn("python tools/run_python_tests.py --runner pytest", workflow)
        self.assertIn("python tools/release_smoke.py --dry-run --skip-full-tests --manual-smoke-mode skip", workflow)
        self.assertIn("Install cross-platform Python service dependencies", workflow)
        self.assertIn('python -m pip install -e "./Languages/Python[service]"', workflow)
        self.assertIn(
            "python tools/check_python_sources_compile.py apps/service-api/main.py "
            "Languages/Python/app/service Languages/Python/app/settings Languages/Python/trading_core",
            workflow,
        )
        self.assertNotIn(
            "python -m compileall apps/service-api/main.py Languages/Python/app/service",
            workflow,
        )
        self.assertIn("Web Dashboard Quality", workflow)
        self.assertIn("actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38", workflow)
        self.assertIn('node-version: "24"', workflow)
        self.assertIn("working-directory: apps/web-dashboard", workflow)
        self.assertIn("node --check modules/render.js", workflow)
        self.assertIn("npm test", workflow)

    def test_native_cpp_product_smoke_is_bounded_offline_and_drains_qt_deletes(self):
        cpp_root = REPO_ROOT / "experiments" / "native-cpp" / "src"
        main_source = (cpp_root / "main.cpp").read_text(encoding="utf-8")
        window_source = (cpp_root / "TradingBotWindow.cpp").read_text(encoding="utf-8")
        dashboard_config_source = (
            cpp_root / "TradingBotWindow.dashboard_overrides.cpp"
        ).read_text(encoding="utf-8")
        chart_source = (cpp_root / "TradingBotWindow.chart.cpp").read_text(encoding="utf-8")
        web_source = (cpp_root / "TradingBotWindow.web.cpp").read_text(encoding="utf-8")

        self.assertIn('app.setProperty("tradingBotBoundedSmoke", true)', main_source)
        self.assertIn("const int exitCode = app.exec();", main_source)
        self.assertIn("window.reset();", main_source)
        self.assertIn("QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete)", main_source)
        self.assertIn('property("tradingBotBoundedSmoke")', window_source)
        self.assertIn("if (!boundedSmoke)", window_source)
        self.assertIn(
            "Smoke mode: generated chart symbols loaded without network access.",
            chart_source,
        )
        self.assertIn('property("tradingBotBoundedSmoke")', chart_source)
        self.assertIn('property("tradingBotBoundedSmoke")', web_source)
        self.assertIn("if (!boundedSmoke)", web_source)
        self.assertIn('QStringLiteral("stop_without_close")', dashboard_config_source)
        self.assertIn("dashboardStopWithoutCloseCheck_->setChecked", dashboard_config_source)

    def test_windows_native_cpp_bundle_smoke_is_isolated_and_complete(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release-windows.yml").read_text(
            encoding="utf-8"
        )
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        verifier = (REPO_ROOT / "tools" / "Test-NativeCppWindowsBundle.ps1").read_text(
            encoding="utf-8"
        )
        runtime_copier = (REPO_ROOT / "tools" / "Copy-MsvcRuntimeToBundle.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("windeployqt failed with exit code", workflow)
        self.assertIn("Copy-MsvcRuntimeToBundle.ps1", workflow)
        self.assertIn("$compilerRuntimeArchitecture", workflow)
        self.assertIn("Test-NativeCppWindowsBundle.ps1", workflow)
        self.assertIn("-RequireCompilerRuntime", workflow)
        self.assertIn("-RequireQtWebEngine:($env:TB_REQUIRE_QT_WEBENGINE -eq \"ON\")", workflow)
        self.assertIn("-EvidencePath $cppSmokeEvidence", workflow)
        self.assertIn('-SourceRevision "${{ github.sha }}"', workflow)
        self.assertIn("release/native-cpp-windows-smoke-*.json", workflow)
        self.assertIn("./tools/Copy-MsvcRuntimeToBundle.ps1 -SelfTest", ci_workflow)
        self.assertIn("./tools/Test-NativeCppWindowsBundle.ps1 -SelfTest", ci_workflow)
        for required_path in (
            '"Qt6Core.dll"',
            '"Qt6WebEngineCore.dll"',
            '"QtWebEngineProcess.exe"',
            '"platforms\\qwindows.dll"',
            '"resources\\qtwebengine_resources.pak"',
            '"translations\\qtwebengine_locales\\en-US.pak"',
            '"msvcp140.dll"',
            '"vcruntime140.dll"',
        ):
            self.assertIn(required_path, verifier)
        self.assertIn('"QT_PLUGIN_PATH"', verifier)
        self.assertIn('"QTWEBENGINEPROCESS_PATH"', verifier)
        self.assertIn("-RedirectStandardError", verifier)
        self.assertIn("Packaged C++ smoke emitted diagnostics", verifier)
        self.assertIn('ParameterSetName = "SelfTest"', verifier)
        self.assertIn("Assert-NativeCppBundleComplete", verifier)
        self.assertIn("RequireQtWebEngine", verifier)
        self.assertIn("Assert-NativeCppSmokeResult", verifier)
        self.assertIn("Invoke-WithIsolatedQtEnvironment", verifier)
        self.assertIn("Write-NativeCppBundleEvidence", verifier)
        self.assertIn('kind = "native-cpp-windows-bundle-smoke"', verifier)
        self.assertIn("Get-FileHash -LiteralPath $executablePath -Algorithm SHA256", verifier)
        self.assertIn("source_revision = $SourceRevision", verifier)
        self.assertIn("Test-NativeCppWindowsBundle self-test passed", verifier)
        self.assertIn('ValidateSet("x64", "arm64")', runtime_copier)
        self.assertIn("VCToolsRedistDir", runtime_copier)
        self.assertIn("Microsoft.VC143.CRT", runtime_copier)
        self.assertIn("Microsoft.VC145.CRT", runtime_copier)
        self.assertIn("Copy-Item -LiteralPath", runtime_copier)
        self.assertIn('ParameterSetName = "SelfTest"', runtime_copier)
        self.assertIn("Find-RuntimeDirectory", runtime_copier)
        self.assertIn("Copy-MsvcRuntimeFiles", runtime_copier)
        self.assertIn("Copy-MsvcRuntimeToBundle self-test passed", runtime_copier)

    def test_python_package_metadata_includes_public_trading_core_surface(self):
        pyproject = (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('include = ["app*", "trading_core*"]', pyproject)
        self.assertIn('trading_core = ["py.typed"]', pyproject)

    def test_release_dependency_constraints_avoid_ci_known_conflicts(self):
        pyproject = tomllib.loads(
            (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        )
        optional_dependencies = pyproject["project"]["optional-dependencies"]
        runtime_dependencies = pyproject["project"]["dependencies"]

        self.assertIn("numpy==2.2.6; python_version < '3.11'", runtime_dependencies)
        self.assertIn("numpy==2.4.4; python_version >= '3.11'", runtime_dependencies)
        self.assertIn("pandas==2.3.2; python_version < '3.11'", runtime_dependencies)
        self.assertIn("pandas==3.0.2; python_version >= '3.11'", runtime_dependencies)
        self.assertNotIn("numpy==2.4.4", runtime_dependencies)
        self.assertNotIn("pandas==3.0.2", runtime_dependencies)

        desktop_dependencies = optional_dependencies["desktop"]
        self.assertNotIn("numba", "\n".join(desktop_dependencies))
        self.assertNotIn("llvmlite", "\n".join(desktop_dependencies))

        dependency_catalog = (
            PYTHON_ROOT / "app" / "gui" / "code" / "code_language_catalog.py"
        ).read_text(encoding="utf-8")
        dependency_usage_runtime = (
            PYTHON_ROOT / "app" / "gui" / "code" / "dependency_versions_usage_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"package": "numba"', dependency_catalog)
        self.assertNotIn('"package": "llvmlite"', dependency_catalog)
        self.assertNotIn('"numba":', dependency_usage_runtime)
        self.assertNotIn('"llvmlite":', dependency_usage_runtime)

        windows_arm64_dependencies = optional_dependencies["windows-arm64"]
        self.assertNotIn("aiohttp==0.13.1", windows_arm64_dependencies)
        self.assertIn("aiohttp>=3.9,<4", windows_arm64_dependencies)

        self.assertEqual(
            ["pip-audit==2.10.1", "truststore==0.10.4"],
            optional_dependencies["security"],
        )

    def test_dev_dependency_surface_includes_fastapi_testclient_transport(self):
        pyproject = tomllib.loads(
            (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        )
        optional_dependencies = pyproject["project"]["optional-dependencies"]

        self.assertIn("httpx>=0.27,<1", optional_dependencies["dev"])
        self.assertNotIn("httpx>=0.27,<1", optional_dependencies["service"])

        docs = {
            "root README": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "Python README": (REPO_ROOT / "Languages" / "Python" / "README.md").read_text(encoding="utf-8"),
            "Python tools README": (REPO_ROOT / "Languages" / "Python" / "tools" / "README.md").read_text(
                encoding="utf-8"
            ),
            "service API README": (REPO_ROOT / "apps" / "service-api" / "README.md").read_text(encoding="utf-8"),
            "service API guide": (REPO_ROOT / "docs" / "SERVICE_API.md").read_text(encoding="utf-8"),
        }
        service_test_runner = (
            REPO_ROOT / "Languages" / "Python" / "tools" / "run_service_tests.py"
        ).read_text(encoding="utf-8")
        for docs_text in docs.values():
            self.assertIn('python -m pip install -e ".[desktop,service,dev]"', docs_text)
        for docs_text in (
            docs["root README"],
            docs["Python README"],
            docs["service API guide"],
        ):
            self.assertIn("FastAPI `TestClient`", docs_text)
        for docs_text in (
            docs["service API README"],
            docs["service API guide"],
            docs["Python tools README"],
        ):
            self.assertIn("python tools/run_service_tests.py", docs_text)
            self.assertIn("python tools/run_service_tests.py --check-list", docs_text)
            self.assertIn("python tools/run_service_tests.py --check-docs", docs_text)
            self.assertIn(render_markdown_section(), docs_text)
            for module_name in SERVICE_TEST_MODULES:
                self.assertIn(module_name, docs_text)
            self.assertNotIn("tests.test_service_api_smoke", docs_text)
        self.assertIn("from tools.service_test_manifest import", service_test_runner)
        self.assertNotIn("tests.test_service_api_smoke", service_test_runner)

    def test_windows_release_workflow_uses_arm64_pure_python_aiohttp_fallbacks(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")
        self.assertIn("AIOHTTP_NO_EXTENSIONS", workflow)
        self.assertIn("MULTIDICT_NO_EXTENSIONS", workflow)
        self.assertIn("YARL_NO_EXTENSIONS", workflow)
        self.assertIn("FROZENLIST_NO_EXTENSIONS", workflow)
        self.assertIn("PROPCACHE_NO_EXTENSIONS", workflow)

    def test_release_platform_real_test_matrix_covers_requested_targets(self):
        matrix_path = REPO_ROOT / "docs" / "release-platform-test-matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        checker = REPO_ROOT / "tools" / "check_release_platform_matrix.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--schema-only", "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)

        self.assertEqual(3, report["platform_target_count"])
        self.assertEqual(9, report["browser_target_count"])
        self.assertTrue(matrix["policy"]["no_assumed_passes"])
        self.assertEqual("tier-1-release", matrix["policy"]["support_tier"])
        self.assertEqual(
            {"windows", "macos", "ubuntu"},
            {item["family"] for item in matrix["target_groups"]},
        )
        self.assertEqual(
            {"chrome", "edge", "firefox"},
            {item["browser"] for item in matrix["browser_groups"]},
        )

        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        real_test_workflow = (
            REPO_ROOT / ".github" / "workflows" / "release-platform-real-tests.yml"
        ).read_text(encoding="utf-8")
        rust_release_evidence_workflow = (
            REPO_ROOT / ".github" / "workflows" / "rust-native-release-evidence.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Release Platform Matrix Contract", ci_workflow)
        self.assertIn("python tools/check_release_platform_matrix.py --schema-only", ci_workflow)
        self.assertIn("python tools/run_release_platform_probe.py --list-local-browser-targets", ci_workflow)
        self.assertIn("tools/run_release_platform_probe.py", real_test_workflow)
        self.assertIn("Set up Rust for native release probes", real_test_workflow)
        self.assertIn("Cache Rust dependencies for native release probes", real_test_workflow)
        self.assertIn("Install Linux Rust desktop dependencies", real_test_workflow)
        self.assertIn("libwebkit2gtk-4.1-dev", real_test_workflow)
        self.assertIn("--require-native-source-sync", real_test_workflow)
        self.assertIn("--require-evidence", real_test_workflow)
        self.assertGreaterEqual(real_test_workflow.count("--require-current-commit"), 2)
        self.assertGreaterEqual(real_test_workflow.count("--require-clean-source"), 2)
        self.assertIn("desktop_smoke_command", real_test_workflow)
        self.assertIn("TB_RELEASE_DESKTOP_SMOKE_COMMAND", real_test_workflow)
        self.assertIn("browser_test_command", real_test_workflow)
        self.assertIn("TB_BROWSER_TEST_COMMAND", real_test_workflow)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", real_test_workflow)
        self.assertIn("gh run download", rust_release_evidence_workflow)
        self.assertIn("tools/write_rust_native_release_evidence.py", rust_release_evidence_workflow)
        self.assertIn("--only rust-native-release-platform-evidence", rust_release_evidence_workflow)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", rust_release_evidence_workflow)

    def test_python_version_support_matrix_declares_and_checks_310_to_314(self):
        checker = REPO_ROOT / "tools" / "check_python_version_support.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--current", "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(["3.10", "3.11", "3.12", "3.13", "3.14"], report["supported_versions"])
        self.assertEqual("3.14", report["default_version"])
        self.assertEqual(">=3.10,<3.15", report["requires_python"])

        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python-version-compatibility:", workflow)
        self.assertIn("Python 3.10-3.14 Compatibility", workflow)
        self.assertIn("python tools/check_python_version_support.py --current", workflow)
        for version in report["supported_versions"]:
            self.assertIn(f'"{version}"', workflow)

    def test_release_workflows_use_node24_action_versions(self):
        workflows = {
            name: (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for name in (
                "release-windows.yml",
                "release-linux-macos.yml",
                "release-freebsd.yml",
            )
        }
        combined = "\n".join(workflows.values())

        self.assertNotIn("ilammy/msvc-dev-cmd@v1", combined)
        self.assertNotIn("actions/download-artifact@v6", combined)
        self.assertNotIn("actions/upload-artifact@v6", combined)
        self.assertNotIn("softprops/action-gh-release@v2", combined)

        self.assertIn("TheMrMilchmann/setup-msvc-dev@79dac248aac9d0059f86eae9d8b5bfab4e95e97c", workflows["release-windows.yml"])
        self.assertIn("actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131", workflows["release-windows.yml"])
        self.assertIn("actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131", workflows["release-linux-macos.yml"])
        for workflow in workflows.values():
            self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", workflow)
            self.assertIn("softprops/action-gh-release@3d0d9888cb7fd7b750713d6e236d1fcb99157228", workflow)

    def test_release_workflows_generate_attested_sboms(self):
        workflows = (
            REPO_ROOT / ".github" / "workflows" / "release-windows.yml",
            REPO_ROOT / ".github" / "workflows" / "release-linux-macos.yml",
            REPO_ROOT / ".github" / "workflows" / "release-freebsd.yml",
        )
        for workflow_path in workflows:
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertIn("anchore/sbom-action@e22c389904149dbc22b58101806040fa8d37a610", workflow)
            self.assertIn("actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6", workflow)
            self.assertIn("attestations: write", workflow)
            self.assertIn("id-token: write", workflow)
            expected_sbom_name = (
                "release-sbom-freebsd.spdx.json"
                if workflow_path.name == "release-freebsd.yml"
                else "release-sbom-${{ matrix.id }}.spdx.json"
            )
            self.assertIn(expected_sbom_name, workflow)

    def test_release_workflows_execute_packaged_native_smokes(self):
        workflows = {
            name: (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            for name in (
                "release-windows.yml",
                "release-linux-macos.yml",
                "release-freebsd.yml",
            )
        }
        ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        packaging_script = (
            REPO_ROOT / ".github" / "scripts" / "package_linux_macos_release.sh"
        ).read_text(encoding="utf-8")
        tauri_main = (
            REPO_ROOT
            / "experiments"
            / "rust-shells"
            / "apps"
            / "tauri-desktop"
            / "src"
            / "main.rs"
        ).read_text(encoding="utf-8")

        self.assertIn('BinaryName = "trading-bot-rust"', workflows["release-windows.yml"])
        self.assertIn(
            'BinaryName = "trading-bot-tauri-desktop"',
            workflows["release-windows.yml"],
        )
        self.assertIn("Build required Tauri desktop EXE", workflows["release-windows.yml"])
        self.assertIn('Required = $true', workflows["release-windows.yml"])
        self.assertNotIn("Build optional Rust framework EXEs", workflows["release-windows.yml"])
        self.assertIn("tools/write_rust_package_smoke_evidence.py", workflows["release-windows.yml"])
        self.assertIn("release/rust-package-smoke-*.json", workflows["release-windows.yml"])
        self.assertIn("--require-clean-source", workflows["release-windows.yml"])
        self.assertIn("Test-NativeCppWindowsBundle.ps1", workflows["release-windows.yml"])
        self.assertIn("Build required Tauri desktop binary", workflows["release-linux-macos.yml"])
        self.assertIn(
            "tools/write_rust_package_smoke_evidence.py",
            workflows["release-linux-macos.yml"],
        )
        self.assertIn(
            'release/rust-package-smoke-${{ matrix.id }}.json',
            workflows["release-linux-macos.yml"],
        )
        self.assertIn("--require-clean-source", workflows["release-linux-macos.yml"])
        self.assertNotIn("Build optional Rust framework binaries", workflows["release-linux-macos.yml"])
        self.assertIn('"Trading-Bot-Rust-tauri:trading-bot-tauri-desktop"', packaging_script)
        self.assertIn('for rust_entry in "${required_rust_assets[@]}"', packaging_script)
        self.assertNotIn("optional_rust_assets", packaging_script)
        self.assertIn("cargo test --locked --package trading-bot-tauri-desktop", ci_workflow)
        self.assertIn(
            "cargo run --locked --release --package trading-bot-tauri-desktop -- --smoke",
            ci_workflow,
        )
        self.assertIn('arg == "--smoke"', tauri_main)
        self.assertIn("run_packaged_smoke", tauri_main)
        self.assertIn("Trading Bot Tauri packaged smoke passed", tauri_main)
        macos_release_workflow = workflows["release-linux-macos.yml"]
        self.assertIn('QT_QPA_PLATFORM=offscreen "${cpp_bin}" --smoke', macos_release_workflow)
        self.assertIn("Deploy macOS Qt frameworks", macos_release_workflow)
        self.assertIn('"${macdeployqt}" "${app_bundle}" -always-overwrite', macos_release_workflow)
        self.assertIn('"-libpath=${qt_prefix}/lib"', macos_release_workflow)
        self.assertIn("-DTB_ENABLE_QT_DEPLOY_SCRIPT=OFF", macos_release_workflow)
        self.assertIn("QtConcurrent.framework", macos_release_workflow)
        self.assertIn("embedded-framework LC_RPATH", macos_release_workflow)
        self.assertNotIn("mapfile -t artifacts", macos_release_workflow)
        self.assertIn("while IFS= read -r artifact", macos_release_workflow)
        self.assertIn('artifacts+=("${artifact}")', macos_release_workflow)
        self.assertLess(
            macos_release_workflow.index("Deploy macOS Qt frameworks"),
            macos_release_workflow.index("Smoke packaged native binaries"),
        )
        windows_release_workflow = workflows["release-windows.yml"]
        self.assertIn("function Install-AqtPackage", windows_release_workflow)
        self.assertIn("aqt install failed after 3 attempts", windows_release_workflow)
        self.assertIn("msvc2022_arm64(_cross_compiled)?", windows_release_workflow)
        self.assertNotIn('"qtpositioning", "--autodesktop"', windows_release_workflow)
        native_cpp_cmake = (REPO_ROOT / "experiments" / "native-cpp" / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn('INSTALL_RPATH "@executable_path/../Frameworks"', native_cpp_cmake)
        self.assertIn('QT_QPA_PLATFORM=offscreen "${cpp_bin}" --smoke', workflows["release-freebsd.yml"])
        for workflow_name in ("release-linux-macos.yml", "release-freebsd.yml"):
            workflow = workflows[workflow_name]
            self.assertIn("bash Languages/Python/tools/build_binary.sh", workflow)
            self.assertNotIn("chmod +x Languages/Python/tools/build_binary.sh", workflow)
        self.assertIn("bash .github/scripts/package_linux_macos_release.sh", workflows["release-linux-macos.yml"])
        self.assertNotIn("chmod +x .github/scripts/package_linux_macos_release.sh", workflows["release-linux-macos.yml"])
        for workflow in workflows.values():
            self.assertNotIn("tools/update_loc_snapshot.py", workflow)
