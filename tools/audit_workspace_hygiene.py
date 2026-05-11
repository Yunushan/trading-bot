from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


NOISY_IGNORED_PREFIXES = (
    ".venv/",
    ".tmp_showtests/",
    "build/",
    "dist/",
    "dist_enduser/",
    "Languages/Python/.venv/",
    "Languages/Python/build/",
    "Languages/Rust/target/",
    "experiments/rust-shells/target/",
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
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def ignored_artifact_summary() -> dict[str, object]:
    rows = _git_lines("status", "--ignored", "--short")
    ignored = [row[3:] for row in rows if row.startswith("!! ")]
    noisy = [
        path
        for path in ignored
        if any(path.replace("\\", "/").startswith(prefix) for prefix in NOISY_IGNORED_PREFIXES)
    ]
    return {
        "ignored_count": len(ignored),
        "noisy_artifact_count": len(noisy),
        "noisy_artifacts": noisy,
        "tracked_count": len(_git_lines("ls-files")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report ignored generated artifacts that make the workspace noisy.")
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    parser.add_argument("--fail-on-noisy", action="store_true", help="Exit non-zero when noisy artifacts are present.")
    args = parser.parse_args(argv)

    summary = ignored_artifact_summary()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1 if args.fail_on_noisy and int(summary["noisy_artifact_count"]) > 0 else 0

    print(f"Tracked files: {summary['tracked_count']}")
    print(f"Ignored paths: {summary['ignored_count']}")
    print(f"Noisy generated artifacts: {summary['noisy_artifact_count']}")
    for path in summary["noisy_artifacts"]:
        print(f"  - {path}")
    return 1 if args.fail_on_noisy and int(summary["noisy_artifact_count"]) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
