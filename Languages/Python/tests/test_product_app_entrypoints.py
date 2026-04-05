import importlib.util
import sys
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.schemas.runtime import build_runtime_descriptor  # noqa: E402


class ProductAppEntrypointSmokeTests(unittest.TestCase):
    def _load_module(self, relative_path: str, module_name: str):
        path = REPO_ROOT / relative_path
        spec = importlib.util.spec_from_file_location(module_name, path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return path, module

    def test_desktop_product_wrapper_points_at_workspace_launcher(self):
        path, module = self._load_module("apps/desktop-pyqt/main.py", "desktop_product_wrapper")
        self.assertEqual(path, REPO_ROOT / "apps" / "desktop-pyqt" / "main.py")
        self.assertEqual(module.REPO_ROOT, REPO_ROOT)
        self.assertEqual(module.PYTHON_WORKSPACE_DIR, REPO_ROOT / "Languages" / "Python")
        self.assertEqual(module.CANONICAL_PRODUCT_MODULE, "app.desktop.product_main")
        self.assertTrue(callable(module.main))

    def test_service_product_wrapper_points_at_workspace_service(self):
        path, module = self._load_module("apps/service-api/main.py", "service_product_wrapper")
        self.assertEqual(path, REPO_ROOT / "apps" / "service-api" / "main.py")
        self.assertEqual(module.REPO_ROOT, REPO_ROOT)
        self.assertEqual(module.PYTHON_WORKSPACE_DIR, REPO_ROOT / "Languages" / "Python")
        self.assertEqual(module.CANONICAL_PRODUCT_MODULE, "app.service.product_main")
        self.assertTrue(callable(module.main))

    def test_runtime_descriptor_uses_canonical_product_app_paths(self):
        descriptor = build_runtime_descriptor().to_dict()
        self.assertEqual(descriptor["python_entrypoint"], "apps/service-api/main.py")
        self.assertEqual(descriptor["desktop_entrypoint"], "apps/desktop-pyqt/main.py")
        self.assertTrue(
            any(
                "Deprecated compatibility service entrypoint remains available via 'python -m app.service.main'."
                in note
                for note in descriptor["notes"]
            )
        )
        self.assertTrue(
            any(
                "Deprecated compatibility desktop entrypoint remains available via 'Languages/Python/main.py'."
                in note
                for note in descriptor["notes"]
            )
        )
