from __future__ import annotations

from .record_build_helpers import (
    _apply_interval_metadata_to_row,
    _copy_allocations_for_key,
    _seed_positions_map_from_rows,
    configure_main_window_positions_record_helpers,
)
from .record_futures_merge_helpers import _merge_futures_rows_into_positions_map


def configure_main_window_positions_record_build_runtime(
    *,
    resolve_trigger_indicators=None,
) -> None:
    configure_main_window_positions_record_helpers(
        resolve_trigger_indicators=resolve_trigger_indicators,
    )


def copy_allocations_for_key(alloc_map_global: dict, symbol: str, side_key: str) -> list[dict]:
    return _copy_allocations_for_key(alloc_map_global, symbol, side_key)


def seed_positions_map_from_rows(self, base_rows: list, alloc_map_global: dict, prev_records: dict) -> dict[tuple, dict]:
    return _seed_positions_map_from_rows(self, base_rows, alloc_map_global, prev_records)


def apply_interval_metadata_to_row(
    self,
    *,
    sym: str,
    side_key: str,
    rec: dict,
    data: dict,
    allocations_existing: list[dict],
    intervals_from_alloc: set[str],
    interval_display: dict[str, str],
    interval_lookup: dict[str, str],
    interval_trigger_map: dict[str, set[str]],
    trigger_union: set[str],
) -> None:
    _apply_interval_metadata_to_row(
        self,
        sym=sym,
        side_key=side_key,
        rec=rec,
        data=data,
        allocations_existing=allocations_existing,
        intervals_from_alloc=intervals_from_alloc,
        interval_display=interval_display,
        interval_lookup=interval_lookup,
        interval_trigger_map=interval_trigger_map,
        trigger_union=trigger_union,
    )


def merge_futures_rows_into_positions_map(
    self,
    base_rows: list,
    positions_map: dict,
    alloc_map_global: dict,
) -> None:
    _merge_futures_rows_into_positions_map(self, base_rows, positions_map, alloc_map_global)


def _gui_on_positions_ready(self, rows: list, acct: str, observed_at: str = "", generation: int | None = None):
    from .build_runtime import _gui_on_positions_ready as publish_observation

    return publish_observation(self, rows, acct, observed_at, generation)
