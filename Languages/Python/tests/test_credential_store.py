import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.security import credential_store  # noqa: E402


class CredentialStoreTests(unittest.TestCase):
    def _command_result(self, *, returncode=0, stdout="", stderr=""):
        return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_macos_keychain_round_trip_uses_account_scoped_generic_password(self):
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="Darwin"
        ), mock.patch("app.security.credential_store.shutil.which", return_value="/usr/bin/security"), mock.patch(
            "app.security.credential_store.subprocess.run",
            side_effect=[self._command_result(), self._command_result(stdout="secret-value\n")],
        ) as run:
            self.assertEqual("macos-keychain", credential_store.credential_store_backend())
            credential_store.put_secret(scope="scope", account="api_key", value="secret-value")
            self.assertEqual("secret-value", credential_store.get_secret(scope="scope", account="api_key"))

        self.assertEqual("security", run.call_args_list[0].args[0][0])
        self.assertIn("TradingBot/scope/api_key", run.call_args_list[0].args[0])
        self.assertIn("find-generic-password", run.call_args_list[1].args[0])

    def test_linux_secret_service_uses_stdin_and_can_delete_a_secret(self):
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="Linux"
        ), mock.patch("app.security.credential_store.shutil.which", return_value="/usr/bin/secret-tool"), mock.patch(
            "app.security.credential_store.subprocess.run",
            side_effect=[self._command_result(), self._command_result(stdout="secret-value\n"), self._command_result()],
        ) as run:
            self.assertEqual("linux-secret-service", credential_store.credential_store_backend())
            credential_store.put_secret(scope="scope", account="api_key", value="secret-value")
            self.assertEqual("secret-value", credential_store.get_secret(scope="scope", account="api_key"))
            credential_store.delete_secret(scope="scope", account="api_key")

        self.assertEqual("secret-tool", run.call_args_list[0].args[0][0])
        self.assertEqual("secret-value", run.call_args_list[0].kwargs["input"])
        self.assertIn("lookup", run.call_args_list[1].args[0])
        self.assertIn("clear", run.call_args_list[2].args[0])

    def test_unsupported_platform_refuses_secret_persistence(self):
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="FreeBSD"
        ):
            self.assertEqual("unavailable", credential_store.credential_store_backend())
            with self.assertRaises(credential_store.CredentialStoreUnavailable):
                credential_store.put_secret(scope="scope", account="api_key", value="secret-value")
