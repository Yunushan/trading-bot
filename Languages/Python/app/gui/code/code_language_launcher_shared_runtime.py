from __future__ import annotations

import subprocess
import sys
import time

from PyQt6 import QtWidgets


def poll_early_exit(proc: subprocess.Popen, timeout_s: float) -> int | None:
    deadline = time.time() + max(0.15, float(timeout_s))
    while time.time() < deadline:
        try:
            exit_code = proc.poll()
        except Exception:
            exit_code = 0
        if exit_code is not None:
            return exit_code
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
        time.sleep(0.05)
    return None


def apply_windows_startupinfo(popen_kwargs: dict[str, object]) -> None:
    if sys.platform != "win32":
        return
    popen_kwargs["creationflags"] = 0
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1
        popen_kwargs["startupinfo"] = startupinfo
    except Exception:
        pass


__all__ = ["apply_windows_startupinfo", "poll_early_exit"]
