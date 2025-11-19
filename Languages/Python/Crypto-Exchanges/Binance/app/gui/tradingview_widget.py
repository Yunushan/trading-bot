from __future__ import annotations

import html as _html
import json

from PyQt6 import QtCore

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception as exc:  # pragma: no cover - environment without WebEngine
    QWebEngineView = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body, #tv_container {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background-color: #0b0e11;
      color: #d1d4dc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #fallback {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      height: 100%;
      background-color: #0b0e11;
      color: #d1d4dc;
      font-size: 16px;
    }
  </style>
</head>
<body>
  <div id="tv_container"></div>
  <div id="fallback" style="display:none;">Loading chart…</div>
  <script type="text/javascript">
    (function() {
      const initialConfig = __INIT_CONFIG__ || {};
      let widget = null;

      function ensureTradingView(callback) {
        if (window.TradingView && typeof window.TradingView.widget === "function") {
          callback();
          return;
        }
        setTimeout(function() { ensureTradingView(callback); }, 120);
      }

      function buildConfig(cfg) {
        const base = Object.assign({}, cfg);
        base.container_id = "tv_container";
        base.autosize = true;
        base.withdateranges = true;
        base.hide_side_toolbar = false;
        base.allow_symbol_change = true;
        base.enable_publishing = false;
        base.toolbar_bg = cfg.theme === "light" ? "#f4f6f8" : "#131722";
        base.drawings_access = { type: "all" };
        base.support_host = "https://www.tradingview.com";
        return base;
      }

      function createWidget(cfg) {
        ensureTradingView(function() {
          try {
            document.getElementById("fallback").style.display = "none";
            if (widget && typeof widget.remove === "function") {
              widget.remove();
            }
            widget = new TradingView.widget(buildConfig(cfg));
          } catch (err) {
            console.error(err);
            document.getElementById("fallback").style.display = "flex";
            document.getElementById("fallback").textContent = "TradingView failed to load.";
          }
        });
      }

      createWidget(initialConfig);
    })();
  </script>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
</body>
</html>
"""


class TradingViewWidget(QWebEngineView):  # type: ignore[misc]
    """
    Minimal QWebEngine wrapper around TradingView. We rebuild the widget every
    time the caller asks for a new symbol/interval. That keeps behaviour simple
    and reliable, at the cost of a quick reload flicker.
    """

    DEFAULT_TIMEFRAMES = [
        "1", "3", "5", "15", "30", "45", "60", "120", "240", "720", "1D", "1W", "1M"
    ]

    def __init__(self, parent=None):
        if QWebEngineView is None:  # pragma: no cover - defensive
            raise RuntimeError(f"QtWebEngine is unavailable: {_IMPORT_ERROR}")
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        try:
            self.settings().setAttribute(self.settings().WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass
        self._current_config: dict[str, str | list[str]] = {
            "symbol": "BINANCE:BTCUSDT",
            "interval": "60",
            "theme": "dark",
            "timezone": "Etc/UTC",
            "locale": "en",
            "timeframes": self.DEFAULT_TIMEFRAMES,
        }
        self._rendered = False
        # DO NOT render immediately - defer until widget is shown
        # This prevents QtWebEngine from spawning helper processes during app startup
        # self._render()
    
    def showEvent(self, event):
        """Render chart only when the widget is actually shown"""
        super().showEvent(event)
        if not self._rendered:
            self._rendered = True
            self._render()

    def set_chart(
        self,
        symbol: str,
        interval: str,
        *,
        theme: str = "dark",
        timezone: str = "Etc/UTC",
        locale: str = "en",
    ) -> None:
        self._current_config.update({
            "symbol": str(symbol or "").strip().upper() or "BINANCE:BTCUSDT",
            "interval": str(interval or "").strip() or "60",
            "theme": "light" if str(theme or "").lower().startswith("light") else "dark",
            "timezone": timezone or "Etc/UTC",
            "locale": locale or "en",
        })
        self._render()

    def apply_theme(self, theme: str) -> None:
        self._current_config["theme"] = (
            "light" if str(theme or "").lower().startswith("light") else "dark"
        )
        self._render()

    def show_message(self, message: str, color: str = "#d1d4dc") -> None:
        safe_msg = _html.escape(str(message or ""))
        safe_color = _html.escape(str(color or "#d1d4dc"))
        html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><style>
html, body {{ margin:0; padding:0; width:100%; height:100%; background-color:#0b0e11; }}
.msg {{ display:flex; width:100%; height:100%; align-items:center; justify-content:center;
        color:{safe_color}; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
</style></head><body><div class='msg'>{safe_msg}</div></body></html>"""
        self.setHtml(html, QtCore.QUrl("https://www.tradingview.com/"))

    # Internal helpers -------------------------------------------------
    def _render(self) -> None:
        cfg = dict(self._current_config)
        html = _HTML_TEMPLATE.replace("__INIT_CONFIG__", json.dumps(cfg))
        self.setHtml(html, QtCore.QUrl("https://www.tradingview.com/"))


TRADINGVIEW_EMBED_AVAILABLE = QWebEngineView is not None and _IMPORT_ERROR is None
