from __future__ import annotations

import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.gui import (
    code_language_build,
    code_language_launch,
    code_language_launcher,
    code_language_runtime,
    code_language_status,
    dependency_versions_runtime,
    dependency_versions_ui,
)
from app.gui.code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    CPP_SUPPORTED_EXCHANGE_KEY,
    _rust_framework_key,
    _rust_framework_title,
)

_LanguageSwitchSplash = code_language_launch.LanguageSwitchSplash


def _is_frozen_python_app() -> bool:
    return code_language_runtime.is_frozen_python_app()


def _python_runtime_release_tag() -> str | None:
    return code_language_runtime.python_runtime_release_tag()


def _cpp_runtime_release_snapshot() -> tuple[str | None, str]:
    return code_language_runtime.cpp_runtime_release_snapshot()


def _python_runtime_release_line() -> str:
    return code_language_runtime.python_runtime_release_line()


def _cpp_runtime_release_line() -> str:
    return code_language_runtime.cpp_runtime_release_line()


def _rust_runtime_release_line(config: dict | None = None) -> str:
    return code_language_status.rust_runtime_release_line(
        config,
        rust_project_version=dependency_versions_runtime._rust_project_version,
        rust_tool_version=dependency_versions_runtime._rust_tool_version,
        rust_framework_title=_rust_framework_title,
        rust_framework_key=_rust_framework_key,
        rust_manifest_path=dependency_versions_runtime._rust_manifest_path,
    )


def _refresh_code_language_card_release_labels(self) -> None:
    return code_language_status.refresh_code_language_card_release_labels(
        self,
        rust_release_line=_rust_runtime_release_line(getattr(self, "config", None)),
    )


def _cpp_runtime_is_cached_path(exe_path: Path | None) -> bool:
    return code_language_runtime.cpp_runtime_is_cached_path(exe_path)


def _reset_cpp_dependency_caches() -> None:
    dependency_versions_runtime._reset_cpp_dependency_caches()


def _cpp_packaged_runtime_exe() -> Path | None:
    return code_language_runtime.cpp_packaged_runtime_exe()


def _cpp_packaged_installed_value(target: dict[str, str]) -> str | None:
    return code_language_runtime.cpp_packaged_installed_value(target)


def _ensure_cached_cpp_bundle(force_download: bool = False) -> tuple[Path | None, str | None]:
    return code_language_runtime.ensure_cached_cpp_bundle(force_download=force_download)


def _find_cpp_code_tab_executable() -> Path | None:
    return code_language_runtime.find_cpp_code_tab_executable()


def _cpp_executable_is_stale(exe_path: Path | None) -> bool:
    return code_language_runtime.cpp_executable_is_stale(exe_path)


def _read_cmake_cache_value(cache_file: Path, key: str) -> str | None:
    return code_language_runtime.read_cmake_cache_value(cache_file, key)


def _qt_prefix_has_webengine(path_value: str | Path | None) -> bool:
    return code_language_runtime.qt_prefix_has_webengine(path_value)


def _qt_prefix_has_websockets(path_value: str | Path | None) -> bool:
    return code_language_runtime.qt_prefix_has_websockets(path_value)


def _resolve_cpp_qt_prefix_for_code_tab() -> str | None:
    return code_language_runtime.resolve_cpp_qt_prefix_for_code_tab()


def _discover_cpp_qt_bin_dirs_for_code_tab() -> list[Path]:
    return code_language_runtime.discover_cpp_qt_bin_dirs_for_code_tab()


def _create_cpp_launch_progress_dialog(parent: QtWidgets.QWidget | None) -> _LanguageSwitchSplash | None:
    return code_language_launch.create_launch_progress_dialog("Preparing C++ bot...", parent)


def _detach_cpp_launch_progress_dialog(dialog: _LanguageSwitchSplash | None) -> None:
    return code_language_launch.detach_launch_progress_dialog(dialog)


def _hide_python_window_for_cpp_launch(self, progress_dialog: _LanguageSwitchSplash | None) -> bool:
    return code_language_launch.hide_window_for_handoff(
        self,
        progress_dialog,
        active_attr="_cpp_launch_handoff_active",
        hidden_attr="_cpp_window_hidden_for_cpp_handoff",
    )


def _restore_python_window_after_cpp_launch(self) -> None:
    return code_language_launch.restore_window_after_handoff(
        self,
        hidden_attr="_cpp_window_hidden_for_cpp_handoff",
    )


def _shutdown_python_after_cpp_launch(self) -> None:
    return code_language_launch.shutdown_python_after_handoff(
        self,
        hidden_attr="_cpp_window_hidden_for_cpp_handoff",
    )


def _update_cpp_launch_progress(dialog: _LanguageSwitchSplash | None, text: str) -> None:
    return code_language_launch.update_launch_progress(dialog, text)


def _is_qt_runtime_path(path_value: str | None) -> bool:
    return code_language_launch.is_qt_runtime_path(path_value)


def _compose_cpp_launch_path(qt_bins: list[Path], base_path: str | None) -> str:
    return code_language_launch.compose_cpp_launch_path(qt_bins, base_path)


def _find_windeployqt_for_cpp(qt_bins: list[Path] | None = None) -> Path | None:
    return code_language_launch.find_windeployqt_for_cpp(qt_bins)


def _cpp_runtime_stamp_path(exe_path: Path) -> Path:
    return code_language_launch.cpp_runtime_stamp_path(exe_path)


def _cpp_runtime_bundle_missing(exe_path: Path) -> bool:
    return code_language_launch.cpp_runtime_bundle_missing(exe_path)


def _prepare_cpp_launch_env(
    exe_path: Path,
    qt_bins: list[Path],
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    return code_language_launch.prepare_cpp_launch_env(exe_path, qt_bins, base_env)


def _deploy_cpp_runtime_bundle(
    exe_path: Path,
    *,
    qt_bins: list[Path] | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    return code_language_launch.deploy_cpp_runtime_bundle(exe_path, qt_bins=qt_bins, force=force)


def _format_windows_exit_code(returncode: int | None) -> str:
    return code_language_launch.format_windows_exit_code(returncode)


def _run_command_capture_hidden(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    return code_language_launch.run_command_capture_hidden(command, cwd=cwd, env=env)


def _run_callable_with_ui_pump(
    fn,
    *args,
    poll_interval_s: float = 0.05,
    **kwargs,
):
    return code_language_launch.run_callable_with_ui_pump(
        fn,
        *args,
        poll_interval_s=poll_interval_s,
        **kwargs,
    )


def _create_rust_launch_progress_dialog(parent: QtWidgets.QWidget | None) -> _LanguageSwitchSplash | None:
    return code_language_launch.create_launch_progress_dialog("Preparing Rust bot...", parent)


def _hide_python_window_for_rust_launch(self, progress_dialog: _LanguageSwitchSplash | None) -> bool:
    return code_language_launch.hide_window_for_handoff(
        self,
        progress_dialog,
        active_attr="_rust_launch_handoff_active",
        hidden_attr="_rust_window_hidden_for_rust_handoff",
    )


def _restore_python_window_after_rust_launch(self) -> None:
    return code_language_launch.restore_window_after_handoff(
        self,
        hidden_attr="_rust_window_hidden_for_rust_handoff",
    )


def _shutdown_python_after_rust_launch(self) -> None:
    return code_language_launch.shutdown_python_after_handoff(
        self,
        hidden_attr="_rust_window_hidden_for_rust_handoff",
    )


def _rust_framework_package_name(config: dict | None = None) -> str:
    return code_language_build.rust_framework_package_name(
        config,
        rust_framework_key=_rust_framework_key,
    )


def _build_rust_desktop_executable_for_code_tab(config: dict | None = None) -> tuple[Path | None, str | None]:
    return code_language_build.build_rust_desktop_executable_for_code_tab(
        config,
        rust_framework_key=_rust_framework_key,
        rust_framework_title=_rust_framework_title,
        rust_tool_path=dependency_versions_runtime._rust_tool_path,
        run_command_capture_hidden=_run_command_capture_hidden,
        rust_toolchain_env=dependency_versions_runtime._rust_toolchain_env,
        tail_text=dependency_versions_runtime._tail_text,
    )


def _launch_rust_from_code_tab(self, *, trigger: str = "code-tab") -> bool:
    return code_language_launcher.launch_rust_from_code_tab(
        self,
        trigger=trigger,
        create_progress_dialog=_create_rust_launch_progress_dialog,
        hide_window_for_launch=_hide_python_window_for_rust_launch,
        restore_window=_restore_python_window_after_rust_launch,
        shutdown_after_handoff=_shutdown_python_after_rust_launch,
        update_progress=_update_cpp_launch_progress,
        run_callable_with_ui_pump=_run_callable_with_ui_pump,
        build_rust_desktop_executable_for_code_tab=_build_rust_desktop_executable_for_code_tab,
        install_rust_toolchain=dependency_versions_runtime._install_rust_toolchain,
        reset_rust_dependency_caches=dependency_versions_runtime._reset_rust_dependency_caches,
        refresh_code_language_card_release_labels=_refresh_code_language_card_release_labels,
        rust_toolchain_env=dependency_versions_runtime._rust_toolchain_env,
        rust_framework_key=_rust_framework_key,
        rust_framework_title=_rust_framework_title,
        rust_missing_tool_labels=dependency_versions_runtime._rust_missing_tool_labels,
        rust_auto_install_enabled=dependency_versions_runtime._rust_auto_install_enabled,
        rust_auto_install_cooldown_seconds=dependency_versions_runtime._rust_auto_install_cooldown_seconds,
        format_windows_exit_code=_format_windows_exit_code,
        tail_text=dependency_versions_runtime._tail_text,
    )


def _build_cpp_executable_for_code_tab(self) -> tuple[Path | None, str | None]:
    return code_language_build.build_cpp_executable_for_code_tab(
        self,
        is_frozen_python_app=_is_frozen_python_app,
        resolve_cpp_qt_prefix_for_code_tab=_resolve_cpp_qt_prefix_for_code_tab,
        qt_prefix_has_webengine=_qt_prefix_has_webengine,
        qt_prefix_has_websockets=_qt_prefix_has_websockets,
        cpp_qt_webengine_available=dependency_versions_runtime._cpp_qt_webengine_available,
        run_command_capture_hidden=_run_command_capture_hidden,
        find_cpp_code_tab_executable=_find_cpp_code_tab_executable,
    )


def _cpp_dependency_rows_for_launch(self) -> list[dict[str, str]]:
    return code_language_build.cpp_dependency_rows_for_launch(
        self,
        resolve_dependency_targets_for_config=dependency_versions_runtime._resolve_dependency_targets_for_config,
        collect_dependency_versions=dependency_versions_runtime._collect_dependency_versions,
        reset_cpp_dependency_caches=_reset_cpp_dependency_caches,
    )


def _launch_cpp_from_code_tab(self, *, trigger: str = "code-tab") -> bool:
    return code_language_launcher.launch_cpp_from_code_tab(
        self,
        trigger=trigger,
        cpp_supported_exchange_key=CPP_SUPPORTED_EXCHANGE_KEY,
        cpp_dependency_version_targets=_CPP_DEPENDENCY_VERSION_TARGETS,
        base_project_path=_BASE_PROJECT_PATH,
        create_progress_dialog=_create_cpp_launch_progress_dialog,
        hide_window_for_launch=_hide_python_window_for_cpp_launch,
        restore_window=_restore_python_window_after_cpp_launch,
        shutdown_after_handoff=_shutdown_python_after_cpp_launch,
        update_progress=_update_cpp_launch_progress,
        run_callable_with_ui_pump=_run_callable_with_ui_pump,
        is_frozen_python_app=_is_frozen_python_app,
        cpp_auto_setup_enabled=dependency_versions_runtime._cpp_auto_setup_enabled,
        cpp_auto_prepare_environment_result=dependency_versions_runtime._cpp_auto_prepare_environment_result,
        apply_cpp_auto_prepare_result=dependency_versions_runtime._apply_cpp_auto_prepare_result,
        tail_text=dependency_versions_runtime._tail_text,
        find_cpp_code_tab_executable=_find_cpp_code_tab_executable,
        cpp_runtime_is_cached_path=_cpp_runtime_is_cached_path,
        ensure_cached_cpp_bundle=_ensure_cached_cpp_bundle,
        reset_cpp_dependency_caches=_reset_cpp_dependency_caches,
        cpp_executable_is_stale=_cpp_executable_is_stale,
        build_cpp_executable_for_code_tab=_build_cpp_executable_for_code_tab,
        discover_cpp_qt_bin_dirs_for_code_tab=_discover_cpp_qt_bin_dirs_for_code_tab,
        prepare_cpp_launch_env=_prepare_cpp_launch_env,
        deploy_cpp_runtime_bundle=_deploy_cpp_runtime_bundle,
        cpp_runtime_bundle_missing=_cpp_runtime_bundle_missing,
        cpp_dependency_rows_for_launch=_cpp_dependency_rows_for_launch,
        format_windows_exit_code=_format_windows_exit_code,
        refresh_code_language_card_release_labels=_refresh_code_language_card_release_labels,
    )


def _start_dependency_usage_auto_poll(self) -> None:
    return dependency_versions_ui.start_dependency_usage_auto_poll(
        self,
        interval_ms=dependency_versions_runtime._DEPENDENCY_USAGE_POLL_INTERVAL_MS,
    )


def _stop_dependency_usage_auto_poll(self) -> None:
    return dependency_versions_ui.stop_dependency_usage_auto_poll(self)


def _poll_dependency_usage_states(self) -> None:
    return dependency_versions_ui.poll_dependency_usage_states(
        self,
        refresh_dependency_usage_labels=dependency_versions_runtime._refresh_dependency_usage_labels,
    )


def _rebuild_dependency_version_rows(self, targets: list[dict[str, str]] | None = None) -> None:
    return dependency_versions_ui.rebuild_dependency_version_rows(
        self,
        targets,
        make_dependency_cell_copyable=dependency_versions_runtime._make_dependency_cell_copyable,
        set_dependency_usage_widget=dependency_versions_runtime._set_dependency_usage_widget,
        set_dependency_usage_counter_widget=dependency_versions_runtime._set_dependency_usage_counter_widget,
        refresh_dependency_usage_labels=dependency_versions_runtime._refresh_dependency_usage_labels,
    )


def _refresh_dependency_versions(self) -> None:
    return dependency_versions_ui.refresh_dependency_versions(
        self,
        resolve_dependency_targets_for_config=dependency_versions_runtime._resolve_dependency_targets_for_config,
        dependency_targets_fallback=dependency_versions_runtime.DEPENDENCY_VERSION_TARGETS,
        collect_dependency_versions=dependency_versions_runtime._collect_dependency_versions,
        apply_dependency_usage_entry=dependency_versions_runtime._apply_dependency_usage_entry,
        maybe_auto_prepare_cpp_environment=dependency_versions_runtime._maybe_auto_prepare_cpp_environment,
        dependency_usage_state=dependency_versions_runtime._dependency_usage_state,
        normalize_dependency_usage_text=dependency_versions_runtime._normalize_dependency_usage_text,
    )


@QtCore.pyqtSlot(object)
def _apply_dependency_version_results(self, results: list) -> None:
    """
    Apply the fetched dependency version results to the UI.
    This method is designed to be called via QMetaObject.invokeMethod from a background thread.
    """
    return dependency_versions_ui.apply_dependency_version_results(
        self,
        results,
        apply_dependency_usage_entry=dependency_versions_runtime._apply_dependency_usage_entry,
    )


@QtCore.pyqtSlot(object)
def _on_cpp_auto_prepare_finished(self, result: dict | None) -> None:
    self._cpp_auto_setup_inflight = False
    self._cpp_auto_setup_last_completed_at = time.time()
    dependency_versions_runtime._apply_cpp_auto_prepare_result(self, result, refresh_versions=True)


def bind_main_window_code_runtime(main_window_cls) -> None:
    main_window_cls._is_frozen_python_app = _is_frozen_python_app
    main_window_cls._python_runtime_release_tag = _python_runtime_release_tag
    main_window_cls._cpp_runtime_release_snapshot = _cpp_runtime_release_snapshot
    main_window_cls._python_runtime_release_line = _python_runtime_release_line
    main_window_cls._cpp_runtime_release_line = _cpp_runtime_release_line
    main_window_cls._rust_runtime_release_line = _rust_runtime_release_line
    main_window_cls._refresh_code_language_card_release_labels = _refresh_code_language_card_release_labels
    main_window_cls._cpp_runtime_is_cached_path = _cpp_runtime_is_cached_path
    main_window_cls._reset_cpp_dependency_caches = _reset_cpp_dependency_caches
    main_window_cls._cpp_packaged_runtime_exe = _cpp_packaged_runtime_exe
    main_window_cls._cpp_packaged_installed_value = _cpp_packaged_installed_value
    main_window_cls._ensure_cached_cpp_bundle = _ensure_cached_cpp_bundle
    main_window_cls._find_cpp_code_tab_executable = _find_cpp_code_tab_executable
    main_window_cls._cpp_executable_is_stale = _cpp_executable_is_stale
    main_window_cls._read_cmake_cache_value = _read_cmake_cache_value
    main_window_cls._qt_prefix_has_webengine = _qt_prefix_has_webengine
    main_window_cls._qt_prefix_has_websockets = _qt_prefix_has_websockets
    main_window_cls._resolve_cpp_qt_prefix_for_code_tab = _resolve_cpp_qt_prefix_for_code_tab
    main_window_cls._discover_cpp_qt_bin_dirs_for_code_tab = _discover_cpp_qt_bin_dirs_for_code_tab
    main_window_cls._create_cpp_launch_progress_dialog = _create_cpp_launch_progress_dialog
    main_window_cls._detach_cpp_launch_progress_dialog = _detach_cpp_launch_progress_dialog
    main_window_cls._hide_python_window_for_cpp_launch = _hide_python_window_for_cpp_launch
    main_window_cls._restore_python_window_after_cpp_launch = _restore_python_window_after_cpp_launch
    main_window_cls._shutdown_python_after_cpp_launch = _shutdown_python_after_cpp_launch
    main_window_cls._update_cpp_launch_progress = _update_cpp_launch_progress
    main_window_cls._is_qt_runtime_path = _is_qt_runtime_path
    main_window_cls._compose_cpp_launch_path = _compose_cpp_launch_path
    main_window_cls._find_windeployqt_for_cpp = _find_windeployqt_for_cpp
    main_window_cls._cpp_runtime_stamp_path = _cpp_runtime_stamp_path
    main_window_cls._cpp_runtime_bundle_missing = _cpp_runtime_bundle_missing
    main_window_cls._prepare_cpp_launch_env = _prepare_cpp_launch_env
    main_window_cls._deploy_cpp_runtime_bundle = _deploy_cpp_runtime_bundle
    main_window_cls._format_windows_exit_code = _format_windows_exit_code
    main_window_cls._run_command_capture_hidden = _run_command_capture_hidden
    main_window_cls._run_callable_with_ui_pump = _run_callable_with_ui_pump
    main_window_cls._create_rust_launch_progress_dialog = _create_rust_launch_progress_dialog
    main_window_cls._hide_python_window_for_rust_launch = _hide_python_window_for_rust_launch
    main_window_cls._restore_python_window_after_rust_launch = _restore_python_window_after_rust_launch
    main_window_cls._shutdown_python_after_rust_launch = _shutdown_python_after_rust_launch
    main_window_cls._rust_framework_package_name = _rust_framework_package_name
    main_window_cls._build_rust_desktop_executable_for_code_tab = _build_rust_desktop_executable_for_code_tab
    main_window_cls._launch_rust_from_code_tab = _launch_rust_from_code_tab
    main_window_cls._build_cpp_executable_for_code_tab = _build_cpp_executable_for_code_tab
    main_window_cls._cpp_dependency_rows_for_launch = _cpp_dependency_rows_for_launch
    main_window_cls._launch_cpp_from_code_tab = _launch_cpp_from_code_tab
    main_window_cls._start_dependency_usage_auto_poll = _start_dependency_usage_auto_poll
    main_window_cls._stop_dependency_usage_auto_poll = _stop_dependency_usage_auto_poll
    main_window_cls._poll_dependency_usage_states = _poll_dependency_usage_states
    main_window_cls._rebuild_dependency_version_rows = _rebuild_dependency_version_rows
    main_window_cls._refresh_dependency_versions = _refresh_dependency_versions
    main_window_cls._apply_dependency_version_results = _apply_dependency_version_results
    main_window_cls._maybe_auto_prepare_cpp_environment = dependency_versions_runtime._maybe_auto_prepare_cpp_environment
    main_window_cls._on_cpp_auto_prepare_finished = _on_cpp_auto_prepare_finished
