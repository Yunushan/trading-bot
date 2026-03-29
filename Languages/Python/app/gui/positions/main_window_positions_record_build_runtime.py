"""Backward-compatible import shim for positions record-build helpers."""

from .record_build_runtime import (
    _gui_on_positions_ready,
    apply_interval_metadata_to_row,
    configure_main_window_positions_record_build_runtime,
    copy_allocations_for_key,
    merge_futures_rows_into_positions_map,
    seed_positions_map_from_rows,
)

__all__ = [
    "_gui_on_positions_ready",
    "apply_interval_metadata_to_row",
    "configure_main_window_positions_record_build_runtime",
    "copy_allocations_for_key",
    "merge_futures_rows_into_positions_map",
    "seed_positions_map_from_rows",
]
