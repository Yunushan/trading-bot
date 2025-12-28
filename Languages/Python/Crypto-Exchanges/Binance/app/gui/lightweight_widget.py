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


_LIB_CDN_SOURCES = [
    "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js",
    "https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js",
]


def _resolve_lightweight_lib_sources() -> list[str]:
    sources: list[str] = []
    try:
        local_path = Path(__file__).resolve().parent.parent / "assets" / "lightweight-charts.standalone.production.js"
        if local_path.is_file():
            sources.append(local_path.as_uri())
    except Exception:
        pass
    sources.extend(_LIB_CDN_SOURCES)
    return sources


_LIB_SOURCES = _resolve_lightweight_lib_sources()
_LIB_SOURCES_JSON = json.dumps(_LIB_SOURCES, ensure_ascii=True)

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background-color: #0b0e11;
      color: #d1d4dc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    #root {{
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100%;
    }}
    #main {{
      flex: 1 1 auto;
      min-height: 200px;
    }}
    #indicator_root {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 6px 0 2px 0;
    }}
    .pane {{
      width: 100%;
    }}
    #fallback {{
      position: absolute;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background-color: #0b0e11;
      color: #d1d4dc;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div id="root">
    <div id="main"></div>
    <div id="indicator_root"></div>
  </div>
  <div id="fallback">Loading chart...</div>
  <script type="text/javascript">
    (function() {{
      const initPayload = __INIT_PAYLOAD__ || {{}};
      let currentPayload = Object.assign({{}}, initPayload);
      let mainChart = null;
      let candleSeries = null;
      let volumeSeries = null;
      let overlaySeries = [];
      let paneCharts = [];
      let syncHandler = null;
      let resizeObservers = [];
      let ready = false;
      const LIB_SOURCES = __LIB_SOURCES__;
      let libLoading = false;
      let libLoaded = false;
      let libFailed = false;

      function showFallback(msg) {{
        const fallback = document.getElementById("fallback");
        fallback.style.display = "flex";
        fallback.textContent = msg || "Chart unavailable.";
      }}

      function hideFallback() {{
        const fallback = document.getElementById("fallback");
        fallback.style.display = "none";
      }}

      function loadLibrary(index, done) {{
        if (index >= LIB_SOURCES.length) {{
          done(false);
          return;
        }}
        const script = document.createElement("script");
        script.src = LIB_SOURCES[index];
        script.async = true;
        script.onload = function() {{ done(true); }};
        script.onerror = function() {{ loadLibrary(index + 1, done); }};
        document.head.appendChild(script);
      }}

      function ensureLibrary(callback) {{
        if (window.LightweightCharts && typeof window.LightweightCharts.createChart === "function") {{
          libLoaded = true;
          callback();
          return;
        }}
        if (libFailed) {{
          showFallback("Chart library failed to load. Check network access.");
          return;
        }}
        if (!libLoading && !libLoaded) {{
          libLoading = true;
          showFallback("Loading chart library...");
          loadLibrary(0, function(ok) {{
            libLoading = false;
            libLoaded = ok;
            if (!ok) {{
              libFailed = true;
              showFallback("Chart library failed to load. Check network access.");
            }}
          }});
        }}
        setTimeout(function() {{ ensureLibrary(callback); }}, 200);
      }}

      function clearObservers() {{
        resizeObservers.forEach(obs => {{
          try {{ obs.disconnect(); }} catch (err) {{}}
        }});
        resizeObservers = [];
      }}

      function attachResize(chart, container) {{
        function resize() {{
          const w = container.clientWidth;
          const h = container.clientHeight;
          if (w > 0 && h > 0) {{
            chart.resize(w, h);
          }}
        }}
        if (typeof ResizeObserver !== "undefined") {{
          const obs = new ResizeObserver(resize);
          obs.observe(container);
          resizeObservers.push(obs);
        }} else {{
          const handler = function() {{ resize(); }};
          window.addEventListener("resize", handler);
          resizeObservers.push({{ disconnect: function() {{ window.removeEventListener("resize", handler); }} }});
        }}
        resize();
      }}

      function cleanupPanes() {{
        paneCharts.forEach(entry => {{
          try {{ entry.chart.remove(); }} catch (err) {{}}
        }});
        paneCharts = [];
        const root = document.getElementById("indicator_root");
        root.innerHTML = "";
      }}

      function resetMainChart() {{
        if (mainChart) {{
          try {{ mainChart.remove(); }} catch (err) {{}}
        }}
        mainChart = null;
        candleSeries = null;
        volumeSeries = null;
        overlaySeries = [];
        cleanupPanes();
        clearObservers();
      }}

      function createMainChart(theme) {{
        const mainRoot = document.getElementById("main");
        const isLight = (theme || "dark") === "light";
        mainChart = LightweightCharts.createChart(mainRoot, {{
          layout: {{
            background: {{ color: isLight ? "#f8fafc" : "#0b0e11" }},
            textColor: isLight ? "#111827" : "#94a3b8",
          }},
          grid: {{
            vertLines: {{ color: isLight ? "#e2e8f0" : "#1f2326" }},
            horzLines: {{ color: isLight ? "#e2e8f0" : "#1f2326" }},
          }},
          crosshair: {{
            mode: LightweightCharts.CrosshairMode.Normal,
          }},
          timeScale: {{
            borderColor: isLight ? "#e2e8f0" : "#1f2326",
            timeVisible: true,
            secondsVisible: false,
          }},
          rightPriceScale: {{
            borderColor: isLight ? "#e2e8f0" : "#1f2326",
          }},
        }});
        candleSeries = mainChart.addCandlestickSeries({{
          upColor: "#0ebb7a",
          downColor: "#f75467",
          borderUpColor: "#0ebb7a",
          borderDownColor: "#f75467",
          wickUpColor: "#0ebb7a",
          wickDownColor: "#f75467",
        }});
        volumeSeries = mainChart.addHistogramSeries({{
          priceScaleId: "vol",
          color: "#1f2326",
          priceFormat: {{ type: "volume" }},
        }});
        mainChart.priceScale("vol").applyOptions({{
          scaleMargins: {{ top: 0.8, bottom: 0.0 }},
          borderVisible: false,
        }});
        mainChart.priceScale("right").applyOptions({{
          scaleMargins: {{ top: 0.1, bottom: 0.2 }},
        }});
        attachResize(mainChart, mainRoot);
      }}

      function rebuildOverlays(overlays) {{
        if (!mainChart) {{
          return;
        }}
        overlaySeries.forEach(series => {{
          try {{ mainChart.removeSeries(series); }} catch (err) {{}}
        }});
        overlaySeries = [];
        (overlays || []).forEach(entry => {{
          const line = mainChart.addLineSeries({{
            color: entry.color || "#f59e0b",
            lineWidth: entry.lineWidth || 2,
            lineStyle: entry.lineStyle || 0,
            priceScaleId: entry.scaleId || "right",
          }});
          line.setData(entry.data || []);
          overlaySeries.push(line);
        }});
      }}

      function rebuildPanes(panes, theme) {{
        cleanupPanes();
        const root = document.getElementById("indicator_root");
        if (!panes || !panes.length) {{
          return;
        }}
        const isLight = (theme || "dark") === "light";
        panes.forEach(pane => {{
          const paneDiv = document.createElement("div");
          paneDiv.className = "pane";
          const height = pane.height || 80;
          paneDiv.style.height = `${{height}}px`;
          root.appendChild(paneDiv);
          const chart = LightweightCharts.createChart(paneDiv, {{
            layout: {{
              background: {{ color: isLight ? "#f8fafc" : "#0b0e11" }},
              textColor: isLight ? "#111827" : "#94a3b8",
            }},
            grid: {{
              vertLines: {{ color: isLight ? "#e2e8f0" : "#1f2326" }},
              horzLines: {{ color: isLight ? "#e2e8f0" : "#1f2326" }},
            }},
            timeScale: {{
              visible: false,
            }},
            rightPriceScale: {{
              borderColor: isLight ? "#e2e8f0" : "#1f2326",
            }},
          }});
          if (pane.label) {{
            chart.applyOptions({{
              watermark: {{
                visible: true,
                fontSize: 10,
                color: isLight ? "#64748b" : "#475569",
                text: pane.label,
                horzAlign: "left",
                vertAlign: "top",
              }}
            }});
          }}
          (pane.series || []).forEach(entry => {{
            let series = null;
            if (entry.type === "histogram") {{
              const opts = {{
                color: entry.color || "#94a3b8",
              }};
              if (entry.priceFormat) {{
                opts.priceFormat = entry.priceFormat;
              }}
              series = chart.addHistogramSeries(opts);
            }} else {{
              series = chart.addLineSeries({{
                color: entry.color || "#f59e0b",
                lineWidth: entry.lineWidth || 2,
                lineStyle: entry.lineStyle || 0,
              }});
            }}
            if (series) {{
              series.setData(entry.data || []);
            }}
          }});
          attachResize(chart, paneDiv);
          paneCharts.push({{ chart }});
        }});
      }}

      function syncTimeScale() {{
        if (!mainChart) {{
          return;
        }}
        if (syncHandler) {{
          try {{
            mainChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncHandler);
          }} catch (err) {{}}
        }}
        syncHandler = function(range) {{
          paneCharts.forEach(entry => {{
            try {{
              entry.chart.timeScale().setVisibleLogicalRange(range);
            }} catch (err) {{}}
          }});
        }};
        mainChart.timeScale().subscribeVisibleLogicalRangeChange(syncHandler);
      }}

      function applyPayload(payload) {{
        if (!payload || typeof payload !== "object") {{
          return false;
        }}
        currentPayload = Object.assign({{}}, currentPayload, payload);
        ensureLibrary(function() {{
          hideFallback();
          const theme = currentPayload.theme || "dark";
          if (!mainChart) {{
            createMainChart(theme);
          }}
          if (!mainChart || !candleSeries) {{
            showFallback("Chart unavailable.");
            return;
          }}
          candleSeries.setData(currentPayload.candles || []);
          if (volumeSeries) {{
            volumeSeries.setData(currentPayload.volume || []);
          }}
          rebuildOverlays(currentPayload.overlays || []);
          rebuildPanes(currentPayload.panes || [], theme);
          syncTimeScale();
          ready = true;
        }});
        return true;
      }}

      window.__lw_apply_payload = applyPayload;
      window.__lw_ready = function() {{ return ready; }};

      if (!window.LightweightCharts) {{
        showFallback("Loading chart...");
      }}
      applyPayload(initPayload);
    }})();
  </script>
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


class LightweightChartWidget(QWebEngineView):  # type: ignore[misc]
    """
    QWebEngine wrapper around TradingView Lightweight Charts.
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
            settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(settings.WebAttribute.HyperlinkAuditingEnabled, False)
            local_remote = getattr(settings.WebAttribute, "LocalContentCanAccessRemoteUrls", None)
            if local_remote is not None:
                settings.setAttribute(local_remote, True)
            local_file = getattr(settings.WebAttribute, "LocalContentCanAccessFileUrls", None)
            if local_file is not None:
                settings.setAttribute(local_file, True)
            settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(settings.WebAttribute.JavascriptCanCloseWindows, False)
        except Exception:
            pass
        try:
            profile = self.page().profile()
            profile.setHttpUserAgent(_DEFAULT_UA)
        except Exception:
            pass
        self._rendered = False
        self._page_ready = False
        self._pending_payload: dict | None = None
        try:
            self.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass
        try:
            page = self.page()
            if hasattr(page, "renderProcessTerminated"):
                page.renderProcessTerminated.connect(self._on_render_process_terminated)
        except Exception:
            pass
        _log_chart_event("LightweightChartWidget init")

    def set_chart_data(self, payload: dict) -> None:
        if not payload:
            return
        if not self._rendered:
            self._pending_payload = payload
            self._render(payload)
            return
        self._pending_payload = payload
        if self._page_ready:
            self._apply_payload(payload)

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
        self._pending_payload = None
        self.setHtml(html, QtCore.QUrl("about:blank"))

    def createWindow(self, _type):  # noqa: N802
        return None

    def _render(self, payload: dict | None = None) -> None:
        if self._rendered:
            return
        self._rendered = True
        payload_json = json.dumps(payload or {}, ensure_ascii=True)
        html = _HTML_TEMPLATE.replace("__INIT_PAYLOAD__", payload_json).replace("__LIB_SOURCES__", _LIB_SOURCES_JSON)
        self.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_load_finished(self, ok: bool) -> None:
        self._page_ready = bool(ok)
        try:
            _log_chart_event(f"LightweightChartWidget loadFinished ok={int(bool(ok))}")
        except Exception:
            pass
        if not self._page_ready:
            return
        pending = self._pending_payload
        if pending:
            self._apply_payload(pending)
        try:
            self.ready.emit()
        except Exception:
            pass

    def _on_render_process_terminated(self, *_args) -> None:
        try:
            _log_chart_event(f"LightweightChartWidget renderProcessTerminated args={_args}")
        except Exception:
            pass
        try:
            self.show_message("Lightweight chart crashed. Try disabling WebEngine charts.", color="#f75467")
        except Exception:
            pass

    def _apply_payload(self, payload: dict) -> None:
        if not payload or not self._page_ready:
            return
        try:
            payload_json = json.dumps(payload, ensure_ascii=True)
        except Exception:
            return
        try:
            _log_chart_event(
                "LightweightChartWidget apply_payload "
                f"candles={len(payload.get('candles') or [])} "
                f"overlays={len(payload.get('overlays') or [])} "
                f"panes={len(payload.get('panes') or [])}"
            )
        except Exception:
            pass
        try:
            self.page().runJavaScript(f"window.__lw_apply_payload({payload_json});")
        except Exception:
            pass
