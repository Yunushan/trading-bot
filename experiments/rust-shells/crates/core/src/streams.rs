use std::{
    net::{TcpStream, ToSocketAddrs},
    time::Duration,
};

use anyhow::{Context, Result, anyhow, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{HandshakeError, Message, WebSocket, client_tls};

use crate::market_data::BinanceMarket;

pub type BinanceWebSocket = WebSocket<MaybeTlsStream<TcpStream>>;

const DEFAULT_WEBSOCKET_CONNECT_TIMEOUT: Duration = Duration::from_secs(15);

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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StreamReconnectPolicy {
    pub base_delay_ms: u64,
    pub max_delay_ms: u64,
    pub reset_after_ms: u64,
    pub max_attempts: usize,
}

impl Default for StreamReconnectPolicy {
    fn default() -> Self {
        Self {
            base_delay_ms: 500,
            max_delay_ms: 30_000,
            reset_after_ms: 60_000,
            max_attempts: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StreamReconnectDecision {
    pub should_reconnect: bool,
    pub next_attempt: usize,
    pub delay_ms: u64,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct KlineCacheHealth {
    pub stale: bool,
    pub reason: String,
    pub candle_count: usize,
    pub latest_event_time_ms: Option<i64>,
    pub latest_closed_open_time_ms: Option<i64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StreamSupervisorSnapshot {
    pub connected: bool,
    pub reconnect_attempts: usize,
    pub last_event_time_ms: Option<i64>,
    pub last_disconnect_time_ms: Option<i64>,
    pub kline_cache_health: KlineCacheHealth,
    pub reconnect_decision: StreamReconnectDecision,
}

#[derive(Debug, Clone)]
pub struct StreamSupervisor {
    pub policy: StreamReconnectPolicy,
    pub stale_after_ms: i64,
    pub max_cached_klines: usize,
    connected: bool,
    reconnect_attempts: usize,
    last_event_time_ms: Option<i64>,
    last_disconnect_time_ms: Option<i64>,
    kline_cache: Vec<BinanceKlineStreamCandle>,
}

impl StreamSupervisor {
    pub fn new(policy: StreamReconnectPolicy, stale_after_ms: i64) -> Self {
        Self {
            policy,
            stale_after_ms,
            max_cached_klines: 500,
            connected: false,
            reconnect_attempts: 0,
            last_event_time_ms: None,
            last_disconnect_time_ms: None,
            kline_cache: Vec::new(),
        }
    }

    pub fn record_connected(&mut self) {
        self.connected = true;
        self.reconnect_attempts = 0;
        self.last_disconnect_time_ms = None;
    }

    pub fn record_disconnected(&mut self, now_ms: i64) {
        self.connected = false;
        self.last_disconnect_time_ms = Some(now_ms);
    }

    pub fn record_event(&mut self, event: BinanceStreamEvent, received_at_ms: i64) {
        self.record_connected();
        match event {
            BinanceStreamEvent::BookTicker(_) => {
                self.last_event_time_ms = Some(received_at_ms);
            }
            BinanceStreamEvent::Kline(candle) => {
                self.last_event_time_ms = Some(candle.event_time_ms);
                if let Some(existing) = self.kline_cache.iter_mut().find(|existing| {
                    existing.symbol == candle.symbol
                        && existing.interval == candle.interval
                        && existing.open_time_ms == candle.open_time_ms
                }) {
                    *existing = candle;
                } else {
                    self.kline_cache.push(candle);
                }
                let max_cached = self.max_cached_klines.max(1);
                if self.kline_cache.len() > max_cached {
                    let overflow = self.kline_cache.len() - max_cached;
                    self.kline_cache.drain(0..overflow);
                }
            }
        }
    }

    pub fn next_reconnect_decision(&mut self, now_ms: i64) -> StreamReconnectDecision {
        let decision = self.build_reconnect_decision(now_ms);
        if decision.should_reconnect {
            self.reconnect_attempts = decision.next_attempt;
        }
        decision
    }

    pub fn kline_cache_health(&self, now_ms: i64) -> KlineCacheHealth {
        evaluate_kline_cache_health(&self.kline_cache, now_ms, self.stale_after_ms)
    }

    pub fn snapshot(&self, now_ms: i64) -> StreamSupervisorSnapshot {
        StreamSupervisorSnapshot {
            connected: self.connected,
            reconnect_attempts: self.reconnect_attempts,
            last_event_time_ms: self.last_event_time_ms,
            last_disconnect_time_ms: self.last_disconnect_time_ms,
            kline_cache_health: self.kline_cache_health(now_ms),
            reconnect_decision: self.build_reconnect_decision(now_ms),
        }
    }

    fn build_reconnect_decision(&self, now_ms: i64) -> StreamReconnectDecision {
        build_stream_reconnect_decision(
            !self.connected,
            self.reconnect_attempts,
            self.last_event_age_ms(now_ms),
            &self.policy,
        )
    }

    fn last_event_age_ms(&self, now_ms: i64) -> Option<u64> {
        self.last_event_time_ms
            .map(|event_time| now_ms.saturating_sub(event_time).max(0) as u64)
    }
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
        self.connect_subscription_with_timeout(subscription, DEFAULT_WEBSOCKET_CONNECT_TIMEOUT)
    }

    pub fn connect_subscription_with_timeout(
        &self,
        subscription: &BinanceStreamSubscription,
        timeout: Duration,
    ) -> Result<BinanceWebSocket> {
        let url = subscription.url();
        connect_websocket_url_with_timeout(url.as_str(), timeout)
            .with_context(|| format!("connect {url}"))
    }

    pub fn set_read_timeout(
        socket: &mut BinanceWebSocket,
        timeout: Option<Duration>,
    ) -> Result<()> {
        configure_websocket_read_timeout(socket.get_mut(), timeout)
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

fn configure_websocket_read_timeout(
    stream: &mut MaybeTlsStream<TcpStream>,
    timeout: Option<Duration>,
) -> Result<()> {
    let result = match stream {
        MaybeTlsStream::Plain(socket) => socket.set_read_timeout(timeout),
        MaybeTlsStream::NativeTls(socket) => socket.get_mut().set_read_timeout(timeout),
        _ => bail!("configured Binance WebSocket transport does not expose a TCP read timeout"),
    };
    result.context("set Binance WebSocket read timeout")
}

fn connect_websocket_url_with_timeout(url: &str, timeout: Duration) -> Result<BinanceWebSocket> {
    if timeout.is_zero() {
        bail!("Binance WebSocket connection timeout must be greater than zero");
    }
    let uri = url
        .parse::<tungstenite::http::Uri>()
        .with_context(|| format!("parse Binance WebSocket URL {url}"))?;
    let host = uri
        .host()
        .ok_or_else(|| anyhow!("Binance WebSocket URL has no host: {url}"))?;
    let host = if host.starts_with('[') {
        &host[1..host.len().saturating_sub(1)]
    } else {
        host
    };
    let port = uri.port_u16().unwrap_or_else(|| match uri.scheme_str() {
        Some("wss") => 443,
        _ => 80,
    });
    let addresses = (host, port)
        .to_socket_addrs()
        .with_context(|| format!("resolve Binance WebSocket host {host}:{port}"))?;
    let mut last_error = None;
    for address in addresses {
        match TcpStream::connect_timeout(&address, timeout) {
            Ok(stream) => {
                stream
                    .set_nodelay(true)
                    .context("enable TCP_NODELAY for Binance WebSocket")?;
                stream
                    .set_read_timeout(Some(timeout))
                    .context("set Binance WebSocket handshake read timeout")?;
                stream
                    .set_write_timeout(Some(timeout))
                    .context("set Binance WebSocket handshake write timeout")?;
                return client_tls(url, stream)
                    .map(|(socket, _)| socket)
                    .map_err(|error| match error {
                        HandshakeError::Failure(error) => anyhow!(error),
                        HandshakeError::Interrupted(_) => {
                            anyhow!("Binance WebSocket handshake did not complete within the configured timeout")
                        }
                    })
                    .with_context(|| format!("complete Binance WebSocket TLS handshake for {url}"));
            }
            Err(error) => last_error = Some(error),
        }
    }
    Err(anyhow!(
        "connect to Binance WebSocket {host}:{port} within {timeout:?}: {}",
        last_error
            .map(|error| error.to_string())
            .unwrap_or_else(|| "no resolved addresses".to_owned())
    ))
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
        (BinanceMarket::CoinFutures, true) => "wss://dstream.binancefuture.com/ws",
        (BinanceMarket::CoinFutures, false) => "wss://dstream.binance.com/ws",
        (BinanceMarket::Spot, true) => "wss://testnet.binance.vision/ws",
        (BinanceMarket::Spot, false) => "wss://stream.binance.com:9443/ws",
    }
}

pub fn build_stream_reconnect_decision(
    disconnected: bool,
    attempt_count: usize,
    last_event_age_ms: Option<u64>,
    policy: &StreamReconnectPolicy,
) -> StreamReconnectDecision {
    let should_reset_attempts = last_event_age_ms
        .map(|age| age >= policy.reset_after_ms)
        .unwrap_or(false);
    let current_attempt = if should_reset_attempts {
        0
    } else {
        attempt_count
    };
    if !disconnected {
        return StreamReconnectDecision {
            should_reconnect: false,
            next_attempt: 0,
            delay_ms: 0,
            reason: "stream active".to_owned(),
        };
    }
    if policy.max_attempts > 0 && current_attempt >= policy.max_attempts {
        return StreamReconnectDecision {
            should_reconnect: false,
            next_attempt: current_attempt,
            delay_ms: 0,
            reason: "stream reconnect attempts exhausted".to_owned(),
        };
    }

    let next_attempt = current_attempt.saturating_add(1);
    let shift = current_attempt.min(16) as u32;
    let multiplier = 1_u64.checked_shl(shift).unwrap_or(u64::MAX);
    let delay_ms = policy.base_delay_ms.saturating_mul(multiplier).clamp(
        policy.base_delay_ms,
        policy.max_delay_ms.max(policy.base_delay_ms),
    );
    StreamReconnectDecision {
        should_reconnect: true,
        next_attempt,
        delay_ms,
        reason: if should_reset_attempts {
            "stream stale; reconnect with reset attempt window".to_owned()
        } else {
            "stream disconnected; reconnect with exponential backoff".to_owned()
        },
    }
}

pub fn evaluate_kline_cache_health(
    candles: &[BinanceKlineStreamCandle],
    now_ms: i64,
    stale_after_ms: i64,
) -> KlineCacheHealth {
    if candles.is_empty() {
        return KlineCacheHealth {
            stale: true,
            reason: "no stream candles cached".to_owned(),
            candle_count: 0,
            latest_event_time_ms: None,
            latest_closed_open_time_ms: None,
        };
    }

    let latest_event_time_ms = candles.iter().map(|candle| candle.event_time_ms).max();
    let latest_closed_open_time_ms = candles
        .iter()
        .filter(|candle| candle.is_closed)
        .map(|candle| candle.open_time_ms)
        .max();
    let stale_threshold = stale_after_ms.max(1);
    let latest_age_ms = latest_event_time_ms
        .map(|event_time| now_ms.saturating_sub(event_time))
        .unwrap_or(i64::MAX);
    let stale = latest_age_ms > stale_threshold;
    let reason = if stale {
        format!("latest stream candle age {latest_age_ms}ms exceeds {stale_threshold}ms")
    } else {
        "stream candle cache fresh".to_owned()
    };
    KlineCacheHealth {
        stale,
        reason,
        candle_count: candles.len(),
        latest_event_time_ms,
        latest_closed_open_time_ms,
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
    use std::{net::TcpListener, time::Duration};

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
            BinanceWebSocketClient::book_ticker_url(
                BinanceMarket::CoinFutures,
                "BTCUSD_PERP",
                false,
            )
            .expect("Coin-M url"),
            "wss://dstream.binance.com/ws/btcusd_perp@bookTicker"
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

    #[test]
    fn websocket_read_timeout_is_applied_to_plain_tcp_transport() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind local listener");
        let address = listener.local_addr().expect("listener address");
        let accept_thread = std::thread::spawn(move || {
            listener
                .accept()
                .expect("accept local client")
                .0
        });
        let client = TcpStream::connect(address).expect("connect local client");
        let _server = accept_thread.join().expect("local accept thread");
        let mut stream = MaybeTlsStream::Plain(client);
        let expected_timeout = Duration::from_millis(250);

        configure_websocket_read_timeout(&mut stream, Some(expected_timeout))
            .expect("configure stream timeout");

        let observed_timeout = match stream {
            MaybeTlsStream::Plain(socket) => socket.read_timeout().expect("read timeout"),
            _ => panic!("expected plain TCP stream"),
        };
        assert_eq!(Some(expected_timeout), observed_timeout);
    }

    #[test]
    fn websocket_connection_uses_bounded_tcp_handshake_timeouts() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind local listener");
        let address = listener.local_addr().expect("listener address");
        let accept_thread = std::thread::spawn(move || {
            let (stream, _) = listener.accept().expect("accept WebSocket client");
            tungstenite::accept(stream).expect("accept local WebSocket handshake")
        });
        let expected_timeout = Duration::from_millis(250);
        let socket = connect_websocket_url_with_timeout(
            format!("ws://{address}/ws").as_str(),
            expected_timeout,
        )
        .expect("connect local WebSocket client");

        let observed_timeout = match socket.get_ref() {
            MaybeTlsStream::Plain(stream) => stream.read_timeout().expect("read timeout"),
            _ => panic!("expected plain TCP stream"),
        };
        assert_eq!(Some(expected_timeout), observed_timeout);
        drop(socket);
        drop(accept_thread.join().expect("local accept thread"));
    }

    #[test]
    fn websocket_connection_rejects_zero_timeout() {
        let error = connect_websocket_url_with_timeout("ws://127.0.0.1:1/ws", Duration::ZERO)
            .expect_err("zero timeout must be rejected");

        assert!(error.to_string().contains("must be greater than zero"));
    }

    #[test]
    fn stream_reconnect_decision_uses_reset_window_and_exponential_backoff() {
        let policy = StreamReconnectPolicy {
            base_delay_ms: 250,
            max_delay_ms: 5_000,
            reset_after_ms: 60_000,
            max_attempts: 3,
        };

        let first = build_stream_reconnect_decision(true, 0, Some(1_000), &policy);
        assert!(first.should_reconnect);
        assert_eq!(first.next_attempt, 1);
        assert_eq!(first.delay_ms, 250);

        let second = build_stream_reconnect_decision(true, 1, Some(1_000), &policy);
        assert_eq!(second.next_attempt, 2);
        assert_eq!(second.delay_ms, 500);

        let reset = build_stream_reconnect_decision(true, 3, Some(61_000), &policy);
        assert!(reset.should_reconnect);
        assert_eq!(reset.next_attempt, 1);
        assert_eq!(reset.delay_ms, 250);
        assert!(reset.reason.contains("reset attempt window"));

        let exhausted = build_stream_reconnect_decision(true, 3, Some(1_000), &policy);
        assert!(!exhausted.should_reconnect);
        assert!(exhausted.reason.contains("attempts exhausted"));
    }

    #[test]
    fn kline_cache_health_marks_stale_and_tracks_latest_closed_candle() {
        let candles = vec![
            BinanceKlineStreamCandle {
                symbol: "BTCUSDT".to_owned(),
                interval: "1m".to_owned(),
                open_time_ms: 1_700_000_000_000,
                open: 1.0,
                high: 2.0,
                low: 0.5,
                close: 1.5,
                volume: 10.0,
                is_closed: true,
                event_time_ms: 1_700_000_060_000,
            },
            BinanceKlineStreamCandle {
                symbol: "BTCUSDT".to_owned(),
                interval: "1m".to_owned(),
                open_time_ms: 1_700_000_060_000,
                open: 1.5,
                high: 2.5,
                low: 1.0,
                close: 2.0,
                volume: 12.0,
                is_closed: false,
                event_time_ms: 1_700_000_090_000,
            },
        ];

        let fresh = evaluate_kline_cache_health(&candles, 1_700_000_100_000, 30_000);
        assert!(!fresh.stale);
        assert_eq!(fresh.candle_count, 2);
        assert_eq!(fresh.latest_event_time_ms, Some(1_700_000_090_000));
        assert_eq!(fresh.latest_closed_open_time_ms, Some(1_700_000_000_000));

        let stale = evaluate_kline_cache_health(&candles, 1_700_000_130_001, 30_000);
        assert!(stale.stale);
        assert!(stale.reason.contains("exceeds 30000ms"));
    }

    #[test]
    fn stream_supervisor_owns_reconnect_attempts_and_cache_health() {
        let mut supervisor = StreamSupervisor::new(
            StreamReconnectPolicy {
                base_delay_ms: 100,
                max_delay_ms: 2_000,
                reset_after_ms: 60_000,
                max_attempts: 3,
            },
            30_000,
        );
        supervisor.max_cached_klines = 1;

        let initial = supervisor.snapshot(1_700_000_000_000);
        assert!(!initial.connected);
        assert!(initial.reconnect_decision.should_reconnect);
        assert!(initial.kline_cache_health.stale);

        let first_reconnect = supervisor.next_reconnect_decision(1_700_000_000_000);
        assert_eq!(first_reconnect.next_attempt, 1);
        assert_eq!(supervisor.snapshot(1_700_000_000_000).reconnect_attempts, 1);

        supervisor.record_event(
            BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
                symbol: "BTCUSDT".to_owned(),
                interval: "1m".to_owned(),
                open_time_ms: 1_700_000_000_000,
                open: 1.0,
                high: 2.0,
                low: 0.5,
                close: 1.5,
                volume: 10.0,
                is_closed: true,
                event_time_ms: 1_700_000_001_000,
            }),
            1_700_000_001_100,
        );

        let fresh = supervisor.snapshot(1_700_000_010_000);
        assert!(fresh.connected);
        assert_eq!(fresh.reconnect_attempts, 0);
        assert!(!fresh.kline_cache_health.stale);
        assert_eq!(fresh.kline_cache_health.candle_count, 1);
        assert!(!fresh.reconnect_decision.should_reconnect);

        supervisor.record_event(
            BinanceStreamEvent::Kline(BinanceKlineStreamCandle {
                symbol: "BTCUSDT".to_owned(),
                interval: "1m".to_owned(),
                open_time_ms: 1_700_000_060_000,
                open: 1.5,
                high: 2.5,
                low: 1.0,
                close: 2.0,
                volume: 20.0,
                is_closed: false,
                event_time_ms: 1_700_000_061_000,
            }),
            1_700_000_061_100,
        );
        assert_eq!(
            supervisor
                .snapshot(1_700_000_061_100)
                .kline_cache_health
                .candle_count,
            1
        );

        supervisor.record_disconnected(1_700_000_100_000);
        let stale_after_disconnect = supervisor.snapshot(1_700_000_100_001);
        assert!(!stale_after_disconnect.connected);
        assert!(stale_after_disconnect.kline_cache_health.stale);
        assert!(stale_after_disconnect.reconnect_decision.should_reconnect);
        assert_eq!(stale_after_disconnect.reconnect_decision.next_attempt, 1);
    }

    #[test]
    fn stream_supervisor_resets_reconnect_window_after_stale_disconnect() {
        let mut supervisor = StreamSupervisor::new(
            StreamReconnectPolicy {
                base_delay_ms: 100,
                max_delay_ms: 1_000,
                reset_after_ms: 1_000,
                max_attempts: 2,
            },
            500,
        );
        supervisor.record_event(
            BinanceStreamEvent::BookTicker(BinanceBookTicker {
                symbol: "ETHUSDT".to_owned(),
                bid_price: 10.0,
                ask_price: 11.0,
            }),
            10_000,
        );
        supervisor.record_disconnected(10_100);

        assert_eq!(supervisor.next_reconnect_decision(10_100).next_attempt, 1);
        assert_eq!(supervisor.next_reconnect_decision(10_200).next_attempt, 2);
        assert!(!supervisor.next_reconnect_decision(10_250).should_reconnect);

        let reset = supervisor.next_reconnect_decision(11_001);
        assert!(reset.should_reconnect);
        assert_eq!(reset.next_attempt, 1);
        assert!(reset.reason.contains("reset attempt window"));
    }
}
