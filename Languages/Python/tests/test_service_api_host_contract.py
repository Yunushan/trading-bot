# ruff: noqa: E402

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.service.api import host as host_module
from app.service.api.host import ServiceApiBackgroundHost


class ServiceApiHostContractTests(unittest.TestCase):
    def test_background_host_rejects_ports_outside_tcp_range_before_startup(self):
        for port in (0, -1, 65_536, "not-a-port"):
            with self.subTest(port=port):
                with self.assertRaisesRegex(ValueError, "port"):
                    ServiceApiBackgroundHost(port=port, api_token="test-token")

    def test_background_host_retains_valid_port_in_description(self):
        host = ServiceApiBackgroundHost(port="8443", api_token="test-token")

        self.assertEqual(8443, host.port)
        self.assertEqual(8443, host.describe()["port"])

    def test_pre_server_stop_request_is_forwarded_when_uvicorn_is_created(self):
        instances = []

        class _FakeServer:
            def __init__(self, _config):
                self.should_exit = False
                self.install_signal_handlers = None
                self.observed_shutdown_request = False
                instances.append(self)

            async def serve(self):
                self.observed_shutdown_request = self.should_exit

        fake_uvicorn = SimpleNamespace(Config=lambda *_args, **_kwargs: object(), Server=_FakeServer)
        host = ServiceApiBackgroundHost(api_token="test-token")
        host._shutdown_requested = True

        with mock.patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            host._run_server()

        self.assertEqual(1, len(instances))
        self.assertTrue(instances[0].observed_shutdown_request)

    def test_start_timeout_requests_shutdown_for_a_pre_server_thread(self):
        host = ServiceApiBackgroundHost(api_token="test-token")
        entered = threading.Event()

        def wait_for_shutdown():
            entered.set()
            while not host._shutdown_requested:
                time.sleep(0.005)

        with (
            mock.patch.object(host_module, "create_service_api_app", return_value=object()),
            mock.patch.object(host, "_run_server", side_effect=wait_for_shutdown),
        ):
            with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                host.start(timeout_seconds=0.5)

        self.assertTrue(entered.is_set())
        self.assertTrue(host._shutdown_requested)
        self.assertFalse(host._thread and host._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
