from __future__ import annotations

from .stop_loss_shared_runtime import (
    _checked_from_state,
    _coerce_stop_loss_mode,
    _coerce_stop_loss_scope,
    _normalize_stop_loss,
    _sync_stop_loss_widgets,
)


def _runtime_stop_loss_update(self, **updates):
    current = _normalize_stop_loss(self.config.get("stop_loss"))
    current.update(updates)
    current = _normalize_stop_loss(current)
    self.config["stop_loss"] = current
    return current


def _update_runtime_stop_loss_widgets(self):
    cfg = _normalize_stop_loss(self.config.get("stop_loss"))
    self.config["stop_loss"] = cfg
    _sync_stop_loss_widgets(
        cfg=cfg,
        checkbox=getattr(self, "stop_loss_enable_cb", None),
        combo=getattr(self, "stop_loss_mode_combo", None),
        usdt_spin=getattr(self, "stop_loss_usdt_spin", None),
        pct_spin=getattr(self, "stop_loss_percent_spin", None),
        scope_combo=getattr(self, "stop_loss_scope_combo", None),
        controls_locked=bool(getattr(self, "_bot_active", False)),
    )


def _on_runtime_stop_loss_enabled(self, checked: bool):
    self._runtime_stop_loss_update(enabled=_checked_from_state(checked))
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_mode_changed(self):
    combo = getattr(self, "stop_loss_mode_combo", None)
    mode = combo.currentData() if combo is not None else None
    self._runtime_stop_loss_update(mode=_coerce_stop_loss_mode(mode))
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_scope_changed(self):
    combo = getattr(self, "stop_loss_scope_combo", None)
    scope = combo.currentData() if combo is not None else None
    self._runtime_stop_loss_update(scope=_coerce_stop_loss_scope(scope))
    self._update_runtime_stop_loss_widgets()


def _on_runtime_stop_loss_value_changed(self, kind: str, value: float):
    if kind == "usdt":
        self._runtime_stop_loss_update(usdt=max(0.0, float(value)))
    elif kind == "percent":
        self._runtime_stop_loss_update(percent=max(0.0, float(value)))
    self._update_runtime_stop_loss_widgets()
