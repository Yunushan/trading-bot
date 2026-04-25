import os
import sys
import tempfile
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from app.gui.code import dependency_versions_usage_runtime as dependency_versions_runtime  # noqa: E402

    DEPENDENCY_RUNTIME_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on optional desktop imports
    dependency_versions_runtime = None
    DEPENDENCY_RUNTIME_IMPORT_ERROR = str(exc)


@unittest.skipIf(
    dependency_versions_runtime is None,
    f"Dependency version runtime is unavailable: {DEPENDENCY_RUNTIME_IMPORT_ERROR}",
)
class DependencyVersionRequirementTests(unittest.TestCase):
    def test_local_project_requirements_are_not_dependency_names(self):
        for requirement in (".", ".[desktop]", "./local-package", "../shared-package", "file:../shared-package"):
            with self.subTest(requirement=requirement):
                self.assertIsNone(dependency_versions_runtime._extract_requirement_name(requirement))

    def test_normal_package_requirements_still_extract_names(self):
        cases = {
            "requests==2.33.1": "requests",
            "PyQt6[desktop]==6.11.0": "PyQt6",
            "python-binance>=1.0": "python-binance",
            "package_name @ https://example.invalid/package-name.whl": "package_name",
        }
        for requirement, expected in cases.items():
            with self.subTest(requirement=requirement):
                self.assertEqual(dependency_versions_runtime._extract_requirement_name(requirement), expected)

    def test_local_only_requirements_fall_back_to_default_python_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements_path = Path(temp_dir) / "requirements.txt"
            requirements_path.write_text(".[desktop]\n", encoding="utf-8")

            targets = dependency_versions_runtime._dependency_targets_from_requirements([requirements_path])

        labels = {target["label"] for target in targets}
        self.assertNotIn(".", labels)
        self.assertIn("python-binance", labels)
        self.assertIn("PyQt6", labels)


if __name__ == "__main__":
    unittest.main()
