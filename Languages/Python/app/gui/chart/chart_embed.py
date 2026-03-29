from __future__ import annotations

from . import chart_embed_host_runtime, chart_embed_state_runtime

_native_chart_host_prewarm_enabled = chart_embed_state_runtime._native_chart_host_prewarm_enabled
_configure_tradingview_webengine_env = chart_embed_state_runtime._configure_tradingview_webengine_env
_webengine_charts_allowed = chart_embed_state_runtime._webengine_charts_allowed
_chart_safe_mode_enabled = chart_embed_state_runtime._chart_safe_mode_enabled
_resolve_dist_version = chart_embed_state_runtime._resolve_dist_version
_tradingview_embed_health = chart_embed_state_runtime._tradingview_embed_health
_webengine_embed_health = chart_embed_state_runtime._webengine_embed_health
_webengine_embed_unavailable_reason = chart_embed_state_runtime._webengine_embed_unavailable_reason
_tradingview_unavailable_reason = chart_embed_state_runtime._tradingview_unavailable_reason
_binance_unavailable_reason = chart_embed_state_runtime._binance_unavailable_reason
_lightweight_unavailable_reason = chart_embed_state_runtime._lightweight_unavailable_reason
_load_tradingview_widget = chart_embed_state_runtime._load_tradingview_widget
_load_binance_widget = chart_embed_state_runtime._load_binance_widget
_load_lightweight_widget = chart_embed_state_runtime._load_lightweight_widget
_tradingview_supported = chart_embed_state_runtime._tradingview_supported
_binance_supported = chart_embed_state_runtime._binance_supported
_lightweight_supported = chart_embed_state_runtime._lightweight_supported
_tradingview_external_preferred = chart_embed_state_runtime._tradingview_external_preferred
_build_tradingview_url = chart_embed_state_runtime._build_tradingview_url

ensure_tradingview_widget = chart_embed_host_runtime.ensure_tradingview_widget
bind_tradingview_ready = chart_embed_host_runtime.bind_tradingview_ready
ensure_binance_widget = chart_embed_host_runtime.ensure_binance_widget
ensure_lightweight_widget = chart_embed_host_runtime.ensure_lightweight_widget
update_chart_overlay_geometry = chart_embed_host_runtime.update_chart_overlay_geometry
show_chart_switch_overlay = chart_embed_host_runtime.show_chart_switch_overlay
hide_chart_switch_overlay = chart_embed_host_runtime.hide_chart_switch_overlay
prime_tradingview_chart = chart_embed_host_runtime.prime_tradingview_chart
open_tradingview_external = chart_embed_host_runtime.open_tradingview_external


def __getattr__(name: str):
    if name in {
        "TradingViewWidget",
        "TRADINGVIEW_EMBED_AVAILABLE",
        "_TRADINGVIEW_IMPORT_ERROR",
        "_TRADINGVIEW_ENV_CONFIGURED",
        "_TRADINGVIEW_EXTERNAL_PREFERRED",
        "BinanceWebWidget",
        "BINANCE_WEB_AVAILABLE",
        "_BINANCE_IMPORT_ERROR",
        "LightweightChartWidget",
        "LIGHTWEIGHT_CHART_AVAILABLE",
        "_LIGHTWEIGHT_IMPORT_ERROR",
        "_WEBENGINE_DISABLED_REASON",
        "_DEFAULT_WEB_UA",
    }:
        return getattr(chart_embed_state_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BINANCE_WEB_AVAILABLE",
    "BinanceWebWidget",
    "LIGHTWEIGHT_CHART_AVAILABLE",
    "LightweightChartWidget",
    "TRADINGVIEW_EMBED_AVAILABLE",
    "TradingViewWidget",
    "_DEFAULT_WEB_UA",
    "_BINANCE_IMPORT_ERROR",
    "_LIGHTWEIGHT_IMPORT_ERROR",
    "_TRADINGVIEW_ENV_CONFIGURED",
    "_TRADINGVIEW_EXTERNAL_PREFERRED",
    "_TRADINGVIEW_IMPORT_ERROR",
    "_WEBENGINE_DISABLED_REASON",
    "_binance_supported",
    "_binance_unavailable_reason",
    "_build_tradingview_url",
    "_chart_safe_mode_enabled",
    "_configure_tradingview_webengine_env",
    "_lightweight_supported",
    "_lightweight_unavailable_reason",
    "_load_binance_widget",
    "_load_lightweight_widget",
    "_load_tradingview_widget",
    "_native_chart_host_prewarm_enabled",
    "_resolve_dist_version",
    "_tradingview_embed_health",
    "_tradingview_external_preferred",
    "_tradingview_supported",
    "_tradingview_unavailable_reason",
    "_webengine_charts_allowed",
    "_webengine_embed_health",
    "_webengine_embed_unavailable_reason",
    "bind_tradingview_ready",
    "ensure_binance_widget",
    "ensure_lightweight_widget",
    "ensure_tradingview_widget",
    "hide_chart_switch_overlay",
    "open_tradingview_external",
    "prime_tradingview_chart",
    "show_chart_switch_overlay",
    "update_chart_overlay_geometry",
]
