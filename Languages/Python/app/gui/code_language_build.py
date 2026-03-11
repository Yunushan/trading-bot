from __future__ import annotations

import copy
import os
import shutil
import sys
from pathlib import Path

from app.gui.code_language_catalog import (
    CPP_BUILD_ROOT,
    CPP_CODE_LANGUAGE_KEY,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    CPP_PROJECT_PATH,
    CPP_SUPPORTED_EXCHANGE_KEY,
    RUST_FRAMEWORK_PACKAGES,
    RUST_PROJECT_PATH,
)


def rust_framework_package_name(config: dict | None = None, *, rust_framework_key) -> str:
    return str(RUST_FRAMEWORK_PACKAGES.get(rust_framework_key(config)) or "").strip()


def build_rust_desktop_executable_for_code_tab(
    config: dict | None = None,
    *,
    rust_framework_key,
    rust_framework_title,
    rust_tool_path,
    run_command_capture_hidden,
    rust_toolchain_env,
    tail_text,
) -> tuple[Path | None, str | None]:
    config_snapshot = dict(config or {})
    framework_title = rust_framework_title(config_snapshot)
    package_name = rust_framework_package_name(config_snapshot, rust_framework_key=rust_framework_key)
    if not framework_title or not package_name:
        return None, "No Rust desktop framework is selected."
    if not RUST_PROJECT_PATH.is_dir():
        return None, f"Rust workspace directory is missing: {RUST_PROJECT_PATH}"

    cargo_path = rust_tool_path("cargo")
    if cargo_path is None:
        return None, "cargo is not installed."

    command = [
        str(cargo_path),
        "build",
        "--manifest-path",
        str(RUST_PROJECT_PATH / "Cargo.toml"),
        "-p",
        package_name,
    ]
    ok, output = run_command_capture_hidden(command, cwd=RUST_PROJECT_PATH, env=rust_toolchain_env())
    if not ok:
        tail = tail_text(output, max_lines=25, max_chars=5000)
        return None, f"Cargo build failed for {framework_title}.\n{tail}".strip()

    executable_name = package_name
    if sys.platform == "win32":
        executable_name = f"{executable_name}.exe"
    candidates = [
        RUST_PROJECT_PATH / "target" / "debug" / executable_name,
        RUST_PROJECT_PATH / "target" / "release" / executable_name,
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve(), None
        except Exception:
            continue
    return None, f"Cargo build completed but {framework_title} executable was not found."


def build_cpp_executable_for_code_tab(
    window,
    *,
    is_frozen_python_app,
    resolve_cpp_qt_prefix_for_code_tab,
    qt_prefix_has_webengine,
    qt_prefix_has_websockets,
    cpp_qt_webengine_available,
    run_command_capture_hidden,
    find_cpp_code_tab_executable,
) -> tuple[Path | None, str | None]:
    if is_frozen_python_app():
        return (
            None,
            "Bundled source build is unavailable in the packaged app. "
            "Automatic C++ runtime download was attempted. If it failed, extract Trading-Bot-C++.zip next to Trading-Bot-Python.exe.",
        )
    if not CPP_PROJECT_PATH.is_dir():
        return None, f"C++ project directory is missing: {CPP_PROJECT_PATH}"
    if shutil.which("cmake") is None:
        return None, "CMake is not available in PATH."
    try:
        CPP_BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return None, f"Could not create build directory '{CPP_BUILD_ROOT}': {exc}"

    prefix_env = resolve_cpp_qt_prefix_for_code_tab()

    def _parse_env_bool(name: str) -> bool | None:
        raw = str(os.environ.get(name, "") or "").strip().lower()
        if not raw:
            return None
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        return None

    env_require_webengine = _parse_env_bool("TB_REQUIRE_QT_WEBENGINE")
    if env_require_webengine is None:
        detected_webengine = qt_prefix_has_webengine(prefix_env) or cpp_qt_webengine_available()
        require_webengine = bool(detected_webengine)
    else:
        require_webengine = bool(env_require_webengine)

    def _configure_cmd(require_we: bool) -> list[str]:
        command = ["cmake", "-S", str(CPP_PROJECT_PATH), "-B", str(CPP_BUILD_ROOT)]
        prefix_has_webengine = qt_prefix_has_webengine(prefix_env)
        prefix_has_websockets = qt_prefix_has_websockets(prefix_env)
        if prefix_env:
            command.append(f"-DCMAKE_PREFIX_PATH={prefix_env}")
            command.append(f"-DQt6_DIR={prefix_env}")
            command.append(
                f"-DCMAKE_DISABLE_FIND_PACKAGE_Qt6WebEngineWidgets={'OFF' if prefix_has_webengine else 'ON'}"
            )
            command.append(
                f"-DCMAKE_DISABLE_FIND_PACKAGE_Qt6WebSockets={'OFF' if prefix_has_websockets else 'ON'}"
            )
        command.append(f"-DTB_REQUIRE_QT_WEBENGINE={'ON' if require_we else 'OFF'}")
        return command

    def _clean_configure_state() -> None:
        try:
            (CPP_BUILD_ROOT / "CMakeCache.txt").unlink(missing_ok=True)
        except Exception:
            pass
        try:
            shutil.rmtree(CPP_BUILD_ROOT / "CMakeFiles", ignore_errors=True)
        except Exception:
            pass

    configure_cmd = _configure_cmd(require_webengine)
    ok, output = run_command_capture_hidden(configure_cmd, cwd=CPP_PROJECT_PATH)
    if not ok:
        _clean_configure_state()
        ok, output = run_command_capture_hidden(configure_cmd, cwd=CPP_PROJECT_PATH)

    if not ok and require_webengine and env_require_webengine is None:
        fallback_cmd = _configure_cmd(False)
        _clean_configure_state()
        ok, output = run_command_capture_hidden(fallback_cmd, cwd=CPP_PROJECT_PATH)
        if ok:
            try:
                window.log("C++ configure retry succeeded with Qt WebEngine disabled.")
            except Exception:
                pass
    if not ok:
        tail = "\n".join([line for line in output.splitlines() if line][-20:])
        return None, f"CMake configure failed.\n{tail}".strip()

    if sys.platform == "win32":
        build_commands: list[list[str]] = [
            ["cmake", "--build", str(CPP_BUILD_ROOT), "--config", "Release"],
            ["cmake", "--build", str(CPP_BUILD_ROOT), "--config", "Debug"],
        ]
    else:
        build_commands = [["cmake", "--build", str(CPP_BUILD_ROOT)]]

    last_output = ""
    for command in build_commands:
        ok, last_output = run_command_capture_hidden(command, cwd=CPP_PROJECT_PATH)
        if ok:
            break
    if not ok:
        tail = "\n".join([line for line in last_output.splitlines() if line][-20:])
        return None, f"CMake build failed.\n{tail}".strip()

    exe_path = find_cpp_code_tab_executable()
    if exe_path is None or not exe_path.is_file():
        return None, "Build completed but Trading-Bot-C++ executable was not found."
    return exe_path, None


def cpp_dependency_rows_for_launch(
    window,
    *,
    resolve_dependency_targets_for_config,
    collect_dependency_versions,
    reset_cpp_dependency_caches,
) -> list[dict[str, str]]:
    try:
        config_snapshot = dict(window.config or {})
    except Exception:
        config_snapshot = {}
    config_snapshot["code_language"] = CPP_CODE_LANGUAGE_KEY
    config_snapshot["selected_exchange"] = CPP_SUPPORTED_EXCHANGE_KEY

    try:
        targets = resolve_dependency_targets_for_config(config_snapshot)
    except Exception:
        targets = copy.deepcopy(_CPP_DEPENDENCY_VERSION_TARGETS)

    latest_from_ui: dict[str, str] = {}
    labels = getattr(window, "_dep_version_labels", None)
    if isinstance(labels, dict) and labels:
        for target in targets:
            label = str(target.get("label") or "").strip()
            if not label:
                continue
            widgets = labels.get(label)
            if not widgets or len(widgets) < 2:
                continue
            latest_widget = widgets[1]
            latest = str(latest_widget.text() or "").strip() or "Unknown"
            if latest.lower() not in {"checking...", "not checked"}:
                latest_from_ui[label] = latest

    reset_cpp_dependency_caches()

    try:
        resolved_versions = collect_dependency_versions(
            targets,
            include_latest=False,
            config=config_snapshot,
        )
    except Exception:
        resolved_versions = collect_dependency_versions(
            targets,
            include_latest=False,
            config=config_snapshot,
        )

    rows: list[dict[str, str]] = []
    for item in resolved_versions:
        if not item:
            continue
        label = str(item[0] or "").strip()
        if not label:
            continue
        installed = str(item[1] if len(item) > 1 else "Unknown").strip() or "Unknown"
        latest = str(latest_from_ui.get(label) or (item[2] if len(item) > 2 else "Unknown")).strip() or "Unknown"
        if latest.lower() in {"checking...", "not checked"}:
            latest = installed if installed.lower() != "not installed" else "Unknown"
        rows.append({"name": label, "installed": installed, "latest": latest})
    return rows
