use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::generated_python_parity::{PYTHON_CONNECTOR_OPTIONS, PythonConnectorOption};
use crate::order_audit::{redact_text, redact_value};

pub const DEFAULT_CONNECTOR_BACKEND: &str = "binance-sdk-derivatives-trading-usds-futures";
pub const SUPPORTED_EXCHANGES: &[&str] = &["Binance"];
pub const SUPPORTED_FOREX_BROKERS: &[&str] = &[];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ExchangeSupportInput {
    pub selected_exchange: String,
    pub connector_backend: String,
    pub selected_forex_broker: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ExchangeSupportPayload {
    pub selected_exchange: String,
    pub connector_backend: String,
    pub selected_forex_broker: String,
    pub exchange_supported: bool,
    pub connector_backend_supported: bool,
    pub broker_supported: bool,
    pub trading_supported: bool,
    pub unsupported_reasons: Vec<String>,
    pub supported_exchanges: Vec<String>,
    pub supported_connector_backends: Vec<String>,
    pub supported_forex_brokers: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LimiterSettings {
    pub max_per_minute: f64,
    pub min_interval: f64,
    pub safety_margin: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorHttpBackoff {
    pub triggered: bool,
    pub ban_until: f64,
    pub seconds_until_unban: f64,
    pub category: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConnectorHealthInput {
    pub credentials_present: bool,
    pub connector_backend: String,
    pub account_type: String,
    pub mode: String,
    pub seconds_until_unban: f64,
    pub network_offline: bool,
    pub network_offline_since: Option<f64>,
    pub network_offline_hits: u64,
    pub last_error: Option<Value>,
    pub order_audit: Option<Value>,
    pub generated_at: f64,
}

impl Default for ConnectorHealthInput {
    fn default() -> Self {
        Self {
            credentials_present: false,
            connector_backend: String::new(),
            account_type: String::new(),
            mode: String::new(),
            seconds_until_unban: 0.0,
            network_offline: false,
            network_offline_since: None,
            network_offline_hits: 0,
            last_error: None,
            order_audit: None,
            generated_at: 0.0,
        }
    }
}

pub fn connector_options() -> &'static [PythonConnectorOption] {
    PYTHON_CONNECTOR_OPTIONS
}

pub fn support_key(value: impl AsRef<str>) -> String {
    value.as_ref().trim().to_lowercase().replace('_', "-")
}

pub fn supported_connector_backends() -> Vec<String> {
    PYTHON_CONNECTOR_OPTIONS
        .iter()
        .map(|option| option.key.to_owned())
        .collect()
}

pub fn normalize_connector_backend(value: impl AsRef<str>) -> String {
    let key = support_key(value);
    if key.is_empty() {
        return DEFAULT_CONNECTOR_BACKEND.to_owned();
    }
    if let Some(option) = PYTHON_CONNECTOR_OPTIONS
        .iter()
        .find(|option| support_key(option.key) == key)
    {
        option.key.to_owned()
    } else {
        key
    }
}

pub fn build_exchange_support_payload(
    config: ExchangeSupportInput,
    snapshot: Option<ExchangeSupportInput>,
) -> ExchangeSupportPayload {
    let raw = snapshot.unwrap_or_default();
    let selected_exchange = first_non_empty(&[&raw.selected_exchange, &config.selected_exchange])
        .unwrap_or_else(|| "Unknown".to_owned());
    let connector_backend = first_non_empty(&[&raw.connector_backend, &config.connector_backend])
        .unwrap_or_else(|| "Unknown".to_owned());
    let selected_forex_broker =
        first_non_empty(&[&raw.selected_forex_broker, &config.selected_forex_broker])
            .unwrap_or_default();

    let exchange_supported = SUPPORTED_EXCHANGES
        .iter()
        .any(|item| support_key(item) == support_key(&selected_exchange));
    let supported_backends = supported_connector_backends();
    let connector_backend_supported = supported_backends
        .iter()
        .any(|item| support_key(item) == support_key(&connector_backend));
    let broker_supported = selected_forex_broker.trim().is_empty()
        || SUPPORTED_FOREX_BROKERS
            .iter()
            .any(|item| support_key(item) == support_key(&selected_forex_broker));

    let mut unsupported_reasons = Vec::new();
    if !exchange_supported {
        unsupported_reasons.push(format!(
            "Exchange '{selected_exchange}' is not implemented by this runtime."
        ));
    }
    if !connector_backend_supported {
        unsupported_reasons.push(format!(
            "Connector backend '{connector_backend}' is not implemented by this runtime."
        ));
    }
    if !broker_supported {
        unsupported_reasons.push(format!(
            "Forex broker '{selected_forex_broker}' is not implemented by this runtime."
        ));
    }

    ExchangeSupportPayload {
        selected_exchange,
        connector_backend,
        selected_forex_broker,
        exchange_supported,
        connector_backend_supported,
        broker_supported,
        trading_supported: exchange_supported && connector_backend_supported && broker_supported,
        unsupported_reasons,
        supported_exchanges: SUPPORTED_EXCHANGES
            .iter()
            .map(|item| (*item).to_owned())
            .collect(),
        supported_connector_backends: supported_backends,
        supported_forex_brokers: SUPPORTED_FOREX_BROKERS
            .iter()
            .map(|item| (*item).to_owned())
            .collect(),
    }
}

fn first_non_empty(values: &[&String]) -> Option<String> {
    values
        .iter()
        .map(|item| item.trim())
        .find(|item| !item.is_empty())
        .map(str::to_owned)
}

pub fn estimate_request_weight(path: impl AsRef<str>) -> f64 {
    let lower = path.as_ref().to_lowercase();
    if lower.is_empty() {
        return 1.0;
    }
    if lower.contains("exchangeinfo") {
        10.0
    } else if lower.contains("balance") || lower.contains("account") {
        5.0
    } else if lower.contains("position") {
        5.0
    } else if lower.contains("klines") {
        4.0
    } else if lower.contains("ticker") {
        if lower.contains("price") { 1.0 } else { 2.0 }
    } else if lower.contains("margin") || lower.contains("leverage") || lower.contains("order") {
        1.0
    } else {
        2.0
    }
}

pub fn environment_tag(mode_value: impl AsRef<str>) -> &'static str {
    let text = mode_value.as_ref().to_lowercase();
    if text.contains("test") || text.contains("demo") {
        "testnet"
    } else {
        "live"
    }
}

pub fn account_tag(account_value: impl AsRef<str>) -> &'static str {
    if account_value
        .as_ref()
        .trim()
        .to_uppercase()
        .starts_with("SPOT")
    {
        "spot"
    } else {
        "futures"
    }
}

pub fn limiter_settings_for(
    env_tag: impl AsRef<str>,
    acct_tag: impl AsRef<str>,
) -> LimiterSettings {
    let env = env_tag.as_ref();
    let acct = acct_tag.as_ref();
    if env == "testnet" {
        LimiterSettings {
            max_per_minute: 180.0,
            min_interval: 0.65,
            safety_margin: 0.8,
        }
    } else if acct == "spot" {
        LimiterSettings {
            max_per_minute: 900.0,
            min_interval: 0.25,
            safety_margin: 0.85,
        }
    } else {
        LimiterSettings {
            max_per_minute: 1100.0,
            min_interval: 0.2,
            safety_margin: 0.9,
        }
    }
}

pub fn extract_ban_until(message: impl AsRef<str>, now_epoch: f64) -> Option<f64> {
    let message = message.as_ref();
    if message.is_empty() {
        return None;
    }
    if let Some(raw) = number_after(message, "banned until ") {
        return Some(if raw > 1e12 {
            raw / 1000.0
        } else if raw > 1e5 {
            raw
        } else {
            now_epoch + raw
        });
    }
    if let Some(raw) = number_after_any(message, &["after ", "wait "]) {
        let lower = message.to_lowercase();
        if lower.contains("ms") || lower.contains("milliseconds") {
            return Some(now_epoch + (raw / 1000.0).max(0.0));
        }
        if lower.contains('s') || lower.contains("seconds") {
            return Some(now_epoch + raw.max(0.0));
        }
    }
    None
}

fn number_after_any(message: &str, prefixes: &[&str]) -> Option<f64> {
    prefixes
        .iter()
        .find_map(|prefix| number_after(message, prefix))
}

fn number_after(message: &str, prefix: &str) -> Option<f64> {
    let lower = message.to_lowercase();
    let start = lower.find(prefix)? + prefix.len();
    let digits: String = lower[start..]
        .chars()
        .skip_while(|ch| ch.is_whitespace())
        .take_while(|ch| ch.is_ascii_digit() || *ch == '.')
        .collect();
    digits.parse::<f64>().ok()
}

pub fn build_http_backoff(
    status_code: Option<i64>,
    code: Option<i64>,
    message: impl AsRef<str>,
    retry_after: Option<f64>,
    now_epoch: f64,
) -> Option<ConnectorHttpBackoff> {
    let message = message.as_ref();
    let lower = message.to_lowercase();
    let triggered = matches!(code, Some(-1003 | 429))
        || matches!(status_code, Some(418 | 429))
        || lower.contains("banned until")
        || lower.contains("too many requests")
        || lower.contains("too frequent")
        || lower.contains("frequency");
    if !triggered {
        return None;
    }
    let ban_until = extract_ban_until(message, now_epoch)
        .or_else(|| retry_after.map(|seconds| now_epoch + seconds.max(0.0)))
        .unwrap_or(now_epoch + 8.0);
    Some(ConnectorHttpBackoff {
        triggered: true,
        ban_until,
        seconds_until_unban: (ban_until - now_epoch).max(0.0),
        category: "rate_limited".to_owned(),
    })
}

pub fn build_connector_health_snapshot(input: ConnectorHealthInput) -> Value {
    let last_error = input.last_error.map(redact_value);
    let category = last_error
        .as_ref()
        .and_then(|value| value.get("category"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_lowercase();
    let retryable = last_error
        .as_ref()
        .and_then(|value| value.get("retryable"))
        .and_then(Value::as_bool);

    let mut health = if input.credentials_present {
        "ok".to_owned()
    } else {
        "unknown".to_owned()
    };
    let mut state = if input.credentials_present {
        "ready".to_owned()
    } else {
        "missing_credentials".to_owned()
    };
    if input.network_offline {
        health = "error".to_owned();
        state = "network_offline".to_owned();
    } else if input.seconds_until_unban > 0.0 {
        health = "warning".to_owned();
        state = "rate_limited".to_owned();
    } else if last_error.is_some() {
        if category == "auth" {
            health = "error".to_owned();
            state = "auth_error".to_owned();
        } else if category == "rate_limited" {
            health = "warning".to_owned();
            state = "rate_limited".to_owned();
        } else if retryable == Some(true) {
            health = "warning".to_owned();
            state = if category.is_empty() {
                "exchange_warning".to_owned()
            } else {
                category.clone()
            };
        } else {
            health = "error".to_owned();
            state = if category.is_empty() {
                "exchange_error".to_owned()
            } else {
                category.clone()
            };
        }
    }

    let order_audit = input.order_audit.map(redact_value);
    if order_audit
        .as_ref()
        .and_then(|value| value.get("last_write_error"))
        .is_some()
        && health != "error"
    {
        health = "warning".to_owned();
        if matches!(state.as_str(), "ready" | "missing_credentials" | "unknown") {
            state = "order_audit_write_failed".to_owned();
        }
    }

    let mut payload = json!({
        "health": health,
        "state": state,
        "generated_at": input.generated_at,
        "source": "binance-wrapper",
        "selected_exchange": "Binance",
        "connector_backend": non_empty_or(input.connector_backend, "Unknown"),
        "account_type": non_empty_or(input.account_type, "Unknown"),
        "mode": non_empty_or(input.mode, "Unknown"),
        "rate_limit": {
            "active": input.seconds_until_unban > 0.0,
            "seconds_until_unban": input.seconds_until_unban.max(0.0),
            "ban_until": if input.seconds_until_unban > 0.0 {
                Value::from(input.generated_at + input.seconds_until_unban)
            } else {
                Value::Null
            },
        },
        "network": {
            "offline": input.network_offline,
            "offline_since": input.network_offline_since,
            "offline_hits": input.network_offline_hits,
        },
        "last_error": last_error,
    });
    if let Some(order_audit) = order_audit {
        payload["order_audit"] = order_audit;
    }
    redact_value(payload)
}

fn non_empty_or(value: String, fallback: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        fallback.to_owned()
    } else {
        redact_text(trimmed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn support_payload_matches_python_exchange_support() {
        let supported = build_exchange_support_payload(
            ExchangeSupportInput {
                selected_exchange: "Binance".to_owned(),
                connector_backend: DEFAULT_CONNECTOR_BACKEND.to_owned(),
                selected_forex_broker: String::new(),
            },
            None,
        );
        assert!(supported.trading_supported);
        assert!(
            supported
                .supported_connector_backends
                .contains(&"ccxt".to_owned())
        );

        let unsupported = build_exchange_support_payload(
            ExchangeSupportInput {
                selected_exchange: "Bybit".to_owned(),
                connector_backend: "custom-native".to_owned(),
                selected_forex_broker: "MetaTrader".to_owned(),
            },
            None,
        );
        assert!(!unsupported.trading_supported);
        assert!(
            unsupported
                .unsupported_reasons
                .contains(&"Exchange 'Bybit' is not implemented by this runtime.".to_owned())
        );
        assert!(unsupported.unsupported_reasons.contains(
            &"Connector backend 'custom-native' is not implemented by this runtime.".to_owned()
        ));
        assert!(
            unsupported.unsupported_reasons.contains(
                &"Forex broker 'MetaTrader' is not implemented by this runtime.".to_owned()
            )
        );
    }

    #[test]
    fn rate_limit_weights_and_limiter_settings_follow_python_runtime() {
        assert_eq!(estimate_request_weight("/fapi/v1/exchangeInfo"), 10.0);
        assert_eq!(estimate_request_weight("/fapi/v2/balance"), 5.0);
        assert_eq!(estimate_request_weight("/fapi/v1/klines"), 4.0);
        assert_eq!(estimate_request_weight("/fapi/v1/ticker/price"), 1.0);
        assert_eq!(environment_tag("Demo/Testnet"), "testnet");
        assert_eq!(account_tag("Spot"), "spot");
        assert_eq!(
            limiter_settings_for("testnet", "futures"),
            LimiterSettings {
                max_per_minute: 180.0,
                min_interval: 0.65,
                safety_margin: 0.8,
            }
        );
        assert_eq!(
            limiter_settings_for("live", "spot"),
            LimiterSettings {
                max_per_minute: 900.0,
                min_interval: 0.25,
                safety_margin: 0.85,
            }
        );
    }

    #[test]
    fn http_backoff_parses_bans_retry_after_and_default_pause() {
        let banned = build_http_backoff(
            Some(418),
            Some(-1003),
            "IP banned until 1770000100000",
            None,
            1_770_000_000.0,
        )
        .expect("ban");
        assert_eq!(banned.ban_until, 1_770_000_100.0);
        assert_eq!(banned.seconds_until_unban, 100.0);

        let retry = build_http_backoff(
            Some(429),
            None,
            "Too many requests",
            Some(12.5),
            1_770_000_000.0,
        )
        .expect("retry");
        assert_eq!(retry.seconds_until_unban, 12.5);

        let default_pause =
            build_http_backoff(None, None, "request too frequent", None, 1_770_000_000.0)
                .expect("default pause");
        assert_eq!(default_pause.seconds_until_unban, 8.0);
    }

    #[test]
    fn health_snapshot_matches_python_diagnostics_and_redacts() {
        let snapshot = build_connector_health_snapshot(ConnectorHealthInput {
            credentials_present: true,
            connector_backend: "binance-sdk-spot".to_owned(),
            account_type: "Spot".to_owned(),
            mode: "Live".to_owned(),
            seconds_until_unban: 12.5,
            last_error: Some(json!({
                "category": "rate_limited",
                "message": "Too many requests signature=leaked",
                "retryable": true,
            })),
            generated_at: 1_770_000_000.0,
            ..Default::default()
        });
        assert_eq!(snapshot["health"], "warning");
        assert_eq!(snapshot["state"], "rate_limited");
        assert_eq!(snapshot["rate_limit"]["active"], true);
        assert_eq!(
            snapshot["last_error"]["message"],
            "Too many requests signature=<redacted>"
        );
        assert!(!snapshot.to_string().contains("leaked"));

        let auth = build_connector_health_snapshot(ConnectorHealthInput {
            credentials_present: true,
            last_error: Some(json!({"category": "auth", "message": "api_secret=leaked"})),
            ..Default::default()
        });
        assert_eq!(auth["health"], "error");
        assert_eq!(auth["state"], "auth_error");
    }
}
