use std::collections::BTreeMap;

use serde_json::Value;

use crate::generated_python_parity::PYTHON_INDICATOR_CATALOG;
use crate::market_data::BinanceKlineCandle;

/// Runtime indicators currently computed natively from the Python-owned config.
///
/// Future unknown catalog items remain visible in the generated contract but are
/// not silently approximated here. The native runtime only evaluates a selected
/// item when this module has an explicit, tested implementation for it.
pub const NATIVE_RUNTIME_COMPUTED_INDICATOR_KEYS: &[&str] = &[
    "ma",
    "donchian",
    "psar",
    "ema",
    "bb",
    "bbw",
    "rsi",
    "volume",
    "obv",
    "rvol",
    "cmf",
    "cci",
    "roc",
    "trix",
    "ppo",
    "ao",
    "atr",
    "natr",
    "vwap",
    "mfi",
    "keltner",
    "ichimoku",
    "kst",
    "aroon",
    "chop",
    "uo",
    "adx",
    "dmi",
    "supertrend",
    "stoch_rsi",
    "willr",
    "macd",
    "stochastic",
];

pub fn default_runtime_indicator_configs() -> BTreeMap<String, Value> {
    PYTHON_INDICATOR_CATALOG
        .iter()
        .filter(|indicator| indicator.default_enabled)
        .filter_map(|indicator| {
            serde_json::from_str::<Value>(indicator.runtime_config_json)
                .ok()
                .map(|config| (indicator.key.to_owned(), config))
        })
        .collect()
}

pub fn unsupported_enabled_indicator_keys(configs: &BTreeMap<String, Value>) -> Vec<String> {
    configs
        .iter()
        .filter(|(key, config)| {
            config_enabled(config)
                && !NATIVE_RUNTIME_COMPUTED_INDICATOR_KEYS.contains(&key.as_str())
        })
        .map(|(key, _)| key.clone())
        .collect()
}

pub fn compute_configured_indicator_series(
    candles: &[BinanceKlineCandle],
    configs: &BTreeMap<String, Value>,
) -> BTreeMap<String, Vec<f64>> {
    let mut output = BTreeMap::new();
    for (key, config) in configs {
        if !config_enabled(config) {
            continue;
        }
        match key.as_str() {
            "donchian" => {
                let (high, low, middle) =
                    donchian_channels(candles, config_length(config, "length", 20));
                output.insert("donchian_high".to_owned(), high);
                output.insert("donchian_low".to_owned(), low);
                output.insert("donchian".to_owned(), middle);
            }
            "psar" => {
                output.insert(
                    "psar".to_owned(),
                    parabolic_sar_series(
                        candles,
                        config_f64(config, "af", 0.02),
                        config_f64(config, "max_af", 0.2),
                    ),
                );
            }
            "ma" => {
                let values = closes(candles);
                let length = config_length(config, "length", 20);
                let series = match config_string(config, "type").as_deref() {
                    Some("EMA") => ema_series(&values, length),
                    _ => rolling_mean_exact(&values, length),
                };
                output.insert("ma".to_owned(), series);
            }
            "ema" => {
                output.insert(
                    "ema".to_owned(),
                    ema_series(&closes(candles), config_length(config, "length", 20)),
                );
            }
            "bb" => {
                let (upper, middle, lower) = bollinger_bands(
                    &closes(candles),
                    config_length(config, "length", 20),
                    config_f64(config, "std", 2.0),
                );
                output.insert("bb_upper".to_owned(), upper);
                output.insert("bb_mid".to_owned(), middle);
                output.insert("bb_lower".to_owned(), lower);
            }
            "bbw" => {
                output.insert(
                    "bbw".to_owned(),
                    bollinger_band_width(
                        &closes(candles),
                        config_length(config, "length", 20),
                        config_f64(config, "std", 2.0),
                    ),
                );
            }
            "keltner" => {
                let (upper, middle, lower) = keltner_channels(
                    candles,
                    config_length(config, "length", 20),
                    config_length(config, "atr_length", 10),
                    config_f64(config, "multiplier", 2.0),
                );
                output.insert("keltner_upper".to_owned(), upper);
                output.insert("keltner_mid".to_owned(), middle);
                output.insert("keltner_lower".to_owned(), lower);
            }
            "ichimoku" => {
                let (tenkan, kijun, span_a, span_b, chikou) = ichimoku_cloud(
                    candles,
                    config_length(config, "conversion_length", 9),
                    config_length(config, "base_length", 26),
                    config_length(config, "span_b_length", 52),
                    config_length(config, "displacement", 26),
                );
                let difference = tenkan
                    .iter()
                    .zip(&kijun)
                    .map(|(tenkan, kijun)| tenkan - kijun)
                    .collect();
                output.insert("ichimoku_tenkan".to_owned(), tenkan);
                output.insert("ichimoku_kijun".to_owned(), kijun);
                output.insert("ichimoku_span_a".to_owned(), span_a);
                output.insert("ichimoku_span_b".to_owned(), span_b);
                output.insert("ichimoku_chikou".to_owned(), chikou);
                output.insert("ichimoku".to_owned(), difference);
            }
            "rsi" => {
                output.insert(
                    "rsi".to_owned(),
                    rsi_series(candles, config_length(config, "length", 14)),
                );
            }
            "stoch_rsi" => {
                let (k, d) = stoch_rsi_series(
                    candles,
                    config_length(config, "length", 14),
                    config_length(config, "smooth_k", 3),
                    config_length(config, "smooth_d", 3),
                );
                output.insert("stoch_rsi".to_owned(), k.clone());
                output.insert("stoch_rsi_k".to_owned(), k);
                output.insert("stoch_rsi_d".to_owned(), d);
            }
            "willr" => {
                output.insert(
                    "willr".to_owned(),
                    williams_r_series(candles, config_length(config, "length", 14)),
                );
            }
            "volume" => {
                output.insert("volume".to_owned(), volumes(candles));
            }
            "obv" => {
                output.insert("obv".to_owned(), obv_series(candles));
            }
            "rvol" => {
                output.insert(
                    "rvol".to_owned(),
                    relative_volume_series(candles, config_length(config, "length", 20)),
                );
            }
            "cmf" => {
                output.insert(
                    "cmf".to_owned(),
                    chaikin_money_flow_series(candles, config_length(config, "length", 20)),
                );
            }
            "cci" => {
                output.insert(
                    "cci".to_owned(),
                    cci_series(
                        candles,
                        config_length(config, "length", 20),
                        config_f64(config, "constant", 0.015),
                    ),
                );
            }
            "roc" => {
                output.insert(
                    "roc".to_owned(),
                    roc_series(&closes(candles), config_length(config, "length", 12)),
                );
            }
            "trix" => {
                output.insert(
                    "trix".to_owned(),
                    trix_series(&closes(candles), config_length(config, "length", 15)),
                );
            }
            "ppo" => {
                let (line, signal, hist) = ppo_series(
                    &closes(candles),
                    config_length(config, "fast", 12),
                    config_length(config, "slow", 26),
                    config_length(config, "signal", 9),
                );
                output.insert("ppo".to_owned(), line);
                output.insert("ppo_signal".to_owned(), signal);
                output.insert("ppo_hist".to_owned(), hist);
            }
            "ao" => {
                output.insert(
                    "ao".to_owned(),
                    awesome_oscillator_series(
                        candles,
                        config_length(config, "fast", 5),
                        config_length(config, "slow", 34),
                    ),
                );
            }
            "kst" => {
                let (line, signal, histogram) = kst_series(
                    &closes(candles),
                    config_length(config, "roc1", 10),
                    config_length(config, "roc2", 15),
                    config_length(config, "roc3", 20),
                    config_length(config, "roc4", 30),
                    config_length(config, "sma1", 10),
                    config_length(config, "sma2", 10),
                    config_length(config, "sma3", 10),
                    config_length(config, "sma4", 15),
                    config_length(config, "signal", 9),
                );
                output.insert("kst".to_owned(), line);
                output.insert("kst_signal".to_owned(), signal);
                output.insert("kst_hist".to_owned(), histogram);
            }
            "aroon" => {
                let (up, down, oscillator) =
                    aroon_series(candles, config_length(config, "length", 25));
                output.insert("aroon_up".to_owned(), up);
                output.insert("aroon_down".to_owned(), down);
                output.insert("aroon".to_owned(), oscillator);
            }
            "chop" => {
                output.insert(
                    "chop".to_owned(),
                    choppiness_index_series(candles, config_length(config, "length", 14)),
                );
            }
            "atr" => {
                output.insert(
                    "atr".to_owned(),
                    atr_series(candles, config_length(config, "length", 14)),
                );
            }
            "natr" => {
                output.insert(
                    "natr".to_owned(),
                    natr_series(candles, config_length(config, "length", 14)),
                );
            }
            "vwap" => {
                output.insert(
                    "vwap".to_owned(),
                    vwap_series(candles, config_length(config, "length", 20)),
                );
            }
            "mfi" => {
                output.insert(
                    "mfi".to_owned(),
                    mfi_series(candles, config_length(config, "length", 14)),
                );
            }
            "uo" => {
                output.insert(
                    "uo".to_owned(),
                    ultimate_oscillator_series(
                        candles,
                        config_length(config, "short", 7),
                        config_length(config, "medium", 14),
                        config_length(config, "long", 28),
                    ),
                );
            }
            "macd" => {
                let (line, signal, _) = macd_series(
                    &closes(candles),
                    config_length(config, "fast", 12),
                    config_length(config, "slow", 26),
                    config_length(config, "signal", 9),
                );
                output.insert("macd_line".to_owned(), line);
                output.insert("macd_signal".to_owned(), signal);
            }
            "adx" => {
                let (_, _, adx) = dmi_series(candles, config_length(config, "length", 14));
                output.insert("adx".to_owned(), adx);
            }
            "dmi" => {
                let (plus, minus, _) = dmi_series(candles, config_length(config, "length", 14));
                let difference = plus
                    .iter()
                    .zip(&minus)
                    .map(|(plus, minus)| plus - minus)
                    .collect();
                output.insert("dmi_plus".to_owned(), plus);
                output.insert("dmi_minus".to_owned(), minus);
                output.insert("dmi".to_owned(), difference);
            }
            "supertrend" => {
                output.insert(
                    "supertrend".to_owned(),
                    supertrend_series(
                        candles,
                        config_length(config, "atr_period", 10),
                        config_f64(config, "multiplier", 3.0),
                    ),
                );
            }
            "stochastic" => {
                let (k, d) = stochastic_series(
                    candles,
                    config_length(config, "length", 14),
                    config_length(config, "smooth_k", 3),
                    config_length(config, "smooth_d", 3),
                );
                output.insert("stochastic".to_owned(), k.clone());
                output.insert("stochastic_k".to_owned(), k);
                output.insert("stochastic_d".to_owned(), d);
            }
            _ => {}
        }
    }
    output
}

pub fn rsi_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let length = length.max(1);
    let mut result = vec![f64::NAN; candles.len()];
    if candles.len() < 2 {
        return result;
    }

    let alpha = 1.0 / length as f64;
    let mut average_gain = 0.0;
    let mut average_loss = 0.0;
    for index in 1..candles.len() {
        let delta = candles[index].close - candles[index - 1].close;
        if !delta.is_finite() {
            continue;
        }
        let gain = delta.max(0.0);
        let loss = (-delta).max(0.0);
        if index == 1 {
            average_gain = gain;
            average_loss = loss;
        } else {
            average_gain = alpha * gain + (1.0 - alpha) * average_gain;
            average_loss = alpha * loss + (1.0 - alpha) * average_loss;
        }
        result[index] = if average_loss == 0.0 {
            if average_gain == 0.0 { f64::NAN } else { 100.0 }
        } else {
            100.0 - (100.0 / (1.0 + average_gain / average_loss))
        };
    }
    result
}

pub fn stoch_rsi_series(
    candles: &[BinanceKlineCandle],
    length: usize,
    smooth_k: usize,
    smooth_d: usize,
) -> (Vec<f64>, Vec<f64>) {
    let length = length.max(1);
    let rsi = rsi_series(candles, length);
    let mut stochastic = vec![f64::NAN; rsi.len()];
    for index in 0..rsi.len() {
        let Some(window) = exact_finite_window(&rsi, index, length) else {
            continue;
        };
        let min = window.iter().copied().fold(f64::INFINITY, f64::min);
        let max = window.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        if max != min {
            stochastic[index] = 100.0 * (rsi[index] - min) / (max - min);
        }
    }
    let k = rolling_mean_exact(&stochastic, smooth_k.max(1));
    let d = rolling_mean_exact(&k, smooth_d.max(1));
    (k, d)
}

pub fn williams_r_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let length = length.max(1);
    let mut result = vec![f64::NAN; candles.len()];
    for index in 0..candles.len() {
        if index + 1 < length {
            continue;
        }
        let window = &candles[index + 1 - length..=index];
        if !window.iter().all(|candle| {
            candle.high.is_finite() && candle.low.is_finite() && candle.close.is_finite()
        }) {
            continue;
        }
        let highest = window
            .iter()
            .map(|candle| candle.high)
            .fold(f64::NEG_INFINITY, f64::max);
        let lowest = window
            .iter()
            .map(|candle| candle.low)
            .fold(f64::INFINITY, f64::min);
        if highest != lowest {
            result[index] = (highest - candles[index].close) / (highest - lowest) * -100.0;
        }
    }
    result
}

fn closes(candles: &[BinanceKlineCandle]) -> Vec<f64> {
    candles.iter().map(|candle| candle.close).collect()
}

fn volumes(candles: &[BinanceKlineCandle]) -> Vec<f64> {
    candles.iter().map(|candle| candle.volume).collect()
}

fn ema_series(values: &[f64], length: usize) -> Vec<f64> {
    let alpha = 2.0 / (length.max(1) as f64 + 1.0);
    let mut previous = f64::NAN;
    values
        .iter()
        .map(|value| {
            if !value.is_finite() {
                previous = f64::NAN;
            } else if previous.is_finite() {
                previous = alpha * value + (1.0 - alpha) * previous;
            } else {
                previous = *value;
            }
            previous
        })
        .collect()
}

fn rolling_mean_min(values: &[f64], length: usize) -> Vec<f64> {
    let length = length.max(1);
    (0..values.len())
        .map(|index| {
            let window = &values[index + 1 - length.min(index + 1)..=index];
            let finite = window
                .iter()
                .copied()
                .filter(|value| value.is_finite())
                .collect::<Vec<_>>();
            if finite.is_empty() {
                f64::NAN
            } else {
                finite.iter().sum::<f64>() / finite.len() as f64
            }
        })
        .collect()
}

fn rolling_sum_min(values: &[f64], length: usize) -> Vec<f64> {
    let length = length.max(1);
    (0..values.len())
        .map(|index| {
            let window = &values[index + 1 - length.min(index + 1)..=index];
            let finite = window
                .iter()
                .copied()
                .filter(|value| value.is_finite())
                .collect::<Vec<_>>();
            if finite.is_empty() {
                f64::NAN
            } else {
                finite.iter().sum()
            }
        })
        .collect()
}

fn bollinger_bands(values: &[f64], length: usize, std: f64) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let middle = rolling_mean_exact(values, length);
    let deviation = (0..values.len())
        .map(|index| {
            let Some(window) = exact_finite_window(values, index, length) else {
                return f64::NAN;
            };
            if window.len() < 2 {
                return f64::NAN;
            }
            let mean = middle[index];
            (window
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                / (window.len() - 1) as f64)
                .sqrt()
        })
        .collect::<Vec<_>>();
    let upper = middle
        .iter()
        .zip(&deviation)
        .map(|(mean, deviation)| mean + std * deviation)
        .collect();
    let lower = middle
        .iter()
        .zip(&deviation)
        .map(|(mean, deviation)| mean - std * deviation)
        .collect();
    (upper, middle, lower)
}

fn bollinger_band_width(values: &[f64], length: usize, std: f64) -> Vec<f64> {
    let (upper, middle, lower) = bollinger_bands(values, length, std);
    upper
        .iter()
        .zip(middle.iter().zip(lower))
        .map(|(upper, (middle, lower))| {
            if middle.is_finite() && *middle != 0.0 && upper.is_finite() && lower.is_finite() {
                (upper - lower) / middle * 100.0
            } else {
                0.0
            }
        })
        .collect()
}

fn true_range_series(candles: &[BinanceKlineCandle]) -> Vec<f64> {
    candles
        .iter()
        .enumerate()
        .map(|(index, candle)| {
            let base = (candle.high - candle.low).abs();
            if index == 0 {
                base
            } else {
                let previous_close = candles[index - 1].close;
                base.max((candle.high - previous_close).abs())
                    .max((candle.low - previous_close).abs())
            }
        })
        .collect()
}

fn atr_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let values = true_range_series(candles);
    let alpha = 1.0 / length.max(1) as f64;
    let mut previous = f64::NAN;
    values
        .into_iter()
        .map(|value| {
            previous = if previous.is_finite() {
                alpha * value + (1.0 - alpha) * previous
            } else {
                value
            };
            previous
        })
        .collect()
}

fn natr_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    atr_series(candles, length)
        .into_iter()
        .zip(candles)
        .map(|(atr, candle)| {
            if atr.is_finite() && candle.close.is_finite() && candle.close != 0.0 {
                atr / candle.close * 100.0
            } else {
                0.0
            }
        })
        .collect()
}

fn obv_series(candles: &[BinanceKlineCandle]) -> Vec<f64> {
    let mut cumulative = 0.0;
    candles
        .iter()
        .enumerate()
        .map(|(index, candle)| {
            if index > 0 {
                cumulative += if candle.close > candles[index - 1].close {
                    candle.volume
                } else if candle.close < candles[index - 1].close {
                    -candle.volume
                } else {
                    0.0
                };
            }
            cumulative
        })
        .collect()
}

fn relative_volume_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let volume = volumes(candles);
    volume
        .iter()
        .zip(rolling_mean_min(&volume, length))
        .map(|(value, average)| {
            if average.is_finite() && average != 0.0 {
                value / average
            } else {
                0.0
            }
        })
        .collect()
}

fn chaikin_money_flow_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let money_flow_volume = candles
        .iter()
        .map(|candle| {
            let range = candle.high - candle.low;
            if range == 0.0 {
                0.0
            } else {
                ((candle.close - candle.low) - (candle.high - candle.close)) / range * candle.volume
            }
        })
        .collect::<Vec<_>>();
    let volume = volumes(candles);
    rolling_sum_min(&money_flow_volume, length)
        .into_iter()
        .zip(rolling_sum_min(&volume, length))
        .map(|(flow, volume)| {
            if flow.is_finite() && volume.is_finite() && volume != 0.0 {
                flow / volume
            } else {
                0.0
            }
        })
        .collect()
}

fn cci_series(candles: &[BinanceKlineCandle], length: usize, constant: f64) -> Vec<f64> {
    let typical = candles
        .iter()
        .map(|candle| (candle.high + candle.low + candle.close) / 3.0)
        .collect::<Vec<_>>();
    let average = rolling_mean_min(&typical, length);
    (0..typical.len())
        .map(|index| {
            let window = &typical[index + 1 - length.max(1).min(index + 1)..=index];
            let deviation = window
                .iter()
                .map(|value| (value - average[index]).abs())
                .sum::<f64>()
                / window.len() as f64;
            let denominator = constant * deviation;
            if denominator.is_finite() && denominator != 0.0 {
                (typical[index] - average[index]) / denominator
            } else {
                0.0
            }
        })
        .collect()
}

fn roc_series(values: &[f64], length: usize) -> Vec<f64> {
    let length = length.max(1);
    values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            if index < length || values[index - length] == 0.0 {
                0.0
            } else {
                (value - values[index - length]) / values[index - length] * 100.0
            }
        })
        .collect()
}

fn trix_series(values: &[f64], length: usize) -> Vec<f64> {
    let third = ema_series(&ema_series(&ema_series(values, length), length), length);
    third
        .iter()
        .enumerate()
        .map(|(index, value)| {
            if index == 0 || third[index - 1] == 0.0 {
                0.0
            } else {
                (value / third[index - 1] - 1.0) * 100.0
            }
        })
        .collect()
}

fn macd_series(
    values: &[f64],
    fast: usize,
    slow: usize,
    signal: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let fast = ema_series(values, fast);
    let slow = ema_series(values, slow);
    let line = fast
        .iter()
        .zip(&slow)
        .map(|(fast, slow)| fast - slow)
        .collect::<Vec<_>>();
    let signal = ema_series(&line, signal);
    let histogram = line
        .iter()
        .zip(&signal)
        .map(|(line, signal)| line - signal)
        .collect();
    (line, signal, histogram)
}

fn ppo_series(
    values: &[f64],
    fast: usize,
    slow: usize,
    signal: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let fast = ema_series(values, fast);
    let slow = ema_series(values, slow);
    let line = fast
        .iter()
        .zip(&slow)
        .map(|(fast, slow)| {
            if *slow != 0.0 {
                (fast - slow) / slow * 100.0
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let signal = ema_series(&line, signal);
    let histogram = line
        .iter()
        .zip(&signal)
        .map(|(line, signal)| line - signal)
        .collect();
    (line, signal, histogram)
}

fn awesome_oscillator_series(candles: &[BinanceKlineCandle], fast: usize, slow: usize) -> Vec<f64> {
    let median = candles
        .iter()
        .map(|candle| (candle.high + candle.low) / 2.0)
        .collect::<Vec<_>>();
    rolling_mean_min(&median, fast)
        .into_iter()
        .zip(rolling_mean_min(&median, slow))
        .map(|(fast, slow)| {
            if fast.is_finite() && slow.is_finite() {
                fast - slow
            } else {
                0.0
            }
        })
        .collect()
}

fn vwap_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let typical = candles
        .iter()
        .map(|candle| (candle.high + candle.low + candle.close) / 3.0)
        .collect::<Vec<_>>();
    let volume = volumes(candles);
    let weighted = typical
        .iter()
        .zip(&volume)
        .map(|(price, volume)| price * volume)
        .collect::<Vec<_>>();
    rolling_sum_min(&weighted, length)
        .into_iter()
        .zip(rolling_sum_min(&volume, length))
        .map(|(weighted, volume)| {
            if weighted.is_finite() && volume.is_finite() && volume != 0.0 {
                weighted / volume
            } else {
                f64::NAN
            }
        })
        .collect()
}

fn mfi_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let typical = candles
        .iter()
        .map(|candle| (candle.high + candle.low + candle.close) / 3.0)
        .collect::<Vec<_>>();
    let raw = typical
        .iter()
        .zip(candles)
        .map(|(price, candle)| price * candle.volume)
        .collect::<Vec<_>>();
    let positive = raw
        .iter()
        .enumerate()
        .map(|(index, flow)| {
            if index > 0 && typical[index] > typical[index - 1] {
                *flow
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let negative = raw
        .iter()
        .enumerate()
        .map(|(index, flow)| {
            if index > 0 && typical[index] < typical[index - 1] {
                *flow
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    rolling_sum_min(&positive, length)
        .into_iter()
        .zip(rolling_sum_min(&negative, length))
        .map(|(positive, negative)| {
            if positive == 0.0 && negative == 0.0 {
                50.0
            } else if positive == 0.0 {
                0.0
            } else if negative == 0.0 {
                100.0
            } else {
                100.0 - 100.0 / (1.0 + positive / negative)
            }
        })
        .collect()
}

fn stochastic_series(
    candles: &[BinanceKlineCandle],
    length: usize,
    smooth_k: usize,
    smooth_d: usize,
) -> (Vec<f64>, Vec<f64>) {
    let length = length.max(1);
    let raw = candles
        .iter()
        .enumerate()
        .map(|(index, candle)| {
            if index + 1 < length {
                return f64::NAN;
            }
            let window = &candles[index + 1 - length..=index];
            let high = window
                .iter()
                .map(|candle| candle.high)
                .fold(f64::NEG_INFINITY, f64::max);
            let low = window
                .iter()
                .map(|candle| candle.low)
                .fold(f64::INFINITY, f64::min);
            if high != low {
                100.0 * (candle.close - low) / (high - low)
            } else {
                f64::NAN
            }
        })
        .collect::<Vec<_>>();
    let k_raw = rolling_mean_min(&raw, smooth_k);
    let d_raw = rolling_mean_min(&k_raw, smooth_d);
    let k = k_raw
        .into_iter()
        .map(|value| if value.is_finite() { value } else { 0.0 })
        .collect::<Vec<_>>();
    let d = d_raw
        .into_iter()
        .map(|value| if value.is_finite() { value } else { 0.0 })
        .collect::<Vec<_>>();
    (k, d)
}

fn keltner_channels(
    candles: &[BinanceKlineCandle],
    length: usize,
    atr_length: usize,
    multiplier: f64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let middle = ema_series(&closes(candles), length);
    let range = atr_series(candles, atr_length);
    let upper = middle
        .iter()
        .zip(&range)
        .map(|(middle, range)| middle + range * multiplier)
        .collect();
    let lower = middle
        .iter()
        .zip(&range)
        .map(|(middle, range)| middle - range * multiplier)
        .collect();
    (upper, middle, lower)
}

fn rolling_midpoint(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let length = length.max(1);
    (0..candles.len())
        .map(|index| {
            if index + 1 < length {
                return f64::NAN;
            }
            let window = &candles[index + 1 - length..=index];
            let high = window
                .iter()
                .map(|candle| candle.high)
                .fold(f64::NEG_INFINITY, f64::max);
            let low = window
                .iter()
                .map(|candle| candle.low)
                .fold(f64::INFINITY, f64::min);
            (high + low) / 2.0
        })
        .collect()
}

fn donchian_channels(
    candles: &[BinanceKlineCandle],
    length: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let length = length.max(1);
    let high = (0..candles.len())
        .map(|index| {
            if index + 1 < length {
                f64::NAN
            } else {
                candles[index + 1 - length..=index]
                    .iter()
                    .map(|candle| candle.high)
                    .fold(f64::NEG_INFINITY, f64::max)
            }
        })
        .collect::<Vec<_>>();
    let low = (0..candles.len())
        .map(|index| {
            if index + 1 < length {
                f64::NAN
            } else {
                candles[index + 1 - length..=index]
                    .iter()
                    .map(|candle| candle.low)
                    .fold(f64::INFINITY, f64::min)
            }
        })
        .collect::<Vec<_>>();
    let middle = high
        .iter()
        .zip(&low)
        .map(|(high, low)| (high + low) / 2.0)
        .collect();
    (high, low, middle)
}

fn parabolic_sar_series(candles: &[BinanceKlineCandle], af: f64, max_af: f64) -> Vec<f64> {
    if candles.is_empty() {
        return Vec::new();
    }
    let mut result = candles
        .iter()
        .map(|candle| candle.close)
        .collect::<Vec<_>>();
    let mut bullish = true;
    let mut acceleration = af;
    let mut extreme_point = candles[0].high;
    result[0] = candles[0].low;
    for index in 1..candles.len() {
        result[index] = result[index - 1] + acceleration * (extreme_point - result[index - 1]);
        if bullish {
            if candles[index].low < result[index] {
                bullish = false;
                result[index] = extreme_point;
                acceleration = af;
                extreme_point = candles[index].low;
            } else if candles[index].high > extreme_point {
                extreme_point = candles[index].high;
                acceleration = (acceleration + af).min(max_af);
            }
        } else if candles[index].high > result[index] {
            bullish = true;
            result[index] = extreme_point;
            acceleration = af;
            extreme_point = candles[index].high;
        } else if candles[index].low < extreme_point {
            extreme_point = candles[index].low;
            acceleration = (acceleration + af).min(max_af);
        }
    }
    result
}

fn shift_right(values: &[f64], offset: usize) -> Vec<f64> {
    (0..values.len())
        .map(|index| {
            if index < offset {
                f64::NAN
            } else {
                values[index - offset]
            }
        })
        .collect()
}

fn shift_left(values: &[f64], offset: usize) -> Vec<f64> {
    (0..values.len())
        .map(|index| values.get(index + offset).copied().unwrap_or(f64::NAN))
        .collect()
}

fn ichimoku_cloud(
    candles: &[BinanceKlineCandle],
    conversion_length: usize,
    base_length: usize,
    span_b_length: usize,
    displacement: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>) {
    let tenkan = rolling_midpoint(candles, conversion_length);
    let kijun = rolling_midpoint(candles, base_length);
    let unshifted_span_a = tenkan
        .iter()
        .zip(&kijun)
        .map(|(tenkan, kijun)| (tenkan + kijun) / 2.0)
        .collect::<Vec<_>>();
    let span_a = shift_right(&unshifted_span_a, displacement);
    let span_b = shift_right(&rolling_midpoint(candles, span_b_length), displacement);
    let chikou = shift_left(&closes(candles), displacement);
    (tenkan, kijun, span_a, span_b, chikou)
}

#[allow(clippy::too_many_arguments)]
fn kst_series(
    values: &[f64],
    roc1: usize,
    roc2: usize,
    roc3: usize,
    roc4: usize,
    sma1: usize,
    sma2: usize,
    sma3: usize,
    sma4: usize,
    signal: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let roc_1 = rolling_mean_min(&roc_series(values, roc1), sma1);
    let roc_2 = rolling_mean_min(&roc_series(values, roc2), sma2);
    let roc_3 = rolling_mean_min(&roc_series(values, roc3), sma3);
    let roc_4 = rolling_mean_min(&roc_series(values, roc4), sma4);
    let line = (0..values.len())
        .map(|index| roc_1[index] + 2.0 * roc_2[index] + 3.0 * roc_3[index] + 4.0 * roc_4[index])
        .collect::<Vec<_>>();
    let signal_line = rolling_mean_min(&line, signal);
    let histogram = line
        .iter()
        .zip(&signal_line)
        .map(|(line, signal)| line - signal)
        .collect();
    (line, signal_line, histogram)
}

fn aroon_series(candles: &[BinanceKlineCandle], length: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let length = length.max(1);
    let score = |values: Vec<f64>, find_high: bool| {
        (0..values.len())
            .map(|index| {
                let start = index + 1 - length.min(index + 1);
                let window = &values[start..=index];
                if window.len() <= 1 {
                    return 100.0;
                }
                let mut chosen = 0usize;
                for (position, value) in window.iter().enumerate() {
                    if (find_high && *value >= window[chosen])
                        || (!find_high && *value <= window[chosen])
                    {
                        chosen = position;
                    }
                }
                100.0 * chosen as f64 / (window.len() - 1) as f64
            })
            .collect::<Vec<_>>()
    };
    let up = score(candles.iter().map(|candle| candle.high).collect(), true);
    let down = score(candles.iter().map(|candle| candle.low).collect(), false);
    let oscillator = up.iter().zip(&down).map(|(up, down)| up - down).collect();
    (up, down, oscillator)
}

fn choppiness_index_series(candles: &[BinanceKlineCandle], length: usize) -> Vec<f64> {
    let length = length.max(2);
    let tr = true_range_series(candles);
    (0..candles.len())
        .map(|index| {
            if index + 1 < length {
                return 0.0;
            }
            let candle_window = &candles[index + 1 - length..=index];
            let range = candle_window
                .iter()
                .map(|candle| candle.high)
                .fold(f64::NEG_INFINITY, f64::max)
                - candle_window
                    .iter()
                    .map(|candle| candle.low)
                    .fold(f64::INFINITY, f64::min);
            let sum = tr[index + 1 - length..=index].iter().sum::<f64>();
            if range > 0.0 && sum > 0.0 {
                100.0 * (sum / range).log10() / (length as f64).log10()
            } else {
                0.0
            }
        })
        .collect()
}

fn ultimate_oscillator_series(
    candles: &[BinanceKlineCandle],
    short: usize,
    medium: usize,
    long: usize,
) -> Vec<f64> {
    let mut buying_pressure = Vec::with_capacity(candles.len());
    let mut true_range = Vec::with_capacity(candles.len());
    for (index, candle) in candles.iter().enumerate() {
        let previous_close = if index == 0 {
            candle.close
        } else {
            candles[index - 1].close
        };
        let true_low = candle.low.min(previous_close);
        let true_high = candle.high.max(previous_close);
        buying_pressure.push(candle.close - true_low);
        true_range.push(true_high - true_low);
    }
    let ratio = |length| {
        rolling_sum_min(&buying_pressure, length)
            .into_iter()
            .zip(rolling_sum_min(&true_range, length))
            .map(|(pressure, range)| if range != 0.0 { pressure / range } else { 0.0 })
            .collect::<Vec<_>>()
    };
    let short = ratio(short);
    let medium = ratio(medium);
    let long = ratio(long);
    (0..candles.len())
        .map(|index| 100.0 * (4.0 * short[index] + 2.0 * medium[index] + long[index]) / 7.0)
        .collect()
}

fn ewm_alpha_series(values: &[f64], alpha: f64) -> Vec<f64> {
    let mut previous = f64::NAN;
    values
        .iter()
        .map(|value| {
            previous = if previous.is_finite() {
                alpha * value + (1.0 - alpha) * previous
            } else {
                *value
            };
            previous
        })
        .collect()
}

fn dmi_series(candles: &[BinanceKlineCandle], length: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let length = length.max(1);
    let mut plus_dm = Vec::with_capacity(candles.len());
    let mut minus_dm = Vec::with_capacity(candles.len());
    for (index, candle) in candles.iter().enumerate() {
        if index == 0 {
            plus_dm.push(0.0);
            minus_dm.push(0.0);
            continue;
        }
        let up_move = candle.high - candles[index - 1].high;
        let down_move = candles[index - 1].low - candle.low;
        plus_dm.push(if up_move > down_move && up_move > 0.0 {
            up_move
        } else {
            0.0
        });
        minus_dm.push(if down_move > up_move && down_move > 0.0 {
            down_move
        } else {
            0.0
        });
    }
    let atr = atr_series(candles, length);
    let plus_smoothed = ewm_alpha_series(&plus_dm, 1.0 / length as f64);
    let minus_smoothed = ewm_alpha_series(&minus_dm, 1.0 / length as f64);
    let plus = plus_smoothed
        .iter()
        .zip(&atr)
        .map(|(value, atr)| {
            if *atr != 0.0 {
                100.0 * value / atr
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let minus = minus_smoothed
        .iter()
        .zip(&atr)
        .map(|(value, atr)| {
            if *atr != 0.0 {
                100.0 * value / atr
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let dx = plus
        .iter()
        .zip(&minus)
        .map(|(plus, minus)| {
            let sum = plus + minus;
            if sum != 0.0 {
                (plus - minus).abs() / sum * 100.0
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let adx = ewm_alpha_series(&dx, 1.0 / length as f64);
    (plus, minus, adx)
}

fn supertrend_series(
    candles: &[BinanceKlineCandle],
    atr_period: usize,
    multiplier: f64,
) -> Vec<f64> {
    if candles.is_empty() {
        return Vec::new();
    }
    let atr = atr_series(candles, atr_period);
    let basic_upper = candles
        .iter()
        .zip(&atr)
        .map(|(candle, atr)| (candle.high + candle.low) / 2.0 + multiplier * atr)
        .collect::<Vec<_>>();
    let basic_lower = candles
        .iter()
        .zip(&atr)
        .map(|(candle, atr)| (candle.high + candle.low) / 2.0 - multiplier * atr)
        .collect::<Vec<_>>();
    let mut final_upper = basic_upper.clone();
    let mut final_lower = basic_lower.clone();
    for index in 1..candles.len() {
        final_upper[index] = if candles[index - 1].close > final_upper[index - 1] {
            basic_upper[index]
        } else {
            basic_upper[index].min(final_upper[index - 1])
        };
        final_lower[index] = if candles[index - 1].close < final_lower[index - 1] {
            basic_lower[index]
        } else {
            basic_lower[index].max(final_lower[index - 1])
        };
    }
    let mut line = vec![(candles[0].high + candles[0].low) / 2.0];
    for index in 1..candles.len() {
        let next = if line[index - 1] == final_upper[index - 1] {
            if candles[index].close <= final_upper[index] {
                final_upper[index]
            } else {
                final_lower[index]
            }
        } else if candles[index].close >= final_lower[index] {
            final_lower[index]
        } else {
            final_upper[index]
        };
        line.push(next);
    }
    candles
        .iter()
        .zip(&line)
        .map(|(candle, line)| candle.close - line)
        .collect()
}

fn config_enabled(config: &Value) -> bool {
    match config.get("enabled") {
        Some(Value::Bool(value)) => *value,
        Some(Value::Number(value)) => value.as_f64().is_some_and(|value| value != 0.0),
        Some(Value::String(value)) => matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on" | "y"
        ),
        _ => false,
    }
}

fn config_length(config: &Value, key: &str, fallback: usize) -> usize {
    config
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .filter(|value| *value > 0)
        .unwrap_or(fallback)
}

fn config_f64(config: &Value, key: &str, fallback: f64) -> f64 {
    config
        .get(key)
        .and_then(|value| match value {
            Value::Number(value) => value.as_f64(),
            Value::String(value) => value.trim().parse::<f64>().ok(),
            _ => None,
        })
        .filter(|value| value.is_finite())
        .filter(|value| *value != 0.0)
        .unwrap_or(fallback)
}

fn config_string(config: &Value, key: &str) -> Option<String> {
    config
        .get(key)
        .and_then(Value::as_str)
        .map(|value| value.trim().to_ascii_uppercase())
        .filter(|value| !value.is_empty())
}

fn exact_finite_window(values: &[f64], index: usize, length: usize) -> Option<&[f64]> {
    if index + 1 < length {
        return None;
    }
    let window = &values[index + 1 - length..=index];
    window
        .iter()
        .all(|value| value.is_finite())
        .then_some(window)
}

fn rolling_mean_exact(values: &[f64], length: usize) -> Vec<f64> {
    (0..values.len())
        .map(|index| {
            exact_finite_window(values, index, length)
                .map(|window| window.iter().sum::<f64>() / length as f64)
                .unwrap_or(f64::NAN)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn candle(index: i64, close: f64) -> BinanceKlineCandle {
        BinanceKlineCandle {
            open_time_ms: index * 60_000,
            open: close - 0.5,
            high: close + 1.0,
            low: close - 1.0,
            close,
            volume: 100.0,
        }
    }

    #[test]
    fn default_runtime_catalog_uses_python_enabled_rsi_config() {
        let configs = default_runtime_indicator_configs();
        let rsi = configs.get("rsi").expect("Python runtime RSI config");
        assert_eq!(rsi.get("enabled").and_then(Value::as_bool), Some(true));
        assert_eq!(rsi.get("length").and_then(Value::as_u64), Some(14));
    }

    #[test]
    fn native_calculator_coverage_matches_every_python_catalog_key() {
        let python_keys = PYTHON_INDICATOR_CATALOG
            .iter()
            .map(|indicator| indicator.key)
            .collect::<BTreeSet<_>>();
        let native_keys = NATIVE_RUNTIME_COMPUTED_INDICATOR_KEYS
            .iter()
            .copied()
            .collect::<BTreeSet<_>>();
        assert_eq!(native_keys, python_keys);
    }

    #[test]
    fn rsi_matches_python_wilder_seed_and_handles_flat_series_as_nan() {
        let rising = rsi_series(&[candle(0, 1.0), candle(1, 2.0), candle(2, 3.0)], 14);
        assert!(rising[0].is_nan());
        assert_eq!(rising[1], 100.0);
        assert_eq!(rising[2], 100.0);

        let flat = rsi_series(&[candle(0, 1.0), candle(1, 1.0)], 14);
        assert!(flat[1].is_nan());
    }

    #[test]
    fn rolling_helpers_match_pandas_min_periods_and_or_default_semantics() {
        let mean = rolling_mean_min(&[f64::NAN, 10.0, 20.0], 2);
        assert!(mean[0].is_nan());
        assert_eq!(mean[1], 10.0);
        assert_eq!(mean[2], 15.0);
        let config = serde_json::json!({"multiplier": 0.0});
        assert_eq!(config_f64(&config, "multiplier", 2.0), 2.0);
    }

    #[test]
    fn configured_stoch_rsi_and_williams_r_preserve_python_warmup_behavior() {
        let candles: Vec<_> = [100.0, 102.0, 99.0, 103.0, 98.0, 104.0, 97.0, 105.0, 96.0]
            .into_iter()
            .enumerate()
            .map(|(index, close)| candle(index as i64, close))
            .collect();
        let configs = BTreeMap::from([
            (
                "stoch_rsi".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "smooth_k": 2, "smooth_d": 2}),
            ),
            (
                "willr".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
        ]);
        let values = compute_configured_indicator_series(&candles, &configs);
        assert!(values["stoch_rsi"][0].is_nan());
        assert!(values["stoch_rsi_k"][6].is_finite());
        assert!(values["stoch_rsi_d"][7].is_finite());
        assert!(values["willr"][1].is_nan());
        assert!(values["willr"][2].is_finite());
    }

    #[test]
    fn configured_price_and_volume_group_matches_python_warmup_and_output_keys() {
        let candles: Vec<_> = [100.0, 102.0, 99.0, 103.0, 98.0, 104.0]
            .into_iter()
            .enumerate()
            .map(|(index, close)| candle(index as i64, close))
            .collect();
        let configs = BTreeMap::from([
            (
                "ma".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "type": "SMA"}),
            ),
            (
                "ema".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "bb".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "std": 2}),
            ),
            (
                "atr".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "natr".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            ("volume".to_owned(), serde_json::json!({"enabled": true})),
            ("obv".to_owned(), serde_json::json!({"enabled": true})),
            (
                "rvol".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "cmf".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "cci".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "constant": 0.015}),
            ),
            (
                "roc".to_owned(),
                serde_json::json!({"enabled": true, "length": 2}),
            ),
            (
                "trix".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "ppo".to_owned(),
                serde_json::json!({"enabled": true, "fast": 2, "slow": 3, "signal": 2}),
            ),
            (
                "ao".to_owned(),
                serde_json::json!({"enabled": true, "fast": 2, "slow": 3}),
            ),
            (
                "vwap".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "mfi".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "macd".to_owned(),
                serde_json::json!({"enabled": true, "fast": 2, "slow": 3, "signal": 2}),
            ),
            (
                "stochastic".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "smooth_k": 2, "smooth_d": 2}),
            ),
        ]);

        let values = compute_configured_indicator_series(&candles, &configs);
        assert!(values["ma"][0].is_nan());
        assert!((values["ma"][2] - (100.0 + 102.0 + 99.0) / 3.0).abs() < 1e-10);
        assert_eq!(values["ema"][0], 100.0);
        assert!(values["bb_upper"][2].is_finite());
        assert!(values["bb_mid"][2].is_finite());
        assert!(values["bb_lower"][2].is_finite());
        assert_eq!(values["volume"], vec![100.0; 6]);
        assert_eq!(values["obv"][0], 0.0);
        assert_eq!(values["obv"][1], 100.0);
        assert_eq!(values["obv"][2], 0.0);
        assert_eq!(values["rvol"], vec![1.0; 6]);
        assert_eq!(values["cmf"], vec![0.0; 6]);
        assert_eq!(values["roc"][0], 0.0);
        assert!(values["roc"][2].is_finite());
        assert!(values["atr"].iter().all(|value| value.is_finite()));
        assert!(values["natr"].iter().all(|value| value.is_finite()));
        assert!(values["ppo_hist"].iter().all(|value| value.is_finite()));
        assert!(values["macd_line"].iter().all(|value| value.is_finite()));
        assert!(values["stochastic_k"].iter().all(|value| value.is_finite()));
        assert!(values["stochastic_d"].iter().all(|value| value.is_finite()));
    }

    #[test]
    fn configured_extended_catalog_group_exposes_python_strategy_output_keys() {
        let candles: Vec<_> = [100.0, 102.0, 99.0, 103.0, 98.0, 104.0, 97.0, 105.0]
            .into_iter()
            .enumerate()
            .map(|(index, close)| candle(index as i64, close))
            .collect();
        let configs = BTreeMap::from([
            (
                "donchian".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "psar".to_owned(),
                serde_json::json!({"enabled": true, "af": 0.02, "max_af": 0.2}),
            ),
            (
                "keltner".to_owned(),
                serde_json::json!({"enabled": true, "length": 3, "atr_length": 2, "multiplier": 2.0}),
            ),
            (
                "ichimoku".to_owned(),
                serde_json::json!({"enabled": true, "conversion_length": 2, "base_length": 3, "span_b_length": 4, "displacement": 2}),
            ),
            (
                "kst".to_owned(),
                serde_json::json!({"enabled": true, "roc1": 1, "roc2": 2, "roc3": 3, "roc4": 4, "sma1": 2, "sma2": 2, "sma3": 2, "sma4": 2, "signal": 2}),
            ),
            (
                "aroon".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "chop".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "uo".to_owned(),
                serde_json::json!({"enabled": true, "short": 2, "medium": 3, "long": 4}),
            ),
            (
                "adx".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "dmi".to_owned(),
                serde_json::json!({"enabled": true, "length": 3}),
            ),
            (
                "supertrend".to_owned(),
                serde_json::json!({"enabled": true, "atr_period": 2, "multiplier": 3.0}),
            ),
        ]);
        let values = compute_configured_indicator_series(&candles, &configs);
        for key in [
            "donchian",
            "donchian_high",
            "donchian_low",
            "psar",
            "keltner_upper",
            "keltner_mid",
            "keltner_lower",
            "ichimoku",
            "ichimoku_tenkan",
            "ichimoku_kijun",
            "ichimoku_span_a",
            "ichimoku_span_b",
            "ichimoku_chikou",
            "kst",
            "kst_signal",
            "kst_hist",
            "aroon",
            "aroon_up",
            "aroon_down",
            "chop",
            "uo",
            "adx",
            "dmi",
            "dmi_plus",
            "dmi_minus",
            "supertrend",
        ] {
            assert_eq!(
                values[key].len(),
                candles.len(),
                "missing or wrong-length {key}"
            );
        }
        assert!(values["donchian"][0].is_nan());
        assert!(values["donchian"][2].is_finite());
        assert_eq!(values["psar"][0], candles[0].low);
        assert!(values["keltner_mid"].iter().all(|value| value.is_finite()));
        assert!(values["aroon"].iter().all(|value| value.is_finite()));
        assert!(values["chop"].iter().all(|value| value.is_finite()));
        assert!(values["uo"].iter().all(|value| value.is_finite()));
        assert!(values["adx"].iter().all(|value| value.is_finite()));
        assert!(values["supertrend"].iter().all(|value| value.is_finite()));
    }

    #[test]
    fn native_series_match_python_generated_reference_fixture() {
        let fixture: Value = serde_json::from_str(
            crate::generated_python_indicator_reference::PYTHON_INDICATOR_REFERENCE_JSON,
        )
        .expect("generated Python indicator reference JSON");
        assert_eq!(
            fixture["python_source_contract_hash"].as_str(),
            Some(crate::generated_python_parity::PYTHON_SOURCE_CONTRACT_HASH),
        );
        assert_eq!(
            crate::generated_python_indicator_reference::PYTHON_INDICATOR_REFERENCE_CONTRACT_HASH,
            crate::generated_python_parity::PYTHON_SOURCE_CONTRACT_HASH,
        );
        let candles = fixture["candles"]
            .as_array()
            .expect("fixture candles")
            .iter()
            .enumerate()
            .map(|(index, candle)| BinanceKlineCandle {
                open_time_ms: index as i64 * 60_000,
                open: candle["open"].as_f64().expect("open"),
                high: candle["high"].as_f64().expect("high"),
                low: candle["low"].as_f64().expect("low"),
                close: candle["close"].as_f64().expect("close"),
                volume: candle["volume"].as_f64().expect("volume"),
            })
            .collect::<Vec<_>>();
        let configs = fixture["configs"]
            .as_object()
            .expect("fixture configs")
            .iter()
            .map(|(key, config)| (key.clone(), config.clone()))
            .collect::<BTreeMap<_, _>>();
        let actual = compute_configured_indicator_series(&candles, &configs);
        let expected = fixture["expected"]
            .as_object()
            .expect("fixture expected series");
        assert_eq!(actual.len(), expected.len());
        for (key, expected_series) in expected {
            let actual_series = actual.get(key).unwrap_or_else(|| panic!("missing {key}"));
            let expected_values = expected_series.as_array().expect("fixture series values");
            assert_eq!(
                actual_series.len(),
                expected_values.len(),
                "length mismatch for {key}"
            );
            for (index, (actual_value, expected_value)) in
                actual_series.iter().zip(expected_values).enumerate()
            {
                if expected_value.is_null() {
                    assert!(
                        actual_value.is_nan(),
                        "{key}[{index}] should be NaN, got {actual_value}"
                    );
                } else {
                    let expected_value = expected_value.as_f64().expect("numeric fixture value");
                    let tolerance = 1e-9_f64.max(expected_value.abs() * 1e-9);
                    assert!(
                        (actual_value - expected_value).abs() <= tolerance,
                        "{key}[{index}] expected {expected_value}, got {actual_value}",
                    );
                }
            }
        }
    }
}
