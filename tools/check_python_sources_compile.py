from __future__ import annotations

import argparse
import json
import tokenize
from pathlib import Path


DEFAULT_TARGETS = (
    "apps/desktop-pyqt/main.py",
    "apps/service-api/main.py",
    "Languages/Python/app",
    "Languages/Python/trading_core",
    "Languages/Python/main.py",
    "Languages/Python/tools",
    "tools",
)

SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vcpkg",
    "__pycache__",
    "build",
    "dist",
    "dist_enduser",
    "node_modules",
    "target",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def _iter_python_files(root: Path, targets: list[str]) -> tuple[list[Path], list[dict[str, str]]]:
    files: list[Path] = []
    errors: list[dict[str, str]] = []
    for target in targets:
        path = (root / target).resolve()
        if not path.exists():
            errors.append({"path": target, "error": "path does not exist"})
            continue
        if path.is_file():
            if path.suffix == ".py":
                files.append(path)
            continue
        for child in path.rglob("*.py"):
            relative_child = child.relative_to(root)
            if not _is_skipped(relative_child):
                files.append(child)
    unique_files = sorted(set(files), key=lambda item: _display_path(item, root))
    return unique_files, errors


def _syntax_error_message(exc: SyntaxError) -> str:
    location = ""
    if exc.lineno is not None:
        location = f" line {exc.lineno}"
        if exc.offset is not None:
            location += f", column {exc.offset}"
    return f"{exc.msg}{location}"


def check_python_sources_compile(
    targets: list[str] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, object]:
    repo_root = (root or _repo_root()).resolve()
    selected_targets = list(targets or DEFAULT_TARGETS)
    files, errors = _iter_python_files(repo_root, selected_targets)
    checked: list[str] = []
    for path in files:
        display_path = _display_path(path, repo_root)
        try:
            with tokenize.open(str(path)) as handle:
                source = handle.read()
            compile(source, display_path, "exec", dont_inherit=True)
            checked.append(display_path)
        except SyntaxError as exc:
            errors.append({"path": display_path, "error": _syntax_error_message(exc)})
        except OSError as exc:
            errors.append({"path": display_path, "error": str(exc)})
    return {
        "checked_count": len(checked),
        "errors": errors,
        "ok": not errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Python sources in memory without writing __pycache__.")
    parser.add_argument("targets", nargs="*", help="Files or directories to compile. Defaults to release targets.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable summary.")
    args = parser.parse_args(argv)

    payload = check_python_sources_compile(list(args.targets) or None)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Compiled {payload['checked_count']} Python source file(s) in memory.")
        for error in payload["errors"]:
            print(f"[FAIL] {error['path']}: {error['error']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
