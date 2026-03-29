from __future__ import annotations

from . import startup_window_suppression_cbt_state_runtime as cbt_state


def _install_hook_for_thread(api, thread_id: int) -> None:
    if not thread_id:
        return
    if cbt_state._CBT_STARTUP_WINDOW_PROC is None or cbt_state._CBT_STARTUP_WINDOW_LOCK is None:
        return
    with cbt_state._CBT_STARTUP_WINDOW_LOCK:
        if thread_id in cbt_state._CBT_STARTUP_WINDOW_HOOKS:
            return
        hook = api.user32.SetWindowsHookExW(
            api.WH_CBT,
            cbt_state._CBT_STARTUP_WINDOW_PROC,
            0,
            int(thread_id),
        )
        if hook:
            cbt_state._CBT_STARTUP_WINDOW_HOOKS[int(thread_id)] = int(hook)
        if api.debug_window_events:
            try:
                with open(api.debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                    fh.write(f"cbt-hook-install tid={int(thread_id)} hook={int(hook) if hook else 0}\n")
            except Exception:
                pass


def _enumerate_thread_ids(api, pid: int) -> set[int]:
    thread_ids: set[int] = set()
    if not pid:
        return thread_ids
    try:
        TH32CS_SNAPTHREAD = 0x00000004
        snapshot = api.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot in (0, api.ctypes.c_void_p(-1).value):
            return thread_ids

        class THREADENTRY32(api.ctypes.Structure):
            _fields_ = [
                ("dwSize", api.wintypes.DWORD),
                ("cntUsage", api.wintypes.DWORD),
                ("th32ThreadID", api.wintypes.DWORD),
                ("th32OwnerProcessID", api.wintypes.DWORD),
                ("tpBasePri", api.wintypes.LONG),
                ("tpDeltaPri", api.wintypes.LONG),
                ("dwFlags", api.wintypes.DWORD),
            ]

        entry = THREADENTRY32()
        entry.dwSize = api.ctypes.sizeof(entry)
        try:
            if not api.kernel32.Thread32First(snapshot, api.ctypes.byref(entry)):
                return thread_ids
            while True:
                if int(entry.th32OwnerProcessID) == int(pid):
                    thread_ids.add(int(entry.th32ThreadID))
                if not api.kernel32.Thread32Next(snapshot, api.ctypes.byref(entry)):
                    break
        finally:
            try:
                api.kernel32.CloseHandle(snapshot)
            except Exception:
                pass
    except Exception:
        return thread_ids
    return thread_ids
