# ruff: noqa: E402

import ctypes
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.bootstrap import startup_cover_runtime


class _WinFunction:
    def __init__(self, result=None, callback=None):
        self.result = result
        self.callback = callback

    def __call__(self, *args):
        if self.callback is not None:
            return self.callback(*args)
        return self.result


class NativeStartupCoverTests(unittest.TestCase):
    def test_capture_failure_releases_resources_when_gdi_restore_also_fails(self):
        deleted_bitmaps = []
        deleted_dcs = []
        released_dcs = []
        selected_objects = []

        def populate_monitor_info(_monitor, info_pointer):
            info = info_pointer._obj
            info.rcMonitor.left = 0
            info.rcMonitor.top = 0
            info.rcMonitor.right = 1920
            info.rcMonitor.bottom = 1080
            return 1

        def select_object(dc, obj):
            selected_objects.append((dc, obj))
            if len(selected_objects) == 2:
                raise OSError("restore failed")
            return 104

        user32 = SimpleNamespace(
            MonitorFromPoint=_WinFunction(1),
            GetMonitorInfoW=_WinFunction(callback=populate_monitor_info),
            CreateWindowExW=_WinFunction(0),
            SendMessageW=_WinFunction(0),
            SetWindowPos=_WinFunction(1),
            UpdateWindow=_WinFunction(1),
            GetDC=_WinFunction(101),
            ReleaseDC=_WinFunction(callback=lambda _window, dc: released_dcs.append(dc) or 1),
        )
        gdi32 = SimpleNamespace(
            CreateCompatibleDC=_WinFunction(102),
            CreateCompatibleBitmap=_WinFunction(103),
            SelectObject=_WinFunction(callback=select_object),
            BitBlt=_WinFunction(0),
            DeleteDC=_WinFunction(callback=lambda dc: deleted_dcs.append(dc) or 1),
            DeleteObject=_WinFunction(callback=lambda bitmap: deleted_bitmaps.append(bitmap) or 1),
        )

        with (
            mock.patch.object(startup_cover_runtime.sys, "platform", "win32"),
            mock.patch.dict(
                startup_cover_runtime.os.environ,
                {"BOT_STARTUP_MASK_ENABLED": "1", "BOT_NATIVE_STARTUP_COVER_ENABLED": "1"},
                clear=False,
            ),
            mock.patch.object(ctypes, "windll", SimpleNamespace(user32=user32, gdi32=gdi32)),
        ):
            cover = startup_cover_runtime._show_native_startup_cover()

        self.assertIsNone(cover)
        self.assertEqual([103], deleted_bitmaps)
        self.assertEqual([102], deleted_dcs)
        self.assertEqual([101], released_dcs)
        self.assertEqual([(102, 103), (102, 104)], selected_objects)


if __name__ == "__main__":
    unittest.main()
