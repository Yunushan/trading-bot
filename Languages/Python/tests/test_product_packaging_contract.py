import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parents[3]


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
            "preflight-state",
            "preflight-start",
            "preflight-orders",
            "preflight-mode",
            "preflight-critical",
            "preflight-recheck-button",
            "preflight-message",
        ):
            self.assertIn(f'id="{element_id}"', index)

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
        self.assertIn("preflightState: document.getElementById(\"preflight-state\")", state)
        self.assertIn("preflightOrders: document.getElementById(\"preflight-orders\")", state)
        self.assertIn(
            "preflightRecheckButton: document.getElementById(\"preflight-recheck-button\")",
            state,
        )
        self.assertIn("function renderExchangeConnector", render)
        self.assertIn("export function renderPreflight", render)
        self.assertIn("function renderCircuitIncidentLog", render)
        self.assertIn("function renderLastCircuitIncident", render)
        self.assertIn("function renderConnectorIncidents", render)
        self.assertIn("payload.operational?.preflight", render)
        self.assertIn("runtime/operational-preflight", app)
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
        self.assertIn("payload.last_write_error?.message", render)

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
        ):
            self.assertIn(required_id, bound_ids)

    def test_ci_smoke_uses_canonical_service_wrapper(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python apps/service-api/main.py --healthcheck", workflow)
        self.assertIn("apps/desktop-pyqt/main.py", workflow)
        self.assertIn("apps/service-api/main.py", workflow)

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
