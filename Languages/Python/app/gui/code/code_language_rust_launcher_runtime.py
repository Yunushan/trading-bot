from __future__ import annotations

import math
import subprocess
import time

from PyQt6 import QtCore, QtWidgets

from .code_language_launcher_shared_runtime import apply_windows_startupinfo, poll_early_exit


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
        apply_windows_startupinfo(popen_kwargs)

        _progress(f"Launching Rust {framework_title} bot...")
        try:
            process = subprocess.Popen([str(exe_path)], **popen_kwargs)
        except Exception as exc:
            window.log(f"Rust launch failed: {exc}")
            _dismiss_progress_dialog()
            restore_window(window)
            QtWidgets.QMessageBox.warning(window, "Rust launch failed", str(exc))
            return False

        early_exit = poll_early_exit(process, timeout_s=0.6)
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
        progress_dialog = None


__all__ = ["launch_rust_from_code_tab"]
