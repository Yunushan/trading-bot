# ruff: noqa: E402

import ctypes
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.bootstrap import startup_icon_runtime


class _WinFunction:
    def __init__(self, result=None, callback=None):
        self.result = result
        self.callback = callback

    def __call__(self, *args):
        if self.callback is not None:
            return self.callback(*args)
        return self.result


class _Window:
    def effectiveWinId(self):
        return 777


class StartupIconRuntimeTests(unittest.TestCase):
    def test_native_icon_application_reuses_loaded_handles_for_same_window_and_path(self):
        load_calls = []
        sent_messages = []

        def load_image(*args):
            load_calls.append(args)
            return 101 if len(load_calls) == 1 else 102

        user32 = SimpleNamespace(
            GetWindowLongPtrW=_WinFunction(0),
            SetWindowLongPtrW=_WinFunction(0),
            SetWindowPos=_WinFunction(1),
            GetSystemMetrics=_WinFunction(32),
            LoadImageW=_WinFunction(callback=load_image),
            SendMessageW=_WinFunction(callback=lambda *args: sent_messages.append(args) or 0),
            SetClassLongPtrW=_WinFunction(0),
        )

        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "Trading Bot.ico"
            icon.touch()
            with (
                mock.patch.object(startup_icon_runtime.sys, "platform", "win32"),
                mock.patch.object(startup_icon_runtime, "_resolve_native_icon_path", return_value=icon),
                mock.patch.object(startup_icon_runtime, "_native_icon_cache", {}),
                mock.patch.object(startup_icon_runtime, "_native_icon_handles", []),
                mock.patch.object(ctypes, "windll", SimpleNamespace(user32=user32)),
            ):
                window = _Window()
                self.assertTrue(startup_icon_runtime._set_native_window_icon(window))
                self.assertTrue(startup_icon_runtime._set_native_window_icon(window))
                self.assertEqual([101, 102], startup_icon_runtime._native_icon_handles)

        self.assertEqual(2, len(load_calls))
        self.assertEqual(2, len(sent_messages))

    def test_native_icon_cache_does_not_suppress_a_different_window_with_reused_handle(self):
        load_calls = []

        def load_image(*args):
            load_calls.append(args)
            return 100 + len(load_calls)

        user32 = SimpleNamespace(
            GetWindowLongPtrW=_WinFunction(0),
            SetWindowLongPtrW=_WinFunction(0),
            SetWindowPos=_WinFunction(1),
            GetSystemMetrics=_WinFunction(32),
            LoadImageW=_WinFunction(callback=load_image),
            SendMessageW=_WinFunction(0),
            SetClassLongPtrW=_WinFunction(0),
        )

        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "Trading Bot.ico"
            icon.touch()
            with (
                mock.patch.object(startup_icon_runtime.sys, "platform", "win32"),
                mock.patch.object(startup_icon_runtime, "_resolve_native_icon_path", return_value=icon),
                mock.patch.object(startup_icon_runtime, "_native_icon_cache", {}),
                mock.patch.object(startup_icon_runtime, "_native_icon_handles", []),
                mock.patch.object(ctypes, "windll", SimpleNamespace(user32=user32)),
            ):
                first_window = _Window()
                second_window = _Window()
                self.assertTrue(startup_icon_runtime._set_native_window_icon(first_window))
                self.assertTrue(startup_icon_runtime._set_native_window_icon(second_window))

        self.assertEqual(4, len(load_calls))

    def test_native_icon_assignment_failure_destroys_the_unapplied_handle(self):
        destroyed_icons = []
        load_results = iter((101, 102))

        def send_message(_hwnd, _message, icon_size, _handle):
            if icon_size == 1:
                raise OSError("big icon assignment failed")
            return 0

        user32 = SimpleNamespace(
            GetWindowLongPtrW=_WinFunction(0),
            SetWindowLongPtrW=_WinFunction(0),
            SetWindowPos=_WinFunction(1),
            GetSystemMetrics=_WinFunction(32),
            LoadImageW=_WinFunction(callback=lambda *_args: next(load_results)),
            SendMessageW=_WinFunction(callback=send_message),
            SetClassLongPtrW=_WinFunction(0),
            DestroyIcon=_WinFunction(callback=lambda handle: destroyed_icons.append(handle) or 1),
        )

        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "Trading Bot.ico"
            icon.touch()
            with (
                mock.patch.object(startup_icon_runtime.sys, "platform", "win32"),
                mock.patch.object(startup_icon_runtime, "_resolve_native_icon_path", return_value=icon),
                mock.patch.object(startup_icon_runtime, "_native_icon_cache", {}),
                mock.patch.object(startup_icon_runtime, "_native_icon_handles", []),
                mock.patch.object(ctypes, "windll", SimpleNamespace(user32=user32)),
            ):
                self.assertTrue(startup_icon_runtime._set_native_window_icon(_Window()))
                self.assertEqual([101], startup_icon_runtime._native_icon_handles)

        self.assertEqual([102], destroyed_icons)


if __name__ == "__main__":
    unittest.main()
