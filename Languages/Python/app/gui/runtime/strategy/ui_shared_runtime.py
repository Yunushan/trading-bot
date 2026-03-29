from __future__ import annotations

import re

from PyQt6 import QtCore, QtWidgets

_ACCOUNT_MODE_OPTIONS: tuple[str, ...] = ("Classic Trading",)
_STOP_LOSS_SCOPE_OPTIONS: tuple[str, ...] = ("per_trade",)


def configure_main_window_strategy_ui_shared_runtime(
    *,
    account_mode_options=None,
    stop_loss_scope_options=None,
) -> None:
    global _ACCOUNT_MODE_OPTIONS
    global _STOP_LOSS_SCOPE_OPTIONS

    _ACCOUNT_MODE_OPTIONS = tuple(account_mode_options or ("Classic Trading",))
    _STOP_LOSS_SCOPE_OPTIONS = tuple(stop_loss_scope_options or ("per_trade",))


def _register_runtime_active_exemption(self, widget):
    if widget is None:
        return
    try:
        exemptions = getattr(self, "_runtime_active_exemptions", None)
        if isinstance(exemptions, set):
            exemptions.add(widget)
    except Exception:
        pass


def _normalize_loop_override(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"\s+", "", text.lower())
    if re.match(r"^\d+(s|m|h|d|w)?$", cleaned):
        return cleaned
    return None


def _loop_choice_value(self, combo: QtWidgets.QComboBox | None) -> str:
    if combo is None:
        return ""
    try:
        data = combo.currentData()
    except Exception:
        data = ""
    if data is None:
        data = ""
    normalized = self._normalize_loop_override(data)
    if normalized:
        return normalized
    return ""


def _set_loop_combo_value(self, combo: QtWidgets.QComboBox | None, value: str | None) -> None:
    if combo is None:
        return
    target = _normalize_loop_override(value)
    if not target:
        target = ""
    idx = combo.findData(target)
    if idx < 0 and target:
        combo.addItem(target, target)
        idx = combo.count() - 1
    try:
        blocker = QtCore.QSignalBlocker(combo)
    except Exception:
        blocker = None
    if idx < 0:
        idx = 0
    combo.setCurrentIndex(idx)
    if blocker is not None:
        del blocker


def _default_account_mode_option() -> str:
    return _ACCOUNT_MODE_OPTIONS[0] if _ACCOUNT_MODE_OPTIONS else "Classic Trading"


def _default_stop_loss_scope_option() -> str:
    return _STOP_LOSS_SCOPE_OPTIONS[0] if _STOP_LOSS_SCOPE_OPTIONS else "per_trade"
