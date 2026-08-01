from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_release_version.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_release_version", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_metadata(root: Path, version: str) -> None:
    paths = (
        "Languages/Python/pyproject.toml",
        "experiments/rust-shells/Cargo.toml",
        "experiments/rust-shells/crates/core/Cargo.toml",
        "experiments/rust-shells/crates/contracts/Cargo.toml",
        "experiments/rust-shells/apps/tauri-desktop/Cargo.toml",
    )
    for relative_path in paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        section = "project" if relative_path.endswith("pyproject.toml") else "package"
        path.write_text(f"[{section}]\nversion = \"{version}\"\n", encoding="utf-8")
    config_path = root / "experiments/rust-shells/apps/tauri-desktop/tauri.conf.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"version": version}), encoding="utf-8")


class ReleaseVersionTests(unittest.TestCase):
    def test_accepts_matching_metadata_versions(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_metadata(root, "1.2.3")
            expected, versions, issues = checker.validate_release_version("v1.2.3", root)
        self.assertEqual("1.2.3", expected)
        self.assertEqual([], issues)
        self.assertTrue(versions)

    def test_reports_each_mismatched_metadata_file(self):
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_metadata(root, "1.2.3")
            (root / "experiments/rust-shells/apps/tauri-desktop/tauri.conf.json").write_text(
                json.dumps({"version": "0.1.0"}), encoding="utf-8"
            )
            _, _, issues = checker.validate_release_version("v1.2.3", root)
        self.assertEqual(
            [
                "experiments/rust-shells/apps/tauri-desktop/tauri.conf.json version '0.1.0' "
                "does not match release version '1.2.3'"
            ],
            issues,
        )

    def test_rejects_non_semantic_release_tag(self):
        checker = _load_checker()
        expected, versions, issues = checker.validate_release_version("release-1.2.3")
        self.assertEqual("", expected)
        self.assertEqual({}, versions)
        self.assertEqual(["release tag must use vMAJOR.MINOR.PATCH form: release-1.2.3"], issues)


if __name__ == "__main__":
    unittest.main()
