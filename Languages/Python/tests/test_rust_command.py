from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import rust_command  # noqa: E402


class RustCommandTests(unittest.TestCase):
    def test_schannel_revocation_failure_is_detected_precisely(self):
        failed = subprocess.CompletedProcess(["cargo"], 101, stdout="", stderr="CRYPT_E_NO_REVOCATION_CHECK")
        unrelated = subprocess.CompletedProcess(["cargo"], 101, stdout="", stderr="connection refused")

        self.assertTrue(rust_command.is_schannel_revocation_failure(failed))
        self.assertFalse(rust_command.is_schannel_revocation_failure(unrelated))

    def test_windows_schannel_failure_retries_through_wsl_without_tls_override(self):
        command = ["cargo", "check", "--workspace", "--locked"]
        native = subprocess.CompletedProcess(command, 101, stdout="", stderr="CRYPT_E_NO_REVOCATION_CHECK")
        wsl_path = subprocess.CompletedProcess(["wsl.exe"], 0, stdout="/mnt/c/workspace\n", stderr="")
        fallback = subprocess.CompletedProcess(command, 0, stdout="Finished", stderr="")
        with mock.patch.object(rust_command.sys, "platform", "win32"), mock.patch.object(
            rust_command.shutil, "which", side_effect=lambda name: "wsl.exe" if name == "wsl.exe" else None
        ), mock.patch.object(
            rust_command, "_write_wsl_environment_file", return_value=(Path("C:/temp/env.sh"), "/mnt/c/temp/env.sh")
        ), mock.patch.object(rust_command.subprocess, "run", side_effect=[native, wsl_path, fallback]) as run:
            result, execution_environment = rust_command.run_cargo_with_secure_wsl_fallback(
                command,
                cwd=Path(r"C:\workspace"),
                env={"BINANCE_TESTNET": "true"},
                timeout=90,
            )

        self.assertEqual(0, result.returncode)
        self.assertEqual("wsl", execution_environment)
        fallback_command = run.call_args_list[-1].args[0]
        self.assertIn("bash", fallback_command)
        self.assertIn("cargo check --workspace --locked", fallback_command[-1])
        self.assertIn("/mnt/c/temp/env.sh", fallback_command[-1])
        self.assertNotIn("BINANCE_TESTNET", fallback_command[-1])
        self.assertNotIn("CHECK_REVOKE", fallback_command[-1])

    def test_wsl_path_normalizes_windows_separators(self):
        converted = subprocess.CompletedProcess(["wsl.exe"], 0, stdout="/mnt/c/workspace\n", stderr="")
        with mock.patch.object(rust_command.subprocess, "run", return_value=converted) as run:
            result = rust_command._wsl_path("wsl.exe", Path(r"C:\\workspace\\nested"), timeout=90)

        self.assertEqual("/mnt/c/workspace", result)
        self.assertEqual("C:/workspace/nested", run.call_args.args[0][-1])

    def test_wsl_environment_file_quotes_values_without_command_line_exposure(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            rust_command.tempfile, "gettempdir", return_value=temp_dir
        ), mock.patch.object(rust_command, "_wsl_path", return_value="/mnt/c/temp/environment.sh"):
            path, wsl_path = rust_command._write_wsl_environment_file(
                "wsl.exe",
                {
                    "BINANCE_API_KEY": "secret value; $(do-not-run)",
                    "RUST_NATIVE_RUNTIME_EVIDENCE_DIR": r"C:\\temp\\evidence",
                    "UNRELATED_VALUE": "not-forwarded",
                },
                timeout=90,
            )
            self.assertIsNotNone(path)
            assert path is not None
            contents = path.read_text(encoding="utf-8")
            path.unlink()

        self.assertEqual("/mnt/c/temp/environment.sh", wsl_path)
        self.assertIn("BINANCE_API_KEY='secret value; $(do-not-run)'", contents)
        self.assertIn("RUST_NATIVE_RUNTIME_EVIDENCE_DIR=", contents)
        self.assertNotIn("UNRELATED_VALUE", contents)

    def test_wsl_nonzero_result_preserves_the_fallback_output(self):
        command = ["cargo", "run", "--locked"]
        native = subprocess.CompletedProcess(command, 101, stdout="", stderr="CRYPT_E_NO_REVOCATION_CHECK")
        wsl_path = subprocess.CompletedProcess(["wsl.exe"], 0, stdout="/mnt/c/workspace\n", stderr="")
        fallback = subprocess.CompletedProcess(command, 1, stdout="{\"ok\": false}", stderr="expected preflight failure")
        with mock.patch.object(rust_command.sys, "platform", "win32"), mock.patch.object(
            rust_command.shutil, "which", side_effect=lambda name: "wsl.exe" if name == "wsl.exe" else None
        ), mock.patch.object(
            rust_command, "_write_wsl_environment_file", return_value=(None, "")
        ), mock.patch.object(rust_command.subprocess, "run", side_effect=[native, wsl_path, fallback]):
            result, execution_environment = rust_command.run_cargo_with_secure_wsl_fallback(
                command,
                cwd=Path(r"C:\\workspace"),
                timeout=90,
            )

        self.assertEqual(1, result.returncode)
        self.assertEqual("wsl", execution_environment)
        self.assertEqual('{"ok": false}', result.stdout)
        self.assertIn("completed with exit code 1", result.stderr)

    def test_unrelated_cargo_failure_does_not_attempt_wsl(self):
        command = ["cargo", "check", "--workspace", "--locked"]
        native = subprocess.CompletedProcess(command, 101, stdout="", stderr="connection refused")
        with mock.patch.object(rust_command.sys, "platform", "win32"), mock.patch.object(
            rust_command.subprocess, "run", return_value=native
        ) as run:
            result, execution_environment = rust_command.run_cargo_with_secure_wsl_fallback(
                command,
                cwd=Path(r"C:\workspace"),
                timeout=90,
            )

        self.assertEqual(101, result.returncode)
        self.assertEqual("native", execution_environment)
        run.assert_called_once()
