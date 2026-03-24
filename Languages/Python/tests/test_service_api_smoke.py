import json
import socket
import sys
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import EmbeddedDesktopServiceClient, RemoteDesktopServiceClient, create_desktop_service_client
from app.service.auth import auth_required, validate_bearer_token
from app.service import (
    FASTAPI_AVAILABLE,
    ServiceApiBackgroundHost,
    TradingBotService,
    create_service_api_app,
)


class ServiceApiSmokeTests(unittest.TestCase):
    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_service_api_app_exposes_expected_routes(self):
        app = create_service_api_app()
        paths = {route.path for route in app.router.routes}
        self.assertIn("/", paths)
        self.assertIn("/health", paths)
        self.assertIn("/ui", paths)
        self.assertIn("/api/dashboard", paths)
        self.assertIn("/api/stream/dashboard", paths)
        self.assertIn("/api/config", paths)
        self.assertIn("/api/status", paths)
        self.assertIn("/api/config-summary", paths)
        self.assertIn("/api/account", paths)
        self.assertIn("/api/portfolio", paths)
        self.assertIn("/api/logs", paths)
        self.assertEqual(app.state.service_api_host_context, "standalone-service")
        self.assertEqual(app.state.service_api_host_owner, "service-process")

    def test_desktop_service_client_defaults_to_embedded_mode(self):
        client = create_desktop_service_client(config={"mode": "Paper"})
        self.assertIsInstance(client, EmbeddedDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "embedded")

    def test_desktop_service_client_can_be_forced_to_remote_mode(self):
        client = create_desktop_service_client(
            client_mode="remote",
            base_url="http://127.0.0.1:9000",
        )
        self.assertIsInstance(client, RemoteDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "remote")
        self.assertEqual(descriptor.get("base_url"), "http://127.0.0.1:9000")

    def test_service_api_auth_helpers(self):
        self.assertFalse(auth_required(""))
        self.assertTrue(validate_bearer_token(None, ""))
        self.assertTrue(validate_bearer_token("Bearer token-123", "token-123"))
        self.assertFalse(validate_bearer_token("Bearer wrong", "token-123"))

    def test_service_config_patch_round_trip(self):
        service = TradingBotService()
        initial_config = service.get_config_payload().to_dict()
        self.assertEqual(initial_config["mode"], "Live")

        payload = service.update_config(
            {
                "mode": "Demo/Testnet",
                "symbols": ["ETHUSDT", "BTCUSDT"],
                "intervals": ["5m", "15m"],
                "leverage": 10,
                "position_pct": 4.5,
            }
        ).to_dict()
        self.assertEqual(payload["mode"], "Demo/Testnet")
        self.assertEqual(payload["symbols"], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual(payload["intervals"], ["5m", "15m"])
        self.assertEqual(payload["leverage"], 10)
        self.assertEqual(payload["position_pct"], 4.5)

        summary = service.get_config_summary().to_dict()
        self.assertEqual(summary["symbol_count"], 2)
        self.assertEqual(summary["interval_count"], 2)

    def test_service_dashboard_snapshot_contains_expected_sections(self):
        service = TradingBotService()
        snapshot = service.get_dashboard_snapshot(log_limit=5)
        self.assertIn("runtime", snapshot)
        self.assertIn("status", snapshot)
        self.assertIn("config", snapshot)
        self.assertIn("config_summary", snapshot)
        self.assertIn("account", snapshot)
        self.assertIn("portfolio", snapshot)
        self.assertIn("logs", snapshot)
        self.assertIsInstance(snapshot["logs"], list)

    def test_service_control_handler_dispatches_non_desktop_requests(self):
        service = TradingBotService()
        dispatched: list[dict] = []

        def _handler(request):
            dispatched.append(request.to_dict())
            return {"accepted": True, "message": "Forwarded to desktop GUI."}

        service.set_control_request_handler(_handler)
        result = service.request_start(requested_job_count=2, source="web-ui").to_dict()

        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0]["action"], "start")
        self.assertTrue(result["accepted"])
        self.assertIn("Forwarded to desktop GUI.", result["status_message"])

        service.request_start(requested_job_count=1, source="desktop-start")
        self.assertEqual(len(dispatched), 1)

    def test_service_control_handler_can_reject_requests(self):
        service = TradingBotService()

        def _handler(_request):
            return {"accepted": False, "message": "Desktop control dispatch unavailable."}

        service.set_control_request_handler(_handler)
        result = service.request_stop(close_positions=True, source="web-ui").to_dict()
        status = service.get_status().to_dict()

        self.assertFalse(result["accepted"])
        self.assertIn("dispatch unavailable", result["status_message"].lower())
        self.assertEqual(status["lifecycle_phase"], "idle")
        self.assertEqual(status["requested_action"], "")

    @unittest.skipUnless(FASTAPI_AVAILABLE, "FastAPI optional dependencies are not installed")
    def test_background_service_api_host_serves_embedded_service_state(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        client = create_desktop_service_client(config={"mode": "Demo/Testnet"})
        self.assertIsInstance(client, EmbeddedDesktopServiceClient)
        host = ServiceApiBackgroundHost(
            service=client.service,
            host="127.0.0.1",
            port=port,
            api_token="token-123",
        )
        try:
            self.assertTrue(host.start(timeout_seconds=5.0))
            request = Request(
                f"http://127.0.0.1:{port}/api/dashboard",
                headers={"Authorization": "Bearer token-123"},
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["status"]["mode"], "Demo/Testnet")
            self.assertEqual(payload["service_api"]["host_context"], "desktop-embedded")
            self.assertEqual(payload["service_api"]["host_owner"], "desktop-gui")
            self.assertTrue(host.describe()["running"])
            self.assertEqual(host.describe()["host_context"], "desktop-embedded")
        finally:
            self.assertTrue(host.stop(timeout_seconds=5.0))


if __name__ == "__main__":
    unittest.main()
