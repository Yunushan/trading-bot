from __future__ import annotations

import os
from pathlib import Path


BINANCE_SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

BINANCE_INTERVAL_LOWER = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
}

BACKTEST_INTERVAL_ORDER = [
    "1m", "3m", "5m", "10m", "15m", "20m", "30m",
    "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h",
    "1d", "2d", "3d", "4d", "5d", "6d",
    "1w", "2w", "3w",
    "1month", "2months", "3months", "6months",
    "1mo", "2mo", "3mo", "6mo",
    "1y", "2y",
]

TRADINGVIEW_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "10m": "10",
    "15m": "15",
    "20m": "20",
    "30m": "30",
    "45m": "45",
    "1h": "60",
    "2h": "120",
    "3h": "180",
    "4h": "240",
    "5h": "300",
    "6h": "360",
    "7h": "420",
    "8h": "480",
    "9h": "540",
    "10h": "600",
    "11h": "660",
    "12h": "720",
    "1d": "1D",
    "2d": "2D",
    "3d": "3D",
    "4d": "4D",
    "5d": "5D",
    "6d": "6D",
    "1w": "1W",
    "2w": "2W",
    "3w": "3W",
    "1mo": "1M",
    "2mo": "2M",
    "3mo": "3M",
    "6mo": "6M",
    "1month": "1M",
    "2months": "2M",
    "3months": "3M",
    "6months": "6M",
    "1y": "12M",
    "2y": "24M",
}

STOP_LOSS_MODE_LABELS = {
    "usdt": "USDT Based Stop Loss",
    "percent": "Percentage Based Stop Loss",
    "both": "Both Stop Loss (USDT & Percentage)",
}

STOP_LOSS_SCOPE_LABELS = {
    "per_trade": "Per Trade Stop Loss",
    "cumulative": "Cumulative Stop Loss",
    "entire_account": "Entire Account Stop Loss",
}

DASHBOARD_LOOP_CHOICES = [
    ("30 seconds", "30s"),
    ("45 seconds", "45s"),
    ("1 minute", "1m"),
    ("2 minutes", "2m"),
    ("3 minutes", "3m"),
    ("5 minutes", "5m"),
    ("10 minutes", "10m"),
    ("30 minutes", "30m"),
    ("1 hour", "1h"),
    ("2 hours", "2h"),
]

LEAD_TRADER_OPTIONS = [
    ("Futures Public Lead Trader", "futures_public"),
    ("Futures Private Lead Trader", "futures_private"),
    ("Spot Public Lead Trader", "spot_public"),
    ("Spot Private Lead Trader", "spot_private"),
]

MDD_LOGIC_LABELS = {
    "per_trade": "Per Trade MDD",
    "cumulative": "Cumulative MDD",
    "entire_account": "Entire Account MDD",
}

FUTURES_CONNECTOR_KEYS = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-connector",
    "ccxt",
    "python-binance",
}

SPOT_CONNECTOR_KEYS = {
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
}

CHART_INTERVAL_OPTIONS = list(BACKTEST_INTERVAL_ORDER)
CHART_MARKET_OPTIONS = ["Futures", "Spot"]
ACCOUNT_MODE_OPTIONS = ["Classic Trading", "Portfolio Margin"]
DEFAULT_CHART_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
]
SIDE_LABELS = {
    "BUY": "Buy (Long)",
    "SELL": "Sell (Short)",
    "BOTH": "Both (Long/Short)",
}

MAX_CLOSED_HISTORY = 200
APP_STATE_PATH = Path.home() / ".trading_bot_state.json"
LEGACY_APP_STATE_PATH = Path.home() / ".binance_trading_bot_state.json"
TRADINGVIEW_SYMBOL_PREFIX = "BINANCE:"
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17
WAITING_POSITION_LATE_THRESHOLD = 45.0
DBG_BACKTEST_DASHBOARD = True
DBG_BACKTEST_RUN = True


def _connector_options() -> list[tuple[str, str]]:
    return [
        ("Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)", "binance-sdk-derivatives-trading-usds-futures"),
        ("Binance SDK Derivatives Trading COIN-M Futures", "binance-sdk-derivatives-trading-coin-futures"),
        ("Binance SDK Spot (Official Recommended)", "binance-sdk-spot"),
        ("Binance Connector Python", "binance-connector"),
        ("CCXT (Unified)", "ccxt"),
        ("python-binance (Community)", "python-binance"),
    ]


def _env_flag_enabled(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_symbol_fetch_top_n() -> int:
    try:
        value = int(os.environ.get("BOT_SYMBOL_FETCH_TOP_N") or 200)
    except Exception:
        value = 200
    return max(50, min(value, 5000))
