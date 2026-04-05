from __future__ import annotations

from typing import cast

from ..shared.indicator_value_core import normalize_interval_token
from ..runtime.window import runtime as main_window_runtime


def _interval_sort_key(label: str) -> tuple[object, ...]:
    return cast(tuple[object, ...], main_window_runtime._mw_interval_sort_key(label))


def _normalize_indicator_list(raw) -> list[str]:
    return sorted(
        dict.fromkeys(
            str(value).strip()
            for value in (raw or [])
            if str(value).strip()
        )
    )


def build_meta_map(metadata: dict) -> dict[tuple[str, str], list[dict]]:
    merged_meta: dict[tuple[str, str, str, tuple[str, ...]], dict] = {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        sym = str(meta.get("symbol") or "").strip().upper()
        if not sym:
            continue
        interval_raw = str(meta.get("interval") or "").strip()
        interval = normalize_interval_token(interval_raw) or interval_raw.lower()
        side_cfg = str(meta.get("side") or "BOTH").upper()
        stop_enabled = bool(meta.get("stop_loss_enabled"))
        indicators = _normalize_indicator_list(meta.get("indicators"))
        if side_cfg == "BUY":
            sides = ["L"]
        elif side_cfg == "SELL":
            sides = ["S"]
        else:
            sides = ["L", "S"]
        for side in sides:
            merge_key = (sym, side, interval, tuple(indicators))
            existing = merged_meta.get(merge_key)
            if existing is None:
                merged_meta[merge_key] = {
                    "interval": interval,
                    "indicators": list(indicators),
                    "stop_loss_enabled": stop_enabled,
                }
                continue
            if interval and not existing.get("interval"):
                existing["interval"] = interval
            existing["stop_loss_enabled"] = bool(existing.get("stop_loss_enabled") or stop_enabled)

    meta_map: dict[tuple[str, str], list[dict]] = {}
    for (sym, side, _interval_key, _indicators_key), payload in sorted(
        merged_meta.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            _interval_sort_key(str(item[1].get("interval") or "")),
            item[0][3],
        ),
    ):
        meta_map.setdefault((sym, side), []).append(
            {
                "interval": str(payload.get("interval") or "").strip(),
                "indicators": list(payload.get("indicators") or []),
                "stop_loss_enabled": bool(payload.get("stop_loss_enabled")),
            }
        )
    return meta_map


def _normalize_interval(self, value):
    try:
        canon = self._canonicalize_interval(value)
    except Exception:
        canon = None
    if canon:
        return canon
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered or None
    return None
