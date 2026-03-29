from __future__ import annotations


def update_closed_trade_registry(
    self,
    *,
    snap: dict,
    sym: str,
    side_key: str,
    close_fmt: str,
    pnl_reported,
    margin_reported,
    roi_reported,
    closed_history_max: int,
) -> None:
    try:
        registry = getattr(self, "_closed_trade_registry", None)
        if registry is None:
            registry = {}
            self._closed_trade_registry = registry
        registry_key = snap.get("ledger_id") or f"auto:{sym}:{side_key}:{close_fmt}"

        def _safe_float_report(value):
            try:
                return float(value) if value is not None else None
            except Exception:
                return None

        registry[registry_key] = {
            "pnl_value": _safe_float_report(pnl_reported),
            "margin_usdt": _safe_float_report(margin_reported),
            "roi_percent": _safe_float_report(roi_reported),
        }
        if len(registry) > closed_history_max:
            excess = len(registry) - closed_history_max
            if excess > 0:
                for old_key in list(registry.keys())[:excess]:
                    registry.pop(old_key, None)
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
    except Exception:
        pass
