from __future__ import annotations

import importlib.util
import importlib.metadata as importlib_metadata
import json
import os
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found]


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_pyqt6_compatibility as checker  # noqa: E402


CONTRACT = {
    "minimum_version": "6.11.0",
    "maximum_version_exclusive": "6.13.0",
    "future_target_version": "6.12.0",
}


class PyQt6CompatibilityTests(unittest.TestCase):
    def test_pyproject_declares_the_future_612_contract_for_both_desktop_surfaces(self):
        pyproject = tomllib.loads(
            (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        )
        contract = pyproject["tool"]["trading-bot"]["pyqt6"]
        expected = {
            "minimum_version": "6.11.0",
            "maximum_version_exclusive": "6.13.0",
            "future_target_version": "6.12.0",
        }
        self.assertEqual(expected, contract)
        for group_name in ("desktop", "windows-arm64"):
            self.assertEqual(
                [
                    "PyQt6>=6.11.0,<6.13.0",
                    "PyQt6-Qt6>=6.11.0,<6.13.0",
                    "PyQt6-WebEngine>=6.11.0,<6.13.0",
                    "PyQt6-WebEngine-Qt6>=6.11.0,<6.13.0",
                ],
                pyproject["project"]["optional-dependencies"][group_name][:4],
            )

    def test_ci_contains_the_runtime_gate_and_future_workflow_targets_612(self):
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        future_workflow = (
            REPO_ROOT / ".github" / "workflows" / "pyqt6-future-compatibility.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("python tools/check_pyqt6_compatibility.py --json", ci)
        self.assertIn('default: "6.12.0"', future_workflow)
        self.assertIn('description: "Exact stable PyQt6 release to validate"', future_workflow)
        self.assertIn("PYQT6_TARGET: ${{ inputs.pyqt_version || '6.12.0' }}", future_workflow)
        self.assertIn("name: PyQt6 ${{ inputs.pyqt_version || '6.12.0' }} compatibility", future_workflow)
        self.assertIn("matrix:", future_workflow)
        self.assertIn("ubuntu-24.04", future_workflow)
        self.assertIn("windows-2025", future_workflow)
        self.assertIn("macos-15", future_workflow)
        self.assertIn("matrix.os == 'ubuntu-24.04'", future_workflow)
        self.assertIn('cron: "17 6 * * 1"', future_workflow)
        self.assertIn("Check whether the requested PyQt6 release is published", future_workflow)
        self.assertIn('"PyQt6-Qt6"', future_workflow)
        self.assertIn('"PyQt6-WebEngine"', future_workflow)
        self.assertIn('"PyQt6-WebEngine-Qt6"', future_workflow)
        self.assertIn("github.event_name == 'schedule'", future_workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", future_workflow)
        self.assertIn("Fail manual dispatch when the requested family is unavailable", future_workflow)
        self.assertIn('"PyQt6-WebEngine>=${PYQT6_TARGET},<6.13.0"', future_workflow)
        self.assertIn('"PyQt6-Qt6>=${PYQT6_TARGET},<6.13.0"', future_workflow)
        self.assertIn('"PyQt6-WebEngine-Qt6>=${PYQT6_TARGET},<6.13.0"', future_workflow)
        self.assertIn("--require-version", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke-window", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke-webengine", future_workflow)

        release_smoke_job = ci.split("  python-315-release-smoke:", 1)[1].split(
            "  web-dashboard-quality:", 1
        )[0]
        self.assertIn("Install Linux Qt runtime dependencies for Python 3.15 release smoke", release_smoke_job)
        self.assertIn("libegl1", release_smoke_job)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke-webengine", release_smoke_job)

    def test_release_version_parser_accepts_release_and_prerelease_suffixes(self):
        self.assertEqual((6, 12, 0), checker.parse_release_version("6.12.0"))
        self.assertEqual((6, 12, 0), checker.parse_release_version("6.12.0rc1"))
        self.assertEqual((6, 12, 0), checker.parse_release_version("6.12"))
        self.assertIsNone(checker.parse_release_version("6"))
        self.assertIsNone(checker.parse_release_version("not-a-version"))

    def test_package_validation_accepts_patch_skew_within_one_release_series(self):
        errors, package_series, future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.11.0",
                "PyQt6-Qt6": "6.11.2",
                "PyQt6-WebEngine": "6.11.1",
                "PyQt6-WebEngine-Qt6": "6.11.1",
            },
            CONTRACT,
        )

        self.assertEqual([], errors)
        self.assertEqual(
            {
                "PyQt6": (6, 11),
                "PyQt6-Qt6": (6, 11),
                "PyQt6-WebEngine": (6, 11),
                "PyQt6-WebEngine-Qt6": (6, 11),
            },
            package_series,
        )
        self.assertFalse(future_target_available)

    def test_package_validation_rejects_mixed_release_series(self):
        errors, _package_series, _future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.12.0",
                "PyQt6-Qt6": "6.11.2",
                "PyQt6-WebEngine": "6.12.0",
                "PyQt6-WebEngine-Qt6": "6.12.0",
            },
            CONTRACT,
        )

        self.assertTrue(any("share one major.minor series" in error for error in errors))

    def test_package_validation_can_require_the_future_release_series(self):
        errors, _package_series, future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.12.0",
                "PyQt6-Qt6": "6.12.1",
                "PyQt6-WebEngine": "6.12.0",
                "PyQt6-WebEngine-Qt6": "6.12.0",
            },
            CONTRACT,
            required_version="6.12.0",
        )

        self.assertEqual([], errors)
        self.assertTrue(future_target_available)

    def test_package_validation_rejects_versions_above_reviewed_upper_bound(self):
        errors, _package_series, _future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.13.0",
                "PyQt6-Qt6": "6.13.0",
                "PyQt6-WebEngine": "6.13.0",
                "PyQt6-WebEngine-Qt6": "6.13.0",
            },
            CONTRACT,
        )

        self.assertEqual(4, sum("outside the reviewed PyQt6 range" in error for error in errors))

    def test_package_validation_rejects_an_incomplete_webengine_family(self):
        errors, _package_series, _future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.11.0",
                "PyQt6-Qt6": "6.11.0",
                "PyQt6-WebEngine": "6.11.0",
            },
            CONTRACT,
        )

        self.assertTrue(any("PyQt6-WebEngine-Qt6 is not installed" in error for error in errors))

    def test_chart_webengine_guard_accepts_patch_skew_within_one_release_series(self):
        from app.gui.chart import chart_embed_state_runtime

        self.assertEqual("6.11", chart_embed_state_runtime._version_series_text("6.11.0"))
        self.assertEqual("6.11", chart_embed_state_runtime._version_series_text("6.11.2+local"))
        self.assertNotEqual(
            chart_embed_state_runtime._version_series_text("6.11.0"),
            chart_embed_state_runtime._version_series_text("6.12.0"),
        )

    def test_chart_webengine_guard_rejects_mixed_webengine_runtime_series(self):
        from app.gui.chart import chart_embed_state_runtime

        versions = {
            "PyQt6": "6.12.0",
            "PyQt6-Qt6": "6.12.1",
            "PyQt6-WebEngine": "6.12.0",
            "PyQt6-WebEngine-Qt6": "6.11.2",
        }

        def resolve_version(*names):
            return versions.get(names[0])

        with (
            mock.patch.object(chart_embed_state_runtime.sys, "platform", "win32"),
            mock.patch.object(
                chart_embed_state_runtime,
                "_resolve_dist_version",
                side_effect=resolve_version,
            ),
        ):
            healthy, reason = chart_embed_state_runtime._tradingview_embed_health()

        self.assertFalse(healthy)
        self.assertIn("PyQt6-WebEngine-Qt6", reason)

    def test_current_environment_passes_runtime_probe_when_desktop_dependencies_exist(self):
        if importlib.util.find_spec("PyQt6") is None:
            self.skipTest("PyQt6 is not installed in this environment")
        for package_name in checker.PYQT6_PACKAGE_NAMES:
            try:
                importlib_metadata.version(package_name)
            except importlib_metadata.PackageNotFoundError:
                self.skipTest(f"{package_name} is not installed in this environment")

        environment = os.environ.copy()
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "check_pyqt6_compatibility.py"), "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
            check=False,
        )
        report = json.loads(result.stdout)

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertTrue(report["ok"], report)
        self.assertTrue(all(report["api_checks"].values()))
        self.assertIn("PyQt6", report["runtime_versions"])


if __name__ == "__main__":
    unittest.main()
