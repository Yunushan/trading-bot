import importlib.util
import json
import os
import stat
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api import (  # noqa: E402
    FASTAPI_AVAILABLE,
    ServiceApiBackgroundHost,
    create_service_api_app,
    run_service_api_server,
)
from app.service.api_contract import (  # noqa: E402
    SERVICE_API_BASE_PATH,
    SERVICE_API_LEGACY_BASE_PATH,
    SERVICE_API_LEGACY_ROUTE_PATHS,
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SCHEMAS,
    SERVICE_API_STREAM_DASHBOARD_PATH,
    SERVICE_API_VERSION,
)
from app.service.auth import (  # noqa: E402
    MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH,
    SERVICE_API_TOKEN_FILE_ENV,
    auth_required,
    host_requires_service_api_token,
    resolve_service_api_token,
    service_api_url_scheme,
    validate_bearer_token,
    validate_service_api_exposure,
)
from app.desktop.service_bridge_host_runtime import _resolve_desktop_service_api_settings  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402
from app.integrations.llm.local_models import (  # noqa: E402
    LocalModelServerStartResult,
    LocalModelStatus,
)

REPO_ROOT = PYTHON_ROOT.parents[1]
FASTAPI_TESTCLIENT_AVAILABLE = FASTAPI_AVAILABLE and importlib.util.find_spec("httpx") is not None


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value)


def _create_test_client(app):
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover - depends on optional test dependency stack
        raise AssertionError(
            "FastAPI TestClient is required for service API HTTP contract tests. "
            'Install the dev surface with: python -m pip install -e ".[desktop,service,dev]". '
            f"Import failed: {exc}"
        ) from exc
    return TestClient(app)


class ServiceApiHttpContractTests(unittest.TestCase):
    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_app_exposes_expected_routes(self):
        app = create_service_api_app()
        paths = {route.path for route in app.router.routes}
        schema_paths = set(app.openapi()["paths"])
        route_methods_by_path: dict[str, set[str]] = {}
        for route in app.router.routes:
            methods = getattr(route, "methods", None)
            if not methods:
                continue
            route_methods_by_path.setdefault(route.path, set()).update(
                method for method in methods if method not in {"HEAD", "OPTIONS"}
            )
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn("/livez", paths)
        self.assertIn("/readyz", paths)
        self.assertIn("/ui", paths)
        self.assertEqual(SERVICE_API_BASE_PATH, "/api/v1")
        self.assertEqual(SERVICE_API_LEGACY_BASE_PATH, "/api")
        self.assertEqual(SERVICE_API_VERSION, "1.0.0")
        self.assertEqual(SERVICE_API_STREAM_DASHBOARD_PATH, "/api/v1/stream/dashboard")
        for route_name in (
            "dashboard",
            "runtime",
            "status",
            "metrics",
            "config",
            "config_summary",
            "config_persistence",
            "config_save",
            "config_load",
            "account",
            "portfolio",
            "exchange_connector",
            "connector_order_circuit_breaker",
            "connector_order_circuit_breaker_reset",
            "connector_order_circuit_incidents",
            "logs",
            "terminal_run",
            "llm_providers",
            "llm_config",
            "llm_prompt",
            "llm_local_model_status",
            "llm_local_model_start",
            "llm_local_model_pull",
            "llm_local_model_delete",
            "execution",
            "backtest",
            "runtime_state",
            "operational_preflight",
            "control_start",
            "control_stop",
            "control_start_failed",
            "backtest_run",
            "backtest_stop",
            "stream_dashboard",
        ):
            self.assertIn(SERVICE_API_ROUTE_PATHS[route_name], paths)
            self.assertIn(SERVICE_API_ROUTE_PATHS[route_name], schema_paths)
            self.assertIn(SERVICE_API_LEGACY_ROUTE_PATHS[route_name], paths)
            self.assertNotIn(SERVICE_API_LEGACY_ROUTE_PATHS[route_name], schema_paths)
            self.assertEqual(
                set(SERVICE_API_ROUTE_METHODS[route_name]),
                route_methods_by_path[SERVICE_API_ROUTE_PATHS[route_name]],
            )
            self.assertEqual(
                set(SERVICE_API_ROUTE_METHODS[route_name]),
                route_methods_by_path[SERVICE_API_LEGACY_ROUTE_PATHS[route_name]],
            )
        self.assertEqual(app.version, SERVICE_API_VERSION)
        self.assertEqual(app.state.service_api_base_path, SERVICE_API_BASE_PATH)
        self.assertEqual(app.state.service_api_legacy_base_path, SERVICE_API_LEGACY_BASE_PATH)
        self.assertEqual(app.state.service_api_stream_path, SERVICE_API_STREAM_DASHBOARD_PATH)
        self.assertEqual(Path(app.state.web_client_dir).name, "web-dashboard")
        self.assertEqual(app.state.service_api_host_context, "standalone-service")
        self.assertEqual(app.state.service_api_host_owner, "service-process")
        self.assertEqual(
            app.state.service.describe_runtime().to_dict()["control_plane"]["mode"],
            "local-service-executor",
        )
        self.assertEqual(
            app.state.service.describe_runtime().to_dict()["control_plane"]["execution_scope"],
            "service-lifecycle-heartbeat",
        )
        self.assertFalse(
            app.state.service.describe_runtime().to_dict()["control_plane"]["trading_execution_supported"]
        )

    @unittest.skipUnless(
        FASTAPI_TESTCLIENT_AVAILABLE,
        "FastAPI TestClient optional dependencies are not installed",
    )
    def test_service_api_liveness_and_readiness_probes(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)

        liveness = client.get("/livez")
        readiness = client.get("/readyz")

        self.assertEqual(200, liveness.status_code)
        self.assertEqual({"status": "ok"}, liveness.json())
        self.assertEqual(200, readiness.status_code)
        self.assertEqual("ready", readiness.json()["status"])
        self.assertEqual("trading-bot-service", readiness.json()["service_name"])

        with mock.patch.object(app.state.service, "describe_runtime", side_effect=RuntimeError("boom")):
            not_ready = client.get("/readyz")

        self.assertEqual(503, not_ready.status_code)
        self.assertEqual({"status": "not-ready"}, not_ready.json())

    @unittest.skipUnless(
        FASTAPI_TESTCLIENT_AVAILABLE,
        "FastAPI TestClient optional dependencies are not installed",
    )
    def test_service_api_route_schemas_cover_openapi_and_live_read_responses(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)
        headers = {"Authorization": "Bearer token-123"}
        openapi_paths = app.openapi()["paths"]

        self.assertEqual(set(SERVICE_API_ROUTE_PATHS), set(SERVICE_API_ROUTE_SCHEMAS))
        for route_name, route_path in SERVICE_API_ROUTE_PATHS.items():
            schema = SERVICE_API_ROUTE_SCHEMAS[route_name]
            path_item = openapi_paths[route_path]
            for method in SERVICE_API_ROUTE_METHODS[route_name]:
                operation = path_item[method.lower()]
                query_fields = {
                    str(parameter["name"])
                    for parameter in operation.get("parameters", [])
                    if parameter.get("in") == "query"
                }
                self.assertTrue(
                    set(schema["query_fields"]).issubset(query_fields),
                    f"{route_name} should expose declared query fields in OpenAPI",
                )

        live_read_routes = (
            "runtime",
            "dashboard",
            "status",
            "metrics",
            "execution",
            "backtest",
            "config_summary",
            "config",
            "config_persistence",
            "operational_preflight",
            "connector_order_circuit_breaker",
            "connector_order_circuit_incidents",
            "account",
            "portfolio",
            "exchange_connector",
            "llm_config",
        )
        for route_name in live_read_routes:
            response = client.get(SERVICE_API_ROUTE_PATHS[route_name], headers=headers)
            self.assertEqual(200, response.status_code, route_name)
            payload = response.json()
            self.assertTrue(
                set(SERVICE_API_ROUTE_SCHEMAS[route_name]["response_fields"]).issubset(payload),
                f"{route_name} should return declared top-level response fields",
            )

    @unittest.skipUnless(
        FASTAPI_TESTCLIENT_AVAILABLE,
        "FastAPI TestClient optional dependencies are not installed",
    )
    def test_service_api_exposes_local_llm_model_management_routes(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)
        headers = {"Authorization": "Bearer token-123"}
        status_payload = LocalModelStatus(
            model="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            server_kind="ollama",
            installed=False,
            can_download=True,
            can_start=True,
            storage_hint="outside this project",
            storage_paths=("C:/Users/Test/.ollama/models",),
            estimated_size_label="about 5 GB",
        )

        with (
            mock.patch("app.service.api.app.get_local_model_status", return_value=status_payload) as status_mock,
            mock.patch(
                "app.service.api.app.start_ollama_server",
                return_value=LocalModelServerStartResult(started=True, server_kind="ollama", executable="ollama"),
            ) as start_mock,
            mock.patch("app.service.api.app.pull_ollama_model") as pull_mock,
            mock.patch("app.service.api.app.delete_ollama_model") as delete_mock,
        ):
            status_response = client.get(
                SERVICE_API_ROUTE_PATHS["llm_local_model_status"],
                params={"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
            )
            self.assertEqual(200, status_response.status_code)
            self.assertEqual("ollama", status_response.json()["server_kind"])
            self.assertIn(".ollama", status_response.json()["storage_paths"][0])

            unauthorized_start_response = client.post(
                SERVICE_API_ROUTE_PATHS["llm_local_model_start"],
                json={"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
            )
            self.assertEqual(401, unauthorized_start_response.status_code)

            start_response = client.post(
                SERVICE_API_ROUTE_PATHS["llm_local_model_start"],
                headers=headers,
                json={"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
            )
            self.assertEqual(200, start_response.status_code)
            self.assertTrue(start_response.json()["started"])

            pull_response = client.post(
                SERVICE_API_ROUTE_PATHS["llm_local_model_pull"],
                headers=headers,
                json={"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
            )
            self.assertEqual(200, pull_response.status_code)
            self.assertEqual("pull", pull_response.json()["action"])

            delete_response = client.post(
                SERVICE_API_ROUTE_PATHS["llm_local_model_delete"],
                headers=headers,
                json={"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3:8b"},
            )
            self.assertEqual(200, delete_response.status_code)
            self.assertEqual("delete", delete_response.json()["action"])

        status_mock.assert_called()
        start_mock.assert_called_once()
        pull_mock.assert_called_once_with("http://127.0.0.1:11434/v1", "qwen3:8b")
        delete_mock.assert_called_once_with("http://127.0.0.1:11434/v1", "qwen3:8b")

    def test_service_api_auth_helpers(self):
        self.assertFalse(auth_required(""))
        self.assertTrue(validate_bearer_token(None, ""))
        self.assertTrue(validate_bearer_token("Bearer token-123", "token-123"))
        self.assertFalse(validate_bearer_token("Bearer wrong", "token-123"))
        self.assertFalse(host_requires_service_api_token("127.0.0.1"))
        self.assertFalse(host_requires_service_api_token("localhost"))
        self.assertTrue(host_requires_service_api_token("0.0.0.0"))
        self.assertTrue(host_requires_service_api_token("192.168.1.10"))
        validate_service_api_exposure("127.0.0.1", "short-token")
        with self.assertRaisesRegex(RuntimeError, "at least 32 characters"):
            validate_service_api_exposure("0.0.0.0", "short-token")
        with self.assertRaisesRegex(RuntimeError, "requires TLS"):
            validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
        with mock.patch.dict(os.environ, {"BOT_SERVICE_API_TRUST_PROXY_TLS": "1"}, clear=True):
            validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
        with mock.patch.dict(os.environ, {"BOT_SERVICE_API_TRUST_LOOPBACK_PROXY": "1"}, clear=True):
            validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
        with tempfile.TemporaryDirectory() as temporary_directory:
            certificate = Path(temporary_directory) / "service.crt"
            private_key = Path(temporary_directory) / "service.key"
            certificate.write_text("certificate", encoding="utf-8")
            private_key.write_text("private-key", encoding="utf-8")
            private_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(
                os.environ,
                {
                    "BOT_SERVICE_API_TLS_CERTFILE": str(certificate),
                    "BOT_SERVICE_API_TLS_KEYFILE": str(private_key),
                },
                clear=True,
            ):
                validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
            with mock.patch.dict(
                os.environ,
                {
                    "BOT_SERVICE_API_TLS_CERTFILE": str(certificate),
                    "BOT_SERVICE_API_TLS_KEYFILE": str(private_key),
                },
                clear=True,
            ), mock.patch(
                "app.service.auth.token.os.name", "posix"
            ), mock.patch(
                "app.service.auth.token.os.fstat",
                return_value=mock.Mock(
                    st_mode=stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP,
                    st_size=len("private-key"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "private-key file must not grant group or other permissions"):
                    validate_service_api_exposure("127.0.0.1", "short-token")
        with mock.patch.dict(
            os.environ,
            {
                "BOT_SERVICE_API_TRUST_PROXY_TLS": "1",
                "BOT_SERVICE_API_TLS_CERTFILE": "missing-service.crt",
                "BOT_SERVICE_API_TLS_KEYFILE": "missing-service.key",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "certificate or key file does not exist"):
                validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
        with mock.patch.dict(os.environ, {"BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "only allowed when the service API binds to a loopback host"):
                validate_service_api_exposure("0.0.0.0", "x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH)
            validate_service_api_exposure("127.0.0.1", "short-token")

    def test_service_api_token_file_fallback_is_bounded_and_explicit_token_wins(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            token_file = Path(temporary_directory) / "service-api-token"
            token_file.write_text("file-token\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {SERVICE_API_TOKEN_FILE_ENV: str(token_file)}, clear=True):
                self.assertEqual("file-token", resolve_service_api_token())
                self.assertTrue(auth_required())
                self.assertEqual("explicit-token", resolve_service_api_token("explicit-token"))
            with mock.patch.dict(
                os.environ,
                {"BOT_SERVICE_API_TOKEN": "environment-token", SERVICE_API_TOKEN_FILE_ENV: str(token_file)},
                clear=True,
            ):
                self.assertEqual("environment-token", resolve_service_api_token())

            with mock.patch.dict(os.environ, {SERVICE_API_TOKEN_FILE_ENV: str(token_file)}, clear=True), mock.patch(
                "app.service.auth.token.os.name", "posix"
            ), mock.patch(
                "app.service.auth.token.os.fstat",
                return_value=mock.Mock(st_mode=stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR, st_size=len("file-token\n")),
            ):
                self.assertEqual("file-token", resolve_service_api_token())
            with mock.patch.dict(os.environ, {SERVICE_API_TOKEN_FILE_ENV: str(token_file)}, clear=True), mock.patch(
                "app.service.auth.token.os.name", "posix"
            ), mock.patch(
                "app.service.auth.token.os.fstat",
                return_value=mock.Mock(
                    st_mode=stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP,
                    st_size=len("file-token\n"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "must not grant group or other permissions"):
                    resolve_service_api_token()

            token_file.write_text("x" * 4097, encoding="utf-8")
            with mock.patch.dict(os.environ, {SERVICE_API_TOKEN_FILE_ENV: str(token_file)}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "safety limit"):
                    resolve_service_api_token()
            with mock.patch.dict(
                os.environ,
                {SERVICE_API_TOKEN_FILE_ENV: str(token_file.with_name("missing-token"))},
                clear=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "readable file"):
                    resolve_service_api_token()

    def test_tls_enabled_service_api_reports_https_urls_to_desktop_clients(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            certificate = Path(temporary_directory) / "service.crt"
            private_key = Path(temporary_directory) / "service.key"
            certificate.write_text("certificate", encoding="utf-8")
            private_key.write_text("private-key", encoding="utf-8")
            private_key.chmod(stat.S_IRUSR | stat.S_IWUSR)
            with mock.patch.dict(
                os.environ,
                {
                    "BOT_SERVICE_API_TLS_CERTFILE": str(certificate),
                    "BOT_SERVICE_API_TLS_KEYFILE": str(private_key),
                },
                clear=False,
            ):
                self.assertEqual("https", service_api_url_scheme())
                host = ServiceApiBackgroundHost(host="127.0.0.1", port=8443, api_token="token-123")
                self.assertEqual("https://127.0.0.1:8443", host.describe()["url"])
                settings = _resolve_desktop_service_api_settings(object(), host="127.0.0.1", port=8443)
                self.assertEqual("https://127.0.0.1:8443", settings["url"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_exposed_service_api_requires_token(self):
        with self.assertRaisesRegex(RuntimeError, "BOT_SERVICE_API_TOKEN"):
            run_service_api_server(host="0.0.0.0", port=8000, api_token="")
        with self.assertRaisesRegex(RuntimeError, "BOT_SERVICE_API_TOKEN"):
            ServiceApiBackgroundHost(host="0.0.0.0", port=8000, api_token="")
        with self.assertRaisesRegex(RuntimeError, "requires TLS"):
            run_service_api_server(
                host="0.0.0.0",
                port=8000,
                api_token="x" * MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH,
            )

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_config_validation_errors_are_client_errors(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            response = client.patch(
                f"{SERVICE_API_BASE_PATH}/config",
                headers={"Authorization": "Bearer token-123"},
                json={"config": {"leverage": 0, "position_pct": 0}},
            )

        self.assertEqual(422, response.status_code)
        self.assertFalse(any("HTTP_422_UNPROCESSABLE_ENTITY" in str(item.message) for item in caught))
        detail = response.json()["detail"]
        fields = {issue["field"] for issue in detail["issues"]}
        self.assertIn("leverage", fields)
        self.assertIn("position_pct", fields)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_config_persistence_routes_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "service-config.json"
            service = TradingBotService(config_path=path)
            app = create_service_api_app(service=service, api_token="token-123")
            client = _create_test_client(app)
            headers = {"Authorization": "Bearer token-123"}

            patch_response = client.patch(
                f"{SERVICE_API_BASE_PATH}/config",
                headers=headers,
                json={"config": {"symbols": ["ETHUSDT"], "intervals": ["5m"], "theme": "Dark"}},
            )
            self.assertEqual(200, patch_response.status_code)
            self.assertFalse(path.exists())

            status_response = client.get(
                f"{SERVICE_API_BASE_PATH}/config/persistence",
                headers=headers,
            )
            self.assertEqual(200, status_response.status_code)
            self.assertTrue(status_response.json()["dirty"])

            save_response = client.post(
                f"{SERVICE_API_BASE_PATH}/config/save",
                headers=headers,
                json={"source": "api-smoke"},
            )
            self.assertEqual(200, save_response.status_code)
            self.assertTrue(path.is_file())
            self.assertFalse(save_response.json()["dirty"])

            unsafe_path_response = client.post(
                f"{SERVICE_API_BASE_PATH}/config/save",
                headers=headers,
                json={"path": str(Path(tmp) / "manual-service-config.json"), "source": "api-smoke"},
            )
            self.assertEqual(403, unsafe_path_response.status_code)

            client.patch(
                f"{SERVICE_API_BASE_PATH}/config",
                headers=headers,
                json={"config": {"theme": "Light"}},
            )
            load_response = client.post(
                f"{SERVICE_API_BASE_PATH}/config/load",
                headers=headers,
                json={"source": "api-smoke"},
            )

            self.assertEqual(200, load_response.status_code)
            payload = load_response.json()
            self.assertEqual("Dark", payload["config"]["theme"])
            self.assertFalse(payload["persistence"]["dirty"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_desktop_embedded_service_api_write_routes_require_token(self):
        app = create_service_api_app(
            service=TradingBotService(),
            host_context="desktop-embedded",
            host_owner="desktop-gui",
            api_token="",
        )
        client = _create_test_client(app)

        read_response = client.get(f"{SERVICE_API_BASE_PATH}/dashboard")
        self.assertEqual(200, read_response.status_code)
        self.assertTrue(read_response.json()["service_api"]["write_auth_required"])

        write_response = client.patch(
            f"{SERVICE_API_BASE_PATH}/config",
            json={"config": {"theme": "Dark"}},
        )
        self.assertEqual(403, write_response.status_code)
        self.assertIn("Write endpoints require", write_response.json()["detail"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_standalone_service_api_write_routes_require_token(self):
        app = create_service_api_app(
            service=TradingBotService(),
            host_context="standalone-service",
            host_owner="service-process",
            api_token="",
        )
        client = _create_test_client(app)

        read_response = client.get(f"{SERVICE_API_BASE_PATH}/dashboard")
        self.assertEqual(200, read_response.status_code)
        self.assertTrue(read_response.json()["service_api"]["write_auth_required"])

        write_response = client.post(
            f"{SERVICE_API_BASE_PATH}/logs",
            json={"message": "write attempt"},
        )
        self.assertEqual(403, write_response.status_code)
        self.assertIn("Write endpoints require", write_response.json()["detail"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_reports_unsafe_escape_hatches_in_metadata(self):
        with mock.patch.dict(
            "os.environ",
            {
                "BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES": "1",
                "BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS": "1",
                "BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH": "1",
            },
            clear=False,
        ):
            app = create_service_api_app(service=TradingBotService(), api_token="")
            client = _create_test_client(app)
            response = client.get("/health")

        self.assertEqual(200, response.status_code)
        service_api = response.json()["service_api"]
        security = service_api["security"]
        self.assertTrue(service_api["unsafe_flags_active"])
        self.assertFalse(service_api["write_auth_required"])
        self.assertTrue(security["unauthenticated_writes_allowed"])
        self.assertFalse(security["inline_config_secrets_allowed"])
        self.assertTrue(security["legacy_inline_config_secrets_requested"])
        self.assertTrue(security["unsafe_config_paths_allowed"])
        self.assertIn("BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES", " ".join(security["warnings"]))
        self.assertEqual("BOT_SERVICE_API_MAX_REQUEST_BYTES", service_api["limits"]["env_vars"]["max_request_bytes"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_rejects_oversized_request_bodies(self):
        with mock.patch.dict("os.environ", {"BOT_SERVICE_API_MAX_REQUEST_BYTES": "64"}, clear=False):
            app = create_service_api_app(service=TradingBotService(), api_token="token-123")
            client = _create_test_client(app)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", DeprecationWarning)
                response = client.post(
                    f"{SERVICE_API_BASE_PATH}/logs",
                    headers={"Authorization": "Bearer token-123"},
                    json={"message": "x" * 200},
                )

        self.assertEqual(413, response.status_code)
        self.assertIn("too large", response.json()["detail"])
        self.assertEqual("no-store", response.headers.get("cache-control"))
        self.assertEqual("nosniff", response.headers.get("x-content-type-options"))
        self.assertFalse(any("HTTP_413_REQUEST_ENTITY_TOO_LARGE" in str(item.message) for item in caught))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_rejects_oversized_request_bodies_without_content_length(self):
        with mock.patch.dict("os.environ", {"BOT_SERVICE_API_MAX_REQUEST_BYTES": "64"}, clear=False):
            app = create_service_api_app(service=TradingBotService(), api_token="token-123")
            client = _create_test_client(app)
            request = client.build_request(
                "POST",
                f"{SERVICE_API_BASE_PATH}/logs",
                headers={"Authorization": "Bearer token-123", "content-type": "application/json"},
                content=b'{"message":"' + (b"x" * 200) + b'"}',
            )
            request.headers.pop("content-length", None)
            response = client.send(request)

        self.assertEqual(413, response.status_code)
        self.assertIn("too large", response.json()["detail"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_can_rate_limit_write_routes(self):
        with mock.patch.dict("os.environ", {"BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE": "1"}, clear=False):
            app = create_service_api_app(service=TradingBotService(), api_token="token-123")
            client = _create_test_client(app)
            headers = {"Authorization": "Bearer token-123"}

            first = client.post(
                f"{SERVICE_API_BASE_PATH}/logs",
                headers=headers,
                json={"message": "first"},
            )
            second = client.post(
                f"{SERVICE_API_BASE_PATH}/logs",
                headers=headers,
                json={"message": "second"},
            )

        self.assertEqual(200, first.status_code)
        self.assertEqual(429, second.status_code)
        self.assertEqual("60", second.headers.get("retry-after"))
        self.assertEqual("no-store", second.headers.get("cache-control"))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_sensitive_responses_disable_intermediary_caching(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)

        for path in ("/health", "/livez", "/readyz", f"{SERVICE_API_BASE_PATH}/dashboard"):
            response = client.get(path, headers={"Authorization": "Bearer token-123"})
            self.assertEqual(200, response.status_code, path)
            self.assertEqual("no-store", response.headers.get("cache-control"), path)
            self.assertEqual("no-cache", response.headers.get("pragma"), path)
            self.assertEqual("no-referrer", response.headers.get("referrer-policy"), path)
            self.assertEqual("nosniff", response.headers.get("x-content-type-options"), path)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_bounds_rate_limit_client_tracking(self):
        with mock.patch.dict(
            "os.environ",
            {
                "BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE": "1",
                "BOT_SERVICE_API_WRITE_RATE_LIMIT_MAX_CLIENTS": "1",
            },
            clear=False,
        ):
            app = create_service_api_app(service=TradingBotService(), api_token="token-123")
            app.state.service_api_rate_limit_windows["existing-client"] = {
                "started_at": time.monotonic(),
                "count": 1,
            }
            client = _create_test_client(app)
            response = client.post(
                f"{SERVICE_API_BASE_PATH}/logs",
                headers={"Authorization": "Bearer token-123"},
                json={"message": "capacity"},
            )

        self.assertEqual(429, response.status_code)
        self.assertEqual("60", response.headers.get("retry-after"))
        self.assertIn("client capacity", response.json()["detail"])
        self.assertEqual({"existing-client"}, set(app.state.service_api_rate_limit_windows))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_non_loopback_service_api_enforces_a_nonzero_write_rate_limit(self):
        with mock.patch.dict("os.environ", {"BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE": ""}, clear=False):
            app = create_service_api_app(
                service=TradingBotService(),
                api_token="token-123",
                bound_host="0.0.0.0",
            )
            client = _create_test_client(app)
            response = client.get("/health")

        self.assertEqual(200, response.status_code)
        limits = response.json()["service_api"]["limits"]
        self.assertTrue(limits["non_loopback_binding"])
        self.assertEqual(60, limits["write_rate_limit_per_minute"])
        self.assertEqual(10_000, limits["write_rate_limit_max_clients"])

        with mock.patch.dict("os.environ", {"BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE": "0"}, clear=False):
            app = create_service_api_app(
                service=TradingBotService(),
                api_token="token-123",
                bound_host="192.168.1.10",
            )
            client = _create_test_client(app)
            response = client.get("/health")

        self.assertEqual(1, response.json()["service_api"]["limits"]["write_rate_limit_per_minute"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_desktop_embedded_service_api_write_routes_accept_bearer_token(self):
        app = create_service_api_app(
            service=TradingBotService(),
            host_context="desktop-embedded",
            host_owner="desktop-gui",
            api_token="token-123",
        )
        client = _create_test_client(app)

        unauthorized = client.patch(
            f"{SERVICE_API_BASE_PATH}/config",
            json={"config": {"theme": "Dark"}},
        )
        self.assertEqual(401, unauthorized.status_code)

        authorized = client.patch(
            f"{SERVICE_API_BASE_PATH}/config",
            headers={"Authorization": "Bearer token-123"},
            json={"config": {"theme": "Dark"}},
        )
        self.assertEqual(200, authorized.status_code)
        self.assertEqual("Dark", authorized.json()["theme"])

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_stream_accepts_authorization_header(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)

        unauthorized = client.get(f"{SERVICE_API_BASE_PATH}/stream/dashboard")
        self.assertEqual(401, unauthorized.status_code)

        query_token = client.get(f"{SERVICE_API_BASE_PATH}/stream/dashboard?token=token-123&max_events=1")
        self.assertEqual(401, query_token.status_code)

        with client.stream(
            "GET",
            f"{SERVICE_API_BASE_PATH}/stream/dashboard?interval_ms=250&max_events=1",
            headers={"Authorization": "Bearer token-123"},
        ) as response:
            self.assertEqual(200, response.status_code)
            lines = response.iter_lines()
            self.assertEqual("event: dashboard", next(lines))

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_runtime_and_dashboard_routes_expose_contract_control_plane(self):
        sample_path = REPO_ROOT / "apps" / "service-api" / "contracts" / "runtime.sample.json"
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        app = create_service_api_app()
        client = _create_test_client(app)

        runtime_response = client.get(SERVICE_API_ROUTE_PATHS["runtime"])
        dashboard_response = client.get(SERVICE_API_ROUTE_PATHS["dashboard"])

        self.assertEqual(200, runtime_response.status_code)
        self.assertEqual(200, dashboard_response.status_code)
        runtime = runtime_response.json()
        dashboard = dashboard_response.json()

        self.assertEqual(set(sample), set(runtime))
        self.assertEqual(_shape(sample), _shape(runtime))
        self.assertEqual(sample["capabilities"], runtime["capabilities"])
        self.assertEqual(sample["control_plane"], runtime["control_plane"])
        self.assertEqual(sample["control_plane"], dashboard["runtime"]["control_plane"])
        self.assertEqual(runtime["service_name"], dashboard["runtime"]["service_name"])
        self.assertEqual(runtime["phase"], dashboard["runtime"]["phase"])
        self.assertEqual("local-service-executor", runtime["control_plane"]["mode"])
        self.assertEqual("service-process", runtime["control_plane"]["owner"])
        self.assertTrue(runtime["control_plane"]["start_supported"])
        self.assertTrue(runtime["control_plane"]["stop_supported"])
        self.assertEqual("service-lifecycle-heartbeat", runtime["control_plane"]["execution_scope"])
        self.assertFalse(runtime["control_plane"]["trading_execution_supported"])
        self.assertIn(
            "This adapter only maintains a service lifecycle heartbeat.",
            runtime["control_plane"]["notes"],
        )
        self.assertEqual("standalone-service", dashboard["service_api"]["host_context"])
        self.assertEqual("service-process", dashboard["service_api"]["host_owner"])
        self.assertEqual("service-lifecycle-heartbeat", dashboard["service_api"]["execution_scope"])
        self.assertFalse(dashboard["service_api"]["trading_execution_supported"])
