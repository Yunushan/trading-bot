
from __future__ import annotations
import time, threading
from typing import Dict, Tuple, Optional, Any, List

class IntervalPositionGuard:
    """Prevents duplicate opens for (symbol, interval, side).

    - Tracks a ledger of successful opens stamped by timestamp.
    - Tracks 'pending' in-flight attempts keyed by (symbol, side) to coalesce
      near-simultaneous signals arriving from multiple intervals.
    - Optionally can be strict by symbol+side across all intervals (disabled by default).
    """
    def __init__(self, stale_ttl_sec: Optional[int]=180) -> None:
        self.stale_ttl_sec: int = int(stale_ttl_sec or 180)
        self.ledger: Dict[Tuple[str, str, str], float] = {}
        self.pending_attempts: Dict[Tuple[str, str], Tuple[float, str]] = {}
        self.active: Dict[Tuple[str, str], Dict[str, int]] = {}
        self.strict_symbol_side: bool = True  # block across intervals if True
        self._bw = None  # late-attached binance wrapper
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

    # ----- internal
    def _expire_old_unlocked(self) -> None:
        if not self.stale_ttl_sec:
            return
        now = time.time()
        for k,ts in list(self.ledger.items()):
            if now - ts > self.stale_ttl_sec:
                self.ledger.pop(k, None)
                try:
                    sym, iv, sd = k
                    state = self.active.get((sym, iv))
                    if state:
                        state[sd] = max(0, state.get(sd, 0) - 1)
                        if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
                            self.active.pop((sym, iv), None)
                except Exception:
                    pass

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
                                self.ledger[(sym, iv, sd)] = now
            except Exception:
                # never block on reconciliation errors
                pass

    def can_open(self, symbol: str, interval: str, side: str) -> bool:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        with self._lock:
            self._expire_old_unlocked()
            state = self.active.get((sym, iv), {})
            opposite = 'SELL' if sd == 'BUY' else 'BUY'
            if state.get(opposite, 0) > 0:
                return False
            if (sym, iv, sd) in self.ledger:
                return False
            if (sym, sd) in self.pending_attempts:
                return False
            if (sym, opposite) in self.pending_attempts:
                return False
            for (s, i, ss) in self.ledger.keys():
                if s == sym and i == iv and ss != sd:
                    return False
            if self.strict_symbol_side:
                for (s, i, ss) in self.ledger.keys():
                    if s == sym and ss == sd:
                        return False
            # defensive exchange check
            try:
                bw = self._bw
                if bw:
                    for p in (bw.list_open_futures_positions() or []):
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
            self.pending_attempts[(sym, sd)] = (time.time(), iv)
            return True

    def _record_active(self, sym: str, iv: str, sd: str, delta: int = 0) -> None:
        state = self.active.setdefault((sym, iv), {'BUY': 0, 'SELL': 0})
        if delta != 0:
            state[sd] = max(0, state.get(sd, 0) + delta)
        else:
            state.setdefault(sd, state.get(sd, 0))
        if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
            self.active.pop((sym, iv), None)

    def mark_opened(self, symbol: str, interval: str, side: str) -> None:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        with self._lock:
            self.ledger[(sym, iv, sd)] = time.time()
            self._record_active(sym, iv, sd, delta=1)

    # in-flight coalescer
    def begin_open(self, symbol: str, interval: str, side: str, ttl: float=45.0) -> bool:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        now = time.time()
        with self._lock:
            self._expire_old_unlocked()
            # purge old attempts
            for k,(ts,_iv) in list(self.pending_attempts.items()):
                if now - ts > float(ttl):
                    self.pending_attempts.pop(k, None)
            key = (sym, sd)
            if key in self.pending_attempts:
                return False
            self.pending_attempts[key] = (now, iv)
            return True

    def end_open(self, symbol: str, interval: str, side: str, success: bool) -> None:
        key = ((symbol or '').upper(), (side or '').upper())
        with self._lock:
            self.pending_attempts.pop(key, None)
            if success:
                self.ledger[((symbol or '').upper(), interval or '', (side or '').upper())] = time.time()
                self._record_active((symbol or '').upper(), interval or '', (side or '').upper(), delta=1)

    def mark_closed(self, symbol: str, interval: str, side: str) -> None:
        sym = (symbol or '').upper()
        iv = interval or ''
        sd = (side or '').upper()
        with self._lock:
            self.ledger.pop((sym, iv, sd), None)
            state = self.active.get((sym, iv))
            if state:
                state[sd] = max(0, state.get(sd, 0) - 1)
                if state.get('BUY', 0) <= 0 and state.get('SELL', 0) <= 0:
                    self.active.pop((sym, iv), None)
