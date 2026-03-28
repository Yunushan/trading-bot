from __future__ import annotations

from . import main_window_positions_record_build_runtime


def configure_main_window_positions_build_runtime(
    *,
    resolve_trigger_indicators=None,
) -> None:
    main_window_positions_record_build_runtime.configure_main_window_positions_record_build_runtime(
        resolve_trigger_indicators=resolve_trigger_indicators,
    )


def _copy_allocations_for_key(alloc_map_global: dict, symbol: str, side_key: str) -> list[dict]:
    return main_window_positions_record_build_runtime.copy_allocations_for_key(
        alloc_map_global,
        symbol,
        side_key,
    )


def _seed_positions_map_from_rows(self, base_rows: list, alloc_map_global: dict, prev_records: dict) -> dict[tuple, dict]:
    return main_window_positions_record_build_runtime.seed_positions_map_from_rows(
        self,
        base_rows,
        alloc_map_global,
        prev_records,
    )


def _apply_interval_metadata_to_row(
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
    main_window_positions_record_build_runtime.apply_interval_metadata_to_row(
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


def _merge_futures_rows_into_positions_map(self, base_rows: list, positions_map: dict, alloc_map_global: dict) -> None:
    main_window_positions_record_build_runtime.merge_futures_rows_into_positions_map(
        self,
        base_rows,
        positions_map,
        alloc_map_global,
    )


def _gui_on_positions_ready(self, rows: list, acct: str):
    try:
        try:
            rows = sorted(rows, key=lambda r: (str(r.get("symbol") or ""), str(r.get("side_key") or "")))
        except Exception:
            rows = rows or []
        base_rows = rows or []
        alloc_map_global = getattr(self, "_entry_allocations", {}) or {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        if not isinstance(prev_records, dict):
            prev_records = {}
        positions_map = _seed_positions_map_from_rows(self, base_rows, alloc_map_global, prev_records)
        acct_upper = str(acct or "").upper()
        self._positions_account_type = acct_upper
        self._positions_account_is_futures = acct_upper.startswith("FUT")
        if acct_upper.startswith("FUT"):
            _merge_futures_rows_into_positions_map(self, base_rows, positions_map, alloc_map_global)
        self._update_position_history(positions_map)
        self._render_positions_table()
    except Exception as e:
        self.log(f"Positions render failed: {e}")
