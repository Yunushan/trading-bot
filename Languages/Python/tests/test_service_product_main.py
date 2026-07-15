import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.service import product_main  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402
from app.settings.validation import ConfigValidationError, ConfigValidationIssue  # noqa: E402


class _FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


class ServiceProductMainTests(unittest.TestCase):
    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            argv = list(args)
            if "--config-path" not in argv and not any(
                option in argv for option in ("--healthcheck", "--serve", "--base-url")
            ):
                argv.extend(("--config-path", str(Path(temp_dir) / "service-config.json")))
            with redirect_stdout(stdout), redirect_stderr(stderr):
                returncode = product_main.main(argv)
        return returncode, stdout.getvalue(), stderr.getvalue()

    def test_healthcheck_is_process_safe_and_does_not_construct_runtime(self):
        with patch.object(product_main, "TradingBotService") as service_class:
            returncode, stdout, stderr = self._run("--healthcheck")

        self.assertEqual(0, returncode)
        self.assertEqual("ok\n", stdout)
        self.assertEqual("", stderr)
        service_class.assert_not_called()

    def test_local_json_descriptor_contains_all_operator_snapshots(self):
        returncode, stdout, stderr = self._run("--json")

        self.assertEqual(0, returncode)
        self.assertEqual("", stderr)
        payload = json.loads(stdout)
        self.assertEqual(
            {
                "account_snapshot",
                "backtest_snapshot",
                "config_persistence",
                "config_summary",
                "control_result",
                "execution_snapshot",
                "log_event",
                "logs",
                "portfolio_snapshot",
                "runtime",
                "status",
                "terminal_result",
            },
            set(payload),
        )
        self.assertFalse(payload["runtime"]["control_plane"]["trading_execution_supported"])

    def test_each_local_snapshot_mode_emits_valid_json(self):
        cases = (
            (("--status",), "mode"),
            (("--config-summary",), "symbol_count"),
            (("--config-persistence",), "path"),
            (("--account-snapshot",), "source"),
            (("--portfolio-snapshot",), "source"),
            (("--execution-snapshot",), "state"),
            (("--backtest-snapshot",), "state"),
            (("--logs",), None),
        )

        for args, expected_key in cases:
            with self.subTest(args=args):
                returncode, stdout, stderr = self._run(*args)
                self.assertEqual(0, returncode)
                self.assertEqual("", stderr)
                payload = json.loads(stdout)
                if expected_key is None:
                    self.assertIsInstance(payload, list)
                else:
                    self.assertIn(expected_key, payload)

    def test_llm_catalog_and_config_outputs_are_json_and_redacted(self):
        for args in (("--llm-providers",), ("--llm-config",)):
            with self.subTest(args=args):
                returncode, stdout, stderr = self._run(*args)
                self.assertEqual(0, returncode)
                self.assertEqual("", stderr)
                json.loads(stdout)
                self.assertNotIn("api_key_value", stdout.lower())

    def test_terminal_log_and_control_modes_return_operator_results(self):
        cases = (
            (("--terminal", "status"), '"mode"'),
            (("--record-log", "launcher smoke"), "launcher smoke"),
            (("--request-start", "--jobs", "2"), "accepted"),
            (("--request-stop", "--close-positions"), "accepted"),
        )

        for args, expected_text in cases:
            with self.subTest(args=args):
                returncode, stdout, stderr = self._run(*args)
                self.assertEqual(0, returncode)
                self.assertEqual("", stderr)
                self.assertIn(expected_text.lower(), stdout.lower())

    def test_default_output_describes_current_execution_boundary(self):
        returncode, stdout, stderr = self._run()

        self.assertEqual(0, returncode)
        self.assertEqual("", stderr)
        self.assertIn("Trading Bot service skeleton is available.", stdout)
        self.assertIn("Standalone start/stop: lifecycle heartbeat only", stdout)
        self.assertIn("Trading runtime: use desktop-hosted API mode", stdout)

    def test_valid_config_patch_can_be_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "saved-config.json"
            returncode, stdout, stderr = self._run(
                "--config-path",
                str(config_path),
                "--config-patch",
                '{"symbols":["BTCUSDT"],"intervals":["1m"]}',
                "--save-config",
                "--config-persistence",
            )

            self.assertEqual(0, returncode)
            self.assertEqual("", stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["exists"])
            self.assertFalse(payload["dirty"])
            self.assertTrue(payload["last_saved_at"])
            self.assertTrue(config_path.is_file())

    def test_invalid_config_patch_json_and_non_object_are_rejected(self):
        for patch_value, expected_text in (("{", "Invalid --config-patch JSON"), ("[]", "expects a JSON object")):
            with self.subTest(patch_value=patch_value):
                returncode, stdout, stderr = self._run("--config-patch", patch_value)
                self.assertEqual(2, returncode)
                self.assertEqual("", stdout)
                self.assertIn(expected_text, stderr)

    def test_config_validation_error_is_reported_without_continuing(self):
        service = unittest.mock.MagicMock()
        issue = ConfigValidationIssue(field="symbols", message="invalid symbol")
        service.update_config.side_effect = ConfigValidationError([issue])

        with patch.object(product_main, "TradingBotService", return_value=service):
            returncode, stdout, stderr = self._run("--config-patch", '{"symbols":["bad"]}')

        self.assertEqual(2, returncode)
        self.assertEqual("", stdout)
        self.assertIn("symbols: invalid symbol", stderr)
        service.describe_runtime.assert_not_called()

    def test_runtime_construction_and_persistence_errors_are_fail_closed(self):
        with patch.object(product_main, "TradingBotService", side_effect=FileNotFoundError("missing config")):
            returncode, stdout, stderr = self._run("--load-config")
        self.assertEqual(2, returncode)
        self.assertEqual("", stdout)
        self.assertIn("missing config", stderr)

        with patch.object(TradingBotService, "save_config", side_effect=OSError("disk full")):
            returncode, stdout, stderr = self._run("--save-config")
        self.assertEqual(2, returncode)
        self.assertEqual("", stdout)
        self.assertIn("disk full", stderr)

    def test_serve_delegates_validated_settings_and_reports_failure(self):
        with patch.object(product_main, "run_service_api_server") as run_server:
            returncode, stdout, stderr = self._run(
                "--serve",
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
                "--api-token",
                "test-token",
                "--config-path",
                "service.json",
                "--load-config",
            )
        self.assertEqual(0, returncode)
        self.assertEqual("", stdout)
        self.assertEqual("", stderr)
        run_server.assert_called_once_with(
            host="127.0.0.1",
            port=8123,
            api_token="test-token",
            config_path="service.json",
            load_persisted_config=True,
        )

        with patch.object(product_main, "run_service_api_server", side_effect=ValueError("unsafe bind")):
            returncode, stdout, stderr = self._run("--serve")
        self.assertEqual(2, returncode)
        self.assertEqual("", stdout)
        self.assertIn("unsafe bind", stderr)

    def test_remote_terminal_supports_text_json_and_transport_failures(self):
        remote_payload = {"output": "remote status", "exit_code": 3}
        with patch.object(product_main, "_remote_json_request", return_value=remote_payload) as request:
            returncode, stdout, stderr = self._run(
                "--base-url",
                "http://127.0.0.1:8000/",
                "--api-token",
                "token",
                "--terminal",
                "status",
            )
        self.assertEqual(3, returncode)
        self.assertEqual("remote status\n", stdout)
        self.assertEqual("", stderr)
        request.assert_called_once()

        with patch.object(product_main, "_remote_json_request", return_value=remote_payload):
            returncode, stdout, stderr = self._run(
                "--base-url",
                "http://127.0.0.1:8000",
                "--terminal",
                "status",
                "--json",
            )
        self.assertEqual(3, returncode)
        self.assertEqual(remote_payload, json.loads(stdout))
        self.assertEqual("", stderr)

        with patch.object(product_main, "_remote_json_request", side_effect=RuntimeError("connection refused")):
            returncode, stdout, stderr = self._run(
                "--base-url",
                "http://127.0.0.1:8000",
                "--terminal",
                "status",
            )
        self.assertEqual(1, returncode)
        self.assertEqual("", stdout)
        self.assertIn("connection refused", stderr)

    def test_remote_json_request_builds_authenticated_get_and_post_requests(self):
        responses = (_FakeHttpResponse(b'{"status":"ok"}'), _FakeHttpResponse(b'{"exit_code":0}'))
        with patch.object(product_main, "urlopen", side_effect=responses) as urlopen_mock:
            get_result = product_main._remote_json_request(
                "http://127.0.0.1:8000/",
                "/api/v1/status",
                api_token="secret-token",
            )
            post_result = product_main._remote_json_request(
                "http://127.0.0.1:8000",
                "/api/v1/terminal/run",
                api_token="secret-token",
                payload={"command": "status"},
            )

        self.assertEqual({"status": "ok"}, get_result)
        self.assertEqual({"exit_code": 0}, post_result)
        get_request = urlopen_mock.call_args_list[0].args[0]
        post_request = urlopen_mock.call_args_list[1].args[0]
        self.assertEqual("GET", get_request.method)
        self.assertEqual("POST", post_request.method)
        self.assertEqual("Bearer secret-token", get_request.get_header("Authorization"))
        self.assertEqual("application/json", post_request.get_header("Content-type"))
        self.assertEqual(b'{"command": "status"}', post_request.data)

    def test_remote_json_request_converts_http_error_to_redacted_runtime_error(self):
        error = HTTPError(
            "http://127.0.0.1:8000/api/v1/status",
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":"missing token"}'),
        )
        with patch.object(product_main, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "401 Unauthorized"):
                product_main._remote_json_request("http://127.0.0.1:8000", "/api/v1/status")


if __name__ == "__main__":
    unittest.main()
