from __future__ import annotations

from PyQt6 import QtCore

_NORMALIZE_STOP_LOSS_DICT = None
_STOP_LOSS_MODE_ORDER: tuple[str, ...] = ()
_STOP_LOSS_SCOPE_OPTIONS: tuple[str, ...] = ()


def configure_main_window_stop_loss_shared_runtime(
    *,
    normalize_stop_loss_dict=None,
    stop_loss_mode_order=None,
    stop_loss_scope_options=None,
) -> None:
    global _NORMALIZE_STOP_LOSS_DICT
    global _STOP_LOSS_MODE_ORDER
    global _STOP_LOSS_SCOPE_OPTIONS

    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _STOP_LOSS_MODE_ORDER = tuple(stop_loss_mode_order or ())
    _STOP_LOSS_SCOPE_OPTIONS = tuple(stop_loss_scope_options or ())


def _normalize_stop_loss(payload):
    func = _NORMALIZE_STOP_LOSS_DICT
    if callable(func):
        try:
            return func(payload)
        except Exception:
            pass
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _default_stop_loss_mode() -> str:
    return _STOP_LOSS_MODE_ORDER[0] if _STOP_LOSS_MODE_ORDER else "usdt"


def _default_stop_loss_scope() -> str:
    return _STOP_LOSS_SCOPE_OPTIONS[0] if _STOP_LOSS_SCOPE_OPTIONS else "per_trade"


def _coerce_stop_loss_mode(value) -> str:
    if value in _STOP_LOSS_MODE_ORDER:
        return str(value)
    return _default_stop_loss_mode()


def _coerce_stop_loss_scope(value) -> str:
    if value in _STOP_LOSS_SCOPE_OPTIONS:
        return str(value)
    return _default_stop_loss_scope()


def _set_combo_data_value(combo, value, fallback) -> None:
    if combo is None:
        return
    combo.blockSignals(True)
    idx = combo.findData(value)
    if idx < 0:
        idx = combo.findData(fallback)
        if idx < 0:
            idx = 0
    combo.setCurrentIndex(idx)
    combo.blockSignals(False)


def _set_checkbox_checked(checkbox, checked: bool) -> None:
    if checkbox is None:
        return
    checkbox.blockSignals(True)
    checkbox.setChecked(bool(checked))
    checkbox.blockSignals(False)


def _set_spin_value(spin, value: float) -> None:
    if spin is None:
        return
    spin.blockSignals(True)
    spin.setValue(float(value))
    spin.blockSignals(False)


def _sync_stop_loss_widgets(
    *,
    cfg: dict,
    checkbox=None,
    combo=None,
    usdt_spin=None,
    pct_spin=None,
    scope_combo=None,
    controls_locked: bool,
) -> None:
    enabled = bool(cfg.get("enabled"))
    mode = str(cfg.get("mode") or _default_stop_loss_mode()).lower()
    scope = str(cfg.get("scope") or _default_stop_loss_scope()).lower()

    _set_checkbox_checked(checkbox, enabled)
    _set_combo_data_value(combo, mode, _default_stop_loss_mode())
    if combo is not None:
        combo.setEnabled(enabled and not controls_locked)

    _set_spin_value(usdt_spin, float(cfg.get("usdt", 0.0)))
    if usdt_spin is not None:
        usdt_spin.setEnabled(enabled and not controls_locked and mode in ("usdt", "both"))

    _set_spin_value(pct_spin, float(cfg.get("percent", 0.0)))
    if pct_spin is not None:
        pct_spin.setEnabled(enabled and not controls_locked and mode in ("percent", "both"))

    _set_combo_data_value(scope_combo, scope, _default_stop_loss_scope())
    if scope_combo is not None:
        scope_combo.setEnabled(enabled and not controls_locked)


def _checked_from_state(state) -> bool:
    return state == QtCore.Qt.CheckState.Checked or bool(state)
