import os
import copy

STOP_LOSS_MODE_ORDER = ["usdt", "percent", "both"]
STOP_LOSS_SCOPE_OPTIONS = ["per_trade", "cumulative", "entire_account"]
STOP_LOSS_DEFAULT = {
    "enabled": False,
    "mode": "usdt",
    "usdt": 0.0,
    "percent": 0.0,
    "scope": "per_trade",
}

MDD_LOGIC_OPTIONS = ["per_trade", "cumulative", "entire_account"]
MDD_LOGIC_DEFAULT = MDD_LOGIC_OPTIONS[0]

BACKTEST_TEMPLATE_DEFAULT = {"enabled": False, "name": None}


DEFAULT_CONFIG = {
    "api_key": os.getenv("BINANCE_API_KEY", ""),
    "api_secret": os.getenv("BINANCE_API_SECRET", ""),
    "mode": "Live",              # "Live" or "Demo/Testnet"
    "account_type": "Futures",   # "Spot" or "Futures"
    "margin_mode": "Isolated",   # For Futures: "Cross" or "Isolated"
    "symbols": ["BTCUSDT"],
    "intervals": ["1m"],
    "lookback": 200,
    "leverage": 20,
    "tif": "GTC",
    "gtd_minutes": 30,           # Only used when tif == 'GTD'
    "position_mode": "Hedge",    # "One-way" or "Hedge"
    "assets_mode": "Single-Asset",
    "account_mode": "Classic Trading",
    "lead_trader_enabled": False,
    "lead_trader_profile": None,
    "loop_interval_override": "1m",
    "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
    "code_language": "Python (PyQt)",
    "selected_exchange": "Binance",
    "selected_forex_broker": None,
    "indicator_flip_cooldown_bars": 1,
    "indicator_flip_cooldown_seconds": 0.0,
    "indicator_use_live_values": True,
    "indicator_min_position_hold_seconds": 0.0,
    "indicator_min_position_hold_bars": 1,
    # Prevent closing an indicator leg unless an explicit opposite signal/flip is present.
    "require_indicator_flip_signal": True,
    # Extra safety: skip indicator closes if no matching opposite signature is provided.
    "strict_indicator_flip_enforcement": True,
    # Blocks immediate re-entry on the same symbol/interval/side after a close to prevent ping-pong loops.
    "indicator_reentry_cooldown_seconds": 0.0,
    "indicator_reentry_cooldown_bars": 1,
    # Require the indicator signal to reset (leave its trigger zone) before re-entering the same side.
    "indicator_reentry_requires_signal_reset": True,
    # When True, flip to the opposite side after a full indicator close (always-in-market).
    "auto_flip_on_close": True,
    # When True, close paths may bypass the hold guard; keep False to prevent instant churn.
    "allow_close_ignoring_hold": False,
    # When False, a close triggered by one indicator will not flatten trades opened by multi-indicator signals.
    "allow_multi_indicator_close": False,
    # When False, an indicator close without an explicit opposite signal/signature is skipped.
    "allow_indicator_close_without_signal": False,
    "indicator_flip_confirmation_bars": 1,
    "indicator_source": "Binance futures",  # Binance spot | Binance futures | TradingView | Bybit
    "close_on_exit": False,
    "positions_missing_threshold": 2,
    "positions_missing_autoclose": True,
    "positions_missing_grace_seconds": 30,
    # Allow stacking long/short legs in hedge mode; per-indicator/interval closes will still target only
    # the matching leg when a counter-signal arrives.
    "allow_opposite_positions": True,
    "hedge_preserve_opposites": False,
    "indicators": {
        "ma":        {"enabled": False, "length": 20, "type": "SMA", "buy_value": None, "sell_value": None},
        "donchian":  {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        "psar":      {"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
        "bb":        {"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
        "rsi":       {"enabled": True,  "length": 14, "buy_value": None, "sell_value": None},
        "volume":    {"enabled": False, "buy_value": None, "sell_value": None},
        "stoch_rsi": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
        "willr":     {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        "macd":      {"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
        "uo":        {"enabled": False, "short": 7, "medium": 14, "long": 28, "buy_value": None, "sell_value": None},
        "adx":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        "dmi":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
        "supertrend": {"enabled": False, "atr_period": 10, "multiplier": 3.0, "buy_value": None, "sell_value": None},
        "ema":       {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
        "stochastic": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
    },
    "backtest": {
        "symbols": ["BTCUSDT"],
        "intervals": ["1h"],
        "capital": 1000.0,
        "logic": "AND",
        "symbol_source": "Futures",
        "start_date": None,
        "end_date": None,
        "position_pct": 2.0,
        "side": "BOTH",
        "margin_mode": "Isolated",
        "position_mode": "Hedge",
        "assets_mode": "Single-Asset",
        "account_mode": "Classic Trading",
        "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
        "leverage": 20,
        "mdd_logic": MDD_LOGIC_DEFAULT,
        "scan_top_n": 200,
        "scan_mdd_limit": 10.0,
        "scan_auto_apply": True,
        "template": copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT),
        "indicators": {},
        "stop_loss": copy.deepcopy(STOP_LOSS_DEFAULT),
    },
    "runtime_symbol_interval_pairs": [],
    "backtest_symbol_interval_pairs": [],
    "side": "BOTH",              # "BUY", "SELL", or "BOTH"
    "position_pct": 2.0,         # % of USDT to allocate (Futures: notional before leverage)
    "order_type": "MARKET",
    "max_auto_bump_percent": 5.0,
    "auto_bump_percent_multiplier": 10.0,
    "stop_loss": copy.deepcopy(STOP_LOSS_DEFAULT),
}

# Central registry of available indicators and their default params (all disabled by default)
AVAILABLE_INDICATORS = {
    "ma":        {"enabled": False, "length": 20, "type": "SMA", "buy_value": None, "sell_value": None},
    "donchian":  {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
    "psar":      {"enabled": False, "af": 0.02, "max_af": 0.2, "buy_value": None, "sell_value": None},
    "bb":        {"enabled": False, "length": 20, "std": 2, "buy_value": None, "sell_value": None},
    "rsi":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "volume":    {"enabled": False, "buy_value": None, "sell_value": None},
    "stoch_rsi": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
    "willr":     {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "macd":      {"enabled": False, "fast": 12, "slow": 26, "signal": 9, "buy_value": None, "sell_value": None},
    "uo":        {"enabled": False, "short": 7, "medium": 14, "long": 28, "buy_value": None, "sell_value": None},
    "adx":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "dmi":       {"enabled": False, "length": 14, "buy_value": None, "sell_value": None},
    "supertrend": {"enabled": False, "atr_period": 10, "multiplier": 3.0, "buy_value": None, "sell_value": None},
    "ema":       {"enabled": False, "length": 20, "buy_value": None, "sell_value": None},
    "stochastic": {"enabled": False, "length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": None, "sell_value": None},
}

INDICATOR_DISPLAY_NAMES = {
    'ma': 'Moving Average (MA)',
    'donchian': 'Donchian Channels (DC)',
    'psar': 'Parabolic SAR (PSAR)',
    'bb': 'Bollinger Bands (BB)',
    'rsi': 'Relative Strength Index (RSI)',
    'volume': 'Volume',
    'stoch_rsi': 'Stochastic RSI (SRSI)',
    'willr': 'Williams %R',
    'macd': 'Moving Average Convergence/Divergence (MACD)',
    'uo': 'Ultimate Oscillator (UO)',
    'adx': 'Average Directional Index (ADX)',
    'dmi': 'Directional Movement Index (DMI)',
    'supertrend': 'SuperTrend (ST)',
    'ema': 'Exponential Moving Average (EMA)',
    'stochastic': 'Stochastic Oscillator',
}

DEFAULT_CONFIG["backtest"]["indicators"] = copy.deepcopy(DEFAULT_CONFIG["indicators"])
if "rsi" in DEFAULT_CONFIG["backtest"]["indicators"]:
    DEFAULT_CONFIG["backtest"]["indicators"]["rsi"].update({"enabled": True, "buy_value": 30, "sell_value": 70})

def normalize_stop_loss_dict(value):
    data = copy.deepcopy(STOP_LOSS_DEFAULT)
    if isinstance(value, dict):
        for key in ("enabled", "mode", "usdt", "percent", "scope"):
            if key in value:
                data[key] = value[key]
    data["enabled"] = bool(data.get("enabled", False))
    mode = str(data.get("mode") or "usdt").lower()
    if mode not in STOP_LOSS_MODE_ORDER:
        mode = "usdt"
    data["mode"] = mode
    try:
        data["usdt"] = max(0.0, float(data.get("usdt", 0.0) or 0.0))
    except Exception:
        data["usdt"] = 0.0
    try:
        data["percent"] = max(0.0, float(data.get("percent", 0.0) or 0.0))
    except Exception:
        data["percent"] = 0.0
    scope = str(data.get("scope") or "per_trade").lower()
    if scope not in STOP_LOSS_SCOPE_OPTIONS:
        scope = STOP_LOSS_SCOPE_OPTIONS[0]
    data["scope"] = scope
    return data


def coerce_bool(value, default=False):
    """
    Normalize loose user-provided values (bools/strings/ints) into a strict bool.

    We frequently persist settings as JSON, so this helper tolerates values like
    "false", "0", 0, None, etc. and falls back to the provided default.
    """
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return bool(default)
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        if text in {"none", "null"}:
            return bool(default)
        return bool(default)
    try:
        return bool(int(value))
    except Exception:
        return bool(value)
