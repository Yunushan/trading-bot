#!/usr/bin/env python3
"""Update the README LOC snapshot block from tracked repository files."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path


START_MARKER = "<!-- LOC-SNAPSHOT:START -->"
END_MARKER = "<!-- LOC-SNAPSHOT:END -->"
SNAPSHOT_TIME_PATTERN = re.compile(
    r"^- Snapshot date: `(\d{2}\.\d{2}\.\d{4}) GMT\+3 Time \d{2}:\d{2}:\d{2}`$",
    flags=re.MULTILINE,
)

# Count only tracked source/config/script-like files.
COUNTED_EXTENSIONS = {
    ".py",
    ".cpp",
    ".h",
    ".hpp",
    ".c",
    ".cc",
    ".cxx",
    ".js",
    ".ts",
    ".tsx",
    ".ps1",
    ".sh",
    ".bat",
    ".yml",
    ".yaml",
    ".toml",
    ".cmake",
    ".qrc",
    ".in",
}

COUNTED_FILENAMES = {
    "CMakeLists.txt",
}

COUNT_SCOPE_TEXT = (
    "tracked files with extensions `.py`, `.cpp`, `.h`, `.js`, `.ps1`, `.sh`, "
    "`.bat`, `.yml`, `.cmake`, `.qrc`, `.in` (plus `CMakeLists.txt`)"
)


def _tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    files: list[Path] = []
    for raw in result.stdout.splitlines():
        rel = raw.strip()
        if not rel:
            continue
        path = repo_root / rel
        if not path.is_file():
            continue
        if path.name in COUNTED_FILENAMES or path.suffix.lower() in COUNTED_EXTENSIONS:
            files.append(path)
    return files


def _count_lines(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    total = len(lines)
    non_empty = sum(1 for line in lines if line.strip())
    return total, non_empty


def _normalized_snapshot_time(text: str) -> str:
    """Normalize volatile time-of-day so --check stays meaningful."""
    return SNAPSHOT_TIME_PATTERN.sub(
        r"- Snapshot date: `\1 GMT+3 Time <time>`",
        text,
    )


def build_snapshot_block(repo_root: Path) -> str:
    tracked = _tracked_files(repo_root)
    total = 0
    non_empty = 0
    for path in tracked:
        t, n = _count_lines(path)
        total += t
        non_empty += n

    gmt_plus_3 = dt.timezone(dt.timedelta(hours=3))
    snapshot_dt = dt.datetime.now(gmt_plus_3)
    snapshot_label = (
        f"{snapshot_dt.strftime('%d.%m.%Y')} GMT+3 Time {snapshot_dt.strftime('%H:%M:%S')}"
    )
    return "\n".join(
        [
            f"- Snapshot date: `{snapshot_label}`",
            f"- Total tracked code/config/script lines: `{total:,}`",
            f"- Non-empty tracked code/config/script lines (SLOC-style): `{non_empty:,}`",
            f"- Counting scope: {COUNT_SCOPE_TEXT}",
        ]
    )


def update_readme(readme_path: Path, snapshot_block: str) -> tuple[bool, str]:
    original = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(START_MARKER)}\n)(.*?)(\n{re.escape(END_MARKER)})",
        flags=re.DOTALL,
    )
    match = pattern.search(original)
    if not match:
        raise RuntimeError(
            f"Could not find LOC snapshot markers in {readme_path} "
            f"({START_MARKER} ... {END_MARKER})."
        )

    updated = pattern.sub(rf"\1{snapshot_block}\3", original, count=1)
    changed = updated != original
    return changed, updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--readme",
        default="README.md",
        help="README file path relative to repo root (default: README.md).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; return non-zero if README would change.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    readme_path = (repo_root / args.readme).resolve()

    snapshot = build_snapshot_block(repo_root)
    changed, updated = update_readme(readme_path, snapshot)

    if args.check:
        if changed:
            original = readme_path.read_text(encoding="utf-8")
            # Ignore time-only drift; still enforce date, counts, and scope text.
            if _normalized_snapshot_time(original) == _normalized_snapshot_time(updated):
                print("LOC snapshot is up-to-date.")
                return 0
            print("LOC snapshot is outdated.")
            return 1
        print("LOC snapshot is up-to-date.")
        return 0

    if changed:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"Updated LOC snapshot in {readme_path}")
    else:
        print("LOC snapshot already up-to-date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
