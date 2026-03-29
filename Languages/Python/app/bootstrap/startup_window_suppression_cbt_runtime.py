from __future__ import annotations

import sys

from . import startup_window_suppression_cbt_state_runtime as cbt_state
from .startup_window_suppression_cbt_api_runtime import build_cbt_api
from .startup_window_suppression_cbt_cleanup_runtime import uninstall_cbt_startup_window_suppression
from .startup_window_suppression_cbt_install_runtime import bootstrap_cbt_thread_hooks
from .startup_window_suppression_cbt_proc_runtime import build_cbt_window_proc
from .startup_window_suppression_shared_runtime import _env_flag


def _install_cbt_startup_window_suppression() -> None:
    """Best-effort: clear WS_VISIBLE at create-time for tiny helper windows (Windows only)."""
    if sys.platform != "win32" or cbt_state._CBT_STARTUP_WINDOW_PROC is not None:
        return
    if not _env_flag("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS"):
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS") or _env_flag("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS"):
        return

    api, cbt_proc_cls, cbt_createwnd_cls = build_cbt_api()
    if api is None:
        return

    if cbt_state._CBT_STARTUP_HELPER_COVER_LOCK is None:
        cbt_state._CBT_STARTUP_HELPER_COVER_LOCK = api.threading.Lock()

    cbt_state._CBT_STARTUP_WINDOW_PROC = build_cbt_window_proc(
        api,
        cbt_proc_cls,
        cbt_createwnd_cls,
    )
    bootstrap_cbt_thread_hooks(api)


def _uninstall_cbt_startup_window_suppression() -> None:
    if sys.platform != "win32":
        return
    uninstall_cbt_startup_window_suppression()
