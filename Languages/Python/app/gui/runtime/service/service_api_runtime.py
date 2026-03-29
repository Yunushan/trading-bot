from __future__ import annotations

import os

from PyQt6 import QtCore, QtGui, QtWidgets

_SAVE_APP_STATE_FILE = lambda path, data: None  # type: ignore


def bind_main_window_service_api_runtime(main_window_cls, *, save_app_state_file) -> None:
    global _SAVE_APP_STATE_FILE

    _SAVE_APP_STATE_FILE = save_app_state_file
    main_window_cls._initialize_desktop_service_api_preferences = _initialize_desktop_service_api_preferences
    main_window_cls._persist_desktop_service_api_preferences = _persist_desktop_service_api_preferences
    main_window_cls._read_desktop_service_api_ui_settings = _read_desktop_service_api_ui_settings
    main_window_cls._refresh_desktop_service_api_ui = _refresh_desktop_service_api_ui
    main_window_cls._on_desktop_service_api_enabled_toggled = _on_desktop_service_api_enabled_toggled
    main_window_cls._apply_desktop_service_api_ui_settings = _apply_desktop_service_api_ui_settings
    main_window_cls._open_desktop_service_api_dashboard = _open_desktop_service_api_dashboard


def _env_flag(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_host(value: object, default: str = "127.0.0.1") -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_port(value: object, default: int = 8000) -> int:
    try:
        return max(1, min(65535, int(value)))
    except Exception:
        return int(default)


def _initialize_desktop_service_api_preferences(self) -> None:
    app_state = dict(getattr(self, "_app_state", {}) or {})
    env_enabled = _env_flag("BOT_ENABLE_DESKTOP_SERVICE_API")
    if env_enabled is None:
        enabled = bool(app_state.get("desktop_service_api_enabled", False))
    else:
        enabled = bool(env_enabled)
    host = os.environ.get("BOT_DESKTOP_SERVICE_API_HOST")
    if host is None:
        host = app_state.get("desktop_service_api_host", "127.0.0.1")
    port_env = os.environ.get("BOT_DESKTOP_SERVICE_API_PORT")
    port = port_env if port_env not in (None, "") else app_state.get("desktop_service_api_port", 8000)
    token = os.environ.get("BOT_SERVICE_API_TOKEN", "")

    self._desktop_service_api_enabled_pref = bool(enabled)
    self._desktop_service_api_host_pref = _normalize_host(host)
    self._desktop_service_api_port_pref = _normalize_port(port)
    self._desktop_service_api_token_pref = str(token or "").strip()


def _persist_desktop_service_api_preferences(
    self,
    *,
    enabled: bool,
    host: str,
    port: int,
) -> None:
    try:
        data = dict(getattr(self, "_app_state", {}) or {})
    except Exception:
        data = {}
    data["desktop_service_api_enabled"] = bool(enabled)
    data["desktop_service_api_host"] = _normalize_host(host)
    data["desktop_service_api_port"] = _normalize_port(port)
    try:
        _SAVE_APP_STATE_FILE(self._state_path, data)
        self._app_state = data
    except Exception:
        pass


def _read_desktop_service_api_ui_settings(self) -> dict[str, object]:
    enabled = bool(getattr(self, "_desktop_service_api_enabled_pref", False))
    host = _normalize_host(getattr(self, "_desktop_service_api_host_pref", "127.0.0.1"))
    port = _normalize_port(getattr(self, "_desktop_service_api_port_pref", 8000))
    token = str(getattr(self, "_desktop_service_api_token_pref", "") or "").strip()

    cb = getattr(self, "desktop_service_api_enable_cb", None)
    if cb is not None:
        enabled = bool(cb.isChecked())
    host_edit = getattr(self, "desktop_service_api_host_edit", None)
    if host_edit is not None:
        host = _normalize_host(host_edit.text(), host)
    port_spin = getattr(self, "desktop_service_api_port_spin", None)
    if port_spin is not None:
        port = _normalize_port(port_spin.value(), port)
    token_edit = getattr(self, "desktop_service_api_token_edit", None)
    if token_edit is not None:
        token = str(token_edit.text() or "").strip()

    return {
        "enabled": enabled,
        "host": host,
        "port": port,
        "api_token": token,
        "url": f"http://{host}:{port}",
    }


def _refresh_desktop_service_api_ui(self, status: dict | None = None) -> None:
    settings = self._read_desktop_service_api_ui_settings()
    status = status if isinstance(status, dict) else self._get_desktop_service_api_host_status()

    enabled = bool(settings.get("enabled"))
    running = bool(isinstance(status, dict) and status.get("running"))
    auth_enabled = bool(isinstance(status, dict) and status.get("auth_enabled"))
    url = str((status or {}).get("url") or settings.get("url") or "").strip()
    startup_error = str((status or {}).get("startup_error") or "").strip()

    apply_btn = getattr(self, "desktop_service_api_apply_btn", None)
    open_btn = getattr(self, "desktop_service_api_open_btn", None)
    status_label = getattr(self, "desktop_service_api_status_label", None)

    if apply_btn is not None:
        if enabled and running:
            apply_btn.setText("Restart API")
        elif enabled:
            apply_btn.setText("Start API")
        else:
            apply_btn.setText("Stop API")

    if open_btn is not None:
        open_btn.setEnabled(bool(running and url))

    if status_label is not None:
        if running:
            text = f"Service API: running at {url} ({'auth on' if auth_enabled else 'auth off'})"
            color = "#3FB950"
        elif startup_error:
            text = f"Service API: {startup_error}"
            color = "#F97068"
        elif enabled:
            text = f"Service API: stopped, ready for {url}"
            color = "#F59E0B"
        else:
            text = "Service API: off"
            color = "#8B949E"
        status_label.setText(text)
        status_label.setStyleSheet(f"font-weight: 600; color: {color};")


def _on_desktop_service_api_enabled_toggled(self, checked: bool) -> None:
    self._desktop_service_api_enabled_pref = bool(checked)
    self._refresh_desktop_service_api_ui()


def _apply_desktop_service_api_ui_settings(self) -> dict | None:
    settings = self._read_desktop_service_api_ui_settings()
    self._desktop_service_api_enabled_pref = bool(settings["enabled"])
    self._desktop_service_api_host_pref = str(settings["host"])
    self._desktop_service_api_port_pref = int(settings["port"])
    self._desktop_service_api_token_pref = str(settings["api_token"])
    self._persist_desktop_service_api_preferences(
        enabled=bool(settings["enabled"]),
        host=str(settings["host"]),
        port=int(settings["port"]),
    )

    try:
        if settings["enabled"]:
            status = self._maybe_start_desktop_service_api_host(
                enabled=True,
                host=str(settings["host"]),
                port=int(settings["port"]),
                api_token=str(settings["api_token"]),
            )
        else:
            self._shutdown_desktop_service_api_host()
            status = self._get_desktop_service_api_host_status()
    except Exception as exc:
        status = {
            "running": False,
            "url": str(settings["url"]),
            "host": str(settings["host"]),
            "port": int(settings["port"]),
            "auth_enabled": bool(settings["api_token"]),
            "startup_error": str(exc),
        }
    self._refresh_desktop_service_api_ui(status)
    return status


def _open_desktop_service_api_dashboard(self) -> bool:
    settings = self._read_desktop_service_api_ui_settings()
    status = self._get_desktop_service_api_host_status()
    if not isinstance(status, dict) or not status.get("running"):
        if not settings["enabled"]:
            try:
                self.log("Enable the Desktop Service API first.")
            except Exception:
                pass
            return False
        status = self._apply_desktop_service_api_ui_settings()
    if not isinstance(status, dict) or not status.get("running"):
        return False
    url = str(status.get("url") or "").rstrip("/")
    if not url:
        return False
    return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(f"{url}/ui/")))
