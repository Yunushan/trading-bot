import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from app.gui.code import dependency_versions_runtime, dependency_versions_ui  # noqa: E402
    from app.gui.code.code_language_catalog import (  # noqa: E402
        PYTHON_CODE_LANGUAGE_KEY,
        RUST_CODE_LANGUAGE_KEY,
    )

    DEPENDENCY_UPDATE_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on optional desktop imports
    dependency_versions_runtime = None
    dependency_versions_ui = None
    PYTHON_CODE_LANGUAGE_KEY = ""
    RUST_CODE_LANGUAGE_KEY = ""
    DEPENDENCY_UPDATE_IMPORT_ERROR = str(exc)


class _FakeWindow:
    def __init__(self):
        self.config = {"code_language": PYTHON_CODE_LANGUAGE_KEY}
        self._dep_version_targets = []
        self.commands: list[list[str]] = []
        self.timeouts: list[float | None] = []

    def _run_command_capture_hidden(self, command, *, cwd=None, env=None, timeout=None):
        self.commands.append(list(command))
        self.timeouts.append(timeout)
        package_name = command[-1]
        if package_name == "broken-package":
            return False, "ERROR: could not install broken-package"
        return True, f"Successfully installed {package_name}"


@unittest.skipIf(
    dependency_versions_ui is None,
    f"Dependency update runtime is unavailable: {DEPENDENCY_UPDATE_IMPORT_ERROR}",
)
class DependencyUpdateProgressTests(unittest.TestCase):
    def test_dependency_ui_exception_logger_uses_window_log(self):
        class _Window:
            def __init__(self):
                self.messages: list[str] = []

            def log(self, message):
                self.messages.append(str(message))

        window = _Window()
        dependency_versions_ui._record_dependency_ui_exception(window, "unit_context", RuntimeError("line one\nline two"))

        self.assertEqual(1, len(window.messages))
        self.assertIn("unit_context", window.messages[0])
        self.assertIn("RuntimeError", window.messages[0])
        self.assertIn("line one line two", window.messages[0])

    def test_dependency_ui_exception_logger_falls_back_to_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"TEMP": tmp}):
                dependency_versions_ui._record_dependency_ui_exception(None, "fallback_context", RuntimeError("fallback failed"))

            log_path = Path(tmp) / "trading_bot_dependency_ui.log"
            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn("fallback_context", contents)
            self.assertIn("fallback failed", contents)

    def test_python_install_output_includes_progress_callback_failure(self):
        def broken_callback(_line):
            raise RuntimeError("callback failed")

        ok, output = dependency_versions_ui._run_python_package_install(
            [sys.executable, "-c", "print('hello from installer')"],
            cwd=PYTHON_ROOT,
            timeout=15.0,
            on_output=broken_callback,
        )

        self.assertTrue(ok)
        self.assertIn("hello from installer", output)
        self.assertIn("Progress callback failed: RuntimeError: callback failed", output)

    def test_progress_text_includes_percentage_and_totals(self):
        headline, detail, percent = dependency_versions_ui._format_dependency_progress_text(
            {
                "phase": "Installing",
                "current": "numpy",
                "total": 4,
                "completed": 2,
                "installed": 1,
                "failed": 1,
            }
        )

        self.assertEqual(percent, 50)
        self.assertEqual(headline, "2/4 complete (50%)")
        self.assertIn("1 installed, 1 failed", detail)
        self.assertIn("Installing: numpy", detail)

    def test_windows_access_denied_install_hint_explains_locked_packages(self):
        with mock.patch.object(dependency_versions_ui.sys, "platform", "win32"):
            hint = dependency_versions_ui._windows_access_denied_install_hint(
                "pandas",
                "ERROR: Could not install packages due to an OSError: [WinError 5] Access is denied",
            )

        self.assertIn("Windows denied access", hint)
        self.assertIn("pandas", hint)

    def test_python_update_prefers_active_interpreter(self):
        command = dependency_versions_ui._resolve_python_command_prefix(_FakeWindow())

        self.assertIsNotNone(command)
        self.assertEqual(Path(command[0]).resolve(), Path(sys.executable).resolve())

    def test_python_updates_emit_package_progress_and_report_partial_failures(self):
        window = _FakeWindow()
        progress_events = []
        targets = [
            {"label": "ok-package", "package": "ok-package", "_latest_version": "1.2.3", "_installed_version": "1.0.0"},
            {
                "label": "broken-package",
                "package": "broken-package",
                "_latest_version": "9.9.9",
                "_installed_version": "1.0.0",
            },
        ]

        def fake_install(command, *, cwd, timeout, on_output=None):
            window.commands.append(list(command))
            window.timeouts.append(timeout)
            if callable(on_output):
                on_output(f"Collecting {command[-1]}")
            package_name = str(command[-1]).split("==", 1)[0]
            if package_name == "broken-package":
                return False, "ERROR: could not install broken-package"
            return True, f"Successfully installed {command[-1]}"

        def fake_installed_version(target):
            if target["package"] == "broken-package":
                return "1.0.0"
            return target.get("_latest_version")

        with (
            mock.patch.object(dependency_versions_ui, "_resolve_python_command_prefix", return_value=["python"]),
            mock.patch.object(
                dependency_versions_ui,
                "_emit_dependency_update_progress",
                side_effect=lambda _window, progress: progress_events.append(dict(progress)),
            ),
            mock.patch.object(
                dependency_versions_ui,
                "_run_python_package_install",
                side_effect=fake_install,
            ),
            mock.patch.object(
                dependency_versions_runtime,
                "_installed_version_for_dependency_target",
                side_effect=fake_installed_version,
            ),
        ):
            result = dependency_versions_ui._run_dependency_update_worker(
                window,
                targets=targets,
                selected_only=True,
            )

        self.assertFalse(result["ok"])
        self.assertIn("1 failed", result["message"])
        self.assertEqual([command[-1] for command in window.commands], ["ok-package==1.2.3", "broken-package==9.9.9"])
        self.assertTrue(all("--no-input" in command for command in window.commands))
        self.assertTrue(all(timeout is not None and timeout > 0 for timeout in window.timeouts))
        self.assertEqual(progress_events[-1]["state"], "finished")
        self.assertEqual(progress_events[-1]["installed"], 1)
        self.assertEqual(progress_events[-1]["failed"], 1)
        self.assertTrue(any(event.get("state") == "running" and event.get("current") == "ok-package" for event in progress_events))
        self.assertTrue(any(event.get("state") == "failed" and event.get("current") == "broken-package" for event in progress_events))

    def test_python_update_blocks_loaded_windows_binary_package_before_pip(self):
        window = _FakeWindow()
        progress_events = []
        targets = [
            {
                "label": "pandas",
                "package": "pandas",
                "_latest_version": "3.0.3",
                "_installed_version": "3.0.2",
            },
        ]

        with (
            mock.patch.object(dependency_versions_ui.sys, "platform", "win32"),
            mock.patch.dict(dependency_versions_ui.sys.modules, {"pandas": mock.Mock()}),
            mock.patch.object(dependency_versions_ui, "_resolve_python_command_prefix", return_value=["python"]),
            mock.patch.object(
                dependency_versions_ui,
                "_emit_dependency_update_progress",
                side_effect=lambda _window, progress: progress_events.append(dict(progress)),
            ),
            mock.patch.object(dependency_versions_ui, "_run_python_package_install") as install,
        ):
            result = dependency_versions_ui._run_dependency_update_worker(
                window,
                targets=targets,
                selected_only=True,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["title"], "Python dependency update needs restart")
        self.assertIn("Restart required: pandas", result["message"])
        self.assertIn("pandas is already loaded by the running app", result["message"])
        install.assert_not_called()
        self.assertTrue(any(event.get("state") == "blocked" and event.get("current") == "pandas" for event in progress_events))
        self.assertEqual(progress_events[-1]["state"], "finished")
        self.assertEqual(progress_events[-1]["failed"], 0)
        self.assertEqual(progress_events[-1]["restart_required"], 1)

    def test_rust_update_installs_toolchain_when_rustup_is_missing(self):
        window = _FakeWindow()
        window.config = {"code_language": RUST_CODE_LANGUAGE_KEY}
        progress_events = []
        targets = [
            {"label": "rustc", "custom": "rust_rustc"},
            {"label": "cargo", "custom": "rust_cargo"},
        ]

        with (
            mock.patch.object(dependency_versions_runtime, "_rust_tool_path", return_value=None),
            mock.patch.object(dependency_versions_runtime, "_rust_toolchain_env", return_value={}),
            mock.patch.object(
                dependency_versions_runtime,
                "_install_rust_toolchain",
                return_value=(True, "Rust installed"),
            ),
            mock.patch.object(dependency_versions_runtime, "_reset_rust_dependency_caches"),
            mock.patch.object(
                dependency_versions_ui,
                "_emit_dependency_update_progress",
                side_effect=lambda _window, progress: progress_events.append(dict(progress)),
            ),
        ):
            result = dependency_versions_ui._run_dependency_update_worker(
                window,
                targets=targets,
                selected_only=True,
            )

        self.assertTrue(result["ok"])
        self.assertIn("Rust toolchain installed.", result["message"])
        self.assertEqual(window.commands, [])
        self.assertTrue(any(event.get("phase") == "Installing" for event in progress_events))
        self.assertEqual(progress_events[-1]["state"], "finished")
        self.assertEqual(progress_events[-1]["installed"], 1)
        self.assertEqual(progress_events[-1]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
