from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets


def _poll_early_exit(proc: subprocess.Popen, timeout_s: float) -> int | None:
    deadline = time.time() + max(0.15, float(timeout_s))
    while time.time() < deadline:
        try:
            exit_code = proc.poll()
        except Exception:
            exit_code = 0
        if exit_code is not None:
            return exit_code
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
        time.sleep(0.05)
    return None


def launch_rust_from_code_tab(
    window,
    *,
    trigger: str = "code-tab",
    create_progress_dialog,
    hide_window_for_launch,
    restore_window,
    shutdown_after_handoff,
    update_progress,
    run_callable_with_ui_pump,
    build_rust_desktop_executable_for_code_tab,
    install_rust_toolchain,
    reset_rust_dependency_caches,
    refresh_code_language_card_release_labels,
    rust_toolchain_env,
    rust_framework_key,
    rust_framework_title,
    rust_missing_tool_labels,
    rust_auto_install_enabled,
    rust_auto_install_cooldown_seconds,
    format_windows_exit_code,
    tail_text,
) -> bool:
    existing = getattr(window, "_rust_code_tab_process", None)
    try:
        if existing is not None and existing.poll() is None:
            window.log("Rust bot is already running.")
            QtCore.QTimer.singleShot(0, lambda: shutdown_after_handoff(window))
            return True
    except Exception:
        pass

    progress_dialog = create_progress_dialog(window)
    hide_window_for_launch(window, progress_dialog)
    launch_succeeded = False

    def _progress(message: str) -> None:
        update_progress(progress_dialog, message)

    def _dismiss_progress_dialog() -> None:
        nonlocal progress_dialog
        try:
            if progress_dialog is not None:
                progress_dialog.close()
        except Exception:
            pass


def launch_cpp_from_code_tab(
    window,
    *,
    trigger: str = "code-tab",
    cpp_supported_exchange_key: str,
    cpp_dependency_version_targets,
    base_project_path: Path,
    create_progress_dialog,
    hide_window_for_launch,
    restore_window,
    shutdown_after_handoff,
    update_progress,
    run_callable_with_ui_pump,
    is_frozen_python_app,
    cpp_auto_setup_enabled,
    cpp_auto_prepare_environment_result,
    apply_cpp_auto_prepare_result,
    tail_text,
    find_cpp_code_tab_executable,
    cpp_runtime_is_cached_path,
    ensure_cached_cpp_bundle,
    reset_cpp_dependency_caches,
    cpp_executable_is_stale,
    build_cpp_executable_for_code_tab,
    discover_cpp_qt_bin_dirs_for_code_tab,
    prepare_cpp_launch_env,
    deploy_cpp_runtime_bundle,
    cpp_runtime_bundle_missing,
    cpp_dependency_rows_for_launch,
    format_windows_exit_code,
    refresh_code_language_card_release_labels,
) -> bool:
    if str(window.config.get("selected_exchange") or "") != cpp_supported_exchange_key:
        window.config["selected_exchange"] = cpp_supported_exchange_key
        window.log("C++ preview supports Binance only. Switched exchange to Binance.")
        try:
            window._refresh_code_tab_from_config()
        except Exception:
            pass

    existing = getattr(window, "_cpp_code_tab_process", None)
    try:
        if existing is not None and existing.poll() is None:
            window.log("C++ bot is already running.")
            QtCore.QTimer.singleShot(0, lambda: shutdown_after_handoff(window))
            return True
    except Exception:
        pass

    progress_dialog = create_progress_dialog(window)
    hide_window_for_launch(window, progress_dialog)
    launch_succeeded = False

    def _progress(message: str) -> None:
        update_progress(progress_dialog, message)

    def _dismiss_progress_dialog() -> None:
        nonlocal progress_dialog
        try:
            if progress_dialog is not None:
                progress_dialog.close()
        except Exception:
            pass
        progress_dialog = None

    try:
        if not is_frozen_python_app() and cpp_auto_setup_enabled():
            _progress("Ensuring pinned C++ dependencies...")
            prep_result = run_callable_with_ui_pump(
                cpp_auto_prepare_environment_result,
                reason=f"launch:{trigger}",
                targets=cpp_dependency_version_targets,
                install_when_missing=True,
                poll_interval_s=0.05,
            )
            apply_cpp_auto_prepare_result(window, prep_result, refresh_versions=False)
            if isinstance(prep_result, dict) and not bool(prep_result.get("ready")):
                missing_after = prep_result.get("missing_after") if isinstance(prep_result.get("missing_after"), list) else []
                missing_text = ", ".join(str(item) for item in missing_after) if missing_after else "unknown"
                detail = str(prep_result.get("install_output") or "").strip()
                if detail:
                    detail = tail_text(detail, max_lines=10, max_chars=1200)
                    detail = f"\n\nInstaller output tail:\n{detail}"
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.warning(
                    window,
                    "C++ dependency setup failed",
                    f"Automatic C++ setup could not provision all required environment dependencies.\n\nMissing: {missing_text}{detail}",
                )
                return False

        _progress("Resolving C++ executable...")
        exe_path = find_cpp_code_tab_executable()
        auto_runtime_error = ""
        runtime_bundle_touched = False
        if is_frozen_python_app() and (exe_path is None or cpp_runtime_is_cached_path(exe_path)):
            if exe_path is None:
                _progress("C++ runtime not found. Downloading release bundle...")
                log_message = "C++ runtime not found locally. Downloading Trading-Bot-C++.zip..."
            else:
                _progress("Checking C++ runtime updates...")
                log_message = "Checking C++ runtime cache for newer release..."
            try:
                window.log(log_message)
            except Exception:
                pass
            try:
                cached_exe, cached_err = run_callable_with_ui_pump(
                    ensure_cached_cpp_bundle,
                    force_download=False,
                    poll_interval_s=0.05,
                )
            except Exception as exc:
                cached_exe, cached_err = None, str(exc)
            if cached_exe is not None and cached_exe.is_file():
                exe_path = cached_exe
                runtime_bundle_touched = True
                reset_cpp_dependency_caches()
                try:
                    window.log(f"C++ runtime prepared from cache: {cached_exe.parent}")
                except Exception:
                    pass
            elif cached_err:
                auto_runtime_error = str(cached_err)
                try:
                    window.log(f"C++ auto-download failed: {auto_runtime_error}")
                except Exception:
                    pass
        stale_fallback = exe_path if exe_path is not None and exe_path.is_file() else None
        if exe_path is None or cpp_executable_is_stale(exe_path):
            if exe_path is None:
                window.log("C++ executable not found. Attempting to build it now...")
            else:
                window.log("C++ executable is outdated. Rebuilding to apply latest C++ UI changes...")
            _progress("Compiling C++ bot (this may take a while)...")
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                exe_path, error = build_cpp_executable_for_code_tab(window)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            if exe_path is None:
                detail = error or "Automatic C++ build failed."
                if auto_runtime_error:
                    detail = f"{detail}\nAuto-download failed: {auto_runtime_error}"
                if stale_fallback is not None and stale_fallback.is_file():
                    exe_path = stale_fallback
                    window.log(f"C++ rebuild failed, launching existing executable: {detail}")
                else:
                    window.log(f"C++ launch failed: {detail}")
                    install_hint = "Install Qt + CMake and try again."
                    if is_frozen_python_app():
                        install_hint = (
                            "Automatic C++ runtime download failed. "
                            "Extract Trading-Bot-C++.zip from this release next to Trading-Bot-Python.exe."
                        )
                    _dismiss_progress_dialog()
                    restore_window(window)
                    QtWidgets.QMessageBox.warning(
                        window,
                        "C++ launch failed",
                        f"Could not start the C++ bot.\n\n{detail}\n\n{install_hint}",
                    )
                    return False
            elif stale_fallback is not None and stale_fallback != exe_path:
                try:
                    window.log(f"C++ executable refreshed: {stale_fallback} -> {exe_path}")
                except Exception:
                    pass

        _progress("Preparing Qt runtime...")
        qt_bins = discover_cpp_qt_bin_dirs_for_code_tab()
        env = prepare_cpp_launch_env(exe_path, qt_bins, os.environ.copy())
        env["TB_CPP_EXE_DIR"] = str(exe_path.parent)
        env["TB_CPP_EXE_PATH"] = str(exe_path)
        env["TB_PROJECT_ROOT"] = str(base_project_path)
        if is_frozen_python_app():
            env["TB_PY_FROZEN_EXE"] = str(Path(sys.executable).resolve())
        else:
            source_entry = (base_project_path / "Languages" / "Python" / "main.py").resolve()
            if source_entry.is_file():
                env["TB_PY_SOURCE_SCRIPT"] = str(source_entry)
                env["TB_PY_SOURCE_WORKDIR"] = str(source_entry.parent)
            env["TB_PY_SOURCE_PYTHON"] = str(Path(sys.executable).resolve())

        if not is_frozen_python_app():
            deploy_ok, deploy_output = deploy_cpp_runtime_bundle(exe_path, qt_bins=qt_bins, force=False)
            if not deploy_ok:
                try:
                    window.log(f"C++ runtime deploy warning: {deploy_output}")
                except Exception:
                    pass
        env = prepare_cpp_launch_env(exe_path, qt_bins, env)
        if sys.platform == "win32" and cpp_runtime_bundle_missing(exe_path):
            if is_frozen_python_app():
                _progress("C++ runtime incomplete. Fetching bundle...")
                try:
                    cached_exe, cached_err = run_callable_with_ui_pump(
                        ensure_cached_cpp_bundle,
                        force_download=False,
                        poll_interval_s=0.05,
                    )
                except Exception as exc:
                    cached_exe, cached_err = None, str(exc)
                if cached_exe is not None and cached_exe.is_file():
                    exe_path = cached_exe
                    runtime_bundle_touched = True
                    reset_cpp_dependency_caches()
                    qt_bins = discover_cpp_qt_bin_dirs_for_code_tab()
                    env = prepare_cpp_launch_env(exe_path, qt_bins, env)
                else:
                    hint = (
                        "Could not auto-repair C++ runtime from release. "
                        "Extract Trading-Bot-C++.zip next to Trading-Bot-Python.exe."
                    )
                    extra = f"\n\nAuto-repair error: {cached_err}" if cached_err else ""
                    _dismiss_progress_dialog()
                    restore_window(window)
                    QtWidgets.QMessageBox.warning(
                        window,
                        "C++ launch failed",
                        f"Qt runtime files for C++ are incomplete at:\n{exe_path.parent}\n\n{hint}{extra}",
                    )
                    return False
            else:
                hint = "Run windeployqt or install Qt + CMake and try again."
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.warning(
                    window,
                    "C++ launch failed",
                    f"Qt runtime files for C++ are incomplete at:\n{exe_path.parent}\n\n{hint}",
                )
                return False

        try:
            if is_frozen_python_app():
                reset_cpp_dependency_caches()
            dep_rows = cpp_dependency_rows_for_launch(window)
            if dep_rows:
                payload = json.dumps(dep_rows, ensure_ascii=False, separators=(",", ":"))
                if len(payload) <= 16000:
                    env["TB_CPP_ENV_VERSIONS_JSON"] = payload
        except Exception:
            pass

        popen_kwargs: dict[str, object] = {
            "cwd": str(exe_path.parent),
            "env": env,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = 0
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 1
                popen_kwargs["startupinfo"] = startupinfo
            except Exception:
                pass

        def _spawn_cpp() -> subprocess.Popen:
            return subprocess.Popen([str(exe_path)], **popen_kwargs)

        _progress("Launching C++ bot...")
        try:
            process = _spawn_cpp()
        except Exception as exc:
            window.log(f"C++ launch failed: {exc}")
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(window, "C++ launch failed", str(exc))
            return False

        early_exit = _poll_early_exit(process, timeout_s=0.45)
        if early_exit is not None:
            exit_code = process.returncode
            window.log(f"C++ launch failed: process exited immediately (code {exit_code}).")

            retry_succeeded = False
            retry_reason = ""
            if sys.platform == "win32":
                _progress("C++ exited immediately. Repairing Qt runtime and retrying...")
                redeploy_ok, redeploy_output = deploy_cpp_runtime_bundle(exe_path, qt_bins=qt_bins, force=True)
                if not redeploy_ok:
                    retry_reason = str(redeploy_output or "windeployqt failed")
                else:
                    try:
                        retry_process = _spawn_cpp()
                        retry_exit = _poll_early_exit(retry_process, timeout_s=0.45)
                        if retry_exit is None:
                            process = retry_process
                            retry_succeeded = True
                    except Exception as exc:
                        retry_reason = str(exc)

            if not retry_succeeded and not is_frozen_python_app():
                _progress("Rebuilding C++ bot with current Qt settings and retrying...")
                rebuild_err = ""
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
                try:
                    rebuilt_exe, rebuild_err = build_cpp_executable_for_code_tab(window)
                finally:
                    QtWidgets.QApplication.restoreOverrideCursor()
                if rebuilt_exe is not None and rebuilt_exe.is_file():
                    exe_path = rebuilt_exe
                    qt_bins = discover_cpp_qt_bin_dirs_for_code_tab()
                    env = prepare_cpp_launch_env(exe_path, qt_bins, env)
                    popen_kwargs["cwd"] = str(exe_path.parent)
                    popen_kwargs["env"] = env
                    deploy_cpp_runtime_bundle(exe_path, qt_bins=qt_bins, force=True)
                    try:
                        rebuild_process = _spawn_cpp()
                        rebuild_exit = _poll_early_exit(rebuild_process, timeout_s=0.45)
                        if rebuild_exit is None:
                            process = rebuild_process
                            retry_succeeded = True
                    except Exception as exc:
                        retry_reason = str(exc)
                elif rebuild_err:
                    retry_reason = str(rebuild_err)
            elif not retry_succeeded and not retry_reason:
                retry_reason = (
                    "Packaged C++ app may be missing Qt runtime files after auto-repair. "
                    "Re-extract Trading-Bot-C++.zip next to Trading-Bot-Python.exe."
                )

            if retry_succeeded:
                window._cpp_code_tab_process = process
                try:
                    window._ensure_cpp_process_watchdog()
                except Exception:
                    pass
                window.log(f"Launched C++ bot ({trigger}): {exe_path}")
                if runtime_bundle_touched:
                    QtCore.QTimer.singleShot(0, lambda: refresh_code_language_card_release_labels(window))
                    QtCore.QTimer.singleShot(0, window._refresh_dependency_versions)
                QtCore.QTimer.singleShot(0, lambda: shutdown_after_handoff(window))
                launch_succeeded = True
                return True

            exit_text = format_windows_exit_code(exit_code)
            extra = ""
            if "0xC0000139" in exit_text:
                extra = "\nWindows status 0xC0000139 usually means Qt DLL mismatch."
            if retry_reason:
                extra = f"{extra}\nAuto-repair attempt failed: {retry_reason}".rstrip()
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(
                window,
                "C++ launch failed",
                f"C++ bot exited immediately (code {exit_text}).\n"
                "Check Qt runtime DLL availability and CMake/Qt configuration."
                f"{extra}",
            )
            return False

        window._cpp_code_tab_process = process
        try:
            window._ensure_cpp_process_watchdog()
        except Exception:
            pass
        window.log(f"Launched C++ bot ({trigger}): {exe_path}")
        if runtime_bundle_touched:
            QtCore.QTimer.singleShot(0, lambda: refresh_code_language_card_release_labels(window))
            QtCore.QTimer.singleShot(0, window._refresh_dependency_versions)
        QtCore.QTimer.singleShot(0, lambda: shutdown_after_handoff(window))
        launch_succeeded = True
        return True
    finally:
        if not launch_succeeded:
            restore_window(window)
        try:
            if progress_dialog is not None:
                progress_dialog.close()
        except Exception:
            pass
        progress_dialog = None

    try:
        framework_title = rust_framework_title(window.config)
        missing_tools = rust_missing_tool_labels()
        toolchain_installed = False
        if missing_tools:
            if not rust_auto_install_enabled():
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.warning(
                    window,
                    "Rust launch failed",
                    "Rust desktop launch requires rustup/cargo/rustc, and automatic installation is disabled.",
                )
                return False

            if getattr(window, "_rust_auto_install_inflight", False):
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.information(
                    window,
                    "Rust installation in progress",
                    "Rust toolchain installation is already running. Please wait for it to finish.",
                )
                return False

            now = time.time()
            cooldown_sec = rust_auto_install_cooldown_seconds()
            last_attempt = float(getattr(window, "_rust_auto_install_last_attempt_at", 0.0) or 0.0)
            if cooldown_sec > 0.0 and now - last_attempt < cooldown_sec:
                remaining = int(max(1.0, math.ceil(cooldown_sec - (now - last_attempt))))
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.warning(
                    window,
                    "Rust launch failed",
                    f"Rust toolchain installation was attempted recently. Try again in about {remaining} seconds.",
                )
                return False

            window._rust_auto_install_inflight = True
            window._rust_auto_install_last_attempt_at = now
            window.log(
                "Rust toolchain missing "
                f"({', '.join(missing_tools)}). Starting automatic rustup installation..."
            )
            _progress("Installing Rust toolchain...")
            try:
                install_ok, install_output = run_callable_with_ui_pump(
                    install_rust_toolchain,
                    poll_interval_s=0.05,
                )
            finally:
                window._rust_auto_install_inflight = False
                window._rust_auto_install_last_completed_at = time.time()
            toolchain_installed = bool(install_ok)
            reset_rust_dependency_caches()
            QtCore.QTimer.singleShot(0, lambda: refresh_code_language_card_release_labels(window))
            QtCore.QTimer.singleShot(0, window._refresh_dependency_versions)
            if not install_ok:
                window.log(f"Rust toolchain auto-install failed: {tail_text(install_output, max_lines=12, max_chars=1800)}")
                _dismiss_progress_dialog()
                restore_window(window)
                QtWidgets.QMessageBox.warning(
                    window,
                    "Rust launch failed",
                    (
                        "Automatic Rust installation failed.\n\n"
                        f"{tail_text(install_output, max_lines=20, max_chars=3000) or 'rustup did not complete.'}"
                    ),
                )
                return False
            window.log("Rust toolchain auto-install completed.")

        build_config = dict(window.config or {})
        _progress(f"Building Rust {framework_title} app...")
        exe_path, build_error = run_callable_with_ui_pump(
            build_rust_desktop_executable_for_code_tab,
            build_config,
            poll_interval_s=0.05,
        )
        if exe_path is None or not exe_path.is_file():
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(
                window,
                "Rust launch failed",
                build_error or f"Cargo build did not produce a runnable {framework_title} executable.",
            )
            return False

        env = rust_toolchain_env()
        env["TB_RUST_SELECTED_FRAMEWORK"] = rust_framework_key(build_config)
        env["TB_RUST_FRAMEWORK_TITLE"] = framework_title

        popen_kwargs: dict[str, object] = {
            "cwd": str(exe_path.parent),
            "env": env,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = 0
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 1
                popen_kwargs["startupinfo"] = startupinfo
            except Exception:
                pass

        _progress(f"Launching Rust {framework_title} bot...")
        try:
            process = subprocess.Popen([str(exe_path)], **popen_kwargs)
        except Exception as exc:
            window.log(f"Rust launch failed: {exc}")
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(window, "Rust launch failed", str(exc))
            return False

        early_exit = _poll_early_exit(process, timeout_s=0.6)
        if early_exit is not None:
            exit_text = format_windows_exit_code(process.returncode)
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(
                window,
                "Rust launch failed",
                (
                    f"Rust {framework_title} bot exited immediately (code {exit_text}).\n"
                    "Check the cargo build output and desktop framework prerequisites."
                ),
            )
            return False

        window._rust_code_tab_process = process
        try:
            window._ensure_rust_process_watchdog()
        except Exception:
            pass
        window.log(f"Launched Rust bot ({framework_title}, {trigger}): {exe_path}")
        if toolchain_installed:
            QtCore.QTimer.singleShot(0, lambda: refresh_code_language_card_release_labels(window))
            QtCore.QTimer.singleShot(0, window._refresh_dependency_versions)
        QtCore.QTimer.singleShot(0, lambda: shutdown_after_handoff(window))
        launch_succeeded = True
        return True
    finally:
        if not launch_succeeded:
            restore_window(window)
        try:
            if progress_dialog is not None:
                progress_dialog.close()
        except Exception:
            pass
