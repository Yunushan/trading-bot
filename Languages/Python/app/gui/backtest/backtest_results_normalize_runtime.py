from __future__ import annotations

from dataclasses import asdict, is_dataclass

from app.config import MDD_LOGIC_DEFAULT, MDD_LOGIC_OPTIONS
from ..shared.helper_runtime import _normalize_datetime_pair

_MDD_LOGIC_LABELS: dict[str, str] = {}
_normalize_loop_override = lambda value: None  # type: ignore


def configure_backtest_results_normalize_runtime(
    *,
    mdd_logic_labels: dict[str, str],
    normalize_loop_override,
) -> None:
    global _MDD_LOGIC_LABELS
    global _normalize_loop_override

    _MDD_LOGIC_LABELS = dict(mdd_logic_labels or {})
    if callable(normalize_loop_override):
        _normalize_loop_override = normalize_loop_override


def _normalize_backtest_run(run):
    if is_dataclass(run):
        data = asdict(run)
    elif isinstance(run, dict):
        data = dict(run)
    else:
        indicator_keys = getattr(run, "indicator_keys", [])
        if indicator_keys is None:
            indicator_keys = []
        elif not isinstance(indicator_keys, (list, tuple)):
            indicator_keys = [indicator_keys]
        data = {
            "symbol": getattr(run, "symbol", ""),
            "interval": getattr(run, "interval", ""),
            "logic": getattr(run, "logic", ""),
            "indicator_keys": list(indicator_keys),
            "trades": getattr(run, "trades", 0),
            "roi_value": getattr(run, "roi_value", 0.0),
            "roi_percent": getattr(run, "roi_percent", 0.0),
            "max_drawdown_value": getattr(run, "max_drawdown_value", 0.0),
            "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
            "max_drawdown_during_value": getattr(
                run,
                "max_drawdown_during_value",
                getattr(run, "max_drawdown_value", 0.0),
            ),
            "max_drawdown_during_percent": getattr(
                run,
                "max_drawdown_during_percent",
                getattr(run, "max_drawdown_percent", 0.0),
            ),
            "max_drawdown_result_value": getattr(
                run,
                "max_drawdown_result_value",
                0.0,
            ),
            "max_drawdown_result_percent": getattr(
                run,
                "max_drawdown_result_percent",
                0.0,
            ),
            "mdd_logic": getattr(run, "mdd_logic", None),
        }
    data.setdefault("indicator_keys", [])
    keys = data.get("indicator_keys") or []
    if not isinstance(keys, (list, tuple)):
        keys = [keys]
    data["indicator_keys"] = [str(k) for k in keys if k is not None]
    try:
        data["trades"] = int(data.get("trades", 0) or 0)
    except Exception:
        data["trades"] = 0
    for key in (
        "roi_value",
        "roi_percent",
        "max_drawdown_value",
        "max_drawdown_percent",
        "max_drawdown_during_value",
        "max_drawdown_during_percent",
        "max_drawdown_result_value",
        "max_drawdown_result_percent",
    ):
        try:
            data[key] = float(data.get(key, 0.0) or 0.0)
        except Exception:
            data[key] = 0.0
    for pct_key in ("position_pct",):
        try:
            data[pct_key] = float(data.get(pct_key, 0.0) or 0.0)
        except Exception:
            data[pct_key] = 0.0
    for lev_key in ("leverage",):
        try:
            data[lev_key] = float(data.get(lev_key, 0.0) or 0.0)
        except Exception:
            data[lev_key] = 0.0
    for bool_key in ("stop_loss_enabled",):
        data[bool_key] = bool(data.get(bool_key, False))
    for str_key in (
        "symbol",
        "interval",
        "logic",
        "stop_loss_mode",
        "stop_loss_scope",
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
    ):
        val = data.get(str_key)
        data[str_key] = str(val or "").strip()
    mdd_logic_val = str(data.get("mdd_logic", "") or "").lower()
    if mdd_logic_val not in MDD_LOGIC_OPTIONS:
        mdd_logic_val = MDD_LOGIC_DEFAULT
    data["mdd_logic"] = mdd_logic_val
    data["mdd_logic_display"] = _MDD_LOGIC_LABELS.get(
        mdd_logic_val,
        mdd_logic_val.replace("_", " ").title(),
    )
    loop_raw = data.get("loop_interval_override")
    if loop_raw is None:
        if isinstance(run, dict):
            loop_raw = run.get("loop_interval_override")
        else:
            loop_raw = getattr(run, "loop_interval_override", None)
    if loop_raw is None:
        strategy_controls = data.get("strategy_controls")
        if isinstance(strategy_controls, dict):
            loop_raw = strategy_controls.get("loop_interval_override")
    loop_normalized = _normalize_loop_override(loop_raw)
    data["loop_interval_override"] = loop_normalized or ""
    start_iso, start_display = _normalize_datetime_pair(data.get("start"))
    if not start_iso and hasattr(run, "start"):
        start_iso, start_display = _normalize_datetime_pair(getattr(run, "start"))
    data["start"] = start_iso
    data["start_display"] = start_display or "-"
    end_iso, end_display = _normalize_datetime_pair(data.get("end"))
    if not end_iso and hasattr(run, "end"):
        end_iso, end_display = _normalize_datetime_pair(getattr(run, "end"))
    data["end"] = end_iso
    data["end_display"] = end_display or "-"
    pos_pct_fraction = data.get("position_pct", 0.0)
    try:
        pos_pct_fraction = float(pos_pct_fraction or 0.0)
    except Exception:
        pos_pct_fraction = 0.0
    data["position_pct"] = pos_pct_fraction
    data["position_pct_display"] = f"{max(pos_pct_fraction, 0.0) * 100.0:.2f}%"
    stop_enabled = data.get("stop_loss_enabled", False)
    stop_mode = data.get("stop_loss_mode", "")
    stop_usdt = data.get("stop_loss_usdt", 0.0)
    stop_percent = data.get("stop_loss_percent", 0.0)
    stop_scope = data.get("stop_loss_scope", "")
    try:
        stop_usdt = float(stop_usdt or 0.0)
    except Exception:
        stop_usdt = 0.0
    try:
        stop_percent = float(stop_percent or 0.0)
    except Exception:
        stop_percent = 0.0
    data["stop_loss_usdt"] = stop_usdt
    data["stop_loss_percent"] = stop_percent
    if stop_enabled:
        parts = []
        if stop_mode:
            parts.append(stop_mode)
        if stop_scope:
            parts.append(stop_scope)
        if stop_usdt > 0.0:
            parts.append(f"{stop_usdt:.2f} USDT")
        if stop_percent > 0.0:
            parts.append(f"{stop_percent:.2f}%")
        data["stop_loss_display"] = "Enabled" + (
            f" ({', '.join(parts)})" if parts else ""
        )
    else:
        data["stop_loss_display"] = "Disabled"
    if not data.get("margin_mode"):
        data["margin_mode"] = ""
    if not data.get("position_mode"):
        data["position_mode"] = ""
    if not data.get("assets_mode"):
        data["assets_mode"] = ""
    if not data.get("account_mode"):
        data["account_mode"] = ""
    data["leverage_display"] = f"{data.get('leverage', 0.0):.2f}x"
    max_dd_during_pct = data.get(
        "max_drawdown_during_percent",
        data.get("max_drawdown_percent", 0.0),
    )
    try:
        max_dd_during_pct = float(max_dd_during_pct or 0.0)
    except Exception:
        max_dd_during_pct = 0.0
    max_dd_during_val = data.get(
        "max_drawdown_during_value",
        data.get("max_drawdown_value", 0.0),
    )
    try:
        max_dd_during_val = float(max_dd_during_val or 0.0)
    except Exception:
        max_dd_during_val = 0.0
    max_dd_result_pct = data.get("max_drawdown_result_percent", 0.0)
    try:
        max_dd_result_pct = float(max_dd_result_pct or 0.0)
    except Exception:
        max_dd_result_pct = 0.0
    max_dd_result_val = data.get("max_drawdown_result_value", 0.0)
    try:
        max_dd_result_val = float(max_dd_result_val or 0.0)
    except Exception:
        max_dd_result_val = 0.0
    data["max_drawdown_percent"] = max_dd_during_pct
    data["max_drawdown_value"] = max_dd_during_val
    data["max_drawdown_during_percent"] = max_dd_during_pct
    data["max_drawdown_during_value"] = max_dd_during_val
    data["max_drawdown_result_percent"] = max_dd_result_pct
    data["max_drawdown_result_value"] = max_dd_result_val
    if max_dd_during_pct > 0.0:
        data["max_drawdown_during_display"] = f"{-abs(max_dd_during_pct):.2f}%"
    else:
        data["max_drawdown_during_display"] = "0.00%"
    if max_dd_during_val > 0.0:
        data["max_drawdown_during_value_display"] = (
            f"{-abs(max_dd_during_val):.2f} USDT"
        )
    else:
        data["max_drawdown_during_value_display"] = "0.00 USDT"
    if max_dd_result_pct > 0.0:
        data["max_drawdown_result_display"] = f"{-abs(max_dd_result_pct):.2f}%"
    else:
        data["max_drawdown_result_display"] = "0.00%"
    if max_dd_result_val > 0.0:
        data["max_drawdown_result_value_display"] = (
            f"{-abs(max_dd_result_val):.2f} USDT"
        )
    else:
        data["max_drawdown_result_value_display"] = "0.00 USDT"
    data["symbol"] = str(data.get("symbol") or "")
    data["interval"] = str(data.get("interval") or "")
    data["logic"] = str(data.get("logic") or "")
    return data
