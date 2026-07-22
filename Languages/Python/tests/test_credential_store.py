import ctypes
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

    def test_macos_keychain_round_trip_uses_native_keychain_api_without_secret_arguments(self):
        security = mock.Mock()
        security.SecKeychainAddGenericPassword.return_value = 0
        core_foundation = mock.Mock()
        password = ctypes.create_string_buffer(b"secret-value")
        missing = (security, core_foundation, -25300, ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p())
        found = (
            security,
            core_foundation,
            0,
            ctypes.c_uint32(len(b"secret-value")),
            ctypes.c_void_p(ctypes.addressof(password)),
            ctypes.c_void_p(1),
        )
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="Darwin"
        ), mock.patch(
            "app.security.credential_store._macos_keychain_api", return_value=(security, core_foundation)
        ), mock.patch(
            "app.security.credential_store._macos_keychain_find", side_effect=[missing, found]
        ):
            self.assertEqual("macos-keychain", credential_store.credential_store_backend())
            credential_store.put_secret(scope="scope", account="api_key", value="secret-value")
            self.assertEqual("secret-value", credential_store.get_secret(scope="scope", account="api_key"))

        self.assertEqual(1, security.SecKeychainAddGenericPassword.call_count)
        add_call = security.SecKeychainAddGenericPassword.call_args.args
        self.assertEqual(b"TradingBot/scope/api_key", add_call[2])
        self.assertEqual(b"trading-bot-service-config", add_call[4])
        self.assertEqual(b"secret-value", add_call[6])
        self.assertEqual(0, security.SecKeychainItemModifyAttributesAndData.call_count)

    def test_macos_keychain_write_updates_existing_item_without_running_a_subprocess(self):
        security = mock.Mock()
        security.SecKeychainFindGenericPassword.return_value = 0
        security.SecKeychainItemModifyAttributesAndData.return_value = 0
        core_foundation = mock.Mock()
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="Darwin"
        ), mock.patch(
            "app.security.credential_store._macos_keychain_api", return_value=(security, core_foundation)
        ), mock.patch("app.security.credential_store.subprocess.run") as run:
            credential_store.put_secret(scope="scope", account="api_key", value="rotated-secret")

        run.assert_not_called()
        self.assertEqual(1, security.SecKeychainItemModifyAttributesAndData.call_count)

    def test_macos_keychain_delete_is_idempotent_and_uses_native_api(self):
        security = mock.Mock()
        security.SecKeychainItemDelete.return_value = 0
        core_foundation = mock.Mock()
        found = (security, core_foundation, 0, ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p(1))
        missing = (security, core_foundation, -25300, ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p())
        with mock.patch("app.security.credential_store.os.name", "posix"), mock.patch(
            "app.security.credential_store.platform.system", return_value="Darwin"
        ), mock.patch(
            "app.security.credential_store._macos_keychain_find", side_effect=[found, missing]
        ), mock.patch("app.security.credential_store.subprocess.run") as run:
            credential_store.delete_secret(scope="scope", account="api_key")
            credential_store.delete_secret(scope="scope", account="api_key")

        run.assert_not_called()
        security.SecKeychainItemDelete.assert_called_once_with(mock.ANY)
        core_foundation.CFRelease.assert_called_once_with(mock.ANY)

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
