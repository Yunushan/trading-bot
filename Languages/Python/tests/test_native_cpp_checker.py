import unittest
from pathlib import Path
from unittest.mock import patch

from tools import check_native_cpp


class NativeCppCheckerTests(unittest.TestCase):
    def test_native_cpp_checker_blocks_stale_python_owned_contracts_before_toolchain(self):
        stale_sync = {
            "ok": False,
            "contract_hash": "stale",
            "issues": ["generated contract is stale"],
        }

        with (
            patch.object(check_native_cpp, "audit_native_source_sync", return_value=stale_sync),
            patch.object(check_native_cpp.shutil, "which", side_effect=AssertionError("toolchain lookup should not run")),
        ):
            report = check_native_cpp.check_native_cpp(
                build_dir=Path("build/native-cpp-test"),
                config="Debug",
                require_webengine=False,
                enable_qt_deploy_script=None,
                smoke_targets_only=True,
                qt_version=None,
                timeout=30,
            )

        self.assertFalse(report["ok"])
        self.assertEqual([], report["steps"])
        self.assertEqual(stale_sync, report["native_source_sync"])
        self.assertIn("generate_native_parity_contracts.py", report["remediation"])

    def test_native_cpp_checker_reports_source_sync_when_cmake_is_missing(self):
        fresh_sync = {
            "ok": True,
            "contract_hash": "fresh",
            "issues": [],
        }

        with (
            patch.object(check_native_cpp, "audit_native_source_sync", return_value=fresh_sync),
            patch.object(check_native_cpp.shutil, "which", return_value=None),
        ):
            report = check_native_cpp.check_native_cpp(
                build_dir=Path("build/native-cpp-test"),
                config="Debug",
                require_webengine=False,
                enable_qt_deploy_script=None,
                smoke_targets_only=True,
                qt_version=None,
                timeout=30,
            )

        self.assertFalse(report["ok"])
        self.assertEqual([], report["steps"])
        self.assertEqual(fresh_sync, report["native_source_sync"])
        self.assertFalse(report["toolchain"]["cmake_found"])
        self.assertFalse(report["toolchain"]["ctest_found"])
        self.assertIn("Install CMake", report["remediation"])


if __name__ == "__main__":
    unittest.main()
