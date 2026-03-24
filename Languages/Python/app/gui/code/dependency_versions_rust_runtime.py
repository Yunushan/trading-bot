from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from . import code_language_launch
from .code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    RUST_PROJECT_PATH,
)

_RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC = 180.0
_RUSTUP_WINDOWS_INSTALLER_URL_BASE = "https://win.rustup.rs"
_RUSTUP_UNIX_INSTALLER_URL = "https://sh.rustup.rs"
_RUST_AUTO_INSTALL_LOCK = threading.Lock()
_RUST_PACKAGE_METADATA_CACHE: dict[str, dict[str, str]] = {}
_RUST_TOOL_VERSION_CACHE: dict[str, tuple[str | None, float]] = {}


def _rust_manifest_path(path_value: str | None = None) -> Path:
    relative_path = str(path_value or "").strip()
    if relative_path:
        return (_BASE_PROJECT_PATH / relative_path).resolve()
    return RUST_PROJECT_PATH / "Cargo.toml"


def _rust_package_metadata(path_value: str | None = None) -> dict[str, str]:
    manifest_path = _rust_manifest_path(path_value)
    cache_key = str(manifest_path)
    cached = _RUST_PACKAGE_METADATA_CACHE.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    metadata: dict[str, str] = {}
    try:
        text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        _RUST_PACKAGE_METADATA_CACHE[cache_key] = metadata
        return metadata

    current_section = ""
    for raw_line in text.splitlines():
        stripped = str(raw_line or "").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped.strip("[]").strip().lower()
            continue
        if current_section != "package":
            continue
        match = re.match(r'(?i)(name|version)\s*=\s*"([^"]+)"', stripped)
        if not match:
            continue
        metadata[str(match.group(1)).strip().lower()] = str(match.group(2)).strip()

    _RUST_PACKAGE_METADATA_CACHE[cache_key] = dict(metadata)
    return metadata


def _rust_project_version(path_value: str | None = None) -> str | None:
    version_text = str(_rust_package_metadata(path_value).get("version") or "").strip()
    return version_text or None


def _rust_toolchain_bin_dir() -> Path:
    cargo_home = str(os.environ.get("CARGO_HOME") or "").strip()
    if cargo_home:
        try:
            return Path(cargo_home).expanduser().resolve() / "bin"
        except Exception:
            return Path(cargo_home).expanduser() / "bin"
    return Path.home() / ".cargo" / "bin"


def _rust_tool_path(executable: str) -> Path | None:
    base_name = str(executable or "").strip()
    if not base_name:
        return None

    candidates = [base_name]
    if sys.platform == "win32" and not base_name.lower().endswith(".exe"):
        candidates.insert(0, f"{base_name}.exe")

    for name in candidates:
        found = shutil.which(name)
        if found:
            try:
                return Path(found).resolve()
            except Exception:
                return Path(found)

    bin_dir = _rust_toolchain_bin_dir()
    for name in candidates:
        path = bin_dir / name
        try:
            if path.is_file():
                return path.resolve()
        except Exception:
            continue
    return None


def _rust_toolchain_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ.copy())
    cargo_bin = _rust_toolchain_bin_dir()
    try:
        cargo_bin_text = str(cargo_bin.resolve())
    except Exception:
        cargo_bin_text = str(cargo_bin)
    if cargo_bin_text and cargo_bin.is_dir():
        current_path = str(env.get("PATH") or "")
        parts = [part for part in current_path.split(os.pathsep) if str(part or "").strip()]
        normalized_parts = {os.path.normcase(os.path.normpath(part)) for part in parts}
        normalized_bin = os.path.normcase(os.path.normpath(cargo_bin_text))
        if normalized_bin not in normalized_parts:
            env["PATH"] = os.pathsep.join([cargo_bin_text, *parts]) if parts else cargo_bin_text
    return env


def _reset_rust_dependency_caches() -> None:
    _RUST_PACKAGE_METADATA_CACHE.clear()
    _RUST_TOOL_VERSION_CACHE.clear()


def _runtime():
    from . import dependency_versions_runtime as runtime

    return runtime


def _rust_tool_version(command: list[str], *, cache_key: str) -> str | None:
    now = time.time()
    cached = _RUST_TOOL_VERSION_CACHE.get(cache_key)
    if isinstance(cached, tuple) and len(cached) == 2:
        cached_value, cached_at = cached
        try:
            if now - float(cached_at) < 20.0:
                return str(cached_value or "").strip() or None
        except Exception:
            pass

    executable = str(command[0] if command else "").strip()
    tool_path = _rust_tool_path(executable)
    if not executable or tool_path is None:
        _RUST_TOOL_VERSION_CACHE[cache_key] = (None, now)
        return None

    version_text = None
    try:
        resolved_command = [str(tool_path), *command[1:]]
        run_kwargs: dict[str, object] = {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": 4.0,
            "env": _rust_toolchain_env(),
        }
        if sys.platform == "win32":
            run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
                startupinfo.wShowWindow = 0
                run_kwargs["startupinfo"] = startupinfo
            except Exception:
                pass
        result = subprocess.run(
            resolved_command,
            **run_kwargs,
        )
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        version_text = _runtime()._extract_semver_from_text(output)
    except Exception:
        version_text = None

    _RUST_TOOL_VERSION_CACHE[cache_key] = (version_text, now)
    return version_text


def _rust_custom_installed_value(target: dict[str, str]) -> str | None:
    custom = str(target.get("custom") or "").strip().lower()
    if custom == "rust_rustc":
        return _rust_tool_version(["rustc", "--version"], cache_key="rustc")
    if custom == "rust_cargo":
        return _rust_tool_version(["cargo", "--version"], cache_key="cargo")
    if custom == "rust_file_version":
        manifest_path = _rust_manifest_path(target.get("path"))
        version_text = _rust_project_version(target.get("path"))
        if version_text:
            return version_text
        if manifest_path.is_file():
            return "Scaffolded"
    return None


def _rust_custom_latest_value(target: dict[str, str], installed_value: str) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    latest_text = str(target.get("latest") or "").strip()
    if custom == "rust_file_version":
        return installed_value or latest_text or "Unknown"
    if _runtime()._cpp_version_is_installed_marker(installed_value):
        return installed_value
    return latest_text or "Unknown"


def _rust_custom_usage_value(target: dict[str, str]) -> str:
    custom = str(target.get("custom") or "").strip().lower()
    if custom == "rust_file_version":
        return "Active" if _rust_manifest_path(target.get("path")).is_file() else "Passive"
    installed_value = _rust_custom_installed_value(target)
    return "Active" if _runtime()._cpp_version_is_installed_marker(installed_value) else "Passive"


def _rust_auto_install_enabled() -> bool:
    raw_value = str(os.environ.get("TB_RUST_AUTO_INSTALL", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _rust_auto_install_cooldown_seconds() -> float:
    raw_value = str(os.environ.get("TB_RUST_AUTO_INSTALL_COOLDOWN_SEC", "") or "").strip()
    if not raw_value:
        return _RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC
    try:
        return max(0.0, float(raw_value))
    except Exception:
        return _RUST_AUTO_INSTALL_DEFAULT_COOLDOWN_SEC


def _rust_missing_tool_labels() -> list[str]:
    missing: list[str] = []
    if _rust_tool_path("rustc") is None:
        missing.append("rustc")
    if _rust_tool_path("cargo") is None:
        missing.append("cargo")
    return missing


def _rust_toolchain_is_ready() -> bool:
    return not _rust_missing_tool_labels()


def _rust_installer_cache_dir() -> Path:
    root = (
        str(os.environ.get("LOCALAPPDATA") or "").strip()
        or str(os.environ.get("TEMP") or "").strip()
        or tempfile.gettempdir()
    )
    return (Path(root).expanduser() / "trading-bot-rustup").resolve()


def _rustup_windows_install_url() -> str:
    machine = str(platform.machine() or "").strip().lower()
    arch = "x86_64"
    if machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    elif machine in {"x86", "i386", "i686"}:
        arch = "i686"
    return f"{_RUSTUP_WINDOWS_INSTALLER_URL_BASE}/{arch}"


def _download_to_path(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
    with urllib.request.urlopen(request, timeout=45.0) as response:
        with open(destination, "wb") as fh:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)


def _install_rust_toolchain() -> tuple[bool, str]:
    with _RUST_AUTO_INSTALL_LOCK:
        if _rust_toolchain_is_ready():
            return True, "Rust toolchain already installed."

        cache_dir = _rust_installer_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == "win32":
            installer_path = cache_dir / "rustup-init.exe"
            install_url = _rustup_windows_install_url()
            command = [
                str(installer_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
            ]
        else:
            installer_path = cache_dir / "rustup-init.sh"
            install_url = _RUSTUP_UNIX_INSTALLER_URL
            sh_path = shutil.which("sh") or "/bin/sh"
            command = [
                str(sh_path),
                str(installer_path),
                "-y",
                "--default-toolchain",
                "stable",
                "--profile",
                "minimal",
            ]

        try:
            _download_to_path(install_url, installer_path)
        except Exception as exc:
            return False, f"Failed to download rustup installer from {install_url}: {exc}"

        if sys.platform != "win32":
            try:
                installer_path.chmod(0o755)
            except Exception:
                pass

        ok, output = code_language_launch.run_command_capture_hidden(
            command,
            cwd=cache_dir,
            env=_rust_toolchain_env(),
        )
        env_with_cargo = _rust_toolchain_env()
        try:
            os.environ["PATH"] = env_with_cargo.get("PATH", os.environ.get("PATH", ""))
        except Exception:
            pass

        _reset_rust_dependency_caches()
        ready = _rust_toolchain_is_ready()
        if ok and ready:
            return True, output or "Rust toolchain installed."
        tail = _runtime()._tail_text(output, max_lines=20, max_chars=4000)
        if ready:
            return True, tail or "Rust toolchain installed."
        return False, tail or "rustup installation did not make cargo/rustc available."
