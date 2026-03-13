
import time, copy, math, threading, os, sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    _APP_DIR = Path(__file__).resolve().parent
    if str(_APP_DIR) not in sys.path:
        sys.path.insert(0, str(_APP_DIR))

import pandas as pd
try:
    from .config import (
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        normalize_stop_loss_dict,
        INDICATOR_DISPLAY_NAMES,
        coerce_bool,
    )
    from .binance_wrapper import normalize_margin_ratio
    from .indicators import (
        sma,
        ema,
        bollinger_bands,
        rsi as rsi_fallback,
        macd as macd_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        parabolic_sar as psar_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
    )
    from .preamble import PANDAS_TA_AVAILABLE, PANDAS_VERSION, PANDAS_TA_VERSION
except ImportError:  # pragma: no cover - standalone execution fallback
    from config import (
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        normalize_stop_loss_dict,
        INDICATOR_DISPLAY_NAMES,
        coerce_bool,
    )
    from binance_wrapper import normalize_margin_ratio
    from indicators import (
        sma,
        ema,
        bollinger_bands,
        rsi as rsi_fallback,
        macd as macd_fallback,
        stoch_rsi as stoch_rsi_fallback,
        williams_r as williams_r_fallback,
        parabolic_sar as psar_fallback,
        ultimate_oscillator as uo_fallback,
        dmi as dmi_fallback,
        adx as adx_fallback,
        supertrend as supertrend_fallback,
        stochastic as stochastic_fallback,
    )
    from preamble import PANDAS_TA_AVAILABLE, PANDAS_VERSION, PANDAS_TA_VERSION

try:
    from . import strategy_runtime
    from . import strategy_runtime_support
    from . import strategy_indicator_compute
    from . import strategy_signal_generation
    from . import strategy_signal_orders_runtime
    from . import strategy_indicator_guard
    from . import strategy_indicator_tracking
    from . import strategy_trade_book
    from . import strategy_position_state
    from . import strategy_position_close_runtime
    from . import strategy_position_flip_runtime
except ImportError:  # pragma: no cover - standalone execution fallback
    import strategy_runtime
    import strategy_runtime_support
    import strategy_indicator_compute
    import strategy_signal_generation
    import strategy_signal_orders_runtime
    import strategy_indicator_guard
    import strategy_indicator_tracking
    import strategy_trade_book
    import strategy_position_state
    import strategy_position_close_runtime
    import strategy_position_flip_runtime

def _interval_to_seconds(iv:str)->int:
    try:
        if iv.endswith('m'): return int(iv[:-1])*60
        if iv.endswith('s'): return int(iv[:-1])
        if iv.endswith('h'): return int(iv[:-1])*3600
        if iv.endswith('d'): return int(iv[:-1])*86400
    except Exception:
        pass
    return 60


_CPU_COUNT = os.cpu_count() or 4


def _default_parallel_limit(cpu_count: int) -> int:
    """Heuristic to balance strategy loop concurrency with available CPU cores.

    Too many concurrent loops on low core-count hosts starves the Qt GUI thread,
    so we keep the limit tight for <=4 cores and scale gently afterwards.
    """
    cpu = max(1, int(cpu_count))
    if cpu == 1:
        return 1
    if cpu == 2:
        return 2
    if cpu <= 4:
        return cpu
    if cpu <= 8:
        return int(round(cpu * 1.25))
    return min(16, int(round(cpu * 1.5)))


_MAX_PARALLEL_RUNS = max(1, min(16, _default_parallel_limit(_CPU_COUNT)))


def _normalize_indicator_alias(token: str | None) -> str:
    return str(token or "").strip().lower()


def _strip_indicator_label(alias: str) -> str:
    text = alias.replace("(", " ").replace(")", " ")
    text = text.replace("%", " % ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _build_indicator_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}

    def _register(alias: str | None, canonical: str | None) -> None:
        alias_norm = _normalize_indicator_alias(alias)
        canonical_norm = _normalize_indicator_alias(canonical)
        if alias_norm and canonical_norm and alias_norm not in alias_map:
            alias_map[alias_norm] = canonical_norm

    indicators = INDICATOR_DISPLAY_NAMES or {}
    for key, label in indicators.items():
        _register(key, key)
        _register(label, key)
        if isinstance(label, str):
            _register(_strip_indicator_label(label), key)
            _register(_strip_indicator_label(label).replace(" ", ""), key)
            if "(" in label and ")" in label:
                inner = label[label.find("(") + 1 : label.rfind(")")]
                _register(inner, key)
                _register(inner.replace(" ", ""), key)
    return alias_map


_INDICATOR_ALIAS_MAP = _build_indicator_alias_map()


def _canonical_indicator_token(token: str | None) -> str | None:
    text = _normalize_indicator_alias(token)
    if not text:
        return None
    mapped = _INDICATOR_ALIAS_MAP.get(text)
    if mapped:
        return mapped
    compact = text.replace(" ", "")
    mapped = _INDICATOR_ALIAS_MAP.get(compact)
    if mapped:
        return mapped
    stripped = _strip_indicator_label(text)
    mapped = _INDICATOR_ALIAS_MAP.get(stripped)
    if mapped:
        return mapped
    compact_stripped = stripped.replace(" ", "")
    mapped = _INDICATOR_ALIAS_MAP.get(compact_stripped)
    if mapped:
        return mapped
    return text


class StrategyEngine:
    _RUN_GATE = threading.BoundedSemaphore(_MAX_PARALLEL_RUNS)
    _MAX_ACTIVE = _MAX_PARALLEL_RUNS
    _GLOBAL_SHUTDOWN = threading.Event()
    _GLOBAL_PAUSE = threading.Event()
    _ORDER_THROTTLE_LOCK = threading.Lock()
    _ORDER_LAST_TS = 0.0
    _ORDER_MIN_SPACING = 0.35  # seconds between order submissions by default
    _BAR_GUARD_LOCK = threading.Lock()
    _BAR_GLOBAL_SIGNATURES: dict[tuple[str, str, str], dict[str, object]] = {}
    _SYMBOL_GUARD_LOCK = threading.Lock()
    _SYMBOL_ORDER_STATE: dict[tuple[str, str, str], dict[str, object]] = {}

    @classmethod
    def concurrent_limit(cls, job_count: int | None = None) -> int:
        limit = cls._MAX_ACTIVE
        if job_count is not None:
            try:
                limit = min(limit, max(1, int(job_count)))
            except Exception:
                pass
        return limit

    @classmethod
    def _reserve_order_slot(cls, min_spacing: float | None = None) -> None:
        """Global rate limiter so we don't spam the exchange with concurrent orders."""
        spacing = float(min_spacing) if min_spacing is not None else cls._ORDER_MIN_SPACING
        if not math.isfinite(spacing) or spacing <= 0.0:
            spacing = cls._ORDER_MIN_SPACING
        spacing = max(cls._ORDER_MIN_SPACING, spacing)
        while True:
            with cls._ORDER_THROTTLE_LOCK:
                now = time.time()
                wait = (cls._ORDER_LAST_TS + spacing) - now
                if wait <= 0.0:
                    cls._ORDER_LAST_TS = now
                    return
            time.sleep(min(max(wait, 0.01), 0.5))

    @classmethod
    def _release_order_slot(cls) -> None:
        with cls._ORDER_THROTTLE_LOCK:
            cls._ORDER_LAST_TS = max(cls._ORDER_LAST_TS, time.time())

    def __init__(self, binance_wrapper, config, log_callback, trade_callback=None, loop_interval_override=None, can_open_callback=None):
        self.config = copy.deepcopy(config)
        self.config.setdefault("indicator_flip_cooldown_bars", 1)
        self.config.setdefault("indicator_flip_cooldown_seconds", 0.0)
        self.config.setdefault("indicator_use_live_values", False)
        self.config.setdefault("indicator_min_position_hold_seconds", 0.0)
        self.config.setdefault("indicator_min_position_hold_bars", 1)
        self.config.setdefault("indicator_reentry_cooldown_seconds", 0.0)
        self.config.setdefault("indicator_reentry_cooldown_bars", 1)
        self.config.setdefault("indicator_reentry_requires_signal_reset", True)
        self.config.setdefault("require_indicator_flip_signal", True)
        self.config.setdefault("strict_indicator_flip_enforcement", True)
        self.config.setdefault("auto_flip_on_close", True)
        self.config.setdefault("allow_close_ignoring_hold", False)
        self.config.setdefault("futures_flat_purge_grace_seconds", 12.0)
        self.config.setdefault("futures_flat_purge_miss_threshold", 2)
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.binance = binance_wrapper
        self.log = log_callback
        self.trade_cb = trade_callback
        self.loop_override = loop_interval_override
        self._leg_ledger = {}
        self._last_order_time = {}  # (symbol, interval, side)->{'qty': float, 'timestamp': float}
        self._last_bar_key = set()  # prevent multi entries within same bar per (symbol, interval, side)
        self._bar_order_tracker: dict[tuple[str, str, str], dict[str, object]] = {}
        self._symbol_signature_open: dict[tuple[str, str, str, tuple[str, ...]], int] = {}
        self._symbol_signature_lock = threading.Lock()
        self._indicator_state: dict[tuple[str, str, str], dict[str, set[str]]] = {}
        self._indicator_state_lock = threading.Lock()
        self._trade_book_lock = threading.RLock()
        self._trade_book: dict[tuple[str, str, str, str], dict[str, dict[str, float]]] = {}
        self._ledger_index: dict[str, tuple[str, str, str]] = {}
        self._close_guard_lock = threading.RLock()
        # Tracks in-flight close operations per (symbol, side). Using side granularity
        # lets hedge-mode BUY/SELL closes proceed independently.
        self._close_inflight: dict[tuple[str, str], dict[str, object]] = {}
        self._oneway_overlap_warned: set[tuple[str, str, str]] = set()
        self.can_open_cb = can_open_callback
        self._stop = False
        # Debounce liquidation reconciliation to avoid clearing state on transient API gaps.
        self._reconcile_miss_counts: dict[str, int] = {}
        self._flat_purge_miss_counts: dict[tuple[str, str, str], int] = {}
        key = f"{str(self.config.get('symbol') or '').upper()}@{str(self.config.get('interval') or '').lower()}"
        h = abs(hash(key)) if key.strip('@') else 0
        self._phase_seed = (h % 997) / 997.0 if key.strip('@') else 0.0
        self._phase_offset = self._phase_seed * 25.0
        self._thread = None
        self._offline_backoff = 0.0
        self._last_network_log = 0.0
        self._emergency_close_triggered = False
        self._stop_time = 0.0
        try:
            spacing = float(self.config.get("order_rate_min_spacing", StrategyEngine._ORDER_MIN_SPACING))
        except Exception:
            spacing = StrategyEngine._ORDER_MIN_SPACING
        self._order_rate_min_spacing = max(0.05, min(spacing, 5.0))
        try:
            retry_backoff = float(self.config.get("order_rate_retry_backoff", 0.75))
        except Exception:
            retry_backoff = 0.75
        self._order_rate_retry_backoff = max(0.1, min(retry_backoff, 5.0))
        try:
            self._flat_purge_grace_seconds = max(
                0.0, float(self.config.get("futures_flat_purge_grace_seconds") or 0.0)
            )
        except Exception:
            self._flat_purge_grace_seconds = 12.0
        try:
            self._flat_purge_miss_threshold = max(
                1, int(self.config.get("futures_flat_purge_miss_threshold") or 1)
            )
        except Exception:
            self._flat_purge_miss_threshold = 2
        self._indicator_use_live_values = bool(self.config.get("indicator_use_live_values", False))
        try:
            self._indicator_min_hold_seconds = max(
                0.0, float(self.config.get("indicator_min_position_hold_seconds") or 0.0)
            )
        except Exception:
            self._indicator_min_hold_seconds = 0.0
        try:
            self._indicator_reentry_cooldown_seconds = max(
                0.0, float(self.config.get("indicator_reentry_cooldown_seconds") or 0.0)
            )
        except Exception:
            self._indicator_reentry_cooldown_seconds = 0.0
        try:
            self._indicator_flip_cooldown_seconds = max(
                0.0, float(self.config.get("indicator_flip_cooldown_seconds") or 0.0)
            )
        except Exception:
            self._indicator_flip_cooldown_seconds = 0.0
        try:
            self._indicator_flip_cooldown_bars = max(
                0, int(self.config.get("indicator_flip_cooldown_bars") or 0)
            )
        except Exception:
            self._indicator_flip_cooldown_bars = 0
        try:
            self._indicator_min_hold_bars = max(
                0, int(self.config.get("indicator_min_position_hold_bars") or 0)
            )
        except Exception:
            self._indicator_min_hold_bars = 0
        try:
            self._indicator_reentry_cooldown_bars = max(
                0, int(self.config.get("indicator_reentry_cooldown_bars") or 1)
            )
        except Exception:
            self._indicator_reentry_cooldown_bars = 1
        self._indicator_reentry_requires_reset = bool(
            self.config.get("indicator_reentry_requires_signal_reset", True)
        )
        try:
            self._indicator_flip_confirm_bars = max(
                1, int(self.config.get("indicator_flip_confirmation_bars") or 1)
            )
        except Exception:
            self._indicator_flip_confirm_bars = 1
        self._indicator_last_action: dict[tuple[str, str, str], dict[str, float]] = {}
        self._indicator_signal_tracker: dict[tuple[str, str, str], dict[str, float | int | str]] = {}
        self._reentry_blocks: dict[tuple[str, str, str], float] = {}
        self._indicator_reentry_signal_blocks: dict[tuple[str, str, str], str] = {}
        self._indicator_recent_closes: dict[tuple[str, str, str, str], dict[str, float]] = {}
        self._flip_on_close_requests: dict[tuple[str, str, str], dict[str, object]] = {}
        self._flip_on_close_lock = threading.RLock()

    @staticmethod
    def _normalize_signature_tuple(signature: Iterable[str] | None) -> tuple[str, ...] | None:
        parts: list[str] = []
        for label in signature or []:
            text = str(label or "").strip().lower()
            if not text:
                continue
            if text.startswith("slot"):
                parts.append(text)
            else:
                parts.append(_canonical_indicator_token(text) or text)
        if not parts:
            return None
        parts.sort()
        return tuple(parts)

    @staticmethod
    def _normalize_signature_tokens_no_slots(signature: Iterable[str] | None) -> tuple[str, ...]:
        normalized = StrategyEngine._normalize_signature_tuple(signature) or ()
        filtered: list[str] = []
        for token in normalized:
            token_norm = str(token or "").strip().lower()
            if not token_norm or token_norm.startswith("slot"):
                continue
            canon = _canonical_indicator_token(token_norm) or token_norm
            filtered.append(canon)
        return tuple(filtered)

    @staticmethod
    def _normalize_indicator_token_list(tokens: Iterable[str] | str | None) -> list[str]:
        if tokens is None:
            return []
        if isinstance(tokens, str):
            iterable = [tokens]
        else:
            iterable = list(tokens)
        normalized = StrategyEngine._normalize_signature_tokens_no_slots(iterable)
        return list(dict.fromkeys(normalized))

    def run_once(self):
        cw = self.config
        if self.stopped():
            return
        now_ts = time.time()
        allow_opposite_enabled = coerce_bool(self.config.get("allow_opposite_positions"), True)
        if allow_opposite_enabled and coerce_bool(self.config.get("hedge_preserve_opposites"), False):
            allow_opposite_enabled = False  # keep both sides; do not auto-close opposite legs in hedge stacking
        stop_cfg = normalize_stop_loss_dict(cw.get("stop_loss"))
        stop_mode = str(stop_cfg.get("mode") or "usdt").lower()
        if stop_mode not in STOP_LOSS_MODE_ORDER:
            stop_mode = STOP_LOSS_MODE_ORDER[0]
        stop_usdt_limit = max(0.0, float(stop_cfg.get("usdt", 0.0) or 0.0))
        stop_percent_limit = max(0.0, float(stop_cfg.get("percent", 0.0) or 0.0))
        scope = str(stop_cfg.get("scope") or "per_trade").lower()
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        stop_enabled = bool(stop_cfg.get("enabled", False))
        apply_usdt_limit = stop_enabled and stop_mode in ("usdt", "both") and stop_usdt_limit > 0.0
        apply_percent_limit = stop_enabled and stop_mode in ("percent", "both") and stop_percent_limit > 0.0
        stop_enabled = apply_usdt_limit or apply_percent_limit
        account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        is_cumulative = stop_enabled and scope == "cumulative"
        is_entire_account = stop_enabled and scope == "entire_account"
        if is_entire_account and account_type == "FUTURES":
            total_unrealized = 0.0
            try:
                total_unrealized = float(self.binance.get_total_unrealized_pnl())
            except Exception:
                total_unrealized = 0.0
            triggered = False
            reason = None
            if apply_usdt_limit and total_unrealized <= -stop_usdt_limit:
                triggered = True
                reason = f"entire-account-usdt-limit ({total_unrealized:.2f})"
            if not triggered and apply_percent_limit:
                total_wallet = 0.0
                try:
                    total_wallet = float(self.binance.get_total_wallet_balance())
                except Exception:
                    total_wallet = 0.0
                if total_wallet > 0.0 and total_unrealized < 0.0:
                    loss_pct = (abs(total_unrealized) / total_wallet) * 100.0
                    if loss_pct >= stop_percent_limit:
                        triggered = True
                        reason = f"entire-account-percent-limit ({loss_pct:.2f}%)"
            if triggered:
                try:
                    self.log(f"{cw['symbol']}@{cw.get('interval')} entire account stop-loss triggered: {reason}.")
                except Exception:
                    pass
                self._trigger_emergency_close(cw['symbol'], cw.get('interval'), reason or "entire_account_stop")
                return

        # --- Exchange reconciliation (e.g., after liquidation) ---
        try:
            self._reconcile_liquidations(cw["symbol"])
        except Exception:
            pass
        if self.stopped():
            return
        df = self.binance.get_klines(cw['symbol'], cw['interval'], limit=cw.get('lookback', 200))
        if self.stopped():
            return
        ind = self.compute_indicators(df)
        if self.stopped():
            return
        signal, trigger_desc, trigger_price, trigger_sources, trigger_actions = self.generate_signal(df, ind)
        signal_timestamp = time.time() if signal else None
        try:
            current_bar_marker = int(df.index[-1].value) if not df.empty else None
        except Exception:
            current_bar_marker = None
        
        # --- RSI guard-close (interval-scoped) ---
        try:
            rsi_series = ind.get('rsi') or ind.get('RSI') or None
            if rsi_series is not None:
                _, _, last_rsi = self._indicator_prev_live_signal_values(rsi_series)
            else:
                last_rsi = None
        except Exception:
            last_rsi = None

        # Open-state via internal ledger (per symbol, interval, side)
        key_short = (cw['symbol'], cw.get('interval'), 'SELL')
        key_long  = (cw['symbol'], cw.get('interval'), 'BUY')
        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
        long_open  = bool(self._leg_ledger.get(key_long,  {}).get('qty', 0) > 0)

        dual_side = False
        desired_ps_long_guard = None
        desired_ps_short_guard = None
        if account_type == "FUTURES":
            try:
                dual_side = bool(self.binance.get_futures_dual_side())
            except Exception:
                dual_side = False
            desired_ps_long_guard = "LONG" if dual_side else None
            desired_ps_short_guard = "SHORT" if dual_side else None
        allow_opposite_enabled = coerce_bool(self.config.get("allow_opposite_positions"), True)
        # In one-way mode, allow a new order to reduce/flip an opposite leg instead of skipping.
        hedge_overlap_allowed = bool(allow_opposite_enabled)

        # Exit thresholds
        try:
            rsi_cfg = cw.get('indicators',{}).get('rsi',{})
            exit_up = float(rsi_cfg.get('sell_value', 70))
            exit_dn = float(rsi_cfg.get('buy_value', 30))
        except Exception:
            exit_up, exit_dn = 70.0, 30.0

        if account_type == "FUTURES" and last_rsi is not None and not allow_opposite_enabled:
            interval_current = cw.get('interval')
            try:
                if last_rsi >= exit_up and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'BUY'):
                    try:
                        closed_long, _ = self._close_indicator_positions(
                            cw,
                            interval_current,
                            'rsi',
                            'BUY',
                            desired_ps_long_guard,
                            ignore_hold=True,
                            strict_interval=True,
                            reason="rsi_exit",
                        )
                    except Exception:
                        closed_long = 0
                    if closed_long:
                        long_open = bool(self._leg_ledger.get(key_long, {}).get('qty', 0) > 0)
                        try:
                            plural = "entry" if closed_long == 1 else "entries"
                            self.log(
                                f"Closed {closed_long} RSI LONG {plural} for {cw['symbol']}@{cw.get('interval')} (RSI >= {exit_up})."
                            )
                        except Exception:
                            pass
                if last_rsi <= exit_dn and self._indicator_has_open(cw['symbol'], interval_current, 'rsi', 'SELL'):
                    try:
                        closed_short, _ = self._close_indicator_positions(
                            cw,
                            interval_current,
                            'rsi',
                            'SELL',
                            desired_ps_short_guard,
                            ignore_hold=True,
                            strict_interval=True,
                            reason="rsi_exit",
                        )
                    except Exception:
                        closed_short = 0
                    if closed_short:
                        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
                        try:
                            plural = "entry" if closed_short == 1 else "entries"
                            self.log(
                                f"Closed {closed_short} RSI SHORT {plural} for {cw['symbol']}@{cw.get('interval')} (RSI <= {exit_dn})."
                            )
                        except Exception:
                            pass
            except Exception:
                pass

        last_price = None
        try:
            live_price = float(self.binance.get_last_price(cw['symbol']) or 0.0)
            if live_price > 0.0:
                last_price = live_price
        except Exception:
            last_price = None
        if last_price is None and not df.empty:
            try:
                last_price = float(df['close'].iloc[-1])
            except Exception:
                last_price = None
        positions_cache = None
        positions_cache_ok = False

        def _load_positions_cache():
            nonlocal positions_cache, positions_cache_ok
            if positions_cache is None:
                try:
                    positions_cache = self.binance.list_open_futures_positions() or []
                    positions_cache_ok = True
                except Exception:
                    positions_cache = []
                    positions_cache_ok = False
            return positions_cache or []

        if account_type == "FUTURES":
            try:
                _load_positions_cache()
                if positions_cache_ok:
                    self._purge_flat_futures_legs(
                        cw["symbol"],
                        positions_cache,
                        dual_side=dual_side,
                    )
            except Exception:
                pass

        if stop_enabled and last_price is not None and account_type == "FUTURES":
            def _ensure_entry_price(leg_key, expect_long: bool):
                leg = self._leg_ledger.get(leg_key, {}) or {}
                qty_val = float(leg.get("qty") or 0.0)
                entry_px = float(leg.get("entry_price") or 0.0)
                matched_pos = None
                cache = _load_positions_cache()
                for pos in cache:
                    try:
                        if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                            continue
                        amt = float(pos.get("positionAmt") or 0.0)
                        if dual_side:
                            pos_side = str(pos.get("positionSide") or "").upper()
                            if expect_long and pos_side != "LONG":
                                continue
                            if (not expect_long) and pos_side != "SHORT":
                                continue
                            qty_candidate = abs(amt)
                        else:
                            if expect_long and amt <= 0.0:
                                continue
                            if (not expect_long) and amt >= 0.0:
                                continue
                            qty_candidate = abs(amt)
                        if qty_candidate <= 0.0:
                            continue
                        matched_pos = pos
                        if entry_px <= 0.0:
                            try:
                                entry_px = float(pos.get("entryPrice") or entry_px)
                            except Exception:
                                pass
                        break
                    except Exception:
                        continue
                if matched_pos and entry_px > 0.0:
                    leg["entry_price"] = entry_px
                    self._leg_ledger[leg_key] = leg
                return leg, qty_val, entry_px, matched_pos

            leg_long, qty_long, entry_price_long, pos_long = _ensure_entry_price(key_long, True)
            leg_short, qty_short, entry_price_short, pos_short = _ensure_entry_price(key_short, False)
            pos_long_qty_total = 0.0
            pos_short_qty_total = 0.0

            if qty_long <= 0.0 and pos_long:
                try:
                    qty_long = max(0.0, float(pos_long.get("positionAmt") or 0.0))
                except Exception:
                    qty_long = 0.0
                if qty_long > 0.0:
                    self._sync_leg_entry_totals(key_long, qty_long)
            if pos_long:
                try:
                    amt_val = float(pos_long.get("positionAmt") or 0.0)
                    pos_long_qty_total = abs(amt_val)
                except Exception:
                    pos_long_qty_total = 0.0
            if qty_short <= 0.0 and pos_short:
                try:
                    qty_short = abs(float(pos_short.get("positionAmt") or 0.0))
                except Exception:
                    qty_short = 0.0
                if qty_short > 0.0:
                    self._sync_leg_entry_totals(key_short, qty_short)
            if pos_short:
                try:
                    amt_val = float(pos_short.get("positionAmt") or 0.0)
                    pos_short_qty_total = abs(amt_val)
                except Exception:
                    pos_short_qty_total = 0.0

            entries_long = self._leg_entries(key_long)
            entries_short = self._leg_entries(key_short)

            if scope == "per_trade":
                if entries_long:
                    self._evaluate_per_trade_stop(
                        cw,
                        key_long,
                        entries_long,
                        side_label="BUY",
                        last_price=last_price,
                        apply_usdt_limit=apply_usdt_limit,
                        apply_percent_limit=apply_percent_limit,
                        stop_usdt_limit=stop_usdt_limit,
                        stop_percent_limit=stop_percent_limit,
                        dual_side=dual_side,
                    )
                if entries_short:
                    self._evaluate_per_trade_stop(
                        cw,
                        key_short,
                        entries_short,
                        side_label="SELL",
                        last_price=last_price,
                        apply_usdt_limit=apply_usdt_limit,
                        apply_percent_limit=apply_percent_limit,
                        stop_usdt_limit=stop_usdt_limit,
                        stop_percent_limit=stop_percent_limit,
                        dual_side=dual_side,
                    )
                leg_long = self._leg_ledger.get(key_long, {}) or {}
                leg_short = self._leg_ledger.get(key_short, {}) or {}
                qty_long = float(leg_long.get("qty") or 0.0)
                qty_short = float(leg_short.get("qty") or 0.0)
                entry_price_long = float(leg_long.get("entry_price") or 0.0)
                entry_price_short = float(leg_short.get("entry_price") or 0.0)
            elif is_cumulative:
                cache = _load_positions_cache()
                totals = {
                    "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                    "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                }
                for pos in cache:
                    try:
                        if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                            continue
                        pos_side = str(pos.get("positionSide") or "").upper()
                        amt = float(pos.get("positionAmt") or 0.0)
                        entry_px = float(pos.get("entryPrice") or 0.0)
                        if entry_px <= 0.0:
                            continue
                        if dual_side:
                            if pos_side == "LONG":
                                qty_pos = max(0.0, float(pos.get("positionAmt") or 0.0))
                                side_key = "LONG"
                            elif pos_side == "SHORT":
                                qty_pos = max(0.0, abs(float(pos.get("positionAmt") or 0.0)))
                                side_key = "SHORT"
                            else:
                                continue
                        else:
                            if amt > 0.0:
                                qty_pos = amt
                                side_key = "LONG"
                            elif amt < 0.0:
                                qty_pos = abs(amt)
                                side_key = "SHORT"
                            else:
                                continue
                        if qty_pos <= 0.0:
                            continue
                        margin_val = float(pos.get("isolatedWallet") or 0.0)
                        if margin_val <= 0.0:
                            margin_val = float(pos.get("initialMargin") or 0.0)
                        if margin_val <= 0.0:
                            notional_val = abs(float(pos.get("notional") or 0.0))
                            lev = float(pos.get("leverage") or 1.0) or 1.0
                            if lev > 0.0:
                                margin_val = notional_val / lev
                        if side_key == "LONG":
                            loss_val = max(0.0, (entry_px - last_price) * qty_pos)
                        else:
                            loss_val = max(0.0, (last_price - entry_px) * qty_pos)
                        totals[side_key]["qty"] += qty_pos
                        totals[side_key]["loss"] += loss_val
                        totals[side_key]["margin"] += max(0.0, margin_val)
                    except Exception:
                        continue
                cumulative_triggered = False
                for side_key in ("LONG", "SHORT"):
                    data = totals[side_key]
                    if data["qty"] <= 0.0:
                        continue
                    triggered = False
                    if apply_usdt_limit and data["loss"] >= stop_usdt_limit:
                        triggered = True
                    if (
                        not triggered
                        and apply_percent_limit
                        and data["margin"] > 0.0
                        and (data["loss"] / data["margin"] * 100.0) >= stop_percent_limit
                    ):
                        triggered = True
                    if not triggered:
                        continue
                    cumulative_triggered = True
                    close_side = "SELL" if side_key == "LONG" else "BUY"
                    position_side = side_key if dual_side else None
                    start_ts = time.time()
                    try:
                        res = self.binance.close_futures_leg_exact(
                            cw["symbol"], data["qty"], side=close_side, position_side=position_side
                        )
                    except Exception as exc:
                        try:
                            self.log(f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
                        except Exception:
                            pass
                        continue
                    if isinstance(res, dict) and res.get("ok"):
                        latency_s = max(0.0, time.time() - start_ts)
                        target_side_label = "BUY" if side_key == "LONG" else "SELL"
                        payload = self._build_close_event_payload(
                            cw["symbol"], cw.get("interval"), target_side_label, data["qty"], res
                        )
                        try:
                            payload["reason"] = "cumulative_stop_loss"
                        except Exception:
                            pass
                        for leg_key in list(self._leg_ledger.keys()):
                            if leg_key[0] == cw["symbol"] and leg_key[2] == target_side_label:
                                try:
                                    for entry in self._leg_entries(leg_key):
                                        try:
                                            self._mark_indicator_reentry_signal_block(
                                                cw["symbol"],
                                                cw.get("interval"),
                                                entry,
                                                target_side_label,
                                            )
                                        except Exception:
                                            pass
                                        try:
                                            for indicator_key in self._extract_indicator_keys(entry):
                                                self._record_indicator_close(
                                                    cw["symbol"],
                                                    cw.get("interval"),
                                                    indicator_key,
                                                    target_side_label,
                                                    entry.get("qty"),
                                                )
                                        except Exception:
                                            pass
                                        try:
                                            self._queue_flip_on_close(
                                                cw.get("interval"),
                                                target_side_label,
                                                entry,
                                                payload,
                                            )
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                self._remove_leg_entry(leg_key, None)
                        self._mark_guard_closed(cw["symbol"], cw.get("interval"), target_side_label)
                        self._notify_interval_closed(
                            cw["symbol"],
                            cw.get("interval"),
                            target_side_label,
                            **payload,
                            latency_seconds=latency_s,
                            latency_ms=latency_s * 1000.0,
                            reason="cumulative_stop_loss",
                        )
                        try:
                            margin_val = data["margin"] or 0.0
                            pct_loss = (data["loss"] / margin_val * 100.0) if margin_val > 0.0 else 0.0
                            self._log_latency_metric(
                                cw["symbol"],
                                cw.get("interval"),
                                f"cumulative stop-loss {target_side_label}",
                                latency_s,
                            )
                            self.log(
                                f"Cumulative stop-loss closed {target_side_label} for {cw['symbol']}@{cw.get('interval')} "
                                f"(loss {data['loss']:.4f} USDT / {pct_loss:.2f}%)."
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            self.log(
                                f"Cumulative stop-loss close failed for {cw['symbol']} ({side_key}): {res}"
                            )
                        except Exception:
                            pass
                if cumulative_triggered:
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    long_open = False
                    short_open = False
            else:
                if qty_long > 0.0 and entry_price_long > 0.0:
                    loss_usdt_long = max(0.0, (entry_price_long - last_price) * qty_long)
                    denom_long = entry_price_long * qty_long
                    loss_pct_long = (loss_usdt_long / denom_long * 100.0) if denom_long > 0 else 0.0
                    margin_long, margin_balance_long, mm_long, unrealized_loss_long = self._compute_position_margin_fields(
                        pos_long,
                        qty_hint=qty_long,
                        entry_price_hint=entry_price_long,
                    )
                    ratio_long = normalize_margin_ratio((pos_long or {}).get("marginRatio"))
                    if ratio_long <= 0.0 and mm_long > 0.0 and margin_balance_long > 0.0:
                        ratio_long = ((mm_long + unrealized_loss_long) / margin_balance_long) * 100.0
                    if margin_long > 0.0:
                        try:
                            margin_share = margin_long
                            if pos_long_qty_total > 0.0 and qty_long > 0.0:
                                share = min(1.0, qty_long / pos_long_qty_total)
                                margin_share = max(margin_long * share, 1e-12)
                            margin_pct = (loss_usdt_long / margin_share) * 100.0
                            if margin_pct > loss_pct_long:
                                loss_pct_long = margin_pct
                        except Exception:
                            pass
                    triggered_long = False
                    if apply_usdt_limit and loss_usdt_long >= stop_usdt_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and loss_pct_long >= stop_percent_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and ratio_long >= stop_percent_limit:
                        triggered_long = True
                        if ratio_long > loss_pct_long:
                            loss_pct_long = ratio_long
                    if triggered_long:
                        desired_ps = "LONG" if dual_side else None
                        try:
                            start_ts = time.time()
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_long, side="SELL", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                latency_s = max(0.0, time.time() - start_ts)
                                payload = self._build_close_event_payload(
                                    cw["symbol"], cw.get("interval"), "BUY", qty_long, res
                                )
                                try:
                                    payload["reason"] = "stop_loss_long"
                                except Exception:
                                    pass
                                try:
                                    for entry in self._leg_entries(key_long):
                                        self._mark_indicator_reentry_signal_block(
                                            cw["symbol"],
                                            cw.get("interval"),
                                            entry,
                                            "BUY",
                                        )
                                        try:
                                            for indicator_key in self._extract_indicator_keys(entry):
                                                self._record_indicator_close(
                                                    cw["symbol"],
                                                    cw.get("interval"),
                                                    indicator_key,
                                                    "BUY",
                                                    entry.get("qty"),
                                                )
                                        except Exception:
                                            pass
                                        self._queue_flip_on_close(
                                            cw.get("interval"),
                                            "BUY",
                                            entry,
                                            payload,
                                        )
                                except Exception:
                                    pass
                                self._remove_leg_entry(key_long, None)
                                long_open = False
                                self._mark_guard_closed(cw["symbol"], cw.get("interval"), "BUY")
                                self._log_latency_metric(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "stop-loss BUY leg",
                                    latency_s,
                                )
                                self._notify_interval_closed(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "BUY",
                                    **payload,
                                    latency_seconds=latency_s,
                                    latency_ms=latency_s * 1000.0,
                                    reason="stop_loss_long",
                                )
                                try:
                                    self.log(
                                        f"Stop-loss closed BUY for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_long:.4f} USDT / {loss_pct_long:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (BUY): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                self.log(
                                    f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (BUY): {exc}"
                                )
                            except Exception:
                                pass
                if qty_short > 0.0 and entry_price_short > 0.0:
                    loss_usdt_short = max(0.0, (last_price - entry_price_short) * qty_short)
                    denom_short = entry_price_short * qty_short
                    loss_pct_short = (loss_usdt_short / denom_short * 100.0) if denom_short > 0 else 0.0
                    margin_short, margin_balance_short, mm_short, unrealized_loss_short_val = self._compute_position_margin_fields(
                        pos_short,
                        qty_hint=qty_short,
                        entry_price_hint=entry_price_short,
                    )
                    ratio_short = normalize_margin_ratio((pos_short or {}).get("marginRatio"))
                    if ratio_short <= 0.0 and mm_short > 0.0 and margin_balance_short > 0.0:
                        ratio_short = ((mm_short + unrealized_loss_short_val) / margin_balance_short) * 100.0
                    if margin_short > 0.0:
                        try:
                            margin_share = margin_short
                            if pos_short_qty_total > 0.0 and qty_short > 0.0:
                                share = min(1.0, qty_short / pos_short_qty_total)
                                margin_share = max(margin_short * share, 1e-12)
                            margin_pct = (loss_usdt_short / margin_share) * 100.0
                            if margin_pct > loss_pct_short:
                                loss_pct_short = margin_pct
                        except Exception:
                            pass
                    triggered_short = False
                    if apply_usdt_limit and loss_usdt_short >= stop_usdt_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and loss_pct_short >= stop_percent_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and ratio_short >= stop_percent_limit:
                        triggered_short = True
                        if ratio_short > loss_pct_short:
                            loss_pct_short = ratio_short
                    if triggered_short:
                        desired_ps = "SHORT" if dual_side else None
                        try:
                            start_ts = time.time()
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_short, side="BUY", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                latency_s = max(0.0, time.time() - start_ts)
                                payload = self._build_close_event_payload(
                                    cw["symbol"], cw.get("interval"), "SELL", qty_short, res
                                )
                                try:
                                    payload["reason"] = "stop_loss_short"
                                except Exception:
                                    pass
                                try:
                                    for entry in self._leg_entries(key_short):
                                        self._mark_indicator_reentry_signal_block(
                                            cw["symbol"],
                                            cw.get("interval"),
                                            entry,
                                            "SELL",
                                        )
                                        try:
                                            for indicator_key in self._extract_indicator_keys(entry):
                                                self._record_indicator_close(
                                                    cw["symbol"],
                                                    cw.get("interval"),
                                                    indicator_key,
                                                    "SELL",
                                                    entry.get("qty"),
                                                )
                                        except Exception:
                                            pass
                                        self._queue_flip_on_close(
                                            cw.get("interval"),
                                            "SELL",
                                            entry,
                                            payload,
                                        )
                                except Exception:
                                    pass
                                self._remove_leg_entry(key_short, None)
                                short_open = False
                                self._mark_guard_closed(cw["symbol"], cw.get("interval"), "SELL")
                                self._log_latency_metric(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "stop-loss SELL leg",
                                    latency_s,
                                )
                                self._notify_interval_closed(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    "SELL",
                                    **payload,
                                    latency_seconds=latency_s,
                                    latency_ms=latency_s * 1000.0,
                                    reason="stop_loss_short",
                                )
                                try:
                                    self.log(
                                        f"Stop-loss closed SELL for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_short:.4f} USDT / {loss_pct_short:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (SELL): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                    self.log(
                                        f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (SELL): {exc}"
                                    )
                            except Exception:
                                pass
            leg_long_state = self._leg_ledger.get(key_long, {}) or {}
            leg_short_state = self._leg_ledger.get(key_short, {}) or {}
            qty_long = float(leg_long_state.get("qty") or 0.0)
            qty_short = float(leg_short_state.get("qty") or 0.0)
            entry_price_long = float(leg_long_state.get("entry_price") or 0.0)
            entry_price_short = float(leg_short_state.get("entry_price") or 0.0)
            long_open = qty_long > 0.0
            short_open = qty_short > 0.0

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
            indicator_norm = _canonical_indicator_token(indicator_name) or str(indicator_name or "").strip().lower()
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
                indicator_key = indicator_label.lower()
                if not indicator_key:
                    continue
                action_norm = str(indicator_action or "").strip().lower()
                interval_current = cw.get("interval")
                try:
                    interval_seconds_est = float(_interval_to_seconds(str(interval_current or "1m")))
                except Exception:
                    interval_seconds_est = 60.0
                indicator_interval_tokens: set[str] = set(self._tokenize_interval_label(interval_current))
                label_interval_tokens = StrategyEngine._extract_interval_tokens_from_labels([indicator_label])
                if label_interval_tokens:
                    indicator_interval_tokens.update(label_interval_tokens)
                if action_norm not in {"buy", "sell"}:
                    continue
                action_side_label = "BUY" if action_norm == "buy" else "SELL"
                opp_side_label = "SELL" if action_side_label == "BUY" else "BUY"
                reason_signal = f"{indicator_key}_{action_norm}_signal"
                recent_close = None
                try:
                    recent_close_window = max(5.0, min(interval_seconds_est * 1.5, 600.0))
                    recent_close = self._recent_indicator_close(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        opp_side_label,
                        max_age_seconds=recent_close_window,
                    )
                except Exception:
                    recent_close = None
                # Exclusivity: never allow both long+short for the same indicator/interval.
                same_side_live = self._indicator_live_qty_total(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    action_side_label,
                    interval_aliases=indicator_interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=False,
                )
                opp_side_live = self._indicator_live_qty_total(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    opp_side_label,
                    interval_aliases=indicator_interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=False,
                )
                if self._indicator_reentry_requires_reset:
                    indicator_norm = _canonical_indicator_token(indicator_key) or indicator_key
                    block_key = (
                        str(cw["symbol"] or "").upper(),
                        str(interval_current or "").strip().lower() or "default",
                        indicator_norm,
                    )
                    block_side = self._indicator_reentry_signal_blocks.get(block_key)
                    if block_side == action_side_label and opp_side_live <= qty_tol_indicator:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_norm} {action_side_label} "
                                "blocked: signal has not reset since last close."
                            )
                        except Exception:
                            pass
                        continue
                if same_side_live > qty_tol_indicator and opp_side_live <= qty_tol_indicator:
                    stale_cleared = False
                    if account_type == "FUTURES":
                        try:
                            desired_ps_check = None
                            if dual_side:
                                desired_ps_check = "LONG" if action_side_label == "BUY" else "SHORT"
                            exch_qty = max(
                                0.0,
                                float(
                                    self._current_futures_position_qty(
                                        cw["symbol"], action_side_label, desired_ps_check
                                    )
                                    or 0.0
                                ),
                            )
                            tol_live = max(1e-9, exch_qty * 1e-6)
                            if exch_qty <= tol_live:
                                self._purge_indicator_tracking(
                                    cw["symbol"],
                                    interval_current,
                                    indicator_key,
                                    action_side_label,
                                )
                                same_side_live = 0.0
                                stale_cleared = True
                                try:
                                    self.log(
                                        f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                                        f"{action_side_label} stale guard cleared (no live position)."
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            stale_cleared = False
                    if not stale_cleared:
                        # Same side already active; skip duplicate open.
                        continue
                if not self._indicator_signal_confirmation_ready(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    action_norm,
                    interval_seconds_est,
                    now_indicator_ts,
                ):
                    continue
                cooldown_remaining = self._indicator_cooldown_remaining(
                    cw["symbol"],
                    interval_current,
                    indicator_key,
                    action_side_label,
                    interval_seconds_est,
                    now_indicator_ts,
                )
                if cooldown_remaining > 0.0:
                    allow_flip_cooldown_bypass = False
                    if opp_side_live > qty_tol_indicator:
                        allow_flip_cooldown_bypass = True
                    else:
                        try:
                            opp_live_exch = self._indicator_live_qty_total(
                                cw["symbol"],
                                interval_current,
                                indicator_key,
                                "SELL" if action_norm == "buy" else "BUY",
                                interval_aliases=indicator_interval_tokens,
                                strict_interval=True,
                                use_exchange_fallback=True,
                            )
                            if opp_live_exch > qty_tol_indicator:
                                allow_flip_cooldown_bypass = True
                        except Exception:
                            allow_flip_cooldown_bypass = False
                    if not allow_flip_cooldown_bypass and recent_close:
                        allow_flip_cooldown_bypass = True
                    if not allow_flip_cooldown_bypass:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                                f"{action_side_label} suppressed: cooldown {cooldown_remaining:.1f}s remaining."
                            )
                        except Exception:
                            pass
                        continue
                # Prevent re-entry spam after a position is closed.
                reentry_block = self._reentry_block_remaining(
                    cw["symbol"], interval_current, action_side_label, now_ts=now_ts
                )
                if reentry_block > 0.0:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_current} {action_side_label} re-entry guard: waiting {reentry_block:.1f}s."
                        )
                    except Exception:
                        pass
                    continue
                closed_count = 0
                opposite_qty = opp_side_live

                if allow_opposite_enabled:
                    # Hedge mode: per-slot flip. Close the matching opposite leg for this indicator+interval,
                    # then open the requested side without touching other intervals/indicators.
                    close_side = "SELL" if action_norm == "buy" else "BUY"
                    open_side = "BUY" if action_norm == "buy" else "SELL"
                    desired_ps_close = desired_ps_short if close_side == "SELL" else desired_ps_long

                    close_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        close_side,
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    fallback_live_qty = 0.0
                    if close_qty <= qty_tol_indicator:
                        fallback_live_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            close_side,
                        )
                        if fallback_live_qty > qty_tol_indicator:
                            close_qty = fallback_live_qty
                    if close_qty <= qty_tol_indicator:
                        protect_other = False
                        try:
                            protect_other = self._symbol_side_has_other_positions(
                                cw["symbol"], interval_current, indicator_key, close_side
                            )
                        except Exception:
                            protect_other = False
                        if not protect_other:
                            try:
                                exch_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], close_side, desired_ps_close
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                exch_qty = 0.0
                            if exch_qty > qty_tol_indicator:
                                close_qty = exch_qty

                    if close_qty > qty_tol_indicator:
                        closed_opposite, closed_qty = self._close_indicator_positions(
                            cw,
                            interval_current,
                            indicator_key,
                            close_side,
                            desired_ps_close,
                            signature_hint=(indicator_key,),
                            ignore_hold=True,
                            interval_aliases=indicator_interval_tokens,
                            qty_limit=close_qty,
                            strict_interval=True,
                            allow_hedge_close=True,
                            reason=reason_signal,
                        )
                        closed_count = closed_opposite
                        if closed_opposite <= 0:
                            # Fallback: force-close via exchange positions if ledger-scoped close failed.
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                open_side,
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=close_qty,
                            ):
                                continue
                            closed_opposite = 1
                            closed_qty = max(closed_qty, close_qty)
                        remaining_after_close = self._indicator_open_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            close_side,
                            interval_aliases=indicator_interval_tokens,
                            strict_interval=True,
                        )
                        if remaining_after_close > qty_tol_indicator:
                            try:
                                exch_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], close_side, desired_ps_close
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                exch_qty = 0.0
                            tol_live = max(1e-9, exch_qty * 1e-6)
                            if exch_qty <= tol_live:
                                try:
                                    self._purge_indicator_tracking(
                                        cw["symbol"], interval_current, indicator_key, close_side
                                    )
                                except Exception:
                                    pass
                                remaining_after_close = 0.0
                        if remaining_after_close > qty_tol_indicator:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} {open_side} deferred: "
                                    f"{remaining_after_close:.10f} {close_side.lower()} qty still open."
                                )
                            except Exception:
                                pass
                            continue
                        flip_from_side = close_side if closed_qty > 0.0 else None
                        if closed_opposite > 0 and flip_from_side is None:
                            flip_from_side = close_side
                        flip_qty = closed_qty if closed_qty > 0.0 else 0.0
                        indicator_order_requests.append(
                            {
                                "side": open_side,
                                "labels": [indicator_label],
                                "signature": (indicator_key,),
                                "indicator_key": indicator_key,
                                "flip_from": flip_from_side,
                                "flip_qty": flip_qty,
                                "flip_qty_target": flip_qty,
                            }
                        )
                        continue

                if action_norm == "buy":
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "SELL",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if remaining_indicator_qty <= qty_tol_indicator:
                        fallback_live_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                        )
                        if fallback_live_qty <= qty_tol_indicator:
                            try:
                                fallback_live_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "SELL", desired_ps_short
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_live_qty = 0.0
                        if fallback_live_qty > qty_tol_indicator:
                            remaining_indicator_qty = fallback_live_qty
                    closed_short = 0
                    closed_short_qty = 0.0
                    qty_cap = None
                    needs_close_short = remaining_indicator_qty > qty_tol_indicator
                    if remaining_indicator_qty > qty_tol_indicator or needs_close_short:
                        qty_cap = remaining_indicator_qty if remaining_indicator_qty > qty_tol_indicator else None
                        closed_short, closed_short_qty = self._close_indicator_positions(
                            cw,
                            interval_current,
                            indicator_key,
                            "SELL",
                            desired_ps_short,
                            signature_hint=(indicator_key,),
                            ignore_hold=True,
                            interval_aliases=indicator_interval_tokens,
                            qty_limit=qty_cap,
                            strict_interval=True,
                            allow_hedge_close=True,
                            reason=reason_signal,
                        )
                        closed_count = closed_short
                        if closed_short <= 0:
                            try:
                                still_open = self._indicator_has_open(
                                    cw["symbol"], interval_current, indicator_key, "SELL"
                                )
                            except Exception:
                                still_open = False
                            if still_open:
                                target_qty_hint = qty_cap
                                if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_indicator_qty > 0.0:
                                    target_qty_hint = remaining_indicator_qty
                                if not self._close_opposite_position(
                                    cw["symbol"],
                                    interval_current,
                                    "BUY",
                                    trigger_signature=(indicator_key,),
                                    indicator_key=(indicator_key,),
                                    target_qty=target_qty_hint,
                                ):
                                    continue
                                closed_short = 1
                    if closed_short <= 0:
                        fallback_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                        )
                        if fallback_qty <= 0.0:
                            try:
                                fallback_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "SELL", desired_ps_short
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_qty = 0.0
                            if fallback_qty > 0.0:
                                retry_count, retry_qty = self._close_indicator_positions(
                                    cw,
                                    interval_current,
                                    indicator_key,
                                    "SELL",
                                    desired_ps_short,
                                    signature_hint=(indicator_key,),
                                    ignore_hold=True,
                                    interval_aliases=indicator_interval_tokens,
                                    qty_limit=fallback_qty,
                                    strict_interval=True,
                                    allow_hedge_close=True,
                                    reason=reason_signal,
                                )
                                closed_short = retry_count
                                closed_short_qty = retry_qty
                                closed_count = retry_count
                    if closed_short <= 0:
                        remaining_short_qty = self._indicator_open_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                            interval_aliases=indicator_interval_tokens,
                            strict_interval=True,
                        )
                        if remaining_short_qty > qty_tol_indicator:
                            try:
                                exch_short_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "SELL", desired_ps_short
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                exch_short_qty = 0.0
                            tol_live = max(1e-9, exch_short_qty * 1e-6)
                            if exch_short_qty <= tol_live:
                                try:
                                    self._purge_indicator_tracking(
                                        cw["symbol"], interval_current, indicator_key, "SELL"
                                    )
                                except Exception:
                                    pass
                                remaining_short_qty = 0.0
                        if remaining_short_qty > qty_tol_indicator:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY skipped: "
                                    "short leg still live on exchange."
                                )
                            except Exception:
                                pass
                            continue
                    flip_from_side = None
                    flip_qty = 0.0
                    flip_qty_target = 0.0
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "SELL",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if closed_short > 0 and closed_short_qty > 0.0:
                        flip_from_side = "SELL"
                        flip_qty = closed_short_qty
                        flip_qty_target = closed_short_qty
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current} {indicator_key} flip SELL→BUY "
                                f"(closed {flip_qty:.10f})."
                            )
                        except Exception:
                            pass
                    elif remaining_indicator_qty > 0.0:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY deferred: "
                                f"{remaining_indicator_qty:.10f} short qty still open."
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        protect_short_residual = self._symbol_side_has_other_positions(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "SELL",
                        )
                        live_short_residual = 0.0
                        try:
                            live_short_residual = max(
                                0.0,
                                float(self._current_futures_position_qty(cw["symbol"], "SELL", desired_ps_short)),
                            )
                        except Exception:
                            live_short_residual = 0.0
                        tol_live = max(1e-9, live_short_residual * 1e-6)
                        if protect_short_residual and live_short_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY skipping residual short close "
                                    f"(other SELL legs still active)."
                                )
                            except Exception:
                                pass
                        elif live_short_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY forcing close of residual short "
                                    f"({live_short_residual:.10f})."
                                )
                            except Exception:
                                pass
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                "BUY",
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=live_short_residual,
                            ):
                                continue
                            flip_from_side = "SELL"
                            flip_qty = live_short_residual
                            flip_qty_target = live_short_residual
                        else:
                            current_short_qty = self._indicator_open_qty(
                                cw["symbol"],
                                interval_current,
                                indicator_key,
                                "SELL",
                                interval_aliases=indicator_interval_tokens,
                                strict_interval=True,
                            )
                            if current_short_qty > qty_tol_indicator:
                                try:
                                    exch_short_qty = max(
                                        0.0,
                                        float(
                                            self._current_futures_position_qty(
                                                cw["symbol"], "SELL", desired_ps_short
                                            )
                                            or 0.0
                                        ),
                                    )
                                except Exception:
                                    exch_short_qty = 0.0
                                tol_live = max(1e-9, exch_short_qty * 1e-6)
                                if exch_short_qty <= tol_live:
                                    try:
                                        self._purge_indicator_tracking(
                                            cw["symbol"], interval_current, indicator_key, "SELL"
                                        )
                                    except Exception:
                                        pass
                                    current_short_qty = 0.0
                            if current_short_qty > qty_tol_indicator:
                                if (closed_short_qty or 0.0) <= 0.0 and (flip_qty or 0.0) <= 0.0:
                                    continue
                    if closed_short > 0 and flip_from_side is None:
                        flip_from_side = "SELL"
                    if flip_from_side is None and recent_close:
                        flip_from_side = "SELL"
                        try:
                            if flip_qty <= 0.0:
                                flip_qty = float(recent_close.get("qty") or 0.0)
                            if flip_qty_target <= 0.0 and flip_qty > 0.0:
                                flip_qty_target = flip_qty
                        except Exception:
                            pass
                    current_long_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "BUY",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if current_long_qty > qty_tol_indicator:
                        try:
                            exch_long_qty = max(
                                0.0,
                                float(
                                    self._current_futures_position_qty(
                                        cw["symbol"], "BUY", desired_ps_long
                                    )
                                    or 0.0
                                ),
                            )
                        except Exception:
                            exch_long_qty = 0.0
                        tol_live = max(1e-9, exch_long_qty * 1e-6)
                        if exch_long_qty <= tol_live:
                            try:
                                self._purge_indicator_tracking(
                                    cw["symbol"], interval_current, indicator_key, "BUY"
                                )
                            except Exception:
                                pass
                            current_long_qty = 0.0
                    if current_long_qty > qty_tol_indicator:
                        continue
                    bypass_reentry_guard = bool(
                        flip_from_side
                        or (closed_short or 0) > 0
                        or (closed_short_qty or 0.0) > 0.0
                        or (flip_qty or 0.0) > 0.0
                    )
                    if not bypass_reentry_guard:
                        reentry_remaining = self._reentry_block_remaining(
                            cw["symbol"],
                            interval_current,
                            "BUY",
                            now_ts=now_indicator_ts,
                        )
                        if reentry_remaining > 0.0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY suppressed by "
                                    f"re-entry guard ({reentry_remaining:.1f}s)."
                                )
                            except Exception:
                                pass
                            continue
                    indicator_order_requests.append(
                        {
                            "side": "BUY",
                            "labels": [indicator_label],
                            "signature": (indicator_key,),
                            "indicator_key": indicator_key,
                            "flip_from": flip_from_side,
                            "flip_qty": flip_qty,
                            "flip_qty_target": flip_qty_target,
                        }
                    )
                elif action_norm == "sell":
                    # Close existing longs for this indicator on this interval.
                    remaining_long_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "BUY",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if remaining_long_qty <= qty_tol_indicator:
                        fallback_live_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                        )
                        if fallback_live_qty <= qty_tol_indicator:
                            try:
                                fallback_live_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "BUY", desired_ps_long
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_live_qty = 0.0
                        if fallback_live_qty > qty_tol_indicator:
                            remaining_long_qty = fallback_live_qty
                    closed_long = 0
                    closed_long_qty = 0.0
                    qty_cap = None
                    needs_close_long = remaining_long_qty > qty_tol_indicator
                    if remaining_long_qty > qty_tol_indicator or needs_close_long:
                        qty_cap = remaining_long_qty if remaining_long_qty > qty_tol_indicator else None
                        closed_long, closed_long_qty = self._close_indicator_positions(
                            cw,
                            interval_current,
                            indicator_key,
                            "BUY",
                            desired_ps_long,
                            signature_hint=(indicator_key,),
                            ignore_hold=True,
                            interval_aliases=indicator_interval_tokens,
                            qty_limit=qty_cap,
                            strict_interval=True,
                            allow_hedge_close=True,
                            reason=reason_signal,
                        )
                        closed_count = closed_long
                    if closed_long <= 0:
                        try:
                            still_open = self._indicator_has_open(
                                cw["symbol"], interval_current, indicator_key, "BUY"
                            )
                        except Exception:
                            still_open = False
                        if still_open:
                            target_qty_hint = qty_cap
                            if (target_qty_hint is None or target_qty_hint <= 0.0) and remaining_long_qty > 0.0:
                                target_qty_hint = remaining_long_qty
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                "SELL",
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=target_qty_hint,
                            ):
                                continue
                            closed_long = 1
                    if closed_long <= 0:
                        fallback_qty = self._indicator_trade_book_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                        )
                        if fallback_qty <= 0.0:
                            try:
                                fallback_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "BUY", desired_ps_long
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                fallback_qty = 0.0
                        if fallback_qty > 0.0:
                            retry_count, retry_qty = self._close_indicator_positions(
                                cw,
                                interval_current,
                                indicator_key,
                                "BUY",
                                desired_ps_long,
                                signature_hint=(indicator_key,),
                                ignore_hold=True,
                                interval_aliases=indicator_interval_tokens,
                                qty_limit=fallback_qty,
                                strict_interval=True,
                                allow_hedge_close=True,
                                reason=reason_signal,
                            )
                            closed_long = retry_count
                            closed_long_qty = retry_qty
                            closed_count = retry_count
                    if closed_long <= 0:
                        remaining_long_qty = self._indicator_open_qty(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                            interval_aliases=indicator_interval_tokens,
                            strict_interval=True,
                        )
                        if remaining_long_qty > qty_tol_indicator:
                            try:
                                exch_long_qty = max(
                                    0.0,
                                    float(
                                        self._current_futures_position_qty(
                                            cw["symbol"], "BUY", desired_ps_long
                                        )
                                        or 0.0
                                    ),
                                )
                            except Exception:
                                exch_long_qty = 0.0
                            tol_live = max(1e-9, exch_long_qty * 1e-6)
                            if exch_long_qty <= tol_live:
                                try:
                                    self._purge_indicator_tracking(
                                        cw["symbol"], interval_current, indicator_key, "BUY"
                                    )
                                except Exception:
                                    pass
                                remaining_long_qty = 0.0
                        if remaining_long_qty > qty_tol_indicator:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL skipped: "
                                    "long leg still live on exchange."
                                )
                            except Exception:
                                pass
                            continue
                    flip_from_side = None
                    flip_qty = 0.0
                    flip_qty_target = 0.0
                    remaining_indicator_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "BUY",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if closed_long > 0 and closed_long_qty > 0.0:
                        flip_from_side = "BUY"
                        flip_qty = closed_long_qty
                        flip_qty_target = closed_long_qty
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current} {indicator_key} flip BUY→SELL "
                                f"(closed {flip_qty:.10f})."
                            )
                        except Exception:
                            pass
                    elif remaining_indicator_qty > 0.0:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL deferred: "
                                f"{remaining_indicator_qty:.10f} long qty still open."
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        protect_long_residual = self._symbol_side_has_other_positions(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            "BUY",
                        )
                        live_long_residual = 0.0
                        try:
                            live_long_residual = max(
                                0.0,
                                float(self._current_futures_position_qty(cw["symbol"], "BUY", desired_ps_long)),
                            )
                        except Exception:
                            live_long_residual = 0.0
                        tol_live = max(1e-9, live_long_residual * 1e-6)
                        if protect_long_residual and live_long_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL skipping residual long close "
                                    f"(other BUY legs still active)."
                                )
                            except Exception:
                                pass
                        elif live_long_residual > tol_live:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL forcing close of residual long "
                                    f"({live_long_residual:.10f})."
                                )
                            except Exception:
                                pass
                            if not self._close_opposite_position(
                                cw["symbol"],
                                interval_current,
                                "SELL",
                                trigger_signature=(indicator_key,),
                                indicator_key=(indicator_key,),
                                target_qty=live_long_residual,
                            ):
                                continue
                            flip_from_side = "BUY"
                            flip_qty = live_long_residual
                            flip_qty_target = live_long_residual
                        else:
                            current_long_qty = self._indicator_open_qty(
                                cw["symbol"],
                                interval_current,
                                indicator_key,
                                "BUY",
                                interval_aliases=indicator_interval_tokens,
                                strict_interval=True,
                            )
                            if current_long_qty > qty_tol_indicator:
                                try:
                                    exch_long_qty = max(
                                        0.0,
                                        float(
                                            self._current_futures_position_qty(
                                                cw["symbol"], "BUY", desired_ps_long
                                            )
                                            or 0.0
                                        ),
                                    )
                                except Exception:
                                    exch_long_qty = 0.0
                                tol_live = max(1e-9, exch_long_qty * 1e-6)
                                if exch_long_qty <= tol_live:
                                    try:
                                        self._purge_indicator_tracking(
                                            cw["symbol"], interval_current, indicator_key, "BUY"
                                        )
                                    except Exception:
                                        pass
                                    current_long_qty = 0.0
                            if current_long_qty > qty_tol_indicator:
                                if (closed_long_qty or 0.0) <= 0.0 and (flip_qty or 0.0) <= 0.0:
                                    continue
                    if closed_long > 0 and flip_from_side is None:
                        flip_from_side = "BUY"
                    if flip_from_side is None and recent_close:
                        flip_from_side = "BUY"
                        try:
                            if flip_qty <= 0.0:
                                flip_qty = float(recent_close.get("qty") or 0.0)
                            if flip_qty_target <= 0.0 and flip_qty > 0.0:
                                flip_qty_target = flip_qty
                        except Exception:
                            pass
                    current_short_qty = self._indicator_open_qty(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        "SELL",
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                    )
                    if current_short_qty > qty_tol_indicator:
                        try:
                            exch_short_qty = max(
                                0.0,
                                float(
                                    self._current_futures_position_qty(
                                        cw["symbol"], "SELL", desired_ps_short
                                    )
                                    or 0.0
                                ),
                            )
                        except Exception:
                            exch_short_qty = 0.0
                        tol_live = max(1e-9, exch_short_qty * 1e-6)
                        if exch_short_qty <= tol_live:
                            try:
                                self._purge_indicator_tracking(
                                    cw["symbol"], interval_current, indicator_key, "SELL"
                                )
                            except Exception:
                                pass
                            current_short_qty = 0.0
                    if current_short_qty > qty_tol_indicator:
                        continue
                    bypass_reentry_guard = bool(
                        flip_from_side
                        or (closed_long or 0) > 0
                        or (closed_long_qty or 0.0) > 0.0
                        or (flip_qty or 0.0) > 0.0
                    )
                    if not bypass_reentry_guard:
                        reentry_remaining = self._reentry_block_remaining(
                            cw["symbol"],
                            interval_current,
                            "SELL",
                            now_ts=now_indicator_ts,
                        )
                        if reentry_remaining > 0.0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL suppressed by "
                                    f"re-entry guard ({reentry_remaining:.1f}s)."
                                )
                            except Exception:
                                pass
                            continue
                    indicator_order_requests.append(
                        {
                            "side": "SELL",
                            "labels": [indicator_label],
                            "signature": (indicator_key,),
                            "indicator_key": indicator_key,
                            "flip_from": flip_from_side,
                            "flip_qty": flip_qty,
                            "flip_qty_target": flip_qty_target,
                        }
                    )
            if not indicator_order_requests:
                for indicator_name, indicator_action in trigger_actions.items():
                    indicator_label = str(indicator_name or "").strip()
                    if not indicator_label:
                        continue
                    indicator_key = indicator_label.lower()
                    interval_current = cw.get("interval")
                    action_norm = str(indicator_action or "").strip().lower()
                    try:
                        interval_seconds_est = float(_interval_to_seconds(str(interval_current or "1m")))
                    except Exception:
                        interval_seconds_est = 60.0
                    if action_norm not in {"buy", "sell"}:
                        continue
                    if not self._indicator_signal_confirmation_ready(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        action_norm,
                        interval_seconds_est,
                        now_indicator_ts,
                    ):
                        continue
                    action_side_label = "BUY" if action_norm == "buy" else "SELL"
                    opp_side_label = "SELL" if action_side_label == "BUY" else "BUY"
                    indicator_interval_tokens = set(self._tokenize_interval_label(interval_current))
                    label_interval_tokens = StrategyEngine._extract_interval_tokens_from_labels([indicator_label])
                    if label_interval_tokens:
                        indicator_interval_tokens.update(label_interval_tokens)
                    opp_live_qty = 0.0
                    try:
                        opp_live_qty = self._indicator_live_qty_total(
                            cw["symbol"],
                            interval_current,
                            indicator_key,
                            opp_side_label,
                            interval_aliases=indicator_interval_tokens,
                            strict_interval=True,
                            use_exchange_fallback=False,
                        )
                    except Exception:
                        opp_live_qty = 0.0
                    if opp_live_qty <= qty_tol_indicator:
                        try:
                            account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
                        except Exception:
                            account_type = ""
                        if account_type == "FUTURES":
                            protect_other = False
                            try:
                                protect_other = self._symbol_side_has_other_positions(
                                    cw["symbol"], interval_current, indicator_key, opp_side_label
                                )
                            except Exception:
                                protect_other = False
                            if not protect_other:
                                try:
                                    desired_ps_check = None
                                    if self.binance.get_futures_dual_side():
                                        desired_ps_check = "LONG" if opp_side_label == "BUY" else "SHORT"
                                    exch_qty = max(
                                        0.0,
                                        float(
                                            self._current_futures_position_qty(
                                                cw["symbol"], opp_side_label, desired_ps_check
                                            )
                                            or 0.0
                                        ),
                                    )
                                except Exception:
                                    exch_qty = 0.0
                                if exch_qty > qty_tol_indicator:
                                    opp_live_qty = exch_qty
                    if opp_live_qty > qty_tol_indicator:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                                f"{action_side_label} skipped: opposite {opp_side_label} still open "
                                f"({opp_live_qty:.10f})."
                            )
                            self.log(
                                f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} "
                                f"guard=opp_open skip {action_side_label}."
                            )
                        except Exception:
                            pass
                        continue
                    if action_norm == "buy":
                        if not hedge_overlap_allowed:
                            live_short_qty = 0.0
                            try:
                                live_short_qty = max(
                                    0.0,
                                    float(self._current_futures_position_qty(cw["symbol"], "SELL", desired_ps_short)),
                                )
                            except Exception:
                                live_short_qty = 0.0
                            if live_short_qty > 0.0:
                                try:
                                    self.log(
                                        f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY skipped:"
                                        f" short leg still live on exchange ({live_short_qty:.10f})."
                                    )
                                except Exception:
                                    pass
                                continue
                        reentry_remaining = self._reentry_block_remaining(
                            cw["symbol"],
                            interval_current,
                            "BUY",
                            now_ts=now_indicator_ts,
                        )
                        if reentry_remaining > 0.0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} BUY suppressed by "
                                    f"re-entry guard ({reentry_remaining:.1f}s)."
                                )
                            except Exception:
                                pass
                            continue
                        indicator_order_requests.append(
                            {
                                "side": "BUY",
                                "labels": [indicator_label],
                                "signature": (indicator_key,),
                                "indicator_key": indicator_key,
                            }
                        )
                    else:
                        if not hedge_overlap_allowed:
                            live_long_qty = 0.0
                            try:
                                live_long_qty = max(
                                    0.0,
                                    float(self._current_futures_position_qty(cw["symbol"], "BUY", desired_ps_long)),
                                )
                            except Exception:
                                live_long_qty = 0.0
                            if live_long_qty > 0.0:
                                try:
                                    self.log(
                                        f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL skipped:"
                                        f" long leg still live on exchange ({live_long_qty:.10f})."
                                    )
                                except Exception:
                                    pass
                                continue
                        reentry_remaining = self._reentry_block_remaining(
                            cw["symbol"],
                            interval_current,
                            "SELL",
                            now_ts=now_indicator_ts,
                        )
                        if reentry_remaining > 0.0:
                            try:
                                self.log(
                                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} SELL suppressed by "
                                    f"re-entry guard ({reentry_remaining:.1f}s)."
                                )
                            except Exception:
                                pass
                            continue
                        indicator_order_requests.append(
                            {
                                "side": "SELL",
                                "labels": [indicator_label],
                                "signature": (indicator_key,),
                                "indicator_key": indicator_key,
                            }
                        )
        flip_requests = self._drain_flip_on_close_requests(cw.get("interval"))
        if flip_requests:
            require_flip_signal = coerce_bool(self.config.get("require_indicator_flip_signal"), True)
            strict_flip_guard = coerce_bool(self.config.get("strict_indicator_flip_enforcement"), True)
            allow_without_signal = coerce_bool(
                self.config.get("allow_indicator_close_without_signal"), False
            )
            enforce_flip_signal_confirmation = (
                require_flip_signal and strict_flip_guard and not allow_without_signal
            )
            existing_map: dict[tuple[str, str], dict[str, object]] = {}
            for req in indicator_order_requests:
                side_val = str(req.get("side") or "").upper()
                if side_val not in ("BUY", "SELL"):
                    continue
                indicator_token = _canonical_indicator_token(req.get("indicator_key")) or None
                if not indicator_token:
                    sig = req.get("signature") or ()
                    if sig:
                        indicator_token = _canonical_indicator_token(sig[0]) or str(sig[0] or "").strip().lower()
                if not indicator_token:
                    continue
                existing_map[(indicator_token, side_val)] = req
            interval_current = cw.get("interval")
            indicator_interval_tokens = set(self._tokenize_interval_label(interval_current))
            for req in flip_requests:
                indicator_key = _canonical_indicator_token(req.get("indicator_key")) or str(
                    req.get("indicator_key") or ""
                ).strip().lower()
                side_value = str(req.get("side") or "").upper()
                if not indicator_key or side_value not in ("BUY", "SELL"):
                    continue
                flip_from = str(req.get("flip_from") or "").upper()
                if flip_from in ("BUY", "SELL") and flip_from != side_value:
                    try:
                        self._purge_indicator_tracking(
                            cw["symbol"], interval_current, indicator_key, side_value
                        )
                    except Exception:
                        pass
                existing_req = existing_map.get((indicator_key, side_value))
                if existing_req is not None:
                    if not existing_req.get("indicator_key"):
                        existing_req["indicator_key"] = indicator_key
                    if not existing_req.get("flip_from") and req.get("flip_from"):
                        existing_req["flip_from"] = req.get("flip_from")
                    try:
                        existing_flip_qty = float(existing_req.get("flip_qty") or 0.0)
                    except Exception:
                        existing_flip_qty = 0.0
                    try:
                        existing_flip_target = float(existing_req.get("flip_qty_target") or 0.0)
                    except Exception:
                        existing_flip_target = 0.0
                    try:
                        req_flip_qty = float(req.get("qty") or 0.0)
                    except Exception:
                        req_flip_qty = 0.0
                    if existing_flip_qty <= 0.0 and req_flip_qty > 0.0:
                        existing_req["flip_qty"] = req_flip_qty
                    if existing_flip_target <= 0.0 and req_flip_qty > 0.0:
                        existing_req["flip_qty_target"] = req_flip_qty
                    existing_actions = existing_req.get("trigger_actions")
                    if not isinstance(existing_actions, dict):
                        existing_actions = {}
                    existing_actions[indicator_key] = side_value.lower()
                    existing_req["trigger_actions"] = existing_actions
                    continue
                if enforce_flip_signal_confirmation:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} {side_value} "
                            "flip request ignored (waiting for live indicator confirmation)."
                        )
                    except Exception:
                        pass
                    continue
                allow_exchange_fallback = True
                try:
                    allow_exchange_fallback = not coerce_bool(
                        self.config.get("allow_opposite_positions"), True
                    )
                    live_qty = self._indicator_live_qty_total(
                        cw["symbol"],
                        interval_current,
                        indicator_key,
                        side_value,
                        interval_aliases=indicator_interval_tokens,
                        strict_interval=True,
                        use_exchange_fallback=allow_exchange_fallback,
                    )
                except Exception:
                    live_qty = 0.0
                if live_qty > qty_tol_indicator and allow_exchange_fallback:
                    try:
                        desired_ps_check = None
                        if self.binance.get_futures_dual_side():
                            desired_ps_check = "LONG" if side_value == "BUY" else "SHORT"
                        exch_qty = max(
                            0.0,
                            float(
                                self._current_futures_position_qty(
                                    cw["symbol"], side_value, desired_ps_check
                                )
                                or 0.0
                            ),
                        )
                    except Exception:
                        exch_qty = 0.0
                    tol_live = max(1e-9, exch_qty * 1e-6)
                    if exch_qty <= tol_live:
                        try:
                            self._purge_indicator_tracking(
                                cw["symbol"], interval_current, indicator_key, side_value
                            )
                        except Exception:
                            pass
                        live_qty = 0.0
                if live_qty > qty_tol_indicator:
                    continue
                try:
                    flip_qty_val = float(req.get("qty") or 0.0)
                except Exception:
                    flip_qty_val = 0.0
                indicator_order_requests.append(
                    {
                        "side": side_value,
                        "labels": [indicator_key],
                        "signature": (indicator_key,),
                        "indicator_key": indicator_key,
                        "flip_from": req.get("flip_from"),
                        "flip_qty": flip_qty_val,
                        "flip_qty_target": flip_qty_val,
                        "trigger_desc": f"{indicator_key.upper()} flip-on-close -> {side_value}",
                        "trigger_actions": {indicator_key: side_value.lower()},
                    }
                )
        thresholds = []
        try:
            if cw['indicators']['ma']['enabled'] and 'ma' in ind and not ind['ma'].isnull().all(): 
                thresholds.append(f"MA={float(ind['ma'].iloc[-1]):.8f}")
        except Exception: 
            pass

        ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{ts}", f"{cw['symbol']}@{cw['interval']}",
                 f"Price={last_price:.8f}" if last_price is not None else "Price=None",
                 f"Signal={signal if signal else 'None'}"]
        if trigger_price is not None: parts.append(f"TriggerPrice={trigger_price:.8f}")
        if thresholds: parts.append("Thresholds:" + ",".join(thresholds))
        parts.append("Details:" + trigger_desc)
        self.log(" | ".join(parts))

        trigger_segments = [
            segment.strip()
            for segment in str(trigger_desc or "").split("|")
            if str(segment).strip()
        ]
        orders_to_execute, positions_cache, stop_requested = self._prepare_signal_orders(
            cw=cw,
            indicator_order_requests=indicator_order_requests,
            signal=signal,
            signal_timestamp=signal_timestamp,
            trigger_sources=trigger_sources,
            trigger_desc=trigger_desc,
            trigger_actions=trigger_actions,
            trigger_segments=trigger_segments,
            dual_side=dual_side,
            positions_cache=positions_cache,
            load_positions_cache=_load_positions_cache,
        )
        if stop_requested:
            return

        order_batch_total = len(orders_to_execute)
        order_batch_state = {"counter": 0, "total": order_batch_total}
        positions_cache_holder = {"value": positions_cache}

        for order in orders_to_execute:
            order_ts = order.get("timestamp")
            ts_float = None
            try:
                if order_ts is not None:
                    ts_float = float(order_ts)
            except Exception:
                ts_float = None
            self._execute_signal_order(
                cw=cw,
                order_side=order.get("side"),
                indicator_labels=list(order.get("labels") or []),
                order_signature=tuple(order.get("signature") or ()),
                origin_timestamp=ts_float,
                flip_from_side=order.get("flip_from"),
                flip_qty=order.get("flip_qty"),
                flip_qty_target=order.get("flip_qty_target"),
                order_trigger_desc=order.get("trigger_desc"),
                order_trigger_actions=order.get("trigger_actions"),
                trigger_desc=trigger_desc,
                trigger_sources=trigger_sources,
                last_price=last_price,
                current_bar_marker=current_bar_marker,
                positions_cache_holder=positions_cache_holder,
                order_batch_state=order_batch_state,
            )


strategy_trade_book.bind_strategy_trade_book(
    StrategyEngine,
    canonical_indicator_fn=_canonical_indicator_token,
)
strategy_indicator_guard.bind_strategy_indicator_guard(
    StrategyEngine,
    coerce_bool_fn=coerce_bool,
)
strategy_runtime_support.bind_strategy_runtime_support(StrategyEngine)
strategy_indicator_compute.bind_strategy_indicator_compute(StrategyEngine)
strategy_signal_generation.bind_strategy_signal_generation(StrategyEngine)
strategy_signal_orders_runtime.bind_strategy_signal_orders_runtime(
    StrategyEngine,
    interval_to_seconds_fn=_interval_to_seconds,
)
strategy_indicator_tracking.bind_strategy_indicator_tracking(StrategyEngine)
strategy_position_state.bind_strategy_position_state(StrategyEngine)
strategy_position_close_runtime.bind_strategy_position_close_runtime(StrategyEngine)
strategy_position_flip_runtime.bind_strategy_position_flip_runtime(StrategyEngine)
strategy_runtime.bind_strategy_runtime(StrategyEngine)
