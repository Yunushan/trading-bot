from __future__ import annotations

from ..positions.close_execution import _pause_for_close_uncertainty, _safe_log


def apply_rsi_exit_management(
    self,
    *,
    cw,
    account_type: str,
    allow_opposite_enabled: bool,
    desired_ps_long_guard: str | None,
    desired_ps_short_guard: str | None,
    key_long,
    key_short,
    long_open: bool,
    short_open: bool,
    last_rsi,
    exit_up: float,
    exit_dn: float,
) -> tuple[bool, bool]:
    if account_type == "FUTURES" and last_rsi is not None and not allow_opposite_enabled:
        interval_current = cw.get("interval")
        try:
            close_long = last_rsi >= exit_up and self._indicator_has_open(
                cw["symbol"], interval_current, "rsi", "BUY"
            )
            close_short = last_rsi <= exit_dn and self._indicator_has_open(
                cw["symbol"], interval_current, "rsi", "SELL"
            )
        except Exception as exc:
            _pause_for_close_uncertainty(
                self,
                f"{cw['symbol']}@{interval_current or 'default'} RSI exit ownership check failed: {exc}",
                reconciliation_required=True,
            )
            return long_open, short_open
        if close_long:
            try:
                closed_long, _ = self._close_indicator_positions(
                    cw,
                    interval_current,
                    "rsi",
                    "BUY",
                    desired_ps_long_guard,
                    ignore_hold=True,
                    strict_interval=True,
                    reason="rsi_exit",
                )
            except Exception as exc:
                _pause_for_close_uncertainty(
                    self,
                    f"{cw['symbol']}@{interval_current or 'default'} RSI long exit failed: {exc}",
                    reconciliation_required=True,
                )
                return long_open, short_open
            if closed_long:
                long_open = bool(self._leg_ledger.get(key_long, {}).get("qty", 0) > 0)
                plural = "entry" if closed_long == 1 else "entries"
                _safe_log(
                    self,
                    f"Closed {closed_long} RSI LONG {plural} for {cw['symbol']}@{cw.get('interval')} "
                    f"(RSI >= {exit_up}).",
                )
        if close_short:
            try:
                closed_short, _ = self._close_indicator_positions(
                    cw,
                    interval_current,
                    "rsi",
                    "SELL",
                    desired_ps_short_guard,
                    ignore_hold=True,
                    strict_interval=True,
                    reason="rsi_exit",
                )
            except Exception as exc:
                _pause_for_close_uncertainty(
                    self,
                    f"{cw['symbol']}@{interval_current or 'default'} RSI short exit failed: {exc}",
                    reconciliation_required=True,
                )
                return long_open, short_open
            if closed_short:
                short_open = bool(self._leg_ledger.get(key_short, {}).get("qty", 0) > 0)
                plural = "entry" if closed_short == 1 else "entries"
                _safe_log(
                    self,
                    f"Closed {closed_short} RSI SHORT {plural} for {cw['symbol']}@{cw.get('interval')} "
                    f"(RSI <= {exit_dn}).",
                )
    return long_open, short_open


__all__ = ["apply_rsi_exit_management"]
