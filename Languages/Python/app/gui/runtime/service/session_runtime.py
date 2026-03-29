from __future__ import annotations

import threading
from datetime import datetime

from PyQt6 import QtWidgets

_DEFAULT_CONNECTOR_BACKEND = ""
_NORMALIZE_CONNECTOR_BACKEND = lambda value: value  # type: ignore
_SAVE_APP_STATE_FILE = lambda path, data: None  # type: ignore


def bind_main_window_session_runtime(
    main_window_cls,
    *,
    default_connector_backend,
    normalize_connector_backend,
    save_app_state_file,
) -> None:
    global _DEFAULT_CONNECTOR_BACKEND
    global _NORMALIZE_CONNECTOR_BACKEND
    global _SAVE_APP_STATE_FILE

    _DEFAULT_CONNECTOR_BACKEND = default_connector_backend
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _SAVE_APP_STATE_FILE = save_app_state_file

    main_window_cls._on_close_on_exit_changed = _on_close_on_exit_changed
    main_window_cls._mark_session_active = _mark_session_active
    main_window_cls._mark_session_inactive = _mark_session_inactive
    main_window_cls._handle_post_init_state = _handle_post_init_state
    main_window_cls._set_runtime_controls_enabled = _set_runtime_controls_enabled


def _on_close_on_exit_changed(self, state):
    enabled = bool(state)
    self.config["close_on_exit"] = enabled
    try:
        data = dict(getattr(self, "_app_state", {}) or {})
    except Exception:
        data = {}
    data["close_on_exit"] = enabled
    if getattr(self, "_session_marker_active", False):
        data["session_active"] = True
    else:
        data["session_active"] = bool(data.get("session_active", False))
    data["updated_at"] = datetime.utcnow().isoformat()
    try:
        _SAVE_APP_STATE_FILE(self._state_path, data)
        self._app_state = data
    except Exception:
        pass
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        for eng in engines.values():
            try:
                if hasattr(eng, "config"):
                    eng.config["close_on_exit"] = enabled
            except Exception:
                pass
    except Exception:
        pass


def _mark_session_active(self):
    if getattr(self, "_session_marker_active", False):
        return
    self._session_marker_active = True
    try:
        data = dict(getattr(self, "_app_state", {}) or {})
    except Exception:
        data = {}
    data["session_active"] = True
    data["close_on_exit"] = bool(self.config.get("close_on_exit", False))
    data["activated_at"] = datetime.utcnow().isoformat()
    try:
        _SAVE_APP_STATE_FILE(self._state_path, data)
        self._app_state = data
    except Exception:
        pass


def _mark_session_inactive(self):
    if not getattr(self, "_session_marker_active", False):
        return
    self._session_marker_active = False
    try:
        data = dict(getattr(self, "_app_state", {}) or {})
    except Exception:
        data = {}
    data["session_active"] = False
    data["close_on_exit"] = bool(self.config.get("close_on_exit", False))
    data["deactivated_at"] = datetime.utcnow().isoformat()
    try:
        _SAVE_APP_STATE_FILE(self._state_path, data)
        self._app_state = data
    except Exception:
        pass


def _handle_post_init_state(self):
    try:
        self._mark_session_active()
        if self.config.get("close_on_exit") and getattr(self, "_previous_session_unclosed", False):
            if not getattr(self, "_auto_close_on_restart_triggered", False):
                self._auto_close_on_restart_triggered = True
                self._previous_session_unclosed = False
                self.log(
                    "Previous session ended unexpectedly with close-on-exit enabled; scheduling emergency close of all positions."
                )

                api_key = ""
                api_secret = ""
                mode = ""
                account = ""
                margin_mode = "Isolated"
                leverage = 1
                connector_backend = _DEFAULT_CONNECTOR_BACKEND

                try:
                    api_key = self.api_key_edit.text().strip() if getattr(self, "api_key_edit", None) else ""
                    api_secret = self.api_secret_edit.text().strip() if getattr(self, "api_secret_edit", None) else ""
                except Exception:
                    api_key = ""
                    api_secret = ""

                try:
                    mode = str(self.mode_combo.currentText() or "") if getattr(self, "mode_combo", None) else ""
                except Exception:
                    mode = ""
                try:
                    account = str(self.account_combo.currentText() or "") if getattr(self, "account_combo", None) else ""
                except Exception:
                    account = ""
                try:
                    margin_mode = str(self.margin_mode_combo.currentText() or "Isolated") if getattr(self, "margin_mode_combo", None) else "Isolated"
                except Exception:
                    margin_mode = "Isolated"
                try:
                    leverage = int(self.leverage_spin.value() or 1) if getattr(self, "leverage_spin", None) else 1
                except Exception:
                    leverage = 1
                try:
                    connector_backend = _NORMALIZE_CONNECTOR_BACKEND(
                        self.config.get("connector_backend") or _DEFAULT_CONNECTOR_BACKEND
                    )
                except Exception:
                    connector_backend = _DEFAULT_CONNECTOR_BACKEND

                if api_key and api_secret:
                    try:
                        self.stop_strategy_async(close_positions=False, blocking=False)
                    except Exception:
                        pass

                    def _run_emergency_close(
                        api_key_val: str,
                        api_secret_val: str,
                        mode_val: str,
                        account_val: str,
                        connector_backend_val: str,
                        leverage_val: int,
                        margin_mode_val: str,
                    ) -> None:
                        try:
                            wrapper = self._create_binance_wrapper(
                                api_key=api_key_val,
                                api_secret=api_secret_val,
                                mode=mode_val,
                                account_type=account_val,
                                connector_backend=connector_backend_val,
                                default_leverage=max(1, int(leverage_val or 1)),
                                default_margin_mode=str(margin_mode_val or "Isolated"),
                            )
                            wrapper.trigger_emergency_close_all(reason="restart_recovery", source="startup")
                            try:
                                self.log("Emergency close request submitted.")
                            except Exception:
                                pass
                        except Exception as exc_inner:
                            try:
                                self.log(f"Emergency close scheduling error: {exc_inner}")
                            except Exception:
                                pass

                    threading.Thread(
                        target=_run_emergency_close,
                        args=(api_key, api_secret, mode, account, connector_backend, leverage, margin_mode),
                        daemon=True,
                    ).start()
                else:
                    self.log("Emergency close skipped: API credentials are missing.")
                try:
                    data = dict(getattr(self, "_app_state", {}) or {})
                    data["session_active"] = True
                    data["close_on_exit"] = bool(self.config.get("close_on_exit", False))
                    data["last_recovery_at"] = datetime.utcnow().isoformat()
                    data["last_recovery_reason"] = "restart_recovery"
                    _SAVE_APP_STATE_FILE(self._state_path, data)
                    self._app_state = data
                except Exception:
                    pass
    except Exception as exc:
        try:
            self.log(f"Post-init state handler error: {exc}")
        except Exception:
            pass


def _set_runtime_controls_enabled(self, enabled: bool):
    try:
        widgets = getattr(self, "_runtime_lock_widgets", [])
        exemptions = getattr(self, "_runtime_active_exemptions", set())
        for widget in widgets:
            if widget is None:
                continue
            if enabled:
                widget.setEnabled(True)
                continue
            if widget in exemptions:
                try:
                    widget.setEnabled(True)
                except Exception:
                    pass
            else:
                widget.setEnabled(False)
    except Exception:
        pass
    if enabled:
        try:
            tif_combo = getattr(self, "tif_combo", None)
            gtd_spin = getattr(self, "gtd_minutes_spin", None)
            if tif_combo is not None and gtd_spin is not None:
                is_gtd = tif_combo.currentText() == "GTD"
                gtd_spin.setEnabled(is_gtd)
                gtd_spin.setReadOnly(not is_gtd)
                try:
                    gtd_spin.setButtonSymbols(
                        QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows
                        if is_gtd
                        else QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
                    )
                except Exception:
                    pass
            self._apply_lead_trader_state(bool(self.config.get("lead_trader_enabled", False)))
        except Exception:
            pass
