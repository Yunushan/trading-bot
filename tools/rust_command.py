"""Run locked Cargo commands with a narrow secure WSL retry on Windows."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


_SCHANNEL_REVOCATION_ERROR = "CRYPT_E_NO_REVOCATION_CHECK"


def is_schannel_revocation_failure(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return False
    output = f"{result.stdout}\n{result.stderr}"
    return _SCHANNEL_REVOCATION_ERROR in output


def _wsl_path(wsl: str, path: Path, *, timeout: int) -> str:
    windows_path = str(path).replace("\\", "/")
    result = subprocess.run(
        [wsl, "--", "wslpath", "-a", "-u", windows_path],
        capture_output=True,
        text=True,
        timeout=min(timeout, 30),
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _rust_environment_for_wsl(env: dict[str, str]) -> dict[str, str]:
    prefixes = ("BINANCE_", "RUST_NATIVE_", "TRADING_BOT_")
    return {
        key: value
        for key, value in env.items()
        if key.startswith(prefixes) and key.isidentifier()
    }


def _wsl_environment_value(wsl: str, value: str, *, timeout: int) -> str:
    """Translate Windows absolute paths before exporting them to Linux Cargo."""

    if len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/"):
        try:
            translated = _wsl_path(wsl, Path(value), timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return value
        return translated or value
    return value


def _write_wsl_environment_file(
    wsl: str,
    env: dict[str, str],
    *,
    timeout: int,
) -> tuple[Path | None, str]:
    """Write the narrowly allowed WSL environment without exposing values in argv."""

    values = _rust_environment_for_wsl(env)
    if not values:
        return None, ""
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix="trading-bot-rust-env-",
            suffix=".sh",
            delete=False,
        ) as stream:
            path = Path(stream.name)
            for key, value in sorted(values.items()):
                translated = _wsl_environment_value(wsl, value, timeout=timeout)
                stream.write(f"{key}={shlex.quote(translated)}\n")
        os.chmod(path, 0o600)
        wsl_path = _wsl_path(wsl, path, timeout=timeout)
        if wsl_path:
            return path, wsl_path
    except (OSError, subprocess.SubprocessError):
        pass
    if path is not None:
        path.unlink(missing_ok=True)
    return None, ""


def run_cargo_with_secure_wsl_fallback(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run Cargo normally, retrying only Schannel revocation failures through WSL.

    The fallback does not alter Cargo TLS settings. It is intentionally limited to
    Windows hosts with an available WSL distribution and the specific Schannel
    revocation failure that prevents Cargo from reaching crates.io.
    """

    active_env = env if env is not None else os.environ.copy()
    native = subprocess.run(
        command,
        cwd=cwd,
        env=active_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if sys.platform != "win32" or not is_schannel_revocation_failure(native):
        return native, "native"

    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return native, "native"
    try:
        wsl_cwd = _wsl_path(wsl, cwd, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return native, "native"
    if not wsl_cwd:
        return native, "native"

    environment_file, wsl_environment_file = _write_wsl_environment_file(wsl, active_env, timeout=timeout)
    if _rust_environment_for_wsl(active_env) and not wsl_environment_file:
        return native, "native"
    wsl_command = ["cargo", *command[1:]]
    cargo_command = " ".join(shlex.quote(part) for part in wsl_command)
    source_environment = (
        f"set -a; . {shlex.quote(wsl_environment_file)}; set +a; " if wsl_environment_file else ""
    )
    try:
        fallback = subprocess.run(
            [wsl, "--cd", wsl_cwd, "--", "bash", "-lc", f"{source_environment}exec {cargo_command}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        if environment_file is not None:
            environment_file.unlink(missing_ok=True)
    if fallback.returncode == 0:
        return fallback, "wsl"

    return (
        subprocess.CompletedProcess(
            command,
            fallback.returncode,
            stdout=fallback.stdout,
            stderr=(
                f"Windows Cargo failed with {_SCHANNEL_REVOCATION_ERROR}; "
                f"secure WSL fallback completed with exit code {fallback.returncode}.\n"
                f"{fallback.stderr}"
            ),
        ),
        "wsl",
    )
