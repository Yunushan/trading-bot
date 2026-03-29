from __future__ import annotations

import os
from pathlib import Path

APP_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"
_native_icon_handles: list[int] = []
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _boot_log(message: str) -> None:
    if not _env_flag("BOT_BOOT_LOG"):
        return
    try:
        print(f"[boot] {message}", flush=True)
    except Exception:
        pass
