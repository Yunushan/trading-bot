from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime
from pathlib import Path

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
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden; /* Prevent any scrollbars */
      background-color: #0b0e11;
      color: #d1d4dc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #tv_container {
      position: absolute;
      left: 0; top: 0; right: 0; bottom: 0;
      width: 100%;
      height: 100%;
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
  <script type="text/javascript">
    // Block popup windows so the embed stays in-place.
    window.open = function(_url) { return null; };
    window.close = function() { return false; };
  </script>
  <div id="tv_container"></div>
  <div id="fallback" style="display:none;">Loading chart…</div>
  <script type="text/javascript">
    (function() {
      const initialConfig = __INIT_CONFIG__ || {};
      let widget = null;
      let currentConfig = Object.assign({}, initialConfig);
      let pendingConfig = null;
      window.__tv_ready = false;

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
            window.__tv_ready = false;
            widget = new TradingView.widget(buildConfig(cfg));
            currentConfig = Object.assign({}, cfg);
            if (widget && typeof widget.onChartReady === "function") {
              widget.onChartReady(function() { window.__tv_ready = true; });
            } else {
              window.__tv_ready = true;
            }
          } catch (err) {
            console.error(err);
            document.getElementById("fallback").style.display = "flex";
            document.getElementById("fallback").textContent = "TradingView failed to load.";
          }
        });
      }

      function updateSymbolInterval(cfg) {
        const targetSymbol = cfg.symbol || currentConfig.symbol;
        const targetInterval = cfg.interval || currentConfig.interval;
        if (targetSymbol === currentConfig.symbol && targetInterval === currentConfig.interval) {
          return true;
        }
        function applyUpdate() {
          let updated = false;
          try {
            if (widget && typeof widget.setSymbol === "function") {
              widget.setSymbol(targetSymbol, targetInterval, function() {});
              updated = true;
            } else if (widget && typeof widget.chart === "function") {
              const chart = widget.chart();
              if (chart && typeof chart.setSymbol === "function") {
                chart.setSymbol(targetSymbol, targetInterval, function() {});
                updated = true;
              }
            }
          } catch (err) {
            console.error(err);
            updated = false;
          }
          return updated;
        }
        if (widget && typeof widget.onChartReady === "function") {
          widget.onChartReady(function() { applyUpdate(); });
          return true;
        }
        return applyUpdate();
      }

      function applyConfig(cfg) {
        if (!cfg || typeof cfg !== "object") {
          return false;
        }
        const candidate = Object.assign({}, currentConfig, cfg);
        if (widget) {
          const unchanged =
            candidate.symbol === currentConfig.symbol &&
            candidate.interval === currentConfig.interval &&
            candidate.theme === currentConfig.theme &&
            candidate.timezone === currentConfig.timezone &&
            candidate.locale === currentConfig.locale;
          if (unchanged) {
            return true;
          }
        }
        pendingConfig = candidate;
        ensureTradingView(function() {
          const nextCfg = pendingConfig || cfg;
          pendingConfig = null;
          if (!widget) {
            createWidget(nextCfg);
            return;
          }
          try {
            const requiresRebuild =
              (nextCfg.theme && nextCfg.theme !== currentConfig.theme) ||
              (nextCfg.timezone && nextCfg.timezone !== currentConfig.timezone) ||
              (nextCfg.locale && nextCfg.locale !== currentConfig.locale);
            if (requiresRebuild) {
              createWidget(nextCfg);
              return;
            }
            const updated = updateSymbolInterval(nextCfg);
            if (!updated) {
              createWidget(nextCfg);
              return;
            }
            currentConfig = Object.assign({}, currentConfig, nextCfg);
          } catch (err) {
            console.error(err);
            createWidget(nextCfg);
          }
        });
        return true;
      }

      window.__tv_apply_config = applyConfig;
      window.__tv_get_config = function() { return currentConfig; };

      createWidget(initialConfig);
    })();
  </script>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
</body>
</html>
"""

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


class TradingViewWidget(QWebEngineView):  # type: ignore[misc]
    """
    Minimal QWebEngine wrapper around TradingView. We try to update symbol/interval
    in-place to avoid reload flicker, with a fallback full rebuild when needed.
    """
    ready = QtCore.pyqtSignal()

    DEFAULT_TIMEFRAMES = [
        "1", "3", "5", "15", "30", "45", "60", "120", "240", "720", "1D", "1W", "1M"
    ]

    def __init__(self, parent=None):
        if QWebEngineView is None:  # pragma: no cover - defensive
            raise RuntimeError(f"QtWebEngine is unavailable: {_IMPORT_ERROR}")
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        # Disable scrollbars - the chart should fill the entire widget
        try:
            from PyQt6.QtWidgets import QAbstractScrollArea
            self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            settings = self.settings()
            settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(settings.WebAttribute.HyperlinkAuditingEnabled, False)
            local_remote = getattr(settings.WebAttribute, "LocalContentCanAccessRemoteUrls", None)
            if local_remote is not None:
                settings.setAttribute(local_remote, True)
            local_file = getattr(settings.WebAttribute, "LocalContentCanAccessFileUrls", None)
            if local_file is not None:
                settings.setAttribute(local_file, True)
            js_open_attr = getattr(settings.WebAttribute, "JavascriptCanOpenWindows", None)
            if js_open_attr is not None:
                settings.setAttribute(js_open_attr, False)
            js_close_attr = getattr(settings.WebAttribute, "JavascriptCanCloseWindows", None)
            if js_close_attr is not None:
                settings.setAttribute(js_close_attr, False)
            focus_attr = getattr(settings.WebAttribute, "FocusOnNavigationEnabled", None)
            if focus_attr is not None:
                settings.setAttribute(focus_attr, False)
        except Exception:
            pass
        try:
            profile = self.page().profile()
            profile.setHttpUserAgent(_DEFAULT_UA)
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
        self._render_pending = False
        self._last_render_cfg: dict[str, str | list[str]] | None = None
        self._page_ready = False
        self._widget_ready = False
        self._pending_config: dict[str, str | list[str]] | None = None
        self._ready_probe_timer = None
        self._ready_probe_tries = 0
        try:
            self.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass
        try:
            page = self.page()
            if hasattr(page, "newWindowRequested"):
                page.newWindowRequested.connect(self._on_new_window_requested)
            if hasattr(page, "windowCloseRequested"):
                page.windowCloseRequested.connect(self._on_window_close_requested)
            if hasattr(page, "renderProcessTerminated"):
                page.renderProcessTerminated.connect(self._on_render_process_terminated)
        except Exception:
            pass
        # DO NOT render immediately - defer until widget is shown
        # This prevents QtWebEngine from spawning helper processes during app startup
        # self._render()
        _log_chart_event("TradingViewWidget init")
    
    def showEvent(self, event):
        """Render chart only when the widget is actually shown"""
        super().showEvent(event)
        if not self._rendered or self._render_pending:
            self._render_pending = False
            self._render()
            self._rendered = True
            return
        pending = self._pending_config
        if pending and self._page_ready:
            if self._last_render_cfg != pending:
                self._apply_js_config(pending)
            else:
                self._pending_config = None

    def set_chart(
        self,
        symbol: str,
        interval: str,
        *,
        theme: str = "dark",
        timezone: str = "Etc/UTC",
        locale: str = "en",
    ) -> None:
        new_cfg = {
            "symbol": str(symbol or "").strip().upper() or "BINANCE:BTCUSDT",
            "interval": str(interval or "").strip() or "60",
            "theme": "light" if str(theme or "").lower().startswith("light") else "dark",
            "timezone": timezone or "Etc/UTC",
            "locale": locale or "en",
        }
        if self._rendered and self._page_ready:
            unchanged = all(self._current_config.get(key) == value for key, value in new_cfg.items())
            if unchanged:
                return
        self._current_config.update(new_cfg)
        self._apply_config()

    def apply_theme(self, theme: str) -> None:
        new_theme = "light" if str(theme or "").lower().startswith("light") else "dark"
        if self._rendered and self._page_ready and self._current_config.get("theme") == new_theme:
            return
        self._current_config["theme"] = new_theme
        self._apply_config()

    def is_ready(self) -> bool:
        return bool(self._widget_ready)

    def warmup(self) -> None:
        if self._rendered:
            return
        self._render_pending = False
        self._render()
        self._rendered = True

    def event(self, event):
        try:
            if event.type() == QtCore.QEvent.Type.CursorChange:
                shape = self.cursor().shape()
                if shape in {
                    QtCore.Qt.CursorShape.PointingHandCursor,
                    QtCore.Qt.CursorShape.OpenHandCursor,
                    QtCore.Qt.CursorShape.ClosedHandCursor,
                }:
                    self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        except Exception:
            pass
        return super().event(event)

    # Block TradingView popups from spawning external windows.
    def createWindow(self, _type):  # noqa: N802
        return None

    def _on_new_window_requested(self, request):  # noqa: ANN001
        try:
            request.reject()
        except Exception:
            pass

    def _on_window_close_requested(self) -> None:
        return

    def _on_render_process_terminated(self, *_args) -> None:
        try:
            _log_chart_event(f"TradingViewWidget renderProcessTerminated args={_args}")
        except Exception:
            pass
        try:
            self.show_message("TradingView crashed. Retrying...")
        except Exception:
            pass
        self._rendered = False
        self._page_ready = False
        self._widget_ready = False
        self._pending_config = dict(self._current_config)
        try:
            QtCore.QTimer.singleShot(250, self._render)
        except Exception:
            pass

    def show_message(self, message: str, color: str = "#d1d4dc") -> None:
        safe_msg = _html.escape(str(message or ""))
        safe_color = _html.escape(str(color or "#d1d4dc"))
        html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><style>
html, body {{ margin:0; padding:0; width:100%; height:100%; background-color:#0b0e11; }}
.msg {{ display:flex; width:100%; height:100%; align-items:center; justify-content:center;
        color:{safe_color}; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
</style></head><body><div class='msg'>{safe_msg}</div></body></html>"""
        self._last_render_cfg = None
        self._rendered = False
        self._page_ready = False
        self._widget_ready = False
        self._pending_config = None
        self._reset_ready_probe()
        self.setHtml(html, QtCore.QUrl("https://www.tradingview.com/"))

    # Internal helpers -------------------------------------------------
    def _on_load_finished(self, ok: bool) -> None:
        self._page_ready = bool(ok)
        try:
            _log_chart_event(f"TradingViewWidget loadFinished ok={int(bool(ok))}")
        except Exception:
            pass
        if not self._page_ready:
            return
        self._start_ready_probe()
        pending = self._pending_config
        if pending is None or not self.isVisible():
            return
        if self._last_render_cfg == pending:
            self._pending_config = None
            return
        self._apply_js_config(pending)

    def _reset_ready_probe(self) -> None:
        timer = self._ready_probe_timer
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
        self._ready_probe_timer = None

    def _start_ready_probe(self) -> None:
        if self._widget_ready:
            return
        self._reset_ready_probe()
        if not self._page_ready:
            return
        self._ready_probe_tries = 0
        timer = QtCore.QTimer(self)
        timer.setInterval(120)

        def _handle_result(result):
            if self._widget_ready:
                return
            if bool(result):
                self._widget_ready = True
                try:
                    self.ready.emit()
                except Exception:
                    pass
                self._reset_ready_probe()

        def _tick():
            if not self._page_ready or self._widget_ready:
                self._reset_ready_probe()
                return
            self._ready_probe_tries += 1
            if self._ready_probe_tries > 120:
                self._widget_ready = True
                try:
                    self.ready.emit()
                except Exception:
                    pass
                self._reset_ready_probe()
                return
            try:
                self.page().runJavaScript("window.__tv_ready === true", _handle_result)
            except Exception:
                self._widget_ready = True
                try:
                    self.ready.emit()
                except Exception:
                    pass
                self._reset_ready_probe()

        timer.timeout.connect(_tick)
        timer.start()
        self._ready_probe_timer = timer
        _tick()

    def _apply_config(self) -> None:
        cfg = dict(self._current_config)
        self._pending_config = cfg
        if self._last_render_cfg == cfg and self._page_ready:
            self._pending_config = None
            return
        if not self.isVisible():
            self._render_pending = True
            return
        if not self._rendered:
            self._render()
            self._rendered = True
            return
        if not self._page_ready:
            return
        self._apply_js_config(cfg)

    def _apply_js_config(self, cfg: dict[str, str | list[str]]) -> None:
        payload = json.dumps(cfg)
        script = (
            "(function(cfg){"
            "if (typeof window.__tv_apply_config !== 'function') { return false; }"
            "return window.__tv_apply_config(cfg);"
            "})(%s);"
        ) % payload

        def _done(result):
            if result is False:
                self._render()
                self._rendered = True
                return
            self._last_render_cfg = cfg
            if self._pending_config == cfg:
                self._pending_config = None

        try:
            self.page().runJavaScript(script, _done)
        except Exception:
            self._render()
            self._rendered = True

    def _render(self) -> None:
        cfg = dict(self._current_config)
        if self._last_render_cfg == cfg:
            return
        self._page_ready = False
        self._widget_ready = False
        self._reset_ready_probe()
        self._last_render_cfg = cfg
        html = _HTML_TEMPLATE.replace("__INIT_CONFIG__", json.dumps(cfg))
        self.setHtml(html, QtCore.QUrl("https://www.tradingview.com/"))


TRADINGVIEW_EMBED_AVAILABLE = QWebEngineView is not None and _IMPORT_ERROR is None
