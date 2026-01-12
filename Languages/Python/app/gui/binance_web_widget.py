from __future__ import annotations

import html as _html
import os
import re
from datetime import datetime
from pathlib import Path

from PyQt6 import QtCore

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineProfile
except Exception as exc:  # pragma: no cover - environment without WebEngine
    QWebEngineView = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

_QUOTE_ASSETS = [
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "USD",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
    "GBP",
    "AUD",
    "BRL",
    "RUB",
    "IDR",
    "UAH",
    "ZAR",
    "BIDR",
    "PAX",
]

_DEFAULT_UA = os.environ.get(
    "BOT_WEBENGINE_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


def _resolve_log_path() -> Path:
    override = str(os.environ.get("BOT_CHART_DEBUG_LOG", "") or "").strip()
    if override:
        return Path(override)
    return (Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log")


_LOG_PATH = _resolve_log_path()


def _log_chart_event(message: str) -> None:
    try:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = "unknown-time"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _normalize_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper().replace("/", "")
    if raw.endswith(".P"):
        raw = raw[:-2]
    return raw


def _spot_symbol_with_underscore(symbol: str) -> str:
    if "_" in symbol:
        return symbol
    for quote in _QUOTE_ASSETS:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}_{quote}"
    return symbol


def _build_binance_url(symbol: str, interval: str | None, market: str | None) -> str:
    sym = _normalize_symbol(symbol)
    interval_param = str(interval or "").strip()
    if interval_param:
        interval_param = re.sub(r"\s+", "", interval_param)
    market_key = (market or "").strip().lower()
    if market_key == "spot":
        sym = _spot_symbol_with_underscore(sym)
        url = f"https://www.binance.com/en/trade/{sym}?type=spot"
    else:
        url = f"https://www.binance.com/en/futures/{sym}"
    if interval_param:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}interval={interval_param}"
    return url


class BinanceWebWidget(QWebEngineView):  # type: ignore[misc]
    """
    QWebEngine wrapper that embeds Binance's web chart.
    """

    ready = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        if QWebEngineView is None:  # pragma: no cover - defensive
            raise RuntimeError(f"QtWebEngine is unavailable: {_IMPORT_ERROR}")
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        try:
            self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            settings = self.settings()
            settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(settings.WebAttribute.JavascriptCanCloseWindows, False)
        except Exception:
            pass
        try:
            profile = self.page().profile()
            if isinstance(profile, QWebEngineProfile):
                try:
                    profile.setHttpUserAgent(_DEFAULT_UA)
                except Exception:
                    pass
                profile.setPersistentCookiesPolicy(
                    QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
                )
        except Exception:
            pass
        try:
            page = self.page()
            if hasattr(page, "renderProcessTerminated"):
                page.renderProcessTerminated.connect(self._on_render_process_terminated)
        except Exception:
            pass
        self._rendered = False
        self._page_ready = False
        self._pending_url: str | None = None
        self._current_url: str | None = None
        try:
            self.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass
        _log_chart_event("BinanceWebWidget init")

    def set_chart(self, symbol: str, interval: str | None, market: str | None) -> None:
        url = _build_binance_url(symbol, interval, market)
        if not self._rendered:
            self._pending_url = url
            self._render()
            return
        if url != self._current_url:
            self._current_url = url
            self.load(QtCore.QUrl(url))

    def show_message(self, message: str, color: str = "#d1d4dc") -> None:
        safe_msg = _html.escape(str(message or ""))
        safe_color = _html.escape(str(color or "#d1d4dc"))
        html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><style>
html, body {{ margin:0; padding:0; width:100%; height:100%; background-color:#0b0e11; }}
.msg {{ display:flex; width:100%; height:100%; align-items:center; justify-content:center;
        color:{safe_color}; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
</style></head><body><div class='msg'>{safe_msg}</div></body></html>"""
        self._rendered = False
        self._page_ready = False
        self._pending_url = None
        self._current_url = None
        self.setHtml(html, QtCore.QUrl("https://www.binance.com/"))

    def createWindow(self, _type):  # noqa: N802
        return None

    def event(self, event):
        try:
            if event.type() == QtCore.QEvent.Type.CursorChange:
                if self.cursor().shape() == QtCore.Qt.CursorShape.PointingHandCursor:
                    self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        except Exception:
            pass
        return super().event(event)

    def _render(self) -> None:
        if self._rendered:
            return
        self._rendered = True
        url = self._pending_url or "https://www.binance.com/en/futures/BTCUSDT"
        self._pending_url = None
        self._current_url = url
        self.load(QtCore.QUrl(url))

    def _on_load_finished(self, ok: bool) -> None:
        self._page_ready = bool(ok)
        try:
            _log_chart_event(f"BinanceWebWidget loadFinished ok={int(bool(ok))} url={self._current_url}")
        except Exception:
            pass
        if self._page_ready:
            try:
                self.ready.emit()
            except Exception:
                pass

    def _on_render_process_terminated(self, *_args) -> None:
        try:
            _log_chart_event(f"BinanceWebWidget renderProcessTerminated args={_args}")
        except Exception:
            pass
        try:
            self.show_message("Binance web view crashed. Try disabling WebEngine charts.", color="#f75467")
        except Exception:
            pass
