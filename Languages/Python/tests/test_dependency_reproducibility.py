from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import importlib.util
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
CHECK_SCRIPT = PYTHON_ROOT / "tools" / "check_dependency_metadata.py"
VERIFY_ALL_SCRIPT = REPO_ROOT / "tools" / "verify_all.py"


def _clean_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("COV_CORE_") or key in {"COVERAGE_PROCESS_START", "PYTEST_CURRENT_TEST"}:
            env.pop(key, None)
    return env


class DependencyReproducibilityTests(unittest.TestCase):
    def test_verify_all_includes_ci_python_quality_checks(self):
        spec = importlib.util.spec_from_file_location("verify_all", VERIFY_ALL_SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        check_by_name = {check.name: check for check in module._checks(REPO_ROOT, skip_slow=True)}

        self.assertIn("python lint", check_by_name)
        self.assertIn("python type check", check_by_name)
        self.assertIn("client dependency locks", check_by_name)
        self.assertFalse(check_by_name["client dependency locks"].required)
        self.assertIn("ruff", check_by_name["python lint"].command)
        self.assertIn("mypy", check_by_name["python type check"].command)

    def test_dependency_metadata_check_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK_SCRIPT),
            ],
            cwd=PYTHON_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("requirements.txt -> .[desktop]", result.stdout)
        self.assertIn("requirements.service.txt -> .[service]", result.stdout)
        self.assertIn("dependencies are release-pinned", result.stdout)
        self.assertIn("canonical editable dependency surface", result.stdout)

    def test_repo_declares_local_runtime_tool_versions(self):
        self.assertEqual("3.12", (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip())
        self.assertEqual("24", (REPO_ROOT / ".node-version").read_text(encoding="utf-8").strip())

    def test_runtime_tool_version_checker_reports_expected_shape(self):
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "check_local_tool_versions.py"),
                "--json",
                "--skip-node",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertIn("ok", payload)
        self.assertEqual({"python"}, set(payload["checks"]))
        self.assertEqual("3.12", payload["checks"]["python"]["expected"])

    def test_workspace_cleanup_tool_dry_run_reports_expected_shape(self):
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "clean_workspace_artifacts.py"),
                "--json",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertFalse(payload["applied"])
        self.assertIn("planned_count", payload)
        self.assertIn("planned", payload)
        self.assertIn("removed_count", payload)

    def test_risky_pattern_audit_summary_reports_hotspots_without_full_finding_dump(self):
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "audit_risky_patterns.py"),
                "--json",
                "--summary",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(0, result.returncode, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertIn("finding_count", payload)
        self.assertIn("severity_counts", payload)
        self.assertIn("top_paths", payload)
        self.assertNotIn("findings", payload)

    def test_client_dependency_lock_checker_reports_mobile_lock_gap(self):
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "check_client_dependency_locks.py"),
                "--json",
                "--strict",
            ],
            cwd=REPO_ROOT,
            env=_clean_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        payload = json.loads(result.stdout)
        self.assertIn("clients", payload)
        self.assertIn("errors", payload)
        self.assertTrue(any(item["path"] == "apps/mobile-client" for item in payload["clients"]))
        if not (REPO_ROOT / "apps" / "mobile-client" / "package-lock.json").is_file():
            self.assertNotEqual(0, result.returncode)
            self.assertIn("apps/mobile-client/package-lock.json is missing", payload["errors"])

    def test_client_packages_declare_node_engine_and_package_manager(self):
        for path in (
            REPO_ROOT / "apps" / "web-dashboard" / "package.json",
            REPO_ROOT / "apps" / "mobile-client" / "package.json",
        ):
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("npm@11.6.2", payload["packageManager"])
                self.assertEqual(">=24 <25", payload["engines"]["node"])

        self.assertTrue((REPO_ROOT / "apps" / "web-dashboard" / "package-lock.json").is_file())


if __name__ == "__main__":
    unittest.main()
