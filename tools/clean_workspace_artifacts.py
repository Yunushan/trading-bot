from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from audit_workspace_hygiene import NOISY_IGNORED_PREFIXES


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
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _ignored_paths() -> list[str]:
    rows = _git_lines("status", "--ignored", "--short")
    return [row[3:] for row in rows if row.startswith("!! ")]


def _is_noisy_artifact(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in NOISY_IGNORED_PREFIXES)


def _is_inside_repo(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def clean_workspace_artifacts(*, apply: bool = False) -> dict[str, object]:
    root = _repo_root()
    planned = [path for path in _ignored_paths() if _is_noisy_artifact(path)]
    removed: list[str] = []
    skipped: list[dict[str, str]] = []

    if not apply:
        return {
            "applied": False,
            "planned_count": len(planned),
            "planned": planned,
            "removed_count": 0,
            "removed": removed,
            "skipped": skipped,
        }

    for path in planned:
        target = root / path
        if not _is_inside_repo(target, root):
            skipped.append({"path": path, "reason": "outside repository"})
            continue
        if not target.exists():
            skipped.append({"path": path, "reason": "does not exist"})
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(path)

    return {
        "applied": True,
        "planned_count": len(planned),
        "planned": planned,
        "removed_count": len(removed),
        "removed": removed,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely remove ignored generated artifacts reported by the workspace hygiene audit."
    )
    parser.add_argument("--apply", action="store_true", help="Delete the planned ignored generated artifacts.")
    parser.add_argument("--json", action="store_true", help="Print the cleanup plan/result as JSON.")
    args = parser.parse_args(argv)

    summary = clean_workspace_artifacts(apply=args.apply)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    action = "Removed" if args.apply else "Would remove"
    print(f"{action} {summary['planned_count']} ignored generated artifact(s):")
    for path in summary["planned"]:
        print(f"  - {path}")
    if not args.apply:
        print("Run with --apply to delete these paths.")
    if summary["skipped"]:
        print("Skipped:")
        for item in summary["skipped"]:
            print(f"  - {item['path']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
