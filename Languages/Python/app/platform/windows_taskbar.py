from __future__ import annotations

from .windows_taskbar_metadata_runtime import (
    apply_taskbar_metadata,
    build_relaunch_command,
    ensure_app_user_model_id,
    ensure_taskbar_visible,
    resolve_relaunch_arguments,
    resolve_relaunch_executable,
)
from .windows_taskbar_shortcut_runtime import (
    _apply_shortcut_property_store,
    ensure_start_menu_shortcut,
)

__all__ = [
    "_apply_shortcut_property_store",
    "apply_taskbar_metadata",
    "build_relaunch_command",
    "ensure_app_user_model_id",
    "ensure_start_menu_shortcut",
    "ensure_taskbar_visible",
    "resolve_relaunch_arguments",
    "resolve_relaunch_executable",
]
