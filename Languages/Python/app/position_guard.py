
from __future__ import annotations
import time, threading
from typing import Dict, Tuple, Optional, Any, List

class IntervalPositionGuard:
    """Prevents duplicate opens for (symbol, interval, side).

    - Tracks a ledger of successful opens stamped by timestamp per context.
    - Tracks 'pending' in-flight attempts keyed by (symbol, side, context) to coalesce
      near-simultaneous signals arriving from multiple intervals.
    - By default allows stacking distinct contexts on the same symbol & side while still
      blocking exact duplicates and enforcing opposite-side mutual exclusion.
    """
    def __init__(self, stale_ttl_sec: Optional[int]=180, *, strict_symbol_side: bool = False) -> None:
        self.stale_ttl_sec: int = 0 if stale_ttl_sec in (None, 0) else int(stale_ttl_sec)
        self.ledger: Dict[Tuple[str, str, str], Dict[str, float]] = {}
        self.pending_attempts: Dict[Tuple[str, str, str], Tuple[float, str]] = {}
        self.active: Dict[Tuple[str, str], Dict[str, int]] = {}
        self.strict_symbol_side: bool = bool(strict_symbol_side)
        self.allow_opposite: bool = False
        self._bw = None  # late-attached binance wrapper
        self.block_new: bool = False  # when stopping, disallow new opens immediately
        self._lock = threading.RLock()

    # ----- lifecycle / integration
    def attach_wrapper(self, bw) -> None:
        with self._lock:
            self._bw = bw

    def reset(self) -> None:
        with self._lock:
            self.ledger.clear()
            self.pending_attempts.clear()
            self.active.clear()
            self.block_new = False

    # ----- internal
    def _expire_old_unlocked(self) -> None:
        if not self.stale_ttl_sec:
            return
        now = time.time()
        for key, ctx_map in list(self.ledger.items()):
            if not isinstance(ctx_map, dict):
                ctx_map = {"__legacy__": float(ctx_map or 0.0)}
                self.ledger[key] = ctx_map
            expired_any = False
            sym, iv, sd = key
            for ctx, ts in list(ctx_map.items()):
                try:
                    ts_val = float(ts or 0.0)
                except Exception:
                    ts_val = 0.0
                if now - ts_val > self.stale_ttl_sec:
                    ctx_map.pop(ctx, None)
                    self._record_active(sym, iv, sd, delta=-1)
                    expired_any = True
            if not ctx_map:
                self.ledger.pop(key, None)
            if expired_any:
                state = self.active.get((sym, iv))
                if state and state.get(sd, 0) <= 0:
                    if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
                        self.active.pop((sym, iv), None)

    # ----- public
    def reconcile_with_exchange(self, bw=None, jobs: Optional[List[dict]]=None, account_type: str='FUTURES') -> None:
        bw = bw or self._bw
        if not bw or (account_type or '').upper() != 'FUTURES':
            return
        with self._lock:
            self._expire_old_unlocked()
            try:
                now = time.time()
                live = {}
                for p in (bw.list_open_futures_positions() or []):
                    sym = str(p.get('symbol') or '').upper()
                    amt = float(p.get('positionAmt') or 0.0)
                    if amt > 0:
                        live[(sym, 'BUY')] = True
                    elif amt < 0:
                        live[(sym, 'SELL')] = True
                # seed/reseed entries across configured intervals
                for (sym, sd) in live.keys():
                    for job in (jobs or []):
                        if str(job.get('symbol') or '').upper() == sym:
                            iv = str(job.get('interval') or '')
                            if iv:
                                key = (sym, iv, sd)
                                ctx_map = self.ledger.get(key)
                                if not isinstance(ctx_map, dict):
                                    ctx_map = {}
                                    self.ledger[key] = ctx_map
                                ctx_map["__reconciled__"] = now
            except Exception:
                # never block on reconciliation errors
                pass

    def can_open(self, symbol: str, interval: str, side: str, context: str | None = None) -> bool:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        ctx = str(context) if context is not None else "__legacy__"
        with self._lock:
            self._expire_old_unlocked()
            state = self.active.get((sym, iv), {})
            opposite = 'SELL' if sd == 'BUY' else 'BUY'
            if (not self.allow_opposite) and state.get(opposite, 0) > 0:
                return False
            entry_ctx = self.ledger.get((sym, iv, sd))
            if isinstance(entry_ctx, dict):
                if ctx in entry_ctx:
                    return False
                if context is None and entry_ctx:
                    return False
            elif entry_ctx is not None:
                # legacy float format; block duplicate opens
                return False
            if context is None:
                if any(k[0] == sym and k[1] == sd for k in self.pending_attempts):
                    return False
            else:
                if (sym, sd, ctx) in self.pending_attempts:
                    return False
            if (not self.allow_opposite) and any(k[0] == sym and k[1] == opposite for k in self.pending_attempts):
                return False
            for (s, i, ss), contexts in self.ledger.items():
                if not isinstance(contexts, dict):
                    contexts = {"__legacy__": contexts}
                    self.ledger[(s, i, ss)] = contexts  # type: ignore[assignment]
                if (not self.allow_opposite) and s == sym and i == iv and ss != sd and contexts:
                    return False
                if self.strict_symbol_side and s == sym and ss == sd and contexts:
                    if context is None or any(c != ctx for c in contexts.keys()):
                        return False
            # defensive exchange check
            try:
                bw = self._bw
                # Only enforce global symbol-side duplication guard when we are in strict mode
                # or no contextual key was provided. In hedge/stacking scenarios the caller
                # passes a unique context per indicator, so we allow multiple active legs even
                # if the exchange already reports an open quantity.
                if bw and (self.strict_symbol_side or context is None):
                    for p in (bw.list_open_futures_positions(force_refresh=True) or []):
                        if str(p.get('symbol') or '').upper() != sym:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if sd == 'BUY' and amt > 0:
                            self._record_active(sym, iv, 'BUY', delta=1)
                            return False
                        if sd == 'SELL' and amt < 0:
                            self._record_active(sym, iv, 'SELL', delta=1)
                            return False
            except Exception:
                pass
            # reserve pending attempt immediately (coalescing window)
            self.pending_attempts[(sym, sd, ctx)] = (time.time(), iv)
            return True

    def _record_active(self, sym: str, iv: str, sd: str, delta: int = 0) -> None:
        sd_norm = 'BUY' if str(sd).upper() in ('L', 'LONG', 'BUY') else 'SELL'
        state = self.active.setdefault((sym, iv), {'BUY': 0, 'SELL': 0})
        if delta != 0:
            state[sd_norm] = max(0, state.get(sd_norm, 0) + delta)
        else:
            state.setdefault(sd_norm, state.get(sd_norm, 0))
        if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
            self.active.pop((sym, iv), None)

    def mark_opened(self, symbol: str, interval: str, side: str) -> None:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        with self._lock:
            entry = self.ledger.setdefault((sym, iv, sd), {})
            if "__legacy__" not in entry:
                self._record_active(sym, iv, sd, delta=1)
            entry["__legacy__"] = time.time()

    # in-flight coalescer
    def _pending_ttl(self, ttl: float) -> float:
        """Shorten coalescing TTL on slower/demo environments so attempts don't stay queued too long."""
        try:
            bw = getattr(self, "_bw", None)
            mode_text = str(getattr(bw, "mode", "") or "").lower()
            if "demo" in mode_text or "test" in mode_text:
                return min(12.0, float(ttl) if ttl is not None else 45.0)
        except Exception:
            pass
        return float(ttl) if ttl is not None else 45.0

    def begin_open(self, symbol: str, interval: str, side: str, ttl: float=45.0, context: str | None = None) -> bool:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        now = time.time()
        ctx = str(context) if context is not None else "__legacy__"
        ttl_use = self._pending_ttl(ttl)
        with self._lock:
            if self.block_new:
                return False
            self._expire_old_unlocked()
            # purge old attempts
            for k,(ts,_iv) in list(self.pending_attempts.items()):
                if now - ts > float(ttl_use):
                    self.pending_attempts.pop(k, None)
            key = (sym, sd, ctx)
            pending = self.pending_attempts.get(key)
            if pending is not None:
                pending_iv = pending[1]
                if context is None or not pending_iv or pending_iv == iv:
                    # refresh coalescing window for the same logical attempt
                    self.pending_attempts[key] = (now, iv)
                    return True
                return False
            self.pending_attempts[key] = (now, iv)
            return True

    def end_open(self, symbol: str, interval: str, side: str, success: bool, context: str | None = None) -> None:
        sym = (symbol or '').upper()
        sd = (side or '').upper()
        ctx = str(context) if context is not None else "__legacy__"
        key = (sym, sd, ctx)
        with self._lock:
            self.pending_attempts.pop(key, None)
            if success:
                key = (sym, interval or '', sd)
                ctx_map = self.ledger.setdefault(key, {})
                is_new = ctx not in ctx_map
                ctx_map[ctx] = time.time()
                if is_new:
                    self._record_active(sym, interval or '', sd, delta=1)

    def pause_new(self) -> None:
        """Temporarily block new opens and clear pending attempts (used when stopping)."""
        with self._lock:
            self.block_new = True
            self.pending_attempts.clear()

    def resume_new(self) -> None:
        """Allow new opens again."""
        with self._lock:
            self.block_new = False

    def snapshot_pending_attempts(self) -> List[dict]:
        """
        Return a thread-safe snapshot of in-flight attempts currently held by the guard.
        Each item contains symbol, side, interval, context and the number of seconds queued.
        """
        with self._lock:
            self._expire_old_unlocked()
            now = time.time()
            snapshot: list[dict] = []
            for (sym, side_key, context), meta in list(self.pending_attempts.items()):
                try:
                    ts, interval = meta
                except Exception:
                    ts = meta if isinstance(meta, (int, float)) else 0.0
                    interval = ""
                try:
                    ts_float = float(ts or 0.0)
                except Exception:
                    ts_float = 0.0
                if ts_float <= 0.0:
                    ts_float = 0.0
                age = max(0.0, now - ts_float) if ts_float else 0.0
                try:
                    interval_text = str(interval or "")
                except Exception:
                    interval_text = ""
                side_norm = str(side_key or "").upper()
                if side_norm in ("L", "LONG"):
                    side_norm = "BUY"
                elif side_norm in ("S", "SHORT"):
                    side_norm = "SELL"
                snapshot.append(
                    {
                        "symbol": sym,
                        "side": side_norm or "BUY",
                        "interval": interval_text,
                        "context": str(context),
                        "age": age,
                    }
                )
            return snapshot

    def mark_closed(self, symbol: str, interval: str, side: str) -> None:
        sym = (symbol or '').upper()
        iv = interval or ''
        raw_side = str(side or '').upper()
        if raw_side in ('L', 'LONG'):
            sd = 'BUY'
        elif raw_side in ('S', 'SHORT'):
            sd = 'SELL'
        else:
            sd = raw_side or 'BUY'
        with self._lock:
            entry = self.ledger.pop((sym, iv, sd), None)
            if isinstance(entry, dict):
                removal_count = len(entry)
            else:
                removal_count = 1 if entry is not None else 0
            state = self.active.get((sym, iv))
            if state:
                state[sd] = max(0, state.get(sd, 0) - removal_count)
                if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
                    self.active.pop((sym, iv), None)
