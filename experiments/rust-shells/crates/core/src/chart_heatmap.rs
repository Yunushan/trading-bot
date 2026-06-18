use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::generated_python_parity::{
    PYTHON_DEFAULT_CHART_SYMBOLS, PYTHON_TRADINGVIEW_INTERVAL_MAP, PythonTradingViewInterval,
};

pub const LIGHTWEIGHT_LOCAL_ASSET: &str =
    "Languages/Python/app/assets/lightweight-charts.standalone.production.js";
pub const LIGHTWEIGHT_CDN_SOURCES: &[&str] = &[
    "https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js",
    "https://cdn.jsdelivr.net/npm/lightweight-charts/dist/lightweight-charts.standalone.production.js",
];
pub const SAFE_MODE_STATUS: &str =
    "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.";
pub const SAFE_TRADINGVIEW_EXTERNAL_STATUS: &str =
    "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.";
pub const SAFE_TRADINGVIEW_BLOCKED_STATUS: &str =
    "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ChartStatePayload {
    pub market: String,
    pub symbol: String,
    pub api_symbol: String,
    pub display_symbol: String,
    pub interval: String,
    pub tradingview_interval: String,
    pub view_mode: String,
    pub tradingview_symbol: String,
    pub auto_follow: bool,
    pub default_symbols: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ChartViewModeDecision {
    pub requested_mode: String,
    pub actual_mode: String,
    pub external_url: Option<String>,
    pub status_message: String,
    pub fallback_reason: String,
    pub render_legacy_chart: bool,
    pub should_reload: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandlePayload {
    pub time: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LiquidationHeatmapProvider {
    pub key: &'static str,
    pub label: &'static str,
    pub title: &'static str,
    pub url: &'static str,
    pub parent_tab: &'static str,
}

pub fn normalize_chart_market(value: impl AsRef<str>) -> String {
    let text = value.as_ref().trim().to_lowercase();
    if text.starts_with("spot") {
        "Spot".to_owned()
    } else {
        "Futures".to_owned()
    }
}

pub fn normalize_chart_interval_key(value: impl AsRef<str>) -> String {
    let source = value.as_ref().trim();
    if source.is_empty() {
        return String::new();
    }
    if source.ends_with('M') {
        let digits = source.trim_end_matches('M');
        if digits.chars().all(|ch| ch.is_ascii_digit()) && !digits.is_empty() {
            return format!("{digits}mo");
        }
    }
    let raw = source.to_lowercase();
    let collapsed = raw
        .replace("minutes", "m")
        .replace("minute", "m")
        .replace("mins", "m")
        .replace("min", "m")
        .replace("hours", "h")
        .replace("hour", "h")
        .replace("days", "d")
        .replace("day", "d")
        .replace("weeks", "w")
        .replace("week", "w")
        .replace(' ', "");
    if collapsed.chars().all(|ch| ch.is_ascii_digit()) {
        return normalize_minute_interval(collapsed.parse::<i64>().unwrap_or_default());
    }
    if let Some(minutes) = collapsed
        .strip_suffix('m')
        .and_then(|v| v.parse::<i64>().ok())
    {
        return normalize_minute_interval(minutes);
    }
    if collapsed == "1month" || collapsed == "1months" {
        return "1mo".to_owned();
    }
    collapsed
}

fn normalize_minute_interval(minutes: i64) -> String {
    if minutes > 0 && minutes % 60 == 0 {
        format!("{}h", minutes / 60)
    } else if minutes > 0 {
        format!("{minutes}m")
    } else {
        String::new()
    }
}

pub fn canonicalize_chart_interval(value: impl AsRef<str>) -> String {
    let normalized = normalize_chart_interval_key(value);
    if normalized == "1mo" {
        "1M".to_owned()
    } else {
        normalized
    }
}

pub fn tradingview_interval_by_key(
    value: impl AsRef<str>,
) -> Option<&'static PythonTradingViewInterval> {
    let key = normalize_chart_interval_key(value);
    PYTHON_TRADINGVIEW_INTERVAL_MAP
        .iter()
        .find(|item| item.interval.eq_ignore_ascii_case(&key))
}

pub fn map_tradingview_interval(value: impl AsRef<str>) -> Option<String> {
    let key = normalize_chart_interval_key(value);
    if key.is_empty() {
        return None;
    }
    if let Some(item) = tradingview_interval_by_key(&key) {
        return Some(item.code.to_owned());
    }
    parse_interval_to_tradingview_code(&key)
}

fn parse_interval_to_tradingview_code(key: &str) -> Option<String> {
    if let Some(minutes) = key.strip_suffix('m') {
        return positive_float_to_i64(minutes).map(|value| value.to_string());
    }
    if let Some(hours) = key.strip_suffix('h') {
        return positive_float_to_i64(hours).map(|value| (value * 60).to_string());
    }
    if let Some(days) = key.strip_suffix('d') {
        return positive_float_to_i64(days).map(|value| format!("{value}D"));
    }
    if let Some(weeks) = key.strip_suffix('w') {
        return positive_float_to_i64(weeks).map(|value| format!("{value}W"));
    }
    if key.ends_with("mo") || key.ends_with("month") || key.ends_with("months") {
        let qty = digits_or_one(key);
        return (qty > 0).then(|| format!("{qty}M"));
    }
    if key.ends_with('y') || key.ends_with("year") || key.ends_with("years") {
        let qty = digits_or_one(key);
        return (qty > 0).then(|| format!("{}M", qty * 12));
    }
    None
}

fn positive_float_to_i64(value: &str) -> Option<i64> {
    let parsed = value.parse::<f64>().ok()?;
    (parsed > 0.0).then_some(parsed as i64)
}

fn digits_or_one(value: &str) -> i64 {
    let digits: String = value.chars().filter(char::is_ascii_digit).collect();
    digits.parse::<i64>().unwrap_or(1).max(1)
}

pub fn futures_display_symbol(value: impl AsRef<str>) -> String {
    let symbol = value.as_ref().trim().to_uppercase();
    if symbol.ends_with(".P") || symbol.is_empty() {
        return symbol;
    }
    if symbol.ends_with("USDT") && !symbol.ends_with("BUSD") {
        format!("{symbol}.P")
    } else {
        symbol
    }
}

pub fn resolve_chart_symbol_for_api(
    value: impl AsRef<str>,
    market: impl AsRef<str>,
    alias_pairs: &[(&str, &str)],
) -> String {
    let symbol = value.as_ref().trim().to_uppercase();
    if normalize_chart_market(market) == "Futures" {
        if let Some((_, actual)) = alias_pairs
            .iter()
            .find(|(alias, _)| alias.trim().eq_ignore_ascii_case(&symbol))
        {
            return actual.trim().to_uppercase();
        }
        if let Some(stripped) = symbol.strip_suffix(".P") {
            return stripped.to_owned();
        }
    }
    symbol
}

pub fn format_tradingview_symbol(value: impl AsRef<str>, account_hint: impl AsRef<str>) -> String {
    let raw = value.as_ref().trim().to_uppercase().replace('/', "");
    if raw.contains(':') {
        return raw;
    }
    let account = account_hint.as_ref().trim().to_lowercase();
    let prefix = if account.contains("bybit") {
        "BYBIT:"
    } else {
        "BINANCE:"
    };
    format!("{prefix}{raw}")
}

pub fn build_chart_state_payload(
    market: impl AsRef<str>,
    symbol: impl AsRef<str>,
    interval: impl AsRef<str>,
    view_mode: impl AsRef<str>,
    auto_follow: bool,
) -> ChartStatePayload {
    let market = normalize_chart_market(market);
    let display_symbol = if market == "Futures" {
        futures_display_symbol(symbol.as_ref())
    } else {
        symbol.as_ref().trim().to_uppercase()
    };
    let api_symbol = resolve_chart_symbol_for_api(&display_symbol, &market, &[]);
    let interval = canonicalize_chart_interval(interval);
    let tradingview_interval = map_tradingview_interval(&interval).unwrap_or_default();
    ChartStatePayload {
        market,
        symbol: display_symbol.clone(),
        api_symbol: api_symbol.clone(),
        display_symbol,
        interval,
        tradingview_interval,
        view_mode: view_mode.as_ref().trim().to_lowercase(),
        tradingview_symbol: format_tradingview_symbol(api_symbol, "futures"),
        auto_follow,
        default_symbols: PYTHON_DEFAULT_CHART_SYMBOLS
            .iter()
            .map(|item| (*item).to_owned())
            .collect(),
    }
}

pub fn build_lightweight_payload(
    candles: &[CandlePayload],
    enabled_indicators: &[&str],
    theme_name: impl AsRef<str>,
    overlays: Vec<Value>,
    panes: Vec<Value>,
) -> Value {
    let enabled: BTreeSet<String> = enabled_indicators
        .iter()
        .map(|item| item.trim().to_lowercase())
        .filter(|item| !item.is_empty())
        .collect();
    let candle_values: Vec<Value> = candles
        .iter()
        .map(|candle| {
            json!({
                "time": candle.time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
            })
        })
        .collect();
    let volume_values: Vec<Value> = if enabled.contains("volume") {
        candles
            .iter()
            .map(|candle| {
                json!({
                    "time": candle.time,
                    "value": candle.volume,
                    "color": if candle.close >= candle.open { "#0ebb7a" } else { "#f75467" },
                })
            })
            .collect()
    } else {
        Vec::new()
    };
    let theme = if theme_name
        .as_ref()
        .trim()
        .to_lowercase()
        .starts_with("light")
    {
        "light"
    } else {
        "dark"
    };
    json!({
        "candles": candle_values,
        "volume": volume_values,
        "overlays": overlays,
        "panes": panes,
        "theme": theme,
    })
}

pub fn lightweight_asset_sources(local_asset_available: bool) -> Vec<String> {
    let mut sources = Vec::new();
    if local_asset_available {
        sources.push(format!("file://{LIGHTWEIGHT_LOCAL_ASSET}"));
    }
    sources.extend(
        LIGHTWEIGHT_CDN_SOURCES
            .iter()
            .map(|item| (*item).to_owned()),
    );
    sources
}

pub fn build_chart_view_mode_guard_decision(
    requested_mode: impl AsRef<str>,
    safe_mode_enabled: bool,
    external_opened: bool,
) -> ChartViewModeDecision {
    let mode = requested_mode.as_ref().trim().to_lowercase();
    if safe_mode_enabled && matches!(mode.as_str(), "tradingview" | "original" | "lightweight") {
        let (status_message, external_url) = if mode == "tradingview" && external_opened {
            (
                SAFE_TRADINGVIEW_EXTERNAL_STATUS.to_owned(),
                Some(build_tradingview_url("BINANCE:BTCUSDT", "60")),
            )
        } else if mode == "tradingview" {
            (SAFE_TRADINGVIEW_BLOCKED_STATUS.to_owned(), None)
        } else {
            (SAFE_MODE_STATUS.to_owned(), None)
        };
        return ChartViewModeDecision {
            requested_mode: mode,
            actual_mode: "original".to_owned(),
            external_url,
            status_message,
            fallback_reason: "BOT_SAFE_CHART_TAB".to_owned(),
            render_legacy_chart: true,
            should_reload: true,
        };
    }
    ChartViewModeDecision {
        requested_mode: mode.clone(),
        actual_mode: mode,
        external_url: None,
        status_message: String::new(),
        fallback_reason: String::new(),
        render_legacy_chart: false,
        should_reload: false,
    }
}

pub fn build_tradingview_url(symbol: impl AsRef<str>, interval_code: impl AsRef<str>) -> String {
    format!(
        "https://www.tradingview.com/chart/?symbol={}&interval={}",
        symbol.as_ref().trim(),
        interval_code.as_ref().trim()
    )
}

pub fn liquidation_heatmap_providers() -> &'static [LiquidationHeatmapProvider] {
    &[
        LiquidationHeatmapProvider {
            key: "coinglass-model-1",
            label: "Model 1",
            title: "Coinglass Heatmap Model 1",
            url: "https://www.coinglass.com/pro/futures/LiquidationHeatMap",
            parent_tab: "Coinglass Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "coinglass-model-2",
            label: "Model 2",
            title: "Coinglass Heatmap Model 2",
            url: "https://www.coinglass.com/pro/futures/LiquidationHeatMapNew",
            parent_tab: "Coinglass Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "coinglass-model-3",
            label: "Model 3",
            title: "Coinglass Heatmap Model 3",
            url: "https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3",
            parent_tab: "Coinglass Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "coinank",
            label: "Coinank",
            title: "Coinank Liquidation Heatmap",
            url: "https://coinank.com/chart/derivatives/liq-heat-map",
            parent_tab: "Liquidation Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "bitcoin-counterflow",
            label: "Bitcoin Counterflow",
            title: "Bitcoin Counterflow Liquidation Heatmap",
            url: "https://www.bitcoincounterflow.com/liquidation-heatmap/",
            parent_tab: "Liquidation Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "hyblock-capital",
            label: "Hyblock Capital",
            title: "Hyblock Capital Liquidation Heatmap",
            url: "https://hyblockcapital.com/",
            parent_tab: "Liquidation Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "coinglass-map",
            label: "Coinglass Map",
            title: "Coinglass Liquidation Map",
            url: "https://www.coinglass.com/pro/futures/LiquidationMap",
            parent_tab: "Liquidation Heatmap",
        },
        LiquidationHeatmapProvider {
            key: "hyperliquid-map",
            label: "Hyperliquid Map",
            title: "Hyperliquid Liquidation Map",
            url: "https://www.coinglass.com/hyperliquid-liquidation-map",
            parent_tab: "Liquidation Heatmap",
        },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interval_aliases_match_python_chart_selection() {
        assert_eq!(canonicalize_chart_interval("60m"), "1h");
        assert_eq!(canonicalize_chart_interval("1month"), "1M");
        assert_eq!(map_tradingview_interval("60m").as_deref(), Some("60"));
        assert_eq!(map_tradingview_interval("1H").as_deref(), Some("60"));
        assert_eq!(map_tradingview_interval("1month").as_deref(), Some("1M"));
        assert_eq!(map_tradingview_interval("2 years").as_deref(), Some("24M"));
    }

    #[test]
    fn chart_state_payload_mirrors_python_chart_config() {
        let payload = build_chart_state_payload("futures", "btcusdt", "60m", "TradingView", true);
        assert_eq!(payload.market, "Futures");
        assert_eq!(payload.symbol, "BTCUSDT.P");
        assert_eq!(payload.api_symbol, "BTCUSDT");
        assert_eq!(payload.interval, "1h");
        assert_eq!(payload.tradingview_interval, "60");
        assert_eq!(payload.tradingview_symbol, "BINANCE:BTCUSDT");
        assert!(payload.auto_follow);
        assert!(payload.default_symbols.contains(&"BTCUSDT".to_owned()));
    }

    #[test]
    fn lightweight_payload_and_asset_fallbacks_match_python_shape() {
        let candles = vec![
            CandlePayload {
                time: 1,
                open: 100.0,
                high: 110.0,
                low: 90.0,
                close: 105.0,
                volume: 12.0,
            },
            CandlePayload {
                time: 2,
                open: 105.0,
                high: 106.0,
                low: 95.0,
                close: 96.0,
                volume: 7.5,
            },
        ];
        let payload = build_lightweight_payload(&candles, &["volume"], "Light", vec![], vec![]);
        assert_eq!(payload["theme"], "light");
        assert_eq!(payload["candles"].as_array().unwrap().len(), 2);
        assert_eq!(payload["volume"][0]["color"], "#0ebb7a");
        assert_eq!(payload["volume"][1]["color"], "#f75467");

        let sources = lightweight_asset_sources(true);
        assert!(sources[0].starts_with("file://"));
        assert!(sources[1].contains("unpkg.com/lightweight-charts"));
        assert!(sources[2].contains("cdn.jsdelivr.net/npm/lightweight-charts"));
    }

    #[test]
    fn heatmap_provider_catalog_matches_python_liquidation_tab() {
        let providers = liquidation_heatmap_providers();
        assert_eq!(providers.len(), 8);
        assert_eq!(
            providers[0].url,
            "https://www.coinglass.com/pro/futures/LiquidationHeatMap"
        );
        assert!(providers.iter().any(|provider| provider.label == "Coinank"
            && provider.url == "https://coinank.com/chart/derivatives/liq-heat-map"));
        assert!(
            providers
                .iter()
                .any(|provider| provider.label == "Hyperliquid Map"
                    && provider.url == "https://www.coinglass.com/hyperliquid-liquidation-map")
        );
    }

    #[test]
    fn safe_mode_guard_falls_back_to_original_like_python() {
        let decision = build_chart_view_mode_guard_decision("lightweight", true, false);
        assert_eq!(decision.actual_mode, "original");
        assert_eq!(decision.status_message, SAFE_MODE_STATUS);
        assert!(decision.render_legacy_chart);
        assert!(decision.should_reload);

        let tradingview = build_chart_view_mode_guard_decision("tradingview", true, true);
        assert_eq!(tradingview.actual_mode, "original");
        assert_eq!(tradingview.status_message, SAFE_TRADINGVIEW_EXTERNAL_STATUS);
        assert!(
            tradingview
                .external_url
                .unwrap()
                .contains("tradingview.com/chart")
        );
    }
}
