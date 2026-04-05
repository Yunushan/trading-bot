import sys
import tomllib
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import main as legacy_desktop_main  # noqa: E402
from app.entrypoint_contract import (  # noqa: E402
    DESKTOP_ENTRYPOINT_CONTRACT,
    SERVICE_ENTRYPOINT_CONTRACT,
)
from app.service import main as legacy_service_main  # noqa: E402


class EntrypointContractTests(unittest.TestCase):
    def test_pyproject_scripts_target_canonical_package_entrypoints(self):
        data = tomllib.loads((PYTHON_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        self.assertEqual(scripts["trading-bot-desktop"], "app.desktop.product_main:main")
        self.assertEqual(scripts["trading-bot-service"], "app.service.product_main:main")

    def test_desktop_contract_stays_canonical_with_deprecated_workspace_shim(self):
        self.assertEqual(DESKTOP_ENTRYPOINT_CONTRACT.canonical_repo_path, "apps/desktop-pyqt/main.py")
        self.assertEqual(DESKTOP_ENTRYPOINT_CONTRACT.canonical_module, "app.desktop.product_main")
        self.assertEqual(DESKTOP_ENTRYPOINT_CONTRACT.installed_command, "trading-bot-desktop")
        self.assertEqual(DESKTOP_ENTRYPOINT_CONTRACT.compatibility_status, "deprecated")
        self.assertEqual(DESKTOP_ENTRYPOINT_CONTRACT.compatibility_entrypoint, "Languages/Python/main.py")

    def test_service_contract_stays_canonical_with_deprecated_module_shim(self):
        self.assertEqual(SERVICE_ENTRYPOINT_CONTRACT.canonical_repo_path, "apps/service-api/main.py")
        self.assertEqual(SERVICE_ENTRYPOINT_CONTRACT.canonical_module, "app.service.product_main")
        self.assertEqual(SERVICE_ENTRYPOINT_CONTRACT.installed_command, "trading-bot-service")
        self.assertEqual(SERVICE_ENTRYPOINT_CONTRACT.compatibility_status, "deprecated")
        self.assertEqual(SERVICE_ENTRYPOINT_CONTRACT.compatibility_entrypoint, "python -m app.service.main")

    def test_legacy_compatibility_modules_are_marked_deprecated(self):
        self.assertTrue(legacy_desktop_main.IS_DEPRECATED_COMPATIBILITY_ENTRYPOINT)
        self.assertTrue(legacy_service_main.IS_DEPRECATED_COMPATIBILITY_ENTRYPOINT)
        self.assertIn("Deprecated compatibility desktop entrypoint", legacy_desktop_main.COMPATIBILITY_NOTICE)
        self.assertIn("Deprecated compatibility service entrypoint", legacy_service_main.COMPATIBILITY_NOTICE)
