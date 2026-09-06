from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import run_operational_recovery_drill as recovery  # noqa: E402


def _child(pid):
    child = mock.Mock(pid=pid)
    child.poll.return_value = None
    child.wait.return_value = -9
    child.kill.side_effect = lambda: setattr(child.poll, "return_value", -9)
    child.terminate.side_effect = lambda: setattr(child.poll, "return_value", 0)
    return child


def _ready_observation():
    return {"ready": True, "config_matches": True, "read_only_verified": True, "auth_verified": True, "status_codes": [200] * 4}


class OperationalRecoveryProcessTests(unittest.TestCase):
    def test_child_environment_does_not_inherit_trading_secrets_or_transport_overrides(self):
        inherited = {
            "PATH": os.environ.get("PATH", ""), "SystemRoot": os.environ.get("SystemRoot", ""),
            "BOT_ENABLE_LIVE_TRADING": "1", "BOT_LIVE_TRADING_ACK": "private",
            "BINANCE_API_KEY": "private", "BOT_SERVICE_API_TOKEN": "private",
            "HTTP_PROXY": "http://private.invalid", "HTTPS_PROXY": "http://private.invalid",
            "PYTHONPATH": "private", "LD_PRELOAD": "private", "BOT_SERVICE_API_TLS_KEYFILE": "private",
            "BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES": "1", "BOT_SERVICE_API_READ_ONLY": "0",
        }
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, inherited, clear=True):
            environment = recovery._child_environment(Path(temporary) / "config.json", "fresh-synthetic-token")
            self.assertEqual(temporary, environment["HOME"])
            self.assertEqual(temporary, environment["USERPROFILE"])
        self.assertEqual("1", environment["BOT_SERVICE_API_READ_ONLY"])
        self.assertEqual("0", environment["BOT_ENABLE_LIVE_TRADING"])
        self.assertEqual("fresh-synthetic-token", environment["BOT_SERVICE_API_TOKEN"])
        for key in ("BINANCE_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "PYTHONPATH", "LD_PRELOAD", "BOT_SERVICE_API_TLS_KEYFILE", "BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES", "BOT_LIVE_TRADING_ACK"):
            self.assertNotIn(key, environment)

    def test_status_200_alone_cannot_establish_readiness(self):
        expected = {"symbols": ["BTCUSDT"]}
        for fault in (None, "liveness", "readiness", "runtime", "config", "auth", "read-only", "executor"):
            with self.subTest(fault=fault):
                responses = {
                    "/livez": {"status": "ok"},
                    "/readyz": {"status": "ready", "read_only": True},
                    "/api/v1/runtime": {"service_name": "trading-bot-service", "control_plane": {"trading_execution_supported": False}},
                    "/api/v1/config": expected,
                }
                if fault in ("liveness", "readiness", "runtime", "config"):
                    path = {"liveness": "/livez", "readiness": "/readyz", "runtime": "/api/v1/runtime", "config": "/api/v1/config"}[fault]
                    responses[path] = {"status": "wrong"}
                elif fault == "read-only":
                    responses["/readyz"]["read_only"] = False
                elif fault == "executor":
                    responses["/api/v1/runtime"]["control_plane"]["trading_execution_supported"] = True

                def read(url, *, api_token, deadline):
                    if not api_token:
                        return (200 if fault == "auth" else 401), {}
                    return 200, responses[url.removeprefix("http://127.0.0.1:43210")]

                with mock.patch.object(recovery, "_read_only_json", side_effect=read):
                    result = recovery._wait_for_service(_child(1001), "http://127.0.0.1:43210", "synthetic", expected, time.perf_counter() + 0.02)
                self.assertEqual(fault is None, result["ready"])

    def test_configuration_comparison_ignores_only_host_catalog_metadata(self):
        expected = {"llm": {"model": "chosen-model", "api_key_present": False, "catalog_path": "/parent/catalog.json", "model_suggestions": ["parent-model"]}}
        actual = {"llm": {**expected["llm"], "catalog_path": "/child/catalog.json", "model_suggestions": ["child-model"]}}
        self.assertEqual(recovery._persisted_config_view(expected), recovery._persisted_config_view(actual))
        for field, value in (("model", "wrong-model"), ("api_key_present", True)):
            with self.subTest(field=field):
                changed = {"llm": {**actual["llm"], field: value}}
                self.assertNotEqual(recovery._persisted_config_view(expected), recovery._persisted_config_view(changed))

    def test_recovery_failure_paths_stop_all_children_and_do_not_report_success(self):
        faults = (None, "original-not-ready", "endpoint-still-up", "restore-failed", "wrong-backup", "replacement-start-failed", "replacement-not-ready", "normal-exit", "same-pid")
        for fault in faults:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config_path = root / "config.json"
                backup_path = root / "backup.json"
                config_path.write_text('{"config": {"theme": "Dark"}}', encoding="utf-8")
                backup_path.write_bytes(config_path.read_bytes())
                original = _child(1001)
                replacement = _child(1001 if fault == "same-pid" else 1002)
                original_observation = _ready_observation()
                replacement_observation = _ready_observation()
                if fault == "original-not-ready":
                    original_observation["ready"] = False
                if fault == "replacement-not-ready":
                    replacement_observation["ready"] = False
                if fault == "normal-exit":
                    original.wait.return_value = 0
                launch_results = [original, OSError("synthetic launch failure") if fault == "replacement-start-failed" else replacement]
                restore = recovery._restore_config_backup

                def restore_with_fault(config, backup):
                    if fault == "restore-failed":
                        raise OSError("synthetic restore failure")
                    if fault == "wrong-backup":
                        config.write_text("wrong backup", encoding="utf-8")
                        return
                    restore(config, backup)

                with (
                    mock.patch.object(recovery, "_reserve_loopback_port", return_value=43210),
                    mock.patch.object(recovery, "_launch_child", side_effect=launch_results) as launch,
                    mock.patch.object(recovery, "_wait_for_service", side_effect=[original_observation, replacement_observation]),
                    mock.patch.object(recovery, "_read_only_json", return_value=(200 if fault == "endpoint-still-up" else 0, {})),
                    mock.patch.object(recovery, "_restore_config_backup", side_effect=restore_with_fault),
                ):
                    result = recovery._run_canonical_service_restart(
                        config_path=config_path, backup_path=backup_path, expected_config={},
                        backup_created_at=time.perf_counter(), timeout_seconds=1.0,
                    )
                self.assertEqual("pass" if fault is None else "fail", result["status"])
                self.assertTrue(result["children_stopped"])
                self.assertIsNotNone(original.poll())
                if launch.call_count == 2 and fault != "replacement-start-failed":
                    self.assertIsNotNone(replacement.poll())
                    self.assertEqual(launch.call_args_list[0].args[1], launch.call_args_list[1].args[1])
                    self.assertNotEqual(launch.call_args_list[0].args[2], launch.call_args_list[1].args[2])
                if fault is None:
                    original.kill.assert_called_once()
                    self.assertEqual(config_path.read_bytes(), backup_path.read_bytes())
                    timeline = result["timeline_seconds"]
                    self.assertEqual(result["recovery_time_seconds"], timeline["replacement_ready"] - timeline["forced_exit_requested"])

    def test_atomic_restore_failure_preserves_config_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            backup = root / "backup.json"
            config.write_bytes(b"damaged")
            backup.write_bytes(b"backup")
            with mock.patch.object(recovery.os, "replace", side_effect=OSError("synthetic replacement failure")):
                with self.assertRaises(OSError):
                    recovery._restore_config_backup(config, backup)
            self.assertEqual(b"damaged", config.read_bytes())
            self.assertEqual(b"backup", backup.read_bytes())
            self.assertEqual([], list(root.glob(".restore-*")))


if __name__ == "__main__":
    unittest.main()
