from __future__ import annotations


def build_meta_map(metadata: dict) -> dict[tuple[str, str], list[dict]]:
    meta_map: dict[tuple[str, str], list[dict]] = {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        sym = str(meta.get("symbol") or "").strip().upper()
        if not sym:
            continue
        interval = str(meta.get("interval") or "").strip()
        side_cfg = str(meta.get("side") or "BOTH").upper()
        stop_enabled = bool(meta.get("stop_loss_enabled"))
        indicators = list(meta.get("indicators") or [])
        if side_cfg == "BUY":
            sides = ["L"]
        elif side_cfg == "SELL":
            sides = ["S"]
        else:
            sides = ["L", "S"]
        for side in sides:
            meta_map.setdefault((sym, side), []).append(
                {
                    "interval": interval,
                    "indicators": indicators,
                    "stop_loss_enabled": stop_enabled,
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
