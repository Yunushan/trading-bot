from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "tools" / "write_release_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("write_release_manifest", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_contains_digest_and_source_revision(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "trading-bot.zip"
            artifact.write_bytes(b"release-bytes")
            manifest = module.build_manifest(REPO_ROOT, [artifact])

        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual("trading-bot.zip", manifest["artifacts"][0]["name"])
        self.assertEqual(64, len(manifest["artifacts"][0]["sha256"]))
        self.assertTrue(manifest["source_revision"])

    def test_verify_manifest_detects_artifact_tampering(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            release_dir = Path(tmp)
            artifact = release_dir / "trading-bot.zip"
            artifact.write_bytes(b"release-bytes")
            manifest_path = release_dir / "release-manifest.json"
            manifest_path.write_text(
                json.dumps(module.build_manifest(REPO_ROOT, [artifact])), encoding="utf-8"
            )

            module.verify_manifest(manifest_path, root=REPO_ROOT)
            artifact.write_bytes(b"modified-release-bytes")

            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                module.verify_manifest(manifest_path, root=REPO_ROOT)
