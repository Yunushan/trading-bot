from __future__ import annotations

_FORMAT_INDICATOR_LIST = None
_NORMALIZE_CONNECTOR_BACKEND = None
_NORMALIZE_INDICATOR_VALUES = None
_NORMALIZE_STOP_LOSS_DICT = None


def configure_main_window_override_shared_runtime(
    *,
    format_indicator_list=None,
    normalize_connector_backend=None,
    normalize_indicator_values=None,
    normalize_stop_loss_dict=None,
) -> None:
    global _FORMAT_INDICATOR_LIST
    global _NORMALIZE_CONNECTOR_BACKEND
    global _NORMALIZE_INDICATOR_VALUES
    global _NORMALIZE_STOP_LOSS_DICT

    _FORMAT_INDICATOR_LIST = format_indicator_list
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict


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


def _normalize_indicator_values_list(payload):
    func = _NORMALIZE_INDICATOR_VALUES
    if callable(func):
        try:
            return func(payload)
        except Exception:
            pass
    if isinstance(payload, (list, tuple, set)):
        values = []
        for value in payload:
            text = str(value or "").strip()
            if text:
                values.append(text)
        return values
    return []


def _format_indicator_list_text(values) -> str:
    func = _FORMAT_INDICATOR_LIST
    if callable(func):
        try:
            return func(values)
        except Exception:
            pass
    return ", ".join(str(value) for value in values if str(value).strip())


def _normalize_connector_backend_value(value):
    func = _NORMALIZE_CONNECTOR_BACKEND
    if callable(func):
        try:
            return func(value)
        except Exception:
            pass
    return value


def _override_ctx(self, kind: str) -> dict:
    return getattr(self, "override_contexts", {}).get(kind, {})


def _override_config_list(self, kind: str) -> list:
    ctx = self._override_ctx(kind)
    cfg_key = ctx.get("config_key")
    if not cfg_key:
        return []
    lst = self.config.setdefault(cfg_key, [])
    if not isinstance(lst, list):
        if isinstance(lst, (tuple, set)):
            lst = list(lst)
        elif isinstance(lst, dict):
            lst = [dict(lst)]
        else:
            lst = []
        self.config[cfg_key] = lst
    if kind == "backtest":
        try:
            self.backtest_config[cfg_key] = list(lst)
        except Exception:
            pass
    return lst


def _get_selected_indicator_keys(self, kind: str) -> list[str]:
    try:
        if kind == "runtime":
            widgets = getattr(self, "indicator_widgets", {}) or {}
        else:
            widgets = getattr(self, "backtest_indicator_widgets", {}) or {}
        keys: list[str] = []
        for key, control in widgets.items():
            cb = control[0] if isinstance(control, (tuple, list)) and control else None
            if cb and cb.isChecked():
                keys.append(str(key))
        if keys:
            return keys
    except Exception:
        pass
    try:
        cfg = self.config if kind == "runtime" else self.backtest_config
        indicators_cfg = (cfg or {}).get("indicators", {}) or {}
        return [key for key, params in indicators_cfg.items() if params.get("enabled")]
    except Exception:
        return []


def _build_clean_override_entry(self, kind: str, entry) -> tuple[dict | None, list[str], int | None, dict]:
    sym = str((entry or {}).get("symbol") or "").strip().upper()
    iv = str((entry or {}).get("interval") or "").strip()
    if not sym or not iv:
        return None, [], None, {}

    indicators_raw = entry.get("indicators")
    indicator_values = _normalize_indicator_values_list(indicators_raw)
    controls = self._normalize_strategy_controls(kind, entry.get("strategy_controls"))

    leverage_val = None
    if isinstance(controls, dict):
        lev_ctrl = controls.get("leverage")
        if lev_ctrl is not None:
            try:
                leverage_val = max(1, int(lev_ctrl))
            except Exception:
                leverage_val = None
    if leverage_val is None:
        lev_entry_raw = entry.get("leverage")
        if lev_entry_raw is not None:
            try:
                leverage_val = max(1, int(lev_entry_raw))
            except Exception:
                leverage_val = None

    entry_clean = {"symbol": sym, "interval": iv}
    if indicator_values:
        entry_clean["indicators"] = list(indicator_values)

    loop_val = entry.get("loop_interval_override")
    if not loop_val and isinstance(controls, dict):
        loop_val = controls.get("loop_interval_override")
    loop_val = self._normalize_loop_override(loop_val)
    if loop_val:
        entry_clean["loop_interval_override"] = loop_val

    if controls:
        entry_clean["strategy_controls"] = controls
        stop_cfg = controls.get("stop_loss")
        if isinstance(stop_cfg, dict):
            entry_clean["stop_loss"] = _normalize_stop_loss(stop_cfg)
        backend_ctrl = controls.get("connector_backend")
        if backend_ctrl:
            entry_clean["connector_backend"] = backend_ctrl

    if leverage_val is not None:
        entry_clean["leverage"] = leverage_val
        if isinstance(controls, dict):
            controls["leverage"] = leverage_val

    if "stop_loss" not in entry_clean and entry.get("stop_loss"):
        entry_clean["stop_loss"] = _normalize_stop_loss(entry.get("stop_loss"))

    return entry_clean, indicator_values, leverage_val, controls
