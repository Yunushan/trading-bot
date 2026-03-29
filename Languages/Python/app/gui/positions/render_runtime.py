from __future__ import annotations

from . import table_render_runtime

POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17


def configure_main_window_positions_render_runtime(
    *,
    closed_record_states=None,
    numeric_item_cls=None,
    collect_current_indicator_live_strings=None,
    collect_indicator_value_strings=None,
    collect_record_indicator_keys=None,
    coerce_bool_fn=None,
    dedupe_indicator_entries_normalized=None,
    filter_indicator_entries_for_interval=None,
    format_indicator_list=None,
    indicator_entry_signature=None,
    indicator_short_label=None,
    normalize_indicator_values=None,
    positions_records_cumulative_fn=None,
    pos_triggered_value_column: int = 10,
    pos_current_value_column: int = 11,
    pos_stop_loss_column: int = 15,
    pos_status_column: int = 16,
    pos_close_column: int = 17,
) -> None:
    global POS_TRIGGERED_VALUE_COLUMN
    global POS_CURRENT_VALUE_COLUMN
    global POS_STOP_LOSS_COLUMN
    global POS_STATUS_COLUMN
    global POS_CLOSE_COLUMN

    POS_TRIGGERED_VALUE_COLUMN = int(pos_triggered_value_column)
    POS_CURRENT_VALUE_COLUMN = int(pos_current_value_column)
    POS_STOP_LOSS_COLUMN = int(pos_stop_loss_column)
    POS_STATUS_COLUMN = int(pos_status_column)
    POS_CLOSE_COLUMN = int(pos_close_column)

    table_render_runtime.configure_main_window_positions_render_runtime(
        closed_record_states=closed_record_states,
        numeric_item_cls=numeric_item_cls,
        collect_current_indicator_live_strings=collect_current_indicator_live_strings,
        collect_indicator_value_strings=collect_indicator_value_strings,
        collect_record_indicator_keys=collect_record_indicator_keys,
        coerce_bool_fn=coerce_bool_fn,
        dedupe_indicator_entries_normalized=dedupe_indicator_entries_normalized,
        filter_indicator_entries_for_interval=filter_indicator_entries_for_interval,
        format_indicator_list=format_indicator_list,
        indicator_entry_signature=indicator_entry_signature,
        indicator_short_label=indicator_short_label,
        normalize_indicator_values=normalize_indicator_values,
        positions_records_cumulative_fn=positions_records_cumulative_fn,
        pos_triggered_value_column=POS_TRIGGERED_VALUE_COLUMN,
        pos_current_value_column=POS_CURRENT_VALUE_COLUMN,
        pos_stop_loss_column=POS_STOP_LOSS_COLUMN,
        pos_status_column=POS_STATUS_COLUMN,
        pos_close_column=POS_CLOSE_COLUMN,
    )


def _mw_render_positions_table(self):
    return table_render_runtime._mw_render_positions_table(self)
