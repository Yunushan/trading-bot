from __future__ import annotations

import os
import sys


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _configure_startup_window_suppression_defaults() -> None:
    """Set safe Windows startup suppression defaults unless user already configured them."""
    if sys.platform != "win32":
        return
    if _env_flag("BOT_NO_STARTUP_WINDOW_SUPPRESS"):
        return
    if not _env_flag("BOT_FORCE_STARTUP_WINDOW_HOOKS"):
        os.environ["BOT_DISABLE_STARTUP_WINDOW_HOOKS"] = "1"
        os.environ.setdefault("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS", "1")
        os.environ.setdefault("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS", "2500")
        os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_MS", "3500")
        os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS", "5")
        os.environ.setdefault("BOT_STARTUP_MASK_ENABLED", "0")
        os.environ.setdefault("BOT_STARTUP_MASK_MODE", "snapshot")
        os.environ.setdefault("BOT_STARTUP_MASK_HIDE_MS", "1400")
        os.environ.setdefault("BOT_STARTUP_MASK_SCOPE", "primary")
        os.environ.setdefault("BOT_NATIVE_STARTUP_COVER_ENABLED", "0")
        os.environ.setdefault("BOT_STARTUP_SPLASH_TOPMOST", "0")
        os.environ.setdefault("BOT_STARTUP_REVEAL_DELAY_MS", "0")
        os.environ.setdefault("BOT_PREWARM_WEBENGINE", "0")
        return
    if _env_flag("BOT_DISABLE_STARTUP_WINDOW_HOOKS"):
        return

    os.environ.setdefault("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS", "2500")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_MS", "2500")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS", "20")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_FAST_MS", "900")
    os.environ.setdefault("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS", "8")
    os.environ.setdefault("BOT_STARTUP_WINDOW_SUPPRESS_GLOBAL_HOOK", "0")
    os.environ.setdefault("BOT_TASKBAR_METADATA_DELAY_MS", "1200")
    os.environ.setdefault("BOT_TASKBAR_ENSURE_MS", "0")
    os.environ.setdefault("BOT_TASKBAR_ENSURE_START_DELAY_MS", "1200")
    os.environ.setdefault("BOT_PRIME_NATIVE_CHART_HOST", "1")
    os.environ.setdefault("BOT_STARTUP_REVEAL_DELAY_MS", "0")
    os.environ.setdefault("BOT_STARTUP_WINDOW_HOOK_AUTO_UNINSTALL_MS", "900")

    if _env_flag("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS"):
        return

    os.environ.setdefault("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS", "0")
    os.environ.setdefault("BOT_CBT_STARTUP_WINDOW_SUPPRESS_DURATION_MS", "2500")
    os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_MS", "0")
    os.environ.setdefault("BOT_CBT_THREAD_HOOK_SCAN_INTERVAL_MS", "80")
