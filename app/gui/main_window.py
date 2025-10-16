from __future__ import annotations

import copy
import json
import re
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
try:
    from PyQt6.QtCharts import (
        QChart,
        QChartView,
        QCandlestickSeries,
        QCandlestickSet,
        QDateTimeAxis,
        QValueAxis,
    )
    QT_CHARTS_AVAILABLE = True
except Exception:
    QT_CHARTS_AVAILABLE = False
    QChart = QChartView = QCandlestickSeries = QCandlestickSet = QDateTimeAxis = QValueAxis = None
from PyQt6.QtCore import pyqtSignal

ENABLE_CHART_TAB = True

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.config import DEFAULT_CONFIG, INDICATOR_DISPLAY_NAMES
from app.binance_wrapper import BinanceWrapper, normalize_margin_ratio
from app.backtester import BacktestEngine, BacktestRequest, IndicatorDefinition
from app.strategy import StrategyEngine
from app.workers import StopWorker, StartWorker, CallWorker
from app.position_guard import IntervalPositionGuard
from app.gui.param_dialog import ParamDialog
try:
    from app.gui.tradingview_widget import TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE
except Exception:
    TradingViewWidget = None  # type: ignore[assignment]
    TRADINGVIEW_EMBED_AVAILABLE = False

BINANCE_SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}
BINANCE_INTERVAL_LOWER = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"}

BACKTEST_INTERVAL_ORDER = [
    "1m", "3m", "5m", "10m", "15m", "20m", "30m",
    "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h",
    "1d", "2d", "3d", "4d", "5d", "6d",
    "1w", "2w", "3w",
    "1month", "2months", "3months", "6months",
    "1year", "2year",
    "1mo", "2mo", "3mo", "6mo",
    "1y", "2y"
]

MAX_CLOSED_HISTORY = 200

APP_STATE_PATH = Path.home() / ".binance_trading_bot_state.json"

def _load_app_state_file(path: Path) -> dict:
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def _save_app_state_file(path: Path, data: dict) -> None:
    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass

TRADINGVIEW_SYMBOL_PREFIX = "BINANCE:"
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
    "1year": "12M",
    "2year": "24M",
}

CHART_INTERVAL_OPTIONS = BACKTEST_INTERVAL_ORDER[:]

CHART_MARKET_OPTIONS = ["Futures", "Spot"]

DEFAULT_CHART_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
]

SIDE_LABELS = {
    "BUY": "Buy (Long)",
    "SELL": "Sell (Short)",
    "BOTH": "Both (Long/Short)",
}
SIDE_LABEL_LOOKUP = {label.lower(): code for code, label in SIDE_LABELS.items()}

class SimpleCandlestickWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._candles: list[dict] = []
        self._message: str | None = "Charts unavailable."
        self._message_color: str = "#f75467"
        self.setMinimumHeight(320)

    def set_message(self, message: str, color: str = "#d1d4dc") -> None:
        self._candles = []
        self._message = message
        self._message_color = color
        self.update()

    def set_candles(self, candles: list[dict]) -> None:
        self._candles = candles or []
        if not self._candles:
            self._message = "No data available."
            self._message_color = "#f75467"
        else:
            self._message = None
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor("#0b0e11"))

        if not self._candles:
            if self._message:
                painter.setPen(QtGui.QColor(self._message_color))
                painter.drawText(
                    rect,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    self._message,
                )
            return

        highs = [float(c.get("high", 0.0)) for c in self._candles]
        lows = [float(c.get("low", 0.0)) for c in self._candles]
        if not highs or not lows:
            return

        max_high = max(highs)
        min_low = min(lows)
        if max_high <= min_low:
            max_high = min_low + 1.0

        margin_x = max(int(rect.width() * 0.05), 40)
        margin_y = max(int(rect.height() * 0.1), 30)
        chart_rect = rect.adjusted(margin_x, margin_y, -margin_x, -margin_y)
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return

        painter.setPen(QtGui.QColor("#1f2326"))
        painter.drawRect(chart_rect)

        count = len(self._candles)
        spacing = chart_rect.width() / max(count, 1)
        body_width = max(4.0, spacing * 0.6)

        def price_to_y(price: float) -> float:
            ratio = (price - min_low) / (max_high - min_low)
            return chart_rect.bottom() - ratio * chart_rect.height()

        for idx, candle in enumerate(self._candles):
            try:
                open_ = float(candle.get("open", 0.0))
                close = float(candle.get("close", 0.0))
                high = float(candle.get("high", 0.0))
                low = float(candle.get("low", 0.0))
            except Exception:
                continue

            x_center = chart_rect.left() + (idx + 0.5) * spacing
            color = QtGui.QColor("#0ebb7a" if close >= open_ else "#f75467")
            painter.setPen(QtGui.QPen(color, 1.0))

            y_high = price_to_y(high)
            y_low = price_to_y(low)
            painter.drawLine(QtCore.QPointF(x_center, y_high), QtCore.QPointF(x_center, y_low))

            body_top = price_to_y(max(open_, close))
            body_bottom = price_to_y(min(open_, close))
            rect_body = QtCore.QRectF(
                x_center - body_width / 2.0,
                body_top,
                body_width,
                max(1.0, body_bottom - body_top),
            )
            painter.fillRect(rect_body, QtGui.QBrush(color))

        painter.setPen(QtGui.QColor("#3b434a"))
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
            f"High: {max_high:.4f}",
        )
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight,
            f"Low: {min_low:.4f}",
        )

def _format_indicator_list(keys):
    if not keys:
        return "-"
    rendered = []
    for key in keys:
        rendered.append(INDICATOR_DISPLAY_NAMES.get(key, key))
    return ", ".join(rendered) if rendered else "-"


class _NumericItem(QtWidgets.QTableWidgetItem):
    def __init__(self, text: str, value: float = 0.0):
        super().__init__(text)
        try:
            self._numeric = float(value)
        except Exception:
            self._numeric = 0.0
        self.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, _NumericItem):
            return self._numeric < other._numeric
        try:
            return self._numeric < float(other.text().replace('%', '').strip() or 0.0)
        except Exception:
            try:
                return float(self.text().replace('%', '').strip() or 0.0) < float(other.text().replace('%', '').strip() or 0.0)
            except Exception:
                return super().__lt__(other)


def _safe_float(value, default=0.0):
    try:
        if isinstance(value, str):
            value = value.replace('%', '').strip()
            if value == "":
                return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _make_engine_key(symbol: str, interval: str, indicators: list[str] | None) -> str:
    base = f"{symbol}@{interval}"
    if indicators:
        base += "#" + ",".join(indicators)
    return base



class _PositionsWorker(QtCore.QObject):
    positions_ready = QtCore.pyqtSignal(list, str)  # rows, account_type
    error = QtCore.pyqtSignal(str)

    def __init__(self, api_key:str, api_secret:str, mode:str, account_type:str, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._api_secret = api_secret
        self._mode = mode
        self._acct = account_type
        self._symbols = None  # optional filter set
        self._busy = False
        self._timer = None
        self._wrapper = None
        self._last_err_ts = 0
        self._enabled = True
        self._interval_ms = 5000

    @QtCore.pyqtSlot(int)
    def start_with_interval(self, interval_ms: int):
        try:
            self._enabled = True
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._tick)
            self._timer.start()
            # immediate tick
            try:
                self._tick()
            except Exception:
                pass
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def stop_timer(self):
        try:
            self._enabled = False
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = None
        except Exception:
            pass

    @QtCore.pyqtSlot(int)
    def set_interval(self, interval_ms: int):
        try:
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                self._timer.setInterval(self._interval_ms)
        except Exception:
            pass

    def configure(self, api_key=None, api_secret=None, mode=None, account_type=None, symbols=None):
        if api_key is not None: self._api_key = api_key
        if api_secret is not None: self._api_secret = api_secret
        if mode is not None: self._mode = mode
        if account_type is not None: self._acct = account_type
        self._symbols = set(symbols) if symbols else None
        # force wrapper rebuild on next tick
        self._wrapper = None

    def _ensure_wrapper(self):
        if self._wrapper is None:
            try:
                self._wrapper = BinanceWrapper(
                    self._api_key or "",
                    self._api_secret or "",
                    mode=self._mode or "Live",
                    account_type=self._acct or "Futures",
                )
            except Exception:
                self._wrapper = None

    def _compute_futures_metrics(self, p:dict):
        try:
            amt = float(p.get('positionAmt') or 0.0)
            mark = float(p.get('markPrice') or 0.0)
            lev = int(float(p.get('leverage') or 0.0)) or 0
            pnl = float(p.get('unRealizedProfit') or 0.0)
            notional = float(p.get('notional') or 0.0)
            if notional == 0.0 and mark and amt:
                notional = abs(amt) * mark
            size_usdt = abs(notional)
            iso_wallet = float(p.get('isolatedWallet') or 0.0)
            margin = iso_wallet
            if margin <= 0.0:
                margin = float(p.get('initialMargin') or 0.0)
            if margin <= 0.0 and lev > 0:
                margin = size_usdt / lev
            roi = (pnl / margin * 100.0) if margin > 0 else 0.0
            pnl_roi_str = f"{pnl:+.2f} USDT ({roi:+.2f}%)"

            # Prefer Binance-provided marginRatio when available, otherwise approximate.
            ratio = normalize_margin_ratio(p.get('marginRatio'))
            if ratio <= 0.0:
                # Margin Ratio (isolated) ~= (maintMargin + unrealizedLoss) / isolatedWallet
                try:
                    mm = float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0)
                except Exception:
                    mm = 0.0
                unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                margin_balance = iso_wallet + (pnl if pnl > 0 else 0.0)
                denom = margin_balance if margin_balance > 0.0 else float(p.get('isolatedWallet') or 0.0)
                if denom > 0.0:
                    ratio = ((mm + unrealized_loss) / denom) * 100.0
            return size_usdt, margin, pnl_roi_str, ratio
        except Exception:
            return 0.0, 0.0, "-", 0.0


    def _tick(self):
        if not self._enabled:
            return
        if self._busy:
            return
        self._busy = True
        try:
            acct = str(self._acct or "FUTURES").upper()
            self._ensure_wrapper()
            if self._wrapper is None:
                return
            rows = []
            if acct == "FUTURES":
                try:
                    positions = self._wrapper.list_open_futures_positions() or []
                except Exception as e:
                    import time
                    if time.time() - self._last_err_ts > 5:
                        self._last_err_ts = time.time()
                        self.error.emit(f"Positions error: {e}")
                    return
                for p in positions:
                    try:
                        sym = str(p.get('symbol'))
                        if self._symbols and sym not in self._symbols:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        mark = float(p.get('markPrice') or 0.0)
                        value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        size_usdt, margin_usdt, pnl_roi, margin_ratio = self._compute_futures_metrics(p)
                        rows.append({
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'value': value,
                            'size_usdt': size_usdt,
                            'margin_usdt': margin_usdt,
                            'margin_ratio': margin_ratio,
                            'pnl_roi': pnl_roi,
                            'side_key': side_key,
                        })
                    except Exception:
                        pass
            else:
                # SPOT
                try:
                    balances = self._wrapper.get_balances() or []
                except Exception as e:
                    self.error.emit(f"Spot balances error: {e}")
                    return
                base = "USDT"
                for b in balances:
                    try:
                        asset = b.get("asset")
                        free = float(b.get("free") or 0.0)
                        locked = float(b.get("locked") or 0.0)
                        total = free + locked
                        if asset in (base, None) or total <= 0:
                            continue
                        sym = f"{asset}{base}"
                        if self._symbols and sym not in self._symbols:
                            continue
                        last = float(self._wrapper.get_last_price(sym) or 0.0)
                        value = total * last
                        rows.append({
                            'symbol': sym,
                            'qty': total,
                            'mark': last,
                            'value': value,
                            'size_usdt': 0.0,
                            'margin_usdt': 0.0,
                            'pnl_roi': "-",
                            'side_key': 'SPOT',
                        })
                    except Exception:
                        pass
            self.positions_ready.emit(rows, acct)
        finally:
            self._busy = False


class _BacktestWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(dict, object)

    def __init__(self, engine: BacktestEngine, request: BacktestRequest, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.request = request
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            result = self.engine.run(self.request, progress=self.progress.emit,
                                     should_stop=lambda: bool(self._stop_requested))
            self.finished.emit(result, None)
        except Exception as exc:
            self.finished.emit({}, exc)
from ..position_guard import IntervalPositionGuard
from .param_dialog import ParamDialog

class MainWindow(QtWidgets.QWidget):
    log_signal = pyqtSignal(str)
    trade_signal = pyqtSignal(dict)

    # thread-safe control signals for positions worker
    req_pos_start = QtCore.pyqtSignal(int)
    req_pos_stop = QtCore.pyqtSignal()
    req_pos_set_interval = QtCore.pyqtSignal(int)

    LIGHT_THEME = """
    QWidget { background-color: #FFFFFF; color: #000000; font-family: Arial; }
    QGroupBox { border: 1px solid #C0C0C0; margin-top: 6px; }
    QPushButton { background-color: #F0F0F0; border: 1px solid #B0B0B0; padding: 6px; }
    QPushButton:disabled { background-color: #D5D5D5; border: 1px solid #B8B8B8; color: #7A7A7A; }
    QTextEdit { background-color: #FFFFFF; color: #000000; }
    QLineEdit { background-color: #FFFFFF; color: #000000; }
    QLineEdit:disabled,
    QComboBox:disabled,
    QListWidget:disabled,
    QSpinBox:disabled,
    QDoubleSpinBox:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled { background-color: #E6E6E6; color: #7A7A7A; }
    QCheckBox:disabled,
    QRadioButton:disabled { color: #7A7A7A; }
    QComboBox { background-color: #FFFFFF; color: #000000; }
    QListWidget { background-color: #FFFFFF; color: #000000; }
    QLabel { color: #000000; }
    QLabel:disabled { color: #7A7A7A; }
    """

    DARK_THEME = """
    QWidget { background-color: #121212; color: #E0E0E0; font-family: Arial; }
    QGroupBox { border: 1px solid #333; margin-top: 6px; }
    QPushButton { background-color: #1E1E1E; border: 1px solid #333; padding: 6px; }
    QPushButton:disabled { background-color: #2A2A2A; border: 1px solid #444; color: #808080; }
    QTextEdit { background-color: #0E0E0E; color: #E0E0E0; }
    QLineEdit { background-color: #1E1E1E; color: #E0E0E0; }
    QLineEdit:disabled,
    QComboBox:disabled,
    QListWidget:disabled,
    QSpinBox:disabled,
    QDoubleSpinBox:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled { background-color: #1A1A1A; color: #7E7E7E; }
    QCheckBox:disabled,
    QRadioButton:disabled { color: #7E7E7E; }
    QComboBox { background-color: #1E1E1E; color: #E0E0E0; }
    QListWidget { background-color: #0E0E0E; color: #E0E0E0; }
    QLabel { color: #E0E0E0; }
    QLabel:disabled { color: #6F6F6F; }
    """

    def __init__(self):
        super().__init__()
        self._state_path = APP_STATE_PATH
        self._app_state = _load_app_state_file(self._state_path)
        self._previous_session_unclosed = bool(self._app_state.get("session_active", False))
        self._session_marker_active = False
        self._auto_close_on_restart_triggered = False
        self.guard = IntervalPositionGuard(stale_ttl_sec=180)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        state_close_pref = bool(self._app_state.get("close_on_exit", self.config.get("close_on_exit", False)))
        self.config.setdefault('theme', 'Dark')
        self.config['close_on_exit'] = state_close_pref
        self.config.setdefault('close_on_exit', state_close_pref)
        self.strategy_threads = {}
        self.shared_binance = None
        self.stop_worker = None
        self.indicator_widgets = {}
        self.traded_symbols = set()
        self._chart_pending_initial_load = True
        self._chart_needs_render = True
        self.config.setdefault("chart", {})
        if not isinstance(self.config.get("chart"), dict):
            self.config["chart"] = {}
        self.chart_config = self.config["chart"]
        try:
            self.chart_config.pop("follow_dashboard", None)
        except Exception:
            pass
        self.chart_config.setdefault("auto_follow", True)
        self.chart_auto_follow = bool(self.chart_config.get("auto_follow", True))
        self._chart_manual_override = False
        self._chart_updating = False
        self.chart_enabled = ENABLE_CHART_TAB
        self._chart_worker = None
        self._chart_theme_signal_installed = False
        default_symbols = self.config.get("symbols") or ["BTCUSDT"]
        default_intervals = self.config.get("intervals") or ["1h"]
        self.chart_symbol_cache = {opt: [] for opt in CHART_MARKET_OPTIONS}
        self._chart_symbol_alias_map = {}
        self._chart_symbol_loading = set()
        default_market = self.config.get("account_type", "Futures")
        if not default_market or default_market not in CHART_MARKET_OPTIONS:
            default_market = "Futures"
        self.chart_config.setdefault("market", default_market)
        initial_symbols_norm = [str(sym).strip().upper() for sym in (default_symbols or []) if str(sym).strip()]
        if initial_symbols_norm:
            dedup = []
            seen = set()
            for sym in initial_symbols_norm:
                if sym not in seen:
                    seen.add(sym)
                    dedup.append(sym)
        self.chart_symbol_cache["Futures"] = dedup
        default_symbol = (default_symbols[0] if default_symbols else "BTCUSDT")
        if default_market == "Futures":
            default_symbol = self._futures_display_symbol(default_symbol)
        self.chart_config.setdefault("symbol", default_symbol)
        self.chart_config.setdefault("interval", (default_intervals[0] if default_intervals else "1h"))
        try:
            if self._normalize_chart_market(self.chart_config.get("market")) == "Futures":
                current_cfg_symbol = str(self.chart_config.get("symbol") or "").strip()
                if current_cfg_symbol and not current_cfg_symbol.endswith(".P"):
                    self.chart_config["symbol"] = self._futures_display_symbol(current_cfg_symbol)
        except Exception:
            pass
        self._indicator_runtime_controls = []
        self._runtime_lock_widgets = []
        self._runtime_active_exemptions = set()
        self.backtest_indicator_widgets = {}
        self.backtest_results = []
        self.backtest_worker = None
        self._backtest_symbol_worker = None
        self.backtest_symbols_all = []
        self._backtest_wrappers = {}
        self.backtest_config = copy.deepcopy(self.config.get("backtest", {}))
        if not self.backtest_config:
            self.backtest_config = copy.deepcopy(DEFAULT_CONFIG.get("backtest", {}))
        else:
            self.backtest_config = copy.deepcopy(self.backtest_config)
        if not self.backtest_config.get("indicators"):
            self.backtest_config["indicators"] = copy.deepcopy(DEFAULT_CONFIG["backtest"]["indicators"])
        default_backtest = DEFAULT_CONFIG.get("backtest", {}) or {}
        self.backtest_config.setdefault("symbol_source", default_backtest.get("symbol_source", "Futures"))
        self.backtest_config.setdefault("capital", float(default_backtest.get("capital", 1000.0)))
        self.backtest_config.setdefault("logic", default_backtest.get("logic", "AND"))
        self.backtest_config.setdefault("start_date", default_backtest.get("start_date"))
        self.backtest_config.setdefault("end_date", default_backtest.get("end_date"))
        self.backtest_config.setdefault("symbols", list(default_backtest.get("symbols", [])))
        self.backtest_config.setdefault("intervals", list(default_backtest.get("intervals", [])))
        self.backtest_config.setdefault("position_pct", float(default_backtest.get("position_pct", 2.0)))
        self.backtest_config.setdefault("side", default_backtest.get("side", "BOTH"))
        self.backtest_config.setdefault("margin_mode", default_backtest.get("margin_mode", "Isolated"))
        self.backtest_config.setdefault("position_mode", default_backtest.get("position_mode", "Hedge"))
        self.backtest_config.setdefault("assets_mode", default_backtest.get("assets_mode", "Single-Asset"))
        self.backtest_config.setdefault("leverage", int(default_backtest.get("leverage", 5)))
        self.backtest_config.setdefault("backtest_symbol_interval_pairs", list(self.config.get("backtest_symbol_interval_pairs", [])))
        self._backtest_futures_widgets = []
        self.config.setdefault("runtime_symbol_interval_pairs", [])
        self.config.setdefault("backtest_symbol_interval_pairs", [])
        self.symbol_interval_table = None
        self.pair_add_btn = None
        self.pair_remove_btn = None
        self.pair_clear_btn = None
        self.backtest_run_btn = None
        self.backtest_stop_btn = None
        self.override_contexts = {}
        self.bot_status_label_tab1 = None
        self.bot_status_label_tab2 = None
        self.bot_status_label_tab3 = None
        self._bot_active = False
        self.init_ui()
        self.log_signal.connect(self._buffer_log)
        self.trade_signal.connect(self._on_trade_signal)
        QtCore.QTimer.singleShot(0, self._handle_post_init_state)

    def _on_close_on_exit_changed(self, state):
        enabled = bool(state)
        self.config['close_on_exit'] = enabled
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['close_on_exit'] = enabled
        if getattr(self, "_session_marker_active", False):
            data['session_active'] = True
        else:
            data['session_active'] = bool(data.get('session_active', False))
        data['updated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass
        try:
            engines = getattr(self, "strategy_engines", {}) or {}
            for eng in engines.values():
                try:
                    if hasattr(eng, "config"):
                        eng.config['close_on_exit'] = enabled
                except Exception:
                    pass
        except Exception:
            pass

    def _mark_session_active(self):
        if getattr(self, "_session_marker_active", False):
            return
        self._session_marker_active = True
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['session_active'] = True
        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
        data['activated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass

    def _mark_session_inactive(self):
        if not getattr(self, "_session_marker_active", False):
            return
        self._session_marker_active = False
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['session_active'] = False
        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
        data['deactivated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass

    def _handle_post_init_state(self):
        try:
            self._mark_session_active()
            if self.config.get('close_on_exit') and getattr(self, "_previous_session_unclosed", False):
                if not getattr(self, "_auto_close_on_restart_triggered", False):
                    self._auto_close_on_restart_triggered = True
                    self._previous_session_unclosed = False
                    self.log("Previous session ended unexpectedly with close-on-exit enabled; triggering emergency close of all positions.")
                    try:
                        api_key_ready = bool(getattr(self, "api_key_edit", None) and self.api_key_edit.text().strip())
                        api_secret_ready = bool(getattr(self, "api_secret_edit", None) and self.api_secret_edit.text().strip())
                        if api_key_ready and api_secret_ready:
                            try:
                                self.stop_strategy_async(close_positions=False, blocking=True)
                            except Exception:
                                pass
                            wrapper = getattr(self, "shared_binance", None)
                            if wrapper is None:
                                wrapper = BinanceWrapper(
                                    self.api_key_edit.text().strip(),
                                    self.api_secret_edit.text().strip(),
                                    mode=self.mode_combo.currentText(),
                                    account_type=self.account_combo.currentText(),
                                    default_leverage=int(self.leverage_spin.value() or 1),
                                    default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
                                )
                                self.shared_binance = wrapper
                            else:
                                wrapper = self.shared_binance
                            try:
                                wrapper.trigger_emergency_close_all(reason="restart_recovery", source="startup")
                            except Exception as exc_inner:
                                self.log(f"Emergency close scheduling error: {exc_inner}")
                        else:
                            self.log("Emergency close skipped: API credentials are missing.")
                    except Exception as exc:
                        try:
                            self.log(f"Emergency close scheduling error: {exc}")
                        except Exception:
                            pass
                    try:
                        data = dict(getattr(self, "_app_state", {}) or {})
                        data['session_active'] = True
                        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
                        data['last_recovery_at'] = datetime.utcnow().isoformat()
                        data['last_recovery_reason'] = 'restart_recovery'
                        _save_app_state_file(self._state_path, data)
                        self._app_state = data
                    except Exception:
                        pass
        except Exception as exc:
            try:
                self.log(f"Post-init state handler error: {exc}")
            except Exception:
                pass

    def _set_runtime_controls_enabled(self, enabled: bool):
        try:
            widgets = getattr(self, "_runtime_lock_widgets", [])
            exemptions = getattr(self, "_runtime_active_exemptions", set())
            for widget in widgets:
                if widget is None:
                    continue
                if enabled:
                    widget.setEnabled(True)
                    continue
                if widget in exemptions:
                    try:
                        widget.setEnabled(True)
                    except Exception:
                        pass
                else:
                    widget.setEnabled(False)
        except Exception:
            pass

    def _override_ctx(self, kind: str) -> dict:
        return getattr(self, "override_contexts", {}).get(kind, {})

    def _register_runtime_active_exemption(self, widget):
        if widget is None:
            return
        try:
            exemptions = getattr(self, "_runtime_active_exemptions", None)
            if isinstance(exemptions, set):
                exemptions.add(widget)
        except Exception:
            pass

    def _override_config_list(self, kind: str) -> list:
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return []
        lst = self.config.setdefault(cfg_key, [])
        if kind == "backtest":
            try:
                self.backtest_config[cfg_key] = list(lst)
            except Exception:
                pass
        return lst

    def _get_selected_indicator_keys(self, kind: str) -> list[str]:
        try:
            if kind == "runtime":
                widgets = getattr(self, "indicator_widgets", {}) or {}
            else:
                widgets = getattr(self, "backtest_indicator_widgets", {}) or {}
            keys: list[str] = []
            for key, control in widgets.items():
                cb = control[0] if isinstance(control, (tuple, list)) and control else None
                if cb and cb.isChecked():
                    keys.append(str(key))
            if keys:
                return keys
        except Exception:
            pass
        try:
            cfg = self.config if kind == "runtime" else self.backtest_config
            indicators_cfg = (cfg or {}).get("indicators", {}) or {}
            return [key for key, params in indicators_cfg.items() if params.get("enabled")]
        except Exception:
            return []

    def _refresh_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        pairs_cfg = self._override_config_list(kind) or []
        table.setRowCount(0)
        seen = set()
        cleaned = []
        for entry in pairs_cfg:
            sym = str((entry or {}).get('symbol') or '').strip().upper()
            iv = str((entry or {}).get('interval') or '').strip()
            if not sym or not iv:
                continue
            indicators_raw = entry.get('indicators')
            if isinstance(indicators_raw, (list, tuple)):
                indicator_values = sorted({str(k).strip() for k in indicators_raw if str(k).strip()})
            else:
                indicator_values = []
            key = (sym, iv, tuple(indicator_values))
            if key in seen:
                continue
            seen.add(key)
            entry_clean = {'symbol': sym, 'interval': iv}
            if indicator_values:
                entry_clean['indicators'] = list(indicator_values)
            cleaned.append(entry_clean)
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(iv))
            try:
                table.item(row, 0).setData(QtCore.Qt.ItemDataRole.UserRole, entry_clean)
            except Exception:
                pass
            if table.columnCount() >= 3:
                table.setItem(row, 2, QtWidgets.QTableWidgetItem(_format_indicator_list(indicator_values)))
        cfg_key = ctx.get("config_key")
        if cfg_key:
            self.config[cfg_key] = cleaned
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = list(cleaned)
                except Exception:
                    pass

    def _add_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        symbol_list = ctx.get("symbol_list")
        interval_list = ctx.get("interval_list")
        if symbol_list is None or interval_list is None:
            return
        try:
            symbols = []
            for i in range(symbol_list.count()):
                item = symbol_list.item(i)
                if item and item.isSelected():
                    symbols.append(item.text().strip().upper())
            intervals = []
            for i in range(interval_list.count()):
                item = interval_list.item(i)
                if item and item.isSelected():
                    intervals.append(item.text().strip())
            if not symbols or not intervals:
                return
            pairs_cfg = self._override_config_list(kind)
            existing_keys = {}
            for entry in pairs_cfg:
                sym_existing = str(entry.get('symbol') or '').strip().upper()
                iv_existing = str(entry.get('interval') or '').strip()
                if not (sym_existing and iv_existing):
                    continue
                indicators_existing = entry.get('indicators')
                if isinstance(indicators_existing, (list, tuple)):
                    indicators_existing = sorted({str(k).strip() for k in indicators_existing if str(k).strip()})
                else:
                    indicators_existing = []
                key = (sym_existing, iv_existing, tuple(indicators_existing))
                existing_keys[key] = entry
            changed = False
            sel_indicators = self._get_selected_indicator_keys(kind)
            indicators_value = sorted({str(k).strip() for k in sel_indicators if str(k).strip()}) if sel_indicators else []
            indicators_tuple = tuple(indicators_value)
            for sym in symbols:
                if not sym:
                    continue
                for iv in intervals:
                    if not iv:
                        continue
                    key = (sym, iv, indicators_tuple)
                    if key in existing_keys:
                        continue
                    new_entry = {'symbol': sym, 'interval': iv}
                    if indicators_value:
                        new_entry['indicators'] = list(indicators_value)
                    pairs_cfg.append(new_entry)
                    existing_keys[key] = new_entry
                    changed = True
            if changed:
                self._refresh_symbol_interval_pairs(kind)
            for widget in (symbol_list, interval_list):
                try:
                    for i in range(widget.count()):
                        item = widget.item(i)
                        if item:
                            item.setSelected(False)
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        try:
            rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()}, reverse=True)
            if not rows:
                return
            pairs_cfg = self._override_config_list(kind)
            updated = []
            remove_set = set()
            for row in rows:
                sym_item = table.item(row, 0)
                iv_item = table.item(row, 1)
                sym = sym_item.text().strip().upper() if sym_item else ''
                iv = iv_item.text().strip() if iv_item else ''
                if not (sym and iv):
                    continue
                indicators_raw = None
                exact_match = True
                try:
                    entry_data = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                except Exception:
                    entry_data = None
                if isinstance(entry_data, dict):
                    indicators_raw = entry_data.get('indicators')
                else:
                    exact_match = False
                if isinstance(indicators_raw, (list, tuple)):
                    indicators_norm = sorted({str(k).strip() for k in indicators_raw if str(k).strip()})
                else:
                    indicators_norm = []
                if exact_match:
                    remove_set.add((sym, iv, tuple(indicators_norm)))
                else:
                    remove_set.add((sym, iv, None))
            for entry in pairs_cfg:
                sym = str(entry.get('symbol') or '').strip().upper()
                iv = str(entry.get('interval') or '').strip()
                indicators_raw = entry.get('indicators')
                if isinstance(indicators_raw, (list, tuple)):
                    indicators_norm = sorted({str(k).strip() for k in indicators_raw if str(k).strip()})
                else:
                    indicators_norm = []
                key = (sym, iv, tuple(indicators_norm))
                if key in remove_set or (sym, iv, None) in remove_set:
                    continue
                new_entry = {'symbol': sym, 'interval': iv}
                if indicators_norm:
                    new_entry['indicators'] = list(indicators_norm)
                updated.append(new_entry)
            cfg_key = ctx.get("config_key")
            if cfg_key:
                self.config[cfg_key] = updated
                if kind == "backtest":
                    try:
                        self.backtest_config[cfg_key] = list(updated)
                    except Exception:
                        pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _clear_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return
        try:
            self.config[cfg_key] = []
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = []
                except Exception:
                    pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _create_override_group(self, kind: str, symbol_list, interval_list) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Symbol / Interval Overrides")
        layout = QtWidgets.QVBoxLayout(group)
        columns = ["Symbol", "Interval"]
        if kind == "runtime":
            columns.append("Indicators")
        table = QtWidgets.QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(180)
        try:
            table.verticalHeader().setDefaultSectionSize(28)
        except Exception:
            pass
        try:
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Selected")
        add_btn.clicked.connect(lambda _, k=kind: self._add_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(lambda _, k=kind: self._remove_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(remove_btn)
        clear_btn = QtWidgets.QPushButton("Clear All")
        clear_btn.clicked.connect(lambda _, k=kind: self._clear_symbol_interval_pairs(k))
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        config_key = "runtime_symbol_interval_pairs" if kind == "runtime" else "backtest_symbol_interval_pairs"
        self.override_contexts[kind] = {
            "table": table,
            "symbol_list": symbol_list,
            "interval_list": interval_list,
            "config_key": config_key,
            "add_btn": add_btn,
            "remove_btn": remove_btn,
            "clear_btn": clear_btn,
        }
        if kind == "runtime":
            self.symbol_interval_table = table
            self.pair_add_btn = add_btn
            self.pair_remove_btn = remove_btn
            self.pair_clear_btn = clear_btn
        lock_widgets = getattr(self, '_runtime_lock_widgets', None)
        if isinstance(lock_widgets, list):
            for widget in (table, add_btn, remove_btn, clear_btn):
                if widget and widget not in lock_widgets:
                    lock_widgets.append(widget)
        if kind == "backtest":
            for btn in (add_btn, remove_btn, clear_btn):
                self._register_runtime_active_exemption(btn)
        self._refresh_symbol_interval_pairs(kind)
        return group

    def _on_indicator_toggled(self, key: str, checked: bool):
        try:
            indicators = self.config.setdefault('indicators', {})
            params = indicators.setdefault(key, {})
            params['enabled'] = bool(checked)
        except Exception:
            pass

    def _update_bot_status(self, active=None):
        try:
            if active is not None:
                self._bot_active = bool(active)
            text = "Bot Status: ON" if getattr(self, '_bot_active', False) else "Bot Status: OFF"
            color = "#3FB950" if self._bot_active else "#F97068"
            for label in (
                getattr(self, 'bot_status_label_tab1', None),
                getattr(self, 'bot_status_label_tab2', None),
                getattr(self, 'bot_status_label_tab3', None),
            ):
                if label is None:
                    continue
                label.setText(text)
                label.setStyleSheet(f"font-weight: bold; color: {color};")
        except Exception:
            pass

    def _has_active_engines(self):
        try:
            engines = getattr(self, 'strategy_engines', {}) or {}
        except Exception:
            return False
        for eng in engines.values():
            try:
                if hasattr(eng, 'is_alive'):
                    if eng.is_alive():
                        return True
                else:
                    thread = getattr(eng, '_thread', None)
                    if thread and getattr(thread, 'is_alive', lambda: False)():
                        return True
            except Exception:
                continue
        return False

    def _sync_runtime_state(self):
        active = self._has_active_engines()
        if active:
            self._set_runtime_controls_enabled(False)
        else:
            self._set_runtime_controls_enabled(True)
        try:
            btn = getattr(self, 'refresh_balance_btn', None)
            if btn is not None:
                btn.setEnabled(True)
        except Exception:
            pass
        try:
            start_btn = getattr(self, 'start_btn', None)
            stop_btn = getattr(self, 'stop_btn', None)
            if start_btn is not None:
                start_btn.setEnabled(not active)
            if stop_btn is not None:
                stop_btn.setEnabled(active)
        except Exception:
            pass
        self._update_bot_status(active)
        return active

    @staticmethod
    def _coerce_qdate(value):
        if isinstance(value, QtCore.QDate):
            return value
        if isinstance(value, datetime):
            return QtCore.QDate(value.year, value.month, value.day)
        if isinstance(value, str):
            # Try common formats
            for fmt in ("yyyy-MM-dd", "yyyy/MM/dd", "dd.MM.yyyy"):
                qd = QtCore.QDate.fromString(value, fmt)
                if qd.isValid():
                    return qd
            try:
                dt = datetime.fromisoformat(value)
                return QtCore.QDate(dt.year, dt.month, dt.day)
            except Exception:
                pass
        return QtCore.QDate.currentDate()

    @staticmethod
    def _coerce_qdatetime(value):
        if isinstance(value, QtCore.QDateTime):
            return value
        if isinstance(value, datetime):
            return QtCore.QDateTime(value)
        if isinstance(value, str):
            from datetime import datetime as _dt
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
                try:
                    dt = _dt.strptime(value, fmt)
                    return QtCore.QDateTime(QtCore.QDate(dt.year, dt.month, dt.day), QtCore.QTime(dt.hour, dt.minute))
                except Exception:
                    continue
            try:
                dt = _dt.fromisoformat(value)
                return QtCore.QDateTime(QtCore.QDate(dt.year, dt.month, dt.day), QtCore.QTime(dt.hour, dt.minute))
            except Exception:
                pass
        current = QtCore.QDateTime.currentDateTime()
        return current

    def _initialize_backtest_ui_defaults(self):
        fetch_triggered = False
        try:
            source = self.backtest_config.get("symbol_source") or "Futures"
            idx = self.backtest_symbol_source_combo.findText(source)
            if idx is not None and idx >= 0 and self.backtest_symbol_source_combo.currentIndex() != idx:
                self.backtest_symbol_source_combo.setCurrentIndex(idx)
                fetch_triggered = True
        except Exception:
            pass
        try:
            self._populate_backtest_lists()
        except Exception:
            pass
        try:
            if self.backtest_stop_btn is not None:
                self.backtest_stop_btn.setEnabled(False)
        except Exception:
            pass
        try:
            logic = (self.backtest_config.get("logic") or "AND").upper()
            def _set_combo(combo: QtWidgets.QComboBox, value: str):
                if combo is None:
                    return
                try:
                    target = (value or "").strip().lower()
                    for i in range(combo.count()):
                        if combo.itemText(i).strip().lower() == target:
                            combo.setCurrentIndex(i)
                            return
                except Exception:
                    pass
            _set_combo(self.backtest_logic_combo, logic)
            capital = float(self.backtest_config.get("capital", 1000.0))
            self.backtest_capital_spin.setValue(capital)
            pct_cfg = float(self.backtest_config.get("position_pct", 2.0) or 0.0)
            if pct_cfg <= 1.0:
                pct_disp = pct_cfg * 100.0
                self.backtest_pospct_spin.setValue(pct_disp)
                self._update_backtest_config("position_pct", pct_disp)
            else:
                self.backtest_pospct_spin.setValue(pct_cfg)
            side_cfg = (self.backtest_config.get("side") or "BOTH").upper()
            side_label = SIDE_LABELS.get(side_cfg, SIDE_LABELS["BOTH"])
            try:
                idx_side = self.backtest_side_combo.findText(side_label, QtCore.Qt.MatchFlag.MatchFixedString)
            except Exception:
                idx_side = self.backtest_side_combo.findText(side_label)
            if idx_side is not None and idx_side >= 0:
                self.backtest_side_combo.setCurrentIndex(idx_side)
            margin_mode_cfg = (self.backtest_config.get("margin_mode") or "Isolated")
            _set_combo(self.backtest_margin_mode_combo, margin_mode_cfg)
            position_mode_cfg = (self.backtest_config.get("position_mode") or "Hedge")
            _set_combo(self.backtest_position_mode_combo, position_mode_cfg)
            assets_mode_cfg = (self.backtest_config.get("assets_mode") or "Single-Asset")
            _set_combo(self.backtest_assets_mode_combo, assets_mode_cfg)
            leverage_cfg = int(self.backtest_config.get("leverage", 5) or 1)
            self.backtest_leverage_spin.setValue(leverage_cfg)
            now_dt = QtCore.QDateTime.currentDateTime()
            start_cfg = self.backtest_config.get("start_date")
            end_cfg = self.backtest_config.get("end_date")
            end_qdt = self._coerce_qdatetime(end_cfg) if end_cfg else now_dt
            if not end_qdt.isValid():
                end_qdt = now_dt
            start_qdt = self._coerce_qdatetime(start_cfg) if start_cfg else end_qdt.addMonths(-3)
            if not start_qdt.isValid() or start_qdt > end_qdt:
                start_qdt = end_qdt.addMonths(-3)
            self.backtest_start_edit.setDateTime(start_qdt)
            self.backtest_end_edit.setDateTime(end_qdt)
        except Exception:
            pass
        self._update_backtest_futures_controls()
        if not fetch_triggered:
            self._refresh_backtest_symbols()

    def _populate_backtest_lists(self):
        try:
            if not self.backtest_symbols_all:
                fallback_ordered: list[str] = []

                def _extend_unique(seq):
                    for sym in seq or []:
                        sym_up = str(sym).strip().upper()
                        if not sym_up:
                            continue
                        if sym_up not in fallback_ordered:
                            fallback_ordered.append(sym_up)

                _extend_unique(self.backtest_config.get("symbols"))
                _extend_unique(self.config.get("symbols"))
                try:
                    if hasattr(self, "symbol_list"):
                        for i in range(self.symbol_list.count()):
                            item = self.symbol_list.item(i)
                            if item:
                                _extend_unique([item.text()])
                except Exception:
                    pass
                if not fallback_ordered:
                    fallback_ordered.append("BTCUSDT")
                self.backtest_symbols_all = list(fallback_ordered)
            self._update_backtest_symbol_list(self.backtest_symbols_all)
        except Exception:
            pass

        interval_candidates: list[str] = []

        def _extend_interval(seq):
            for iv in seq or []:
                iv_norm = str(iv).strip()
                if not iv_norm:
                    continue
                if iv_norm not in interval_candidates:
                    interval_candidates.append(iv_norm)

        _extend_interval(self.backtest_config.get("intervals"))
        try:
            if hasattr(self, "interval_list"):
                for i in range(self.interval_list.count()):
                    item = self.interval_list.item(i)
                    if item:
                        _extend_interval([item.text()])
        except Exception:
            pass
        _extend_interval(BACKTEST_INTERVAL_ORDER)
        if not interval_candidates:
            interval_candidates.append("1h")

        ordered_intervals = [iv for iv in BACKTEST_INTERVAL_ORDER if iv in interval_candidates]
        extras = [iv for iv in interval_candidates if iv not in BACKTEST_INTERVAL_ORDER]
        full_order = ordered_intervals + extras

        selected_intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv in full_order]
        if not selected_intervals and full_order:
            selected_intervals = [full_order[0]]
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            self.backtest_interval_list.clear()
            for iv in full_order:
                item = QtWidgets.QListWidgetItem(iv)
                item.setSelected(iv in selected_intervals)
                self.backtest_interval_list.addItem(item)
        self.backtest_config["intervals"] = list(selected_intervals)
        cfg = self.config.setdefault("backtest", {})
        cfg["intervals"] = list(selected_intervals)
        self._backtest_store_intervals()

    def _set_backtest_symbol_selection(self, symbols):
        symbols_upper = {str(s).upper() for s in (symbols or []) if s}
        with QtCore.QSignalBlocker(self.backtest_symbol_list):
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text().upper() in symbols_upper)
        self._backtest_store_symbols()

    def _set_backtest_interval_selection(self, intervals):
        intervals_norm = {str(iv) for iv in (intervals or []) if iv}
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text() in intervals_norm)
        self._backtest_store_intervals()

    def _update_backtest_symbol_list(self, candidates):
        try:
            candidates = [str(sym).upper() for sym in (candidates or []) if sym]
            unique_candidates: list[str] = []
            seen = set()
            for sym in candidates:
                if sym and sym not in seen:
                    seen.add(sym)
                    unique_candidates.append(sym)
            selected_cfg = [str(s).upper() for s in (self.backtest_config.get("symbols") or []) if s]
            selected = [s for s in selected_cfg if s in unique_candidates]
            if not unique_candidates and selected_cfg:
                unique_candidates = []
                seen.clear()
                for sym in selected_cfg:
                    if sym and sym not in seen:
                        seen.add(sym)
                        unique_candidates.append(sym)
                selected = list(unique_candidates)
            if not selected and unique_candidates:
                selected = [unique_candidates[0]]
            with QtCore.QSignalBlocker(self.backtest_symbol_list):
                self.backtest_symbol_list.clear()
                for sym in unique_candidates:
                    item = QtWidgets.QListWidgetItem(sym)
                    item.setSelected(sym in selected)
                    self.backtest_symbol_list.addItem(item)
            self.backtest_symbols_all = list(unique_candidates)
            self.backtest_config["symbols"] = list(selected)
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(selected)
            if unique_candidates and not selected and self.backtest_symbol_list.count():
                self.backtest_symbol_list.item(0).setSelected(True)
            self._backtest_store_symbols()
        except Exception:
            pass

    def _backtest_store_symbols(self):
        try:
            symbols = []
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if item and item.isSelected():
                    symbols.append(item.text().upper())
            self.backtest_config["symbols"] = symbols
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(symbols)
        except Exception:
            pass

    def _backtest_store_intervals(self):
        try:
            intervals = []
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if item and item.isSelected():
                    intervals.append(item.text())
            self.backtest_config["intervals"] = intervals
            cfg = self.config.setdefault("backtest", {})
            cfg["intervals"] = list(intervals)
        except Exception:
            pass

    def _apply_backtest_intervals_to_dashboard(self):
        try:
            intervals = [
                str(iv).strip()
                for iv in (self.backtest_config.get("intervals") or [])
                if str(iv).strip()
            ]
        except Exception:
            intervals = []
        if not intervals:
            intervals = list(BACKTEST_INTERVAL_ORDER)
        existing = {self.interval_list.item(i).text() for i in range(self.interval_list.count())}
        for iv in intervals:
            if iv not in existing:
                self.interval_list.addItem(QtWidgets.QListWidgetItem(iv))
        with QtCore.QSignalBlocker(self.interval_list):
            for i in range(self.interval_list.count()):
                item = self.interval_list.item(i)
                if item is None:
                    continue
                item.setSelected(item.text() in intervals)
        try:
            self.config["intervals"] = list(intervals)
        except Exception:
            pass
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass

    def _update_backtest_futures_controls(self):
        try:
            source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip().lower()
            is_futures = source.startswith("fut")
        except Exception:
            is_futures = True
        for widget in getattr(self, "_backtest_futures_widgets", []):
            if widget is None:
                continue
            try:
                widget.setVisible(is_futures)
                widget.setEnabled(is_futures)
            except Exception:
                pass

    def _backtest_symbol_source_changed(self, text: str):
        self._update_backtest_config("symbol_source", text)
        self._update_backtest_futures_controls()
        self._refresh_backtest_symbols()

    def _refresh_backtest_symbols(self):
        try:
            worker = getattr(self, "_backtest_symbol_worker", None)
            if worker is not None and worker.isRunning():
                return
        except Exception:
            pass
        if not hasattr(self, "backtest_refresh_symbols_btn"):
            return
        self.backtest_refresh_symbols_btn.setEnabled(False)
        self.backtest_refresh_symbols_btn.setText("Refreshing...")
        source_text = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        source_lower = source_text.lower()
        acct = "Spot" if source_lower.startswith("spot") else "Futures"
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        def _do():
            wrapper = BinanceWrapper(
                api_key,
                api_secret,
                mode=mode,
                account_type=acct,
            )
            return wrapper.fetch_symbols(sort_by_volume=True)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(lambda res, err, src=acct: self._on_backtest_symbols_ready(res, err, src))
        self._backtest_symbol_worker = worker
        try:
            self.backtest_status_label.setText(f"Refreshing {acct.upper()} symbols...")
        except Exception:
            pass
        worker.start()

    def _on_backtest_symbols_ready(self, result, error, source_label):
        try:
            self.backtest_refresh_symbols_btn.setEnabled(True)
            self.backtest_refresh_symbols_btn.setText("Refresh")
        except Exception:
            pass
        self._backtest_symbol_worker = None
        if error or not result:
            msg = f"Backtest symbol refresh failed: {error or 'no symbols returned'}"
            self.log(msg)
            try:
                self.backtest_status_label.setText(msg)
            except Exception:
                pass
            return
        symbols = [str(sym).upper() for sym in (result or []) if sym]
        self.backtest_symbols_all = symbols
        self._update_backtest_symbol_list(symbols)
        msg = f"Loaded {len(symbols)} {source_label.upper()} symbols for backtest."
        self.log(msg)
        try:
            self.backtest_status_label.setText(msg)
        except Exception:
            pass

    def _backtest_dates_changed(self):
        try:
            start_dt = self.backtest_start_edit.dateTime().toString("yyyy-MM-dd HH:mm")
            end_dt = self.backtest_end_edit.dateTime().toString("yyyy-MM-dd HH:mm")
            self.backtest_config["start_date"] = start_dt
            self.backtest_config["end_date"] = end_dt
            cfg = self.config.setdefault("backtest", {})
            cfg["start_date"] = start_dt
            cfg["end_date"] = end_dt
        except Exception:
            pass

    def _update_backtest_config(self, key, value):
        try:
            if key == "side":
                value = self._canonical_side_from_text(value)
            self.backtest_config[key] = value
            cfg = self.config.setdefault("backtest", {})
            cfg[key] = value
        except Exception:
            pass

    def _backtest_toggle_indicator(self, key: str, checked: bool):
        try:
            indicators = self.backtest_config.setdefault("indicators", {})
            params = indicators.setdefault(key, {})
            params["enabled"] = bool(checked)
            cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
            cfg[key] = copy.deepcopy(params)
        except Exception:
            pass

    def _open_backtest_params(self, key: str):
        try:
            params = self.backtest_config.setdefault("indicators", {}).setdefault(key, {})
            dlg = ParamDialog(key, params, self, display_name=INDICATOR_DISPLAY_NAMES.get(key, key))
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                updates = dlg.get_params()
                params.update(updates)
                cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
                cfg[key] = copy.deepcopy(params)
        except Exception:
            pass

    def _run_backtest(self):
        if self.backtest_worker and self.backtest_worker.isRunning():
            self.backtest_status_label.setText("Backtest already running...")
            return

        self._backtest_expected_runs = []

        ctx_backtest = self._override_ctx("backtest")
        pair_table = ctx_backtest.get("table") if ctx_backtest else None
        selected_pairs = []
        if pair_table is not None:
            try:
                rows = sorted({idx.row() for idx in pair_table.selectionModel().selectedRows()})
            except Exception:
                rows = []
            if rows:
                for row in rows:
                    sym_item = pair_table.item(row, 0)
                    iv_item = pair_table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ''
                    iv = iv_item.text().strip() if iv_item else ''
                    if sym and iv:
                        selected_pairs.append((sym, iv))
        if selected_pairs:
            pairs_override_raw = selected_pairs
        else:
            pairs_override_raw = [(str((entry or {}).get('symbol') or '').strip().upper(), str((entry or {}).get('interval') or '').strip())
                                for entry in self.config.get('backtest_symbol_interval_pairs', []) or []
                                if str((entry or {}).get('symbol') or '').strip() and str((entry or {}).get('interval') or '').strip()]
        pairs_override = []
        seen_pairs = set()
        for sym, iv in pairs_override_raw:
            key = (sym, iv)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            pairs_override.append(key)
        symbols = [s for s in (self.backtest_config.get("symbols") or []) if s]
        intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
        if pairs_override:
            symbol_order = []
            interval_order = []
            for sym, iv in pairs_override:
                if sym not in symbol_order:
                    symbol_order.append(sym)
                if iv not in interval_order:
                    interval_order.append(iv)
            if not symbol_order or not interval_order:
                self.backtest_status_label.setText("Symbol/Interval overrides list is empty.")
                return
            symbols = symbol_order
            intervals = interval_order
        if not symbols:
            self.backtest_status_label.setText("Select at least one symbol.")
            return
        if not intervals:
            self.backtest_status_label.setText("Select at least one interval.")
            return

        self.backtest_config["symbols"] = list(symbols)
        self.backtest_config["intervals"] = list(intervals)
        cfg_bt = self.config.setdefault("backtest", {})
        cfg_bt["symbols"] = list(symbols)
        cfg_bt["intervals"] = list(intervals)

        indicators_cfg = self.backtest_config.get("indicators", {}) or {}
        indicators = []
        for key, params in indicators_cfg.items():
            if not params or not params.get("enabled"):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=key, params=clean_params))
        if not indicators:
            self.backtest_status_label.setText("Enable at least one indicator to backtest.")
            return

        start_qdt = self.backtest_start_edit.dateTime()
        end_qdt = self.backtest_end_edit.dateTime()
        if start_qdt > end_qdt:
            self.backtest_status_label.setText("Start date/time must be before end date/time.")
            return

        start_dt = start_qdt.toPyDateTime()
        end_dt = end_qdt.toPyDateTime()
        if start_dt >= end_dt:
            self.backtest_status_label.setText("Backtest range must span a positive duration.")
            return

        capital = float(self.backtest_capital_spin.value())
        if capital <= 0.0:
            self.backtest_status_label.setText("Margin capital must be positive.")
            return

        position_pct = float(self.backtest_pospct_spin.value())
        side_value = self._canonical_side_from_text(self.backtest_side_combo.currentText())
        margin_mode = (self.backtest_margin_mode_combo.currentText() or "Isolated").strip()
        position_mode = (self.backtest_position_mode_combo.currentText() or "Hedge").strip()
        assets_mode = (self.backtest_assets_mode_combo.currentText() or "Single-Asset").strip()
        leverage_value = int(self.backtest_leverage_spin.value() or 1)

        logic = (self.backtest_logic_combo.currentText() or "AND").upper()
        self._update_backtest_config("logic", logic)
        self._update_backtest_config("capital", capital)
        self._update_backtest_config("position_pct", position_pct)
        self._update_backtest_config("side", side_value)
        self._update_backtest_config("margin_mode", margin_mode)
        self._update_backtest_config("position_mode", position_mode)
        self._update_backtest_config("assets_mode", assets_mode)
        self._update_backtest_config("leverage", leverage_value)
        indicator_keys_order = [ind.key for ind in indicators]
        combos_sequence = list(pairs_override) if pairs_override else [(sym, iv) for sym in symbols for iv in intervals]
        expected_runs = []
        if logic == "SEPARATE":
            for sym, iv in combos_sequence:
                for ind in indicators:
                    expected_runs.append((sym, iv, [ind.key]))
        else:
            expected_indicator_list = list(indicator_keys_order)
            for sym, iv in combos_sequence:
                expected_runs.append((sym, iv, list(expected_indicator_list)))
        self._backtest_expected_runs = expected_runs
        self._backtest_dates_changed()

        symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        self._update_backtest_config("symbol_source", symbol_source)
        account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        request = BacktestRequest(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            logic=logic,
            symbol_source=symbol_source,
            start=start_dt,
            end=end_dt,
            capital=capital,
            side=side_value,
            position_pct=position_pct,
            leverage=leverage_value,
            margin_mode=margin_mode,
            position_mode=position_mode,
            assets_mode=assets_mode,
            pair_overrides=pairs_override if pairs_override else None,
        )

        signature = (mode, api_key, api_secret)
        wrapper_entry = self._backtest_wrappers.get(account_type)
        wrapper = None
        if isinstance(wrapper_entry, dict) and wrapper_entry.get("signature") == signature:
            wrapper = wrapper_entry.get("wrapper")
        if wrapper is None:
            try:
                wrapper = BinanceWrapper(
                    api_key,
                    api_secret,
                    mode=mode,
                    account_type=account_type,
                )
                self._backtest_wrappers[account_type] = {"signature": signature, "wrapper": wrapper}
            except Exception as exc:
                msg = f"Unable to initialize Binance wrapper: {exc}"
                self.backtest_status_label.setText(msg)
                self.log(msg)
                return
        else:
            try:
                wrapper.account_type = account_type
            except Exception:
                pass

        try:
            wrapper.indicator_source = self.ind_source_combo.currentText()
        except Exception:
            pass

        engine = BacktestEngine(wrapper)
        self.backtest_worker = _BacktestWorker(engine, request, self)
        self.backtest_worker.progress.connect(self._on_backtest_progress)
        self.backtest_worker.finished.connect(self._on_backtest_finished)
        self.backtest_results_table.setRowCount(0)
        self.backtest_status_label.setText("Running backtest...")
        self.backtest_run_btn.setEnabled(False)
        try:
            self.backtest_stop_btn.setEnabled(True)
        except Exception:
            pass
        try:
            self.backtest_stop_btn.setEnabled(True)
        except Exception:
            pass
        self.backtest_worker.start()

    def _stop_backtest(self):
        try:
            worker = getattr(self, 'backtest_worker', None)
            if worker and worker.isRunning():
                if hasattr(worker, 'request_stop'):
                    worker.request_stop()
                self.backtest_status_label.setText('Stopping backtest...')
                try:
                    self.backtest_stop_btn.setEnabled(False)
                except Exception:
                    pass
                return
            self.backtest_status_label.setText('No backtest running.')
        except Exception:
            pass

    def _on_backtest_progress(self, msg: str):
        self.backtest_status_label.setText(str(msg))

    @staticmethod
    def _normalize_backtest_run(run):
        if is_dataclass(run):
            data = asdict(run)
        elif isinstance(run, dict):
            data = dict(run)
        else:
            indicator_keys = getattr(run, "indicator_keys", [])
            if indicator_keys is None:
                indicator_keys = []
            elif not isinstance(indicator_keys, (list, tuple)):
                indicator_keys = [indicator_keys]
            data = {
                "symbol": getattr(run, "symbol", ""),
                "interval": getattr(run, "interval", ""),
                "logic": getattr(run, "logic", ""),
                "indicator_keys": list(indicator_keys),
                "trades": getattr(run, "trades", 0),
                "roi_value": getattr(run, "roi_value", 0.0),
                "roi_percent": getattr(run, "roi_percent", 0.0),
            }
        data.setdefault("indicator_keys", [])
        keys = data.get("indicator_keys") or []
        if not isinstance(keys, (list, tuple)):
            keys = [keys]
        data["indicator_keys"] = [str(k) for k in keys if k is not None]
        try:
            data["trades"] = int(data.get("trades", 0) or 0)
        except Exception:
            data["trades"] = 0
        for key in ("roi_value", "roi_percent"):
            try:
                data[key] = float(data.get(key, 0.0) or 0.0)
            except Exception:
                data[key] = 0.0
        data["symbol"] = str(data.get("symbol") or "")
        data["interval"] = str(data.get("interval") or "")
        data["logic"] = str(data.get("logic") or "")
        return data

    def _on_backtest_finished(self, result: dict, error: object):
        self.backtest_run_btn.setEnabled(True)
        try:
            self.backtest_stop_btn.setEnabled(False)
        except Exception:
            pass
        worker = getattr(self, "backtest_worker", None)
        if worker and worker.isRunning():
            worker.wait(100)
        self.backtest_worker = None
        if error:
            err_text = str(error) if error is not None else ''
            if isinstance(error, RuntimeError) and 'backtest_cancelled' in err_text.lower():
                self.backtest_status_label.setText('Backtest cancelled.')
                return
            msg = f"Backtest failed: {error}"
            self.backtest_status_label.setText(msg)
            self.log(msg)
            return
        runs_raw = result.get("runs", []) if isinstance(result, dict) else []
        errors = result.get("errors", []) if isinstance(result, dict) else []
        run_dicts = [self._normalize_backtest_run(r) for r in (runs_raw or [])]
        self.backtest_results = run_dicts
        expected_runs = getattr(self, "_backtest_expected_runs", []) or []
        for idx, rd in enumerate(run_dicts):
            if idx < len(expected_runs):
                sym, iv, inds = expected_runs[idx]
                if not rd.get("symbol") and sym:
                    rd["symbol"] = sym
                if not rd.get("interval") and iv:
                    rd["interval"] = iv
                if (not rd.get("indicator_keys")) and inds:
                    rd["indicator_keys"] = list(inds)
        try:
            self.log(f"Backtest returned {len(run_dicts)} run(s).")
            for idx, rd in enumerate(run_dicts):
                self.log(f"Backtest run[{idx}]: {rd}")
        except Exception:
            pass
        self._populate_backtest_results_table(run_dicts)
        summary_parts = []
        if run_dicts:
            summary_parts.append(f"{len(run_dicts)} run(s) completed")
            total_roi = sum(r.get("roi_value", 0.0) for r in run_dicts)
            summary_parts.append(f"Total ROI: {total_roi:+.2f} USDT")
            avg_roi_pct = sum(r.get("roi_percent", 0.0) for r in run_dicts) / max(len(run_dicts), 1)
            summary_parts.append(f"Avg ROI %: {avg_roi_pct:+.2f}%")
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
            for err in errors:
                sym = err.get("symbol")
                interval = err.get("interval")
                self.log(f"Backtest error for {sym}@{interval}: {err.get('error')}")
        if not summary_parts:
            summary_parts.append("No results generated.")
        self.backtest_status_label.setText(" | ".join(summary_parts))

    def _populate_backtest_results_table(self, runs):
        try:
            rows_data = list(runs or [])
            try:
                self.backtest_results_table.setSortingEnabled(False)
            except Exception:
                pass
            try:
                self.backtest_results_table.clearContents()
            except Exception:
                pass
            self.backtest_results_table.setRowCount(len(rows_data))
            for row, run in enumerate(rows_data):
                try:
                    data = run if isinstance(run, dict) else self._normalize_backtest_run(run)
                    symbol = data.get("symbol") or "-"
                    interval = data.get("interval") or "-"
                    logic = data.get("logic") or "-"
                    indicator_keys = data.get("indicator_keys") or []
                    trades = _safe_float(data.get("trades", 0.0), 0.0)
                    roi_value = _safe_float(data.get("roi_value", 0.0), 0.0)
                    roi_percent = _safe_float(data.get("roi_percent", 0.0), 0.0)
                    try:
                        self.log(f"Render row {row}: {symbol}@{interval}, trades={trades}, roi={roi_value}/{roi_percent}")
                    except Exception:
                        pass

                    indicators_display = ", ".join(INDICATOR_DISPLAY_NAMES.get(k, k) for k in indicator_keys)
                    self.backtest_results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(symbol or "-"))
                    self.backtest_results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(interval or "-"))
                    self.backtest_results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(logic or "-"))
                    self.backtest_results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(indicators_display or "-"))
                    trades_display = _safe_int(trades, 0)
                    trades_item = _NumericItem(str(trades_display), trades_display)
                    self.backtest_results_table.setItem(row, 4, trades_item)
                    roi_value_item = _NumericItem(f"{roi_value:+.2f}", roi_value)
                    self.backtest_results_table.setItem(row, 5, roi_value_item)
                    roi_percent_item = _NumericItem(f"{roi_percent:+.2f}%", roi_percent)
                    self.backtest_results_table.setItem(row, 6, roi_percent_item)
                except Exception as row_exc:
                    self.log(f"Backtest table row {row} error: {row_exc}")
                    err_item = QtWidgets.QTableWidgetItem(f"Error: {row_exc}")
                    err_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
                    self.backtest_results_table.setItem(row, 0, err_item)
                    self.backtest_results_table.setItem(row, 1, QtWidgets.QTableWidgetItem("-"))
                    self.backtest_results_table.setItem(row, 2, QtWidgets.QTableWidgetItem("-"))
                    self.backtest_results_table.setItem(row, 3, QtWidgets.QTableWidgetItem("-"))
                    self.backtest_results_table.setItem(row, 4, QtWidgets.QTableWidgetItem("0"))
                    self.backtest_results_table.setItem(row, 5, QtWidgets.QTableWidgetItem("0.00"))
                    self.backtest_results_table.setItem(row, 6, QtWidgets.QTableWidgetItem("0.00%"))
                    continue
            self.backtest_results_table.resizeRowsToContents()
        except Exception as exc:
            self.log(f"Backtest results table error: {exc}")
        finally:
            try:
                self.backtest_results_table.setSortingEnabled(True)
            except Exception:
                pass

    def _create_chart_tab(self):
        tab = QtWidgets.QWidget()
        self.chart_tab = tab
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(controls_layout)

        controls_layout.addWidget(QtWidgets.QLabel("Market:"))
        self.chart_market_combo = QtWidgets.QComboBox()
        for opt in CHART_MARKET_OPTIONS:
            self.chart_market_combo.addItem(opt)
        controls_layout.addWidget(self.chart_market_combo)

        controls_layout.addWidget(QtWidgets.QLabel("Symbol:"))
        self.chart_symbol_combo = QtWidgets.QComboBox()
        self.chart_symbol_combo.setEditable(False)
        self.chart_symbol_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        controls_layout.addWidget(self.chart_symbol_combo)

        controls_layout.addWidget(QtWidgets.QLabel("Interval:"))
        self.chart_interval_combo = QtWidgets.QComboBox()
        self.chart_interval_combo.setEditable(False)
        self.chart_interval_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for iv in CHART_INTERVAL_OPTIONS:
            self.chart_interval_combo.addItem(iv)
        controls_layout.addWidget(self.chart_interval_combo)

        controls_layout.addStretch()

        self.chart_view = None
        if TRADINGVIEW_EMBED_AVAILABLE and TradingViewWidget is not None:
            try:
                self.chart_view = TradingViewWidget(self)
            except Exception:
                self.chart_view = None
        if self.chart_view is not None:
            layout.addWidget(self.chart_view, stretch=1)
        elif QT_CHARTS_AVAILABLE:
            view = QChartView()
            try:
                view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            except Exception:
                pass
            view.setMinimumHeight(300)
            layout.addWidget(view, stretch=1)
            self.chart_view = view
        else:
            self.chart_view = SimpleCandlestickWidget()
            layout.addWidget(self.chart_view, stretch=1)

        self.chart_symbol_combo.currentTextChanged.connect(self._on_chart_controls_changed)
        self.chart_interval_combo.currentTextChanged.connect(self._on_chart_controls_changed)
        self.chart_market_combo.currentTextChanged.connect(self._on_chart_market_changed)

        self._restore_chart_controls_from_config()
        self._on_chart_market_changed(self.chart_market_combo.currentText())
        # Preload symbol universes for both markets so selections react quickly.
        self._load_chart_symbols_async("Futures")
        self._load_chart_symbols_async("Spot")

        if not getattr(self, "_chart_theme_signal_installed", False):
            try:
                self.theme_combo.currentTextChanged.connect(self._on_chart_theme_changed)
                self._chart_theme_signal_installed = True
            except Exception:
                pass

        return tab

    def _restore_chart_controls_from_config(self):
        if not getattr(self, "chart_enabled", False):
            return
        market_cfg = self._normalize_chart_market(self.chart_config.get("market"))
        auto_follow_cfg = self.chart_config.get("auto_follow")
        self._chart_manual_override = False
        if auto_follow_cfg is None:
            self.chart_auto_follow = (market_cfg == "Futures")
        else:
            self.chart_auto_follow = bool(auto_follow_cfg) and market_cfg == "Futures"
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is not None:
            try:
                with QtCore.QSignalBlocker(market_combo):
                    idx = market_combo.findText(market_cfg, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        market_combo.setCurrentIndex(idx)
                    else:
                        market_combo.setCurrentText(market_cfg)
            except Exception:
                market_combo.setCurrentText(market_cfg)
        self.chart_config["market"] = market_cfg
        self.chart_config["auto_follow"] = self.chart_auto_follow
        symbol_cfg = str(self.chart_config.get("symbol") or "").strip().upper()
        interval_cfg = str(self.chart_config.get("interval") or "").strip()
        if symbol_cfg:
            self._set_chart_symbol(symbol_cfg, ensure_option=True)
        if interval_cfg:
            self._set_chart_interval(interval_cfg)
        elif CHART_INTERVAL_OPTIONS:
            self._set_chart_interval(CHART_INTERVAL_OPTIONS[0])

    def _update_chart_symbol_options(self, symbols=None):
        if not getattr(self, "chart_enabled", False):
            return
        if not hasattr(self, "chart_symbol_combo"):
            return
        combo = self.chart_symbol_combo
        current = combo.currentText().strip().upper()
        market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
        if symbols is None:
            symbols = list(self.chart_symbol_cache.get(market) or [])
            if not symbols and market == "Futures":
                symbols = self._current_dashboard_symbols()
                if symbols:
                    self.chart_symbol_cache[market] = list(symbols)
        uniques = []
        seen = set()
        for sym in symbols or []:
            sym_norm = str(sym or "").strip().upper()
            if sym_norm and sym_norm not in seen:
                seen.add(sym_norm)
                uniques.append(sym_norm)
        self.chart_symbol_cache[market] = list(uniques)
        display_symbols = list(uniques)
        alias_map = {}
        if market == "Futures":
            display_symbols = []
            for sym in uniques:
                disp = self._futures_display_symbol(sym)
                alias_map[disp] = sym
                if disp not in display_symbols:
                    display_symbols.append(disp)
            preferred_disp = self._futures_display_symbol("BTCUSDT")
            if "BTCUSDT" in uniques:
                if preferred_disp in display_symbols:
                    display_symbols.remove(preferred_disp)
                display_symbols.insert(0, preferred_disp)
                alias_map[preferred_disp] = "BTCUSDT"
        if not isinstance(getattr(self, "_chart_symbol_alias_map", None), dict):
            self._chart_symbol_alias_map = {}
        self._chart_symbol_alias_map[market] = alias_map
        if market == "Futures" and current:
            if current not in alias_map:
                reverse_map = {v: k for k, v in alias_map.items()}
                if current in reverse_map:
                    current = reverse_map[current]
                else:
                    current = self._futures_display_symbol(current)
        elif market != "Futures":
            alias_map = {}
        try:
            with QtCore.QSignalBlocker(combo):
                combo.clear()
                if display_symbols:
                    combo.addItems(display_symbols)
        except Exception:
            combo.clear()
            if display_symbols:
                combo.addItems(display_symbols)
        if current:
            if combo.findText(current, QtCore.Qt.MatchFlag.MatchFixedString) >= 0:
                combo.setCurrentText(current)
            else:
                combo.setEditText(current)
        elif display_symbols:
            combo.setCurrentIndex(0)

    @staticmethod
    def _normalize_chart_market(market):
        text = str(market or "").strip().lower()
        for opt in CHART_MARKET_OPTIONS:
            if text.startswith(opt.lower()):
                return opt
        return "Futures"

    def _futures_display_symbol(self, symbol: str) -> str:
        sym = (symbol or "").strip().upper()
        if not sym:
            return sym
        if sym.endswith(".P"):
            return sym
        if sym.endswith("USDT") and not sym.endswith("BUSD"):
            return f"{sym}.P"
        return sym

    def _resolve_chart_symbol_for_api(self, symbol: str, market: str | None = None) -> str:
        sym = (symbol or "").strip().upper()
        cfg_market = market
        if cfg_market is None:
            try:
                cfg_market = self.chart_config.get("market")
            except Exception:
                cfg_market = None
        market_norm = self._normalize_chart_market(cfg_market)
        if market_norm == "Futures":
            alias_map = {}
            mapping = getattr(self, "_chart_symbol_alias_map", {})
            if isinstance(mapping, dict):
                alias_map = mapping.get(market_norm, {}) or {}
            if sym in alias_map:
                return alias_map[sym]
            if sym.endswith(".P"):
                return sym[:-2]
        return sym

    def _current_dashboard_symbols(self):
        symbols = []
        if hasattr(self, "symbol_list") and isinstance(self.symbol_list, QtWidgets.QListWidget):
            try:
                for idx in range(self.symbol_list.count()):
                    item = self.symbol_list.item(idx)
                    if item:
                        sym = item.text().strip().upper()
                        if sym:
                            symbols.append(sym)
            except Exception:
                return symbols
        return symbols

    def _on_chart_controls_changed(self, *_args):
        if not getattr(self, "chart_enabled", False):
            return
        if not hasattr(self, "chart_config"):
            return
        try:
            symbol = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            return
        changed = False
        symbol_changed = False
        if symbol:
            if self.chart_config.get("symbol") != symbol:
                changed = True
                symbol_changed = True
            self.chart_config["symbol"] = symbol
        if interval:
            if self.chart_config.get("interval") != interval:
                changed = True
            self.chart_config["interval"] = interval
        if self._chart_updating:
            return
        market = self._normalize_chart_market(self.chart_config.get("market"))
        if market == "Futures" and symbol_changed:
            self._chart_manual_override = True
            self.chart_auto_follow = False
            self.chart_config["auto_follow"] = False
        if changed:
            self._chart_needs_render = True
            if self._is_chart_visible():
                self.load_chart(auto=True)

    def _chart_account_type(self, market: str) -> str:
        normalized = self._normalize_chart_market(market)
        return "Spot" if normalized == "Spot" else "Futures"

    def _on_chart_market_changed(self, text: str):
        if not getattr(self, "chart_enabled", False):
            return
        market = self._normalize_chart_market(text)
        self.chart_config["market"] = market
        self._chart_manual_override = False
        self.chart_auto_follow = (market == "Futures")
        self.chart_config["auto_follow"] = self.chart_auto_follow
        cache = list(self.chart_symbol_cache.get(market) or [])
        if not cache:
            cache = list(DEFAULT_CHART_SYMBOLS)
            self.chart_symbol_cache[market] = cache
        self._update_chart_symbol_options(cache)
        self._chart_needs_render = True
        if cache:
            preferred_cfg = self.chart_config.get("symbol")
            preferred_actual = self._resolve_chart_symbol_for_api(preferred_cfg, market) if preferred_cfg else None
            if not preferred_actual or preferred_actual not in cache:
                preferred_actual = cache[0]
            preferred_display = self._futures_display_symbol(preferred_actual) if market == "Futures" else preferred_actual
            changed = self._set_chart_symbol(preferred_display, ensure_option=True, from_follow=self.chart_auto_follow)
            if self.chart_auto_follow and market == "Futures":
                if changed or self._chart_needs_render:
                    self._apply_dashboard_selection_to_chart(load=False)
            elif self._is_chart_visible():
                self.load_chart(auto=True)
        self._load_chart_symbols_async(market)

    def _load_chart_symbols_async(self, market: str):
        if not getattr(self, "chart_enabled", False):
            return
        market_key = self._normalize_chart_market(market)
        if market_key in self._chart_symbol_loading:
            return
        self._chart_symbol_loading.add(market_key)
        api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"
        account_type = self._chart_account_type(market_key)

        def _do():
            tmp_wrapper = BinanceWrapper(api_key, api_secret, mode=mode, account_type=account_type)
            syms = tmp_wrapper.fetch_symbols(sort_by_volume=True)
            cleaned = []
            seen_local = set()
            for sym in syms or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm:
                    continue
                if sym_norm in seen_local:
                    continue
                seen_local.add(sym_norm)
                cleaned.append(sym_norm)
            return cleaned

        def _chart_should_render():
            try:
                return bool(self._chart_pending_initial_load or self._is_chart_visible())
            except Exception:
                return False

        def _done(res, err):
            try:
                symbols = []
                if isinstance(res, list) and res:
                    symbols = [str(sym or "").strip().upper() for sym in res if str(sym or "").strip()]
                if err or not symbols:
                    try:
                        self.log(f"Chart symbol load error for {market_key}: {err or 'no symbols returned'}; using defaults.")
                    except Exception:
                        pass
                    symbols = list(DEFAULT_CHART_SYMBOLS)
                self.chart_symbol_cache[market_key] = symbols
                self._chart_needs_render = True
                current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
                if current_market == market_key:
                    self._update_chart_symbol_options(symbols)
                    if symbols:
                        preferred_cfg = self.chart_config.get("symbol")
                        preferred_actual = self._resolve_chart_symbol_for_api(preferred_cfg, market_key) if preferred_cfg else None
                        if not preferred_actual or preferred_actual not in symbols:
                            preferred_actual = symbols[0]
                        preferred_display = self._futures_display_symbol(preferred_actual) if market_key == "Futures" else preferred_actual
                        from_follow = (market_key == "Futures") and not self._chart_manual_override
                        changed = self._set_chart_symbol(preferred_display, ensure_option=True, from_follow=from_follow)
                        if from_follow:
                            if changed:
                                self._apply_dashboard_selection_to_chart(load=True)
                        elif changed and _chart_should_render():
                            self.load_chart(auto=True)
                    elif _chart_should_render():
                        self.load_chart(auto=True)
            finally:
                self._chart_symbol_loading.discard(market_key)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.start()

    def _apply_dashboard_selection_to_chart(self, load: bool = False):
        if not getattr(self, "chart_enabled", False):
            return
        should_render = self._chart_pending_initial_load or self._is_chart_visible()
        if not self.chart_auto_follow:
            if load and should_render:
                self.load_chart(auto=True)
            return
        current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
        if current_market != "Futures":
            if load and should_render:
                self.load_chart(auto=True)
            return
        changed = False
        symbol = self._selected_dashboard_symbol()
        interval = self._selected_dashboard_interval()
        if symbol:
            display_symbol = self._futures_display_symbol(symbol) if current_market == "Futures" else symbol
            changed = self._set_chart_symbol(display_symbol, ensure_option=True, from_follow=True) or changed
        if interval:
            changed = self._set_chart_interval(interval) or changed
        if (changed and should_render) or (load and should_render):
            self.load_chart(auto=True)

    def _selected_dashboard_symbol(self):
        if not getattr(self, "chart_enabled", False):
            return ""
        if not hasattr(self, "symbol_list"):
            return ""
        selected = []
        try:
            for idx in range(self.symbol_list.count()):
                item = self.symbol_list.item(idx)
                if item and item.isSelected():
                    sym = item.text().strip().upper()
                    if sym:
                        selected.append(sym)
        except Exception:
            return ""
        if selected:
            return selected[0]
        if self.symbol_list.count():
            first_item = self.symbol_list.item(0)
            if first_item:
                return first_item.text().strip().upper()
        return self.chart_config.get("symbol", "")

    def _selected_dashboard_interval(self):
        if not getattr(self, "chart_enabled", False):
            return ""
        if not hasattr(self, "interval_list"):
            return ""
        selected = []
        try:
            for idx in range(self.interval_list.count()):
                item = self.interval_list.item(idx)
                if item and item.isSelected():
                    iv = item.text().strip()
                    if iv:
                        selected.append(iv)
        except Exception:
            return ""
        if selected:
            return selected[0]
        if self.interval_list.count():
            first_item = self.interval_list.item(0)
            if first_item:
                return first_item.text().strip()
        return self.chart_config.get("interval", "")

    @staticmethod
    def _canonical_side_from_text(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return "BOTH"
        lower = raw.lower()
        if lower in SIDE_LABEL_LOOKUP:
            return SIDE_LABEL_LOOKUP[lower]
        if lower.startswith("buy"):
            return "BUY"
        if lower.startswith("sell"):
            return "SELL"
        return "BOTH"

    @staticmethod
    def _canonicalize_interval(interval: str) -> str:
        raw = str(interval or "").strip()
        if not raw:
            return ""
        lower = raw.lower()
        if lower in BINANCE_INTERVAL_LOWER:
            return lower
        if raw.upper() == "1M" or lower in {"1month", "1mo"}:
            return "1M"
        return ""

    def _resolve_dashboard_side(self) -> str:
        sel = self.side_combo.currentText() if hasattr(self, "side_combo") else ""
        return self._canonical_side_from_text(sel)

    def _collect_strategy_indicators(self, symbol: str, side_key: str) -> list[str]:
        indicators = set()
        metadata = getattr(self, "_engine_indicator_map", {}) or {}
        side_key = (side_key or "").upper()
        for meta in metadata.values():
            if not isinstance(meta, dict):
                continue
            if meta.get("symbol") != symbol:
                continue
            side_cfg = (meta.get("side") or "BOTH").upper()
            if side_key in ("", "SPOT") or side_cfg == "BOTH":
                pass
            elif side_key == "L" and side_cfg != "BUY":
                continue
            elif side_key == "S" and side_cfg != "SELL":
                continue
            for ind in meta.get("indicators") or []:
                if ind:
                    indicators.add(str(ind))
        return sorted(indicators)

    def _set_chart_symbol(self, symbol: str, ensure_option: bool = False, from_follow: bool = False) -> bool:
        if not getattr(self, "chart_enabled", False):
            return False
        if not hasattr(self, "chart_symbol_combo"):
            return False
        combo = self.chart_symbol_combo
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        before = combo.currentText().strip().upper()
        self._chart_updating = True
        changed = False
        try:
            try:
                with QtCore.QSignalBlocker(combo):
                    idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    elif ensure_option:
                        combo.addItem(normalized)
                        combo.setCurrentIndex(combo.count() - 1)
                    else:
                        combo.setEditText(normalized)
            except Exception:
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                elif ensure_option:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
                else:
                    combo.setEditText(normalized)
            after = combo.currentText().strip().upper()
            changed = before != after
            if after:
                self.chart_config["symbol"] = after
        finally:
            self._chart_updating = False
        if changed:
            self._chart_needs_render = True
        if from_follow:
            self._chart_manual_override = False
            self.chart_auto_follow = True
            self.chart_config["auto_follow"] = True
        return changed

    def _set_chart_interval(self, interval: str) -> bool:
        if not getattr(self, "chart_enabled", False):
            return False
        if not hasattr(self, "chart_interval_combo"):
            return False
        combo = self.chart_interval_combo
        normalized = str(interval or "").strip()
        if not normalized:
            return False
        before = combo.currentText().strip()
        self._chart_updating = True
        changed = False
        try:
            try:
                with QtCore.QSignalBlocker(combo):
                    idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.addItem(normalized)
                        combo.setCurrentIndex(combo.count() - 1)
            except Exception:
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
            after = combo.currentText().strip()
            changed = before != after
            if after:
                self.chart_config["interval"] = after
        finally:
            self._chart_updating = False
        if changed:
            self._chart_needs_render = True
        return changed

    def _map_chart_interval(self, interval: str) -> str | None:
        key = str(interval or "").strip().lower()
        if not key:
            return None
        mapped = TRADINGVIEW_INTERVAL_MAP.get(key)
        if mapped:
            return mapped
        if key.endswith("m"):
            try:
                minutes = int(float(key[:-1]))
                if minutes > 0:
                    return str(minutes)
            except Exception:
                return None
        if key.endswith("h"):
            try:
                hours = float(key[:-1])
                minutes = int(hours * 60)
                if minutes > 0:
                    return str(minutes)
            except Exception:
                return None
        if key.endswith("d"):
            try:
                days = int(float(key[:-1]))
                if days > 0:
                    return f"{days}D"
            except Exception:
                return None
        if key.endswith("w"):
            try:
                weeks = int(float(key[:-1]))
                if weeks > 0:
                    return f"{weeks}W"
            except Exception:
                return None
        if key.endswith("mo") or key.endswith("month") or key.endswith("months"):
            digits = "".join(ch for ch in key if ch.isdigit())
            try:
                qty = int(digits) if digits else 1
            except Exception:
                qty = 1
            if qty > 0:
                return f"{qty}M"
        if key.endswith("y") or key.endswith("year") or key.endswith("years"):
            digits = "".join(ch for ch in key if ch.isdigit())
            try:
                qty = int(digits) if digits else 1
            except Exception:
                qty = 1
            if qty > 0:
                return f"{qty * 12}M"
        return None

    def _format_chart_symbol(self, symbol: str, market: str | None = None) -> str:
        raw = str(symbol or "").strip().upper().replace("/", "")
        if ":" in raw:
            return raw
        market_norm = self._normalize_chart_market(market)
        prefix = TRADINGVIEW_SYMBOL_PREFIX
        try:
            account_text = (self.account_combo.currentText() or "").strip().lower()
            if "bybit" in account_text:
                prefix = "BYBIT:"
            elif "spot" in account_text:
                prefix = "BINANCE:"
            elif "future" in account_text:
                prefix = "BINANCE:"
        except Exception:
            prefix = TRADINGVIEW_SYMBOL_PREFIX
        return f"{prefix}{raw}"

    def _show_chart_status(self, message: str, color: str = "#d1d4dc"):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
            chart = QChart()
            chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
            try:
                chart.legend().hide()
            except Exception:
                pass
            try:
                text_item = QtWidgets.QGraphicsSimpleTextItem(str(message), chart)
                text_item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
                text_item.setPos(12, 12)
            except Exception:
                try:
                    chart.setTitle(str(message))
                    chart.setTitleBrush(QtGui.QBrush(QtGui.QColor(color)))
                except Exception:
                    pass
            view.setChart(chart)
        elif TRADINGVIEW_EMBED_AVAILABLE and TradingViewWidget is not None and isinstance(view, TradingViewWidget):
            try:
                view.show_message(message, color=color)
            except Exception:
                pass
        elif isinstance(view, SimpleCandlestickWidget):
            view.set_message(message, color=color)

    def _render_candlestick_chart(self, symbol: str, interval_code: str, candles: list[dict]):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
            if not candles:
                self._show_chart_status("No data available.", color="#f75467")
                return
            chart = QChart()
            chart.setTitle(f"{symbol} - {interval_code}")
            chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
            chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
            try:
                chart.legend().hide()
            except Exception:
                pass

            series = QCandlestickSeries()
            try:
                series.setIncreasingColor(QtGui.QColor("#0ebb7a"))
                series.setDecreasingColor(QtGui.QColor("#f75467"))
            except Exception:
                pass

            lows: list[float] = []
            highs: list[float] = []
            for candle in candles:
                try:
                    open_ = float(candle.get("open", 0.0))
                    high = float(candle.get("high", 0.0))
                    low = float(candle.get("low", 0.0))
                    close = float(candle.get("close", 0.0))
                    timestamp = float(candle.get("time", 0.0)) * 1000.0
                except Exception:
                    continue
                set_item = QCandlestickSet(open_, high, low, close, timestamp)
                series.append(set_item)
                lows.append(low)
                highs.append(high)

            if not lows or not highs:
                self._show_chart_status("No data available.", color="#f75467")
                return

            chart.addSeries(series)

            axis_x = QDateTimeAxis()
            axis_x.setFormat("dd.MM HH:mm")
            axis_x.setLabelsColor(QtGui.QColor("#d1d4dc"))
            axis_x.setTitleText("Time")
            chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)
            try:
                axis_x.setRange(
                    QtCore.QDateTime.fromSecsSinceEpoch(int(candles[0]["time"])),
                    QtCore.QDateTime.fromSecsSinceEpoch(int(candles[-1]["time"])),
                )
            except Exception:
                pass

            axis_y = QValueAxis()
            axis_y.setLabelFormat("%.2f")
            axis_y.setTitleText("Price")
            axis_y.setLabelsColor(QtGui.QColor("#d1d4dc"))
            chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)
            try:
                axis_y.setRange(min(lows), max(highs))
            except Exception:
                pass

            chart.setMargins(QtCore.QMargins(8, 8, 8, 8))
            view.setChart(chart)
        elif isinstance(view, SimpleCandlestickWidget):
            if not candles:
                view.set_message("No data available.", color="#f75467")
            else:
                view.set_candles(candles)
        else:
            return

    def _on_chart_theme_changed(self, *_args):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if TRADINGVIEW_EMBED_AVAILABLE and TradingViewWidget is not None and isinstance(view, TradingViewWidget):
            try:
                theme_name = (self.theme_combo.currentText() or "").strip()
            except Exception:
                theme_name = self.config.get("theme", "Dark")
            try:
                view.apply_theme(theme_name)
            except Exception:
                pass

    def _on_dashboard_selection_for_chart(self):
        if self.chart_auto_follow:
            self._apply_dashboard_selection_to_chart(load=True)

    def _is_chart_visible(self):
        if not getattr(self, "chart_enabled", False):
            return False
        try:
            tabs = getattr(self, "tabs", None)
            chart_tab = getattr(self, "chart_tab", None)
            if tabs is None or chart_tab is None:
                return False
            return tabs.currentWidget() is chart_tab
        except Exception:
            return False

    def _on_tab_changed(self, index: int):
        try:
            widget = self.tabs.widget(index)
        except Exception:
            return
        if widget is getattr(self, "chart_tab", None):
            if self._chart_pending_initial_load:
                self.load_chart(auto=True)
            elif self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=True)
            elif self._chart_needs_render:
                self.load_chart(auto=True)
            self._chart_pending_initial_load = False

    def load_chart(self, auto: bool = False):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if view is None:
            if not auto:
                self.log("Charts unavailable: install PyQt6-Charts for visualization.")
            self._show_chart_status("Charts unavailable.", color="#f75467")
            return
        try:
            symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval_text = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            if not auto:
                self.log("Chart: unable to read current selection.")
            return
        if not symbol_text:
            if not auto:
                self.log("Chart: please choose a symbol.")
            return
        if not interval_text:
            if not auto:
                self.log("Chart: please choose an interval.")
            return
        interval_code = self._map_chart_interval(interval_text)
        if not interval_code:
            if not auto:
                self.log(f"Chart: unsupported interval '{interval_text}'.")
            return
        market_text = self._normalize_chart_market(self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None)
        api_symbol = self._resolve_chart_symbol_for_api(symbol_text, market_text)

        existing_worker = getattr(self, "_chart_worker", None)
        if existing_worker and existing_worker.isRunning():
            try:
                existing_worker.requestInterruption()
            except Exception:
                pass
        self._chart_worker = None

        if TRADINGVIEW_EMBED_AVAILABLE and TradingViewWidget is not None and isinstance(view, TradingViewWidget):
            try:
                theme_name = (self.theme_combo.currentText() or "").strip()
            except Exception:
                theme_name = self.config.get("theme", "Dark")
            tv_symbol = self._format_chart_symbol(symbol_text, market_text)
            theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
            self._chart_pending_initial_load = False
            try:
                view.set_chart(tv_symbol, interval_code, theme=theme_code, timezone="Etc/UTC")
                self.chart_config["symbol"] = symbol_text
                self.chart_config["interval"] = interval_text
                self.chart_config["market"] = market_text
                self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
                self._chart_needs_render = False
            except Exception as exc:
                self._chart_needs_render = True
                if not auto:
                    self.log(f"Chart load failed: {exc}")
                try:
                    view.show_message("Failed to load TradingView chart.", color="#f75467")
                except Exception:
                    pass
            return

        if not QT_CHARTS_AVAILABLE and not isinstance(view, SimpleCandlestickWidget):
            if not auto:
                self.log("Charts unavailable: install PyQt6-Charts for visualization.")
            self._show_chart_status("Charts unavailable.", color="#f75467")
            return
        account_type = "Futures" if market_text == "Futures" else "Spot"
        api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"

        def _do():
            thread = QtCore.QThread.currentThread()
            if thread.isInterruptionRequested():
                return None
            wrapper = BinanceWrapper(api_key, api_secret, mode=mode, account_type=account_type)
            try:
                wrapper.indicator_source = self.ind_source_combo.currentText()
            except Exception:
                pass
            df = wrapper.get_klines(api_symbol, interval_text, limit=400)
            if df is None or df.empty:
                raise RuntimeError("no_kline_data")
            df = df.tail(400)
            candles = []
            for ts, row in df.iterrows():
                if thread.isInterruptionRequested():
                    return None
                try:
                    dt = ts.to_pydatetime()
                except Exception:
                    dt = ts
                if not isinstance(dt, datetime):
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                epoch = int(dt.timestamp())
                try:
                    candles.append({
                        "time": epoch,
                        "open": float(row.get('open', 0.0)),
                        "high": float(row.get('high', 0.0)),
                        "low": float(row.get('low', 0.0)),
                        "close": float(row.get('close', 0.0)),
                    })
                except Exception:
                    continue
            if thread.isInterruptionRequested():
                return None
            if not candles:
                raise RuntimeError("no_valid_candles")
            return {"candles": candles}

        def _done(res, err, worker_ref=None):
            if worker_ref is not getattr(self, "_chart_worker", None):
                return
            self._chart_worker = None
            self._chart_pending_initial_load = False
            if err or not isinstance(res, dict):
                self._chart_needs_render = True
                if not auto and err:
                    self.log(f"Chart load failed: {err}")
                self._show_chart_status("Failed to load chart data.", color="#f75467")
                return
            candles = res.get("candles") or []
            self._render_candlestick_chart(symbol_text, interval_code, candles)
            self.chart_config["symbol"] = symbol_text
            self.chart_config["interval"] = interval_text
            self.chart_config["market"] = market_text
            self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
            self._chart_needs_render = False

        self._show_chart_status("Loading chartâ€¦", color="#d1d4dc")
        self._chart_needs_render = True
        worker = CallWorker(_do, parent=self)
        self._chart_worker = worker
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(lambda res, err, w=worker: _done(res, err, worker_ref=w))
        worker.start()

    def init_ui(self):
        self.setWindowTitle("Binance Trading Bot")
        try:
            self.setWindowIcon(QtGui.QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "binance_icon.ico")))
        except Exception:
            pass
        root_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root_layout.addWidget(self.tabs)

        # ---------------- Dashboard tab ----------------
        tab1 = QtWidgets.QWidget()
        tab1_layout = QtWidgets.QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 0, 0, 0)
        tab1_layout.setSpacing(0)

        self.dashboard_scroll = QtWidgets.QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        tab1_layout.addWidget(self.dashboard_scroll)

        scroll_contents = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_contents)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        self.dashboard_scroll.setWidget(scroll_contents)

        # Top grid
        grid = QtWidgets.QGridLayout()

        grid.addWidget(QtWidgets.QLabel("API Key:"), 0, 0)
        self.api_key_edit = QtWidgets.QLineEdit(self.config['api_key'])
        grid.addWidget(self.api_key_edit, 0, 1)

        grid.addWidget(QtWidgets.QLabel("API Secret:"), 1, 0)
        self.api_secret_edit = QtWidgets.QLineEdit(self.config['api_secret'])
        self.api_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        grid.addWidget(self.api_secret_edit, 1, 1)
        self.api_key_edit.editingFinished.connect(self._reconfigure_positions_worker)
        self.api_secret_edit.editingFinished.connect(self._reconfigure_positions_worker)

        grid.addWidget(QtWidgets.QLabel("Mode:"), 0, 2)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Live", "Demo/Testnet"])
        self.mode_combo.setCurrentText(self.config.get('mode', 'Live'))
        grid.addWidget(self.mode_combo, 0, 3)
        self.mode_combo.currentTextChanged.connect(lambda _=None: self._reconfigure_positions_worker())

        grid.addWidget(QtWidgets.QLabel("Theme:"), 0, 4)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        current_theme = self.config.get("theme") or "Dark"
        if current_theme not in ("Light", "Dark"):
            current_theme = "Dark"
        self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        grid.addWidget(self.theme_combo, 0, 5)

        self.bot_status_label_tab1 = QtWidgets.QLabel()
        self.bot_status_label_tab1.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.bot_status_label_tab1, 0, 6, 1, 4)

        grid.addWidget(QtWidgets.QLabel("Account Type:"), 1, 2)
        self.account_combo = QtWidgets.QComboBox()
        self.account_combo.addItems(["Spot", "Futures"])
        self.account_combo.setCurrentText(self.config.get('account_type', 'Futures'))
        grid.addWidget(self.account_combo, 1, 3)
        self.account_combo.currentTextChanged.connect(lambda _=None: self._reconfigure_positions_worker())

        grid.addWidget(QtWidgets.QLabel("Total USDT balance:"), 2, 0)
        self.balance_label = QtWidgets.QLabel("N/A")
        grid.addWidget(self.balance_label, 2, 1)
        self.pos_mode_label = QtWidgets.QLabel("Position Mode: N/A")
        grid.addWidget(self.pos_mode_label, 2, 6, 1, 2)
        self.refresh_balance_btn = QtWidgets.QPushButton("Refresh Balance")
        self.refresh_balance_btn.clicked.connect(lambda: self.update_balance_label())
        grid.addWidget(self.refresh_balance_btn, 2, 2)

        grid.addWidget(QtWidgets.QLabel("Leverage (Futures):"), 2, 3)
        self.leverage_spin = QtWidgets.QSpinBox()
        self.leverage_spin.setRange(1, 150)
        self.leverage_spin.setValue(self.config.get('leverage', 5))
        self.leverage_spin.valueChanged.connect(self.on_leverage_changed)
        grid.addWidget(self.leverage_spin, 2, 4)

        grid.addWidget(QtWidgets.QLabel("Margin Mode (Futures):"), 2, 5)
        self.margin_mode_combo = QtWidgets.QComboBox()
        self.margin_mode_combo.addItems(["Cross", "Isolated"])
        self.margin_mode_combo.setCurrentText(self.config.get('margin_mode', 'Isolated'))
        grid.addWidget(self.margin_mode_combo, 2, 6)

        grid.addWidget(QtWidgets.QLabel("Position Mode:"), 2, 7)
        self.position_mode_combo = QtWidgets.QComboBox()
        self.position_mode_combo.addItems(["One-way", "Hedge"])
        self.position_mode_combo.setCurrentText(self.config.get("position_mode", "Hedge"))
        grid.addWidget(self.position_mode_combo, 2, 8)

        grid.addWidget(QtWidgets.QLabel("Assets Mode:"), 2, 9)
        self.assets_mode_combo = QtWidgets.QComboBox()
        self.assets_mode_combo.addItems(["Single-Asset", "Multi-Assets"])
        self.assets_mode_combo.setCurrentText(self.config.get("assets_mode", "Single-Asset"))
        grid.addWidget(self.assets_mode_combo, 2, 10)

        grid.addWidget(QtWidgets.QLabel("Time-in-Force:"), 3, 2)
        self.tif_combo = QtWidgets.QComboBox()
        self.tif_combo.addItems(["GTC", "IOC", "FOK", "GTD"])
        self.tif_combo.setCurrentText(self.config.get("tif", "GTC"))
        grid.addWidget(self.tif_combo, 3, 3)
        self.gtd_minutes_spin = QtWidgets.QSpinBox()
        self.gtd_minutes_spin.setRange(1, 1440)
        self.gtd_minutes_spin.setValue(self.config.get("gtd_minutes", 30))
        self.gtd_minutes_spin.setSuffix(" min (GTD)")
        grid.addWidget(self.gtd_minutes_spin, 3, 4)
        # Show GTD minutes only when TIF == 'GTD'
        def _update_gtd_visibility(text:str):
            is_gtd = (text == 'GTD')
            self.gtd_minutes_spin.setVisible(is_gtd)
            self.gtd_minutes_spin.setEnabled(is_gtd)
        self.tif_combo.currentTextChanged.connect(_update_gtd_visibility)
        _update_gtd_visibility(self.tif_combo.currentText())

        grid.addWidget(QtWidgets.QLabel("Indicator Source:"), 3, 0)
        self.ind_source_combo = QtWidgets.QComboBox()
        self.ind_source_combo.addItems([
            "Binance spot",
            "Binance futures",
            "TradingView",
            "Bybit",
            "Coinbase",
            "OKX",
            "Gate",
            "Bitget",
            "Mexc",
            "Kucoin",
            "HTX",
            "Kraken",
        ])
        self.ind_source_combo.setCurrentText(self.config.get("indicator_source", "Binance futures"))
        grid.addWidget(self.ind_source_combo, 3, 1, 1, 2)

        scroll_layout.addLayout(grid)

        # Markets & Intervals
        sym_group = QtWidgets.QGroupBox("Markets & Intervals")
        sgrid = QtWidgets.QGridLayout(sym_group)

        sgrid.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 0, 0)
        self.symbol_list = QtWidgets.QListWidget()
        self.symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.symbol_list.setMinimumHeight(260)
        self.symbol_list.itemSelectionChanged.connect(self._reconfigure_positions_worker)
        self.symbol_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
        sgrid.addWidget(self.symbol_list, 1, 0, 4, 2)

        self.refresh_symbols_btn = QtWidgets.QPushButton("Refresh Symbols")
        self.refresh_symbols_btn.clicked.connect(self.refresh_symbols)
        sgrid.addWidget(self.refresh_symbols_btn, 5, 0, 1, 2)

        sgrid.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 0, 2)
        self.interval_list = QtWidgets.QListWidget()
        self.interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.interval_list.setMinimumHeight(260)
        for it in CHART_INTERVAL_OPTIONS:
            self.interval_list.addItem(QtWidgets.QListWidgetItem(it))
        self.interval_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
        sgrid.addWidget(self.interval_list, 1, 2, 3, 2)

        self.custom_interval_edit = QtWidgets.QLineEdit()
        self.custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
        self.add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")
        def _add_custom_intervals():
            txt = self.custom_interval_edit.text().strip()
            if not txt:
                return
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            existing = set(self.interval_list.item(i).text() for i in range(self.interval_list.count()))
            source = (self.ind_source_combo.currentText() or '').strip().lower() if hasattr(self, 'ind_source_combo') else ''
            is_binance_source = 'binance' in source
            for p in parts:
                norm = p.strip()
                key = norm.lower()
                if is_binance_source and key not in BINANCE_SUPPORTED_INTERVALS:
                    self.log(f"Skipping unsupported Binance interval '{norm}'.")
                    continue
                if norm not in existing:
                    self.interval_list.addItem(QtWidgets.QListWidgetItem(norm))
                    existing.add(norm)
            self.custom_interval_edit.clear()
        self.add_interval_btn.clicked.connect(_add_custom_intervals)
        sgrid.addWidget(self.custom_interval_edit, 4, 2)
        sgrid.addWidget(self.add_interval_btn, 4, 3)
        self.use_backtest_intervals_btn = QtWidgets.QPushButton("Use Backtest Intervals")
        self.use_backtest_intervals_btn.clicked.connect(self._apply_backtest_intervals_to_dashboard)
        sgrid.addWidget(self.use_backtest_intervals_btn, 5, 2, 1, 2)

        scroll_layout.addWidget(sym_group)

        runtime_override_group = self._create_override_group("runtime", self.symbol_list, self.interval_list)
        scroll_layout.addWidget(runtime_override_group)

        # Strategy Controls
        strat_group = QtWidgets.QGroupBox("Strategy Controls")
        g = QtWidgets.QGridLayout(strat_group)

        g.addWidget(QtWidgets.QLabel("Side:"), 0, 0)
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems([SIDE_LABELS["BUY"], SIDE_LABELS["SELL"], SIDE_LABELS["BOTH"]])
        current_side = (self.config.get("side", "BOTH") or "BOTH").upper()
        label = SIDE_LABELS.get(current_side, SIDE_LABELS["BOTH"])
        idx = self.side_combo.findText(label, QtCore.Qt.MatchFlag.MatchFixedString) if hasattr(QtCore.Qt, "MatchFlag") else self.side_combo.findText(label)
        if idx >= 0:
            self.side_combo.setCurrentIndex(idx)
        else:
            self.side_combo.setCurrentIndex(2)
        self.config["side"] = self._resolve_dashboard_side()
        self.side_combo.currentTextChanged.connect(lambda _=None: self.config.__setitem__("side", self._resolve_dashboard_side()))
        g.addWidget(self.side_combo, 0, 1)

        g.addWidget(QtWidgets.QLabel("Position % of Balance:"), 0, 2)
        self.pospct_spin = QtWidgets.QDoubleSpinBox()
        self.pospct_spin.setRange(0.01, 100.0)
        self.pospct_spin.setDecimals(2)
        # Show as percentage 0..100; config can be 0..1 or 0..100
        initial_pct = float(self.config.get("position_pct", 2.0))
        if initial_pct <= 1.0:
            initial_pct *= 100.0
        self.pospct_spin.setValue(initial_pct)
        g.addWidget(self.pospct_spin, 0, 3)

        g.addWidget(QtWidgets.QLabel("Loop Interval Override:"), 0, 4)
        self.loop_edit = QtWidgets.QLineEdit()
        self.loop_edit.setPlaceholderText("Leave empty to use candle interval; e.g., 30s")
        g.addWidget(self.loop_edit, 0, 5)

        # Add-only (One-way guard) option
        self.cb_add_only = QtWidgets.QCheckBox("Add-only in current net direction (one-way)")
        self.cb_add_only.setChecked(bool(self.config.get('add_only', False)))
        g.addWidget(self.cb_add_only, 1, 0, 1, 6)

        self.cb_close_on_exit = QtWidgets.QCheckBox("Market Close All On Window Close")
        self.cb_close_on_exit.setChecked(bool(self.config.get('close_on_exit', False)))
        self.cb_close_on_exit.stateChanged.connect(self._on_close_on_exit_changed)
        g.addWidget(self.cb_close_on_exit, 2, 0, 1, 6)

        scroll_layout.addWidget(strat_group)

        # Indicators
        ind_group = QtWidgets.QGroupBox("Indicators")
        il = QtWidgets.QGridLayout(ind_group)

        self._indicator_runtime_controls = []
        row = 0
        for key, params in self.config['indicators'].items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty('indicator_key', key)
            cb.setChecked(bool(params.get("enabled", False)))
            def make_toggle_handler(_key=key):
                def _toggle(checked):
                    self._on_indicator_toggled(_key, checked)
                return _toggle
            cb.toggled.connect(make_toggle_handler())
            btn = QtWidgets.QPushButton("Params...")
            def make_handler(_key=key, _params=params):
                def handler():
                    dlg = ParamDialog(_key, _params, self, display_name=INDICATOR_DISPLAY_NAMES.get(_key, _key))
                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        self.config['indicators'][_key].update(dlg.get_params())
                        self.indicator_widgets[_key][0].setChecked(bool(self.config['indicators'][_key].get("enabled", False)))
                return handler
            btn.clicked.connect(make_handler())
            il.addWidget(cb, row, 0)
            il.addWidget(btn, row, 1)
            self.indicator_widgets[key] = (cb, btn)
            self._indicator_runtime_controls.extend([cb, btn])
            row += 1

        scroll_layout.addWidget(ind_group)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.clicked.connect(self.start_strategy)
        btn_layout.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(lambda checked=False: self.stop_strategy_async(close_positions=True))
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)
        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self.load_config)
        btn_layout.addWidget(self.load_btn)
        scroll_layout.addLayout(btn_layout)

        self._runtime_lock_widgets = [
            self.api_key_edit,
            self.api_secret_edit,
            self.mode_combo,
            self.theme_combo,
            self.account_combo,
            self.leverage_spin,
            self.margin_mode_combo,
            self.position_mode_combo,
            self.assets_mode_combo,
            self.tif_combo,
            self.gtd_minutes_spin,
            self.ind_source_combo,
            self.symbol_list,
            self.refresh_symbols_btn,
            self.interval_list,
            self.custom_interval_edit,
            self.add_interval_btn,
            self.use_backtest_intervals_btn,
            self.side_combo,
            self.pospct_spin,
            self.loop_edit,
            self.cb_add_only,
            self.cb_close_on_exit,
            self.start_btn,
            self.save_btn,
            self.load_btn
        ] + list(self._indicator_runtime_controls)
        self._set_runtime_controls_enabled(True)


        # Log
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(220)
        try:
            self.log_edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        try:
            self.log_edit.document().setMaximumBlockCount(1000)
        except Exception:
            pass
        scroll_layout.addWidget(self.log_edit)

        self.tabs.addTab(tab1, "Dashboard")

        if self.chart_enabled:
            chart_tab = self._create_chart_tab()
            self.tabs.addTab(chart_tab, "Chart")
            try:
                self._runtime_lock_widgets.extend([
                    self.chart_market_combo,
                    self.chart_symbol_combo,
                    self.chart_interval_combo,
                ])
                for widget in (self.chart_market_combo, self.chart_symbol_combo, self.chart_interval_combo):
                    self._register_runtime_active_exemption(widget)
            except Exception:
                pass
            if self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=False)
            elif QT_CHARTS_AVAILABLE:
                try:
                    self.load_chart(auto=True)
                except Exception:
                    pass
        else:
            self.chart_tab = None
            self.chart_view = None
        # Map symbol -> {'L': set(), 'S': set()} for intervals shown in Positions tab
        self._entry_intervals = {}
        self._entry_times = {}  # (sym, 'L'/'S') -> last trade time string
        self._entry_times_by_iv = {}
        self._open_position_records = {}
        self._closed_position_records = []
        self._engine_indicator_map = {}


        # ---------------- Positions tab ----------------
        tab2 = QtWidgets.QWidget()
        tab2_layout = QtWidgets.QVBoxLayout(tab2)

        ctrl_layout = QtWidgets.QHBoxLayout()
        self.refresh_pos_btn = QtWidgets.QPushButton("Refresh Positions")
        self.refresh_pos_btn.clicked.connect(self.refresh_positions)
        ctrl_layout.addWidget(self.refresh_pos_btn)
        self.close_all_btn = QtWidgets.QPushButton("Market Close ALL Positions")
        self.close_all_btn.clicked.connect(self.close_all_positions_async)
        ctrl_layout.addWidget(self.close_all_btn)
        ctrl_layout.addStretch()
        self.bot_status_label_tab2 = QtWidgets.QLabel()
        self.bot_status_label_tab2.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        ctrl_layout.addWidget(self.bot_status_label_tab2)
        tab2_layout.addLayout(ctrl_layout)
        self._sync_runtime_state()

        self.pos_table = QtWidgets.QTableWidget(0, 14, tab2)
        self.pos_table.setHorizontalHeaderLabels(["Symbol","Balance/Position","Last Price (USDT)","Size (USDT)","Margin Ratio","Margin (USDT)","PNL (ROI%)","Interval","Indicator","Side","Open Time","Close Time","Status","Close"])
        self.pos_table.horizontalHeader().setStretchLastSection(True)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        try:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tab2_layout.addWidget(self.pos_table)

        pos_btn_layout = QtWidgets.QHBoxLayout()
        self.pos_clear_selected_btn = QtWidgets.QPushButton("Clear Selected")
        self.pos_clear_selected_btn.clicked.connect(self._clear_positions_selected)
        pos_btn_layout.addWidget(self.pos_clear_selected_btn)
        self.pos_clear_all_btn = QtWidgets.QPushButton("Clear All")
        self.pos_clear_all_btn.clicked.connect(self._clear_positions_all)
        pos_btn_layout.addWidget(self.pos_clear_all_btn)
        pos_btn_layout.addStretch()
        tab2_layout.addLayout(pos_btn_layout)

        self.tabs.addTab(tab2, "Positions")

        # Background positions worker (keeps UI thread snappy)
        self._pos_thread = QtCore.QThread(self)
        self._pos_worker = _PositionsWorker(
            self.api_key_edit.text().strip(),
            self.api_secret_edit.text().strip(),
            self.mode_combo.currentText(),
            self.account_combo.currentText(),
        )
        # Wire thread-safe control signals
        self.req_pos_start.connect(self._pos_worker.start_with_interval)
        self.req_pos_stop.connect(self._pos_worker.stop_timer)
        self.req_pos_set_interval.connect(self._pos_worker.set_interval)
        self._pos_worker.moveToThread(self._pos_thread)
        self._pos_worker.positions_ready.connect(self._on_positions_ready)
        self._pos_worker.error.connect(lambda e: self.log(f"Positions worker: {e}"))
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass
        
        self._pos_thread.start()
        # adjust worker refresh interval
        try:
            self._apply_positions_refresh_settings()
        except Exception:
            pass

        # ---------------- Backtest tab ----------------
        tab3 = QtWidgets.QWidget()
        tab3_layout = QtWidgets.QVBoxLayout(tab3)

        top_layout = QtWidgets.QHBoxLayout()

        market_group = QtWidgets.QGroupBox("Markets")
        market_layout = QtWidgets.QGridLayout(market_group)

        market_layout.addWidget(QtWidgets.QLabel("Symbol Source:"), 0, 0)
        self.backtest_symbol_source_combo = QtWidgets.QComboBox()
        self.backtest_symbol_source_combo.addItems(["Futures", "Spot"])
        self.backtest_symbol_source_combo.currentTextChanged.connect(self._backtest_symbol_source_changed)
        market_layout.addWidget(self.backtest_symbol_source_combo, 0, 1)
        self.backtest_refresh_symbols_btn = QtWidgets.QPushButton("Refresh")
        self.backtest_refresh_symbols_btn.clicked.connect(self._refresh_backtest_symbols)
        market_layout.addWidget(self.backtest_refresh_symbols_btn, 0, 2)

        market_layout.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 1, 0, 1, 3)
        self.backtest_symbol_list = QtWidgets.QListWidget()
        self.backtest_symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_symbol_list.itemSelectionChanged.connect(self._backtest_store_symbols)
        market_layout.addWidget(self.backtest_symbol_list, 2, 0, 4, 3)

        market_layout.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 1, 3)
        self.backtest_interval_list = QtWidgets.QListWidget()
        self.backtest_interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_interval_list.itemSelectionChanged.connect(self._backtest_store_intervals)
        market_layout.addWidget(self.backtest_interval_list, 2, 3, 4, 2)
        pair_group = self._create_override_group("backtest", self.backtest_symbol_list, self.backtest_interval_list)
        market_layout.addWidget(pair_group, 6, 0, 1, 5)


        market_layout.setColumnStretch(0, 2)
        market_layout.setColumnStretch(1, 1)
        market_layout.setColumnStretch(2, 1)
        market_layout.setColumnStretch(3, 1)
        market_layout.setColumnStretch(4, 1)

        top_layout.addWidget(market_group)

        param_group = QtWidgets.QGroupBox("Backtest Parameters")
        param_form = QtWidgets.QFormLayout(param_group)

        self.backtest_start_edit = QtWidgets.QDateTimeEdit()
        self.backtest_start_edit.setCalendarPopup(True)
        self.backtest_start_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.backtest_end_edit = QtWidgets.QDateTimeEdit()
        self.backtest_end_edit.setCalendarPopup(True)
        self.backtest_end_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.backtest_start_edit.dateTimeChanged.connect(self._backtest_dates_changed)
        self.backtest_end_edit.dateTimeChanged.connect(self._backtest_dates_changed)

        param_form.addRow("Start Date/Time:", self.backtest_start_edit)
        param_form.addRow("End Date/Time:", self.backtest_end_edit)

        self.backtest_logic_combo = QtWidgets.QComboBox()
        self.backtest_logic_combo.addItems(["AND", "OR", "SEPARATE"])
        self.backtest_logic_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("logic", v))
        param_form.addRow("Signal Logic:", self.backtest_logic_combo)

        self.backtest_capital_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_capital_spin.setDecimals(2)
        self.backtest_capital_spin.setRange(1.0, 1_000_000_000.0)
        self.backtest_capital_spin.setSuffix(" USDT")
        self.backtest_capital_spin.valueChanged.connect(lambda v: self._update_backtest_config("capital", float(v)))
        param_form.addRow("Margin Capital:", self.backtest_capital_spin)

        self.backtest_pospct_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_pospct_spin.setDecimals(2)
        self.backtest_pospct_spin.setRange(0.01, 100.0)
        self.backtest_pospct_spin.setSuffix(" %")
        self.backtest_pospct_spin.valueChanged.connect(lambda v: self._update_backtest_config("position_pct", float(v)))
        param_form.addRow("Position % of Balance:", self.backtest_pospct_spin)

        self.backtest_side_combo = QtWidgets.QComboBox()
        self.backtest_side_combo.addItems([SIDE_LABELS["BUY"], SIDE_LABELS["SELL"], SIDE_LABELS["BOTH"]])
        self.backtest_side_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("side", v))
        param_form.addRow("Side:", self.backtest_side_combo)

        self.backtest_margin_mode_combo = QtWidgets.QComboBox()
        self.backtest_margin_mode_combo.addItems(["Isolated", "Cross"])
        self.backtest_margin_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("margin_mode", v))
        param_form.addRow("Margin Mode (Futures):", self.backtest_margin_mode_combo)

        self.backtest_position_mode_combo = QtWidgets.QComboBox()
        self.backtest_position_mode_combo.addItems(["Hedge", "One-way"])
        self.backtest_position_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("position_mode", v))
        param_form.addRow("Position Mode:", self.backtest_position_mode_combo)

        self.backtest_assets_mode_combo = QtWidgets.QComboBox()
        self.backtest_assets_mode_combo.addItems(["Single-Asset", "Multi-Assets"])
        self.backtest_assets_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("assets_mode", v))
        param_form.addRow("Assets Mode:", self.backtest_assets_mode_combo)

        self.backtest_leverage_spin = QtWidgets.QSpinBox()
        self.backtest_leverage_spin.setRange(1, 150)
        self.backtest_leverage_spin.valueChanged.connect(lambda v: self._update_backtest_config("leverage", int(v)))
        param_form.addRow("Leverage (Futures):", self.backtest_leverage_spin)

        self._backtest_futures_widgets = [
            self.backtest_margin_mode_combo,
            param_form.labelForField(self.backtest_margin_mode_combo),
            self.backtest_position_mode_combo,
            param_form.labelForField(self.backtest_position_mode_combo),
            self.backtest_assets_mode_combo,
            param_form.labelForField(self.backtest_assets_mode_combo),
            self.backtest_leverage_spin,
            param_form.labelForField(self.backtest_leverage_spin),
        ]

        top_layout.addWidget(param_group)

        indicator_group = QtWidgets.QGroupBox("Indicators")
        ind_layout = QtWidgets.QGridLayout(indicator_group)
        self.backtest_indicator_widgets.clear()
        row = 0
        for key, params in self.backtest_config.get("indicators", {}).items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty("indicator_key", key)
            cb.setChecked(bool(params.get("enabled", False)))
            cb.toggled.connect(lambda checked, _key=key: self._backtest_toggle_indicator(_key, checked))
            btn = QtWidgets.QPushButton("Params...")
            btn.clicked.connect(lambda _=False, _key=key: self._open_backtest_params(_key))
            ind_layout.addWidget(cb, row, 0)
            ind_layout.addWidget(btn, row, 1)
            self.backtest_indicator_widgets[key] = (cb, btn)
            row += 1
        top_layout.addWidget(indicator_group, stretch=1)

        tab3_layout.addLayout(top_layout)

        controls_layout = QtWidgets.QHBoxLayout()
        self.backtest_run_btn = QtWidgets.QPushButton("Run Backtest")
        self.backtest_run_btn.clicked.connect(self._run_backtest)
        controls_layout.addWidget(self.backtest_run_btn)
        self.backtest_stop_btn = QtWidgets.QPushButton("Stop")
        self.backtest_stop_btn.setEnabled(False)
        self.backtest_stop_btn.clicked.connect(self._stop_backtest)
        controls_layout.addWidget(self.backtest_stop_btn)
        self.backtest_status_label = QtWidgets.QLabel()
        controls_layout.addWidget(self.backtest_status_label)
        controls_layout.addStretch()
        self.bot_status_label_tab3 = QtWidgets.QLabel()
        self.bot_status_label_tab3.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addWidget(self.bot_status_label_tab3)
        tab3_layout.addLayout(controls_layout)
        self._update_bot_status()
        try:
            for widget in (self.backtest_run_btn, self.backtest_stop_btn):
                if widget and widget not in self._runtime_lock_widgets:
                    self._runtime_lock_widgets.append(widget)
                    self._register_runtime_active_exemption(widget)
        except Exception:
            pass

        self.backtest_results_table = QtWidgets.QTableWidget(0, 7)
        self.backtest_results_table.setHorizontalHeaderLabels(["Symbol", "Interval", "Logic", "Indicators", "Trades", "ROI (USDT)", "ROI (%)"])
        header = self.backtest_results_table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        except Exception:
            try:
                header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            except Exception:
                pass
        self.backtest_results_table.setSortingEnabled(True)
        try:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tab3_layout.addWidget(self.backtest_results_table)

        self.tabs.addTab(tab3, "Backtest")
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self._initialize_backtest_ui_defaults()


        

        self.resize(1200, 900)
        self.apply_theme(self.theme_combo.currentText())
        self._setup_log_buffer()
        try:
            self.ind_source_combo.currentTextChanged.connect(lambda v: self.config.__setitem__("indicator_source", v))
        except Exception:
            pass

    
    

def _gui_on_positions_ready(self, rows: list, acct: str):
    try:
        try:
            rows = sorted(rows, key=lambda r: (str(r.get('symbol') or ''), str(r.get('side_key') or '')))
        except Exception:
            rows = rows or []

        positions_map: dict[tuple, dict] = {}
        base_rows = rows or []
        for r in base_rows:
            try:
                sym = r.get('symbol')
                side_key = r.get('side_key') or 'SPOT'
                if not sym:
                    continue
                positions_map[(sym, side_key)] = {
                    'symbol': sym,
                    'side_key': side_key,
                    'entry_tf': r.get('entry_tf'),
                    'open_time': r.get('open_time'),
                    'close_time': '-',
                    'status': 'Active',
                    'data': dict(r),
                    'indicators': self._collect_strategy_indicators(sym, side_key),
                }
            except Exception:
                continue

        acct_upper = str(acct or '').upper()
        if acct_upper.startswith('FUT'):
            try:
                worker = getattr(self, '_pos_worker', None)
                bw = getattr(worker, '_wrapper', None) if worker else None
                if worker and bw is None:
                    try:
                        worker._ensure_wrapper()
                        bw = getattr(worker, '_wrapper', None)
                    except Exception:
                        bw = None
                if bw is None:
                    bw = getattr(self, 'shared_binance', None)
                if bw is None:
                    bw = BinanceWrapper(
                        self.api_key_edit.text().strip(),
                        self.api_secret_edit.text().strip(),
                        mode=self.mode_combo.currentText(),
                        account_type=self.account_combo.currentText(),
                    )
                raw = bw.list_open_futures_positions() or []
                syms_filter = None
                try:
                    selected = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count()) if self.symbol_list.item(i).isSelected()]
                    if selected:
                        syms_filter = set(selected)
                except Exception:
                    syms_filter = None
                for p in raw:
                    try:
                        sym = str(p.get('symbol'))
                        if syms_filter and sym not in syms_filter:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        mark = float(p.get('markPrice') or 0.0)
                        value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        margin_usdt = float(p.get('isolatedWallet') or p.get('initialMargin') or 0.0)
                        pnl = float(p.get('unRealizedProfit') or 0.0)
                        margin_ratio = normalize_margin_ratio(p.get('marginRatio') or p.get('margin_ratio'))
                        if margin_ratio <= 0.0 and margin_usdt > 0:
                            try:
                                maint = float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0)
                            except Exception:
                                maint = 0.0
                            unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                            margin_balance = margin_usdt + (pnl if pnl > 0 else 0.0)
                            denom = margin_balance if margin_balance > 0.0 else margin_usdt
                            if denom > 0.0:
                                margin_ratio = ((maint + unrealized_loss) / denom) * 100.0
                        roi_pct = 0.0
                        if margin_usdt > 0:
                            try:
                                roi_pct = (pnl / margin_usdt) * 100.0
                            except Exception:
                                roi_pct = 0.0
                            pnl_roi = f"{pnl:+.2f} USDT ({roi_pct:+.2f}%)"
                        else:
                            pnl_roi = f"{pnl:+.2f} USDT"
                        try:
                            update_time = int(float(p.get('updateTime') or p.get('update_time') or 0))
                        except Exception:
                            update_time = 0
                        data = {
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'size_usdt': value,
                            'margin_usdt': margin_usdt,
                            'margin_ratio': margin_ratio,
                            'pnl_roi': pnl_roi,
                            'pnl_value': pnl,
                            'roi_percent': roi_pct,
                            'side_key': side_key,
                            'update_time': update_time,
                        }
                        rec = positions_map.get((sym, side_key))
                        if rec is None:
                            rec = {
                                'symbol': sym,
                                'side_key': side_key,
                                'entry_tf': '-',
                                'open_time': '-',
                                'close_time': '-',
                                'status': 'Active',
                            }
                        else:
                            rec = dict(rec)
                        rec['data'] = data
                        rec['status'] = 'Active'
                        rec['close_time'] = '-'
                        entry_times_map = getattr(self, '_entry_times_by_iv', {}) or {}
                        intervals = set()
                        try:
                            for (sym_key, side_key_key, iv_key), ts in entry_times_map.items():
                                if sym_key == sym and side_key_key == side_key and ts and iv_key:
                                    iv_norm = str(iv_key).strip().lower()
                                    if iv_norm:
                                        intervals.add(iv_norm)
                        except Exception:
                            pass
                        if not intervals:
                            intervals = {str(iv).strip().lower() for iv in (self._entry_intervals.get(sym, {}) or {}).get(side_key, set()) if str(iv).strip()}
                        if intervals:
                            rec['entry_tf'] = ', '.join(sorted(intervals, key=_mw_interval_sort_key))
                        else:
                            rec['entry_tf'] = '-'
                        open_times = []
                        for iv in intervals:
                            ts = entry_times_map.get((sym, side_key, iv))
                            dt_obj = self._parse_any_datetime(ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times:
                            base_ts = getattr(self, '_entry_times', {}).get((sym, side_key)) if hasattr(self, '_entry_times') else None
                            dt_obj = self._parse_any_datetime(base_ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times and data.get('update_time'):
                            dt_obj = self._parse_any_datetime(data.get('update_time'))
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if open_times:
                            open_times.sort(key=lambda item: item[0])
                            rec['open_time'] = self._format_display_time(open_times[0][1])
                        rec['indicators'] = self._collect_strategy_indicators(sym, side_key)
                        positions_map[(sym, side_key)] = rec
                    except Exception:
                        continue
            except Exception:
                pass

        self._update_position_history(positions_map)
        self._render_positions_table()
    except Exception as e:
        self.log(f"Positions render failed: {e}")


def _mw_update_position_history(self, positions_map: dict):
    try:
        if not hasattr(self, "_open_position_records"):
            self._open_position_records = {}
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        prev_records = getattr(self, "_open_position_records", {}) or {}
        closed_keys = [key for key in prev_records if key not in positions_map]
        if closed_keys:
            from datetime import datetime as _dt
            now_fmt = self._format_display_time(_dt.now().astimezone())
            for key in closed_keys:
                rec = prev_records.get(key)
                if not rec:
                    continue
                snap = copy.deepcopy(rec)
                snap["status"] = "Closed"
                snap["close_time"] = now_fmt
                self._closed_position_records.insert(0, snap)
            if len(self._closed_position_records) > MAX_CLOSED_HISTORY:
                self._closed_position_records = self._closed_position_records[:MAX_CLOSED_HISTORY]
        self._open_position_records = positions_map
    except Exception:
        pass


def _mw_render_positions_table(self):
    try:
        open_records = getattr(self, "_open_position_records", {}) or {}
        closed_records = getattr(self, "_closed_position_records", []) or []
        display_records = sorted(open_records.values(), key=lambda d: (d['symbol'], d.get('side_key'), d.get('entry_tf'))) + list(closed_records)
        self.pos_table.setRowCount(0)
        for rec in display_records:
            try:
                data = rec.get('data', {}) or {}
                sym = rec.get('symbol')
                side_key = rec.get('side_key')
                interval = rec.get('entry_tf') or '-'
                row = self.pos_table.rowCount()
                self.pos_table.insertRow(row)

                qty_show = float(data.get('qty') or 0.0)
                mark = float(data.get('mark') or 0.0)
                size_usdt = float(data.get('size_usdt') or (qty_show * mark))
                mr = normalize_margin_ratio(data.get('margin_ratio'))
                margin_usdt = float(data.get('margin_usdt') or 0.0)
                pnl_roi = data.get('pnl_roi')
                side_text = 'Long' if side_key == 'L' else ('Short' if side_key == 'S' else 'Spot')
                open_time = rec.get('open_time') or '-'
                close_time = rec.get('close_time') if rec.get('status') == 'Closed' else '-'
                status_txt = rec.get('status', 'Active')

                self.pos_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))

                qty_item = _NumericItem(f"{qty_show:.8f}", qty_show)
                self.pos_table.setItem(row, 1, qty_item)

                mark_item = _NumericItem(f"{mark:.8f}" if mark else "-", mark)
                self.pos_table.setItem(row, 2, mark_item)

                size_item = _NumericItem(f"{size_usdt:.2f}", size_usdt)
                self.pos_table.setItem(row, 3, size_item)

                mr_display = f"{mr:.2f}%" if mr > 0 else "-"
                mr_item = _NumericItem(mr_display, mr)
                self.pos_table.setItem(row, 4, mr_item)

                margin_item = _NumericItem(f"{margin_usdt:.2f} USDT" if margin_usdt else "-", margin_usdt)
                self.pos_table.setItem(row, 5, margin_item)

                pnl_item = _NumericItem(str(pnl_roi or "-"), float(data.get('pnl_value') or 0.0))
                self.pos_table.setItem(row, 6, pnl_item)
                self.pos_table.setItem(row, 7, QtWidgets.QTableWidgetItem(interval or '-'))
                indicators_raw = rec.get('indicators')
                indicators_display = '-'
                if isinstance(indicators_raw, (list, tuple)):
                    indicators_display = _format_indicator_list(indicators_raw) or '-'
                elif isinstance(indicators_raw, str) and indicators_raw.strip():
                    indicators_display = indicators_raw.strip()
                self.pos_table.setItem(row, 8, QtWidgets.QTableWidgetItem(indicators_display))
                self.pos_table.setItem(row, 9, QtWidgets.QTableWidgetItem(side_text))
                self.pos_table.setItem(row, 10, QtWidgets.QTableWidgetItem(str(open_time or '-')))
                self.pos_table.setItem(row, 11, QtWidgets.QTableWidgetItem(str(close_time or '-')))
                self.pos_table.setItem(row, 12, QtWidgets.QTableWidgetItem(status_txt))
                btn = self._make_close_btn(sym, side_key, interval, qty_show)
                if status_txt != 'Active':
                    btn.setEnabled(False)
                self.pos_table.setCellWidget(row, 13, btn)
            except Exception:
                pass
        try:
            if getattr(self, "chart_enabled", False) and getattr(self, "chart_auto_follow", False) and not getattr(self, "_chart_manual_override", False):
                self._sync_chart_to_active_positions()
        except Exception:
            pass
    except Exception as exc:
        try:
            self.log(f"Positions table update failed: {exc}")
        except Exception:
            pass


def _mw_clear_positions_selected(self):
    try:
        table = getattr(self, "pos_table", None)
        if table is None:
            return
        sel_model = table.selectionModel()
        if sel_model is None:
            return
        rows = sorted({index.row() for index in sel_model.selectedRows()}, reverse=True)
        if not rows:
            return
        closed_records = list(getattr(self, "_closed_position_records", []) or [])
        changed = False
        skipped_active = False
        for row in rows:
            status_item = table.item(row, 12)
            status = (status_item.text().strip().upper() if status_item else "")
            if status != "CLOSED":
                skipped_active = True
                continue
            symbol_item = table.item(row, 0)
            side_item = table.item(row, 9)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            side_txt = (side_item.text().strip().upper() if side_item else "")
            side_key = None
            if "LONG" in side_txt or side_txt == "BUY":
                side_key = "L"
            elif "SHORT" in side_txt or side_txt == "SELL":
                side_key = "S"
            remove_idx = None
            for idx, rec in enumerate(closed_records):
                rec_sym = str(rec.get('symbol') or '').strip().upper()
                rec_side = str(rec.get('side_key') or '').strip().upper()
                if rec_sym == symbol and (side_key is None or not rec_side or rec_side == side_key):
                    remove_idx = idx
                    break
            if remove_idx is not None:
                closed_records.pop(remove_idx)
                changed = True
        if changed:
            self._closed_position_records = closed_records
            self._render_positions_table()
        if skipped_active:
            try:
                self.log("Positions: only closed history rows can be cleared.")
            except Exception:
                pass
    except Exception:
        pass


def _mw_clear_positions_all(self):
    try:
        if hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        self._render_positions_table()
    except Exception:
        pass


def _mw_snapshot_closed_position(self, symbol: str, side_key: str) -> bool:
    try:
        if not symbol or side_key not in ("L", "S"):
            return False
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        open_records = getattr(self, "_open_position_records", {}) or {}
        rec = open_records.get((symbol, side_key))
        if not rec:
            return False
        from datetime import datetime as _dt
        snap = copy.deepcopy(rec)
        snap['status'] = 'Closed'
        snap['close_time'] = self._format_display_time(_dt.now().astimezone())
        self._closed_position_records.insert(0, snap)
        if len(self._closed_position_records) > MAX_CLOSED_HISTORY:
            self._closed_position_records = self._closed_position_records[:MAX_CLOSED_HISTORY]
        try:
            open_records.pop((symbol, side_key), None)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _mw_sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get('status', 'Active')).upper() != 'ACTIVE':
                    continue
                sym = str(rec.get('symbol') or '').strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass


def _mw_make_close_btn(self, symbol: str, side_key: str | None = None, interval: str | None = None, qty: float | None = None):
    label = "Close"
    if side_key == "L":
        label = "Close Long"
    elif side_key == "S":
        label = "Close Short"
    btn = QtWidgets.QPushButton(label)
    tooltip_bits = []
    if side_key == "L":
        tooltip_bits.append("Closes the long leg")
    elif side_key == "S":
        tooltip_bits.append("Closes the short leg")
    if interval and interval not in ("-", "SPOT"):
        tooltip_bits.append(f"Interval {interval}")
    if qty and qty > 0:
        try:
            tooltip_bits.append(f"Qty ~= {qty:.6f}")
        except Exception:
            pass
    if tooltip_bits:
        btn.setToolTip(" | ".join(tooltip_bits))
    btn.setEnabled(side_key in ("L", "S"))
    interval_key = interval if interval not in ("-", "SPOT") else None
    btn.clicked.connect(lambda _, s=symbol, sk=side_key, iv=interval_key, q=qty: self._close_position_single(s, sk, iv, q))
    return btn


def _mw_close_position_single(self, symbol: str, side_key: str | None, interval: str | None, qty: float | None):
    if not symbol:
        return
    try:
        from ..workers import CallWorker as _CallWorker
    except Exception as exc:
        try:
            self.log(f"Close {symbol} setup error: {exc}")
        except Exception:
            pass
        return
    if side_key not in ("L", "S"):
        try:
            self.log(f"{symbol}: manual close is only available for futures legs.")
        except Exception:
            pass
        return
    if getattr(self, "shared_binance", None) is None:
        try:
            self.shared_binance = BinanceWrapper(
                self.api_key_edit.text().strip(),
                self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
            )
        except Exception as exc:
            try:
                self.log(f"Close {symbol} setup error: {exc}")
            except Exception:
                pass
            return
    account = (self.account_combo.currentText() or "").upper()
    try:
        qty_val = float(qty or 0.0)
    except Exception:
        qty_val = 0.0

    def _do():
        bw = self.shared_binance
        if account.startswith("FUT"):
            if side_key in ("L", "S") and qty_val > 0:
                try:
                    dual = bool(bw.get_futures_dual_side())
                except Exception:
                    dual = False
                order_side = "SELL" if side_key == "L" else "BUY"
                pos_side = None
                if dual:
                    pos_side = "LONG" if side_key == "L" else "SHORT"
                return bw.close_futures_leg_exact(symbol, qty_val, side=order_side, position_side=pos_side)
            return bw.close_futures_position(symbol)
        return {"ok": False, "error": "Spot manual close via UI is not available yet"}

    def _done(res, err):
        succeeded = False
        try:
            if err:
                self.log(f"Close {symbol} error: {err}")
            else:
                self.log(f"Close {symbol} result: {res}")
                succeeded = isinstance(res, dict) and res.get("ok")
            if succeeded and interval and side_key in ("L", "S"):
                try:
                    self._entry_intervals.setdefault(symbol, {"L": set(), "S": set()}).setdefault(side_key, set()).discard(interval)
                except Exception:
                    pass
                try:
                    self._entry_times_by_iv.pop((symbol, side_key, interval), None)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.refresh_positions(symbols=[symbol])
        except Exception:
            pass

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)
    worker.finished.connect(_cleanup)
    worker.start()


def on_leverage_changed(self, value):
    try:
        value_int = int(value)
    except Exception:
        value_int = 0
    try:
        self.config['leverage'] = value_int
    except Exception:
        pass
    try:
        if value_int > 0 and hasattr(self, 'shared_binance') and self.shared_binance and (self.account_combo.currentText() or '').upper().startswith('FUT'):
            self.shared_binance.set_futures_leverage(value_int)
    except Exception:
        pass


def refresh_symbols(self):
    from ..workers import CallWorker as _CallWorker
    self.refresh_symbols_btn.setEnabled(False)
    self.refresh_symbols_btn.setText("Refreshing...")
    def _do():
        tmp_wrapper = BinanceWrapper(self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                                     mode=self.mode_combo.currentText(),
                                     account_type=self.account_combo.currentText())
        syms = tmp_wrapper.fetch_symbols(sort_by_volume=True)
        return syms
    def _done(res, err):
        try:
            if err or not res:
                self.log(f"Failed to refresh symbols: {err or 'no symbols'}")
                return
            self.symbol_list.clear()
            all_symbols = []
            filtered = []
            seen = set()
            for sym in res or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm or sym_norm in seen:
                    continue
                seen.add(sym_norm)
                all_symbols.append(sym_norm)
                if sym_norm.endswith("USDT"):
                    filtered.append(sym_norm)
            if filtered:
                self.symbol_list.addItems(filtered)
            if all_symbols:
                self.chart_symbol_cache["Futures"] = all_symbols
            current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
            if current_market == "Futures":
                self._update_chart_symbol_options(all_symbols if all_symbols else filtered)
                self._chart_needs_render = True
                if self.chart_auto_follow and not self._chart_manual_override:
                    self._apply_dashboard_selection_to_chart(load=True)
                elif self._chart_pending_initial_load or self._is_chart_visible():
                    self.load_chart(auto=True)
            self.log(f"Loaded {self.symbol_list.count()} USDT-pair symbols for {self.account_combo.currentText()}.")
        finally:
            self.refresh_symbols_btn.setEnabled(True)
            self.refresh_symbols_btn.setText("Refresh Symbols")
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()

def apply_futures_modes(self):
    from ..workers import CallWorker as _CallWorker
    mm = self.margin_mode_combo.currentText().upper()
    pos_mode = self.position_mode_combo.currentText()
    hedge = (pos_mode.strip().lower() == 'hedge')
    assets_mode = self.assets_mode_combo.currentText()
    multi = (assets_mode.strip().lower() == 'multi-assets')
    tif = self.tif_combo.currentText()
    gtdm = int(self.gtd_minutes_spin.value())
    def _do():
        try:
            self.shared_binance.set_position_mode(hedge)
        except Exception:
            pass
        try:
            self.shared_binance.set_multi_assets_mode(multi)
        except Exception:
            pass
        return True
    def _done(res, err):
        if err:
            self.log(f"Apply futures modes error: {err}")
            return
        self.config['margin_mode'] = 'Isolated' if mm == 'ISOLATED' else 'Cross'
        self.config['position_mode'] = 'Hedge' if hedge else 'One-way'
        self.config['assets_mode'] = 'Multi-Assets' if multi else 'Single-Asset'
        self.config['tif'] = tif
        self.config['gtd_minutes'] = gtdm
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()


def start_strategy(self):
    started = 0
    try:
        raw_override = (self.loop_edit.text().strip() if hasattr(self, 'loop_edit') else '')
        loop_override = re.sub(r'\s+', '', raw_override.lower()) if raw_override else None
        if loop_override and not re.match(r'^\d+(s|m|h|d|w)?$', loop_override):
            self.log(f"Invalid loop interval override: {raw_override}. Use formats like '10s', '2m', '1h'. Ignoring.")
            loop_override = None

        runtime_ctx = self._override_ctx("runtime")
        account_type_text = (self.account_combo.currentText() or "Futures").strip()
        pair_entries = []
        table = runtime_ctx.get("table") if runtime_ctx else None
        if table is not None:
            try:
                selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
            except Exception:
                selected_rows = []
            if selected_rows:
                for row in selected_rows:
                    sym_item = table.item(row, 0)
                    iv_item = table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ''
                    iv_raw = iv_item.text().strip() if iv_item else ''
                    iv_canonical = self._canonicalize_interval(iv_raw)
                    if sym and iv_canonical:
                        entry_obj = None
                        try:
                            entry_obj = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                        except Exception:
                            entry_obj = None
                        indicators = None
                        if isinstance(entry_obj, dict):
                            indicators = entry_obj.get("indicators")
                            if isinstance(indicators, (list, tuple)):
                                indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
                            else:
                                indicators = None
                        pair_entries.append({
                            "symbol": sym,
                            "interval": iv_canonical,
                            "indicators": list(indicators) if indicators else None,
                        })
                    elif sym and iv_raw:
                        self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")
        if not pair_entries:
            for entry in self.config.get("runtime_symbol_interval_pairs", []) or []:
                sym = str((entry or {}).get('symbol') or '').strip().upper()
                interval_val = str((entry or {}).get('interval') or '').strip()
                iv_canonical = self._canonicalize_interval(interval_val)
                if not (sym and iv_canonical):
                    if sym and interval_val:
                        self.log(f"Skipping unsupported interval '{interval_val}' for {account_type_text} {sym}.")
                    continue
                indicators = entry.get("indicators")
                if isinstance(indicators, (list, tuple)):
                    indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
                else:
                    indicators = None
                pair_entries.append({
                    "symbol": sym,
                    "interval": iv_canonical,
                    "indicators": list(indicators) if indicators else None,
                })
        syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())
                if self.symbol_list.item(i).isSelected()]
        if not syms and self.symbol_list.count():
            syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())]

        ivs = [self.interval_list.item(i).text() for i in range(self.interval_list.count())
               if self.interval_list.item(i).isSelected()]
        if not ivs:
            ivs = ["1m"]

        if pair_entries:
            combos_source = pair_entries
        else:
            if not syms:
                self.log("No symbols available. Click Refresh Symbols.")
                return
            current_indicators = self._get_selected_indicator_keys("runtime")
            indicator_value = sorted({str(k).strip() for k in current_indicators if str(k).strip()}) if current_indicators else None
            combos_source = []
            for sym in syms:
                for iv in ivs:
                    iv_canonical = self._canonicalize_interval(iv)
                    if not iv_canonical:
                        self.log(f"Skipping unsupported interval '{iv}' for {account_type_text} {sym}.")
                        continue
                    combos_source.append({
                        "symbol": sym,
                        "interval": iv_canonical,
                        "indicators": list(indicator_value) if indicator_value else None,
                    })

        combos = []
        seen_combo = set()
        for entry in combos_source:
            sym = str(entry.get("symbol") or "").strip().upper()
            iv_raw = str(entry.get("interval") or "").strip()
            iv = self._canonicalize_interval(iv_raw)
            if not sym or not iv:
                if sym and iv_raw:
                    self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")
                continue
            indicators = entry.get("indicators")
            if isinstance(indicators, (list, tuple)):
                indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
            else:
                indicators = []
            key = (sym, iv, tuple(indicators))
            if key in seen_combo:
                continue
            seen_combo.add(key)
            item = {"symbol": sym, "interval": iv}
            if indicators:
                item["indicators"] = indicators
            combos.append(item)
        total_jobs = len(combos)
        concurrency = StrategyEngine.concurrent_limit()
        if total_jobs > concurrency:
            self.log(f"{total_jobs} symbol/interval loops requested; limiting concurrent execution to {concurrency} to keep the UI responsive.")

        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = BinanceWrapper(
                self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(), account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
            )

        if not hasattr(self, "strategy_engines"):
            self.strategy_engines = {}

        for combo in combos:
            sym = combo.get("symbol")
            iv = combo.get("interval")
            if not sym or not iv:
                continue
            indicator_override = combo.get("indicators")
            indicator_list = []
            if isinstance(indicator_override, (list, tuple)):
                indicator_list = [str(k).strip() for k in indicator_override if str(k).strip()]
            elif indicator_override:
                indicator_list = [str(indicator_override).strip()]
            key = _make_engine_key(sym, iv, indicator_list)
            try:
                if key in self.strategy_engines and getattr(self.strategy_engines[key], "is_alive", lambda: False)():
                    self.log(f"Engine already running for {key}, skipping.")
                    continue

                cfg = copy.deepcopy(self.config)
                cfg.update({
                    "symbol": sym,
                    "interval": iv,
                    "position_pct": float(self.pospct_spin.value() or self.config.get("position_pct", 100.0)),
                    "side": self._resolve_dashboard_side(),
                })
                indicators_cfg = cfg.get("indicators", {}) or {}
                if indicator_list:
                    indicator_set = set(indicator_list)
                    if isinstance(indicators_cfg, dict):
                        for ind_key, params in indicators_cfg.items():
                            try:
                                params['enabled'] = ind_key in indicator_set
                            except Exception:
                                try:
                                    indicators_cfg[ind_key] = dict(params)
                                    indicators_cfg[ind_key]['enabled'] = ind_key in indicator_set
                                except Exception:
                                    pass
                active_indicators = []
                try:
                    active_indicators = [
                        ind_key
                        for ind_key, params in indicators_cfg.items()
                        if isinstance(params, dict) and params.get("enabled")
                    ]
                except Exception:
                    active_indicators = []
                if not active_indicators:
                    if indicator_list:
                        active_indicators = list(indicator_list)
                    else:
                        active_indicators = self._get_selected_indicator_keys("runtime")
                active_indicators = sorted({str(k).strip() for k in (active_indicators or []) if str(k).strip()})
                eng = StrategyEngine(self.shared_binance, cfg, log_callback=self.log,
                                     trade_callback=self._on_trade_signal,
                                     loop_interval_override=loop_override)
                eng.start()
                self.strategy_engines[key] = eng
                try:
                    self._engine_indicator_map[key] = {
                        "symbol": sym,
                        "interval": iv,
                        "side": cfg.get("side", "BOTH"),
                        "indicators": active_indicators,
                    }
                except Exception:
                    pass
                indicator_note = ""
                if active_indicators:
                    indicator_note = f" (Indicators: {_format_indicator_list(active_indicators)})"
                self.log(f"Loop start for {key}{indicator_note}.")
                started += 1
            except Exception as e:
                self.log(f"Failed to start engine for {key}: {e}")

        if started == 0:
            self.log("No new engines started (already running?)")
    except Exception as e:
        try:
            self.log(f"Start error: {e}")
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass


def stop_strategy_async(self, close_positions: bool = True, blocking: bool = False):
    """Stop all StrategyEngine threads and then market-close ALL active positions asynchronously."""
    try:
        if hasattr(self, "strategy_engines") and self.strategy_engines:
            for key, eng in list(self.strategy_engines.items()):
                try:
                    eng.stop()
                except Exception:
                    pass
            try:
                import time as _t; _t.sleep(0.05)
            except Exception:
                pass
            self.strategy_engines.clear()
            try:
                self._engine_indicator_map.clear()
            except Exception:
                pass
            self.log("Stopped all strategy engines.")
        else:
            self.log("No engines to stop.")
        try:
            if close_positions:
                if blocking:
                    self._close_all_positions_blocking()
                else:
                    self.close_all_positions_async()
        except Exception as e:
            try:
                self.log(f"Failed to trigger close-all: {e}")
            except Exception:
                pass
    except Exception as e:
        try:
            self.log(f"Stop error: {e}")
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass


def save_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
        dlg = QtWidgets.QFileDialog(self)
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dlg.setNameFilter("JSON Files (*.json)")
        dlg.setDefaultSuffix("json")
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            fn = dlg.selectedFiles()[0]
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.log(f"Saved config to {fn}")
    except Exception as e:
        try:
            self.log(f"Save config error: {e}")
        except Exception:
            pass


def load_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json)")
        if not fn:
            return
        with open(fn, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            self.config.update(cfg)
        chart_cfg = self.config.get("chart")
        if not isinstance(chart_cfg, dict):
            chart_cfg = {}
        self.config["chart"] = chart_cfg
        self.chart_config = chart_cfg
        if getattr(self, "chart_enabled", False):
            self.chart_config.setdefault("auto_follow", True)
            self.chart_auto_follow = bool(self.chart_config.get("auto_follow", True))
            self._restore_chart_controls_from_config()
            current_market_text = self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else "Futures"
            self._chart_needs_render = True
            self._on_chart_market_changed(current_market_text)
            if self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=True)
            elif QT_CHARTS_AVAILABLE:
                try:
                    if self._is_chart_visible() or self._chart_pending_initial_load:
                        self.load_chart(auto=True)
                except Exception:
                    pass
        self.config.setdefault('runtime_symbol_interval_pairs', [])
        self.config.setdefault('backtest_symbol_interval_pairs', [])
        self.backtest_config.setdefault('backtest_symbol_interval_pairs', list(self.config.get('backtest_symbol_interval_pairs', [])))
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self.log(f"Loaded config from {fn}")
        try:
            self.leverage_spin.setValue(int(self.config.get("leverage", self.leverage_spin.value())))
            self.margin_mode_combo.setCurrentText(self.config.get("margin_mode", self.margin_mode_combo.currentText()))
            self.position_mode_combo.setCurrentText(self.config.get("position_mode", self.position_mode_combo.currentText()))
            self.assets_mode_combo.setCurrentText(self.config.get("assets_mode", self.assets_mode_combo.currentText()))
            self.tif_combo.setCurrentText(self.config.get("tif", self.tif_combo.currentText()))
            self.gtd_minutes_spin.setValue(int(self.config.get("gtd_minutes", self.gtd_minutes_spin.value())))
        except Exception:
            pass
    except Exception as e:
        try:
            self.log(f"Load config error: {e}")
        except Exception:
            pass

def refresh_positions(self, symbols=None, *args, **kwargs):
    """Manual refresh of positions: reconfigure worker and trigger an immediate tick."""
    try:
        try:
            self._reconfigure_positions_worker(symbols=symbols)
        except Exception:
            pass
        try:
            self.req_pos_start.emit(5000)
        except Exception:
            pass
        self.log("Positions refresh requested.")
    except Exception as e:
        try:
            self.log(f"Refresh positions error: {e}")
        except Exception:
            pass

try:
    MainWindow.start_strategy = start_strategy
except Exception:
    pass
try:
    MainWindow.stop_strategy_async = stop_strategy_async
except Exception:
    pass
try:
    MainWindow.save_config = save_config
    MainWindow.load_config = load_config
except Exception:
    pass
try:
    MainWindow.refresh_symbols = refresh_symbols
except Exception:
    pass
try:
    MainWindow.apply_futures_modes = apply_futures_modes
except Exception:
    pass
try:
    MainWindow.on_leverage_changed = on_leverage_changed
except Exception:
    pass
try:
    MainWindow.refresh_positions = refresh_positions
except Exception:
    pass

def _close_all_positions_sync(self):
    from ..close_all import close_all_futures_positions as _close_all_futures
    if getattr(self, "shared_binance", None) is None:
        self.shared_binance = BinanceWrapper(
            self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(), account_type=self.account_combo.currentText(),
            default_leverage=int(self.leverage_spin.value() or 1),
            default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
        )
    acct_text = (self.account_combo.currentText() or '').upper()
    if acct_text.startswith('FUT'):
        return _close_all_futures(self.shared_binance)
    return self.shared_binance.close_all_spot_positions()

def _handle_close_all_result(self, res):
    try:
        details = res or []
        for r in details:
            sym = r.get('symbol') or '?'
            if not r.get('ok'):
                self.log(f"Close-all {sym}: error -> {r.get('error')}")
            elif r.get('skipped'):
                self.log(f"Close-all {sym}: skipped ({r.get('reason')})")
            else:
                self.log(f"Close-all {sym}: ok")
        n_ok = sum(1 for r in details if r.get('ok'))
        n_all = len(details)
        self.log(f"Close-all completed: {n_ok}/{n_all} ok.")
    except Exception:
        self.log(f"Close-all result: {res}")
    try:
        self.refresh_positions()
    except Exception:
        pass
    try:
        self.trigger_positions_refresh()
    except Exception:
        pass

def _close_all_positions_blocking(self):
    try:
        result = _close_all_positions_sync(self)
        _handle_close_all_result(self, result)
    except Exception as e:
        self.log(f"Close-all error: {e}")

def close_all_positions_async(self):
    """Close all open futures positions using reduce-only market orders in a worker."""
    try:
        from ..workers import CallWorker as _CallWorker
        def _do():
            return _close_all_positions_sync(self)
        def _done(res, err):
            if err:
                self.log(f"Close-all error: {err}")
                return
            _handle_close_all_result(self, res)
        w = _CallWorker(_do, parent=self)
        try:
            w.progress.connect(self.log)
        except Exception:
            pass
        w.done.connect(_done)
        w.start()
    except Exception as e:
        try:
            self.log(f"Close-all setup error: {e}")
        except Exception:
            pass

try:
    MainWindow.close_all_positions_async = close_all_positions_async
    MainWindow._close_all_positions_sync = _close_all_positions_sync
    MainWindow._close_all_positions_blocking = _close_all_positions_blocking
    MainWindow._handle_close_all_result = _handle_close_all_result
except Exception:
    pass


def update_balance_label(self):
    """Refresh the 'Total USDT balance' label safely after an order."""
    btn = getattr(self, "refresh_balance_btn", None)
    old_btn_text = btn.text() if btn else None
    try:
        if btn:
            btn.setEnabled(False)
            btn.setText("Refreshing...")
        try:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("Refreshing...")
        except Exception:
            pass

        if getattr(self, "shared_binance", None) is None:
            api_key = ""
            api_secret = ""
            try:
                if hasattr(self, "api_key_edit"):
                    api_key = (self.api_key_edit.text() or "").strip()
                if hasattr(self, "api_secret_edit"):
                    api_secret = (self.api_secret_edit.text() or "").strip()
            except Exception:
                api_key = api_key or ""
                api_secret = api_secret or ""

            if not api_key or not api_secret:
                try:
                    if getattr(self, "balance_label", None):
                        self.balance_label.setText("API credentials missing")
                except Exception:
                    pass
                return

            try:
                default_leverage = int(self.leverage_spin.value() or 1)
            except Exception:
                default_leverage = 1
            default_margin_mode = "Isolated"
            try:
                default_margin_mode = self.margin_mode_combo.currentText() or "Isolated"
            except Exception:
                pass
            try:
                self.shared_binance = BinanceWrapper(
                    api_key,
                    api_secret,
                    mode=getattr(self.mode_combo, "currentText", lambda: "Live")(),
                    account_type=getattr(self.account_combo, "currentText", lambda: "Futures")(),
                    default_leverage=default_leverage,
                    default_margin_mode=default_margin_mode,
                )
            except Exception as exc:
                try:
                    if getattr(self, "balance_label", None):
                        self.balance_label.setText("Balance error")
                    self.log(f"Balance setup error: {exc}")
                except Exception:
                    pass
                return

        bal = 0.0
        try:
            account_text = (self.account_combo.currentText() or "").upper()
        except Exception:
            account_text = ""
        try:
            if account_text.startswith("FUT"):
                bal = float(self.shared_binance.get_futures_balance_usdt() or 0.0)
            else:
                bal = float(self.shared_binance.get_spot_balance("USDT") or 0.0)
        except Exception as exc:
            try:
                self.log(f"Balance fetch error: {exc}")
            except Exception:
                pass

        try:
            if getattr(self, "balance_label", None):
                self.balance_label.setText(f"{bal:.3f} USDT")
        except Exception:
            # Fallback: log only
            try:
                self.log(f"Balance updated: {bal:.3f} USDT")
            except Exception:
                pass
    except Exception as e:
        try:
            self.log(f"Balance label update error: {e}")
        except Exception:
            pass
    finally:
        if btn:
            btn.setEnabled(True)
            if old_btn_text is not None:
                btn.setText(old_btn_text)

try:
    MainWindow.update_balance_label = update_balance_label
except Exception:
    pass


# --- Graceful teardown to avoid "QThread destroyed while running" and timer warnings ---
def _teardown_positions_thread(self):
    try:
        if getattr(self, "_pos_worker", None) is not None:
            try:
                # Ask the worker (in its own thread) to stop its QTimer
                self.req_pos_stop.emit()
            except Exception:
                pass
        if getattr(self, "_pos_thread", None) is not None:
            try:
                self._pos_thread.quit()
                # wait up to 2 seconds for a clean exit
                self._pos_thread.wait(2000)
            except Exception:
                pass
        self._pos_worker = None
        self._pos_thread = None
    except Exception:
        pass

def closeEvent(self, event):
    try:
        # Stop strategy loops and close positions if needed
        try:
            self.stop_strategy_async(close_positions=bool(getattr(self, "cb_close_on_exit", None) and self.cb_close_on_exit.isChecked()), blocking=True)
        except Exception:
            pass
        _teardown_positions_thread(self)
        try:
            self._mark_session_inactive()
        except Exception:
            pass
    finally:
        try:
            super(MainWindow, self).closeEvent(event)
        except Exception:
            # if super call fails (rare), still accept close
            try:
                event.accept()
            except Exception:
                pass

try:
    MainWindow._teardown_positions_thread = _teardown_positions_thread
    MainWindow.closeEvent = closeEvent
except Exception:
    pass


def _gui_apply_theme(self, name: str):
    theme = (name or '').strip().lower()
    stylesheet = self.DARK_THEME if theme.startswith('dark') else self.LIGHT_THEME
    self.setStyleSheet(stylesheet)
    try:
        self.config['theme'] = 'Dark' if theme.startswith('dark') else 'Light'
    except Exception:
        pass

try:
    MainWindow.apply_theme = _gui_apply_theme
except Exception:
    pass

try:
    MainWindow._update_position_history = _mw_update_position_history
    MainWindow._render_positions_table = _mw_render_positions_table
    MainWindow._snapshot_closed_position = _mw_snapshot_closed_position
    MainWindow._make_close_btn = _mw_make_close_btn
    MainWindow._close_position_single = _mw_close_position_single
    MainWindow._clear_positions_selected = _mw_clear_positions_selected
    MainWindow._clear_positions_all = _mw_clear_positions_all
except Exception:
    pass

try:
    MainWindow._on_positions_ready = _gui_on_positions_ready
except Exception:
    pass


def _gui_setup_log_buffer(self):
    from collections import deque
    self._log_buf = deque(maxlen=8000)
    self._log_timer = QtCore.QTimer(self)
    self._log_timer.setInterval(200)
    self._log_timer.timeout.connect(self._flush_log_buffer)
    self._log_timer.start()

def _gui_buffer_log(self, msg: str):
    try:
        self._log_buf.append(msg)
    except Exception:
        pass

def _mw_reconfigure_positions_worker(self, symbols=None):
    try:
        worker = getattr(self, '_pos_worker', None)
        if worker is None:
            return
        if symbols is None:
            try:
                symbols = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count()) if self.symbol_list.item(i).isSelected()]
            except Exception:
                symbols = None
        worker.configure(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
            symbols=symbols or None,
        )
    except Exception:
        pass


def _mw_collect_strategy_intervals(self, symbol: str, side_key: str):
    intervals = set()
    try:
        engines = getattr(self, 'strategy_engines', {}) or {}
        sym_upper = (symbol or '').upper()
        side_key_upper = (side_key or '').upper()
        for eng in engines.values():
            cfg = getattr(eng, 'config', {}) or {}
            cfg_sym = str(cfg.get('symbol') or '').upper()
            if not cfg_sym or cfg_sym != sym_upper:
                continue
            interval = str(cfg.get('interval') or '').strip()
            if not interval:
                continue
            side_pref = str(cfg.get('side') or 'BOTH').upper()
            if side_pref in ('BUY', 'LONG'):
                allowed = {'L'}
            elif side_pref in ('SELL', 'SHORT'):
                allowed = {'S'}
            else:
                allowed = {'L', 'S'}
            if side_key_upper in allowed:
                intervals.add(interval)
    except Exception:
        pass
    return intervals


def _mw_parse_any_datetime(self, value):
    from datetime import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt):
        try:
            return value.astimezone() if value.tzinfo else value
        except Exception:
            return value
    if isinstance(value, (int, float)):
        try:
            raw = float(value)
            if raw > 1e12:
                raw /= 1000.0
            return _dt.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except Exception:
            pass
    try:
        s = str(value).strip()
    except Exception:
        return None
    if not s:
        return None
    s_norm = s.replace('/', '-')
    patterns = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%d-%m-%Y %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
    )
    for fmt in patterns:
        try:
            dt = _dt.strptime(s_norm, fmt)
            if fmt.endswith('Z'):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone() if dt.tzinfo else dt
        except Exception:
            continue
    try:
        dt = _dt.fromisoformat(s_norm.replace('Z', '+00:00'))
        return dt.astimezone() if dt.tzinfo else dt
    except Exception:
        return None


def _mw_format_display_time(self, value):
    dt = _mw_parse_any_datetime(self, value)
    if dt is None:
        try:
            return str(value) if value not in (None, '') else '-'
        except Exception:
            return '-'
    try:
        if getattr(dt, 'tzinfo', None):
            dt = dt.astimezone()
    except Exception:
        pass
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def _mw_interval_sort_key(label: str):
    try:
        lbl = (label or '').strip().lower()
        if not lbl:
            return (float('inf'), '')
        import re as _re
        match = _re.match(r'(\d+(?:\.\d+)?)([smhdw]?)', lbl)
        if not match:
            return (float('inf'), lbl)
        value = float(match.group(1))
        unit = match.group(2) or 'm'
        factor = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}.get(unit, 60)
        return (value * factor, lbl)
    except Exception:
        return (float('inf'), str(label))


def _gui_flush_log_buffer(self):
    try:
        if not hasattr(self, '_log_buf') or not self._log_buf:
            return
        lines = []
        for _ in range(300):
            if not self._log_buf:
                break
            lines.append(self._log_buf.popleft())
        if not lines:
            return
        from datetime import datetime as _dt
        import re as _re
        pat = _re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]?\s*(.*)$')
        pat2 = _re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)$')
        formatted = []
        for raw in lines:
            line = str(raw)
            match = pat.match(line)
            if match:
                iso_ts, rest = match.groups()
                body = rest.strip()
                nested = pat2.match(body)
                if nested:
                    body = nested.group(2).strip()
                try:
                    ts = _dt.strptime(iso_ts, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M:%S')
                except Exception:
                    ts = _dt.now().strftime('%d.%m.%Y %H:%M:%S')
                formatted.append(f"[{ts}] {body}" if body else f"[{ts}]")
            else:
                ts = _dt.now().strftime('%d.%m.%Y %H:%M:%S')
                formatted.append(f"[{ts}] {line}")
        text = '\n'.join(formatted)
        try:
            self.log_edit.appendPlainText(text)
        except Exception:
            self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
    except Exception:
        pass

try:
    MainWindow._collect_strategy_intervals = _mw_collect_strategy_intervals
except Exception:
    pass

try:
    MainWindow._parse_any_datetime = _mw_parse_any_datetime
    MainWindow._format_display_time = _mw_format_display_time
except Exception:
    pass


try:
    MainWindow._setup_log_buffer = _gui_setup_log_buffer
    MainWindow._buffer_log = _gui_buffer_log
    MainWindow._flush_log_buffer = _gui_flush_log_buffer
except Exception:
    pass

try:
    MainWindow._reconfigure_positions_worker = _mw_reconfigure_positions_worker
except Exception:
    pass


def _mw_log(self, msg: str):
    try:
        self.log_signal.emit(str(msg))
    except Exception:
        pass

def _mw_trade_mux(self, evt: dict):
    try:
        guard = getattr(self, 'guard', None)
        hook = getattr(guard, 'trade_hook', None)
        if callable(hook):
            hook(evt)
    except Exception:
        pass
    try:
        self.trade_signal.emit(evt)
    except Exception:
        pass

def _mw_on_trade_signal(self, order_info: dict):
    self.log(f"TRADE UPDATE: {order_info}")
    sym = order_info.get("symbol")
    interval = order_info.get("interval")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    event_type = str(order_info.get("event") or "").lower()
    status = str(order_info.get("status") or "").lower()
    ok_flag = order_info.get("ok")
    interval = order_info.get("interval")
    side_for_key = position_side or side
    side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
    if event_type == "close_interval":
        try:
            self._entry_intervals.setdefault(sym, {"L": set(), "S": set()}).setdefault(side_key, set()).discard(interval)
        except Exception:
            pass
        try:
            self._entry_times_by_iv.pop((sym, side_key, interval), None)
        except Exception:
            pass
        if sym:
            self.traded_symbols.add(sym)
        self.update_balance_label()
        self.refresh_positions(symbols=[sym] if sym else None)
        return
    is_success = (status != "error") and (ok_flag is None or ok_flag is True)
    if sym and interval and side_for_key:
        side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
        self._entry_intervals.setdefault(sym, {'L': set(), 'S': set()})
        if is_success:
            self._entry_intervals[sym][side_key].add(interval)
            tstr = order_info.get('time')
            if tstr:
                self._entry_times[(sym, side_key)] = tstr
            else:
                from datetime import datetime
                tstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self._entry_times[(sym, side_key)] = tstr
            self._entry_times_by_iv[(sym, side_key, interval)] = tstr
        else:
            try:
                self._entry_intervals[sym][side_key].discard(interval)
                self._entry_times_by_iv.pop((sym, side_key, interval), None)
            except Exception:
                pass
    if sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)

try:
    if not hasattr(MainWindow, 'log'):
        MainWindow.log = _mw_log
    if not hasattr(MainWindow, '_trade_mux'):
        MainWindow._trade_mux = _mw_trade_mux
    if not hasattr(MainWindow, '_on_trade_signal'):
        MainWindow._on_trade_signal = _mw_on_trade_signal
except Exception:
    pass





