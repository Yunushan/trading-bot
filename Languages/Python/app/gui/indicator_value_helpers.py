from __future__ import annotations

import re

from app.config import INDICATOR_DISPLAY_NAMES


_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")
_ACTION_RE = re.compile(r"->\s*(BUY|SELL)", re.IGNORECASE)
_INDICATOR_SHORT_LABEL_OVERRIDES = {
    "stoch_rsi": "SRSI",
    "rsi": "RSI",
    "willr": "W%R",
}

CLOSED_RECORD_STATES = {
    "closed",
    "liquidated",
    "liquidation",
    "error",
    "stopped",
}

CLOSED_ALLOCATION_STATES = {
    "closed",
    "error",
    "cancelled",
    "canceled",
    "liquidated",
    "liquidation",
    "stopped",
    "completed",
    "filled",
}


def indicator_short_label(indicator_key: str) -> str:
    key_norm = str(indicator_key or "").strip().lower()
    if not key_norm:
        return "-"
    if key_norm in _INDICATOR_SHORT_LABEL_OVERRIDES:
        return _INDICATOR_SHORT_LABEL_OVERRIDES[key_norm]
    display = INDICATOR_DISPLAY_NAMES.get(key_norm)
    if display:
        if "(" in display and ")" in display:
            candidate = display.rsplit("(", 1)[-1].rstrip(")")
            if candidate.strip():
                return candidate.strip()
        first_word = display.strip().split()[0]
        if first_word:
            return first_word.upper()
    return key_norm.upper()


def indicator_entry_signature(text: str) -> tuple[str, str]:
    parts = text.split("@", 1)
    label_part = parts[0].strip().lower()
    interval_part = ""
    if len(parts) == 2:
        remainder = parts[1]
        interval_part = remainder.split(None, 1)[0].strip().lower()
    return label_part, interval_part


def dedupe_indicator_entries(entries: list[str] | None) -> list[str]:
    if not entries:
        return []
    seen: set[tuple[str, str]] = set()
    deduped: list[str] = []
    for entry in entries:
        sig = indicator_entry_signature(entry)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(entry)
    return deduped


def dedupe_indicator_entries_normalized(
    entries: list[str] | None,
    *,
    normalize_indicator_token,
) -> list[str]:
    if not entries:
        return []
    seen_idx: dict[tuple[str, str], int] = {}
    deduped: list[str] = []
    for entry in entries:
        label_part, interval_part = indicator_entry_signature(entry)
        label_key = normalize_indicator_token(label_part) or label_part
        interval_key = normalize_indicator_token(interval_part) or interval_part
        sig = (label_key, interval_key)
        prior = seen_idx.get(sig)
        if prior is None:
            seen_idx[sig] = len(deduped)
            deduped.append(entry)
        else:
            deduped[prior] = entry
    return deduped


def normalize_interval_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(value).strip().lower() or None
    except Exception:
        return None


def normalize_trigger_actions_map(
    raw_actions,
    *,
    canonicalize_indicator_key,
) -> dict[str, str]:
    if not isinstance(raw_actions, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_action in raw_actions.items():
        key_norm = canonicalize_indicator_key(raw_key)
        action_norm = str(raw_action or "").strip().lower()
        if not key_norm or action_norm not in {"buy", "sell"}:
            continue
        normalized[key_norm] = action_norm.title()
    return normalized


def filter_indicator_entries_for_interval(
    entries: list[str],
    interval_hint: str | None,
    *,
    include_non_matching: bool = True,
) -> list[str]:
    if not entries:
        return []
    interval_targets: list[str] = []
    if interval_hint:
        for part in str(interval_hint).split(","):
            token = normalize_interval_token(part)
            if token and token not in interval_targets:
                interval_targets.append(token)
    seen: set[tuple[str, str]] = set()
    filtered: list[str] = []

    def _interval_token(text: str) -> str | None:
        if "@" not in text:
            return None
        return text.split("@", 1)[1].split(None, 1)[0].strip().lower()

    def _label_token(text: str) -> str:
        return text.split("@", 1)[0].strip().lower()

    matched: list[str] = []
    if interval_targets:
        for target in interval_targets:
            for text in entries:
                token = _interval_token(text)
                if token != target:
                    continue
                label = _label_token(text)
                sig = (label, token)
                if sig in seen:
                    continue
                seen.add(sig)
                matched.append(text)
    if matched:
        return dedupe_indicator_entries(matched)
    any_interval_token = any(_interval_token(text) is not None for text in entries)
    if not any_interval_token:
        return dedupe_indicator_entries(entries)
    if not include_non_matching:
        return []
    for text in entries:
        token = _interval_token(text)
        if token is None:
            continue
        label = _label_token(text)
        sig = (label, token)
        if sig in seen:
            continue
        seen.add(sig)
        filtered.append(text)
    return dedupe_indicator_entries(filtered or entries)


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
    interval_label = str(interval_hint or "").strip().upper()
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


def collect_record_indicator_keys(
    rec: dict,
    *,
    include_inactive_allocs: bool = False,
    include_allocation_scope: bool = True,
    resolve_trigger_indicators,
    normalize_indicator_values,
    canonicalize_indicator_key,
) -> list[str]:
    if not isinstance(rec, dict):
        return []
    collected: list[str] = []
    seen: set[str] = set()

    def _add_keys(raw, desc_text: str | None = None) -> None:
        resolved = resolve_trigger_indicators(raw, desc_text)
        for key in normalize_indicator_values(resolved):
            key_norm = canonicalize_indicator_key(key)
            if not key_norm or key_norm in seen:
                continue
            seen.add(key_norm)
            collected.append(key_norm)

    def _iter_allocations(payload) -> list[dict]:
        if isinstance(payload, dict):
            payload = list(payload.values())
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _normalized_action_keys(raw_actions, preferred: list[str] | None = None) -> list[str]:
        if not isinstance(raw_actions, dict):
            return []
        preferred_set: set[str] = set()
        for item in preferred or []:
            canon = canonicalize_indicator_key(item)
            if canon:
                preferred_set.add(canon)
        selected: list[str] = []
        for raw_key in (raw_actions or {}).keys():
            canon = canonicalize_indicator_key(raw_key)
            if not canon:
                continue
            if preferred_set and canon not in preferred_set:
                continue
            selected.append(canon)
        return selected

    data = rec.get("data") or {}
    base_desc = data.get("trigger_desc") or rec.get("trigger_desc")
    base_trigger_keys = resolve_trigger_indicators(data.get("trigger_indicators"), base_desc)
    if not base_trigger_keys:
        base_trigger_keys = normalize_indicator_values(rec.get("indicators"))
    _add_keys(rec.get("indicators"))
    _add_keys(base_trigger_keys)
    data_action_keys = _normalized_action_keys(data.get("trigger_actions"), base_trigger_keys)
    if not data_action_keys and isinstance(data.get("trigger_actions"), dict):
        data_action_keys = _normalized_action_keys(data.get("trigger_actions"))
    if data_action_keys:
        _add_keys(data_action_keys)
    if not collected:
        _add_keys(None, base_desc)

    if include_allocation_scope:
        for alloc in _iter_allocations(rec.get("allocations")):
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            alloc_trigger_keys = resolve_trigger_indicators(
                alloc.get("trigger_indicators"),
                alloc.get("trigger_desc"),
            )
            _add_keys(alloc_trigger_keys, alloc.get("trigger_desc"))
            alloc_action_keys = _normalized_action_keys(alloc.get("trigger_actions"), alloc_trigger_keys)
            if not alloc_action_keys and isinstance(alloc.get("trigger_actions"), dict):
                alloc_action_keys = _normalized_action_keys(alloc.get("trigger_actions"))
            if alloc_action_keys:
                _add_keys(alloc_action_keys)

    aggregated_entries = rec.get("_aggregated_entries")
    if isinstance(aggregated_entries, list):
        for agg in aggregated_entries:
            if not isinstance(agg, dict):
                continue
            agg_data = agg.get("data") or {}
            agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
            if agg_status in CLOSED_RECORD_STATES and not include_inactive_allocs:
                continue
            agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
            agg_trigger_keys = resolve_trigger_indicators(agg_data.get("trigger_indicators"), agg_desc)
            _add_keys(agg.get("indicators"))
            _add_keys(agg_trigger_keys)
            agg_action_keys = _normalized_action_keys(agg_data.get("trigger_actions"), agg_trigger_keys)
            if not agg_action_keys and isinstance(agg_data.get("trigger_actions"), dict):
                agg_action_keys = _normalized_action_keys(agg_data.get("trigger_actions"))
            if agg_action_keys:
                _add_keys(agg_action_keys)
            if not collected:
                _add_keys(None, agg_desc)
            if include_allocation_scope:
                for alloc in _iter_allocations(agg.get("allocations")):
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    if status_flag in CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                        continue
                    alloc_trigger_keys = resolve_trigger_indicators(
                        alloc.get("trigger_indicators"),
                        alloc.get("trigger_desc"),
                    )
                    _add_keys(alloc_trigger_keys, alloc.get("trigger_desc"))
                    alloc_action_keys = _normalized_action_keys(alloc.get("trigger_actions"), alloc_trigger_keys)
                    if not alloc_action_keys and isinstance(alloc.get("trigger_actions"), dict):
                        alloc_action_keys = _normalized_action_keys(alloc.get("trigger_actions"))
                    if alloc_action_keys:
                        _add_keys(alloc_action_keys)
    return collected


def collect_indicator_value_strings(
    rec: dict,
    interval_hint: str | None = None,
    *,
    resolve_trigger_indicators,
    normalize_indicator_values,
    canonicalize_indicator_key,
) -> tuple[list[str], dict[str, list[str]]]:
    data = rec.get("data") or {}
    record_status = str(rec.get("status") or data.get("status") or "").strip().lower()
    include_inactive_allocs = record_status in CLOSED_RECORD_STATES
    primary_interval = ""
    if interval_hint:
        primary_interval = str(interval_hint).split(",")[0].strip()
    elif isinstance(data.get("interval_display"), str):
        primary_interval = str(data.get("interval_display")).split(",")[0].strip()

    indicator_keys = collect_record_indicator_keys(
        rec,
        include_inactive_allocs=include_inactive_allocs,
        resolve_trigger_indicators=resolve_trigger_indicators,
        normalize_indicator_values=normalize_indicator_values,
        canonicalize_indicator_key=canonicalize_indicator_key,
    )
    if not indicator_keys:
        return [], {}
    indicator_key_set = set(indicator_keys)
    action_overrides_by_interval: dict[tuple[str, str | None], str] = {}

    sources: list[dict] = []

    def _append_source(interval_value, desc_text, raw_indicators=None, raw_actions=None):
        if not desc_text:
            return
        segments = split_trigger_desc(desc_text)
        if not segments:
            return
        source_indicator_keys: set[str] = set(resolve_trigger_indicators(raw_indicators, desc_text))
        normalized_actions = normalize_trigger_actions_map(
            raw_actions,
            canonicalize_indicator_key=canonicalize_indicator_key,
        )
        if normalized_actions:
            source_indicator_keys.update(normalized_actions.keys())
        for candidate_key in indicator_keys:
            cand_norm = canonicalize_indicator_key(candidate_key) or str(candidate_key or "").strip().lower()
            if not cand_norm:
                continue
            metric_val, metric_action = _extract_indicator_metrics(
                cand_norm,
                segments,
                canonicalize_indicator_key=canonicalize_indicator_key,
            )
            if metric_val is not None or metric_action is not None:
                source_indicator_keys.add(cand_norm)
        interval_tokens: list[tuple[str | None, str | None]] = []
        if interval_value:
            parts = [part.strip() for part in str(interval_value).split(",") if part.strip()]
            for part in parts:
                interval_tokens.append((part, normalize_interval_token(part)))
        if not interval_tokens:
            interval_tokens.append(((interval_value or "").strip() or None, normalize_interval_token(interval_value)))
        for display_token, norm_token in interval_tokens:
            sources.append(
                {
                    "interval": display_token or interval_value,
                    "norm_interval": norm_token,
                    "segments": segments,
                    "indicator_keys": source_indicator_keys,
                }
            )

    def _register_action_overrides(interval_value, raw_actions) -> None:
        normalized_actions = normalize_trigger_actions_map(
            raw_actions,
            canonicalize_indicator_key=canonicalize_indicator_key,
        )
        if not normalized_actions:
            return
        interval_norm_tokens: list[str | None] = []
        if interval_value:
            for part in [p.strip() for p in str(interval_value).split(",") if p.strip()]:
                interval_norm_tokens.append(normalize_interval_token(part))
        if not interval_norm_tokens:
            interval_norm_tokens.append(normalize_interval_token(interval_value))
        if None not in interval_norm_tokens:
            interval_norm_tokens.append(None)
        for indicator_key, action_val in normalized_actions.items():
            key_norm = canonicalize_indicator_key(indicator_key) or indicator_key
            if not key_norm:
                continue
            for interval_norm_token in interval_norm_tokens:
                action_overrides_by_interval[(key_norm, interval_norm_token)] = action_val

    aggregated_entries = rec.get("_aggregated_entries")
    data_desc = data.get("trigger_desc")
    data_interval = data.get("interval_display") or data.get("interval") or primary_interval
    _register_action_overrides(data_interval, data.get("trigger_actions") or rec.get("trigger_actions"))
    if data_desc and not aggregated_entries:
        _append_source(
            data_interval,
            data_desc,
            data.get("trigger_indicators") or rec.get("trigger_indicators"),
            data.get("trigger_actions") or rec.get("trigger_actions"),
        )

    allocations = rec.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())
    if isinstance(allocations, list):
        for alloc in allocations:
            if not isinstance(alloc, dict):
                continue
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            desc = alloc.get("trigger_desc")
            if not desc:
                continue
            iv = alloc.get("interval_display") or alloc.get("interval")
            _register_action_overrides(iv, alloc.get("trigger_actions"))
            _append_source(
                iv,
                desc,
                alloc.get("trigger_indicators"),
                alloc.get("trigger_actions"),
            )

    if isinstance(aggregated_entries, list):
        for agg in aggregated_entries:
            if not isinstance(agg, dict):
                continue
            agg_data = agg.get("data") or {}
            agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
            if agg_status in CLOSED_RECORD_STATES and not include_inactive_allocs:
                continue
            agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
            if agg_desc:
                agg_interval = (
                    agg_data.get("interval_display")
                    or agg_data.get("interval")
                    or agg.get("entry_tf")
                    or primary_interval
                )
                _register_action_overrides(
                    agg_interval,
                    agg_data.get("trigger_actions") or agg.get("trigger_actions"),
                )
                _append_source(
                    agg_interval,
                    agg_desc,
                    agg_data.get("trigger_indicators") or agg.get("trigger_indicators"),
                    agg_data.get("trigger_actions") or agg.get("trigger_actions"),
                )
            agg_allocs = agg.get("allocations") or []
            if isinstance(agg_allocs, dict):
                agg_allocs = list(agg_allocs.values())
            if isinstance(agg_allocs, list):
                for alloc in agg_allocs:
                    if not isinstance(alloc, dict):
                        continue
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    if status_flag in CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                        continue
                    desc = alloc.get("trigger_desc")
                    if not desc:
                        continue
                    iv = alloc.get("interval_display") or alloc.get("interval")
                    _register_action_overrides(iv, alloc.get("trigger_actions"))
                    _append_source(
                        iv,
                        desc,
                        alloc.get("trigger_indicators"),
                        alloc.get("trigger_actions"),
                    )

    primary_norm = normalize_interval_token(primary_interval)
    restrict_to_primary = bool(rec.get("_aggregate_is_primary"))
    sources_to_use = sources
    if restrict_to_primary and primary_norm:
        preferred_sources = [src for src in sources if src.get("norm_interval") == primary_norm]
        if preferred_sources:
            sources_to_use = preferred_sources
        else:
            fallback_sources = [src for src in sources if src.get("norm_interval") in (None, "")]
            if fallback_sources:
                sources_to_use = fallback_sources
    interval_map: dict[str, list[str]] = {}
    results: list[str] = []
    allow_value_without_action = len(indicator_keys) == 1
    for key in indicator_keys:
        key_norm = canonicalize_indicator_key(key) or key.lower()
        interval_entry_order: list[str | None] = []
        interval_entry_map: dict[str | None, str] = {}

        for source in sources_to_use:
            source_indicator_keys = source.get("indicator_keys")
            if isinstance(source_indicator_keys, (set, list, tuple)) and source_indicator_keys:
                if key_norm not in source_indicator_keys:
                    continue
            segments = source.get("segments") or []
            value, action = _extract_indicator_metrics(
                key,
                segments,
                canonicalize_indicator_key=canonicalize_indicator_key,
            )
            source_interval_norm = source.get("norm_interval")
            if action is None:
                action = action_overrides_by_interval.get((key_norm, source_interval_norm))
            if action is None:
                action = action_overrides_by_interval.get((key_norm, None))
            if action is None and (value is None or not allow_value_without_action):
                continue
            interval_label = source.get("interval") or primary_interval
            interval_display = (interval_label or "").strip()
            if not interval_display and primary_interval:
                interval_display = primary_interval
            label = indicator_short_label(key)
            interval_part = f"@{interval_display.upper()}" if interval_display else ""
            if value is not None:
                try:
                    value_display = f"{float(value):.2f}"
                except Exception:
                    value_display = str(value)
            else:
                value_display = "--"
            action_part = f" -{action}" if action else ""
            entry = f"{label}{interval_part} {value_display}{action_part}".strip()
            interval_reg_key = (interval_display or "").strip().lower() or None
            if interval_reg_key in interval_entry_map:
                interval_entry_map[interval_reg_key] = entry
            else:
                interval_entry_map[interval_reg_key] = entry
                interval_entry_order.append(interval_reg_key)
            if interval_display:
                interval_clean = interval_display.strip().upper()
                slots = interval_map.setdefault(key.lower(), [])
                if interval_clean not in slots:
                    slots.append(interval_clean)
        if interval_entry_map:
            results.extend(interval_entry_map[idx] for idx in interval_entry_order)

    deduped_results = dedupe_indicator_entries(results)

    if not deduped_results and action_overrides_by_interval:
        interval_order: list[str | None] = []
        if primary_norm is not None:
            interval_order.append(primary_norm)
        if None not in interval_order:
            interval_order.append(None)
        for key in indicator_keys:
            key_norm = canonicalize_indicator_key(key) or key.lower()
            action_val = None
            for interval_norm in interval_order:
                action_val = action_overrides_by_interval.get((key_norm, interval_norm))
                if action_val:
                    break
            if not action_val:
                continue
            interval_display = (primary_interval or "").strip()
            label = indicator_short_label(key)
            interval_part = f"@{interval_display.upper()}" if interval_display else ""
            entry = f"{label}{interval_part} -- -{action_val}".strip()
            deduped_results.append(entry)
            if interval_display:
                interval_clean = interval_display.strip().upper()
                slots = interval_map.setdefault(key.lower(), [])
                if interval_clean not in slots:
                    slots.append(interval_clean)

    seen_interval_pairs = {indicator_entry_signature(entry) for entry in deduped_results}
    fallback_entries: list[str] = []
    data_desc_primary = (rec.get("data") or {}).get("trigger_desc") or rec.get("trigger_desc")
    fallback_entries.extend(
        _fallback_trigger_entries_from_desc(
            data_desc_primary,
            interval_hint,
            canonicalize_indicator_key=canonicalize_indicator_key,
            allowed_indicators=indicator_key_set,
        )
    )
    allocations = rec.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())
    for alloc in allocations or []:
        if not isinstance(alloc, dict):
            continue
        status_flag = str(alloc.get("status") or "").strip().lower()
        if status_flag in CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
            continue
        fallback_entries.extend(
            _fallback_trigger_entries_from_desc(
                alloc.get("trigger_desc"),
                alloc.get("interval_display") or alloc.get("interval") or interval_hint,
                canonicalize_indicator_key=canonicalize_indicator_key,
                allowed_indicators=indicator_key_set,
            )
        )
    aggregated_entries = rec.get("_aggregated_entries") or []
    if isinstance(aggregated_entries, list):
        for agg in aggregated_entries:
            if not isinstance(agg, dict):
                continue
            agg_data = agg.get("data") or {}
            agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
            if agg_status in CLOSED_RECORD_STATES and not include_inactive_allocs:
                continue
            agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
            fallback_entries.extend(
                _fallback_trigger_entries_from_desc(
                    agg_desc,
                    agg.get("entry_tf") or agg_data.get("interval_display") or interval_hint,
                    canonicalize_indicator_key=canonicalize_indicator_key,
                    allowed_indicators=indicator_key_set,
                )
            )

    if not deduped_results:
        if fallback_entries:
            filtered: list[str] = []
            for entry in fallback_entries:
                interval_key = indicator_entry_signature(entry)
                if interval_key in seen_interval_pairs:
                    continue
                seen_interval_pairs.add(interval_key)
                filtered.append(entry)
            if filtered:
                deduped_results = list(dict.fromkeys(filtered))
    elif fallback_entries:
        for entry in fallback_entries:
            interval_key = indicator_entry_signature(entry)
            if interval_key in seen_interval_pairs:
                continue
            seen_interval_pairs.add(interval_key)
            if entry not in deduped_results:
                deduped_results.append(entry)

    if deduped_results:
        label_map = {
            indicator_short_label(key).strip().lower(): key
            for key in indicator_keys
        }
        for entry in deduped_results:
            label_part, interval_part = indicator_entry_signature(entry)
            if not interval_part:
                continue
            key = label_map.get(label_part)
            if not key:
                continue
            interval_slots = interval_map.setdefault(key.lower(), [])
            interval_clean = interval_part.strip().upper()
            if interval_clean and interval_clean not in interval_slots:
                interval_slots.append(interval_clean)
    return deduped_results, interval_map
