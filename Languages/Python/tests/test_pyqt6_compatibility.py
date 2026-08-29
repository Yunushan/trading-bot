from __future__ import annotations

import importlib.util
import importlib.metadata as importlib_metadata
import json
import os
import ssl
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
from tools import check_pyqt6_future_release as future_release_checker  # noqa: E402


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
        self.assertIn("PYQT6_PLATFORM: ${{ matrix.os }}", future_workflow)
        self.assertIn(
            "name: PyQt6 ${{ inputs.pyqt_version || '6.12.0' }} compatibility (${{ matrix.os }}, Python ${{ matrix.python-version }})",
            future_workflow,
        )
        self.assertIn("matrix:", future_workflow)
        self.assertIn("ubuntu-24.04", future_workflow)
        self.assertIn("windows-2025", future_workflow)
        self.assertIn("macos-15", future_workflow)
        self.assertIn("python-version:", future_workflow)
        for python_version in ("3.10", "3.11", "3.12", "3.13", "3.14", "3.15"):
            self.assertIn(f'          - "{python_version}"', future_workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", future_workflow)
        self.assertIn("allow-prereleases: true", future_workflow)
        self.assertIn("matrix.os == 'ubuntu-24.04'", future_workflow)
        self.assertIn('cron: "17 6 * * 1"', future_workflow)
        self.assertIn("Check whether the requested PyQt6 release is published", future_workflow)
        self.assertIn("python tools/check_pyqt6_future_release.py", future_workflow)
        self.assertIn('--target "${PYQT6_TARGET}"', future_workflow)
        self.assertIn('--platform "${PYQT6_PLATFORM}"', future_workflow)
        self.assertIn('--github-output "${GITHUB_OUTPUT}"', future_workflow)
        self.assertIn("github.event_name == 'schedule'", future_workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", future_workflow)
        self.assertIn("Fail manual dispatch when the requested family is unavailable", future_workflow)
        self.assertIn('target_series_start="${PYQT6_TARGET%.*}.0"', future_workflow)
        self.assertIn('"PyQt6-WebEngine>=${target_series_start},<6.13.0"', future_workflow)
        self.assertIn('"PyQt6-Qt6>=${target_series_start},<6.13.0"', future_workflow)
        self.assertIn('"PyQt6-WebEngine-Qt6>=${target_series_start},<6.13.0"', future_workflow)
        self.assertNotIn("pip install --pre --only-binary=:all:", future_workflow)
        self.assertIn("--require-exact-pyqt6-version", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke-window", future_workflow)
        self.assertIn("python apps/desktop-pyqt/main.py --smoke-webengine", future_workflow)
        self.assertIn("Build and smoke-test frozen Windows executable", future_workflow)
        self.assertIn("matrix.os == 'windows-2025'", future_workflow)
        self.assertIn("requirements.packaging.txt", future_workflow)
        self.assertIn("build_exe.ps1", future_workflow)
        self.assertIn("-SkipDependencyInstall", future_workflow)
        self.assertIn("Build and smoke-test frozen Unix executable", future_workflow)
        self.assertIn("matrix.os != 'windows-2025'", future_workflow)
        self.assertIn("build_binary.sh", future_workflow)
        self.assertIn("pyqt6-future-wheel-audit:", future_workflow)
        self.assertIn("Audit requested PyQt6 wheel tags for the declared runner", future_workflow)
        self.assertIn('--architecture "${{ matrix.architecture }}"', future_workflow)
        for platform_name, architecture in (
            ("ubuntu-24.04", "x86_64"),
            ("ubuntu-24.04-arm", "aarch64"),
            ("windows-2025", "AMD64"),
            ("windows-11-arm", "ARM64"),
            ("macos-14", "arm64"),
            ("macos-15-intel", "x86_64"),
            ("macos-15", "arm64"),
            ("macos-26", "arm64"),
        ):
            self.assertIn(f"          - platform: {platform_name}", future_workflow)
            self.assertIn(f"            architecture: {architecture}", future_workflow)

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

    def test_package_validation_can_require_exact_base_pyqt6_with_companion_patch_skew(self):
        errors, _package_series, future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.12.0",
                "PyQt6-Qt6": "6.12.1",
                "PyQt6-WebEngine": "6.12.0",
                "PyQt6-WebEngine-Qt6": "6.12.1",
            },
            CONTRACT,
            exact_pyqt6_version="6.12.0",
        )

        self.assertEqual([], errors)
        self.assertTrue(future_target_available)

    def test_package_validation_rejects_exact_base_pyqt6_patch_drift(self):
        errors, _package_series, _future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.12.1",
                "PyQt6-Qt6": "6.12.1",
                "PyQt6-WebEngine": "6.12.0",
                "PyQt6-WebEngine-Qt6": "6.12.1",
            },
            CONTRACT,
            exact_pyqt6_version="6.12.0",
        )

        self.assertTrue(any("requested exact PyQt6 version" in error for error in errors))

    def test_package_validation_rejects_noncanonical_exact_target(self):
        errors, _package_series, _future_target_available = checker._validate_package_versions(
            {
                "PyQt6": "6.12.0",
                "PyQt6-Qt6": "6.12.1",
                "PyQt6-WebEngine": "6.12.0",
                "PyQt6-WebEngine-Qt6": "6.12.1",
            },
            CONTRACT,
            exact_pyqt6_version="6.12",
        )

        self.assertTrue(any("requested exact PyQt6 version is invalid" in error for error in errors))

    def test_runtime_validation_requires_exact_pyqt6_binding_version(self):
        package_versions = {
            "PyQt6": "6.12.0",
            "PyQt6-Qt6": "6.12.1",
            "PyQt6-WebEngine": "6.12.0",
            "PyQt6-WebEngine-Qt6": "6.12.1",
        }

        self.assertEqual(
            [],
            checker._validate_runtime_versions(
                package_versions,
                {"PyQt6": "6.12.0", "Qt6": "6.12.1"},
                exact_pyqt6_version="6.12.0",
            ),
        )
        errors = checker._validate_runtime_versions(
            package_versions,
            {"PyQt6": "6.12.1", "Qt6": "6.12.1"},
            exact_pyqt6_version="6.12.0",
        )
        self.assertTrue(any("requested exact PyQt6 runtime version" in error for error in errors))

    def test_future_release_checker_filters_wheels_by_platform_and_artifact_type(self):
        ubuntu_markers = future_release_checker.PLATFORM_WHEEL_MARKERS["ubuntu-24.04"]

        self.assertTrue(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0-cp314-abi3-manylinux_2_39_x86_64.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
            )
        )
        self.assertTrue(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0-cp314-abi3-linux_x86_64.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
            )
        )
        self.assertFalse(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0-cp314-abi3-musllinux_1_2_x86_64.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
            )
        )
        self.assertFalse(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0.tar.gz", "packagetype": "sdist"}],
                ubuntu_markers,
            )
        )
        self.assertFalse(
            future_release_checker.has_installable_wheel(
                [
                    {
                        "filename": "PyQt6-6.12.0-cp314-abi3-manylinux_2_39_x86_64.whl",
                        "packagetype": "bdist_wheel",
                        "yanked": True,
                    }
                ],
                ubuntu_markers,
            )
        )

    def test_future_release_checker_rejects_incompatible_architecture_and_python_tags(self):
        ubuntu_markers = future_release_checker.PLATFORM_WHEEL_MARKERS["ubuntu-24.04"]
        x64 = ("x86_64", "amd64", "universal2")

        self.assertFalse(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0-cp314-abi3-manylinux_2_39_aarch64.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
                x64,
                (3, 14),
            )
        )
        self.assertFalse(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-6.12.0-cp312-cp312-manylinux_2_39_x86_64.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
                x64,
                (3, 14),
            )
        )
        self.assertTrue(
            future_release_checker.has_installable_wheel(
                [{"filename": "PyQt6-Qt6-6.12.0-py3-none-any.whl", "packagetype": "bdist_wheel"}],
                ubuntu_markers,
                x64,
                (3, 14),
            )
        )

    def test_future_release_checker_matches_declared_arm_and_macos_intel_targets(self):
        cases = (
            (
                "ubuntu-24.04-arm",
                "aarch64",
                "PyQt6-6.12.0-cp310-abi3-manylinux_2_39_aarch64.whl",
            ),
            (
                "windows-11-arm",
                "arm64",
                "PyQt6-6.12.0-cp310-abi3-win_arm64.whl",
            ),
            (
                "macos-15-intel",
                "x86_64",
                "PyQt6-6.12.0-cp310-abi3-macosx_10_14_x86_64.whl",
            ),
            (
                "macos-15",
                "arm64",
                "PyQt6-6.12.0-cp310-abi3-macosx_11_0_arm64.whl",
            ),
        )
        for platform_name, machine, filename in cases:
            with self.subTest(platform=platform_name):
                with mock.patch.object(future_release_checker.platform, "machine", return_value=machine):
                    architectures = future_release_checker.runner_wheel_architectures(platform_name)
                self.assertTrue(
                    future_release_checker.has_installable_wheel(
                        [{"filename": filename, "packagetype": "bdist_wheel"}],
                        future_release_checker.PLATFORM_WHEEL_MARKERS[platform_name],
                        architectures,
                        (3, 14),
                    )
                )

    def test_future_release_checker_keeps_every_declared_runner_label_architecture_bound(self):
        expected = {
            "ubuntu-24.04": ("x86_64", ("x86_64", "amd64")),
            "ubuntu-24.04-arm": ("aarch64", ("arm64", "aarch64")),
            "windows-2025": ("AMD64", ("x86_64", "amd64")),
            "windows-11-arm": ("ARM64", ("arm64", "aarch64")),
            "macos-14": ("arm64", ("arm64", "aarch64", "universal2")),
            "macos-15-intel": ("x86_64", ("x86_64", "amd64", "universal2")),
            "macos-15": ("arm64", ("arm64", "aarch64", "universal2")),
            "macos-26": ("arm64", ("arm64", "aarch64", "universal2")),
        }

        self.assertEqual(set(expected), set(future_release_checker.PLATFORM_WHEEL_MARKERS))
        self.assertEqual(set(expected), set(future_release_checker.PLATFORM_MACHINE_FAMILIES))
        for platform_name, (machine, architectures) in expected.items():
            with self.subTest(platform=platform_name):
                self.assertEqual(
                    architectures,
                    future_release_checker.runner_wheel_architectures(platform_name, machine),
                )

    def test_future_release_checker_rejects_runner_label_architecture_mismatch(self):
        with mock.patch.object(future_release_checker.platform, "machine", return_value="x86_64"):
            with self.assertRaisesRegex(ValueError, "ubuntu-24.04-arm.*expected arm64"):
                future_release_checker.runner_wheel_architectures("ubuntu-24.04-arm")
        self.assertEqual(
            ("arm64", "aarch64", "universal2"),
            future_release_checker.runner_wheel_architectures("macos-15", "arm64"),
        )

    def test_future_release_checker_requires_a_complete_family_for_the_runner(self):
        wheel = {
            "filename": "PyQt6-6.12.0-cp314-abi3-manylinux_2_39_x86_64.whl",
            "packagetype": "bdist_wheel",
        }
        payloads = {
            package_name: {"releases": {"6.12.0": [wheel]}}
            for package_name in future_release_checker.PYQT6_PACKAGE_NAMES
        }

        status, target_series = future_release_checker.check_family(
            "6.12.0",
            "ubuntu-24.04",
            metadata_loader=lambda package_name: payloads[package_name],
        )

        self.assertEqual((6, 12), target_series)
        self.assertTrue(all(status.values()))
        payloads["PyQt6-WebEngine-Qt6"] = {"releases": {"6.12.0": []}}
        status, _target_series = future_release_checker.check_family(
            "6.12.0",
            "ubuntu-24.04",
            metadata_loader=lambda package_name: payloads[package_name],
        )
        self.assertFalse(status["PyQt6-WebEngine-Qt6"])

    def test_future_release_checker_keeps_https_certificate_verification_enabled(self):
        context = future_release_checker._pypi_ssl_context()

        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)

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
