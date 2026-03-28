
import time, copy, math, threading, os, sys
from collections.abc import Iterable
from pathlib import Path

if __package__ in (None, ""):
    _APP_DIR = Path(__file__).resolve().parents[2]
    if str(_APP_DIR) not in sys.path:
        sys.path.insert(0, str(_APP_DIR))

import pandas as pd
try:
    from ...config import (
        STOP_LOSS_MODE_ORDER,
        STOP_LOSS_SCOPE_OPTIONS,
        normalize_stop_loss_dict,
        INDICATOR_DISPLAY_NAMES,
        coerce_bool,
    )
    from ...integrations.exchanges.binance import normalize_margin_ratio
    from ..indicators import (
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
    from ...preamble import PANDAS_TA_AVAILABLE, PANDAS_VERSION, PANDAS_TA_VERSION
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
    from .orders import strategy_signal_orders_runtime
    from .positions import (
        strategy_indicator_guard,
        strategy_position_close_runtime,
        strategy_position_flip_runtime,
        strategy_position_state,
        strategy_trade_book,
    )
    from .runtime import (
        strategy_cycle_runtime,
        strategy_indicator_compute,
        strategy_indicator_tracking,
        strategy_runtime,
        strategy_runtime_support,
        strategy_signal_generation,
    )
except ImportError:  # pragma: no cover - standalone execution fallback
    from core.strategy.orders import strategy_signal_orders_runtime
    from core.strategy.positions import (
        strategy_indicator_guard,
        strategy_position_close_runtime,
        strategy_position_flip_runtime,
        strategy_position_state,
        strategy_trade_book,
    )
    from core.strategy.runtime import (
        strategy_cycle_runtime,
        strategy_indicator_compute,
        strategy_indicator_tracking,
        strategy_runtime,
        strategy_runtime_support,
        strategy_signal_generation,
    )

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
        return strategy_cycle_runtime.run_once(self)


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
    canonical_indicator_token_fn=_canonical_indicator_token,
)
strategy_indicator_tracking.bind_strategy_indicator_tracking(StrategyEngine)
strategy_position_state.bind_strategy_position_state(StrategyEngine)
strategy_position_close_runtime.bind_strategy_position_close_runtime(StrategyEngine)
strategy_position_flip_runtime.bind_strategy_position_flip_runtime(StrategyEngine)
strategy_runtime.bind_strategy_runtime(StrategyEngine)
