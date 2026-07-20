use anyhow::{Result, anyhow, bail};
use serde_json::{Map, Value};

use crate::account::{BinanceApiCredentials, BinanceSignedRestClient, current_timestamp_ms};

const FUTURES_ORDER_RECV_WINDOW_MS: u64 = 5_000;

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesSymbolFilters {
    pub symbol: String,
    pub step_size: f64,
    pub tick_size: f64,
    pub min_qty: f64,
    pub max_qty: f64,
    pub min_notional: f64,
    pub quantity_precision: i64,
    pub price_precision: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesOrderResult {
    pub symbol: String,
    pub side: String,
    pub position_side: String,
    pub order_id: String,
    pub status: String,
    pub executed_qty: f64,
    pub avg_price: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesOrderParams {
    pub params: Vec<(&'static str, String)>,
    pub symbol: String,
    pub side: String,
    pub position_side: String,
}

impl BinanceSignedRestClient {
    pub fn fetch_futures_symbol_filters(
        &self,
        symbol: impl AsRef<str>,
    ) -> Result<BinanceFuturesSymbolFilters> {
        self.require_futures_market()?;
        let exchange_info_path = self.futures_v1_path("/exchangeInfo");
        let payload = self.public_get_json(&exchange_info_path, &[])?;
        parse_futures_symbol_filters(&payload, symbol.as_ref())
    }

    pub fn place_futures_market_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        side: impl AsRef<str>,
        quantity: f64,
        reduce_only: bool,
        position_side: impl AsRef<str>,
    ) -> Result<BinanceFuturesOrderResult> {
        self.require_futures_market()?;
        let order_params =
            build_futures_market_order_params(symbol, side, quantity, reduce_only, position_side)?;
        let payload = self.signed_post_json(
            &self.futures_v1_path("/order"),
            credentials,
            &order_params.params,
            current_timestamp_ms()?,
            FUTURES_ORDER_RECV_WINDOW_MS,
        )?;
        parse_futures_order_result(
            &payload,
            &order_params.symbol,
            &order_params.side,
            &order_params.position_side,
        )
    }

    // The public request mirrors Binance's independent order fields and the Python contract.
    #[allow(clippy::too_many_arguments)]
    pub fn place_futures_limit_order(
        &self,
        credentials: &BinanceApiCredentials,
        symbol: impl AsRef<str>,
        side: impl AsRef<str>,
        quantity: f64,
        price: f64,
        reduce_only: bool,
        position_side: impl AsRef<str>,
        time_in_force: impl AsRef<str>,
    ) -> Result<BinanceFuturesOrderResult> {
        self.require_futures_market()?;
        let order_params = build_futures_limit_order_params(
            symbol,
            side,
            quantity,
            price,
            reduce_only,
            position_side,
            time_in_force,
        )?;
        let payload = self.signed_post_json(
            &self.futures_v1_path("/order"),
            credentials,
            &order_params.params,
            current_timestamp_ms()?,
            FUTURES_ORDER_RECV_WINDOW_MS,
        )?;
        parse_futures_order_result(
            &payload,
            &order_params.symbol,
            &order_params.side,
            &order_params.position_side,
        )
    }
}

pub fn build_futures_market_order_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
    reduce_only: bool,
    position_side: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    validate_positive("Quantity", quantity)?;
    let position_side = normalize_position_side(position_side.as_ref());
    let has_directional_side = is_directional_position_side(&position_side);

    let mut params = vec![
        ("symbol", symbol.clone()),
        ("side", side.clone()),
        ("type", "MARKET".to_owned()),
        ("quantity", format_decimal_for_order(quantity, 8)),
    ];
    if reduce_only && !has_directional_side {
        params.push(("reduceOnly", "true".to_owned()));
    }
    if has_directional_side {
        params.push(("positionSide", position_side.clone()));
    }
    Ok(BinanceFuturesOrderParams {
        params,
        symbol,
        side,
        position_side,
    })
}

pub fn build_futures_limit_order_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
    price: f64,
    reduce_only: bool,
    position_side: impl AsRef<str>,
    time_in_force: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    validate_positive("Quantity", quantity)?;
    validate_positive("Price", price)?;
    let position_side = normalize_position_side(position_side.as_ref());
    let has_directional_side = is_directional_position_side(&position_side);
    let time_in_force = normalize_time_in_force(time_in_force.as_ref());

    let mut params = vec![
        ("symbol", symbol.clone()),
        ("side", side.clone()),
        ("type", "LIMIT".to_owned()),
        ("timeInForce", time_in_force),
        ("quantity", format_decimal_for_order(quantity, 8)),
        ("price", format_decimal_for_order(price, 8)),
    ];
    if reduce_only && !has_directional_side {
        params.push(("reduceOnly", "true".to_owned()));
    }
    if has_directional_side {
        params.push(("positionSide", position_side.clone()));
    }
    Ok(BinanceFuturesOrderParams {
        params,
        symbol,
        side,
        position_side,
    })
}

pub fn parse_futures_symbol_filters(
    exchange_info: &Value,
    symbol: &str,
) -> Result<BinanceFuturesSymbolFilters> {
    ensure_not_binance_error(exchange_info)?;
    let clean_symbol = normalize_symbol(symbol)?;
    let rows = exchange_info
        .get("symbols")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("exchangeInfo response missing symbols array"))?;
    for value in rows {
        let Some(row) = value.as_object() else {
            continue;
        };
        let current = row
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase();
        if current != clean_symbol {
            continue;
        }

        let mut result = BinanceFuturesSymbolFilters {
            symbol: clean_symbol,
            step_size: 0.0,
            tick_size: 0.0,
            min_qty: 0.0,
            max_qty: 0.0,
            min_notional: 0.0,
            quantity_precision: parse_json_i64(row.get("quantityPrecision"))
                .unwrap_or(0)
                .max(0),
            price_precision: parse_json_i64(row.get("pricePrecision"))
                .unwrap_or(0)
                .max(0),
        };
        let mut lot_step_size = 0.0;
        let mut lot_min_qty = 0.0;
        let mut lot_max_qty = 0.0;
        let mut market_step_size = 0.0;
        let mut market_min_qty = 0.0;
        let mut market_max_qty = 0.0;
        let mut price_tick_size = 0.0;

        for filter in row
            .get("filters")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let Some(filter) = filter.as_object() else {
                continue;
            };
            match filter
                .get("filterType")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim()
                .to_uppercase()
                .as_str()
            {
                "LOT_SIZE" => {
                    lot_step_size = first_f64(filter, &["stepSize"]).unwrap_or(0.0);
                    lot_min_qty = first_f64(filter, &["minQty"]).unwrap_or(0.0);
                    lot_max_qty = first_f64(filter, &["maxQty"]).unwrap_or(0.0);
                }
                "MARKET_LOT_SIZE" => {
                    market_step_size = first_f64(filter, &["stepSize"]).unwrap_or(0.0);
                    market_min_qty = first_f64(filter, &["minQty"]).unwrap_or(0.0);
                    market_max_qty = first_f64(filter, &["maxQty"]).unwrap_or(0.0);
                }
                "MIN_NOTIONAL" | "NOTIONAL" => {
                    result.min_notional =
                        first_f64(filter, &["notional", "minNotional"]).unwrap_or(0.0);
                }
                "PRICE_FILTER" => {
                    price_tick_size = first_f64(filter, &["tickSize"]).unwrap_or(0.0);
                }
                _ => {}
            }
        }

        result.step_size = positive_or_zero(if market_step_size > 0.0 {
            market_step_size
        } else {
            lot_step_size
        });
        result.tick_size = positive_or_zero(price_tick_size);
        result.min_qty = positive_or_zero(if market_min_qty > 0.0 {
            market_min_qty
        } else {
            lot_min_qty
        });
        result.max_qty = positive_or_zero(if market_max_qty > 0.0 {
            market_max_qty
        } else {
            lot_max_qty
        });
        result.min_notional = positive_or_zero(result.min_notional);
        return Ok(result);
    }

    bail!("Symbol {clean_symbol} not found in futures exchangeInfo")
}

pub fn parse_futures_order_result(
    payload: &Value,
    fallback_symbol: &str,
    fallback_side: &str,
    fallback_position_side: &str,
) -> Result<BinanceFuturesOrderResult> {
    ensure_not_binance_order_error(payload)?;
    let obj = payload
        .as_object()
        .ok_or_else(|| anyhow!("futures order response must be an object"))?;
    let avg_price = first_f64(obj, &["avgPrice"])
        .filter(|value| *value > 0.0)
        .or_else(|| first_f64(obj, &["price"]))
        .unwrap_or(0.0);
    let executed_qty = first_f64(obj, &["executedQty"])
        .filter(|value| *value > 0.0)
        .or_else(|| first_f64(obj, &["origQty"]))
        .unwrap_or(0.0);
    Ok(BinanceFuturesOrderResult {
        symbol: obj
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or(fallback_symbol)
            .trim()
            .to_uppercase(),
        side: obj
            .get("side")
            .and_then(Value::as_str)
            .unwrap_or(fallback_side)
            .trim()
            .to_uppercase(),
        position_side: obj
            .get("positionSide")
            .and_then(Value::as_str)
            .unwrap_or(fallback_position_side)
            .trim()
            .to_uppercase(),
        order_id: json_value_to_string(obj.get("orderId")).unwrap_or_default(),
        status: obj
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_uppercase(),
        executed_qty,
        avg_price,
    })
}

pub fn futures_order_recv_window_ms() -> u64 {
    FUTURES_ORDER_RECV_WINDOW_MS
}

pub fn format_decimal_for_order(value: f64, precision_hint: usize) -> String {
    let precision = precision_hint.min(16);
    let mut text = format!("{value:.precision$}");
    while text.contains('.') && (text.ends_with('0') || text.ends_with('.')) {
        text.pop();
    }
    if text.is_empty() {
        "0".to_owned()
    } else {
        text
    }
}

fn normalize_symbol(value: &str) -> Result<String> {
    let symbol = value.trim().to_uppercase();
    if symbol.is_empty() {
        bail!("Symbol is required");
    }
    Ok(symbol)
}

fn normalize_order_side(value: &str) -> Result<String> {
    match value.trim().to_uppercase().as_str() {
        "BUY" | "LONG" | "L" => Ok("BUY".to_owned()),
        "SELL" | "SHORT" | "S" => Ok("SELL".to_owned()),
        _ => bail!("Side must be BUY or SELL"),
    }
}

fn normalize_position_side(value: &str) -> String {
    value.trim().to_uppercase()
}

fn normalize_time_in_force(value: &str) -> String {
    let normalized = value.trim().to_uppercase();
    if normalized.is_empty() {
        "IOC".to_owned()
    } else {
        normalized
    }
}

fn is_directional_position_side(value: &str) -> bool {
    matches!(value.trim().to_uppercase().as_str(), "LONG" | "SHORT")
}

fn validate_positive(label: &str, value: f64) -> Result<()> {
    if !value.is_finite() || value <= 0.0 {
        bail!("{label} must be > 0");
    }
    Ok(())
}

fn first_f64(row: &Map<String, Value>, keys: &[&str]) -> Option<f64> {
    for key in keys {
        if let Some(value) = parse_json_f64(row.get(*key)).filter(|value| value.is_finite()) {
            return Some(value);
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

fn json_value_to_string(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::Number(number) => Some(number.to_string()),
        Value::String(text) => Some(text.trim().to_owned()),
        _ => None,
    }
}

fn positive_or_zero(value: f64) -> f64 {
    if value.is_finite() && value > 0.0 {
        value
    } else {
        0.0
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

fn ensure_not_binance_order_error(value: &Value) -> Result<()> {
    let Some(obj) = value.as_object() else {
        return Ok(());
    };
    if obj.contains_key("code") || obj.contains_key("msg") {
        let message = obj.get("msg").and_then(Value::as_str).unwrap_or("unknown");
        bail!("Binance order error: {message}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use crate::account::signed_query_string;

    use super::*;

    #[test]
    fn parses_futures_symbol_filters_like_cpp_preferring_market_lot_size() {
        let payload = json!({
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "quantityPrecision": 3,
                    "pricePrecision": 2,
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "100"},
                        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.01", "minQty": "0.02", "maxQty": "50"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"}
                    ]
                }
            ]
        });
        let filters = parse_futures_symbol_filters(&payload, "btcusdt").expect("filters");
        assert_eq!(filters.symbol, "BTCUSDT");
        assert_eq!(filters.step_size, 0.01);
        assert_eq!(filters.min_qty, 0.02);
        assert_eq!(filters.max_qty, 50.0);
        assert_eq!(filters.tick_size, 0.10);
        assert_eq!(filters.min_notional, 5.0);
        assert_eq!(filters.quantity_precision, 3);
        assert_eq!(filters.price_precision, 2);
    }

    #[test]
    fn market_order_params_match_python_and_cpp_reduce_only_hedge_rules() {
        let one_way = build_futures_market_order_params("ethusdt", "long", 0.123400, true, "BOTH")
            .expect("one-way params");
        assert_eq!(
            one_way.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "BUY".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "0.1234".to_owned()),
                ("reduceOnly", "true".to_owned()),
            ]
        );

        let hedge = build_futures_market_order_params("ethusdt", "SELL", 2.0, true, "SHORT")
            .expect("hedge params");
        assert_eq!(
            hedge.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "2".to_owned()),
                ("positionSide", "SHORT".to_owned()),
            ]
        );
    }

    #[test]
    fn limit_order_params_default_ioc_and_format_decimal_values() {
        let order = build_futures_limit_order_params(
            "btcusdt",
            "sell",
            1.250000,
            20123.450000,
            false,
            "",
            "",
        )
        .expect("limit params");
        assert_eq!(
            order.params,
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "LIMIT".to_owned()),
                ("timeInForce", "IOC".to_owned()),
                ("quantity", "1.25".to_owned()),
                ("price", "20123.45".to_owned()),
            ]
        );
    }

    #[test]
    fn signed_order_query_uses_cpp_order_recv_window() {
        let order = build_futures_market_order_params("BTCUSDT", "BUY", 1.0, false, "")
            .expect("market params");
        let query = signed_query_string(
            "test-secret",
            1_700_000_000_000,
            futures_order_recv_window_ms(),
            &order.params,
        );
        assert!(query.starts_with(
            "symbol=BTCUSDT&side=BUY&type=MARKET&quantity=1&timestamp=1700000000000&recvWindow=5000&signature="
        ));
        assert_eq!(query.rsplit_once('=').expect("signature").1.len(), 64);
    }

    #[test]
    fn parses_order_result_with_cpp_fallback_fields() {
        let payload = json!({
            "symbol": "BTCUSDT",
            "side": "BUY",
            "positionSide": "LONG",
            "orderId": 12345,
            "status": "FILLED",
            "executedQty": "0",
            "origQty": "0.2",
            "avgPrice": "0",
            "price": "21000.5"
        });
        let result =
            parse_futures_order_result(&payload, "ETHUSDT", "SELL", "BOTH").expect("order result");
        assert_eq!(result.symbol, "BTCUSDT");
        assert_eq!(result.side, "BUY");
        assert_eq!(result.position_side, "LONG");
        assert_eq!(result.order_id, "12345");
        assert_eq!(result.status, "FILLED");
        assert_eq!(result.executed_qty, 0.2);
        assert_eq!(result.avg_price, 21000.5);
    }

    #[test]
    fn validation_and_error_payloads_fail_closed() {
        assert!(build_futures_market_order_params("", "BUY", 1.0, false, "").is_err());
        assert!(build_futures_market_order_params("BTCUSDT", "HOLD", 1.0, false, "").is_err());
        assert!(
            build_futures_limit_order_params("BTCUSDT", "BUY", 1.0, 0.0, false, "", "").is_err()
        );

        let payload = json!({"code": -2010, "msg": "Account has insufficient balance."});
        assert!(parse_futures_order_result(&payload, "BTCUSDT", "BUY", "BOTH").is_err());
    }
}
