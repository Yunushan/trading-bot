use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use reqwest::blocking::Client;
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinanceMarket {
    Futures,
    CoinFutures,
    Spot,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceKlineCandle {
    pub open_time_ms: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceTickerPrice {
    pub symbol: String,
    pub price: f64,
}

#[derive(Debug, Clone)]
pub struct BinanceRestMarketDataClient {
    http: Client,
    market: BinanceMarket,
    base_url: String,
}

const BINANCE_NATIVE_INTERVALS: &[&str] = &[
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M",
];

impl BinanceMarket {
    pub fn default_base_url(self, testnet: bool) -> &'static str {
        match (self, testnet) {
            (Self::Futures, true) => "https://testnet.binancefuture.com",
            (Self::Futures, false) => "https://fapi.binance.com",
            (Self::CoinFutures, true) => "https://testnet.binancefuture.com",
            (Self::CoinFutures, false) => "https://dapi.binance.com",
            (Self::Spot, true) => "https://testnet.binance.vision",
            (Self::Spot, false) => "https://api.binance.com",
        }
    }

    pub fn is_futures(self) -> bool {
        matches!(self, Self::Futures | Self::CoinFutures)
    }

    pub(crate) fn futures_api_prefix(self) -> &'static str {
        match self {
            Self::Futures => "/fapi",
            Self::CoinFutures => "/dapi",
            Self::Spot => "",
        }
    }

    fn exchange_info_path(self) -> &'static str {
        match self {
            Self::Futures | Self::CoinFutures => match self {
                Self::Futures => "/fapi/v1/exchangeInfo",
                Self::CoinFutures => "/dapi/v1/exchangeInfo",
                Self::Spot => unreachable!(),
            },
            Self::Spot => "/api/v3/exchangeInfo",
        }
    }

    fn ticker_24h_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/ticker/24hr",
            Self::CoinFutures => "/dapi/v1/ticker/24hr",
            Self::Spot => "/api/v3/ticker/24hr",
        }
    }

    fn klines_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/klines",
            Self::CoinFutures => "/dapi/v1/klines",
            Self::Spot => "/api/v3/klines",
        }
    }

    fn ticker_price_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/ticker/price",
            Self::CoinFutures => "/dapi/v1/ticker/price",
            Self::Spot => "/api/v3/ticker/price",
        }
    }
}

impl BinanceRestMarketDataClient {
    pub fn new(market: BinanceMarket, testnet: bool) -> Result<Self> {
        Self::with_base_url(market, market.default_base_url(testnet))
    }

    pub fn with_base_url(market: BinanceMarket, base_url: impl Into<String>) -> Result<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(10))
            .user_agent("trading-bot-rust/0.1")
            .build()
            .context("build Binance REST market-data HTTP client")?;
        Self::with_http_client(market, base_url, http)
    }

    pub fn with_http_client(
        market: BinanceMarket,
        base_url: impl Into<String>,
        http: Client,
    ) -> Result<Self> {
        let base_url = normalize_base_url(base_url.into())?;
        Ok(Self {
            http,
            market,
            base_url,
        })
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub fn exchange_info_url(&self) -> String {
        self.url_for_path(self.market.exchange_info_path())
    }

    pub fn ticker_24h_url(&self) -> String {
        self.url_for_path(self.market.ticker_24h_path())
    }

    pub fn klines_url(&self) -> String {
        self.url_for_path(self.market.klines_path())
    }

    pub fn ticker_price_url(&self) -> String {
        self.url_for_path(self.market.ticker_price_path())
    }

    pub fn fetch_usdt_symbols(
        &self,
        sort_by_volume: bool,
        top_n: Option<usize>,
    ) -> Result<Vec<String>> {
        let exchange_info = self.get_json(&self.exchange_info_url(), &[])?;
        let mut symbols = parse_usdt_symbols(&exchange_info, self.market)?;
        if sort_by_volume && !symbols.is_empty() {
            let ticker_24h = self.get_json(&self.ticker_24h_url(), &[])?;
            sort_symbols_by_quote_volume(&mut symbols, &ticker_24h)?;
        }
        if let Some(limit) = top_n.filter(|limit| *limit > 0) {
            symbols.truncate(limit);
        }
        Ok(symbols)
    }

    pub fn fetch_klines(
        &self,
        symbol: impl AsRef<str>,
        interval: impl AsRef<str>,
        limit: usize,
    ) -> Result<Vec<BinanceKlineCandle>> {
        let clean_symbol = normalize_symbol(symbol.as_ref())?;
        let clean_interval = normalize_interval(interval.as_ref())?;
        let safe_limit = limit.clamp(10, 1000);
        if let Some(base_interval) = custom_interval_base(&clean_interval, self.market)? {
            let requested_interval_seconds = interval_seconds(&clean_interval)?;
            let base_seconds = interval_seconds(base_interval)?;
            let factor = (requested_interval_seconds / base_seconds).ceil().max(1.0) as usize;
            let base_limit = safe_limit
                .saturating_mul(factor)
                .saturating_add(factor)
                .clamp(10, 1000);
            let base_candles =
                self.fetch_native_klines(&clean_symbol, base_interval, base_limit)?;
            let aggregated = aggregate_klines_to_interval(&base_candles, &clean_interval)?;
            if aggregated.len() <= safe_limit {
                return Ok(aggregated);
            }
            return Ok(aggregated[aggregated.len() - safe_limit..].to_vec());
        }
        self.fetch_native_klines(&clean_symbol, &clean_interval, safe_limit)
    }

    fn fetch_native_klines(
        &self,
        clean_symbol: &str,
        clean_interval: &str,
        safe_limit: usize,
    ) -> Result<Vec<BinanceKlineCandle>> {
        let safe_limit = safe_limit.clamp(10, 1000).to_string();
        let payload = self.get_json(
            &self.klines_url(),
            &[
                ("symbol", clean_symbol),
                ("interval", clean_interval),
                ("limit", safe_limit.as_str()),
            ],
        )?;
        parse_klines(&payload)
    }

    pub fn fetch_ticker_price(&self, symbol: impl AsRef<str>) -> Result<BinanceTickerPrice> {
        let clean_symbol = normalize_symbol(symbol.as_ref())?;
        let payload = self.get_json(
            &self.ticker_price_url(),
            &[("symbol", clean_symbol.as_str())],
        )?;
        parse_ticker_price(&payload)
    }

    fn url_for_path(&self, path: &str) -> String {
        format!("{}{}", self.base_url, path)
    }

    fn get_json(&self, url: &str, query: &[(&str, &str)]) -> Result<Value> {
        let response = self
            .http
            .get(url)
            .query(query)
            .send()
            .with_context(|| format!("GET {url}"))?;
        let status = response.status();
        let payload = response
            .text()
            .with_context(|| format!("read Binance response body from {url}"))?;
        if !status.is_success() {
            bail!("Binance REST {url} returned HTTP {status}: {payload}");
        }
        let value: Value = serde_json::from_str(&payload)
            .with_context(|| format!("parse Binance JSON response from {url}"))?;
        ensure_not_binance_error(&value)?;
        Ok(value)
    }
}

pub fn parse_usdt_symbols(exchange_info: &Value, market: BinanceMarket) -> Result<Vec<String>> {
    ensure_not_binance_error(exchange_info)?;
    let symbols = exchange_info
        .get("symbols")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("exchangeInfo response missing symbols array"))?;
    let mut collected = Vec::new();
    for entry in symbols {
        let Some(row) = entry.as_object() else {
            continue;
        };
        if row.get("quoteAsset").and_then(Value::as_str) != Some("USDT") {
            continue;
        }
        if row
            .get("status")
            .and_then(Value::as_str)
            .map(str::to_uppercase)
            .as_deref()
            != Some("TRADING")
        {
            continue;
        }
        if market.is_futures()
            && row
                .get("contractType")
                .and_then(Value::as_str)
                .map(str::to_uppercase)
                .as_deref()
                != Some("PERPETUAL")
        {
            continue;
        }
        let Some(symbol) = row.get("symbol").and_then(Value::as_str) else {
            continue;
        };
        let symbol = symbol.trim().to_uppercase();
        if !symbol.is_empty() && !collected.contains(&symbol) {
            collected.push(symbol);
        }
    }
    collected.sort();
    Ok(collected)
}

pub fn sort_symbols_by_quote_volume(symbols: &mut [String], ticker_24h: &Value) -> Result<()> {
    ensure_not_binance_error(ticker_24h)?;
    let tickers = ticker_24h
        .as_array()
        .ok_or_else(|| anyhow!("24h ticker response must be an array"))?;
    let mut quote_volume_by_symbol = std::collections::HashMap::<String, f64>::new();
    for entry in tickers {
        let Some(row) = entry.as_object() else {
            continue;
        };
        let Some(symbol) = row.get("symbol").and_then(Value::as_str) else {
            continue;
        };
        if let Some(quote_volume) = parse_json_f64(row.get("quoteVolume")) {
            quote_volume_by_symbol.insert(symbol.trim().to_uppercase(), quote_volume);
        }
    }
    symbols.sort_by(|a, b| {
        let a_volume = quote_volume_by_symbol
            .get(&a.to_uppercase())
            .copied()
            .unwrap_or(0.0);
        let b_volume = quote_volume_by_symbol
            .get(&b.to_uppercase())
            .copied()
            .unwrap_or(0.0);
        b_volume
            .partial_cmp(&a_volume)
            .unwrap_or(Ordering::Equal)
            .then_with(|| a.cmp(b))
    });
    Ok(())
}

pub fn parse_klines(payload: &Value) -> Result<Vec<BinanceKlineCandle>> {
    ensure_not_binance_error(payload)?;
    let rows = payload
        .as_array()
        .ok_or_else(|| anyhow!("kline response must be an array"))?;
    let mut candles = Vec::with_capacity(rows.len());
    for row in rows {
        let Some(values) = row.as_array() else {
            continue;
        };
        if values.len() < 6 {
            continue;
        }
        let Some(open_time_ms) = parse_json_i64(values.first()) else {
            continue;
        };
        let (Some(open), Some(high), Some(low), Some(close), Some(volume)) = (
            parse_json_f64(values.get(1)),
            parse_json_f64(values.get(2)),
            parse_json_f64(values.get(3)),
            parse_json_f64(values.get(4)),
            parse_json_f64(values.get(5)),
        ) else {
            continue;
        };
        candles.push(BinanceKlineCandle {
            open_time_ms,
            open,
            high,
            low,
            close,
            volume,
        });
    }
    if candles.is_empty() {
        bail!("no valid kline candles returned");
    }
    Ok(candles)
}

pub fn aggregate_klines_to_interval(
    candles: &[BinanceKlineCandle],
    interval: impl AsRef<str>,
) -> Result<Vec<BinanceKlineCandle>> {
    let clean_interval = normalize_interval(interval.as_ref())?;
    let interval_ms = interval_millis(&clean_interval)?;
    if interval_ms < 60_000 {
        bail!("Custom interval '{clean_interval}' below 1 minute is not supported.");
    }

    let mut sorted = candles.to_vec();
    sorted.sort_by_key(|candle| candle.open_time_ms);

    let mut buckets = BTreeMap::<i64, BinanceKlineCandle>::new();
    for candle in sorted {
        if ![
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        ]
        .iter()
        .all(|value| value.is_finite())
        {
            continue;
        }
        let bucket_open_time = candle.open_time_ms.div_euclid(interval_ms) * interval_ms;
        buckets
            .entry(bucket_open_time)
            .and_modify(|bucket| {
                bucket.high = bucket.high.max(candle.high);
                bucket.low = bucket.low.min(candle.low);
                bucket.close = candle.close;
                bucket.volume += candle.volume;
            })
            .or_insert_with(|| BinanceKlineCandle {
                open_time_ms: bucket_open_time,
                open: candle.open,
                high: candle.high,
                low: candle.low,
                close: candle.close,
                volume: candle.volume,
            });
    }

    let aggregated: Vec<_> = buckets.into_values().collect();
    if aggregated.is_empty() {
        bail!("no valid kline candles returned");
    }
    Ok(aggregated)
}

pub fn custom_interval_base(
    interval: impl AsRef<str>,
    _market: BinanceMarket,
) -> Result<Option<&'static str>> {
    let clean_interval = normalize_interval(interval.as_ref())?;
    if is_native_interval(&clean_interval) {
        return Ok(None);
    }

    let interval_ms = interval_millis(&clean_interval)?;
    if interval_ms < 60_000 {
        bail!("Custom interval '{clean_interval}' below 1 minute is not supported.");
    }

    let (base_interval, base_ms) = if interval_ms < 3_600_000 {
        ("1m", 60_000)
    } else if interval_ms < 86_400_000 {
        ("1h", 3_600_000)
    } else {
        ("1d", 86_400_000)
    };
    if interval_ms % base_ms != 0 {
        bail!("Custom interval '{clean_interval}' is not a multiple of {base_interval}.");
    }
    Ok(Some(base_interval))
}

pub fn interval_seconds(interval: impl AsRef<str>) -> Result<f64> {
    let raw = interval.as_ref().trim();
    if raw.is_empty() {
        return Ok(60.0);
    }
    let lower = raw.to_ascii_lowercase();
    let (amount_text, unit_multiplier) =
        interval_amount_and_unit_multiplier(&lower).unwrap_or((lower.as_str(), 1.0));
    let amount = amount_text
        .trim()
        .parse::<f64>()
        .with_context(|| format!("parse interval amount from '{raw}'"))?;
    if !amount.is_finite() || amount <= 0.0 {
        bail!("interval must be positive");
    }
    Ok((amount * unit_multiplier).max(1.0))
}

pub fn parse_ticker_price(payload: &Value) -> Result<BinanceTickerPrice> {
    ensure_not_binance_error(payload)?;
    let obj = payload
        .as_object()
        .ok_or_else(|| anyhow!("ticker price response must be an object"))?;
    let symbol = obj
        .get("symbol")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_uppercase();
    if symbol.is_empty() {
        bail!("ticker price response missing symbol");
    }
    let price = parse_json_f64(obj.get("price"))
        .filter(|value| value.is_finite() && *value > 0.0)
        .ok_or_else(|| anyhow!("ticker price missing for {symbol}"))?;
    Ok(BinanceTickerPrice { symbol, price })
}

fn normalize_base_url(value: String) -> Result<String> {
    let trimmed = value.trim().trim_end_matches('/').to_owned();
    if trimmed.is_empty() {
        bail!("base URL is required");
    }
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        bail!("base URL must start with http:// or https://");
    }
    Ok(trimmed)
}

fn normalize_symbol(value: &str) -> Result<String> {
    let symbol = value.trim().to_uppercase();
    if symbol.is_empty() {
        bail!("symbol is required");
    }
    Ok(symbol)
}

fn normalize_interval(value: &str) -> Result<String> {
    let raw = value.trim();
    if raw.is_empty() {
        bail!("interval is required");
    }
    if raw == "1M" {
        return Ok("1M".to_owned());
    }
    let lower = raw.to_ascii_lowercase();
    if matches!(lower.as_str(), "1mo" | "1mon" | "1month" | "1months") {
        return Ok("1M".to_owned());
    }
    Ok(lower)
}

fn is_native_interval(interval: &str) -> bool {
    BINANCE_NATIVE_INTERVALS.contains(&interval)
}

fn interval_millis(interval: &str) -> Result<i64> {
    let seconds = interval_seconds(interval)?;
    let millis = seconds * 1000.0;
    if !millis.is_finite() || millis < 1.0 {
        bail!("interval must be positive");
    }
    let rounded = millis.round();
    if (millis - rounded).abs() > f64::EPSILON {
        bail!("interval must resolve to whole milliseconds");
    }
    Ok(rounded as i64)
}

fn interval_amount_and_unit_multiplier(lower: &str) -> Option<(&str, f64)> {
    for (suffix, multiplier) in [
        ("months", 30.0 * 86_400.0),
        ("month", 30.0 * 86_400.0),
        ("mons", 30.0 * 86_400.0),
        ("mon", 30.0 * 86_400.0),
        ("mo", 30.0 * 86_400.0),
        ("years", 365.0 * 86_400.0),
        ("year", 365.0 * 86_400.0),
        ("y", 365.0 * 86_400.0),
        ("w", 7.0 * 86_400.0),
        ("d", 86_400.0),
        ("h", 3_600.0),
        ("m", 60.0),
        ("s", 1.0),
    ] {
        if let Some(amount) = lower.strip_suffix(suffix) {
            return Some((amount, multiplier));
        }
    }
    None
}

fn parse_json_f64(value: Option<&Value>) -> Option<f64> {
    match value? {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn parse_json_i64(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn ensure_not_binance_error(value: &Value) -> Result<()> {
    let Some(obj) = value.as_object() else {
        return Ok(());
    };
    if obj.contains_key("code") && obj.contains_key("msg") {
        let message = obj
            .get("msg")
            .and_then(Value::as_str)
            .unwrap_or("Binance API error");
        bail!("{message}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn market_base_urls_match_binance_surfaces() {
        assert_eq!(
            BinanceMarket::Futures.default_base_url(false),
            "https://fapi.binance.com"
        );
        assert_eq!(
            BinanceMarket::Futures.default_base_url(true),
            "https://testnet.binancefuture.com"
        );
        assert_eq!(
            BinanceMarket::CoinFutures.default_base_url(false),
            "https://dapi.binance.com"
        );
        assert_eq!(
            BinanceMarket::CoinFutures.default_base_url(true),
            "https://testnet.binancefuture.com"
        );
        assert_eq!(
            BinanceMarket::Spot.default_base_url(false),
            "https://api.binance.com"
        );
        assert_eq!(
            BinanceMarket::Spot.default_base_url(true),
            "https://testnet.binance.vision"
        );
    }

    #[test]
    fn client_builds_cpp_equivalent_endpoint_paths() {
        let futures = BinanceRestMarketDataClient::with_base_url(
            BinanceMarket::Futures,
            "https://example.test/",
        )
        .expect("futures client");
        let spot =
            BinanceRestMarketDataClient::with_base_url(BinanceMarket::Spot, "https://spot.test")
                .expect("spot client");
        let coin = BinanceRestMarketDataClient::with_base_url(
            BinanceMarket::CoinFutures,
            "https://coin.test",
        )
        .expect("Coin-M client");

        assert_eq!(
            futures.exchange_info_url(),
            "https://example.test/fapi/v1/exchangeInfo"
        );
        assert_eq!(futures.klines_url(), "https://example.test/fapi/v1/klines");
        assert_eq!(
            coin.exchange_info_url(),
            "https://coin.test/dapi/v1/exchangeInfo"
        );
        assert_eq!(coin.klines_url(), "https://coin.test/dapi/v1/klines");
        assert_eq!(
            coin.ticker_price_url(),
            "https://coin.test/dapi/v1/ticker/price"
        );
        assert_eq!(
            futures.ticker_price_url(),
            "https://example.test/fapi/v1/ticker/price"
        );
        assert_eq!(
            futures.ticker_24h_url(),
            "https://example.test/fapi/v1/ticker/24hr"
        );
        assert_eq!(
            spot.exchange_info_url(),
            "https://spot.test/api/v3/exchangeInfo"
        );
        assert_eq!(spot.klines_url(), "https://spot.test/api/v3/klines");
    }

    #[test]
    fn parses_usdt_perpetual_symbols_and_sorts_like_cpp() {
        let payload = json!({
            "symbols": [
                {"symbol": "ETHUSDT", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"},
                {"symbol": "BTCBUSD", "quoteAsset": "BUSD", "status": "TRADING", "contractType": "PERPETUAL"},
                {"symbol": "BNBUSDT", "quoteAsset": "USDT", "status": "BREAK", "contractType": "PERPETUAL"},
                {"symbol": "XRPUSDT", "quoteAsset": "USDT", "status": "TRADING", "contractType": "CURRENT_QUARTER"},
                {"symbol": "BTCUSDT", "quoteAsset": "USDT", "status": "TRADING", "contractType": "PERPETUAL"}
            ]
        });
        let mut symbols = parse_usdt_symbols(&payload, BinanceMarket::Futures).expect("symbols");
        assert_eq!(symbols, ["BTCUSDT", "ETHUSDT"]);

        let tickers = json!([
            {"symbol": "ETHUSDT", "quoteVolume": "100"},
            {"symbol": "BTCUSDT", "quoteVolume": "200"}
        ]);
        sort_symbols_by_quote_volume(&mut symbols, &tickers).expect("sort by volume");
        assert_eq!(symbols, ["BTCUSDT", "ETHUSDT"]);
    }

    #[test]
    fn spot_symbols_do_not_require_contract_type() {
        let payload = json!({
            "symbols": [
                {"symbol": "SOLUSDT", "quoteAsset": "USDT", "status": "TRADING"},
                {"symbol": "ADAUSDT", "quoteAsset": "USDT", "status": "TRADING"}
            ]
        });
        let symbols = parse_usdt_symbols(&payload, BinanceMarket::Spot).expect("symbols");
        assert_eq!(symbols, ["ADAUSDT", "SOLUSDT"]);
    }

    #[test]
    fn parses_klines_into_ohlcv_candles() {
        let payload = json!([
            [
                1710000000000_i64,
                "1.25",
                "2.50",
                "1.10",
                "2.00",
                "99.5",
                0,
                "0",
                0,
                "0",
                "0",
                "0"
            ],
            [
                1710000060000_i64,
                "2.00",
                "3.00",
                "1.90",
                "2.50",
                "100.5",
                0,
                "0",
                0,
                "0",
                "0",
                "0"
            ]
        ]);
        let candles = parse_klines(&payload).expect("klines");
        assert_eq!(candles.len(), 2);
        assert_eq!(candles[0].open_time_ms, 1710000000000);
        assert_eq!(candles[0].open, 1.25);
        assert_eq!(candles[1].close, 2.50);
        assert_eq!(candles[1].volume, 100.5);
    }

    #[test]
    fn custom_interval_base_matches_python_binance_fallbacks() {
        assert_eq!(
            custom_interval_base("10m", BinanceMarket::Futures).expect("10m"),
            Some("1m")
        );
        assert_eq!(
            custom_interval_base("3h", BinanceMarket::Futures).expect("3h"),
            Some("1h")
        );
        assert_eq!(
            custom_interval_base("2d", BinanceMarket::Futures).expect("2d"),
            Some("1d")
        );
        assert_eq!(
            custom_interval_base("1M", BinanceMarket::Futures).expect("1M"),
            None
        );
        assert_eq!(
            custom_interval_base("1month", BinanceMarket::Futures).expect("1month"),
            None
        );

        let sub_minute = custom_interval_base("45s", BinanceMarket::Futures)
            .expect_err("sub-minute custom intervals are unsupported");
        assert!(sub_minute.to_string().contains("below 1 minute"));

        let not_multiple = custom_interval_base("90m", BinanceMarket::Futures)
            .expect_err("90m cannot be composed from hourly candles");
        assert!(not_multiple.to_string().contains("multiple of 1h"));
    }

    #[test]
    fn custom_interval_klines_follow_python_resample_boundaries() {
        let candles = vec![
            BinanceKlineCandle {
                open_time_ms: 120_000,
                open: 12.0,
                high: 13.0,
                low: 11.5,
                close: 12.5,
                volume: 3.0,
            },
            BinanceKlineCandle {
                open_time_ms: 0,
                open: 10.0,
                high: 11.0,
                low: 9.5,
                close: 10.5,
                volume: 1.0,
            },
            BinanceKlineCandle {
                open_time_ms: 60_000,
                open: 10.5,
                high: 12.0,
                low: 10.0,
                close: 11.5,
                volume: 2.0,
            },
        ];

        let aggregated = aggregate_klines_to_interval(&candles, "2m").expect("aggregate 2m");

        assert_eq!(aggregated.len(), 2);
        assert_eq!(aggregated[0].open_time_ms, 0);
        assert_eq!(aggregated[0].open, 10.0);
        assert_eq!(aggregated[0].high, 12.0);
        assert_eq!(aggregated[0].low, 9.5);
        assert_eq!(aggregated[0].close, 11.5);
        assert_eq!(aggregated[0].volume, 3.0);
        assert_eq!(aggregated[1].open_time_ms, 120_000);
        assert_eq!(aggregated[1].open, 12.0);
        assert_eq!(aggregated[1].close, 12.5);
    }

    #[test]
    fn parses_ticker_price_and_binance_error_payloads() {
        let ticker =
            parse_ticker_price(&json!({"symbol": "btcusdt", "price": "65000.25"})).expect("ticker");
        assert_eq!(
            ticker,
            BinanceTickerPrice {
                symbol: "BTCUSDT".to_owned(),
                price: 65000.25,
            }
        );

        let error = parse_ticker_price(&json!({"code": -1121, "msg": "Invalid symbol."}))
            .expect_err("Binance errors should fail");
        assert!(error.to_string().contains("Invalid symbol"));
    }
}
