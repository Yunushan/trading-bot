from __future__ import annotations

"""Backward-compatible facade for shared indicator value helpers."""

from .indicator_value_collect_runtime import (
    collect_indicator_value_strings,
    collect_record_indicator_keys,
)
from .indicator_value_core import (
    CLOSED_ALLOCATION_STATES,
    CLOSED_RECORD_STATES,
    _ACTION_RE,
    _FLOAT_RE,
    _INDICATOR_SHORT_LABEL_OVERRIDES,
    dedupe_indicator_entries,
    dedupe_indicator_entries_normalized,
    filter_indicator_entries_for_interval,
    indicator_entry_signature,
    indicator_short_label,
    normalize_interval_token,
    normalize_trigger_actions_map,
)
from .indicator_value_desc_runtime import (
    _extract_indicator_metrics,
    _fallback_trigger_entries_from_desc,
    _indicator_segment_match,
    split_trigger_desc,
)
