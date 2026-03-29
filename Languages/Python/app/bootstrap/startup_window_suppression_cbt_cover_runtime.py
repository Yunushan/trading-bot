from __future__ import annotations

from . import startup_window_suppression_cbt_state_runtime as cbt_state


def _set_helper_cover_visible(api, key: tuple[int, int, int, int], info: dict[str, object], visible: bool) -> None:
    hwnd = int(info.get("hwnd") or 0)
    if not hwnd:
        return
    left, top, width, height = key
    if visible:
        try:
            api.user32.SetWindowPos(
                api.wintypes.HWND(hwnd),
                api.wintypes.HWND(api.HWND_TOPMOST),
                left,
                top,
                width,
                height,
                api.SWP_NOACTIVATE | api.SWP_SHOWWINDOW,
            )
            if getattr(api.user32, "ShowWindowAsync", None):
                api.user32.ShowWindowAsync(api.wintypes.HWND(hwnd), api.SW_SHOWNOACTIVATE)
            else:
                api.user32.ShowWindow(api.wintypes.HWND(hwnd), api.SW_SHOWNOACTIVATE)
            info["hidden"] = False
            return
        except Exception:
            pass
    try:
        api.user32.SetWindowPos(
            api.wintypes.HWND(hwnd),
            0,
            -32000,
            -32000,
            0,
            0,
            api.SWP_NOSIZE | api.SWP_NOZORDER | api.SWP_NOACTIVATE | api.SWP_HIDEWINDOW | api.SWP_ASYNCWINDOWPOS,
        )
    except Exception:
        pass
    try:
        if getattr(api.user32, "ShowWindowAsync", None):
            api.user32.ShowWindowAsync(api.wintypes.HWND(hwnd), api.SW_HIDE)
        else:
            api.user32.ShowWindow(api.wintypes.HWND(hwnd), api.SW_HIDE)
    except Exception:
        pass
    info["hidden"] = True


def _cleanup_expired_helper_covers(api, *, force: bool = False) -> None:
    lock = cbt_state._CBT_STARTUP_HELPER_COVER_LOCK
    if lock is None:
        return
    try:
        now = api.time.monotonic()
    except Exception:
        now = 0.0
    with lock:
        items = list(cbt_state._CBT_STARTUP_HELPER_COVERS.items())
    for key, info in items:
        try:
            expires_at = float(info.get("expires_at") or 0.0)
        except Exception:
            expires_at = 0.0
        if not force and expires_at > now:
            continue
        if bool(info.get("hidden")) and not force:
            continue
        _set_helper_cover_visible(api, key, info, False)


def _ensure_helper_cover_cleanup_thread(api) -> None:
    if cbt_state._CBT_STARTUP_HELPER_COVER_THREAD is not None:
        return
    stop_event = api.threading.Event()
    cbt_state._CBT_STARTUP_HELPER_COVER_STOP = stop_event

    def _cover_cleanup_loop() -> None:
        while not stop_event.wait(0.03):
            _cleanup_expired_helper_covers(api, force=False)

    thread = api.threading.Thread(target=_cover_cleanup_loop, name="cbt-helper-cover-cleanup", daemon=True)
    cbt_state._CBT_STARTUP_HELPER_COVER_THREAD = thread
    thread.start()


def _create_helper_cover(api, left: int, top: int, width: int, height: int) -> tuple[int, int]:
    screen_dc = None
    mem_dc = None
    bitmap = 0
    old_obj = 0
    hwnd = 0
    try:
        screen_dc = api.user32.GetDC(0)
        if not screen_dc:
            return 0, 0
        mem_dc = api.gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            return 0, 0
        bitmap = int(api.gdi32.CreateCompatibleBitmap(screen_dc, width, height) or 0)
        if not bitmap:
            return 0, 0
        old_obj = int(api.gdi32.SelectObject(mem_dc, bitmap) or 0)
        if not api.gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, api.SRCCOPY | api.CAPTUREBLT):
            return 0, 0
        hwnd = int(
            api.user32.CreateWindowExW(
                api.WS_EX_TOPMOST | api.WS_EX_TOOLWINDOW | api.WS_EX_NOACTIVATE | api.WS_EX_LAYERED | api.WS_EX_TRANSPARENT,
                "Static",
                api.HELPER_COVER_TITLE,
                api.WS_POPUP | api.SS_BITMAP,
                left,
                top,
                width,
                height,
                0,
                0,
                0,
                None,
            )
            or 0
        )
        if not hwnd:
            return 0, 0
        api.user32.SendMessageW(api.wintypes.HWND(hwnd), api.STM_SETIMAGE, api.IMAGE_BITMAP, bitmap)
        api.user32.SetWindowPos(
            api.wintypes.HWND(hwnd),
            api.wintypes.HWND(api.HWND_TOPMOST),
            left,
            top,
            width,
            height,
            api.SWP_NOACTIVATE | api.SWP_SHOWWINDOW,
        )
        return hwnd, bitmap
    except Exception:
        return 0, 0
    finally:
        try:
            if mem_dc:
                if old_obj:
                    api.gdi32.SelectObject(mem_dc, old_obj)
                api.gdi32.DeleteDC(mem_dc)
        except Exception:
            pass
        try:
            if screen_dc:
                api.user32.ReleaseDC(0, screen_dc)
        except Exception:
            pass


def _show_helper_cover(api, left: int, top: int, width: int, height: int, *, duration_ms: int = 900) -> None:
    if width <= 0 or height <= 0:
        return
    if width > 6000 or height > 160:
        return
    if abs(int(left)) > 50000 or abs(int(top)) > 50000:
        return
    if left <= -32000 or top <= -32000:
        return
    key = (int(left), int(top), int(width), int(height))
    try:
        expires_at = api.time.monotonic() + (max(120, min(duration_ms, 5000)) / 1000.0)
    except Exception:
        expires_at = 0.0
    lock = cbt_state._CBT_STARTUP_HELPER_COVER_LOCK
    if lock is None:
        return
    with lock:
        existing = cbt_state._CBT_STARTUP_HELPER_COVERS.get(key)
        if existing is not None:
            existing["expires_at"] = max(float(existing.get("expires_at") or 0.0), expires_at)
            if bool(existing.get("hidden")):
                _set_helper_cover_visible(api, key, existing, True)
            return
    hwnd, bitmap = _create_helper_cover(api, left, top, width, height)
    if not hwnd:
        return
    with lock:
        existing = cbt_state._CBT_STARTUP_HELPER_COVERS.get(key)
        if existing is None:
            cbt_state._CBT_STARTUP_HELPER_COVERS[key] = {
                "hwnd": int(hwnd),
                "hbitmap": int(bitmap),
                "expires_at": float(expires_at),
                "hidden": False,
            }
        else:
            existing["expires_at"] = max(float(existing.get("expires_at") or 0.0), expires_at)
            if bool(existing.get("hidden")):
                _set_helper_cover_visible(api, key, existing, True)
    _ensure_helper_cover_cleanup_thread(api)
    if api.debug_window_events:
        try:
            with open(api.debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(f"cbt-cover-show rect={left},{top},{width},{height} hwnd={hwnd}\n")
        except Exception:
            pass
