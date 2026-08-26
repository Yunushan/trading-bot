from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

CHECKER_PATH = TOOLS_DIR / "check_release_publication_state.py"
TAG = "v1.0.41"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_release_publication_state", CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleasePublicationStateTests(unittest.TestCase):
    def test_accepts_missing_or_existing_prerelease_candidate(self):
        checker = _load_checker()
        self.assertEqual([], checker.validate_publication_state(None, tag=TAG))
        self.assertEqual(
            [],
            checker.validate_publication_state(
                {"tag_name": TAG, "draft": False, "prerelease": True},
                tag=TAG,
            ),
        )

    def test_rejects_stable_release_to_prevent_demotion(self):
        checker = _load_checker()
        issues = checker.validate_publication_state(
            {"tag_name": TAG, "draft": False, "prerelease": False},
            tag=TAG,
        )
        self.assertTrue(any("must not demote" in issue for issue in issues))

    def test_rejects_draft_or_wrong_tag_release(self):
        checker = _load_checker()
        issues = checker.validate_publication_state(
            {"tag_name": "v1.0.42", "draft": True, "prerelease": True},
            tag=TAG,
        )
        self.assertTrue(any("tag_name" in issue for issue in issues))
        self.assertTrue(any("not draft" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
