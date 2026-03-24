from __future__ import annotations

import copy
import threading
import time

from PyQt6 import QtCore, QtWidgets


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

    header_dep = QtWidgets.QLabel("Dependency")
    header_dep.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_inst = QtWidgets.QLabel("Installed")
    header_inst.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_latest = QtWidgets.QLabel("Latest")
    header_latest.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_usage = QtWidgets.QLabel("Usage")
    header_usage.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_usage_counter = QtWidgets.QLabel("Usage Change Counter")
    header_usage_counter.setStyleSheet("font-weight: 600; font-size: 12px;")
    layout.addWidget(header_dep, 0, 0)
    layout.addWidget(header_inst, 0, 1)
    layout.addWidget(header_latest, 0, 2)
    layout.addWidget(header_usage, 0, 3)
    layout.addWidget(header_usage_counter, 0, 4)

    labels: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel]] = {}
    count_map = getattr(self, "_dep_usage_change_counts", None)
    if not isinstance(count_map, dict):
        count_map = {}
        self._dep_usage_change_counts = count_map

    for row, target in enumerate(target_list, start=1):
        label_widget = QtWidgets.QLabel(target["label"])
        label_widget.setStyleSheet("font-weight: 600; font-size: 11px; padding: 2px;")
        label_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(label_widget)

        installed_widget = QtWidgets.QLabel("Click Check Versions")
        installed_widget.setStyleSheet("font-size: 11px; padding: 2px;")
        installed_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(installed_widget)

        latest_widget = QtWidgets.QLabel("Click Check Versions")
        latest_widget.setStyleSheet("font-size: 11px; padding: 2px;")
        latest_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(latest_widget)

        usage_widget = QtWidgets.QLabel()
        usage_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(usage_widget)
        set_dependency_usage_widget(usage_widget, "On demand")

        usage_counter_widget = QtWidgets.QLabel()
        usage_counter_widget.setMinimumHeight(20)
        make_dependency_cell_copyable(usage_counter_widget)
        set_dependency_usage_counter_widget(usage_counter_widget, count_map.get(target["label"], 0))

        layout.addWidget(label_widget, row, 0)
        layout.addWidget(installed_widget, row, 1)
        layout.addWidget(latest_widget, row, 2)
        layout.addWidget(usage_widget, row, 3)
        layout.addWidget(usage_counter_widget, row, 4)
        labels[target["label"]] = (installed_widget, latest_widget, usage_widget, usage_counter_widget)

    self._dep_version_labels = labels
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

    rows = len(target_list) + 1
    try:
        fm = container.fontMetrics()
        row_height = max(30, fm.height() + 12)
    except Exception:
        row_height = 30
    target_height = rows * row_height + 32
    try:
        container.setMinimumHeight(target_height)
        group.setMinimumHeight(min(800, max(480, target_height + 60)))
    except Exception:
        pass

    if scroll is not None:
        scroll.setMinimumHeight(min(720, max(420, target_height)))
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        try:
            scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass


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
        except Exception:
            self._dep_version_refresh_inflight = False

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
        if getattr(self, "_dep_version_refresh_pending", False):
            self._dep_version_refresh_pending = False
            QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
    except Exception:
        self._dep_version_refresh_inflight = False
