# ruff: noqa: E402
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.desktop import service_bridge


class _FakeDesktopClient:
    def __init__(self, config=None):
        self.config = config
        self.exchange_connector_snapshot = None
        self.connector_order_circuit_breaker_snapshot = None

    def replace_config(self, config):
        self.config = config

    def set_exchange_connector_snapshot(self, snapshot=None, **kwargs):
        self.exchange_connector_snapshot = dict(snapshot or {})
        self.exchange_connector_snapshot.update(kwargs)
        return self.exchange_connector_snapshot

    def set_connector_order_circuit_breaker_snapshot(self, snapshot=None, **kwargs):
        self.connector_order_circuit_breaker_snapshot = dict(snapshot or {})
        self.connector_order_circuit_breaker_snapshot.update(kwargs)
        return self.connector_order_circuit_breaker_snapshot

    def reset_connector_order_circuit_breaker(self, *, source="desktop", force=False):
        self.connector_order_circuit_breaker_snapshot = {
            "active": False,
            "state": "closed",
            "source": source,
            "force": force,
        }
        return self.connector_order_circuit_breaker_snapshot

    def get_connector_order_circuit_breaker_snapshot(self):
        return self.connector_order_circuit_breaker_snapshot


class DesktopServiceBridgeSmokeTests(unittest.TestCase):
    def test_bind_main_window_desktop_service_bridge_attaches_methods(self):
        class DummyWindow:
            def __init__(self):
                self.config = {"demo": True}

        service_bridge.bind_main_window_desktop_service_bridge(
            DummyWindow,
            desktop_service_client_factory=lambda config=None: _FakeDesktopClient(config=config),
        )

        window = DummyWindow()
        window._initialize_desktop_service_bridge()

        expected_methods = [
            "_initialize_desktop_service_bridge",
            "_register_service_control_dispatcher",
            "_queue_service_control_request",
            "_handle_service_control_request",
            "_sync_service_config_snapshot",
            "_sync_service_runtime_snapshot",
            "_sync_service_account_snapshot",
            "_sync_service_portfolio_snapshot",
            "_sync_service_exchange_connector_snapshot",
            "_sync_service_connector_order_circuit_breaker_snapshot",
            "_reset_service_connector_order_circuit_breaker",
            "_service_request_start",
            "_service_request_stop",
            "_service_mark_start_failed",
            "_service_record_log_event",
            "_get_service_client_descriptor",
            "_get_service_account_snapshot",
            "_get_service_status_snapshot",
            "_get_service_config_summary",
            "_get_service_portfolio_snapshot",
            "_get_service_exchange_connector_snapshot",
            "_get_service_operational_snapshot",
            "_get_service_connector_order_circuit_breaker_snapshot",
            "_get_service_recent_logs",
            "_maybe_start_desktop_service_api_host",
            "_shutdown_desktop_service_api_host",
            "_get_desktop_service_api_host_status",
        ]
        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(DummyWindow, method_name))
                self.assertTrue(callable(getattr(DummyWindow, method_name)))
        self.assertIsInstance(window._desktop_service_client, _FakeDesktopClient)
        self.assertEqual(window._desktop_service_client.config, {"demo": True})


if __name__ == "__main__":
    unittest.main()
