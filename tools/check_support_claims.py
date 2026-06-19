from __future__ import annotations

import argparse
import json
from pathlib import Path


SCAN_ROOTS = (
    "README.md",
    "docs",
    "Languages/Python",
    "experiments",
    "tools",
)

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "target",
}

BANNED_CLAIMS = (
    "Entire Python app parity ready: true",
    "C++ entire Python app parity ready: true",
    "Rust entire Python app parity ready: true",
    "Full feature parity with Python app",
    "source-level full-parity",
    "native_full_python_app_parity_ready() == true",
    "cpp_entire_python_app_parity_ready() == true",
    "rust_entire_python_app_parity_ready() == true",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_binary(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return True
    return b"\0" in sample


def _candidate_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for scan_root in SCAN_ROOTS:
        path = root / scan_root
        if path.is_file():
            candidates.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in EXCLUDED_PARTS for part in candidate.relative_to(root).parts):
                continue
            candidates.append(candidate)
    return candidates


def check_support_claims(root: Path | None = None) -> dict[str, object]:
    repo_root = root or _repo_root()
    own_path = Path(__file__).resolve()
    findings: list[dict[str, object]] = []
    for path in _candidate_files(repo_root):
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved == own_path or _is_binary(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        for claim in BANNED_CLAIMS:
            start = 0
            while True:
                index = text.find(claim, start)
                if index < 0:
                    break
                line = text.count("\n", 0, index) + 1
                findings.append({"path": rel_path, "line": line, "claim": claim})
                start = index + len(claim)
    return {
        "ok": not findings,
        "checked_files": len(_candidate_files(repo_root)),
        "banned_claims": list(BANNED_CLAIMS),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block known unsupported parity/support claims.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    report = check_support_claims()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        status = "ok" if report["ok"] else "failed"
        print(f"Support claim audit: {status}")
        for finding in report["findings"]:
            print(f"- {finding['path']}:{finding['line']} banned claim: {finding['claim']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
