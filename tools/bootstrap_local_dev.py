from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
CLIENT_DIRS = (REPO_ROOT / "apps" / "web-dashboard", REPO_ROOT / "apps" / "mobile-client")

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from check_local_tool_versions import build_tool_version_report  # noqa: E402


@dataclass(frozen=True, slots=True)
class BootstrapStep:
    name: str
    cwd: Path
    command: tuple[str, ...]


def _command_path(name: str) -> str:
    candidates = (name, f"{name}.cmd") if sys.platform == "win32" else (name,)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return name


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


def _coerce_python_command(
    *, python_executable: str | None = None, python_command: tuple[str, ...] | None = None
) -> tuple[str, ...]:
    if python_command:
        return python_command
    if python_executable:
        return (python_executable,)
    return (sys.executable,)


def _display_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return str(path)
    return "." if str(relative) == "." else relative.as_posix()


def _display_command(command: tuple[str, ...], *, python_command: tuple[str, ...], npm_executable: str) -> str:
    display_args = list(command)
    if python_command == (sys.executable,) and tuple(display_args[:1]) == python_command:
        display_args[:1] = ["python"]
    display_args = ["npm" if arg == npm_executable else arg for arg in display_args]
    return " ".join(_quote_arg(str(arg)) for arg in display_args)


def build_bootstrap_steps(
    *,
    python_executable: str | None = None,
    python_command: tuple[str, ...] | None = None,
    npm_executable: str,
    include_python_deps: bool = True,
    include_client_deps: bool = True,
) -> list[BootstrapStep]:
    python = _coerce_python_command(python_executable=python_executable, python_command=python_command)
    steps: list[BootstrapStep] = []
    if include_python_deps:
        steps.extend(
            [
                BootstrapStep(
                    name="upgrade pip",
                    cwd=REPO_ROOT,
                    command=(*python, "-m", "pip", "install", "--upgrade", "pip"),
                ),
                BootstrapStep(
                    name="install Python desktop/service/dev surface",
                    cwd=REPO_ROOT,
                    command=(
                        *python,
                        "-m",
                        "pip",
                        "install",
                        "-e",
                        "Languages/Python[desktop,service,dev]",
                    ),
                ),
            ]
        )
    if include_client_deps:
        for client_dir in CLIENT_DIRS:
            if (client_dir / "package.json").is_file():
                steps.append(
                    BootstrapStep(
                        name=f"install {client_dir.name} client dependencies",
                        cwd=client_dir,
                        command=(npm_executable, "install"),
                    )
                )
    return steps


def runtime_remediations(
    *,
    include_python_deps: bool,
    include_client_deps: bool,
    python_command: tuple[str, ...],
) -> list[str]:
    report = build_tool_version_report(
        skip_python=not include_python_deps,
        skip_node=not include_client_deps,
        python_command=python_command,
    )
    remediations = report.get("remediations")
    if not isinstance(remediations, list):
        return []
    return [str(item) for item in remediations if str(item).strip()]


def _print_plan(steps: list[BootstrapStep], *, python_command: tuple[str, ...], npm_executable: str) -> None:
    print("Local developer bootstrap plan:")
    for step in steps:
        cwd = _display_path(step.cwd)
        command = _display_command(step.command, python_command=python_command, npm_executable=npm_executable)
        print(f"- {step.name} [cwd={cwd}]: {command}")


def _run_steps(steps: list[BootstrapStep], *, python_command: tuple[str, ...], npm_executable: str) -> int:
    for step in steps:
        cwd = _display_path(step.cwd)
        command = _display_command(step.command, python_command=python_command, npm_executable=npm_executable)
        print(f"[RUN] {step.name} [cwd={cwd}]: {command}", flush=True)
        result = subprocess.run(list(step.command), cwd=step.cwd, check=False)
        if result.returncode != 0:
            print(f"[FAIL] {step.name} exited with {result.returncode}", flush=True)
            return int(result.returncode)
        print(f"[PASS] {step.name}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap the local contributor environment after runtime versions are installed."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without running them.")
    parser.add_argument("--skip-python-deps", action="store_true", help="Do not install the Python dev surface.")
    parser.add_argument("--skip-client-deps", action="store_true", help="Do not run npm install for app clients.")
    parser.add_argument(
        "--python-command",
        default="",
        help='Python command to validate and use for installs, for example: "py -3.12" or python3.12.',
    )
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Run install commands even when local Python or Node does not match repo version files.",
    )
    args = parser.parse_args(argv)

    include_python_deps = not args.skip_python_deps
    include_client_deps = not args.skip_client_deps
    try:
        python_command = _split_command(args.python_command) if args.python_command else (sys.executable,)
    except ValueError as exc:
        print(f"Invalid --python-command: {exc}")
        return 2
    npm_executable = _command_path("npm")
    remediations = runtime_remediations(
        include_python_deps=include_python_deps,
        include_client_deps=include_client_deps,
        python_command=python_command,
    )
    if remediations:
        print("Runtime setup needs attention:")
        for remediation in remediations:
            print(f"- {remediation}")
        if not args.dry_run and not args.allow_version_mismatch:
            print("Install the declared runtimes first, or pass --allow-version-mismatch to continue anyway.")
            return 1

    steps = build_bootstrap_steps(
        python_command=python_command,
        npm_executable=npm_executable,
        include_python_deps=include_python_deps,
        include_client_deps=include_client_deps,
    )
    if args.dry_run:
        _print_plan(steps, python_command=python_command, npm_executable=npm_executable)
        return 0
    return _run_steps(steps, python_command=python_command, npm_executable=npm_executable)


if __name__ == "__main__":
    raise SystemExit(main())
