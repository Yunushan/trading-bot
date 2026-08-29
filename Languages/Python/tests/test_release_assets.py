from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_release_assets as checker  # noqa: E402


TAG = "v1.0.41"
DIGEST = "sha256:" + ("a" * 64)


def _candidate_payload() -> tuple[dict[str, object], list[checker.ExpectedAsset]]:
    _, expected_assets = checker._build_expected_assets(TAG)
    rows = [
        {
            "name": asset.name,
            "state": "uploaded",
            "size": 1,
            "digest": DIGEST,
        }
        for asset in expected_assets
        if asset.required
    ]
    return (
        {
            "tag_name": TAG,
            "draft": False,
            "prerelease": True,
            "assets": rows,
        },
        expected_assets,
    )


class ReleaseAssetPayloadTests(unittest.TestCase):
    def test_extracts_http_status_from_cli_fallback_error(self):
        self.assertEqual(
            404,
            checker._http_status_from_error_text("gh: Not Found (HTTP 404)"),
        )
        self.assertIsNone(checker._http_status_from_error_text("authentication failed"))

    def test_accepts_complete_digest_bound_prerelease_candidate(self):
        payload, expected_assets = _candidate_payload()
        self.assertEqual(
            [],
            checker._release_payload_issues(
                payload,
                tag=TAG,
                expected_assets=expected_assets,
                require_prerelease_candidate=True,
            ),
        )

    def test_rejects_wrong_release_state_and_tag(self):
        payload, expected_assets = _candidate_payload()
        payload.update({"tag_name": "v1.0.42", "draft": True, "prerelease": False})
        issues = checker._release_payload_issues(
            payload,
            tag=TAG,
            expected_assets=expected_assets,
            require_prerelease_candidate=True,
        )
        self.assertTrue(any("tag_name" in issue for issue in issues))
        self.assertTrue(any("not draft" in issue for issue in issues))
        self.assertTrue(any("marked prerelease" in issue for issue in issues))

    def test_rejects_incomplete_or_ambiguous_required_asset_metadata(self):
        payload, expected_assets = _candidate_payload()
        rows = payload["assets"]
        assert isinstance(rows, list)
        first = rows[0]
        second = rows[1]
        third = rows[2]
        assert isinstance(first, dict)
        assert isinstance(second, dict)
        assert isinstance(third, dict)
        first["state"] = "new"
        second["size"] = 0
        third["digest"] = ""
        rows.append(copy.deepcopy(rows[3]))

        issues = checker._release_payload_issues(
            payload,
            tag=TAG,
            expected_assets=expected_assets,
            require_prerelease_candidate=True,
        )
        self.assertTrue(any("not fully uploaded" in issue for issue in issues))
        self.assertTrue(any("positive byte size" in issue for issue in issues))
        self.assertTrue(any("SHA-256 digest" in issue for issue in issues))
        self.assertTrue(any("exactly once" in issue for issue in issues))

    def test_legacy_release_does_not_retroactively_require_api_digest(self):
        _, expected_assets = checker._build_expected_assets("v1.0.40")
        payload = {
            "tag_name": "v1.0.40",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": asset.name, "state": "uploaded", "size": 1, "digest": None}
                for asset in expected_assets
                if asset.required
            ],
        }
        self.assertEqual(
            [],
            checker._release_payload_issues(
                payload,
                tag="v1.0.40",
                expected_assets=expected_assets,
            ),
        )


if __name__ == "__main__":
    unittest.main()
