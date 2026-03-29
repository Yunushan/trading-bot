from __future__ import annotations

from . import startup_window_suppression_cbt_cover_runtime as cbt_cover_runtime
from . import startup_window_suppression_cbt_window_runtime as cbt_window_runtime


def build_cbt_window_proc(api, cbt_proc_cls, cbt_createwnd_cls):
    def _call_next(n_code, w_param, l_param):
        return api.user32.CallNextHookEx(0, n_code, w_param, l_param)

    def _cbt_proc(n_code, w_param, l_param):  # noqa: ANN001
        try:
            if int(n_code) != api.HCBT_CREATEWND:
                return _call_next(n_code, w_param, l_param)
            hwnd_val = int(w_param)
            if not hwnd_val:
                return _call_next(n_code, w_param, l_param)
            lp_val = int(l_param)
            if not lp_val or lp_val < 0x10000:
                return _call_next(n_code, w_param, l_param)
            cbt = api.ctypes.cast(lp_val, api.ctypes.POINTER(cbt_createwnd_cls)).contents
            if not cbt.lpcs:
                return _call_next(n_code, w_param, l_param)
            cs = cbt.lpcs.contents
            width = int(cs.cx)
            height = int(cs.cy)
            if width <= 0 or height <= 0:
                return _call_next(n_code, w_param, l_param)
            cs_class = cbt_window_runtime._read_cs_string(api, cs.lpszClass)
            cs_title = cbt_window_runtime._read_cs_string(api, cs.lpszName)
            if cs_title == api.HELPER_COVER_TITLE:
                return _call_next(n_code, w_param, l_param)
            style = int(cs.style) & 0xFFFFFFFF
            if style & api.WS_CHILD:
                return _call_next(n_code, w_param, l_param)
            class_name = cs_class or cbt_window_runtime._read_hwnd_class(api, hwnd_val)
            title_text = cs_title or cbt_window_runtime._read_hwnd_title(api, hwnd_val)
            if cbt_window_runtime._looks_like_qt_internal_helper_window(class_name=class_name, title=title_text):
                orig_x = int(cs.x)
                orig_y = int(cs.y)
                is_q_titlebar_helper = class_name == "_q_titlebar" or title_text == "_q_titlebar"
                if is_q_titlebar_helper:
                    cbt_cover_runtime._show_helper_cover(api, orig_x, orig_y, width, height)
                cs.style = int(style & ~api.WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | api.WS_EX_TOOLWINDOW | api.WS_EX_NOACTIVATE) & ~api.WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                cs.cx = 1
                cs.cy = 1
                if api.debug_window_events:
                    try:
                        with open(api.debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            reason = "cbt-hide-qt-titlebar-helper" if is_q_titlebar_helper else "cbt-hide-qt-helper"
                            fh.write(
                                f"{reason} hwnd={hwnd_val} pos={orig_x},{orig_y} size={width}x{height} class={class_name!r} title={title_text!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
                return _call_next(n_code, w_param, l_param)
            if width >= 360 and height >= 220:
                return _call_next(n_code, w_param, l_param)
            is_tiny_strip = height <= 120 and width <= 4000
            is_tiny_popup = width <= 320 and height <= 320
            if is_tiny_strip or is_tiny_popup:
                cs.style = int(style & ~api.WS_VISIBLE)
                ex_style = int(cs.dwExStyle) & 0xFFFFFFFF
                cs.dwExStyle = int((ex_style | api.WS_EX_TOOLWINDOW | api.WS_EX_NOACTIVATE) & ~api.WS_EX_APPWINDOW)
                cs.x = -32000
                cs.y = -32000
                cs.cx = 1
                cs.cy = 1
                if api.debug_window_events:
                    try:
                        with open(api.debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                            fh.write(
                                f"cbt-hide hwnd={hwnd_val} size={width}x{height} class={class_name!r} title={cs_title!r} "
                                f"style=0x{style:08X} exstyle=0x{ex_style:08X}\n"
                            )
                    except Exception:
                        pass
        except Exception:
            pass
        return _call_next(n_code, w_param, l_param)

    return cbt_proc_cls(_cbt_proc)
