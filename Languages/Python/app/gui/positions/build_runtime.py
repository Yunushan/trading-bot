from __future__ import annotations

from app.security.redaction import redact_text
from app.service.schemas.positions import portfolio_observation_is_valid, position_observation_is_valid

from . import record_build_runtime


def configure_main_window_positions_build_runtime(
    *,
    resolve_trigger_indicators=None,
) -> None:
    record_build_runtime.configure_main_window_positions_record_build_runtime(
        resolve_trigger_indicators=resolve_trigger_indicators,
    )


def _copy_allocations_for_key(alloc_map_global: dict, symbol: str, side_key: str) -> list[dict]:
    return record_build_runtime.copy_allocations_for_key(
        alloc_map_global,
        symbol,
        side_key,
    )


def _seed_positions_map_from_rows(self, base_rows: list, alloc_map_global: dict, prev_records: dict) -> dict[tuple, dict]:
    return record_build_runtime.seed_positions_map_from_rows(
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
    return record_build_runtime.apply_interval_metadata_to_row(
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
    record_build_runtime.merge_futures_rows_into_positions_map(
        self,
        base_rows,
        positions_map,
        alloc_map_global,
    )


def _position_observation_is_current(self, generation: int | None) -> bool:
    worker = getattr(self, "_pos_worker", None)
    return worker is None or generation == worker._observation_generation


def _invalidate_positions_observation(self) -> None:
    self._positions_observed_at = ""
    sync = getattr(self, "_sync_service_portfolio_snapshot", None)
    if callable(sync):
        sync(source="desktop-positions-unavailable")


def _gui_on_positions_observation_failed(self, generation: int) -> None:
    if _position_observation_is_current(self, generation):
        _invalidate_positions_observation(self)


def _gui_on_positions_ready(self, rows: list, acct: str, observed_at: str = "", generation: int | None = None):
    if not _position_observation_is_current(self, generation):
        return
    try:
        if not isinstance(rows, list) or not all(position_observation_is_valid({"data": row}) for row in rows):
            raise ValueError("Positions observation contains an invalid row")
        base_rows = sorted(rows, key=lambda row: (row["symbol"], row["side_key"]))
        alloc_map_global = getattr(self, "_entry_allocations", {}) or {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        if not isinstance(prev_records, dict):
            prev_records = {}
        positions_map = _seed_positions_map_from_rows(self, base_rows, alloc_map_global, prev_records)
        expected_keys = {(row["symbol"].strip().upper(), row["side_key"].strip().upper()) for row in base_rows}
        if set(positions_map) != expected_keys or len(expected_keys) != len(base_rows):
            raise ValueError("Positions observation could not be converted completely")
        acct_upper = str(acct or "").upper()
        self._positions_account_type = acct_upper
        self._positions_account_is_futures = acct_upper.startswith("FUT")
        if acct_upper.startswith("FUT"):
            _merge_futures_rows_into_positions_map(self, base_rows, positions_map, alloc_map_global)
        if not portfolio_observation_is_valid(positions_map):
            raise ValueError("Converted positions observation is invalid")
        self._update_position_history(positions_map)
        self._positions_observed_at = observed_at
        self._render_positions_table()
    except Exception as e:
        _invalidate_positions_observation(self)
        self.log(f"Positions render failed: {redact_text(e)}")
