use std::net::TcpStream;

use anyhow::{Context, Result, anyhow, bail};
use serde_json::{Map, Value};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket, connect};

use crate::market_data::BinanceMarket;

pub type BinanceWebSocket = WebSocket<MaybeTlsStream<TcpStream>>;

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceBookTicker {
    pub symbol: String,
    pub bid_price: f64,
    pub ask_price: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceKlineStreamCandle {
    pub symbol: String,
    pub interval: String,
    pub open_time_ms: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub is_closed: bool,
    pub event_time_ms: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum BinanceStreamEvent {
    BookTicker(BinanceBookTicker),
    Kline(BinanceKlineStreamCandle),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinanceStreamKind {
    BookTicker,
    Kline,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinanceStreamSubscription {
    pub market: BinanceMarket,
    pub kind: BinanceStreamKind,
    pub symbol: String,
    pub interval: Option<String>,
    pub testnet: bool,
}

#[derive(Debug, Clone, Default)]
pub struct BinanceWebSocketClient;

impl BinanceWebSocketClient {
    pub fn new() -> Self {
        Self
    }

    pub fn book_ticker_subscription(
        market: BinanceMarket,
        symbol: impl AsRef<str>,
        testnet: bool,
    ) -> Result<BinanceStreamSubscription> {
        Ok(BinanceStreamSubscription {
            market,
            kind: BinanceStreamKind::BookTicker,
            symbol: normalize_stream_symbol(symbol.as_ref())?,
            interval: None,
            testnet,
        })
    }

    pub fn kline_subscription(
        market: BinanceMarket,
        symbol: impl AsRef<str>,
        interval: impl AsRef<str>,
        testnet: bool,
    ) -> Result<BinanceStreamSubscription> {
        Ok(BinanceStreamSubscription {
            market,
            kind: BinanceStreamKind::Kline,
            symbol: normalize_stream_symbol(symbol.as_ref())?,
            interval: Some(normalize_stream_interval(interval.as_ref())?),
            testnet,
        })
    }

    pub fn book_ticker_url(
        market: BinanceMarket,
        symbol: impl AsRef<str>,
        testnet: bool,
    ) -> Result<String> {
        let subscription = Self::book_ticker_subscription(market, symbol, testnet)?;
        Ok(subscription.url())
    }

    pub fn kline_url(
        market: BinanceMarket,
        symbol: impl AsRef<str>,
        interval: impl AsRef<str>,
        testnet: bool,
    ) -> Result<String> {
        let subscription = Self::kline_subscription(market, symbol, interval, testnet)?;
        Ok(subscription.url())
    }

    pub fn connect_subscription(
        &self,
        subscription: &BinanceStreamSubscription,
    ) -> Result<BinanceWebSocket> {
        let url = subscription.url();
        let (socket, _) = connect(url.as_str()).with_context(|| format!("connect {url}"))?;
        Ok(socket)
    }

    pub fn read_next_event(socket: &mut BinanceWebSocket) -> Result<Option<BinanceStreamEvent>> {
        loop {
            match socket.read().context("read Binance WebSocket message")? {
                Message::Text(text) => return parse_stream_event(text.as_str()).map(Some),
                Message::Binary(bytes) => {
                    let text =
                        std::str::from_utf8(&bytes).context("decode Binance WebSocket binary")?;
                    return parse_stream_event(text).map(Some);
                }
                Message::Ping(_) | Message::Pong(_) | Message::Frame(_) => continue,
                Message::Close(_) => return Ok(None),
            }
        }
    }
}

impl BinanceStreamSubscription {
    pub fn stream_name(&self) -> String {
        match self.kind {
            BinanceStreamKind::BookTicker => format!("{}@bookTicker", self.symbol),
            BinanceStreamKind::Kline => {
                let interval = self.interval.as_deref().unwrap_or_default();
                format!("{}@kline_{interval}", self.symbol)
            }
        }
    }

    pub fn base_url(&self) -> &'static str {
        websocket_base_url(self.market, self.testnet)
    }

    pub fn url(&self) -> String {
        format!("{}/{}", self.base_url(), self.stream_name())
    }
}

pub fn websocket_base_url(market: BinanceMarket, testnet: bool) -> &'static str {
    match (market, testnet) {
        (BinanceMarket::Futures, true) => "wss://stream.binancefuture.com/ws",
        (BinanceMarket::Futures, false) => "wss://fstream.binance.com/ws",
        (BinanceMarket::Spot, true) => "wss://testnet.binance.vision/ws",
        (BinanceMarket::Spot, false) => "wss://stream.binance.com:9443/ws",
    }
}

pub fn parse_stream_event(message: &str) -> Result<BinanceStreamEvent> {
    let payload: Value = serde_json::from_str(message).context("parse Binance stream JSON")?;
    parse_stream_event_value(&payload)
}

pub fn parse_stream_event_value(payload: &Value) -> Result<BinanceStreamEvent> {
    let obj = payload
        .as_object()
        .ok_or_else(|| anyhow!("Binance stream message must be an object"))?;
    let event_obj = obj.get("data").and_then(Value::as_object).unwrap_or(obj);

    if let Some(kline_obj) = event_obj.get("k").and_then(Value::as_object) {
        return parse_kline_event(event_obj, kline_obj).map(BinanceStreamEvent::Kline);
    }
    parse_book_ticker_event(event_obj).map(BinanceStreamEvent::BookTicker)
}

pub fn parse_book_ticker_event(row: &Map<String, Value>) -> Result<BinanceBookTicker> {
    let symbol = row
        .get("s")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_uppercase();
    if symbol.is_empty() {
        bail!("bookTicker message missing symbol");
    }
    let bid_price = parse_json_f64(row.get("b"))
        .filter(|value| value.is_finite())
        .ok_or_else(|| anyhow!("bookTicker message missing bid"))?;
    let ask_price = parse_json_f64(row.get("a"))
        .filter(|value| value.is_finite())
        .ok_or_else(|| anyhow!("bookTicker message missing ask"))?;
    Ok(BinanceBookTicker {
        symbol,
        bid_price,
        ask_price,
    })
}

pub fn parse_kline_event(
    parent: &Map<String, Value>,
    row: &Map<String, Value>,
) -> Result<BinanceKlineStreamCandle> {
    let symbol = row
        .get("s")
        .or_else(|| parent.get("s"))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_uppercase();
    let interval = row
        .get("i")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_owned();
    if symbol.is_empty() || interval.is_empty() {
        bail!("kline message missing symbol or interval");
    }
    Ok(BinanceKlineStreamCandle {
        symbol,
        interval,
        open_time_ms: parse_json_i64(row.get("t"))
            .ok_or_else(|| anyhow!("kline message missing open time"))?,
        open: parse_required_f64(row, "o", "open")?,
        high: parse_required_f64(row, "h", "high")?,
        low: parse_required_f64(row, "l", "low")?,
        close: parse_required_f64(row, "c", "close")?,
        volume: parse_required_f64(row, "v", "volume")?,
        is_closed: row.get("x").and_then(Value::as_bool).unwrap_or(false),
        event_time_ms: parse_json_i64(parent.get("E")).unwrap_or(0),
    })
}

fn normalize_stream_symbol(symbol: &str) -> Result<String> {
    let stream = symbol.trim().to_lowercase().replace(' ', "");
    if stream.is_empty() {
        bail!("Symbol is empty");
    }
    Ok(stream)
}

fn normalize_stream_interval(interval: &str) -> Result<String> {
    let stream = interval.trim().to_lowercase().replace(' ', "");
    if stream.is_empty() {
        bail!("Interval is empty");
    }
    Ok(stream)
}

fn parse_required_f64(row: &Map<String, Value>, key: &str, label: &str) -> Result<f64> {
    parse_json_f64(row.get(key))
        .filter(|value| value.is_finite())
        .ok_or_else(|| anyhow!("kline message missing {label}"))
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

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn builds_cpp_equivalent_book_ticker_urls() {
        assert_eq!(
            BinanceWebSocketClient::book_ticker_url(BinanceMarket::Futures, "BTCUSDT", false)
                .expect("futures url"),
            "wss://fstream.binance.com/ws/btcusdt@bookTicker"
        );
        assert_eq!(
            BinanceWebSocketClient::book_ticker_url(BinanceMarket::Futures, "BTCUSDT", true)
                .expect("futures testnet url"),
            "wss://stream.binancefuture.com/ws/btcusdt@bookTicker"
        );
        assert_eq!(
            BinanceWebSocketClient::book_ticker_url(BinanceMarket::Spot, "ETH USDT", false)
                .expect("spot url"),
            "wss://stream.binance.com:9443/ws/ethusdt@bookTicker"
        );
        assert_eq!(
            BinanceWebSocketClient::book_ticker_url(BinanceMarket::Spot, "ETHUSDT", true)
                .expect("spot testnet url"),
            "wss://testnet.binance.vision/ws/ethusdt@bookTicker"
        );
    }

    #[test]
    fn builds_cpp_equivalent_kline_urls() {
        let subscription = BinanceWebSocketClient::kline_subscription(
            BinanceMarket::Futures,
            "BTCUSDT",
            " 1H ",
            false,
        )
        .expect("subscription");
        assert_eq!(subscription.stream_name(), "btcusdt@kline_1h");
        assert_eq!(
            subscription.url(),
            "wss://fstream.binance.com/ws/btcusdt@kline_1h"
        );
    }

    #[test]
    fn parses_book_ticker_messages() {
        let event =
            parse_stream_event(r#"{"e":"bookTicker","s":"BTCUSDT","b":"61000.10","a":"61000.20"}"#)
                .expect("book ticker");
        assert_eq!(
            event,
            BinanceStreamEvent::BookTicker(BinanceBookTicker {
                symbol: "BTCUSDT".to_owned(),
                bid_price: 61000.10,
                ask_price: 61000.20,
            })
        );
    }

    #[test]
    fn parses_kline_messages_like_python_ws_cache() {
        let payload = json!({
            "E": 1700000001234_i64,
            "s": "ETHUSDT",
            "k": {
                "s": "ETHUSDT",
                "i": "1m",
                "t": 1700000000000_i64,
                "o": "2000.1",
                "h": "2002.2",
                "l": "1999.9",
                "c": "2001.5",
                "v": "123.456",
                "x": true
            }
        });
        let event = parse_stream_event_value(&payload).expect("kline");
        assert_eq!(
            event,
            BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
                symbol: "ETHUSDT".to_owned(),
                interval: "1m".to_owned(),
                open_time_ms: 1_700_000_000_000,
                open: 2000.1,
                high: 2002.2,
                low: 1999.9,
                close: 2001.5,
                volume: 123.456,
                is_closed: true,
                event_time_ms: 1_700_000_001_234,
            })
        );
    }

    #[test]
    fn parses_combined_stream_wrappers() {
        let event = parse_stream_event(
            r#"{"stream":"btcusdt@bookTicker","data":{"s":"BTCUSDT","b":"1.1","a":"1.2"}}"#,
        )
        .expect("combined stream");
        match event {
            BinanceStreamEvent::BookTicker(ticker) => {
                assert_eq!(ticker.symbol, "BTCUSDT");
                assert_eq!(ticker.bid_price, 1.1);
                assert_eq!(ticker.ask_price, 1.2);
            }
            BinanceStreamEvent::Kline(_) => panic!("expected book ticker"),
        }
    }

    #[test]
    fn invalid_stream_messages_fail_closed() {
        assert!(
            BinanceWebSocketClient::book_ticker_url(BinanceMarket::Futures, "", false).is_err()
        );
        assert!(
            BinanceWebSocketClient::kline_url(BinanceMarket::Futures, "BTCUSDT", "", false)
                .is_err()
        );
        assert!(parse_stream_event(r#"{"s":"BTCUSDT","b":"1"}"#).is_err());
        assert!(parse_stream_event(r#"{"k":{"s":"BTCUSDT","i":"1m","t":1,"o":"1"}}"#).is_err());
    }
}
