from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

CHECKER_PATH = TOOLS_DIR / "check_release_candidate_manifests.py"
TAG = "v1.0.41"
REVISION = "a" * 40
ARTIFACT_DIGEST = "b" * 64


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_candidate_manifests", CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(checker):
    _, expected_assets = checker.check_release_assets._build_expected_assets(TAG)
    required_names = {asset.name for asset in expected_assets if asset.required}
    manifest_names = sorted(
        name for name in required_names if name.startswith("release-manifest-")
    )
    covered_names = sorted(
        name
        for name in required_names
        if not name.startswith("release-manifest-")
        and not name.startswith("release-sbom-")
    )
    buckets = {name: [] for name in manifest_names}
    for index, name in enumerate(covered_names):
        buckets[manifest_names[index % len(manifest_names)]].append(
            {"name": name, "sha256": ARTIFACT_DIGEST, "size_bytes": 10}
        )

    manifests = {}
    release_rows = [
        {
            "name": name,
            "state": "uploaded",
            "size": 10,
            "digest": f"sha256:{ARTIFACT_DIGEST}",
        }
        for name in required_names
        if name not in manifest_names
    ]
    for name in manifest_names:
        payload = {
            "schema_version": 1,
            "source_revision": REVISION,
            "artifacts": buckets[name],
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        manifests[name] = checker.LoadedManifest(
            name=name,
            payload=payload,
            size_bytes=len(raw),
            sha256=digest,
        )
        release_rows.append(
            {
                "name": name,
                "state": "uploaded",
                "size": len(raw),
                "digest": f"sha256:{digest}",
            }
        )
    return {"assets": release_rows}, manifests


class ReleaseCandidateManifestTests(unittest.TestCase):
    def test_accepts_source_and_api_digest_bound_manifests(self):
        checker = _load_checker()
        release_payload, manifests = _candidate(checker)
        self.assertEqual(
            [],
            checker.validate_candidate_manifests(
                release_payload,
                manifests,
                tag=TAG,
                expected_source_revision=REVISION,
            ),
        )

    def test_rejects_wrong_manifest_source_revision(self):
        checker = _load_checker()
        release_payload, manifests = _candidate(checker)
        first = manifests[sorted(manifests)[0]]
        first.payload["source_revision"] = "c" * 40
        issues = checker.validate_candidate_manifests(
            release_payload,
            manifests,
            tag=TAG,
            expected_source_revision=REVISION,
        )
        self.assertTrue(any("source revision" in issue for issue in issues))

    def test_rejects_manifest_artifact_api_digest_mismatch(self):
        checker = _load_checker()
        release_payload, manifests = _candidate(checker)
        first_manifest = manifests[sorted(manifests)[0]]
        first_artifact = first_manifest.payload["artifacts"][0]["name"]
        for row in release_payload["assets"]:
            if row["name"] == first_artifact:
                row["digest"] = "sha256:" + ("d" * 64)
                break
        issues = checker.validate_candidate_manifests(
            release_payload,
            manifests,
            tag=TAG,
            expected_source_revision=REVISION,
        )
        self.assertTrue(any("digest does not match" in issue for issue in issues))

    def test_rejects_required_asset_not_covered_by_any_manifest(self):
        checker = _load_checker()
        release_payload, manifests = _candidate(checker)
        first_manifest = manifests[sorted(manifests)[0]]
        removed = first_manifest.payload["artifacts"].pop()
        issues = checker.validate_candidate_manifests(
            release_payload,
            manifests,
            tag=TAG,
            expected_source_revision=REVISION,
        )
        self.assertTrue(
            any(
                "not source-bound by a manifest" in issue and removed["name"] in issue
                for issue in issues
            )
        )


if __name__ == "__main__":
    unittest.main()
