from __future__ import annotations

import copy
import shutil
import threading
import time
from pathlib import Path
import sys

from PyQt6 import QtCore, QtWidgets

from .code_language_catalog import BASE_PROJECT_PATH, CPP_CODE_LANGUAGE_KEY, RUST_CODE_LANGUAGE_KEY, RUST_PROJECT_PATH


def _dependency_target_label(target: dict[str, str] | None) -> str:
    if not isinstance(target, dict):
        return ""
    return str(target.get("label") or "").strip()


def _selected_dependency_targets(self) -> list[dict[str, str]]:
    checkboxes = getattr(self, "_dep_version_checkboxes", None)
    targets = getattr(self, "_dep_version_targets", None)
    if not isinstance(checkboxes, dict) or not isinstance(targets, list):
        return []
    target_map = {
        _dependency_target_label(target): target
        for target in targets
        if _dependency_target_label(target)
    }
    selected: list[dict[str, str]] = []
    for label, checkbox in checkboxes.items():
        try:
            is_checked = bool(checkbox.isChecked())
        except Exception:
            is_checked = False
        if is_checked and label in target_map:
            selected.append(target_map[label])
    return selected


def update_dependency_action_buttons(self) -> None:
    targets = getattr(self, "_dep_version_targets", None)
    target_count = len(targets or []) if isinstance(targets, list) else 0
    selected_count = len(_selected_dependency_targets(self))
    refresh_inflight = bool(getattr(self, "_dep_version_refresh_inflight", False))
    update_inflight = bool(getattr(self, "_dep_version_update_inflight", False))
    busy = refresh_inflight or update_inflight
    update_scope = str(getattr(self, "_dep_version_update_scope", "") or "").strip().lower()
    status_text = str(getattr(self, "_dep_version_update_status_text", "") or "").strip()

    status_label = getattr(self, "_dependency_selection_status_label", None)
    if status_label is not None:
        if update_inflight:
            status_label.setText(status_text or "Updating dependencies...")
            status_label.setStyleSheet("color: #f59e0b; font-weight: 600;")
        elif refresh_inflight:
            status_label.setText("Checking versions...")
            status_label.setStyleSheet("color: #38bdf8; font-weight: 600;")
        elif target_count:
            status_label.setText(f"{selected_count} selected")
            status_label.setStyleSheet("color: #94a3b8; font-weight: 600;")
        else:
            status_label.setText("No dependencies")
            status_label.setStyleSheet("color: #94a3b8; font-weight: 600;")

    selected_btn = getattr(self, "_version_update_selected_btn", None)
    if selected_btn is not None:
        selected_btn.setText("Updating..." if update_inflight and update_scope == "selected" else "Update Selected")
        selected_btn.setEnabled((selected_count > 0) and not busy)

    all_btn = getattr(self, "_version_update_all_btn", None)
    if all_btn is not None:
        all_btn.setText("Updating..." if update_inflight and update_scope == "all" else "Update All")
        all_btn.setEnabled((target_count > 0) and not busy)

    refresh_btn = getattr(self, "_version_refresh_btn", None)
    if refresh_btn is not None:
        refresh_btn.setText("Checking..." if refresh_inflight and not update_inflight else "Check Versions")
        refresh_btn.setEnabled(not busy)

    checkboxes = getattr(self, "_dep_version_checkboxes", None)
    if isinstance(checkboxes, dict):
        for checkbox in checkboxes.values():
            try:
                checkbox.setEnabled(not busy)
            except Exception:
                pass


def _set_dependency_update_state(
    self,
    busy: bool,
    *,
    scope: str = "",
    status_text: str = "",
) -> None:
    self._dep_version_update_inflight = bool(busy)
    self._dep_version_update_scope = str(scope or "").strip().lower()
    self._dep_version_update_status_text = str(status_text or "").strip()
    update_dependency_action_buttons(self)


def _resolve_python_command_prefix(self) -> list[str] | None:
    frozen = False
    try:
        frozen = bool(self._is_frozen_python_app())
    except Exception:
        frozen = False

    candidates: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def _add(command: list[str] | None) -> None:
        if not command:
            return
        normalized = tuple(str(part or "").strip() for part in command if str(part or "").strip())
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(list(normalized))

    if not frozen:
        try:
            current_python = Path(sys.executable).resolve()
        except Exception:
            current_python = Path(sys.executable)
        if current_python.name.lower().startswith("python"):
            _add([str(current_python)])

    venv_root = BASE_PROJECT_PATH / ".venv"
    if sys.platform == "win32":
        _add([str(venv_root / "Scripts" / "python.exe")])
    else:
        _add([str(venv_root / "bin" / "python3")])
        _add([str(venv_root / "bin" / "python")])

    for executable in ("python", "python3"):
        found = shutil.which(executable)
        if found:
            try:
                _add([str(Path(found).resolve())])
            except Exception:
                _add([found])

    py_launcher = shutil.which("py") if sys.platform == "win32" else None
    if py_launcher:
        try:
            _add([str(Path(py_launcher).resolve()), "-3"])
        except Exception:
            _add([py_launcher, "-3"])

    for command in candidates:
        first = str(command[0] if command else "").strip()
        if not first:
            continue
        if Path(first).exists() or shutil.which(first):
            return command
    return None


def _trim_update_output(runtime, output: str) -> str:
    try:
        return str(runtime._tail_text(output, max_lines=20, max_chars=4000) or "").strip()
    except Exception:
        text = str(output or "").strip()
        if not text:
            return ""
        lines = [line for line in text.splitlines() if line][-20:]
        return "\n".join(lines)[-4000:].strip()


def _run_dependency_update_worker(
    self,
    *,
    targets: list[dict[str, str]],
    selected_only: bool,
) -> dict[str, object]:
    from . import dependency_versions_runtime as runtime

    language_key = str((getattr(self, "config", None) or {}).get("code_language") or "").strip()
    target_labels = [_dependency_target_label(target) for target in targets if _dependency_target_label(target)]
    all_targets = getattr(self, "_dep_version_targets", None)
    full_target_count = len(all_targets or []) if isinstance(all_targets, list) else len(targets)

    if language_key == CPP_CODE_LANGUAGE_KEY:
        command, cwd = runtime._cpp_dependency_installer_command()
        if not command or cwd is None:
            return {
                "ok": False,
                "title": "C++ dependency update failed",
                "message": "C++ dependency installer is not available on this system.",
                "refresh_versions": True,
            }
        ok, output = self._run_command_capture_hidden(command, cwd=cwd)
        runtime._reset_cpp_dependency_caches()
        detail = _trim_update_output(runtime, output)
        summary_lines = []
        if selected_only and len(targets) < full_target_count:
            summary_lines.append("Selected C++ updates currently run the shared installer for the full C++ toolchain.")
        summary_lines.append("C++ dependency installer completed." if ok else "C++ dependency installer failed.")
        if detail:
            summary_lines.append(detail)
        return {
            "ok": ok,
            "title": "C++ dependency update finished" if ok else "C++ dependency update failed",
            "message": "\n\n".join(line for line in summary_lines if line),
            "refresh_versions": True,
            "log_message": "; ".join(
                line
                for line in (
                    "C++ dependency update succeeded" if ok else "C++ dependency update failed",
                    ", ".join(target_labels) if target_labels else "",
                )
                if line
            ),
        }

    if language_key == RUST_CODE_LANGUAGE_KEY:
        needs_toolchain = any(str(target.get("custom") or "").strip().lower() in {"rust_rustc", "rust_cargo"} for target in targets)
        needs_workspace = any(str(target.get("custom") or "").strip().lower() == "rust_file_version" for target in targets)
        if not needs_toolchain and not needs_workspace:
            return {
                "ok": False,
                "title": "Rust dependency update failed",
                "message": "No Rust update targets were selected.",
                "refresh_versions": True,
            }

        step_messages: list[str] = []
        env = runtime._rust_toolchain_env()

        if needs_toolchain:
            rustup_path = runtime._rust_tool_path("rustup")
            if rustup_path is None:
                return {
                    "ok": False,
                    "title": "Rust dependency update failed",
                    "message": "rustup was not found. Install rustup before updating the Rust toolchain.",
                    "refresh_versions": True,
                }
            ok, output = self._run_command_capture_hidden([str(rustup_path), "update"], cwd=BASE_PROJECT_PATH, env=env)
            detail = _trim_update_output(runtime, output)
            step_messages.append("Rust toolchain refreshed." if ok else "Rust toolchain refresh failed.")
            if detail:
                step_messages.append(detail)
            if not ok:
                runtime._reset_rust_dependency_caches()
                return {
                    "ok": False,
                    "title": "Rust dependency update failed",
                    "message": "\n\n".join(step_messages),
                    "refresh_versions": True,
                    "log_message": "Rust dependency update failed during rustup update",
                }

        if needs_workspace:
            cargo_path = runtime._rust_tool_path("cargo")
            if cargo_path is None:
                return {
                    "ok": False,
                    "title": "Rust dependency update failed",
                    "message": "cargo was not found. Install the Rust toolchain before updating the workspace.",
                    "refresh_versions": True,
                }
            command = [str(cargo_path), "update", "--manifest-path", str(RUST_PROJECT_PATH / "Cargo.toml")]
            ok, output = self._run_command_capture_hidden(command, cwd=RUST_PROJECT_PATH, env=env)
            detail = _trim_update_output(runtime, output)
            step_messages.append("Rust workspace lockfile refreshed." if ok else "Rust workspace lockfile refresh failed.")
            if detail:
                step_messages.append(detail)
            if ok:
                step_messages.append(
                    "Workspace rows in this table show local Cargo.toml versions, so those version numbers may stay the same."
                )
            else:
                runtime._reset_rust_dependency_caches()
                return {
                    "ok": False,
                    "title": "Rust dependency update failed",
                    "message": "\n\n".join(step_messages),
                    "refresh_versions": True,
                    "log_message": "Rust dependency update failed during cargo update",
                }

        runtime._reset_rust_dependency_caches()
        return {
            "ok": True,
            "title": "Rust dependency update finished",
            "message": "\n\n".join(step_messages),
            "refresh_versions": True,
            "log_message": "; ".join(
                line
                for line in (
                    "Rust dependency update succeeded",
                    ", ".join(target_labels) if target_labels else "",
                )
                if line
            ),
        }

    packages: list[str] = []
    seen_packages: set[str] = set()
    for target in targets:
        custom = str(target.get("custom") or "").strip().lower()
        if custom:
            continue
        package_name = str(target.get("pypi") or target.get("package") or "").strip()
        if not package_name or package_name in seen_packages:
            continue
        seen_packages.add(package_name)
        packages.append(package_name)

    if not packages:
        return {
            "ok": False,
            "title": "Python dependency update failed",
            "message": "No Python packages were available to update.",
            "refresh_versions": True,
        }

    command_prefix = _resolve_python_command_prefix(self)
    if not command_prefix:
        return {
            "ok": False,
            "title": "Python dependency update failed",
            "message": "A usable Python interpreter was not found for package updates.",
            "refresh_versions": True,
        }

    command = [*command_prefix, "-m", "pip", "install", "--upgrade", *packages]
    ok, output = self._run_command_capture_hidden(command, cwd=BASE_PROJECT_PATH)
    detail = _trim_update_output(runtime, output)
    summary_lines = [
        f"Updated {len(packages)} Python package(s)." if ok else "Python package update failed.",
    ]
    if detail:
        summary_lines.append(detail)
    return {
        "ok": ok,
        "title": "Python dependency update finished" if ok else "Python dependency update failed",
        "message": "\n\n".join(summary_lines),
        "refresh_versions": True,
        "log_message": "; ".join(
            line
            for line in (
                "Python dependency update succeeded" if ok else "Python dependency update failed",
                ", ".join(target_labels) if target_labels else "",
            )
            if line
        ),
    }


def _start_dependency_update(self, *, selected_only: bool) -> None:
    if getattr(self, "_dep_version_update_inflight", False):
        return

    targets = _selected_dependency_targets(self) if selected_only else list(getattr(self, "_dep_version_targets", []) or [])
    if not targets:
        try:
            QtWidgets.QMessageBox.information(
                self,
                "No dependencies selected" if selected_only else "No dependencies available",
                (
                    "Select at least one dependency before using Update Selected."
                    if selected_only
                    else "There are no dependencies available to update for the current language section."
                ),
            )
        except Exception:
            pass
        return

    language_key = str((getattr(self, "config", None) or {}).get("code_language") or "").strip()
    language_title = "Rust" if language_key == RUST_CODE_LANGUAGE_KEY else "C++" if language_key == CPP_CODE_LANGUAGE_KEY else "Python"
    action_title = "selected dependencies" if selected_only else "all dependencies"
    status_text = f"Updating {language_title} {action_title}..."
    _set_dependency_update_state(
        self,
        True,
        scope="selected" if selected_only else "all",
        status_text=status_text,
    )
    try:
        self.log(status_text)
    except Exception:
        pass

    def _worker() -> None:
        result = _run_dependency_update_worker(self, targets=targets, selected_only=selected_only)
        try:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_apply_dependency_update_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(object, result),
            )
        except Exception:
            try:
                _set_dependency_update_state(self, False)
            except Exception:
                pass

    threading.Thread(target=_worker, name="dependency-update", daemon=True).start()


def update_selected_dependency_versions(self) -> None:
    return _start_dependency_update(self, selected_only=True)


def update_all_dependency_versions(self) -> None:
    return _start_dependency_update(self, selected_only=False)


def apply_dependency_update_finished(self, result: dict | None) -> None:
    payload = result if isinstance(result, dict) else {}
    _set_dependency_update_state(self, False)

    log_message = str(payload.get("log_message") or "").strip()
    if log_message:
        try:
            self.log(log_message)
        except Exception:
            pass

    title = str(payload.get("title") or "Dependency update finished").strip() or "Dependency update finished"
    message = str(payload.get("message") or "").strip() or "The dependency update finished."
    ok = bool(payload.get("ok"))

    try:
        if ok:
            QtWidgets.QMessageBox.information(self, title, message)
        else:
            QtWidgets.QMessageBox.warning(self, title, message)
    except Exception:
        pass

    if bool(payload.get("refresh_versions", True)):
        QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)


def start_dependency_usage_auto_poll(self, *, interval_ms: int) -> None:
    timer = getattr(self, "_dep_usage_poll_timer", None)
    if timer is None:
        try:
            timer = QtCore.QTimer(self)
            timer.setInterval(interval_ms)
            timer.timeout.connect(self._poll_dependency_usage_states)
            self._dep_usage_poll_timer = timer
        except Exception:
            return
    try:
        if not timer.isActive():
            timer.start()
    except Exception:
        pass
    self._poll_dependency_usage_states()


def stop_dependency_usage_auto_poll(self) -> None:
    timer = getattr(self, "_dep_usage_poll_timer", None)
    if timer is None:
        return
    try:
        timer.stop()
    except Exception:
        pass


def poll_dependency_usage_states(self, *, refresh_dependency_usage_labels) -> None:
    if not self._code_tab_visible():
        return
    refresh_dependency_usage_labels(self)


def rebuild_dependency_version_rows(
    self,
    targets: list[dict[str, str]] | None = None,
    *,
    make_dependency_cell_copyable,
    set_dependency_usage_widget,
    set_dependency_usage_counter_widget,
    refresh_dependency_usage_labels,
) -> None:
    layout = getattr(self, "_dep_versions_layout", None)
    container = getattr(self, "_dep_versions_container", None)
    scroll = getattr(self, "_dep_versions_scroll", None)
    group = getattr(self, "_dep_versions_group", None)
    target_list = targets or getattr(self, "_dep_version_targets", []) or []
    if layout is None or container is None or group is None:
        return

    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    row_label_style = "font-size: 11px; padding: 2px 4px 4px 4px;"
    row_value_style = "font-size: 11px; padding: 2px 4px 4px 4px;"
    row_usage_counter_style = "font-size: 11px; padding: 2px 4px 4px 4px; font-weight: 600;"

    header_select = QtWidgets.QLabel("Select")
    header_select.setStyleSheet("font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;")
    header_dep = QtWidgets.QLabel("Dependency")
    header_dep.setStyleSheet("font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;")
    header_inst = QtWidgets.QLabel("Installed")
    header_inst.setStyleSheet("font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;")
    header_latest = QtWidgets.QLabel("Latest")
    header_latest.setStyleSheet("font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;")
    header_usage = QtWidgets.QLabel("Usage")
    header_usage.setStyleSheet("font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;")
    header_usage_counter = QtWidgets.QLabel("Usage Change Counter")
    header_usage_counter.setStyleSheet(
        "font-weight: 600; font-size: 12px; padding-bottom: 6px; border-bottom: 1px solid #334155;"
    )
    layout.addWidget(header_select, 0, 0)
    layout.addWidget(header_dep, 0, 1)
    layout.addWidget(header_inst, 0, 2)
    layout.addWidget(header_latest, 0, 3)
    layout.addWidget(header_usage, 0, 4)
    layout.addWidget(header_usage_counter, 0, 5)

    labels: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel]] = {}
    checkboxes: dict[str, QtWidgets.QCheckBox] = {}
    count_map = getattr(self, "_dep_usage_change_counts", None)
    if not isinstance(count_map, dict):
        count_map = {}
        self._dep_usage_change_counts = count_map

    for row, target in enumerate(target_list, start=1):
        grid_row = row * 2 - 1
        select_widget = QtWidgets.QCheckBox()
        select_widget.setChecked(False)
        select_widget.stateChanged.connect(lambda _state, window=self: update_dependency_action_buttons(window))
        select_widget.setStyleSheet("padding-bottom: 4px;")

        label_widget = QtWidgets.QLabel(target["label"])
        label_widget.setStyleSheet(f"font-weight: 600; {row_label_style}")
        label_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(label_widget)

        installed_widget = QtWidgets.QLabel("Not checked")
        installed_widget.setStyleSheet(row_value_style)
        installed_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(installed_widget)

        latest_widget = QtWidgets.QLabel("Not checked")
        latest_widget.setStyleSheet(row_value_style)
        latest_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(latest_widget)

        usage_widget = QtWidgets.QLabel()
        usage_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(usage_widget)
        set_dependency_usage_widget(usage_widget, "On demand")
        current_usage_style = str(usage_widget.styleSheet() or "").strip()
        usage_widget.setStyleSheet(f"{current_usage_style} padding: 2px 4px 4px 4px;")

        usage_counter_widget = QtWidgets.QLabel()
        usage_counter_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(usage_counter_widget)
        set_dependency_usage_counter_widget(usage_counter_widget, count_map.get(target["label"], 0))
        usage_counter_widget.setStyleSheet(row_usage_counter_style)

        layout.addWidget(select_widget, grid_row, 0, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label_widget, grid_row, 1)
        layout.addWidget(installed_widget, grid_row, 2)
        layout.addWidget(latest_widget, grid_row, 3)
        layout.addWidget(usage_widget, grid_row, 4)
        layout.addWidget(usage_counter_widget, grid_row, 5)
        labels[target["label"]] = (installed_widget, latest_widget, usage_widget, usage_counter_widget)
        checkboxes[target["label"]] = select_widget

        separator = QtWidgets.QFrame(container)
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        separator.setStyleSheet("color: #111827; background: #111827; min-height: 1px; max-height: 1px;")
        layout.addWidget(separator, grid_row + 1, 0, 1, 7)

    self._dep_version_labels = labels
    self._dep_version_checkboxes = checkboxes
    self._dep_version_targets = list(target_list)
    tracked_labels = {str(target.get("label") or "").strip() for target in target_list}
    try:
        state_map = getattr(self, "_dep_usage_last_state", None)
        if isinstance(state_map, dict):
            for key in list(state_map.keys()):
                if key not in tracked_labels:
                    state_map.pop(key, None)
    except Exception:
        pass
    try:
        count_map_local = getattr(self, "_dep_usage_change_counts", None)
        if isinstance(count_map_local, dict):
            for key in list(count_map_local.keys()):
                if key not in tracked_labels:
                    count_map_local.pop(key, None)
    except Exception:
        pass
    refresh_dependency_usage_labels(self, target_list)

    rows = (len(target_list) * 2) + 1
    try:
        fm = container.fontMetrics()
        row_height = max(30, fm.height() + 12)
    except Exception:
        row_height = 30
    target_height = rows * row_height + 32
    try:
        container.setMinimumHeight(target_height)
        group.setMinimumHeight(0)
        group.setMaximumHeight(16777215)
    except Exception:
        pass

    if scroll is not None:
        preferred_height = min(420, max(240, target_height))
        scroll.setMinimumHeight(preferred_height)
        scroll.setMaximumHeight(preferred_height)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        try:
            scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass
    update_dependency_action_buttons(self)


def refresh_dependency_versions(
    self,
    *,
    resolve_dependency_targets_for_config,
    dependency_targets_fallback,
    collect_dependency_versions,
    apply_dependency_usage_entry,
    maybe_auto_prepare_cpp_environment,
    dependency_usage_state,
    normalize_dependency_usage_text,
) -> None:
    if getattr(self, "_dep_version_refresh_inflight", False):
        self._dep_version_refresh_pending = True
        return

    self._dep_version_refresh_inflight = True
    self._dep_version_refresh_pending = False
    self._dep_version_watchdog_token = time.monotonic()
    update_dependency_action_buttons(self)

    try:
        resolved_targets = resolve_dependency_targets_for_config(self.config)
    except Exception:
        resolved_targets = copy.deepcopy(dependency_targets_fallback)
    try:
        config_snapshot = dict(self.config or {})
    except Exception:
        config_snapshot = {}

    try:
        if resolved_targets and resolved_targets != getattr(self, "_dep_version_targets", None):
            self._rebuild_dependency_version_rows(resolved_targets)
        else:
            try:
                self._dep_version_targets = list(resolved_targets or [])
            except Exception:
                pass
    except Exception:
        pass

    try:
        maybe_auto_prepare_cpp_environment(
            self,
            resolved_targets=resolved_targets,
            reason="dependency-refresh",
        )
    except Exception:
        pass

    labels = getattr(self, "_dep_version_labels", None)
    if labels:
        for label, widgets in labels.items():
            _, latest_widget, _, _ = widgets
            try:
                latest_widget.setText("Checking...")
            except Exception:
                pass
            apply_dependency_usage_entry(self, label, "Checking...", widgets=widgets, track_change=False)

    try:
        installed_snapshot = collect_dependency_versions(
            resolved_targets,
            include_latest=False,
            config=config_snapshot,
        )
    except Exception:
        installed_snapshot = []
    if labels and installed_snapshot:
        for label, installed, _, usage in installed_snapshot:
            widgets = labels.get(label)
            if not widgets:
                continue
            installed_widget, _, _, _ = widgets
            try:
                installed_widget.setText(installed)
            except Exception:
                pass
            apply_dependency_usage_entry(self, label, usage, widgets=widgets, track_change=True)

    def _watchdog(token: float):
        try:
            if not getattr(self, "_dep_version_refresh_inflight", False):
                return
            if token != getattr(self, "_dep_version_watchdog_token", None):
                return
            labels_local = getattr(self, "_dep_version_labels", None)
            if labels_local:
                for label, widgets in labels_local.items():
                    _, latest_widget, _, _ = widgets
                    try:
                        latest_widget.setText("Unknown")
                    except Exception:
                        pass
                    if normalize_dependency_usage_text(widgets[2].text()) == "Checking...":
                        apply_dependency_usage_entry(self, label, "Passive", widgets=widgets, track_change=False)
            self._dep_version_refresh_inflight = False
            update_dependency_action_buttons(self)
        except Exception:
            self._dep_version_refresh_inflight = False
            update_dependency_action_buttons(self)

    QtCore.QTimer.singleShot(20000, lambda token=self._dep_version_watchdog_token: _watchdog(token))

    def _run_latest():
        try:
            installed_snapshot_local = list(
                collect_dependency_versions(
                    resolved_targets,
                    include_latest=False,
                    config=config_snapshot,
                )
            )
        except Exception:
            installed_snapshot_local = []

        try:
            results = list(
                collect_dependency_versions(
                    resolved_targets,
                    include_latest=True,
                    config=config_snapshot,
                )
            )
        except Exception:
            results = []
        if not results:
            if installed_snapshot_local:
                results = [
                    (label, installed, "Unknown", usage)
                    for (label, installed, _, usage) in installed_snapshot_local
                ]
            else:
                results = [
                    (
                        target["label"],
                        "Not installed",
                        "Unknown",
                        dependency_usage_state(target, config=config_snapshot),
                    )
                    for target in (resolved_targets or [])
                ]

        QtCore.QMetaObject.invokeMethod(
            self,
            "_apply_dependency_version_results",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, results),
        )

    threading.Thread(target=_run_latest, daemon=True).start()


def apply_dependency_version_results(
    self,
    results: list,
    *,
    apply_dependency_usage_entry,
) -> None:
    try:
        labels_local = getattr(self, "_dep_version_labels", None)
        if labels_local:
            installed_map = {}
            latest_map = {}
            usage_map = {}
            for row in (results or []):
                if not row:
                    continue
                label = row[0]
                installed = row[1] if len(row) > 1 else "Not installed"
                latest = row[2] if len(row) > 2 else "Unknown"
                usage = row[3] if len(row) > 3 else "Passive"
                installed_map[label] = installed
                latest_map[label] = latest
                usage_map[label] = usage

            for label, widgets in labels_local.items():
                if widgets is None:
                    continue
                installed_widget, latest_widget, _, _ = widgets
                try:
                    if label in installed_map:
                        installed_widget.setText(installed_map[label])
                except Exception:
                    pass
                try:
                    latest_widget.setText(latest_map.get(label, "Unknown"))
                except Exception:
                    pass
                apply_dependency_usage_entry(
                    self,
                    label,
                    usage_map.get(label, "Passive"),
                    widgets=widgets,
                    track_change=True,
                )

        self._dep_version_refresh_inflight = False
        update_dependency_action_buttons(self)
        if getattr(self, "_dep_version_refresh_pending", False):
            self._dep_version_refresh_pending = False
            QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
    except Exception:
        self._dep_version_refresh_inflight = False
        update_dependency_action_buttons(self)
