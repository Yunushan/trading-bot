use std::cmp::Ordering;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use reqwest::blocking::Client;
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinanceMarket {
    Futures,
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

impl BinanceMarket {
    pub fn default_base_url(self, testnet: bool) -> &'static str {
        match (self, testnet) {
            (Self::Futures, true) => "https://testnet.binancefuture.com",
            (Self::Futures, false) => "https://fapi.binance.com",
            (Self::Spot, true) => "https://testnet.binance.vision",
            (Self::Spot, false) => "https://api.binance.com",
        }
    }

    fn exchange_info_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/exchangeInfo",
            Self::Spot => "/api/v3/exchangeInfo",
        }
    }

    fn ticker_24h_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/ticker/24hr",
            Self::Spot => "/api/v3/ticker/24hr",
        }
    }

    fn klines_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/klines",
            Self::Spot => "/api/v3/klines",
        }
    }

    fn ticker_price_path(self) -> &'static str {
        match self {
            Self::Futures => "/fapi/v1/ticker/price",
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
        let safe_limit = limit.clamp(10, 1000).to_string();
        let payload = self.get_json(
            &self.klines_url(),
            &[
                ("symbol", clean_symbol.as_str()),
                ("interval", clean_interval.as_str()),
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
        if market == BinanceMarket::Futures
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
    let interval = value.trim().to_owned();
    if interval.is_empty() {
        bail!("interval is required");
    }
    Ok(interval)
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

        assert_eq!(
            futures.exchange_info_url(),
            "https://example.test/fapi/v1/exchangeInfo"
        );
        assert_eq!(futures.klines_url(), "https://example.test/fapi/v1/klines");
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
