from __future__ import annotations


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
            if last_rsi >= exit_up and self._indicator_has_open(cw["symbol"], interval_current, "rsi", "BUY"):
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
                except Exception:
                    closed_long = 0
                if closed_long:
                    long_open = bool(self._leg_ledger.get(key_long, {}).get("qty", 0) > 0)
                    try:
                        plural = "entry" if closed_long == 1 else "entries"
                        self.log(
                            f"Closed {closed_long} RSI LONG {plural} for {cw['symbol']}@{cw.get('interval')} (RSI >= {exit_up})."
                        )
                    except Exception:
                        pass
            if last_rsi <= exit_dn and self._indicator_has_open(cw["symbol"], interval_current, "rsi", "SELL"):
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
                except Exception:
                    closed_short = 0
                if closed_short:
                    short_open = bool(self._leg_ledger.get(key_short, {}).get("qty", 0) > 0)
                    try:
                        plural = "entry" if closed_short == 1 else "entries"
                        self.log(
                            f"Closed {closed_short} RSI SHORT {plural} for {cw['symbol']}@{cw.get('interval')} (RSI <= {exit_dn})."
                        )
                    except Exception:
                        pass
        except Exception:
            pass
    return long_open, short_open


__all__ = ["apply_rsi_exit_management"]
