from __future__ import annotations

from .indicator_value_core import (
    _ACTION_RE,
    _FLOAT_RE,
    format_interval_display_token,
    indicator_short_label,
)


def split_trigger_desc(desc: str | None) -> list[str]:
    if not desc:
        return []
    return [segment.strip() for segment in str(desc).split("|") if segment.strip()]


def _indicator_segment_match(
    indicator_key: str,
    segment: str,
    *,
    canonicalize_indicator_key,
) -> bool:
    key_norm = canonicalize_indicator_key(indicator_key) or str(indicator_key or "").strip().lower()
    seg_low = segment.lower()
    if not key_norm or not seg_low:
        return False
    if key_norm == "stoch_rsi":
        return "stochrsi" in seg_low
    if key_norm == "rsi":
        return "rsi" in seg_low and "stochrsi" not in seg_low
    if key_norm == "willr":
        return "williams" in seg_low
    token = key_norm.replace("_", "")
    return token in seg_low if token else False


def _extract_indicator_metrics(
    indicator_key: str,
    segments: list[str],
    *,
    canonicalize_indicator_key,
) -> tuple[str | None, str | None]:
    if not segments:
        return None, None
    value_str: str | None = None
    action_str: str | None = None
    for seg in segments:
        if not _indicator_segment_match(
            indicator_key,
            seg,
            canonicalize_indicator_key=canonicalize_indicator_key,
        ):
            continue
        if "=" in seg and "->" not in seg:
            match = _FLOAT_RE.search(seg.split("=", 1)[1])
            if match:
                value_str = match.group(0)
                break
    if value_str is None:
        for seg in segments:
            if not _indicator_segment_match(
                indicator_key,
                seg,
                canonicalize_indicator_key=canonicalize_indicator_key,
            ):
                continue
            if "->" in seg:
                continue
            match = _FLOAT_RE.search(seg)
            if match:
                value_str = match.group(0)
                break
    if value_str is None:
        for seg in segments:
            if not _indicator_segment_match(
                indicator_key,
                seg,
                canonicalize_indicator_key=canonicalize_indicator_key,
            ):
                continue
            match = _FLOAT_RE.search(seg)
            if match:
                value_str = match.group(0)
                break
    for seg in segments:
        if not _indicator_segment_match(
            indicator_key,
            seg,
            canonicalize_indicator_key=canonicalize_indicator_key,
        ):
            continue
        match = _ACTION_RE.search(seg)
        if match:
            action_str = match.group(1).title()
            break
    return value_str, action_str


def _fallback_trigger_entries_from_desc(
    desc: str | None,
    interval_hint: str | None,
    *,
    canonicalize_indicator_key,
    allowed_indicators: set[str] | None = None,
) -> list[str]:
    if not desc:
        return []
    interval_label = format_interval_display_token(interval_hint)
    interval_part = f"@{interval_label}" if interval_label else ""
    results: list[str] = []

    def _infer_indicator_key(segment: str) -> str | None:
        seg_low = segment.lower()
        if "stochrsi" in seg_low:
            return "stoch_rsi"
        if "williams" in seg_low or "%r" in seg_low:
            return "willr"
        if "rsi" in seg_low:
            return "rsi"
        return None

    for segment in split_trigger_desc(desc):
        seg_clean = segment.strip()
        if not seg_clean:
            continue
        indicator_key = _infer_indicator_key(seg_clean)
        if not indicator_key:
            continue
        if allowed_indicators and indicator_key not in allowed_indicators:
            continue
        value_str, action_str = _extract_indicator_metrics(
            indicator_key,
            [seg_clean],
            canonicalize_indicator_key=canonicalize_indicator_key,
        )
        if value_str is None:
            match = _FLOAT_RE.search(seg_clean)
            if match:
                value_str = match.group(0)
        if value_str is not None:
            try:
                value_display = f"{float(value_str):.2f}"
            except Exception:
                value_display = str(value_str)
        else:
            value_display = "--"
        label = indicator_short_label(indicator_key)
        action_part = f" -{action_str}" if action_str else ""
        entry_text = f"{label}{interval_part} {value_display}{action_part}".strip()
        if entry_text:
            results.append(entry_text)
    return results
