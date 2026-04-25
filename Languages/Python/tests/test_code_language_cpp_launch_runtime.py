import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.gui.code import code_language_cpp_bundle_packaged_runtime, code_language_launch  # noqa: E402


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


class CodeLanguageCppLaunchRuntimeTests(unittest.TestCase):
    def test_debug_qt_runtime_bundle_is_not_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe_path = Path(tmp) / "build" / "binance_cpp" / "Debug" / "Trading-Bot-C++.exe"
            _touch(exe_path)
            for dll_name in ("Qt6Cored.dll", "Qt6Guid.dll", "Qt6Widgetsd.dll", "Qt6Networkd.dll"):
                _touch(exe_path.parent / dll_name)
            _touch(exe_path.parent / "platforms" / "qwindowsd.dll")

            with (
                mock.patch.object(code_language_launch.sys, "platform", "win32"),
                mock.patch.object(code_language_cpp_bundle_packaged_runtime.sys, "platform", "win32"),
            ):
                self.assertFalse(code_language_launch.cpp_runtime_bundle_missing(exe_path))
                self.assertFalse(code_language_cpp_bundle_packaged_runtime.cpp_runtime_bundle_missing(exe_path))

    def test_debug_qt_runtime_bundle_requires_debug_platform_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe_path = Path(tmp) / "build" / "binance_cpp" / "Debug" / "Trading-Bot-C++.exe"
            _touch(exe_path)
            for dll_name in ("Qt6Cored.dll", "Qt6Guid.dll", "Qt6Widgetsd.dll", "Qt6Networkd.dll"):
                _touch(exe_path.parent / dll_name)

            with mock.patch.object(code_language_launch.sys, "platform", "win32"):
                self.assertTrue(code_language_launch.cpp_runtime_bundle_missing(exe_path))

    def test_debug_build_deploy_uses_debug_windeployqt_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe_path = Path(tmp) / "build" / "binance_cpp" / "Debug" / "Trading-Bot-C++.exe"
            windeployqt_path = Path(tmp) / "Qt" / "bin" / "windeployqt.exe"
            _touch(exe_path)
            _touch(windeployqt_path)
            commands = []

            def fake_run(command, *, cwd=None, env=None):
                commands.append(list(command))
                return True, "deployed"

            with (
                mock.patch.object(code_language_launch.sys, "platform", "win32"),
                mock.patch.object(code_language_launch, "find_windeployqt_for_cpp", return_value=windeployqt_path),
                mock.patch.object(code_language_launch, "run_command_capture_hidden", side_effect=fake_run),
            ):
                ok, output = code_language_launch.deploy_cpp_runtime_bundle(exe_path, force=True)

            self.assertTrue(ok)
            self.assertEqual(output, "deployed")
            self.assertTrue(commands)
            self.assertIn("--debug", commands[0])


if __name__ == "__main__":
    unittest.main()
