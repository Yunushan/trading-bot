from __future__ import annotations

from .start_collect_runtime import _collect_strategy_start_context
from .start_engine_runtime import (
    _prepare_strategy_runtime_start,
    _start_strategy_engines,
)


def start_strategy(
    self,
    *,
    strategy_engine_cls=None,
    make_engine_key=None,
    coerce_bool=None,
    normalize_stop_loss_dict=None,
    format_indicator_list=None,
) -> None:
    if strategy_engine_cls is None:
        try:
            self.log("Strategy runtime is not available.")
        except Exception:
            pass
        return
    if getattr(self, "_is_stopping_engines", False):
        self.log("Stop in progress; cannot start new engines.")
        return
    shared = getattr(self, "shared_binance", None)
    if shared is not None and getattr(shared, "_emergency_close_requested", False):
        self.log("Emergency close-all in progress; wait for it to finish before starting.")
        return
    try:
        strategy_engine_cls.resume_trading()
    except Exception:
        pass

    started = 0
    try:
        start_context = _collect_strategy_start_context(self)
        if not start_context.pair_entries:
            self.log("No symbol/interval overrides configured. Add entries before starting.")
            return
        if not start_context.combos:
            self.log("No valid symbol/interval overrides found.")
            return

        guard_obj, guard_can_open = _prepare_strategy_runtime_start(
            self,
            combos=start_context.combos,
            account_type_text=start_context.account_type_text,
            is_futures_account=start_context.is_futures_account,
            strategy_engine_cls=strategy_engine_cls,
            coerce_bool=coerce_bool,
        )
        started = _start_strategy_engines(
            self,
            combos=start_context.combos,
            default_loop_override=start_context.default_loop_override,
            strategy_engine_cls=strategy_engine_cls,
            make_engine_key=make_engine_key,
            normalize_stop_loss_dict=normalize_stop_loss_dict,
            format_indicator_list=format_indicator_list,
            guard_obj=guard_obj,
            guard_can_open=guard_can_open,
        )

        if started == 0:
            self.log("No new engines started (already running?)")
            try:
                self._service_mark_start_failed(
                    reason="No new engines started.",
                    source="desktop-start",
                )
            except Exception:
                pass
    except Exception as exc:
        try:
            self.log(f"Start error: {exc}")
        except Exception:
            pass
        try:
            self._service_mark_start_failed(
                reason=f"Start error: {exc}",
                source="desktop-start",
            )
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass
