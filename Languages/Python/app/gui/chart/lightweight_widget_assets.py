from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from PyQt6 import QtCore

_LIB_CDN_SOURCES = [
    "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js",
    "https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js",
]


def _resolve_lightweight_local_lib() -> Path | None:
    try:
        local_path = (
            Path(__file__).resolve().parent.parent.parent
            / "assets"
            / "lightweight-charts.standalone.production.js"
        )
        if local_path.is_file():
            return local_path
    except Exception:
        return None
    return None


_LOCAL_LIB_PATH = _resolve_lightweight_local_lib()


def _resolve_lightweight_lib_sources() -> list[str]:
    sources: list[str] = []
    try:
        if _LOCAL_LIB_PATH is not None and _LOCAL_LIB_PATH.is_file():
            sources.append(_LOCAL_LIB_PATH.as_uri())
    except Exception:
        pass
    sources.extend(_LIB_CDN_SOURCES)
    return sources


_LIB_SOURCES = _resolve_lightweight_lib_sources()
_LIB_SOURCES_JSON = json.dumps(_LIB_SOURCES, ensure_ascii=True)
_INLINE_LIB_CACHE: str | None = None


def _resolve_lightweight_base_url() -> QtCore.QUrl:
    """
    Use a file:// origin when possible so local JS assets load even when HTTPS
    access is blocked or intercepted on Windows.
    """
    try:
        if _LOCAL_LIB_PATH is not None and _LOCAL_LIB_PATH.is_file():
            return QtCore.QUrl.fromLocalFile(str(_LOCAL_LIB_PATH))
        return QtCore.QUrl.fromLocalFile(str(Path(__file__).resolve()))
    except Exception:
        return QtCore.QUrl("https://localhost/")


_BASE_URL = _resolve_lightweight_base_url()


def _resolve_lightweight_html_path() -> Path | None:
    try:
        temp_root = Path(os.getenv("TEMP") or ".").resolve()
        temp_root.mkdir(parents=True, exist_ok=True)
        return temp_root / f"binance_lightweight_{uuid4().hex}.html"
    except Exception:
        return None


def _load_inline_library(log_chart_event) -> str:
    global _INLINE_LIB_CACHE
    if _INLINE_LIB_CACHE is not None:
        return _INLINE_LIB_CACHE
    if _LOCAL_LIB_PATH is None or not _LOCAL_LIB_PATH.is_file():
        _INLINE_LIB_CACHE = ""
        return _INLINE_LIB_CACHE
    try:
        content = _LOCAL_LIB_PATH.read_text(encoding="utf-8", errors="ignore")
        _INLINE_LIB_CACHE = f"<script>\n{content}\n</script>"
        log_chart_event(f"LightweightChartWidget inline lib loaded size={len(content)}")
        return _INLINE_LIB_CACHE
    except Exception as exc:
        _INLINE_LIB_CACHE = ""
        log_chart_event(f"LightweightChartWidget inline lib failed: {exc}")
        return _INLINE_LIB_CACHE


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
  __LIB_INLINE__
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


def _build_lightweight_chart_html(payload: dict | None, log_chart_event) -> str:
    payload_json = json.dumps(payload or {}, ensure_ascii=True)
    template = _HTML_TEMPLATE.replace("{{", "{").replace("}}", "}")
    html = template.replace("__INIT_PAYLOAD__", payload_json).replace(
        "__LIB_SOURCES__",
        _LIB_SOURCES_JSON,
    )
    return html.replace("__LIB_INLINE__", _load_inline_library(log_chart_event))
