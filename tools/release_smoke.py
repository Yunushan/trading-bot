from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"


@dataclass(frozen=True)
class ReleaseStep:
    name: str
    cwd: Path
    command: list[str]


def _quote_arg(value: str) -> str:
    if not value:
        return '""'
    if any(char.isspace() for char in value) or '"' in value:
        return '"' + value.replace('"', r"\"") + '"'
    return value


def _split_command(value: str) -> tuple[str, ...]:
    parts = tuple(part for part in shlex.split(value, posix=sys.platform != "win32") if part)
    if not parts:
        raise ValueError("command cannot be empty")
    return parts


def _display_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return str(path)
    return "." if str(relative) == "." else relative.as_posix()


def _display_command(command: list[str], python_command: tuple[str, ...]) -> str:
    display_args = list(command)
    if python_command == (sys.executable,) and tuple(display_args[:1]) == python_command:
        display_args[:1] = ["python"]
    return " ".join(_quote_arg(str(arg)) for arg in display_args)


def _mypy_cache_dir() -> str:
    return str(Path(tempfile.gettempdir()) / "trading-bot-release-mypy-cache")


def build_release_steps(
    *,
    python_executable: str | None = None,
    python_command: tuple[str, ...] | None = None,
    runtime_python_command_arg: str = "",
    skip_full_tests: bool,
    manual_smoke_mode: str,
) -> list[ReleaseStep]:
    python = python_command or ((python_executable,) if python_executable else (sys.executable,))
    runtime_check_command = [
        *python,
        "tools/check_local_tool_versions.py",
        "--strict",
    ]
    if runtime_python_command_arg:
        runtime_check_command.extend(["--python-command", runtime_python_command_arg])
    steps = [
        ReleaseStep(
            name="check runtime tool versions",
            cwd=REPO_ROOT,
            command=runtime_check_command,
        ),
        ReleaseStep(
            name="check client dependency locks",
            cwd=REPO_ROOT,
            command=[
                *python,
                "tools/check_client_dependency_locks.py",
                "--json",
                "--strict",
            ],
        ),
        ReleaseStep(
            name="compile Python sources",
            cwd=REPO_ROOT,
            command=[
                *python,
                "tools/check_python_sources_compile.py",
                "apps/desktop-pyqt/main.py",
                "apps/service-api/main.py",
                "Languages/Python/app",
                "Languages/Python/trading_core",
                "Languages/Python/main.py",
                "Languages/Python/tools",
                "tools",
            ],
        ),
        ReleaseStep(
            name="lint Python workspace",
            cwd=REPO_ROOT,
            command=[
                *python,
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--config",
                "Languages/Python/pyproject.toml",
                "Languages/Python",
            ],
        ),
        ReleaseStep(
            name="check Python dependency metadata",
            cwd=REPO_ROOT,
            command=[
                *python,
                "Languages/Python/tools/check_dependency_metadata.py",
            ],
        ),
        ReleaseStep(
            name="type-check configured Python targets",
            cwd=PYTHON_ROOT,
            command=[
                *python,
                "-m",
                "mypy",
                "--no-incremental",
                "--cache-dir",
                _mypy_cache_dir(),
                "--config-file",
                "pyproject.toml",
            ],
        ),
        ReleaseStep(
            name="smoke-check canonical service launcher",
            cwd=REPO_ROOT,
            command=[
                *python,
                "apps/service-api/main.py",
                "--healthcheck",
            ],
        ),
    ]

    if manual_smoke_mode != "skip":
        manual_command = [
            *python,
            "tools/manual_smoke.py",
            "--json",
        ]
        if manual_smoke_mode == "fast":
            manual_command.append("--skip-http")
        steps.append(
            ReleaseStep(
                name="manual desktop/service smoke",
                cwd=PYTHON_ROOT,
                command=manual_command,
            )
        )

    if not skip_full_tests:
        steps.append(
            ReleaseStep(
                name="run Python test suite",
                cwd=PYTHON_ROOT,
                command=[
                    *python,
                    "tools/run_python_tests.py",
                    "--runner",
                    "pytest",
                ],
            )
        )

    return steps


def _print_plan(steps: list[ReleaseStep], python_command: tuple[str, ...]) -> None:
    print("Release smoke plan:")
    for step in steps:
        cwd = _display_path(step.cwd)
        command = _display_command(step.command, python_command)
        print(f"- {step.name} [cwd={cwd}]: {command}")


def _run_steps(steps: list[ReleaseStep], python_command: tuple[str, ...]) -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for step in steps:
        command = _display_command(step.command, python_command)
        cwd = _display_path(step.cwd)
        print(f"[RUN] {step.name} [cwd={cwd}]: {command}", flush=True)
        result = subprocess.run(step.command, cwd=step.cwd, check=False, env=env)
        if result.returncode != 0:
            print(f"[FAIL] {step.name} exited with {result.returncode}", flush=True)
            return int(result.returncode)
        print(f"[PASS] {step.name}", flush=True)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local pre-release smoke checks before tagging or publishing assets.",
    )
    parser.add_argument(
        "--python",
        default="",
        help="Single Python executable used for release checks. Default: current interpreter.",
    )
    parser.add_argument(
        "--python-command",
        default="",
        help='Python command used for release checks, for example: "python" or python3.14.',
    )
    parser.add_argument(
        "--skip-full-tests",
        action="store_true",
        help="Skip the full pytest run. Useful when pytest already ran in the same CI job.",
    )
    parser.add_argument(
        "--manual-smoke-mode",
        choices=("full", "fast", "skip"),
        default="full",
        help="Manual smoke depth: full starts the HTTP service, fast skips HTTP, skip disables it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned checks without running them.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.python and args.python_command:
        print("Use either --python or --python-command, not both.", file=sys.stderr)
        return 2
    try:
        python_command = (
            _split_command(str(args.python_command))
            if args.python_command
            else (str(args.python),)
            if args.python
            else (sys.executable,)
        )
    except ValueError as exc:
        print(f"Invalid --python-command: {exc}", file=sys.stderr)
        return 2
    runtime_python_command_arg = str(args.python_command) if args.python_command else ""
    steps = build_release_steps(
        python_command=python_command,
        runtime_python_command_arg=runtime_python_command_arg,
        skip_full_tests=bool(args.skip_full_tests),
        manual_smoke_mode=str(args.manual_smoke_mode),
    )
    if args.dry_run:
        _print_plan(steps, python_command)
        return 0
    return _run_steps(steps, python_command)


if __name__ == "__main__":
    raise SystemExit(main())
