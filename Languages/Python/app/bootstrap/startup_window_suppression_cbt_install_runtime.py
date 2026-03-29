from __future__ import annotations

import os

from . import startup_window_suppression_cbt_state_runtime as cbt_state
from . import startup_window_suppression_cbt_thread_runtime as cbt_thread_runtime


def bootstrap_cbt_thread_hooks(api) -> None:
    if cbt_state._CBT_STARTUP_WINDOW_LOCK is None:
        cbt_state._CBT_STARTUP_WINDOW_LOCK = api.threading.Lock()

    try:
        api.user32.PostThreadMessageW.argtypes = [
            api.wintypes.DWORD,
            api.wintypes.UINT,
            api.wintypes.WPARAM,
            api.wintypes.LPARAM,
        ]
        api.user32.PostThreadMessageW.restype = api.wintypes.BOOL
    except Exception:
        pass

    try:
        msg = api.wintypes.MSG()
        api.user32.PeekMessageW(api.ctypes.byref(msg), 0, 0, 0, 0)
    except Exception:
        pass

    try:
        current_tid = int(api.kernel32.GetCurrentThreadId())
    except Exception:
        current_tid = 0
    cbt_thread_runtime._install_hook_for_thread(api, current_tid)

    try:
        scan_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_MS") or 0)
    except Exception:
        scan_ms = 0
    scan_ms = max(0, min(30000, scan_ms))

    try:
        interval_ms = int(os.environ.get("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS") or 50)
    except Exception:
        interval_ms = 50
    interval_ms = max(20, min(250, interval_ms))

    try:
        pid_val = int(api.kernel32.GetCurrentProcessId())
    except Exception:
        pid_val = 0

    if scan_ms <= 0:
        return

    stop_event = api.threading.Event()
    cbt_state._CBT_STARTUP_WINDOW_SCAN_STOP = stop_event

    def _scan_loop() -> None:
        deadline = api.time.monotonic() + (scan_ms / 1000.0)
        while api.time.monotonic() < deadline and not stop_event.is_set():
            for tid in cbt_thread_runtime._enumerate_thread_ids(api, pid_val):
                cbt_thread_runtime._install_hook_for_thread(api, tid)
            api.time.sleep(interval_ms / 1000.0)

    thread = api.threading.Thread(target=_scan_loop, name="cbt-hook-scan", daemon=True)
    cbt_state._CBT_STARTUP_WINDOW_SCAN_THREAD = thread
    thread.start()
