use anyhow::{Result, bail};

use crate::account::BinanceFuturesPosition;
use crate::orders::{
    BinanceFuturesOrderParams, build_futures_market_order_params, format_decimal_for_order,
};

const POSITION_CLOSE_EPSILON: f64 = 1e-10;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinanceFuturesCloseMethod {
    ClosePosition,
    ReduceOnly,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BinanceFuturesCloseDirective {
    pub symbol: String,
    pub side: String,
    pub position_side: String,
    pub quantity: f64,
    pub quantity_text: String,
    pub reduce_only: bool,
    pub close_position: bool,
    pub method: BinanceFuturesCloseMethod,
}

impl BinanceFuturesCloseDirective {
    pub fn to_order_params(&self) -> Result<BinanceFuturesOrderParams> {
        match self.method {
            BinanceFuturesCloseMethod::ClosePosition => {
                build_close_position_params(&self.symbol, &self.side, &self.position_side)
            }
            BinanceFuturesCloseMethod::ReduceOnly => build_reduce_only_close_params(
                &self.symbol,
                &self.side,
                self.quantity,
                &self.position_side,
            ),
        }
    }
}

pub fn derive_futures_close_side(
    position_amt: f64,
    position_side: impl AsRef<str>,
    hedge_mode: bool,
) -> Option<(String, String)> {
    if !position_amt.is_finite() || position_amt.abs() <= POSITION_CLOSE_EPSILON {
        return None;
    }

    let position_side = normalize_position_side(position_side.as_ref());
    if hedge_mode {
        match position_side.as_str() {
            "LONG" => return Some(("SELL".to_owned(), "LONG".to_owned())),
            "SHORT" => return Some(("BUY".to_owned(), "SHORT".to_owned())),
            _ => {}
        }
    }

    if position_amt > 0.0 {
        Some((
            "SELL".to_owned(),
            if hedge_mode {
                "LONG".to_owned()
            } else {
                String::new()
            },
        ))
    } else {
        Some((
            "BUY".to_owned(),
            if hedge_mode {
                "SHORT".to_owned()
            } else {
                String::new()
            },
        ))
    }
}

pub fn plan_futures_position_close(
    position: &BinanceFuturesPosition,
    hedge_mode: bool,
    step_size: f64,
    prefer_close_position: bool,
) -> Result<Vec<BinanceFuturesCloseDirective>> {
    let symbol = normalize_symbol(&position.symbol)?;
    let Some((side, position_side)) =
        derive_futures_close_side(position.position_amt, &position.position_side, hedge_mode)
    else {
        return Ok(Vec::new());
    };

    let mut directives = Vec::new();
    if prefer_close_position {
        directives.push(close_position_directive(&symbol, &side, &position_side)?);
    }
    directives.push(reduce_only_directive(
        &symbol,
        &side,
        position.position_amt.abs(),
        step_size,
        &position_side,
    )?);
    Ok(directives)
}

pub fn plan_close_all_futures_positions(
    positions: &[BinanceFuturesPosition],
    hedge_mode: bool,
    prefer_close_position: bool,
) -> Result<Vec<BinanceFuturesCloseDirective>> {
    plan_close_all_futures_positions_with_steps(positions, &[], hedge_mode, prefer_close_position)
}

pub fn plan_close_all_futures_positions_with_steps(
    positions: &[BinanceFuturesPosition],
    step_size_by_symbol: &[(&str, f64)],
    hedge_mode: bool,
    prefer_close_position: bool,
) -> Result<Vec<BinanceFuturesCloseDirective>> {
    let mut directives = Vec::new();
    for position in positions {
        let step_size = step_size_for_symbol(step_size_by_symbol, &position.symbol);
        directives.extend(plan_futures_position_close(
            position,
            hedge_mode,
            step_size,
            prefer_close_position,
        )?);
    }
    Ok(directives)
}

pub fn build_close_position_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    position_side: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    let symbol = normalize_symbol(symbol.as_ref())?;
    let side = normalize_order_side(side.as_ref())?;
    let position_side = normalize_position_side(position_side.as_ref());
    let has_directional_side = is_directional_position_side(&position_side);

    let mut params = vec![
        ("symbol", symbol.clone()),
        ("side", side.clone()),
        ("type", "MARKET".to_owned()),
        ("closePosition", "true".to_owned()),
    ];
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

pub fn build_reduce_only_close_params(
    symbol: impl AsRef<str>,
    side: impl AsRef<str>,
    quantity: f64,
    position_side: impl AsRef<str>,
) -> Result<BinanceFuturesOrderParams> {
    build_futures_market_order_params(symbol, side, quantity, true, position_side)
}

pub fn format_quantity_for_close_order(value: f64, step_size: f64) -> Result<String> {
    if !value.is_finite() || value <= 0.0 {
        bail!("Close quantity must be > 0");
    }

    let adjusted = if step_size.is_finite() && step_size > 0.0 {
        (value / step_size).floor() * step_size
    } else {
        value
    };
    let precision = quantity_precision_from_step(step_size);
    let text = format_decimal_for_order(adjusted, precision);
    let parsed = text.parse::<f64>().unwrap_or(0.0);
    if !parsed.is_finite() || parsed <= 0.0 {
        bail!("Close quantity rounds below the symbol step size");
    }
    Ok(text)
}

pub fn quantity_precision_from_step(step_size: f64) -> usize {
    if !step_size.is_finite() || step_size <= 0.0 {
        return 8;
    }
    let text = format!("{step_size:.16}");
    let trimmed = text.trim_end_matches('0').trim_end_matches('.');
    trimmed
        .split_once('.')
        .map(|(_, decimals)| decimals.len().min(16))
        .unwrap_or(0)
}

fn close_position_directive(
    symbol: &str,
    side: &str,
    position_side: &str,
) -> Result<BinanceFuturesCloseDirective> {
    let order = build_close_position_params(symbol, side, position_side)?;
    Ok(BinanceFuturesCloseDirective {
        symbol: order.symbol,
        side: order.side,
        position_side: order.position_side,
        quantity: 0.0,
        quantity_text: String::new(),
        reduce_only: false,
        close_position: true,
        method: BinanceFuturesCloseMethod::ClosePosition,
    })
}

fn reduce_only_directive(
    symbol: &str,
    side: &str,
    quantity: f64,
    step_size: f64,
    position_side: &str,
) -> Result<BinanceFuturesCloseDirective> {
    let quantity_text = format_quantity_for_close_order(quantity, step_size)?;
    let quantity = quantity_text.parse::<f64>().unwrap_or(quantity);
    let order = build_reduce_only_close_params(symbol, side, quantity, position_side)?;
    Ok(BinanceFuturesCloseDirective {
        symbol: order.symbol,
        side: order.side,
        position_side: order.position_side,
        quantity,
        quantity_text,
        reduce_only: !is_directional_position_side(position_side),
        close_position: false,
        method: BinanceFuturesCloseMethod::ReduceOnly,
    })
}

fn step_size_for_symbol(step_size_by_symbol: &[(&str, f64)], symbol: &str) -> f64 {
    let normalized_symbol = symbol.trim().to_uppercase();
    for (current_symbol, step_size) in step_size_by_symbol {
        if current_symbol
            .trim()
            .eq_ignore_ascii_case(&normalized_symbol)
        {
            return *step_size;
        }
    }
    0.0
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

fn is_directional_position_side(value: &str) -> bool {
    matches!(value.trim().to_uppercase().as_str(), "LONG" | "SHORT")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn position(symbol: &str, amount: f64, position_side: &str) -> BinanceFuturesPosition {
        BinanceFuturesPosition {
            symbol: symbol.to_owned(),
            position_amt: amount,
            position_side: position_side.to_owned(),
            ..Default::default()
        }
    }

    #[test]
    fn derives_one_way_close_sides_like_python_and_cpp() {
        assert_eq!(
            derive_futures_close_side(0.5, "BOTH", false),
            Some(("SELL".to_owned(), String::new()))
        );
        assert_eq!(
            derive_futures_close_side(-0.5, "BOTH", false),
            Some(("BUY".to_owned(), String::new()))
        );
        assert_eq!(derive_futures_close_side(0.0, "BOTH", false), None);
    }

    #[test]
    fn derives_hedge_close_sides_from_position_side_first() {
        assert_eq!(
            derive_futures_close_side(0.5, "LONG", true),
            Some(("SELL".to_owned(), "LONG".to_owned()))
        );
        assert_eq!(
            derive_futures_close_side(-0.5, "SHORT", true),
            Some(("BUY".to_owned(), "SHORT".to_owned()))
        );
        assert_eq!(
            derive_futures_close_side(0.5, "BOTH", true),
            Some(("SELL".to_owned(), "LONG".to_owned()))
        );
        assert_eq!(
            derive_futures_close_side(-0.5, "", true),
            Some(("BUY".to_owned(), "SHORT".to_owned()))
        );
    }

    #[test]
    fn reduce_only_close_params_match_cpp_hedge_mode_rule() {
        let one_way =
            build_reduce_only_close_params("btcusdt", "sell", 0.125, "").expect("one-way close");
        assert_eq!(
            one_way.params,
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "0.125".to_owned()),
                ("reduceOnly", "true".to_owned()),
            ]
        );

        let hedge =
            build_reduce_only_close_params("btcusdt", "buy", 2.0, "SHORT").expect("hedge close");
        assert_eq!(
            hedge.params,
            vec![
                ("symbol", "BTCUSDT".to_owned()),
                ("side", "BUY".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "2".to_owned()),
                ("positionSide", "SHORT".to_owned()),
            ]
        );
    }

    #[test]
    fn close_position_params_match_python_close_all_first_attempt() {
        let params =
            build_close_position_params("ethusdt", "sell", "LONG").expect("close-position params");
        assert_eq!(
            params.params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("closePosition", "true".to_owned()),
                ("positionSide", "LONG".to_owned()),
            ]
        );
    }

    #[test]
    fn close_quantity_formats_down_to_step_like_python_decimal_quantize() {
        assert_eq!(
            format_quantity_for_close_order(1.23456, 0.001).expect("quantity"),
            "1.234"
        );
        assert_eq!(
            format_quantity_for_close_order(2.0, 1.0).expect("quantity"),
            "2"
        );
        assert!(format_quantity_for_close_order(0.0004, 0.001).is_err());
    }

    #[test]
    fn position_close_plan_can_prefer_close_position_then_quantity_fallback() {
        let plan =
            plan_futures_position_close(&position("ethusdt", 1.23456, "LONG"), true, 0.001, true)
                .expect("close plan");
        assert_eq!(plan.len(), 2);
        assert_eq!(plan[0].method, BinanceFuturesCloseMethod::ClosePosition);
        assert!(plan[0].close_position);
        assert_eq!(plan[0].side, "SELL");
        assert_eq!(plan[0].position_side, "LONG");

        assert_eq!(plan[1].method, BinanceFuturesCloseMethod::ReduceOnly);
        assert!(!plan[1].reduce_only);
        assert_eq!(plan[1].quantity_text, "1.234");
        assert_eq!(
            plan[1].to_order_params().expect("fallback params").params,
            vec![
                ("symbol", "ETHUSDT".to_owned()),
                ("side", "SELL".to_owned()),
                ("type", "MARKET".to_owned()),
                ("quantity", "1.234".to_owned()),
                ("positionSide", "LONG".to_owned()),
            ]
        );
    }

    #[test]
    fn close_all_plan_filters_flat_positions_and_uses_symbol_steps() {
        let positions = vec![
            position("BTCUSDT", 0.0, "BOTH"),
            position("ETHUSDT", 0.56789, "BOTH"),
            position("SOLUSDT", -3.456, "SHORT"),
        ];
        let plan = plan_close_all_futures_positions_with_steps(
            &positions,
            &[("ETHUSDT", 0.01), ("SOLUSDT", 0.1)],
            true,
            false,
        )
        .expect("close-all plan");
        assert_eq!(plan.len(), 2);
        assert_eq!(plan[0].symbol, "ETHUSDT");
        assert_eq!(plan[0].side, "SELL");
        assert_eq!(plan[0].position_side, "LONG");
        assert_eq!(plan[0].quantity_text, "0.56");
        assert_eq!(plan[1].symbol, "SOLUSDT");
        assert_eq!(plan[1].side, "BUY");
        assert_eq!(plan[1].position_side, "SHORT");
        assert_eq!(plan[1].quantity_text, "3.4");
    }
}
