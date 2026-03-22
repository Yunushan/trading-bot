from __future__ import annotations

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
    lower = raw.lower()
    if lower in _BINANCE_INTERVAL_LOWER:
        return lower
    if raw.upper() == "1M" or lower in {"1month", "1mo"}:
        return "1M"
    return ""


def _resolve_dashboard_side(self) -> str:
    sel = self.side_combo.currentText() if hasattr(self, "side_combo") else ""
    return self._canonical_side_from_text(sel)


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
        normalized_intervals = {
            self._canonicalize_interval(iv) or str(iv).strip().lower()
            for iv in intervals
            if iv
        }
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        if meta.get("symbol") != symbol:
            continue
        meta_interval = self._canonicalize_interval(meta.get("interval"))
        if normalized_intervals is not None:
            if meta_interval and meta_interval in normalized_intervals:
                pass
            elif meta_interval and meta_interval.replace(".", "") in normalized_intervals:
                pass
            elif meta.get("interval") and str(meta.get("interval")).strip().lower() in normalized_intervals:
                pass
            else:
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
