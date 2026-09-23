#!/usr/bin/env python3
"""Run a full Git history secret scan without exposing scanner findings in CI logs."""

from __future__ import annotations

import argparse
import secrets
import string
import subprocess
import sys
import tempfile
from pathlib import Path

LEAK_EXIT_CODE = 23


def _scan(source: Path, executable: str, *, timeout: int = 300) -> int:
    # Capture even scanner failures: file contents, matches, paths and command
    # diagnostics must never be echoed into a public CI log.
    result = subprocess.run(
        [
            executable, "git", "--log-opts=--all", "--redact=100",
            "--no-banner", "--log-level=error", "--exit-code", str(LEAK_EXIT_CODE), ".",
        ],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return result.returncode


def synthetic_regression(executable: str) -> bool:
    """A token removed from the working tree must still be found in history."""
    with tempfile.TemporaryDirectory(prefix="trading-bot-secret-scan-") as directory:
        root = Path(directory)
        # Construct at runtime so the fake credential never enters this repo.
        fake = "ghp_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(36))

        def git(*args: str) -> None:
            result = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True,
                check=False, timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError("synthetic Git fixture could not be prepared")

        git("init", "-q")
        git("config", "user.email", "scan-test@example.invalid")
        git("config", "user.name", "Synthetic Scan Test")
        fixture = root / "fixture.txt"
        fixture.write_text("token=" + fake + "\n", encoding="utf-8")
        git("add", "fixture.txt")
        git("commit", "-qm", "synthetic credential")
        fixture.write_text("removed\n", encoding="utf-8")
        git("commit", "-qam", "remove synthetic credential")
        return _scan(root, executable, timeout=60) == LEAK_EXIT_CODE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--gitleaks", default="gitleaks")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            if synthetic_regression(args.gitleaks):
                print("Secret scanner history regression passed.")
                return 0
            print("Secret scanner failed the synthetic history regression.", file=sys.stderr)
            return 1
        source = args.source.resolve(strict=True)
        if not (source / ".git").exists():
            raise ValueError("source must be a Git checkout")
        status = _scan(source, args.gitleaks)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        # Deliberately omit exception text, which may include scanner output.
        print("Secret scan could not complete safely; fail closed.", file=sys.stderr)
        return 1
    if status == 0:
        print("Secret scan passed across fetched Git history.")
        return 0
    if status == LEAK_EXIT_CODE:
        print("Potential credential detected in Git history. Review privately and rotate if real.", file=sys.stderr)
        return 1
    print("Secret scanner returned an error; fail closed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
