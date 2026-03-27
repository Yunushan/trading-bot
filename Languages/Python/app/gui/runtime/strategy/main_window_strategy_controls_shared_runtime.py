from __future__ import annotations

_NORMALIZE_STOP_LOSS_DICT = None
_NORMALIZE_CONNECTOR_BACKEND = None
_SIDE_LABELS: dict[str, str] = {}


def configure_main_window_strategy_controls_shared_runtime(
    *,
    side_labels=None,
    normalize_stop_loss_dict=None,
    normalize_connector_backend=None,
) -> None:
    global _NORMALIZE_STOP_LOSS_DICT
    global _NORMALIZE_CONNECTOR_BACKEND
    global _SIDE_LABELS

    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _SIDE_LABELS = dict(side_labels or {})


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


def _normalize_connector_backend_value(value):
    func = _NORMALIZE_CONNECTOR_BACKEND
    if callable(func):
        try:
            return func(value)
        except Exception:
            pass
    return value


def _normalize_position_pct_units(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"percent", "%", "perc", "percentage"}:
        return "percent"
    if text in {"fraction", "decimal", "ratio"}:
        return "fraction"
    return ""


def side_labels() -> dict[str, str]:
    return dict(_SIDE_LABELS)
