from __future__ import annotations

import copy

from PyQt6 import QtCore

_NORMALIZE_STOP_LOSS_DICT = None
_STOP_LOSS_MODE_ORDER: tuple[str, ...] = ()
_STOP_LOSS_SCOPE_OPTIONS: tuple[str, ...] = ()


def bind_main_window_stop_loss_runtime(
    main_window_cls,
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

    main_window_cls._runtime_stop_loss_update = _runtime_stop_loss_update
    main_window_cls._update_runtime_stop_loss_widgets = _update_runtime_stop_loss_widgets
    main_window_cls._on_runtime_stop_loss_enabled = _on_runtime_stop_loss_enabled
    main_window_cls._on_runtime_stop_loss_mode_changed = _on_runtime_stop_loss_mode_changed
    main_window_cls._on_runtime_stop_loss_scope_changed = _on_runtime_stop_loss_scope_changed
    main_window_cls._on_runtime_stop_loss_value_changed = _on_runtime_stop_loss_value_changed
    main_window_cls._backtest_stop_loss_update = _backtest_stop_loss_update
    main_window_cls._update_backtest_stop_loss_widgets = _update_backtest_stop_loss_widgets
    main_window_cls._on_backtest_stop_loss_enabled = _on_backtest_stop_loss_enabled
    main_window_cls._on_backtest_stop_loss_mode_changed = _on_backtest_stop_loss_mode_changed
    main_window_cls._on_backtest_stop_loss_scope_changed = _on_backtest_stop_loss_scope_changed
    main_window_cls._on_backtest_stop_loss_value_changed = _on_backtest_stop_loss_value_changed


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


def _runtime_stop_loss_update(self, **updates):
    current = _normalize_stop_loss(self.config.get("stop_loss"))
    current.update(updates)
    current = _normalize_stop_loss(current)
    self.config["stop_loss"] = current
    return current


def _update_runtime_stop_loss_widgets(self):
    cfg = _normalize_stop_loss(self.config.get("stop_loss"))
    self.config["stop_loss"] = cfg
    enabled = bool(cfg.get("enabled"))
    mode = str(cfg.get("mode") or "usdt").lower()
    scope = str(cfg.get("scope") or "per_trade").lower()
    bot_active = bool(getattr(self, "_bot_active", False))
    checkbox = getattr(self, "stop_loss_enable_cb", None)
    combo = getattr(self, "stop_loss_mode_combo", None)
    usdt_spin = getattr(self, "stop_loss_usdt_spin", None)
    pct_spin = getattr(self, "stop_loss_percent_spin", None)
    scope_combo = getattr(self, "stop_loss_scope_combo", None)
    if checkbox is not None:
        checkbox.blockSignals(True)
        checkbox.setChecked(enabled)
        checkbox.blockSignals(False)
    if combo is not None:
        combo.blockSignals(True)
        idx = combo.findData(mode)
        if idx < 0:
            idx = combo.findData(_STOP_LOSS_MODE_ORDER[0]) if _STOP_LOSS_MODE_ORDER else -1
            if idx < 0:
                idx = 0
        combo.setCurrentIndex(idx)
        combo.setEnabled(enabled and not bot_active)
        combo.blockSignals(False)
    if usdt_spin is not None:
        usdt_spin.blockSignals(True)
        usdt_spin.setValue(float(cfg.get("usdt", 0.0)))
        usdt_spin.blockSignals(False)
        usdt_spin.setEnabled(enabled and not bot_active and mode in ("usdt", "both"))
    if pct_spin is not None:
        pct_spin.blockSignals(True)
        pct_spin.setValue(float(cfg.get("percent", 0.0)))
        pct_spin.blockSignals(False)
        pct_spin.setEnabled(enabled and not bot_active and mode in ("percent", "both"))
    if scope_combo is not None:
        scope_combo.blockSignals(True)
        idx_scope = scope_combo.findData(scope)
        if idx_scope < 0:
            idx_scope = scope_combo.findData(_STOP_LOSS_SCOPE_OPTIONS[0]) if _STOP_LOSS_SCOPE_OPTIONS else -1
            if idx_scope < 0:
                idx_scope = 0
        scope_combo.setCurrentIndex(idx_scope)
        scope_combo.setEnabled(enabled and not bot_active)
        scope_combo.blockSignals(False)


def _on_runtime_stop_loss_enabled(self, checked: bool):
    self._runtime_stop_loss_update(enabled=bool(checked))
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_mode_changed(self):
    combo = getattr(self, "stop_loss_mode_combo", None)
    mode = combo.currentData() if combo is not None else None
    if mode not in _STOP_LOSS_MODE_ORDER:
        mode = _STOP_LOSS_MODE_ORDER[0] if _STOP_LOSS_MODE_ORDER else "usdt"
    self._runtime_stop_loss_update(mode=mode)
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_scope_changed(self):
    combo = getattr(self, "stop_loss_scope_combo", None)
    scope = combo.currentData() if combo is not None else None
    if scope not in _STOP_LOSS_SCOPE_OPTIONS:
        scope = _STOP_LOSS_SCOPE_OPTIONS[0] if _STOP_LOSS_SCOPE_OPTIONS else "per_trade"
    self._runtime_stop_loss_update(scope=scope)
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_value_changed(self, kind: str, value: float):
    if kind == "usdt":
        self._runtime_stop_loss_update(usdt=max(0.0, float(value)))
    elif kind == "percent":
        self._runtime_stop_loss_update(percent=max(0.0, float(value)))
    self._update_runtime_stop_loss_widgets()


def _backtest_stop_loss_update(self, **updates):
    current = _normalize_stop_loss(self.backtest_config.get("stop_loss"))
    current.update(updates)
    current = _normalize_stop_loss(current)
    self.backtest_config["stop_loss"] = current
    backtest_cfg = self.config.setdefault("backtest", {})
    backtest_cfg["stop_loss"] = copy.deepcopy(current)
    return current


def _update_backtest_stop_loss_widgets(self):
    cfg = _normalize_stop_loss(self.backtest_config.get("stop_loss"))
    self.backtest_config["stop_loss"] = cfg
    self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(cfg)
    enabled = bool(cfg.get("enabled"))
    mode = str(cfg.get("mode") or "usdt").lower()
    scope = str(cfg.get("scope") or "per_trade").lower()
    checkbox = getattr(self, "backtest_stop_loss_enable_cb", None)
    combo = getattr(self, "backtest_stop_loss_mode_combo", None)
    usdt_spin = getattr(self, "backtest_stop_loss_usdt_spin", None)
    pct_spin = getattr(self, "backtest_stop_loss_percent_spin", None)
    scope_combo = getattr(self, "backtest_stop_loss_scope_combo", None)
    if checkbox is not None:
        checkbox.blockSignals(True)
        checkbox.setChecked(enabled)
        checkbox.blockSignals(False)
    if combo is not None:
        combo.blockSignals(True)
        idx = combo.findData(mode)
        if idx < 0:
            idx = combo.findData(_STOP_LOSS_MODE_ORDER[0]) if _STOP_LOSS_MODE_ORDER else -1
            if idx < 0:
                idx = 0
        combo.setCurrentIndex(idx)
        combo.setEnabled(enabled)
        combo.blockSignals(False)
    if usdt_spin is not None:
        usdt_spin.blockSignals(True)
        usdt_spin.setValue(float(cfg.get("usdt", 0.0)))
        usdt_spin.blockSignals(False)
        usdt_spin.setEnabled(enabled and mode in ("usdt", "both"))
    if pct_spin is not None:
        pct_spin.blockSignals(True)
        pct_spin.setValue(float(cfg.get("percent", 0.0)))
        pct_spin.blockSignals(False)
        pct_spin.setEnabled(enabled and mode in ("percent", "both"))
    if scope_combo is not None:
        scope_combo.blockSignals(True)
        idx_scope = scope_combo.findData(scope)
        if idx_scope < 0:
            idx_scope = scope_combo.findData(_STOP_LOSS_SCOPE_OPTIONS[0]) if _STOP_LOSS_SCOPE_OPTIONS else -1
            if idx_scope < 0:
                idx_scope = 0
        scope_combo.setCurrentIndex(idx_scope)
        scope_combo.setEnabled(enabled)
        scope_combo.blockSignals(False)


def _on_backtest_stop_loss_enabled(self, checked: bool):
    self._backtest_stop_loss_update(enabled=bool(checked))
    self._update_backtest_stop_loss_widgets()


def _on_backtest_stop_loss_mode_changed(self):
    combo = getattr(self, "backtest_stop_loss_mode_combo", None)
    mode = combo.currentData() if combo is not None else None
    if mode not in _STOP_LOSS_MODE_ORDER:
        mode = _STOP_LOSS_MODE_ORDER[0] if _STOP_LOSS_MODE_ORDER else "usdt"
    self._backtest_stop_loss_update(mode=mode)
    self._update_backtest_stop_loss_widgets()


def _on_backtest_stop_loss_scope_changed(self):
    combo = getattr(self, "backtest_stop_loss_scope_combo", None)
    scope = combo.currentData() if combo is not None else None
    if scope not in _STOP_LOSS_SCOPE_OPTIONS:
        scope = _STOP_LOSS_SCOPE_OPTIONS[0] if _STOP_LOSS_SCOPE_OPTIONS else "per_trade"
    self._backtest_stop_loss_update(scope=scope)
    self._update_backtest_stop_loss_widgets()


def _on_backtest_stop_loss_value_changed(self, kind: str, value: float):
    if kind == "usdt":
        self._backtest_stop_loss_update(usdt=max(0.0, float(value)))
    elif kind == "percent":
        self._backtest_stop_loss_update(percent=max(0.0, float(value)))
    self._update_backtest_stop_loss_widgets()
