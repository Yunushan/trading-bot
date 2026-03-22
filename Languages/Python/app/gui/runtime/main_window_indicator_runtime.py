from __future__ import annotations

from ...binance_wrapper import BinanceWrapper
from ..shared import indicator_value_helpers, live_indicator_runtime

_CANONICALIZE_INDICATOR_KEY = None
_NORMALIZE_CONNECTOR_BACKEND = None
_NORMALIZE_INDICATOR_TOKEN = None
_NORMALIZE_INDICATOR_VALUES = None
_RESOLVE_TRIGGER_INDICATORS = None

_indicator_short_label = indicator_value_helpers.indicator_short_label


def bind_main_window_indicator_runtime(
    *,
    canonicalize_indicator_key=None,
    normalize_connector_backend=None,
    normalize_indicator_token=None,
    normalize_indicator_values=None,
    resolve_trigger_indicators=None,
) -> None:
    global _CANONICALIZE_INDICATOR_KEY
    global _NORMALIZE_CONNECTOR_BACKEND
    global _NORMALIZE_INDICATOR_TOKEN
    global _NORMALIZE_INDICATOR_VALUES
    global _RESOLVE_TRIGGER_INDICATORS

    _CANONICALIZE_INDICATOR_KEY = canonicalize_indicator_key
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _NORMALIZE_INDICATOR_TOKEN = normalize_indicator_token
    _NORMALIZE_INDICATOR_VALUES = normalize_indicator_values
    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators


def _normalize_trigger_actions_map(raw_actions) -> dict[str, str]:
    return indicator_value_helpers.normalize_trigger_actions_map(
        raw_actions,
        canonicalize_indicator_key=_CANONICALIZE_INDICATOR_KEY,
    )


def _dedupe_indicator_entries_normalized(entries: list[str] | None) -> list[str]:
    return indicator_value_helpers.dedupe_indicator_entries_normalized(
        entries,
        normalize_indicator_token=_NORMALIZE_INDICATOR_TOKEN,
    )


def _collect_record_indicator_keys(
    rec: dict,
    *,
    include_inactive_allocs: bool = False,
    include_allocation_scope: bool = True,
) -> list[str]:
    return indicator_value_helpers.collect_record_indicator_keys(
        rec,
        include_inactive_allocs=include_inactive_allocs,
        include_allocation_scope=include_allocation_scope,
        resolve_trigger_indicators=_RESOLVE_TRIGGER_INDICATORS,
        normalize_indicator_values=_NORMALIZE_INDICATOR_VALUES,
        canonicalize_indicator_key=_CANONICALIZE_INDICATOR_KEY,
    )


def _collect_indicator_value_strings(rec: dict, interval_hint: str | None = None) -> tuple[list[str], dict[str, list[str]]]:
    return indicator_value_helpers.collect_indicator_value_strings(
        rec,
        interval_hint,
        resolve_trigger_indicators=_RESOLVE_TRIGGER_INDICATORS,
        normalize_indicator_values=_NORMALIZE_INDICATOR_VALUES,
        canonicalize_indicator_key=_CANONICALIZE_INDICATOR_KEY,
    )


def _sanitize_interval_hint(interval_hint: str | None) -> str:
    return live_indicator_runtime.sanitize_interval_hint(interval_hint)


def _calc_indicator_value_from_df(df, indicator_key: str, indicator_cfg: dict, *, use_live_values: bool = True) -> float | None:
    return live_indicator_runtime.calc_indicator_value_from_df(
        df,
        indicator_key,
        indicator_cfg,
        use_live_values=use_live_values,
    )


def _ensure_shared_wrapper(window) -> BinanceWrapper | None:
    return live_indicator_runtime.ensure_shared_wrapper(
        window,
        normalize_connector_backend=_NORMALIZE_CONNECTOR_BACKEND,
    )


def _snapshot_live_indicator_context(window) -> dict:
    def _snapshot_auth_state(_window) -> dict:
        try:
            return dict(_window._snapshot_auth_state())
        except Exception:
            return {}

    return live_indicator_runtime.snapshot_live_indicator_context(
        window,
        snapshot_auth_state=_snapshot_auth_state,
    )


def _get_live_indicator_wrapper(window, context: dict) -> BinanceWrapper | None:
    return live_indicator_runtime.get_live_indicator_wrapper(
        window,
        context,
        normalize_connector_backend=_NORMALIZE_CONNECTOR_BACKEND,
    )


def _start_live_indicator_refresh_worker(window, entry: dict) -> None:
    return live_indicator_runtime.start_live_indicator_refresh_worker(
        window,
        entry,
        get_live_indicator_wrapper=_get_live_indicator_wrapper,
        normalize_connector_backend=_NORMALIZE_CONNECTOR_BACKEND,
        calc_indicator_value_from_df=_calc_indicator_value_from_df,
        process_live_indicator_refresh_queue=_process_live_indicator_refresh_queue,
    )


def _process_live_indicator_refresh_queue(window) -> None:
    return live_indicator_runtime.process_live_indicator_refresh_queue(
        window,
        start_live_indicator_refresh_worker=_start_live_indicator_refresh_worker,
    )


def _queue_live_indicator_refresh(
    window,
    cache: dict,
    cache_key: tuple,
    symbol: str,
    interval: str,
    indicator_keys: set[str],
    indicators_cfg: dict,
    use_live_values: bool,
    indicator_source: str,
) -> None:
    return live_indicator_runtime.queue_live_indicator_refresh(
        window,
        cache,
        cache_key,
        symbol,
        interval,
        indicator_keys,
        indicators_cfg,
        use_live_values,
        indicator_source,
        snapshot_live_indicator_context=_snapshot_live_indicator_context,
        process_live_indicator_refresh_queue=_process_live_indicator_refresh_queue,
    )


def _collect_current_indicator_live_strings(
    window,
    symbol,
    indicator_keys,
    cache,
    interval_map: dict[str, list[str]] | None = None,
    default_interval_hint: str | None = None,
):
    return live_indicator_runtime.collect_current_indicator_live_strings(
        window,
        symbol,
        indicator_keys,
        cache,
        interval_map=interval_map,
        default_interval_hint=default_interval_hint,
        sanitize_interval_hint=_sanitize_interval_hint,
        canonicalize_indicator_key=_CANONICALIZE_INDICATOR_KEY,
        normalize_indicator_token=_NORMALIZE_INDICATOR_TOKEN,
        indicator_short_label=_indicator_short_label,
        dedupe_indicator_entries_normalized=_dedupe_indicator_entries_normalized,
        queue_live_indicator_refresh=_queue_live_indicator_refresh,
    )
