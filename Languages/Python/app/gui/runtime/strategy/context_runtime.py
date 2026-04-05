from __future__ import annotations

from app.gui.shared.indicator_value_core import normalize_interval_token

_SIDE_LABEL_LOOKUP: dict[str, str] = {}
_BINANCE_INTERVAL_LOWER: set[str] = set()


def _canonical_side_from_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "BOTH"
    lower = raw.lower()
    if lower in _SIDE_LABEL_LOOKUP:
        return _SIDE_LABEL_LOOKUP[lower]
    if lower.startswith("buy"):
        return "BUY"
    if lower.startswith("sell"):
        return "SELL"
    return "BOTH"


def _canonicalize_interval(interval: str) -> str:
    raw = str(interval or "").strip()
    if not raw:
        return ""
    normalized = normalize_interval_token(raw)
    if normalized == "1mo":
        return "1M"
    if normalized and normalized in _BINANCE_INTERVAL_LOWER:
        return str(normalized)
    return ""


def _interval_identity_key(interval: str | None) -> str:
    raw = str(interval or "").strip()
    if not raw:
        return ""
    canonical = _canonicalize_interval(raw)
    if canonical:
        return canonical
    normalized = normalize_interval_token(raw)
    if normalized == "1mo":
        return "1M"
    if normalized:
        return str(normalized)
    return raw.lower()


def _resolve_dashboard_side(self) -> str:
    sel = self.side_combo.currentText() if hasattr(self, "side_combo") else ""
    return str(self._canonical_side_from_text(sel) or "BOTH")


def _collect_strategy_indicators(
    self,
    symbol: str,
    side_key: str,
    intervals: list[str] | set[str] | None = None,
) -> list[str]:
    indicators = set()
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    side_key = (side_key or "").upper()
    normalized_intervals: set[str] | None = None
    if intervals:
        normalized_intervals = set()
        for iv in intervals:
            key = _interval_identity_key(iv)
            if key:
                normalized_intervals.add(key)
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        if meta.get("symbol") != symbol:
            continue
        meta_interval = _interval_identity_key(meta.get("interval"))
        if normalized_intervals is not None:
            if meta_interval not in normalized_intervals:
                continue
        side_cfg = (meta.get("side") or "BOTH").upper()
        if side_key in ("", "SPOT") or side_cfg == "BOTH":
            pass
        elif side_key == "L" and side_cfg != "BUY":
            continue
        elif side_key == "S" and side_cfg != "SELL":
            continue
        override_inds = meta.get("override_indicators") or []
        configured_inds = meta.get("configured_indicators") or meta.get("indicators") or []
        selected = override_inds if override_inds else configured_inds
        for ind in selected:
            if ind:
                indicators.add(str(ind))
    return sorted(indicators)


def _position_stop_loss_enabled(self, symbol: str, side_key: str) -> bool:
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    symbol = str(symbol or "").strip().upper()
    side_key = (side_key or "").upper()
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        if str(meta.get("symbol") or "").strip().upper() != symbol:
            continue
        side_cfg = str(meta.get("side") or "BOTH").upper()
        if side_cfg == "BOTH":
            pass
        elif side_cfg == "BUY" and side_key != "L":
            continue
        elif side_cfg == "SELL" and side_key != "S":
            continue
        if meta.get("stop_loss_enabled"):
            return True
    return False


def bind_main_window_strategy_context_runtime(
    main_window_cls,
    *,
    side_label_lookup: dict[str, str],
    binance_interval_lower,
) -> None:
    global _SIDE_LABEL_LOOKUP
    global _BINANCE_INTERVAL_LOWER

    _SIDE_LABEL_LOOKUP = dict(side_label_lookup or {})
    _BINANCE_INTERVAL_LOWER = {str(value) for value in (binance_interval_lower or set())}

    main_window_cls._canonical_side_from_text = staticmethod(_canonical_side_from_text)
    main_window_cls._canonicalize_interval = staticmethod(_canonicalize_interval)
    main_window_cls._resolve_dashboard_side = _resolve_dashboard_side
    main_window_cls._collect_strategy_indicators = _collect_strategy_indicators
    main_window_cls._position_stop_loss_enabled = _position_stop_loss_enabled
