from __future__ import annotations

import json

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


def _build_tradingview_html(cfg: dict[str, str | list[str]]) -> str:
    return _HTML_TEMPLATE.replace("__INIT_CONFIG__", json.dumps(cfg))
