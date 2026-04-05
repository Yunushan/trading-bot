from __future__ import annotations

from .indicator_value_core import (
    CLOSED_ALLOCATION_STATES,
    CLOSED_RECORD_STATES,
    dedupe_indicator_entries,
    format_interval_display_token,
    indicator_entry_signature,
    indicator_short_label,
    normalize_interval_token,
    normalize_trigger_actions_map,
)
from .indicator_value_desc_runtime import (
    _extract_indicator_metrics,
    _fallback_trigger_entries_from_desc,
    split_trigger_desc,
)


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
        primary_interval = format_interval_display_token(
            str(interval_hint).split(",")[0].strip()
        )
    elif isinstance(data.get("interval_display"), str):
        primary_interval = format_interval_display_token(
            str(data.get("interval_display")).split(",")[0].strip()
        )

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
            interval_display = format_interval_display_token(display_token or interval_value)
            sources.append(
                {
                    "interval": interval_display or display_token or interval_value,
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
            interval_display = format_interval_display_token(interval_label)
            if not interval_display and primary_interval:
                interval_display = primary_interval
            label = indicator_short_label(key)
            interval_part = f"@{interval_display}" if interval_display else ""
            if value is not None:
                try:
                    value_display = f"{float(value):.2f}"
                except Exception:
                    value_display = str(value)
            else:
                value_display = "--"
            action_part = f" -{action}" if action else ""
            entry = f"{label}{interval_part} {value_display}{action_part}".strip()
            interval_reg_key = normalize_interval_token(interval_display) or None
            if interval_reg_key in interval_entry_map:
                interval_entry_map[interval_reg_key] = entry
            else:
                interval_entry_map[interval_reg_key] = entry
                interval_entry_order.append(interval_reg_key)
            if interval_display:
                interval_clean = format_interval_display_token(interval_display)
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
            interval_display = format_interval_display_token(primary_interval)
            label = indicator_short_label(key)
            interval_part = f"@{interval_display}" if interval_display else ""
            entry = f"{label}{interval_part} -- -{action_val}".strip()
            deduped_results.append(entry)
            if interval_display:
                interval_clean = format_interval_display_token(interval_display)
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
            indicator_key = label_map.get(label_part)
            if not indicator_key:
                continue
            interval_slots = interval_map.setdefault(indicator_key.lower(), [])
            interval_clean = format_interval_display_token(interval_part)
            if interval_clean and interval_clean not in interval_slots:
                interval_slots.append(interval_clean)
    return deduped_results, interval_map
