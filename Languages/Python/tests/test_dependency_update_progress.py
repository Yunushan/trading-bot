import os
import sys
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
    from app.gui.code.code_language_catalog import PYTHON_CODE_LANGUAGE_KEY  # noqa: E402

    DEPENDENCY_UPDATE_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on optional desktop imports
    dependency_versions_runtime = None
    dependency_versions_ui = None
    PYTHON_CODE_LANGUAGE_KEY = ""
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


if __name__ == "__main__":
    unittest.main()
