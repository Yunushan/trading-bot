from __future__ import annotations

from PyQt6 import QtCore

from .service_bridge_client_runtime import _ensure_service_client, _service_bridge_log


def _register_service_control_dispatcher(self) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    service = getattr(client, "service", None)
    if service is None:
        return
    setter = getattr(service, "set_control_request_handler", None)
    if not callable(setter):
        return
    try:
        setter(
            lambda request, window=self: _queue_service_control_request(window, request),
            mode="desktop-gui-dispatch",
            owner="desktop-gui",
            start_supported=True,
            stop_supported=True,
            notes=(
                "Control requests are queued onto the live desktop GUI thread.",
                "Desktop runtime state flows back into the service snapshot after actual start/stop transitions.",
            ),
        )
        self._desktop_service_control_dispatcher_registered = True
    except Exception:
        pass


def _coerce_service_control_payload(request) -> dict[str, object]:  # noqa: ANN001
    if isinstance(request, dict):
        return dict(request)
    try:
        to_dict = getattr(request, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, dict):
                return dict(payload)
    except Exception:
        pass
    return {}


def _queue_service_control_request(self, request) -> dict[str, object]:  # noqa: ANN001
    payload = _coerce_service_control_payload(request)
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"start", "stop"}:
        return {"accepted": False, "message": f"Unsupported control action: {action or 'unknown'}."}
    if bool(getattr(self, "_force_close", False)) or bool(getattr(self, "_close_in_progress", False)):
        return {"accepted": False, "message": "Desktop window is closing; control request rejected."}
    try:
        QtCore.QMetaObject.invokeMethod(
            self,
            "_handle_service_control_request",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, payload),
        )
    except Exception as exc:
        return {
            "accepted": False,
            "message": f"Failed to queue the control request on the desktop UI thread: {exc}",
        }
    request_source = str(payload.get("source") or "service-api").strip() or "service-api"
    return {
        "accepted": True,
        "message": f"{action.title()} request forwarded to the desktop GUI from {request_source}.",
    }


@QtCore.pyqtSlot(object)
def _handle_service_control_request(self, payload: dict | None) -> None:
    control_payload = payload if isinstance(payload, dict) else {}
    action = str(control_payload.get("action") or "").strip().lower()
    source = str(control_payload.get("source") or "service-api").strip() or "service-api"

    if action == "start":
        if bool(getattr(self, "_is_stopping_engines", False)):
            _service_bridge_log(self, "Service API start request ignored while stop is in progress.")
            try:
                self._service_mark_start_failed(
                    reason="Service API start ignored while stop is in progress.",
                    source="desktop-api",
                )
            except Exception:
                pass
            try:
                self._sync_runtime_state()
            except Exception:
                pass
            return
        try:
            if self._has_active_engines():
                _service_bridge_log(self, "Service API start request ignored because the bot is already running.")
                self._sync_runtime_state()
                return
        except Exception:
            pass
        _service_bridge_log(self, f"Service API start request accepted ({source}).")
        try:
            self.start_strategy()
        except Exception as exc:
            _service_bridge_log(self, f"Service API start dispatch failed: {exc}")
            try:
                self._service_mark_start_failed(
                    reason=f"Service API start dispatch failed: {exc}",
                    source="desktop-api",
                )
            except Exception:
                pass
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return

    if action == "stop":
        close_positions = bool(control_payload.get("close_positions"))
        try:
            if not self._has_active_engines():
                _service_bridge_log(self, "Service API stop request received while the bot is already idle.")
                self._sync_runtime_state()
                return
        except Exception:
            pass
        _service_bridge_log(self, f"Service API stop request accepted ({source}).")
        try:
            self.stop_strategy_async(close_positions=close_positions, blocking=False)
        except Exception as exc:
            _service_bridge_log(self, f"Service API stop dispatch failed: {exc}")
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return

    _service_bridge_log(self, f"Unsupported service control action ignored: {action or 'unknown'}.")
    try:
        self._sync_runtime_state()
    except Exception:
        pass


def _service_request_start(self, *, requested_job_count: int = 0, source: str = "desktop-start") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.request_start(requested_job_count=requested_job_count, source=source)
    except Exception:
        pass


def _service_request_stop(self, *, close_positions: bool = False, source: str = "desktop-stop") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.request_stop(close_positions=close_positions, source=source)
    except Exception:
        pass


def _service_mark_start_failed(self, *, reason: str = "", source: str = "desktop-start") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.mark_start_failed(reason=reason, source=source)
    except Exception:
        pass


def _service_record_log_event(
    self,
    message: str,
    *,
    source: str = "desktop-log",
    level: str = "info",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        record_log_event = getattr(client, "record_log_event", None)
        if callable(record_log_event):
            record_log_event(message, source=source, level=level)
    except Exception:
        pass
