import json
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
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


class ProductPackagingContractTests(unittest.TestCase):
    def test_windows_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("apps\\\\desktop-pyqt\\\\main.py", script)
        self.assertIn('"--paths", $repoRoot', script)
        self.assertIn('"--paths", $pythonRoot', script)
        self.assertIn('$env:BOT_DISABLE_PYTHONW_RELAUNCH = "1"', script)
        self.assertIn('$env:BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH = "1"', script)
        self.assertIn("PyInstaller failed with exit code", script)

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

    def test_unix_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_binary.sh").read_text(encoding="utf-8")
        self.assertIn('DESKTOP_ENTRY_SCRIPT="${REPO_ROOT}/apps/desktop-pyqt/main.py"', script)
        self.assertIn('--paths "${REPO_ROOT}"', script)
        self.assertIn('--paths "${PYTHON_ROOT}"', script)
        self.assertIn(
            'BOT_DISABLE_PYTHONW_RELAUNCH=1 BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH=1 "${PYTHON_BIN}" "${pyinstaller_args[@]}"',
            script,
        )

    def test_docker_backend_uses_canonical_service_wrapper_and_dashboard_assets(self):
        dockerfile = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY apps/service-api /app/apps/service-api", dockerfile)
        self.assertIn("COPY apps/web-dashboard /app/apps/web-dashboard", dockerfile)
        self.assertIn('CMD ["python", "apps/service-api/main.py"', dockerfile)

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
        checker = subprocess.run(
            [sys.executable, str(checker_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
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

    def test_ci_smoke_uses_canonical_service_wrapper(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python apps/service-api/main.py --healthcheck", workflow)
        self.assertIn("python Languages/Python/tools/check_service_api_contracts.py", workflow)
        self.assertIn("Run focused service API tests", workflow)
        self.assertIn("python tools/run_service_tests.py --check-list", workflow)
        self.assertIn("python tools/run_service_tests.py --check-docs", workflow)
        self.assertIn("python tools/run_service_tests.py", workflow)
        self.assertIn("apps/desktop-pyqt/main.py", workflow)
        self.assertIn("apps/service-api/main.py", workflow)
        self.assertIn("python tools/release_smoke.py --dry-run --skip-full-tests --manual-smoke-mode skip", workflow)
        self.assertIn("Web Dashboard Quality", workflow)
        self.assertIn("actions/setup-node@v6", workflow)
        self.assertIn('node-version: "24"', workflow)
        self.assertIn("working-directory: apps/web-dashboard", workflow)
        self.assertIn("node --check modules/render.js", workflow)
        self.assertIn("npm test", workflow)

    def test_python_package_metadata_includes_public_trading_core_surface(self):
        pyproject = (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('include = ["app*", "trading_core*"]', pyproject)
        self.assertIn('trading_core = ["py.typed"]', pyproject)

    def test_release_dependency_constraints_avoid_ci_known_conflicts(self):
        pyproject = tomllib.loads(
            (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        )
        optional_dependencies = pyproject["project"]["optional-dependencies"]

        desktop_dependencies = optional_dependencies["desktop"]
        self.assertIn(
            "numba==0.65.0; platform_system != 'Darwin' or platform_machine != 'x86_64'",
            desktop_dependencies,
        )
        self.assertIn(
            "llvmlite==0.47.0; platform_system != 'Darwin' or platform_machine != 'x86_64'",
            desktop_dependencies,
        )

        windows_arm64_dependencies = optional_dependencies["windows-arm64"]
        self.assertNotIn("aiohttp==0.13.1", windows_arm64_dependencies)
        self.assertIn("aiohttp>=3.9,<4", windows_arm64_dependencies)

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

        self.assertIn("TheMrMilchmann/setup-msvc-dev@v4", workflows["release-windows.yml"])
        self.assertIn("actions/download-artifact@v7", workflows["release-windows.yml"])
        self.assertIn("actions/download-artifact@v7", workflows["release-linux-macos.yml"])
        for workflow in workflows.values():
            self.assertIn("actions/upload-artifact@v7", workflow)
            self.assertIn("softprops/action-gh-release@v3", workflow)
