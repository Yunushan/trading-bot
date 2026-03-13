from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PyQt6 import QtCore

from . import chart_embed, main_window_runtime, window_runtime
from .chart_embed import (
    _configure_tradingview_webengine_env,
    _webengine_charts_allowed,
    _webengine_embed_unavailable_reason,
)


def _ensure_tradingview_widget(self):
    return chart_embed.ensure_tradingview_widget(self)


def _bind_tradingview_ready(self, widget):
    return chart_embed.bind_tradingview_ready(self, widget)


def _ensure_binance_widget(self):
    return chart_embed.ensure_binance_widget(self)


def _ensure_lightweight_widget(self):
    return chart_embed.ensure_lightweight_widget(self)


def _update_chart_overlay_geometry(self):
    return chart_embed.update_chart_overlay_geometry(self)


def _show_chart_switch_overlay(self):
    return chart_embed.show_chart_switch_overlay(self)


def _hide_chart_switch_overlay(self, delay_ms: int = 0):
    return chart_embed.hide_chart_switch_overlay(self, delay_ms=delay_ms)


def _schedule_tradingview_prewarm(self):
    return window_runtime.schedule_tradingview_prewarm(self)


def _schedule_webengine_runtime_prewarm(self):
    return window_runtime.schedule_webengine_runtime_prewarm(self)


def _maybe_run_deferred_webengine_prewarm(self):
    return window_runtime.maybe_run_deferred_webengine_prewarm(self)


def _prewarm_webengine_runtime(self):
    return window_runtime.prewarm_webengine_runtime(
        self,
        webengine_charts_allowed=_webengine_charts_allowed,
        webengine_embed_unavailable_reason=_webengine_embed_unavailable_reason,
        configure_tradingview_webengine_env=_configure_tradingview_webengine_env,
    )


def _prewarm_tradingview(self):
    return window_runtime.prewarm_tradingview(self)


def _start_tradingview_visibility_guard(self):
    return window_runtime.start_tradingview_visibility_guard(self)


def _start_tradingview_visibility_watchdog(self):
    return window_runtime.start_tradingview_visibility_watchdog(self)


def _start_tradingview_close_guard(self):
    return window_runtime.start_tradingview_close_guard(self)


def _start_webengine_close_guard(self):
    return window_runtime.start_webengine_close_guard(
        self,
        webengine_charts_allowed=_webengine_charts_allowed,
    )


def _start_webengine_visibility_watchdog(self):
    return window_runtime.start_webengine_visibility_watchdog(
        self,
        allow_guard_bypass=main_window_runtime._allow_guard_bypass,
        restore_window_after_guard=main_window_runtime._restore_window_after_guard,
    )


def _stop_webengine_visibility_watchdog(self):
    return window_runtime.stop_webengine_visibility_watchdog(self)


def _stop_tradingview_visibility_guard(self):
    return window_runtime.stop_tradingview_visibility_guard(self)


def _stop_tradingview_visibility_watchdog(self):
    return window_runtime.stop_tradingview_visibility_watchdog(self)


def _start_tradingview_window_suppression(self):
    if sys.platform != "win32":
        return
    flag = str(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS", "")).strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    if getattr(self, "_tv_window_suppress_active", False):
        return
    try:
        import ctypes
        import ctypes.wintypes as wintypes
    except Exception:
        return
    self._tv_window_suppress_active = True

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    try:
        pid = int(kernel32.GetCurrentProcessId())
    except Exception:
        pid = 0

    TH32CS_SNAPPROCESS = 0x00000002
    SW_HIDE = 0
    debug_windows = str(os.environ.get("BOT_DEBUG_TRADINGVIEW_WINDOWS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_tv_windows.log"

    def _get_hwnd_pid(hwnd_obj):  # noqa: ANN001
        try:
            out_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
            return int(out_pid.value)
        except Exception:
            return 0

    def _class_name(hwnd_obj):  # noqa: ANN001
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_obj, buf, 256)
            return str(buf.value or "").strip()
        except Exception:
            return ""

    def _is_transient(hwnd_obj, class_name: str | None = None):  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return False
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return False
            class_name = class_name or _class_name(hwnd_obj)
            try:
                GWL_STYLE = -16
                WS_CHILD = 0x40000000
                get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                style = int(get_style(hwnd_obj, GWL_STYLE))
                if style & WS_CHILD:
                    return False
            except Exception:
                pass
            if class_name.startswith("Qt") and class_name.endswith(
                (
                    "PowerDummyWindow",
                    "ClipboardView",
                    "ScreenChangeObserverWindow",
                    "ThemeChangeObserverWindow",
                )
            ):
                return True
            if class_name.startswith("_q_"):
                return height <= 260 and width <= 4000
            if class_name == "Intermediate D3D Window":
                return height <= 500 and width <= 4000
            if class_name.startswith("Chrome_WidgetWin_"):
                return height <= 500 and width <= 4000
            if width >= 500 and height >= 300:
                return False
            return height <= 120 and width <= 4000
        except Exception:
            return False

    def _hide(hwnd_obj):  # noqa: ANN001
        try:
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_HIDEWINDOW = 0x0080
            SWP_ASYNCWINDOWPOS = 0x4000
            user32.SetWindowPos(
                hwnd_obj,
                0,
                -32000,
                -32000,
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_HIDEWINDOW | SWP_ASYNCWINDOWPOS,
            )
        except Exception:
            pass
        try:
            if getattr(user32, "ShowWindowAsync", None):
                user32.ShowWindowAsync(hwnd_obj, SW_HIDE)
            else:
                user32.ShowWindow(hwnd_obj, SW_HIDE)
        except Exception:
            pass

    def _window_size(hwnd_obj):  # noqa: ANN001
        try:
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                return None, None
            return int(rect.right - rect.left), int(rect.bottom - rect.top)
        except Exception:
            return None, None

    def _log_window(hwnd_obj, reason: str, pid_val: int, class_name: str) -> None:  # noqa: ANN001
        if not debug_windows:
            return
        try:
            width, height = _window_size(hwnd_obj)
            with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(
                    f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} class={class_name!r} "
                    f"size={width}x{height}\n"
                )
        except Exception:
            return

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", wintypes.ULONG_PTR),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    def _snapshot_processes():
        entries = []
        try:
            kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
            kernel32.Process32FirstW.restype = wintypes.BOOL
            kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
            kernel32.Process32NextW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
        except Exception:
            pass
        try:
            snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        except Exception:
            snapshot = 0
        if snapshot in (0, ctypes.c_void_p(-1).value):
            return entries

        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return entries
            while True:
                entries.append(
                    (
                        int(entry.th32ProcessID),
                        int(entry.th32ParentProcessID),
                        str(entry.szExeFile or "").strip(),
                    )
                )
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            try:
                kernel32.CloseHandle(snapshot)
            except Exception:
                pass
        return entries

    def _collect_related_pids(root_pid: int):
        entries = _snapshot_processes()
        if not entries:
            return {root_pid} if root_pid else set(), set()
        children = {}
        exe_map = {}
        for proc_pid, parent_pid, exe in entries:
            exe_map[proc_pid] = exe
            children.setdefault(parent_pid, []).append(proc_pid)
        tree = set()
        stack = [root_pid] if root_pid else []
        while stack:
            cur = stack.pop()
            if cur in tree:
                continue
            tree.add(cur)
            stack.extend(children.get(cur, []))
        qt_roots = {
            proc_pid
            for proc_pid in tree
            if "qtwebengineprocess" in (exe_map.get(proc_pid, "") or "").lower()
        }
        qt_tree = set()
        for root in qt_roots:
            stack = [root]
            while stack:
                cur = stack.pop()
                if cur in qt_tree:
                    continue
                qt_tree.add(cur)
                stack.extend(children.get(cur, []))
        return tree if tree else ({root_pid} if root_pid else set()), qt_tree

    pid_cache = {"ts": 0.0, "pids": {pid} if pid else set(), "qt_pids": set()}

    def _get_pid_sets():
        now = time.monotonic()
        if now - pid_cache["ts"] < 0.25:
            return pid_cache["pids"], pid_cache["qt_pids"]
        tree, qt_tree = _collect_related_pids(pid)
        pid_cache["ts"] = now
        pid_cache["pids"] = tree
        pid_cache["qt_pids"] = qt_tree
        return tree, qt_tree

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _poll_once():
        allowed_pids, qt_pids = _get_pid_sets()

        def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
            try:
                pid_val = _get_hwnd_pid(hwnd_obj)
                if allowed_pids and pid_val not in allowed_pids:
                    return True
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return True
                except Exception:
                    return True
                class_name = _class_name(hwnd_obj)
                if qt_pids and pid_val in qt_pids:
                    if _is_transient(hwnd_obj, class_name=class_name):
                        _log_window(hwnd_obj, "hide-qtwebengine", pid_val, class_name)
                        _hide(hwnd_obj)
                    return True
            except Exception:
                return True
            return True

        cb = EnumWindowsProc(_enum_cb)
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

    try:
        duration_ms = int(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS_MS") or 1800)
    except Exception:
        duration_ms = 1800
    duration_ms = max(300, min(duration_ms, 5000))
    try:
        interval_ms = int(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS_INTERVAL_MS") or 30)
    except Exception:
        interval_ms = 30
    interval_ms = max(15, min(interval_ms, 120))

    timer = QtCore.QTimer(self)
    timer.setInterval(interval_ms)
    start_ts = time.monotonic()

    def _tick():
        if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
            self._tv_window_suppress_timer = None
            self._tv_window_suppress_active = False
            return
        _poll_once()

    timer.timeout.connect(_tick)
    timer.start()
    self._tv_window_suppress_timer = timer
    _tick()


def _prime_tradingview_chart(self, widget):
    return chart_embed.prime_tradingview_chart(self, widget)


def _open_tradingview_external(self) -> bool:
    return chart_embed.open_tradingview_external(self)


def bind_main_window_chart_host_runtime(MainWindow):
    MainWindow._ensure_tradingview_widget = _ensure_tradingview_widget
    MainWindow._bind_tradingview_ready = _bind_tradingview_ready
    MainWindow._ensure_binance_widget = _ensure_binance_widget
    MainWindow._ensure_lightweight_widget = _ensure_lightweight_widget
    MainWindow._update_chart_overlay_geometry = _update_chart_overlay_geometry
    MainWindow._show_chart_switch_overlay = _show_chart_switch_overlay
    MainWindow._hide_chart_switch_overlay = _hide_chart_switch_overlay
    MainWindow._schedule_tradingview_prewarm = _schedule_tradingview_prewarm
    MainWindow._schedule_webengine_runtime_prewarm = _schedule_webengine_runtime_prewarm
    MainWindow._maybe_run_deferred_webengine_prewarm = _maybe_run_deferred_webengine_prewarm
    MainWindow._prewarm_webengine_runtime = _prewarm_webengine_runtime
    MainWindow._prewarm_tradingview = _prewarm_tradingview
    MainWindow._start_tradingview_visibility_guard = _start_tradingview_visibility_guard
    MainWindow._start_tradingview_visibility_watchdog = _start_tradingview_visibility_watchdog
    MainWindow._start_tradingview_close_guard = _start_tradingview_close_guard
    MainWindow._start_webengine_close_guard = _start_webengine_close_guard
    MainWindow._start_webengine_visibility_watchdog = _start_webengine_visibility_watchdog
    MainWindow._stop_webengine_visibility_watchdog = _stop_webengine_visibility_watchdog
    MainWindow._stop_tradingview_visibility_guard = _stop_tradingview_visibility_guard
    MainWindow._stop_tradingview_visibility_watchdog = _stop_tradingview_visibility_watchdog
    MainWindow._start_tradingview_window_suppression = _start_tradingview_window_suppression
    MainWindow._prime_tradingview_chart = _prime_tradingview_chart
    MainWindow._open_tradingview_external = _open_tradingview_external
