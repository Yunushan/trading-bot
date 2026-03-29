from __future__ import annotations

from . import startup_window_suppression_winevent_window_runtime as window_runtime


def start_poll_thread(
    api,
    pid_registry,
    *,
    poll_ms: int,
    interval_ms: int,
    fast_ms: int,
    fast_interval_ms: int,
    stop_event,
):
    EnumWindowsProc = api.ctypes.WINFUNCTYPE(api.wintypes.BOOL, api.wintypes.HWND, api.wintypes.LPARAM)

    def _poll_once() -> None:
        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                hwnd_pid = window_runtime._get_hwnd_pid(api, hwnd_obj)
                if not pid_registry.contains(hwnd_pid):
                    return True
                try:
                    if not api.user32.IsWindowVisible(hwnd_obj):
                        return True
                except Exception:
                    return True
                if window_runtime._is_transient_startup_window(api, hwnd_obj):
                    window_runtime._hide_hwnd(api, hwnd_obj)
            except Exception:
                return True
            return True

        cb = EnumWindowsProc(_enum_cb)
        try:
            api.user32.EnumWindows(cb, 0)
        except Exception:
            pass

    def _poll_loop() -> None:
        start = api.time.monotonic()
        deadline = start + (max(200, poll_ms) / 1000.0)
        fast_deadline = start + (max(0, fast_ms) / 1000.0)
        next_pid_refresh = start
        while api.time.monotonic() < deadline and not stop_event.is_set():
            now = api.time.monotonic()
            if now >= next_pid_refresh:
                pid_registry.refresh(force=True)
                next_pid_refresh = now + 0.05
            _poll_once()
            sleep_s = (fast_interval_ms if now < fast_deadline else interval_ms) / 1000.0
            api.time.sleep(max(0.002, sleep_s))

    thread = api.threading.Thread(target=_poll_loop, name="startup-window-poll", daemon=True)
    thread.start()
    return thread
