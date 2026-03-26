from __future__ import annotations

import time

from . import strategy_indicator_order_build_runtime
from . import strategy_indicator_order_context_runtime


def _indicator_exchange_qty(self, symbol: str, side_label: str, desired_ps: str | None) -> float:
    return strategy_indicator_order_build_runtime._indicator_exchange_qty(
        self,
        symbol,
        side_label,
        desired_ps,
    )


def _purge_indicator_side_if_exchange_flat(
    self,
    *,
    symbol: str,
    interval_current,
    indicator_key: str,
    side_label: str,
    desired_ps: str | None,
    tracked_qty: float,
) -> float:
    return strategy_indicator_order_build_runtime._purge_indicator_side_if_exchange_flat(
        self,
        symbol=symbol,
        interval_current=interval_current,
        indicator_key=indicator_key,
        side_label=side_label,
        desired_ps=desired_ps,
        tracked_qty=tracked_qty,
    )


def _build_directional_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_target: str | None,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    reason_signal: str,
    recent_close,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    return strategy_indicator_order_build_runtime._build_directional_indicator_order_request(
        self,
        cw=cw,
        interval_current=interval_current,
        indicator_key=indicator_key,
        indicator_label=indicator_label,
        target_side=target_side,
        desired_ps_target=desired_ps_target,
        desired_ps_opposite=desired_ps_opposite,
        indicator_interval_tokens=indicator_interval_tokens,
        qty_tol_indicator=qty_tol_indicator,
        reason_signal=reason_signal,
        recent_close=recent_close,
        now_indicator_ts=now_indicator_ts,
    )


def _build_fallback_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    hedge_overlap_allowed: bool,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    return strategy_indicator_order_build_runtime._build_fallback_indicator_order_request(
        self,
        cw=cw,
        interval_current=interval_current,
        indicator_key=indicator_key,
        indicator_label=indicator_label,
        target_side=target_side,
        desired_ps_opposite=desired_ps_opposite,
        indicator_interval_tokens=indicator_interval_tokens,
        qty_tol_indicator=qty_tol_indicator,
        hedge_overlap_allowed=hedge_overlap_allowed,
        now_indicator_ts=now_indicator_ts,
    )


def _build_hedge_indicator_order_request(
    self,
    *,
    cw,
    interval_current,
    indicator_key: str,
    indicator_label: str,
    target_side: str,
    desired_ps_opposite: str | None,
    indicator_interval_tokens: set[str],
    qty_tol_indicator: float,
    reason_signal: str,
) -> tuple[bool, dict[str, object] | None]:
    return strategy_indicator_order_build_runtime._build_hedge_indicator_order_request(
        self,
        cw=cw,
        interval_current=interval_current,
        indicator_key=indicator_key,
        indicator_label=indicator_label,
        target_side=target_side,
        desired_ps_opposite=desired_ps_opposite,
        indicator_interval_tokens=indicator_interval_tokens,
        qty_tol_indicator=qty_tol_indicator,
        reason_signal=reason_signal,
    )

def _prepare_indicator_signal_request_context(
    self,
    *,
    cw,
    indicator_label: str,
    indicator_action,
    account_type: str,
    dual_side: bool,
    qty_tol_indicator: float,
    now_ts: float,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    return strategy_indicator_order_context_runtime._prepare_indicator_signal_request_context(
        self,
        cw=cw,
        indicator_label=indicator_label,
        indicator_action=indicator_action,
        account_type=account_type,
        dual_side=dual_side,
        qty_tol_indicator=qty_tol_indicator,
        now_ts=now_ts,
        now_indicator_ts=now_indicator_ts,
    )


def _prepare_fallback_indicator_request_context(
    self,
    *,
    cw,
    indicator_label: str,
    indicator_action,
    now_indicator_ts: float,
) -> dict[str, object] | None:
    return strategy_indicator_order_context_runtime._prepare_fallback_indicator_request_context(
        self,
        cw=cw,
        indicator_label=indicator_label,
        indicator_action=indicator_action,
        now_indicator_ts=now_indicator_ts,
    )


def _collect_indicator_order_requests(
    self,
    *,
    cw,
    trigger_actions,
    dual_side: bool,
    account_type: str,
    allow_opposite_enabled: bool,
    hedge_overlap_allowed: bool,
    now_ts: float,
) -> tuple[list[dict[str, object]], float]:
    indicator_order_requests: list[dict[str, object]] = []
    qty_tol_indicator = 1e-9
    try:
        tol_cfg = float(cw.get("indicator_qty_tolerance") or cw.get("qty_tolerance") or 0.0)
        if tol_cfg > 0.0:
            qty_tol_indicator = max(qty_tol_indicator, tol_cfg)
    except Exception:
        pass
    interval_current = cw.get("interval")
    action_side_map: dict[str, str] = {}
    for indicator_name, indicator_action in (trigger_actions or {}).items():
        indicator_norm = self._canonical_indicator_token(indicator_name) or str(
            indicator_name or ""
        ).strip().lower()
        action_norm = str(indicator_action or "").strip().lower()
        if indicator_norm and action_norm in {"buy", "sell"}:
            action_side_map[indicator_norm] = "BUY" if action_norm == "buy" else "SELL"
    self._refresh_indicator_reentry_signal_blocks(
        cw["symbol"],
        interval_current,
        action_side_map,
    )
    if trigger_actions:
        desired_ps_long = "LONG" if dual_side else None
        desired_ps_short = "SHORT" if dual_side else None
        now_indicator_ts = time.time()
        for indicator_name, indicator_action in trigger_actions.items():
            indicator_label = str(indicator_name or "").strip()
            if not indicator_label:
                continue
            request_ctx = _prepare_indicator_signal_request_context(
                self,
                cw=cw,
                indicator_label=indicator_label,
                indicator_action=indicator_action,
                account_type=account_type,
                dual_side=dual_side,
                qty_tol_indicator=qty_tol_indicator,
                now_ts=now_ts,
                now_indicator_ts=now_indicator_ts,
            )
            if not request_ctx:
                continue
            indicator_key = str(request_ctx["indicator_key"])
            action_side_label = str(request_ctx["action_side_label"])
            interval_current = request_ctx["interval_current"]
            indicator_interval_tokens = set(request_ctx["indicator_interval_tokens"] or ())
            reason_signal = str(request_ctx["reason_signal"])
            recent_close = request_ctx.get("recent_close")

            if allow_opposite_enabled:
                hedge_handled, hedge_request = _build_hedge_indicator_order_request(
                    self,
                    cw=cw,
                    interval_current=interval_current,
                    indicator_key=indicator_key,
                    indicator_label=indicator_label,
                    target_side=action_side_label,
                    desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                    indicator_interval_tokens=indicator_interval_tokens,
                    qty_tol_indicator=qty_tol_indicator,
                    reason_signal=reason_signal,
                )
                if hedge_handled:
                    if hedge_request is not None:
                        indicator_order_requests.append(hedge_request)
                    continue

            directional_request = _build_directional_indicator_order_request(
                self,
                cw=cw,
                interval_current=interval_current,
                indicator_key=indicator_key,
                indicator_label=indicator_label,
                target_side=action_side_label,
                desired_ps_target=desired_ps_long if action_side_label == "BUY" else desired_ps_short,
                desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                indicator_interval_tokens=indicator_interval_tokens,
                qty_tol_indicator=qty_tol_indicator,
                reason_signal=reason_signal,
                recent_close=recent_close,
                now_indicator_ts=now_indicator_ts,
            )
            if directional_request is not None:
                indicator_order_requests.append(directional_request)
        if not indicator_order_requests:
            for indicator_name, indicator_action in trigger_actions.items():
                indicator_label = str(indicator_name or "").strip()
                if not indicator_label:
                    continue
                fallback_ctx = _prepare_fallback_indicator_request_context(
                    self,
                    cw=cw,
                    indicator_label=indicator_label,
                    indicator_action=indicator_action,
                    now_indicator_ts=now_indicator_ts,
                )
                if not fallback_ctx:
                    continue
                indicator_key = str(fallback_ctx["indicator_key"])
                interval_current = fallback_ctx["interval_current"]
                action_side_label = str(fallback_ctx["action_side_label"])
                indicator_interval_tokens = set(fallback_ctx["indicator_interval_tokens"] or ())
                fallback_request = _build_fallback_indicator_order_request(
                    self,
                    cw=cw,
                    interval_current=interval_current,
                    indicator_key=indicator_key,
                    indicator_label=indicator_label,
                    target_side=action_side_label,
                    desired_ps_opposite=desired_ps_short if action_side_label == "BUY" else desired_ps_long,
                    indicator_interval_tokens=indicator_interval_tokens,
                    qty_tol_indicator=qty_tol_indicator,
                    hedge_overlap_allowed=hedge_overlap_allowed,
                    now_indicator_ts=now_indicator_ts,
                )
                if fallback_request is not None:
                    indicator_order_requests.append(fallback_request)
    return indicator_order_requests, qty_tol_indicator


def bind_strategy_signal_order_collect_runtime(strategy_cls) -> None:
    strategy_cls._collect_indicator_order_requests = _collect_indicator_order_requests

