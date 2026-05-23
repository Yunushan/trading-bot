from __future__ import annotations

from PyQt6 import QtCore

_SERVICE_BACKTEST_BACKENDS = {"service", "service-api", "remote", "desktop-service"}
_LOCAL_BACKTEST_BACKENDS = {"", "local", "desktop", "desktop-local"}
_TERMINAL_STATES = {"completed", "failed", "cancelled", "rejected"}


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _backtest_execution_backend(self) -> str:
    candidates: list[object] = []
    backtest_config = getattr(self, "backtest_config", None)
    if isinstance(backtest_config, dict):
        candidates.append(backtest_config.get("execution_backend"))
    config = getattr(self, "config", None)
    if isinstance(config, dict):
        nested = config.get("backtest")
        if isinstance(nested, dict):
            candidates.append(nested.get("execution_backend"))
    for candidate in candidates:
        text = _clean_text(candidate).lower()
        if text:
            return text
    return ""


def _get_service_descriptor(self) -> dict[str, object]:
    getter = getattr(self, "_get_service_client_descriptor", None)
    if not callable(getter):
        return {}
    try:
        descriptor = getter()
    except Exception:
        return {}
    return descriptor if isinstance(descriptor, dict) else {}


def should_use_service_backtest(self) -> bool:
    backend = _backtest_execution_backend(self)
    if backend in _LOCAL_BACKTEST_BACKENDS:
        descriptor = _get_service_descriptor(self)
        return _clean_text(descriptor.get("client_mode")).lower() == "remote"
    return backend in _SERVICE_BACKTEST_BACKENDS


def _set_status(self, message: str) -> None:
    try:
        self.backtest_status_label.setText(message)
    except Exception:
        pass


def _set_button_state(self, *, running: bool) -> None:
    for attr_name, enabled in (
        ("backtest_run_btn", not running),
        ("backtest_scan_btn", not running),
        ("backtest_stop_btn", running),
    ):
        button = getattr(self, attr_name, None)
        if button is None:
            continue
        try:
            button.setEnabled(bool(enabled))
        except Exception:
            pass


def _service_result_payload(snapshot: dict[str, object]) -> dict[str, object]:
    runs = snapshot.get("runs")
    if not isinstance(runs, list):
        runs = snapshot.get("top_runs")
    errors = snapshot.get("errors")
    return {
        "runs": list(runs or []) if isinstance(runs, list) else [],
        "errors": list(errors or []) if isinstance(errors, list) else [],
    }


def _finish_service_backtest(self, snapshot: dict[str, object]) -> None:
    state = _clean_text(snapshot.get("state")).lower()
    message = _clean_text(snapshot.get("status_message"))
    result = _service_result_payload(snapshot)
    if state == "completed":
        error = None
    elif state == "cancelled":
        error = RuntimeError("backtest_cancelled")
    else:
        error = RuntimeError(message or f"Service backtest {state or 'failed'}.")
    scan = _clean_text(getattr(self, "_backtest_service_session_kind", "")).lower() == "scan"
    self._backtest_service_session_active = False
    self._backtest_service_session_kind = ""
    self._backtest_service_session_id = ""
    callback_name = "_on_backtest_scan_finished" if scan else "_on_backtest_finished"
    callback = getattr(self, callback_name, None)
    if callable(callback):
        callback(result, error)
    else:
        _set_button_state(self, running=False)
        if error:
            _set_status(self, str(error))


def poll_service_backtest(self) -> None:
    if not bool(getattr(self, "_backtest_service_session_active", False)):
        return
    getter = getattr(self, "_get_service_backtest_snapshot", None)
    if not callable(getter):
        self._backtest_service_session_active = False
        _set_button_state(self, running=False)
        _set_status(self, "Service backtest snapshot is unavailable.")
        return
    try:
        snapshot = getter()
    except Exception as exc:
        self._backtest_service_session_active = False
        _set_button_state(self, running=False)
        _set_status(self, f"Service backtest polling failed: {exc}")
        return
    if not isinstance(snapshot, dict):
        _schedule_service_backtest_poll(self)
        return
    state = _clean_text(snapshot.get("state")).lower()
    message = _clean_text(snapshot.get("status_message"))
    if message:
        _set_status(self, message)
    if state in _TERMINAL_STATES:
        _finish_service_backtest(self, snapshot)
        return
    _schedule_service_backtest_poll(self)


def _schedule_service_backtest_poll(self) -> None:
    interval_ms = int(getattr(self, "_backtest_service_poll_interval_ms", 1000) or 1000)
    QtCore.QTimer.singleShot(max(250, interval_ms), lambda: poll_service_backtest(self))


def maybe_start_service_backtest(
    self,
    request_payload: dict[str, object],
    *,
    scan: bool = False,
    status_message: str = "Running service backtest...",
) -> bool:
    if not should_use_service_backtest(self):
        return False
    submit = getattr(self, "_service_submit_backtest", None)
    if not callable(submit):
        _set_status(self, "Service backtest backend is selected, but no service client is available.")
        _set_button_state(self, running=False)
        return True
    source = "desktop-backtest-scan" if scan else "desktop-backtest-run"
    try:
        result = submit(dict(request_payload or {}), source=source)
    except Exception as exc:
        _set_status(self, f"Service backtest submit failed: {exc}")
        _set_button_state(self, running=False)
        return True
    if not isinstance(result, dict) or not bool(result.get("accepted")):
        message = (
            _clean_text(result.get("status_message")) if isinstance(result, dict) else ""
        )
        _set_status(message or "Service backtest request was rejected.")
        _set_button_state(self, running=False)
        return True
    try:
        self.backtest_results_table.setRowCount(0)
    except Exception:
        pass
    self._backtest_service_session_active = True
    self._backtest_service_session_kind = "scan" if scan else "run"
    self._backtest_service_session_id = _clean_text(result.get("session_id"))
    self._backtest_service_poll_interval_ms = 1000
    _set_button_state(self, running=True)
    _set_status(self, status_message)
    _schedule_service_backtest_poll(self)
    return True


def stop_service_backtest(self) -> bool:
    if not bool(getattr(self, "_backtest_service_session_active", False)):
        return False
    stopper = getattr(self, "_service_stop_backtest", None)
    if not callable(stopper):
        _set_status(self, "Service backtest stop is unavailable.")
        return True
    try:
        result = stopper(source="desktop-backtest-stop")
    except Exception as exc:
        _set_status(self, f"Service backtest stop failed: {exc}")
        return True
    message = _clean_text(result.get("status_message")) if isinstance(result, dict) else ""
    _set_status(self, message or "Stopping service backtest...")
    try:
        self.backtest_stop_btn.setEnabled(False)
    except Exception:
        pass
    return True


__all__ = [
    "maybe_start_service_backtest",
    "poll_service_backtest",
    "should_use_service_backtest",
    "stop_service_backtest",
]
