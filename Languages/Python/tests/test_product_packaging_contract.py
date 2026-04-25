import unittest
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class ProductPackagingContractTests(unittest.TestCase):
    def test_windows_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("apps\\\\desktop-pyqt\\\\main.py", script)
        self.assertIn('"--paths", $repoRoot', script)
        self.assertIn('"--paths", $pythonRoot', script)
        self.assertIn('$env:BOT_DISABLE_PYTHONW_RELAUNCH = "1"', script)
        self.assertIn('$env:BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH = "1"', script)
        self.assertIn("PyInstaller failed with exit code", script)

    def test_unix_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_binary.sh").read_text(encoding="utf-8")
        self.assertIn('DESKTOP_ENTRY_SCRIPT="${REPO_ROOT}/apps/desktop-pyqt/main.py"', script)
        self.assertIn('--paths "${REPO_ROOT}"', script)
        self.assertIn('--paths "${PYTHON_ROOT}"', script)
        self.assertIn(
            'BOT_DISABLE_PYTHONW_RELAUNCH=1 BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH=1 "${PYTHON_BIN}" "${pyinstaller_args[@]}"',
            script,
        )

    def test_docker_backend_uses_canonical_service_wrapper_and_dashboard_assets(self):
        dockerfile = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY apps/service-api /app/apps/service-api", dockerfile)
        self.assertIn("COPY apps/web-dashboard /app/apps/web-dashboard", dockerfile)
        self.assertIn('CMD ["python", "apps/service-api/main.py"', dockerfile)

    def test_ci_smoke_uses_canonical_service_wrapper(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python apps/service-api/main.py --healthcheck", workflow)
        self.assertIn("apps/desktop-pyqt/main.py", workflow)
        self.assertIn("apps/service-api/main.py", workflow)

    def test_python_package_metadata_includes_public_trading_core_surface(self):
        pyproject = (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('include = ["app*", "trading_core*"]', pyproject)
        self.assertIn('trading_core = ["py.typed"]', pyproject)

    def test_release_dependency_constraints_avoid_ci_known_conflicts(self):
        pyproject = tomllib.loads(
            (REPO_ROOT / "Languages" / "Python" / "pyproject.toml").read_text(encoding="utf-8")
        )
        optional_dependencies = pyproject["project"]["optional-dependencies"]

        desktop_dependencies = optional_dependencies["desktop"]
        self.assertIn(
            "numba==0.65.0; platform_system != 'Darwin' or platform_machine != 'x86_64'",
            desktop_dependencies,
        )
        self.assertIn(
            "llvmlite==0.47.0; platform_system != 'Darwin' or platform_machine != 'x86_64'",
            desktop_dependencies,
        )

        windows_arm64_dependencies = optional_dependencies["windows-arm64"]
        self.assertNotIn("aiohttp==0.13.1", windows_arm64_dependencies)
        self.assertIn("aiohttp>=3.9,<4", windows_arm64_dependencies)

    def test_windows_release_workflow_uses_arm64_pure_python_aiohttp_fallbacks(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release-windows.yml").read_text(encoding="utf-8")
        self.assertIn("AIOHTTP_NO_EXTENSIONS", workflow)
        self.assertIn("MULTIDICT_NO_EXTENSIONS", workflow)
        self.assertIn("YARL_NO_EXTENSIONS", workflow)
        self.assertIn("FROZENLIST_NO_EXTENSIONS", workflow)
        self.assertIn("PROPCACHE_NO_EXTENSIONS", workflow)
