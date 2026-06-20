from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK_SCRIPT = REPO_ROOT / "tools" / "check_hardening_articles.py"

SPEC = importlib.util.spec_from_file_location("check_hardening_articles", CHECK_SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
check_hardening_articles = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_hardening_articles
SPEC.loader.exec_module(check_hardening_articles)


class HardeningArticleTests(unittest.TestCase):
    def test_hardening_article_manifest_covers_all_articles(self):
        article_ids = [article.article_id for article in check_hardening_articles.HARDENING_ARTICLES]

        self.assertEqual(list(range(1, 19)), article_ids)

    def test_hardening_articles_have_current_repository_evidence(self):
        report = check_hardening_articles.check_hardening_articles(REPO_ROOT)

        failed = [
            (article["article"], article["title"], article["evidence"])
            for article in report["articles"]
            if not article["ok"]
        ]
        self.assertEqual([], failed)


if __name__ == "__main__":
    unittest.main()
