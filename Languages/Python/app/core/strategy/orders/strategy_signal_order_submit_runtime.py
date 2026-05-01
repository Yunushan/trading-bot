from __future__ import annotations

import time
from typing import Any

from app.security.redaction import redact_text
from app.settings import is_live_trading_mode

try:
    from . import strategy_order_error_logging
except ImportError:  # pragma: no cover - standalone execution fallback
    import strategy_order_error_logging  # type: ignore[no-redef]


def _connector_order_guard_detail(snapshot: dict[str, Any]) -> str:
    attention = snapshot.get("attention")
    if isinstance(attention, list) and attention:
        return redact_text(str(attention[0] or "").strip())
    last_error = snapshot.get("last_error")
    if isinstance(last_error, dict):
        return redact_text(str(last_error.get("message") or "").strip())
    return ""


def _evaluate_connector_order_guard(wrapper) -> tuple[bool, str, str, dict[str, Any]]:  # noqa: ANN001
    getter = getattr(wrapper, "get_connector_health_snapshot", None)
    if not callable(getter):
        return True, "", "info", {}
    try:
        raw_snapshot = getter() or {}
    except Exception as exc:
        return (
            True,
            f"Connector health snapshot unavailable before order submit: {redact_text(exc)}",
            "warning",
            {},
        )
    snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    health = str(snapshot.get("health") or "unknown").strip().lower()
    state = str(snapshot.get("state") or "unknown").strip().lower() or "unknown"
    rate_limit = snapshot.get("rate_limit")
    rate_limit_active = isinstance(rate_limit, dict) and bool(rate_limit.get("active"))
    seconds_until_unban = 0.0
    if isinstance(rate_limit, dict):
        try:
            seconds_until_unban = max(0.0, float(rate_limit.get("seconds_until_unban") or 0.0))
        except Exception:
            seconds_until_unban = 0.0
    network = snapshot.get("network")
    network_offline = isinstance(network, dict) and bool(network.get("offline"))
    detail = _connector_order_guard_detail(snapshot)

    if health == "error" or state in {"auth_error", "network_offline"} or network_offline:
        message = f"Exchange connector order submit blocked: health={health} state={state}."
        if detail:
            message = f"{message} {detail}"
        return False, message, "error", snapshot

    if state == "rate_limited" or rate_limit_active:
        if seconds_until_unban > 0.0:
            message = f"Exchange connector order submit blocked: rate limited for {seconds_until_unban:.0f}s."
        else:
            message = "Exchange connector order submit blocked: rate limited."
        if detail:
            message = f"{message} {detail}"
        return False, message, "warning", snapshot

    if health == "warning":
        message = f"Exchange connector warning before order submit: state={state}."
        if detail:
            message = f"{message} {detail}"
        return True, message, "warning", snapshot

    return True, "", "info", snapshot


def _get_operational_order_snapshot(self, wrapper) -> dict[str, Any]:  # noqa: ANN001
    callback = getattr(self, "operational_snapshot_callback", None)
    if callable(callback):
        result = callback()
        return result if isinstance(result, dict) else {}

    for attr_name in ("get_operational_snapshot", "get_operational_safety_snapshot"):
        getter = getattr(wrapper, attr_name, None)
        if callable(getter):
            result = getter()
            return result if isinstance(result, dict) else {}
    return {}


def _live_mode_for_order_guard(self, wrapper) -> bool:  # noqa: ANN001
    config = getattr(self, "config", {}) or {}
    mode = config.get("mode") if isinstance(config, dict) else None
    if mode in (None, ""):
        mode = getattr(wrapper, "mode", "")
    return is_live_trading_mode(mode)


def _evaluate_operational_order_guard(self, wrapper) -> tuple[bool, str, str, dict[str, Any]]:  # noqa: ANN001
    config = getattr(self, "config", {}) or {}
    if not isinstance(config, dict):
        config = {}
    coerce_bool = getattr(self, "_strategy_coerce_bool", None)
    enabled_raw = config.get("operational_live_order_gate_enabled", True)
    enabled = bool(coerce_bool(enabled_raw, True)) if callable(coerce_bool) else str(enabled_raw).lower() not in {
        "",
        "0",
        "false",
        "no",
        "off",
    }
    if not enabled:
        return True, "Warning: operational live order safety gate is disabled.", "warning", {}

    try:
        snapshot = _get_operational_order_snapshot(self, wrapper)
    except Exception as exc:
        return (
            True,
            f"Operational safety snapshot unavailable before order submit: {redact_text(exc)}",
            "warning",
            {},
        )
    if not snapshot:
        return True, "", "info", {}

    health = str(snapshot.get("health") or "unknown").strip().lower()
    freshness = snapshot.get("freshness")
    stale_labels: list[str] = []
    if isinstance(freshness, dict):
        for key, label in (
            ("exchange_connector", "exchange connector"),
            ("account", "account"),
            ("portfolio", "portfolio"),
        ):
            item = freshness.get(key)
            if isinstance(item, dict) and bool(item.get("stale")):
                stale_labels.append(label)

    issues: list[str] = []
    if health == "error":
        issues.append("operational health is error")
    if stale_labels:
        issues.append("critical snapshots are stale: " + ", ".join(stale_labels))
    if not issues:
        return True, "", "info", snapshot

    detail = "; ".join(issues)
    if _live_mode_for_order_guard(self, wrapper):
        return (
            False,
            f"Futures order blocked by operational safety gate: {detail}.",
            "error",
            snapshot,
        )
    return (
        True,
        f"Warning: operational safety gate found {detail}; demo/test mode order remains allowed.",
        "warning",
        snapshot,
    )


def _connector_order_block_circuit_config(self) -> tuple[bool, int, float]:
    config = getattr(self, "config", {}) or {}
    if not isinstance(config, dict):
        config = {}
    coerce_bool = getattr(self, "_strategy_coerce_bool", None)
    enabled_raw = config.get("connector_order_block_circuit_breaker_enabled", True)
    if callable(coerce_bool):
        enabled = bool(coerce_bool(enabled_raw, True))
    else:
        enabled = str(enabled_raw).strip().lower() not in {"0", "false", "no", "off", ""}
    try:
        threshold = max(1, int(config.get("connector_order_block_pause_threshold") or 2))
    except Exception:
        threshold = 2
    try:
        window_seconds = max(1.0, float(config.get("connector_order_block_window_seconds") or 60.0))
    except Exception:
        window_seconds = 60.0
    return enabled, threshold, window_seconds


def _record_connector_order_block(
    self,
    *,
    cw,
    side: str,
    account_type: str,
    connector_message: str,
    connector_snapshot: dict[str, Any],
    context_key: str,
    signature,
) -> bool:
    enabled, threshold, window_seconds = _connector_order_block_circuit_config(self)
    if not enabled:
        return False

    cls = type(self)
    lock = getattr(cls, "_CONNECTOR_ORDER_BLOCK_LOCK", None)
    if lock is None:
        return False
    now_ts = time.time()
    cutoff_ts = now_ts - window_seconds
    symbol = str((cw or {}).get("symbol") or getattr(self, "config", {}).get("symbol") or "").upper()
    interval = str((cw or {}).get("interval") or getattr(self, "config", {}).get("interval") or "")
    event = {
        "timestamp": now_ts,
        "symbol": symbol,
        "interval": interval,
        "side": str(side or "").upper(),
        "account_type": str(account_type or "").upper(),
        "connector_health": connector_snapshot.get("health"),
        "connector_state": connector_snapshot.get("state"),
    }

    with lock:
        events = getattr(cls, "_CONNECTOR_ORDER_BLOCK_EVENTS", None)
        if not isinstance(events, list):
            events = []
            cls._CONNECTOR_ORDER_BLOCK_EVENTS = events
        events[:] = [
            item
            for item in events
            if isinstance(item, dict) and float(item.get("timestamp") or 0.0) >= cutoff_ts
        ]
        events.append(event)
        block_count = len(events)
        already_open = bool(getattr(cls, "_CONNECTOR_ORDER_CIRCUIT_OPEN", False))
        if already_open or block_count < threshold:
            return False
        cls._CONNECTOR_ORDER_CIRCUIT_OPEN = True
        try:
            cls._GLOBAL_PAUSE.set()
        except Exception:
            pass

    strategy_order_error_logging.log_order_error(
        self,
        "connector health circuit breaker paused trading",
        cw=cw,
        side=side,
        account_type=account_type,
        extra={
            "context_key": context_key,
            "signature": signature,
            "block_count": block_count,
            "block_threshold": threshold,
            "block_window_seconds": window_seconds,
            "connector_health": connector_snapshot.get("health"),
            "connector_state": connector_snapshot.get("state"),
            "connector_message": connector_message,
        },
        level="error",
    )
    callback = getattr(self, "connector_order_circuit_breaker_callback", None)
    if callable(callback):
        try:
            callback(
                {
                    "active": True,
                    "state": "open",
                    "reason": "connector_order_block",
                    "message": connector_message,
                    "block_count": block_count,
                    "block_threshold": threshold,
                    "block_window_seconds": window_seconds,
                    "symbol": symbol,
                    "interval": interval,
                    "side": str(side or "").upper(),
                    "account_type": str(account_type or "").upper(),
                    "connector_health": connector_snapshot.get("health"),
                    "connector_state": connector_snapshot.get("state"),
                }
            )
        except Exception:
            pass
    return True


def _signal_order_has_opposite_open(
    self,
    *,
    positions,
    symbol: str,
    side: str,
    dual_mode: bool,
    tol: float,
) -> bool:
    symbol_upper = str(symbol or "").upper()
    for pos in positions or []:
        if str(pos.get("symbol") or "").upper() != symbol_upper:
            continue
        try:
            amt_existing = float(pos.get("positionAmt") or 0.0)
        except Exception:
            amt_existing = 0.0
        pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
        if side == "BUY":
            if amt_existing < -tol and (not dual_mode or pos_side in {"BOTH", ""}):
                return True
        elif side == "SELL":
            if amt_existing > tol and (not dual_mode or pos_side in {"BOTH", ""}):
                return True
    return False


def _submit_futures_signal_order(
    self,
    *,
    cw,
    side: str,
    flip_active: bool,
    context_key: str,
    signature,
    key_bar,
    key_dup,
    current_batch_index: int,
    order_batch_total: int,
    desired_ps,
    qty_est: float,
    reduce_only: bool,
    last_price,
    lev,
    abort_guard,
) -> tuple[object, bool, bool]:
    allow_hedge_open = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    guard_obj = getattr(self, "guard", None)
    guard_side = side
    can_open_claimed = False

    connector_allowed, connector_message, connector_level, connector_snapshot = _evaluate_connector_order_guard(
        self.binance
    )
    if not connector_allowed:
        strategy_order_error_logging.log_order_error(
            self,
            "futures order blocked by connector health",
            cw=cw,
            side=side,
            account_type="FUTURES",
            extra={
                "context_key": context_key,
                "signature": signature,
                "connector_health": connector_snapshot.get("health"),
                "connector_state": connector_snapshot.get("state"),
                "connector_message": connector_message,
            },
            level=connector_level,
        )
        _record_connector_order_block(
            self,
            cw=cw,
            side=side,
            account_type="FUTURES",
            connector_message=connector_message,
            connector_snapshot=connector_snapshot,
            context_key=context_key,
            signature=signature,
        )
        abort_guard()
        return {"ok": False, "symbol": cw["symbol"], "error": connector_message}, False, True
    if connector_message:
        strategy_order_error_logging.log_order_error(
            self,
            "futures order connector health warning",
            cw=cw,
            side=side,
            account_type="FUTURES",
            extra={
                "context_key": context_key,
                "signature": signature,
                "connector_health": connector_snapshot.get("health"),
                "connector_state": connector_snapshot.get("state"),
                "connector_message": connector_message,
            },
            level=connector_level,
        )

    operational_allowed, operational_message, operational_level, operational_snapshot = (
        _evaluate_operational_order_guard(self, self.binance)
    )
    if not operational_allowed:
        strategy_order_error_logging.log_order_error(
            self,
            "futures order blocked by operational safety",
            cw=cw,
            side=side,
            account_type="FUTURES",
            extra={
                "context_key": context_key,
                "signature": signature,
                "operational_health": operational_snapshot.get("health"),
                "operational_message": operational_message,
            },
            level=operational_level,
        )
        abort_guard()
        return {"ok": False, "symbol": cw["symbol"], "error": operational_message}, False, True
    if operational_message:
        strategy_order_error_logging.log_order_error(
            self,
            "futures order operational safety warning",
            cw=cw,
            side=side,
            account_type="FUTURES",
            extra={
                "context_key": context_key,
                "signature": signature,
                "operational_health": operational_snapshot.get("health"),
                "operational_message": operational_message,
            },
            level=operational_level,
        )

    def _release_can_open_claim() -> None:
        nonlocal can_open_claimed
        if not can_open_claimed:
            return
        can_open_claimed = False
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, False, context=context_key)
            except Exception:
                pass

    if callable(self.can_open_cb) and not allow_hedge_open:
        if not self.can_open_cb(cw["symbol"], cw.get("interval"), side, context_key):
            self.log(f"{cw['symbol']}@{cw.get('interval')} Duplicate guard: {side} already open - skipping.")
            abort_guard()
            return {}, False, True
        can_open_claimed = True

    try:
        backend_key = str(getattr(self.binance, "_connector_backend", "") or "").lower()
        guard_duplicates = backend_key == "binance-sdk-derivatives-trading-usds-futures" and not allow_hedge_open
        tol = 1e-8
        dual_mode = bool(self.binance.get_futures_dual_side())
        existing_positions = None
        flip_refresh = False
        if flip_active:
            try:
                mode_text = str(getattr(self.binance, "mode", "") or "").lower()
                flip_refresh = any(tag in mode_text for tag in ("demo", "test", "paper"))
            except Exception:
                flip_refresh = False
        if flip_refresh:
            # Demo/testnet positions can lag after flips; retry a fresh snapshot once.
            for attempt in range(2):
                try:
                    invalidator = getattr(self.binance, "_invalidate_futures_positions_cache", None)
                    if callable(invalidator):
                        invalidator()
                except Exception:
                    pass
                try:
                    existing_positions = self.binance.list_open_futures_positions(
                        max_age=0.0,
                        force_refresh=True,
                    ) or []
                except Exception:
                    existing_positions = []
                if not self._signal_order_has_opposite_open(
                    positions=existing_positions,
                    symbol=cw["symbol"],
                    side=side,
                    dual_mode=dual_mode,
                    tol=tol,
                ):
                    break
                if attempt == 0:
                    time.sleep(0.35)
        if existing_positions is None:
            existing_positions = self.binance.list_open_futures_positions(
                max_age=0.0,
                force_refresh=True,
            ) or []
        for pos in existing_positions:
            if str(pos.get("symbol") or "").upper() != cw["symbol"].upper():
                continue
            try:
                amt_existing = float(pos.get("positionAmt") or 0.0)
            except Exception:
                amt_existing = 0.0
            pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
            if side == "BUY":
                if amt_existing < -tol and (not dual_mode or pos_side in {"BOTH", ""}):
                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short still open on exchange; skipping long entry.")
                    _release_can_open_claim()
                    abort_guard()
                    return {}, False, True
                if guard_duplicates:
                    long_active = False
                    if dual_mode:
                        if pos_side == "LONG":
                            long_active = abs(amt_existing) > tol
                        elif pos_side == "BOTH":
                            long_active = amt_existing > tol
                    else:
                        long_active = amt_existing > tol
                    if long_active:
                        entries_dup = self._leg_entries(key_bar)
                        sig_sorted = signature if signature else ()
                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long already active on exchange; skipping duplicate long entry.")
                            _release_can_open_claim()
                            abort_guard()
                            return {}, False, True
            elif side == "SELL":
                if amt_existing > tol and (not dual_mode or pos_side in {"BOTH", ""}):
                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long still open on exchange; skipping short entry.")
                    _release_can_open_claim()
                    abort_guard()
                    return {}, False, True
                if guard_duplicates:
                    short_active = False
                    if dual_mode:
                        if pos_side == "SHORT":
                            short_active = abs(amt_existing) > tol
                        elif pos_side == "BOTH":
                            short_active = amt_existing < -tol
                    else:
                        short_active = amt_existing < -tol
                    if short_active:
                        entries_dup = self._leg_entries(key_dup)
                        sig_sorted = signature if signature else ()
                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short already active on exchange; skipping duplicate short entry.")
                            _release_can_open_claim()
                            abort_guard()
                            return {}, False, True
    except Exception as ex_chk:
        strategy_order_error_logging.log_order_error(
            self,
            "futures order guard check failed",
            cw=cw,
            side=side,
            account_type="FUTURES",
            exc=ex_chk,
            extra={
                "context_key": context_key,
                "signature": signature,
            },
            level="warning",
        )
        _release_can_open_claim()
        abort_guard()
        return {}, False, True

    order_res: dict[str, Any] = {}
    order_success = False
    if guard_obj and hasattr(guard_obj, "begin_open"):
        try:
            if not guard_obj.begin_open(cw["symbol"], cw.get("interval"), guard_side, context=context_key):
                _release_can_open_claim()
                self.log(f"{cw['symbol']}@{cw.get('interval')} guard blocked {guard_side} entry (pending or opposite side active).")
                abort_guard()
                return order_res, order_success, True
            can_open_claimed = False
        except Exception:
            pass
    if self.stopped():
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, False, context=context_key)
            except Exception:
                pass
        return {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}, False, True

    order_attempts = 0
    price_for_order = last_price if (last_price is not None and last_price > 0.0) else cw.get("price")
    last_order_exc: BaseException | None = None
    try:
        order_success = False
        backoff_base = self._order_rate_retry_backoff
        rate_limit_tokens = ("too frequent", "-1003", "frequency", "rate limit", "request too many", "too many requests")
        while True:
            if self.stopped():
                order_res = {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}
                order_success = False
                break
            order_attempts += 1
            spacing_to_use = self._order_rate_min_spacing
            if order_batch_total > 1 and current_batch_index > 0 and order_attempts == 1:
                spacing_to_use = min(
                    spacing_to_use,
                    max(0.1, spacing_to_use * 0.35),
                )
            try:
                type(self)._reserve_order_slot(spacing_to_use)
                if self.stopped():
                    order_res = {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}
                else:
                    order_res = self.binance.place_futures_market_order(
                        cw["symbol"],
                        side,
                        percent_balance=None,
                        leverage=lev,
                        reduce_only=(False if self.binance.get_futures_dual_side() else reduce_only),
                        position_side=desired_ps,
                        price=price_for_order,
                        quantity=qty_est,
                        strict=True,
                        timeInForce=self.config.get("tif", "GTC"),
                        gtd_minutes=int(self.config.get("gtd_minutes", 30)),
                        interval=cw.get("interval"),
                        max_auto_bump_percent=float(self.config.get("max_auto_bump_percent", 5.0)),
                        auto_bump_percent_multiplier=float(self.config.get("auto_bump_percent_multiplier", 10.0)),
                    )
            except Exception as exc_order:
                last_order_exc = exc_order
                order_res = {
                    "ok": False,
                    "symbol": cw["symbol"],
                    "error": redact_text(exc_order),
                    "exception_type": type(exc_order).__name__,
                }
            finally:
                type(self)._release_order_slot()

            order_success = bool(order_res.get("ok", True))
            if self.stopped():
                order_success = False
                break
            if order_success:
                break
            try:
                err_text = order_res.get("error") or order_res
                self.log(f"{cw['symbol']}@{cw.get('interval')} order error: {redact_text(err_text)}")
            except Exception:
                pass
            err_text = str(order_res.get("error") or "").lower()
            if order_attempts < 3 and any(token in err_text for token in rate_limit_tokens):
                wait_time = min(5.0, backoff_base * order_attempts)
                time.sleep(wait_time)
                continue
            break
    finally:
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, order_success, context=context_key)
            except Exception:
                pass

    if self.stopped():
        return order_res, order_success, True
    if order_success:
        try:
            via = order_res.get("via") or getattr(order_res.get("info", {}), "get", lambda *_: None)("via")
            qty_dbg = order_res.get("computed", {}).get("qty") or order_res.get("info", {}).get("origQty")
            self.log(f"{cw['symbol']}@{cw.get('interval')} order placed {side} qty={qty_dbg} via={via or 'primary'}")
        except Exception:
            pass
    else:
        try:
            strategy_order_error_logging.log_order_error(
                self,
                "futures order failed",
                cw=cw,
                side=side,
                account_type="FUTURES",
                exc=last_order_exc,
                extra={
                    "context_key": context_key,
                    "signature": signature,
                    "attempts": order_attempts,
                    "price": price_for_order,
                    "qty": qty_est,
                    "leverage": lev,
                    "reduce_only": reduce_only,
                    "position_side": desired_ps,
                    "order_result": order_res,
                },
                include_traceback=last_order_exc is not None,
            )
        except Exception:
            pass
    return order_res, order_success, False


def bind_strategy_signal_order_submit_runtime(strategy_cls) -> None:
    strategy_cls._record_connector_order_block = _record_connector_order_block
    strategy_cls._signal_order_has_opposite_open = _signal_order_has_opposite_open
    strategy_cls._submit_futures_signal_order = _submit_futures_signal_order
