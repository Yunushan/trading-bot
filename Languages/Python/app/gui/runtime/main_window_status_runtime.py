from __future__ import annotations

import time

from PyQt6 import QtCore, QtWidgets


def bind_main_window_status_runtime(main_window_cls) -> None:
    main_window_cls._update_bot_status = _update_bot_status
    main_window_cls._ensure_bot_time_timer = _ensure_bot_time_timer
    main_window_cls._update_bot_time_labels = _update_bot_time_labels
    main_window_cls._apply_pnl_snapshot_to_labels = _apply_pnl_snapshot_to_labels
    main_window_cls._register_pnl_summary_labels = _register_pnl_summary_labels
    main_window_cls._update_global_pnl_display = _update_global_pnl_display
    main_window_cls._has_active_engines = _has_active_engines
    main_window_cls._sync_runtime_state = _sync_runtime_state
    main_window_cls._format_bot_duration = staticmethod(_format_bot_duration)
    main_window_cls._format_total_pnl_text = staticmethod(_format_total_pnl_text)


def _update_bot_status(self, active=None):
    try:
        if active is not None:
            self._bot_active = bool(active)
        current_active = bool(getattr(self, "_bot_active", False))
        if current_active and not self._bot_active_since:
            self._bot_active_since = time.time()
            self._ensure_bot_time_timer()
            if self._bot_time_timer:
                self._bot_time_timer.start()
        elif not current_active:
            self._bot_active_since = None
            if self._bot_time_timer:
                self._bot_time_timer.stop()
        text = "Bot Status: ON" if current_active else "Bot Status: OFF"
        color = "#3FB950" if current_active else "#F97068"
        for label in (
            getattr(self, "bot_status_label_tab1", None),
            getattr(self, "bot_status_label_tab2", None),
            getattr(self, "bot_status_label_tab3", None),
            getattr(self, "bot_status_label_chart", None),
            getattr(self, "bot_status_label_code_tab", None),
        ):
            if label is None:
                continue
            label.setText(text)
            label.setStyleSheet(f"font-weight: bold; color: {color};")
        self._update_bot_time_labels()
        try:
            self._sync_service_runtime_snapshot(current_active, source="desktop-status")
        except Exception:
            pass
    except Exception:
        pass


def _ensure_bot_time_timer(self):
    if getattr(self, "_bot_time_timer", None) is None:
        try:
            timer = QtCore.QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(self._update_bot_time_labels)
            self._bot_time_timer = timer
        except Exception:
            self._bot_time_timer = None


def _format_bot_duration(seconds: float) -> str:
    remaining = int(max(seconds, 0))
    units = []
    spans = [
        ("mo", 30 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ]
    for suffix, size in spans:
        if remaining >= size:
            value, remaining = divmod(remaining, size)
            units.append(f"{value}{suffix}")
        if len(units) >= 3:
            break
    if not units:
        return "0s"
    return " ".join(units)


def _update_bot_time_labels(self):
    try:
        labels = [
            getattr(self, "bot_time_label_tab1", None),
            getattr(self, "bot_time_label_tab2", None),
            getattr(self, "bot_time_label_tab3", None),
            getattr(self, "bot_time_label_chart", None),
            getattr(self, "bot_time_label_code_tab", None),
        ]
        if not labels:
            return
        if self._bot_active and self._bot_active_since:
            elapsed = max(0.0, time.time() - float(self._bot_active_since))
            text = f"Bot Active Time: {self._format_bot_duration(elapsed)}"
        else:
            text = "Bot Active Time: --"
        for label in labels:
            if label is not None:
                label.setText(text)
    except Exception:
        pass


def _format_total_pnl_text(prefix: str, pnl_value: float | None, total_balance: float | None) -> str:
    if pnl_value is None:
        return f"{prefix}: --"
    text = f"{prefix}: {pnl_value:+.2f} USDT"
    if total_balance is not None:
        try:
            if total_balance != 0:
                roi_value = (float(pnl_value) / float(total_balance)) * 100.0
            else:
                roi_value = None
        except Exception:
            roi_value = None
        if roi_value is not None:
            text += f" ({roi_value:+.2f}%)"
    return text


def _apply_pnl_snapshot_to_labels(
    self,
    active_label: QtWidgets.QLabel | None,
    closed_label: QtWidgets.QLabel | None,
) -> None:
    snapshot = getattr(self, "_last_pnl_snapshot", None) or {}
    balance_snapshot = getattr(self, "_positions_balance_snapshot", None) or {}
    total_balance_ref = balance_snapshot.get("total")
    active_snapshot = snapshot.get("active", {})
    closed_snapshot = snapshot.get("closed", {})
    if active_label is not None:
        active_label.setText(
            self._format_total_pnl_text(
                "Total PNL Active Positions",
                active_snapshot.get("pnl"),
                total_balance_ref,
            )
        )
    if closed_label is not None:
        closed_label.setText(
            self._format_total_pnl_text(
                "Total PNL Closed Positions",
                closed_snapshot.get("pnl"),
                total_balance_ref,
            )
        )


def _register_pnl_summary_labels(
    self,
    active_label: QtWidgets.QLabel | None,
    closed_label: QtWidgets.QLabel | None,
) -> None:
    if not hasattr(self, "_pnl_label_sets") or self._pnl_label_sets is None:
        self._pnl_label_sets = []
    self._pnl_label_sets.append((active_label, closed_label))
    self._apply_pnl_snapshot_to_labels(active_label, closed_label)


def _update_global_pnl_display(
    self,
    active_pnl: float | None,
    active_margin: float | None,
    closed_pnl: float | None,
    closed_margin: float | None,
) -> None:
    try:
        snapshot = getattr(self, "_last_pnl_snapshot", None)
        if snapshot is None:
            snapshot = {"active": {"pnl": None}, "closed": {"pnl": None}}
            self._last_pnl_snapshot = snapshot

        snapshot["active"] = {
            "pnl": active_pnl if active_pnl is not None else None,
        }
        snapshot["closed"] = {
            "pnl": closed_pnl if closed_pnl is not None else None,
        }
        for label_pair in getattr(self, "_pnl_label_sets", []) or []:
            if not isinstance(label_pair, (list, tuple)):
                continue
            if len(label_pair) != 2:
                continue
            active_label, closed_label = label_pair
            self._apply_pnl_snapshot_to_labels(active_label, closed_label)
        try:
            self._sync_service_portfolio_snapshot(
                active_pnl=active_pnl,
                active_margin=active_margin,
                closed_pnl=closed_pnl,
                closed_margin=closed_margin,
                source="desktop-pnl",
            )
        except Exception:
            pass
    except Exception:
        pass


def _has_active_engines(self):
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
    except Exception:
        return False
    for eng in engines.values():
        try:
            if hasattr(eng, "is_alive"):
                if eng.is_alive():
                    return True
            else:
                thread = getattr(eng, "_thread", None)
                if thread and getattr(thread, "is_alive", lambda: False)():
                    return True
        except Exception:
            continue
    return False


def _sync_runtime_state(self):
    active = self._has_active_engines()
    try:
        self._sync_service_config_snapshot()
    except Exception:
        pass
    if active:
        self._set_runtime_controls_enabled(False)
    else:
        self._set_runtime_controls_enabled(True)
    try:
        btn = getattr(self, "refresh_balance_btn", None)
        if btn is not None:
            btn.setEnabled(True)
    except Exception:
        pass
    try:
        start_btn = getattr(self, "start_btn", None)
        stop_btn = getattr(self, "stop_btn", None)
        if start_btn is not None:
            start_btn.setEnabled(not active)
        if stop_btn is not None:
            stop_btn.setEnabled(active)
    except Exception:
        pass
    try:
        for btn in (
            getattr(self, "pair_add_btn", None),
            getattr(self, "pair_remove_btn", None),
            getattr(self, "pair_clear_btn", None),
        ):
            if btn is not None:
                btn.setEnabled(not active)
    except Exception:
        pass
    self._update_bot_status(active)
    try:
        self._update_runtime_stop_loss_widgets()
    except Exception:
        pass
    return active
