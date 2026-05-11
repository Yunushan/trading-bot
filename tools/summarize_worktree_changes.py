from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path


GROUP_RULES = (
    ("ci-tooling", (".github/", ".gitattributes", ".pre-commit-config.yaml", ".python-version", ".node-version", "tools/")),
    ("python-settings", ("Languages/Python/app/settings/", "Languages/Python/app/config.py")),
    ("service-api", ("Languages/Python/app/service/", "apps/service-api/", "docs/SERVICE_API.md")),
    ("exchange-order-safety", ("Languages/Python/app/integrations/exchanges/", "Languages/Python/trading_core/orders.py")),
    ("llm", ("Languages/Python/app/integrations/llm/", "Languages/Python/app/gui/shared/llm_settings_panel.py")),
    ("web-dashboard", ("apps/web-dashboard/",)),
    ("mobile-client", ("apps/mobile-client/",)),
    ("tests", ("Languages/Python/tests/",)),
    ("docs", ("README.md", "Languages/Python/README.md", "docs/")),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def _group_for_path(path: str) -> str:
    clean = path.replace("\\", "/")
    for group, prefixes in GROUP_RULES:
        if any(clean == prefix.rstrip("/") or clean.startswith(prefix) for prefix in prefixes):
            return group
    return "other"


def summarize_worktree() -> dict[str, object]:
    rows = _git_lines("status", "--short")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        status = row[:2].strip() or "modified"
        path = row[3:] if len(row) > 3 else row
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        grouped[_group_for_path(path)].append({"status": status, "path": path})
    return {
        "total_changed_paths": sum(len(items) for items in grouped.values()),
        "groups": {group: items for group, items in sorted(grouped.items())},
        "recommended_review_order": [
            "ci-tooling",
            "python-settings",
            "service-api",
            "exchange-order-safety",
            "llm",
            "web-dashboard",
            "mobile-client",
            "tests",
            "docs",
            "other",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Group dirty working-tree paths into reviewable slices.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)
    summary = summarize_worktree()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    print(f"Changed paths: {summary['total_changed_paths']}")
    groups = summary["groups"]
    for group in summary["recommended_review_order"]:
        items = groups.get(group, [])
        if not items:
            continue
        print(f"\n[{group}] {len(items)} path(s)")
        for item in items:
            print(f"  {item['status']:>2} {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
