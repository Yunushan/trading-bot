"""Shared helpers for the service bot runtime coordinator."""

from __future__ import annotations

import copy

_MISSING = object()


def _normalize_control_plane_notes(notes) -> tuple[str, ...]:  # noqa: ANN001
    if isinstance(notes, str):
        text = notes.strip()
        return (text,) if text else ()
    if not isinstance(notes, (list, tuple, set)):
        return ()
    normalized: list[str] = []
    for item in notes:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return tuple(normalized)


def _deep_merge_mappings(base: dict, patch: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_mappings(merged.get(key) or {}, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
