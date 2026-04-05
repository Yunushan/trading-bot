import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


class ProductPackagingContractTests(unittest.TestCase):
    def test_windows_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("apps\\\\desktop-pyqt\\\\main.py", script)
        self.assertIn('"--paths", $repoRoot', script)
        self.assertIn('"--paths", $pythonRoot', script)

    def test_unix_build_script_targets_canonical_desktop_wrapper(self):
        script = (REPO_ROOT / "Languages" / "Python" / "tools" / "build_binary.sh").read_text(encoding="utf-8")
        self.assertIn('DESKTOP_ENTRY_SCRIPT="${REPO_ROOT}/apps/desktop-pyqt/main.py"', script)
        self.assertIn('--paths "${REPO_ROOT}"', script)
        self.assertIn('--paths "${PYTHON_ROOT}"', script)

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
