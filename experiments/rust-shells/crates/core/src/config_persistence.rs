use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::time::UNIX_EPOCH;

pub const SERVICE_CONFIG_FILE_KIND: &str = "trading-bot-service-config";
pub const SERVICE_CONFIG_FORMAT_VERSION: i64 = 1;
pub const SERVICE_CONFIG_ENV_PATH: &str = "BOT_SERVICE_CONFIG_PATH";
pub const SERVICE_CONFIG_ALLOW_INLINE_SECRETS_ENV: &str = "BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS";
pub const SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV: &str = "BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH";
pub const DEFAULT_SERVICE_CONFIG_PATH: &str = "~/.trading-bot/service-config.json";
pub const SERVICE_CONFIG_SECRET_STORAGE: &str = "plain-json-on-disk";
pub const SERVICE_CONFIG_SECRET_STORAGE_WARNING: &str = "This service config is plain JSON and contains secret-bearing fields; prefer environment variables or OS credential storage for API keys.";

const SECRET_KEY_TOKENS: &[&str] = &[
    "api_key",
    "api_secret",
    "apikey",
    "api-token",
    "api_token",
    "authorization",
    "bearer",
    "password",
    "secret",
    "signature",
    "token",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServiceConfigSecretMetadata {
    pub contains_secrets: bool,
    pub secret_fields: Vec<String>,
    pub secret_storage: String,
    pub secret_storage_warning: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServiceConfigLoadMetadata {
    pub kind: String,
    pub format_version: i64,
    pub migrated_from_format_version: Option<i64>,
    pub saved_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ServiceConfigLoadResult {
    pub config: Value,
    pub metadata: ServiceConfigLoadMetadata,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ServiceConfigValidationIssue {
    pub field: String,
    pub message: String,
}

impl ServiceConfigValidationIssue {
    fn new(field: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            field: field.into(),
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RustConfigPersistenceBoundary {
    pub shell: &'static str,
    pub role: &'static str,
    pub persistence_owner: &'static str,
    pub validation_owner: &'static str,
    pub operational: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceConfigRuntimeState {
    pub loaded: bool,
    pub dirty: bool,
    pub last_loaded_at: String,
    pub last_saved_at: String,
    pub migrated_from_format_version: Option<i64>,
}

impl Default for ServiceConfigRuntimeState {
    fn default() -> Self {
        Self {
            loaded: false,
            dirty: false,
            last_loaded_at: String::new(),
            last_saved_at: String::new(),
            migrated_from_format_version: None,
        }
    }
}

pub const RUST_CONFIG_PERSISTENCE_BOUNDARIES: &[RustConfigPersistenceBoundary] =
    &[RustConfigPersistenceBoundary {
        shell: "Tauri",
        role: "Operational Python Service API client",
        persistence_owner: "Python Service API /api/v1/config/save and /api/v1/config/load",
        validation_owner: "Python validate_runtime_config with Rust helper parity tests",
        operational: true,
    }];

pub fn service_config_env_flag(value: impl AsRef<str>, default_value: bool) -> bool {
    let text = value.as_ref().trim().to_ascii_lowercase();
    if text.is_empty() {
        return default_value;
    }
    matches!(text.as_str(), "1" | "true" | "yes" | "on")
}

pub fn format_service_config_validation_issues(issues: &[ServiceConfigValidationIssue]) -> String {
    if issues.is_empty() {
        return "Invalid config.".to_owned();
    }
    format!(
        "Invalid config: {}",
        issues
            .iter()
            .map(|issue| format!("{}: {}", issue.field, issue.message))
            .collect::<Vec<_>>()
            .join("; ")
    )
}

pub fn validate_service_runtime_config(config: &Value) -> Result<Value, String> {
    let issues = service_config_validation_issues(config);
    if issues.is_empty() {
        Ok(normalize_service_runtime_config(config))
    } else {
        Err(format_service_config_validation_issues(&issues))
    }
}

pub fn service_config_validation_issues(config: &Value) -> Vec<ServiceConfigValidationIssue> {
    let Some(object) = config.as_object() else {
        return vec![ServiceConfigValidationIssue::new(
            "config",
            "must be an object",
        )];
    };
    let mut cfg = object.clone();
    let mut issues = Vec::new();

    validate_allowed_keys(&cfg, RUNTIME_ALLOWED_KEYS, &mut issues, "");
    validate_text(&mut cfg, "api_key", &mut issues, "", true);
    validate_text(&mut cfg, "api_secret", &mut issues, "", true);
    validate_text(&mut cfg, "mode", &mut issues, "", false);
    validate_choice(
        &mut cfg,
        "account_type",
        ACCOUNT_TYPE_CHOICES,
        &mut issues,
        "",
    );
    validate_choice(
        &mut cfg,
        "margin_mode",
        MARGIN_MODE_CHOICES,
        &mut issues,
        "",
    );
    validate_symbol_list(&mut cfg, "symbols", &mut issues, "", true);
    validate_interval_list(&mut cfg, "intervals", &mut issues, "", true);
    validate_int_range(&mut cfg, "lookback", &mut issues, "", 1, 1_000_000);
    validate_int_range(&mut cfg, "leverage", &mut issues, "", 1, 125);
    validate_choice(&mut cfg, "tif", TIF_CHOICES, &mut issues, "");
    validate_int_range(&mut cfg, "gtd_minutes", &mut issues, "", 1, 7 * 24 * 60);
    validate_choice(
        &mut cfg,
        "position_mode",
        POSITION_MODE_CHOICES,
        &mut issues,
        "",
    );
    validate_choice(
        &mut cfg,
        "assets_mode",
        ASSETS_MODE_CHOICES,
        &mut issues,
        "",
    );
    validate_choice(
        &mut cfg,
        "account_mode",
        ACCOUNT_MODE_CHOICES,
        &mut issues,
        "",
    );
    validate_bool(&mut cfg, "lead_trader_enabled", &mut issues, "", false);
    validate_nullable_text(&mut cfg, "lead_trader_profile", &mut issues, "", true);
    validate_text(&mut cfg, "loop_interval_override", &mut issues, "", true);
    if let Some(value) = cfg.get("loop_interval_override") {
        if !value_to_text(value).trim().is_empty() && normalize_interval(value).is_none() {
            issues.push(ServiceConfigValidationIssue::new(
                "loop_interval_override",
                "must be a valid interval",
            ));
        }
    }
    validate_pair_list(&mut cfg, "runtime_symbol_interval_pairs", &mut issues, "");
    validate_pair_list(&mut cfg, "backtest_symbol_interval_pairs", &mut issues, "");
    validate_choice(&mut cfg, "side", SIDE_CHOICES, &mut issues, "");
    validate_float_range(&mut cfg, "position_pct", &mut issues, "", 0.0, 100.0, true);
    validate_choice(&mut cfg, "order_type", ORDER_TYPE_CHOICES, &mut issues, "");
    validate_bool(&mut cfg, "live_trading_enabled", &mut issues, "", false);
    validate_text(
        &mut cfg,
        "live_trading_acknowledgement",
        &mut issues,
        "",
        true,
    );
    validate_bool(
        &mut cfg,
        "live_allow_auto_bump_to_min_order",
        &mut issues,
        "",
        false,
    );
    validate_int_range(
        &mut cfg,
        "live_trading_max_leverage",
        &mut issues,
        "",
        1,
        125,
    );
    validate_float_range(
        &mut cfg,
        "live_trading_max_position_pct",
        &mut issues,
        "",
        0.0,
        100.0,
        true,
    );
    validate_int_range(
        &mut cfg,
        "live_trading_max_session_orders",
        &mut issues,
        "",
        1,
        100_000,
    );
    validate_bool(&mut cfg, "order_audit_enabled", &mut issues, "", true);
    validate_bool(
        &mut cfg,
        "positions_auto_resize_rows",
        &mut issues,
        "",
        true,
    );
    validate_bool(
        &mut cfg,
        "positions_auto_resize_columns",
        &mut issues,
        "",
        true,
    );
    validate_text(&mut cfg, "order_audit_log_path", &mut issues, "", true);
    validate_int_range(
        &mut cfg,
        "order_audit_max_bytes",
        &mut issues,
        "",
        1,
        1_000_000_000,
    );
    validate_int_range(
        &mut cfg,
        "order_audit_backup_count",
        &mut issues,
        "",
        0,
        100,
    );
    validate_text(
        &mut cfg,
        "connector_order_circuit_incident_log_path",
        &mut issues,
        "",
        true,
    );
    validate_int_range(
        &mut cfg,
        "connector_order_circuit_incident_log_max_bytes",
        &mut issues,
        "",
        1,
        1_000_000_000,
    );
    validate_int_range(
        &mut cfg,
        "connector_order_circuit_incident_log_backup_count",
        &mut issues,
        "",
        0,
        100,
    );
    for key in [
        "operational_connector_snapshot_stale_seconds",
        "operational_execution_heartbeat_stale_seconds",
        "operational_account_snapshot_stale_seconds",
        "operational_portfolio_snapshot_stale_seconds",
        "connector_order_block_window_seconds",
    ] {
        validate_float_range(
            &mut cfg,
            key,
            &mut issues,
            "",
            1.0,
            24.0 * 60.0 * 60.0,
            false,
        );
    }
    validate_bool(
        &mut cfg,
        "operational_live_start_gate_enabled",
        &mut issues,
        "",
        true,
    );
    validate_bool(
        &mut cfg,
        "operational_live_order_gate_enabled",
        &mut issues,
        "",
        true,
    );
    validate_bool(
        &mut cfg,
        "connector_order_block_circuit_breaker_enabled",
        &mut issues,
        "",
        true,
    );
    validate_int_range(
        &mut cfg,
        "connector_order_block_pause_threshold",
        &mut issues,
        "",
        1,
        1_000_000,
    );

    for key in RISK_BOOL_KEYS {
        validate_bool(&mut cfg, key, &mut issues, "", false);
    }
    for &(key, min, max) in RISK_INT_RANGES {
        validate_int_range(&mut cfg, key, &mut issues, "", min, max);
    }
    for &(key, min, max) in RISK_FLOAT_RANGES {
        validate_float_range(&mut cfg, key, &mut issues, "", min, max, false);
    }

    validate_text(&mut cfg, "connector_backend", &mut issues, "", false);
    validate_text(&mut cfg, "indicator_source", &mut issues, "", false);
    validate_text(&mut cfg, "code_language", &mut issues, "", false);
    validate_text(&mut cfg, "theme", &mut issues, "", true);
    validate_text(&mut cfg, "design", &mut issues, "", true);
    validate_text(&mut cfg, "selected_rust_framework", &mut issues, "", true);
    validate_text(&mut cfg, "selected_exchange", &mut issues, "", false);
    validate_text(&mut cfg, "selected_forex_broker", &mut issues, "", true);
    validate_bool(&mut cfg, "llm_enabled", &mut issues, "", false);
    validate_choice(
        &mut cfg,
        "llm_provider",
        LLM_PROVIDER_CHOICES,
        &mut issues,
        "",
    );
    validate_text(&mut cfg, "llm_model", &mut issues, "", true);
    validate_text(&mut cfg, "llm_base_url", &mut issues, "", true);
    validate_text(&mut cfg, "llm_api_key", &mut issues, "", true);
    validate_text(&mut cfg, "llm_api_key_env", &mut issues, "", true);
    validate_choice(
        &mut cfg,
        "llm_use_for",
        LLM_USE_FOR_CHOICES,
        &mut issues,
        "",
    );
    validate_bool(&mut cfg, "llm_allow_public_network", &mut issues, "", false);
    validate_choice(
        &mut cfg,
        "llm_reasoning_effort",
        LLM_REASONING_EFFORT_CHOICES,
        &mut issues,
        "",
    );
    validate_stop_loss(&mut cfg, "stop_loss", &mut issues, "");
    validate_mapping(&cfg, "indicators", &mut issues, "");
    validate_chart_config(&mut cfg, &mut issues);
    validate_backtest_config(&mut cfg, &mut issues);

    issues
}

fn normalize_service_runtime_config(config: &Value) -> Value {
    let Some(object) = config.as_object() else {
        return config.clone();
    };
    let mut cfg = object.clone();
    normalize_symbol_list(&mut cfg, "symbols");
    normalize_interval_list(&mut cfg, "intervals");
    if let Some(interval) = cfg
        .get("loop_interval_override")
        .and_then(normalize_interval)
    {
        cfg.insert("loop_interval_override".to_owned(), Value::String(interval));
    }
    normalize_pair_list(&mut cfg, "runtime_symbol_interval_pairs");
    normalize_pair_list(&mut cfg, "backtest_symbol_interval_pairs");
    if let Some(value) = cfg.get("stop_loss").cloned() {
        cfg.insert("stop_loss".to_owned(), normalize_stop_loss_value(&value));
    }
    if let Some(Value::Object(chart)) = cfg.get_mut("chart") {
        normalize_symbol_list(chart, "symbol");
        if let Some(interval) = chart.get("interval").and_then(normalize_interval) {
            chart.insert("interval".to_owned(), Value::String(interval));
        }
    }
    if let Some(Value::Object(backtest)) = cfg.get_mut("backtest") {
        normalize_symbol_list(backtest, "symbols");
        normalize_interval_list(backtest, "intervals");
        if let Some(value) = backtest.get("stop_loss").cloned() {
            backtest.insert("stop_loss".to_owned(), normalize_stop_loss_value(&value));
        }
    }
    Value::Object(cfg)
}

pub fn is_service_config_secret_key(key: impl AsRef<str>) -> bool {
    let text = key.as_ref().trim().to_ascii_lowercase().replace('-', "_");
    if text.ends_with("_env") || text.ends_with("_env_var") {
        return false;
    }
    SECRET_KEY_TOKENS
        .iter()
        .map(|token| token.replace('-', "_"))
        .any(|token| text.contains(&token))
}

pub fn service_config_secret_field_paths(payload: &Value) -> Vec<String> {
    let mut paths = BTreeSet::new();
    collect_secret_field_paths(payload, "", &mut paths);
    paths.into_iter().collect()
}

pub fn service_config_secret_metadata(config: &Value) -> ServiceConfigSecretMetadata {
    let fields = if config.is_object() {
        service_config_secret_field_paths(config)
    } else {
        Vec::new()
    };
    ServiceConfigSecretMetadata {
        contains_secrets: !fields.is_empty(),
        secret_fields: fields,
        secret_storage: SERVICE_CONFIG_SECRET_STORAGE.to_owned(),
        secret_storage_warning: if config.is_object()
            && !service_config_secret_field_paths(config).is_empty()
        {
            SERVICE_CONFIG_SECRET_STORAGE_WARNING.to_owned()
        } else {
            String::new()
        },
    }
}

pub fn without_inline_service_config_secret_values(payload: &Value) -> Value {
    match payload {
        Value::Object(object) => {
            let mut out = Map::new();
            for (key, value) in object {
                if is_service_config_secret_key(key) && value_has_inline_secret(value) {
                    out.insert(key.clone(), Value::String(String::new()));
                } else {
                    out.insert(
                        key.clone(),
                        without_inline_service_config_secret_values(value),
                    );
                }
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(without_inline_service_config_secret_values)
                .collect(),
        ),
        _ => payload.clone(),
    }
}

pub fn build_service_config_persistence_payload(
    config: &Value,
    saved_at: impl AsRef<str>,
    allow_inline_secrets: bool,
) -> Value {
    let metadata = service_config_secret_metadata(config);
    let persisted_config = if metadata.contains_secrets && !allow_inline_secrets {
        without_inline_service_config_secret_values(config)
    } else {
        config.clone()
    };
    json!({
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
        "saved_at": saved_at.as_ref(),
        "config": persisted_config,
        "inline_secrets_persisted": metadata.contains_secrets && allow_inline_secrets,
        "contains_secrets": metadata.contains_secrets,
        "secret_fields": metadata.secret_fields,
        "secret_storage": metadata.secret_storage,
        "secret_storage_warning": metadata.secret_storage_warning,
    })
}

pub fn coerce_service_config_persistence_payload(
    raw_payload: &Value,
    path: impl AsRef<str>,
) -> Result<ServiceConfigLoadResult, String> {
    let raw = raw_payload.as_object().ok_or_else(|| {
        format!(
            "Service config file {} must contain a JSON object.",
            path.as_ref()
        )
    })?;

    let looks_like_envelope = raw.contains_key("config")
        && (raw
            .get("kind")
            .and_then(Value::as_str)
            .is_some_and(|kind| kind == SERVICE_CONFIG_FILE_KIND)
            || raw.contains_key("format_version")
            || raw.contains_key("saved_at"));

    if looks_like_envelope {
        let version = parse_format_version(raw.get("format_version"))?;
        if version > SERVICE_CONFIG_FORMAT_VERSION {
            return Err(format!(
                "Service config file {} uses unsupported format_version {}.",
                path.as_ref(),
                version
            ));
        }
        let config = raw.get("config").cloned().unwrap_or(Value::Null);
        if !config.is_object() {
            return Err(format!(
                "Service config file {} must contain a config object.",
                path.as_ref()
            ));
        }
        let config = validate_service_runtime_config(&config)?;
        return Ok(ServiceConfigLoadResult {
            config,
            metadata: ServiceConfigLoadMetadata {
                kind: raw
                    .get("kind")
                    .and_then(Value::as_str)
                    .unwrap_or(SERVICE_CONFIG_FILE_KIND)
                    .to_owned(),
                format_version: SERVICE_CONFIG_FORMAT_VERSION,
                migrated_from_format_version: (version < SERVICE_CONFIG_FORMAT_VERSION)
                    .then_some(version),
                saved_at: raw
                    .get("saved_at")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_owned(),
            },
        });
    }

    if !raw_payload.is_object() {
        return Err(format!(
            "Service config file {} must contain a config object.",
            path.as_ref()
        ));
    }
    let config = validate_service_runtime_config(raw_payload)?;
    Ok(ServiceConfigLoadResult {
        config,
        metadata: ServiceConfigLoadMetadata {
            kind: "legacy-config".to_owned(),
            format_version: SERVICE_CONFIG_FORMAT_VERSION,
            migrated_from_format_version: None,
            saved_at: String::new(),
        },
    })
}

pub fn resolve_service_config_path(path: Option<&Path>) -> PathBuf {
    let raw = path
        .filter(|value| !value.as_os_str().is_empty())
        .map(PathBuf::from)
        .or_else(|| env::var_os(SERVICE_CONFIG_ENV_PATH).map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from(DEFAULT_SERVICE_CONFIG_PATH));
    absolute_clean_path(&expand_user_path(&raw))
}

pub fn service_config_safe_root() -> PathBuf {
    resolve_service_config_path(Some(Path::new(DEFAULT_SERVICE_CONFIG_PATH)))
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn ensure_service_config_path_allowed(
    path: Option<&Path>,
    allow_unsafe_path: bool,
) -> Result<PathBuf, String> {
    let resolved = resolve_service_config_path(path);
    let env_allows = env::var(SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV)
        .map(|value| service_config_env_flag(value, false))
        .unwrap_or(false);
    if allow_unsafe_path
        || env_allows
        || path_is_relative_to(&resolved, &service_config_safe_root())
    {
        return Ok(resolved);
    }
    Err(format!(
        "Service config path {} is outside the safe config directory {}. Use allow_unsafe_path=true or set {}=1 only for trusted local paths.",
        resolved.display(),
        service_config_safe_root().display(),
        SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV
    ))
}

pub fn write_service_config_file(
    config: &Value,
    path: Option<&Path>,
    allow_unsafe_path: bool,
    allow_inline_secrets: bool,
    saved_at: impl AsRef<str>,
) -> Result<Value, String> {
    let resolved = ensure_service_config_path_allowed(path, allow_unsafe_path)?;
    let validated_config = validate_service_runtime_config(config)?;
    let payload = build_service_config_persistence_payload(
        &validated_config,
        saved_at.as_ref(),
        allow_inline_secrets,
    );
    if let Some(parent) = resolved.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let tmp_path = resolved.with_file_name(format!(
        ".{}.tmp",
        resolved
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("service-config.json")
    ));
    let mut text = serde_json::to_string_pretty(&payload).map_err(|err| err.to_string())?;
    text.push('\n');
    fs::write(&tmp_path, text).map_err(|err| err.to_string())?;
    if resolved.exists() {
        fs::remove_file(&resolved).map_err(|err| err.to_string())?;
    }
    fs::rename(&tmp_path, &resolved).map_err(|err| err.to_string())?;

    let metadata = service_config_secret_metadata(&validated_config);
    Ok(json!({
        "path": resolved.to_string_lossy(),
        "exists": true,
        "saved_at": payload.get("saved_at").and_then(Value::as_str).unwrap_or(""),
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
        "contains_secrets": metadata.contains_secrets,
        "secret_fields": metadata.secret_fields,
        "secret_storage": metadata.secret_storage,
        "secret_storage_warning": metadata.secret_storage_warning,
        "inline_secrets_persisted": payload.get("inline_secrets_persisted").and_then(Value::as_bool).unwrap_or(false),
    }))
}

pub fn load_service_config_file(path: Option<&Path>) -> Result<ServiceConfigLoadResult, String> {
    let resolved = resolve_service_config_path(path);
    let text = fs::read_to_string(&resolved)
        .map_err(|_| format!("Service config file not found: {}", resolved.display()))?;
    let raw: Value = serde_json::from_str(&text).map_err(|err| err.to_string())?;
    let mut result = coerce_service_config_persistence_payload(&raw, resolved.to_string_lossy())?;
    result.metadata.format_version = SERVICE_CONFIG_FORMAT_VERSION;
    Ok(result)
}

pub fn service_config_file_status(path: Option<&Path>) -> Value {
    let resolved = resolve_service_config_path(path);
    let mut payload = Map::new();
    payload.insert(
        "path".to_owned(),
        Value::String(resolved.to_string_lossy().to_string()),
    );
    payload.insert("exists".to_owned(), Value::Bool(resolved.is_file()));
    payload.insert(
        "modified_at".to_owned(),
        Value::String(modified_at_text(&resolved).unwrap_or_default()),
    );
    payload.insert(
        "kind".to_owned(),
        Value::String(SERVICE_CONFIG_FILE_KIND.to_owned()),
    );
    payload.insert(
        "format_version".to_owned(),
        Value::Number(SERVICE_CONFIG_FORMAT_VERSION.into()),
    );

    if resolved.is_file() {
        if let Ok(text) = fs::read_to_string(&resolved) {
            if let Ok(raw) = serde_json::from_str::<Value>(&text) {
                if let Some(object) = raw.as_object() {
                    insert_non_empty(
                        &mut payload,
                        "contains_secrets",
                        object
                            .get("contains_secrets")
                            .cloned()
                            .unwrap_or(Value::Bool(false)),
                    );
                    insert_non_empty(
                        &mut payload,
                        "secret_fields",
                        object
                            .get("secret_fields")
                            .cloned()
                            .unwrap_or_else(|| Value::Array(Vec::new())),
                    );
                    insert_non_empty(
                        &mut payload,
                        "secret_storage",
                        object
                            .get("secret_storage")
                            .cloned()
                            .unwrap_or_else(|| Value::String(String::new())),
                    );
                    insert_non_empty(
                        &mut payload,
                        "secret_storage_warning",
                        object
                            .get("secret_storage_warning")
                            .cloned()
                            .unwrap_or_else(|| Value::String(String::new())),
                    );
                }
            }
        }
    }

    Value::Object(payload)
}

pub fn build_service_config_persistence_status(
    file_status: &Value,
    runtime_state: &ServiceConfigRuntimeState,
) -> Value {
    let mut status = file_status.as_object().cloned().unwrap_or_default();
    status.insert(
        "loaded".to_owned(),
        Value::Bool(runtime_state.loaded || !runtime_state.last_loaded_at.is_empty()),
    );
    status.insert("dirty".to_owned(), Value::Bool(runtime_state.dirty));
    status.insert(
        "last_loaded_at".to_owned(),
        Value::String(runtime_state.last_loaded_at.clone()),
    );
    status.insert(
        "last_saved_at".to_owned(),
        Value::String(runtime_state.last_saved_at.clone()),
    );
    status.insert(
        "migrated_from_format_version".to_owned(),
        runtime_state
            .migrated_from_format_version
            .map(|value| Value::Number(value.into()))
            .unwrap_or(Value::Null),
    );
    Value::Object(status)
}

fn collect_secret_field_paths(payload: &Value, prefix: &str, paths: &mut BTreeSet<String>) {
    match payload {
        Value::Object(object) => {
            for (key, value) in object {
                let path = if prefix.is_empty() {
                    key.clone()
                } else {
                    format!("{prefix}.{key}")
                };
                if is_service_config_secret_key(key) && value_has_inline_secret(value) {
                    paths.insert(path);
                    continue;
                }
                collect_secret_field_paths(value, &path, paths);
            }
        }
        Value::Array(items) => {
            for (idx, value) in items.iter().enumerate() {
                collect_secret_field_paths(value, &format!("{prefix}[{idx}]"), paths);
            }
        }
        _ => {}
    }
}

fn value_has_inline_secret(value: &Value) -> bool {
    !value.is_null() && !matches!(value, Value::String(text) if text.is_empty())
}

fn parse_format_version(value: Option<&Value>) -> Result<i64, String> {
    match value {
        None | Some(Value::Null) => Ok(SERVICE_CONFIG_FORMAT_VERSION),
        Some(Value::Number(number)) => number
            .as_i64()
            .ok_or_else(|| "invalid format_version".to_owned()),
        Some(Value::String(text)) => text
            .trim()
            .parse::<i64>()
            .map_err(|_| "invalid format_version".to_owned()),
        Some(Value::Bool(value)) => Ok(i64::from(*value)),
        _ => Err("invalid format_version".to_owned()),
    }
}

fn expand_user_path(path: &Path) -> PathBuf {
    let text = path.to_string_lossy();
    if text == "~" {
        return home_dir().unwrap_or_else(|| PathBuf::from("~"));
    }
    if let Some(rest) = text.strip_prefix("~/").or_else(|| text.strip_prefix("~\\")) {
        if let Some(home) = home_dir() {
            return home.join(rest);
        }
    }
    path.to_path_buf()
}

fn home_dir() -> Option<PathBuf> {
    env::var_os("HOME")
        .filter(|value| !value.is_empty())
        .or_else(|| env::var_os("USERPROFILE").filter(|value| !value.is_empty()))
        .map(PathBuf::from)
}

fn absolute_clean_path(path: &Path) -> PathBuf {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    normalize_components(&absolute)
}

fn normalize_components(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                out.pop();
            }
            _ => out.push(component.as_os_str()),
        }
    }
    out
}

fn path_is_relative_to(child: &Path, parent: &Path) -> bool {
    let child_text = comparable_path(child);
    let mut parent_text = comparable_path(parent);
    if child_text == parent_text {
        return true;
    }
    if !parent_text.ends_with('/') {
        parent_text.push('/');
    }
    child_text.starts_with(&parent_text)
}

fn comparable_path(path: &Path) -> String {
    let text = absolute_clean_path(path)
        .to_string_lossy()
        .replace('\\', "/");
    if cfg!(windows) {
        text.to_ascii_lowercase()
    } else {
        text
    }
}

fn modified_at_text(path: &Path) -> Option<String> {
    let modified = fs::metadata(path).ok()?.modified().ok()?;
    let seconds = modified.duration_since(UNIX_EPOCH).ok()?.as_secs();
    Some(seconds.to_string())
}

fn insert_non_empty(payload: &mut Map<String, Value>, key: &str, value: Value) {
    match &value {
        Value::Null => return,
        Value::String(text) if text.is_empty() => return,
        Value::Array(items) if items.is_empty() => return,
        _ => {}
    }
    payload.insert(key.to_owned(), value);
}

const RUNTIME_ALLOWED_KEYS: &[&str] = &[
    "account_mode",
    "account_type",
    "add_only",
    "allow_close_ignoring_hold",
    "allow_indicator_close_without_signal",
    "allow_multi_indicator_close",
    "allow_opposite_positions",
    "api_key",
    "api_secret",
    "assets_mode",
    "auto_bump_percent_multiplier",
    "auto_flip_on_close",
    "backtest",
    "backtest_symbol_interval_pairs",
    "chart",
    "close_on_exit",
    "code_language",
    "connector_backend",
    "connector_order_block_circuit_breaker_enabled",
    "connector_order_block_pause_threshold",
    "connector_order_block_window_seconds",
    "connector_order_circuit_incident_log_backup_count",
    "connector_order_circuit_incident_log_max_bytes",
    "connector_order_circuit_incident_log_path",
    "design",
    "futures_flat_purge_grace_seconds",
    "futures_flat_purge_miss_threshold",
    "gtd_minutes",
    "hedge_preserve_opposites",
    "indicator_flip_confirmation_bars",
    "indicator_flip_cooldown_bars",
    "indicator_flip_cooldown_seconds",
    "indicator_min_position_hold_bars",
    "indicator_min_position_hold_seconds",
    "indicator_reentry_cooldown_bars",
    "indicator_reentry_cooldown_seconds",
    "indicator_reentry_requires_signal_reset",
    "indicator_source",
    "indicator_use_live_values",
    "indicators",
    "intervals",
    "lead_trader_enabled",
    "lead_trader_profile",
    "leverage",
    "live_trading_acknowledgement",
    "live_trading_enabled",
    "live_allow_auto_bump_to_min_order",
    "live_trading_max_leverage",
    "live_trading_max_position_pct",
    "live_trading_max_session_orders",
    "llm_allow_public_network",
    "llm_api_key",
    "llm_api_key_env",
    "llm_base_url",
    "llm_enabled",
    "llm_model",
    "llm_provider",
    "llm_reasoning_effort",
    "llm_use_for",
    "lookback",
    "loop_interval_override",
    "margin_mode",
    "max_auto_bump_percent",
    "mode",
    "operational_account_snapshot_stale_seconds",
    "operational_connector_snapshot_stale_seconds",
    "operational_execution_heartbeat_stale_seconds",
    "operational_live_order_gate_enabled",
    "operational_live_start_gate_enabled",
    "operational_portfolio_snapshot_stale_seconds",
    "order_audit_backup_count",
    "order_audit_enabled",
    "order_audit_log_path",
    "order_audit_max_bytes",
    "order_type",
    "position_mode",
    "position_pct",
    "positions_missing_autoclose",
    "positions_auto_resize_columns",
    "positions_auto_resize_rows",
    "positions_missing_grace_seconds",
    "positions_missing_threshold",
    "require_indicator_flip_signal",
    "runtime_symbol_interval_pairs",
    "selected_exchange",
    "selected_forex_broker",
    "selected_rust_framework",
    "side",
    "stop_loss",
    "strict_indicator_flip_enforcement",
    "symbols",
    "theme",
    "tif",
];
const CHART_ALLOWED_KEYS: &[&str] = &["auto_follow", "interval", "market", "symbol", "view_mode"];
const BACKTEST_ALLOWED_KEYS: &[&str] = &[
    "account_mode",
    "assets_mode",
    "capital",
    "connector_backend",
    "end_date",
    "execution_backend",
    "indicators",
    "intervals",
    "leverage",
    "logic",
    "margin_mode",
    "mdd_logic",
    "position_mode",
    "position_pct",
    "optimizer_combo_size",
    "optimizer_metric",
    "optimizer_min_trades",
    "optimizer_mode",
    "scan_auto_apply",
    "scan_mdd_limit",
    "scan_scope",
    "scan_top_n",
    "side",
    "start_date",
    "stop_loss",
    "symbol_source",
    "symbols",
    "template",
];
const ACCOUNT_TYPE_CHOICES: &[(&str, &str)] = &[("spot", "Spot"), ("futures", "Futures")];
const MARGIN_MODE_CHOICES: &[(&str, &str)] = &[("isolated", "Isolated"), ("cross", "Cross")];
const POSITION_MODE_CHOICES: &[(&str, &str)] = &[
    ("hedge", "Hedge"),
    ("one-way", "One-way"),
    ("oneway", "One-way"),
];
const ASSETS_MODE_CHOICES: &[(&str, &str)] = &[
    ("single-asset", "Single-Asset"),
    ("single-asset mode", "Single-Asset"),
    ("multi-assets", "Multi-Assets"),
    ("multi-asset", "Multi-Assets"),
    ("multi-assets mode", "Multi-Assets"),
];
const ACCOUNT_MODE_CHOICES: &[(&str, &str)] = &[
    ("classic trading", "Classic Trading"),
    ("portfolio margin", "Portfolio Margin"),
];
const SIDE_CHOICES: &[(&str, &str)] = &[("both", "BOTH"), ("buy", "BUY"), ("sell", "SELL")];
const ORDER_TYPE_CHOICES: &[(&str, &str)] = &[("market", "MARKET"), ("limit", "LIMIT")];
const TIF_CHOICES: &[(&str, &str)] = &[
    ("gtc", "GTC"),
    ("ioc", "IOC"),
    ("fok", "FOK"),
    ("gtd", "GTD"),
];
const LOGIC_CHOICES: &[(&str, &str)] = &[("and", "AND"), ("or", "OR"), ("separate", "SEPARATE")];
const SCAN_SCOPE_CHOICES: &[(&str, &str)] = &[
    ("selected", "selected"),
    ("top_n", "top_n"),
    ("top-n", "top_n"),
    ("all_loaded", "all_loaded"),
    ("all-loaded", "all_loaded"),
];
const OPTIMIZER_MODE_CHOICES: &[(&str, &str)] = &[
    ("current", "current"),
    ("single", "single"),
    ("pairs", "pairs"),
    ("combinations", "combinations"),
];
const OPTIMIZER_METRIC_CHOICES: &[(&str, &str)] = &[
    ("roi_percent", "roi_percent"),
    ("roi-percent", "roi_percent"),
    ("roi_percent_mdd", "roi_percent_mdd"),
    ("roi-percent-mdd", "roi_percent_mdd"),
    ("roi_drawdown", "roi_drawdown"),
    ("roi-drawdown", "roi_drawdown"),
    ("roi_value", "roi_value"),
    ("roi-value", "roi_value"),
];
const BACKTEST_EXECUTION_BACKEND_CHOICES: &[(&str, &str)] = &[
    ("desktop", "local"),
    ("desktop-local", "local"),
    ("local", "local"),
    ("remote", "service"),
    ("service", "service"),
    ("service-api", "service"),
];
const CHART_VIEW_MODE_CHOICES: &[(&str, &str)] = &[
    ("tradingview", "tradingview"),
    ("original", "original"),
    ("lightweight", "lightweight"),
    ("tradingview lightweight", "lightweight"),
];
const LLM_PROVIDER_CHOICES: &[(&str, &str)] = &[
    ("alibaba", "qwen"),
    ("alibaba-qwen", "qwen"),
    ("anthropic", "anthropic"),
    ("anthropic-claude", "anthropic"),
    ("chatgpt", "openai"),
    ("claude", "anthropic"),
    ("custom", "local"),
    ("dashscope", "qwen"),
    ("deepseek", "deepseek"),
    ("gemini", "gemini"),
    ("google", "gemini"),
    ("google-gemini", "gemini"),
    ("grok", "grok"),
    ("local", "local"),
    ("local-openai", "local"),
    ("local-openai-compatible", "local"),
    ("ollama", "local"),
    ("openai", "openai"),
    ("openai-chatgpt", "openai"),
    ("qwen", "qwen"),
    ("xai", "grok"),
    ("xai-grok", "grok"),
];
const LLM_USE_FOR_CHOICES: &[(&str, &str)] = &[
    ("advisory", "advisory"),
    ("backtest_explanation", "backtest_explanation"),
    ("risk_review", "risk_review"),
    ("signal_confirmation", "signal_confirmation"),
];
const LLM_REASONING_EFFORT_CHOICES: &[(&str, &str)] = &[
    ("default", "default"),
    ("disabled", "disabled"),
    ("enabled", "enabled"),
    ("extra-high", "xhigh"),
    ("extra_high", "xhigh"),
    ("high", "high"),
    ("low", "low"),
    ("max", "max"),
    ("medium", "medium"),
    ("minimal", "minimal"),
    ("none", "none"),
    ("xhigh", "xhigh"),
];
const MDD_LOGIC_CHOICES: &[(&str, &str)] = &[
    ("per_trade", "per_trade"),
    ("cumulative", "cumulative"),
    ("entire_account", "entire_account"),
];
const RISK_BOOL_KEYS: &[&str] = &[
    "add_only",
    "indicator_use_live_values",
    "require_indicator_flip_signal",
    "strict_indicator_flip_enforcement",
    "indicator_reentry_requires_signal_reset",
    "auto_flip_on_close",
    "allow_close_ignoring_hold",
    "allow_multi_indicator_close",
    "allow_indicator_close_without_signal",
    "close_on_exit",
    "positions_missing_autoclose",
    "allow_opposite_positions",
    "hedge_preserve_opposites",
];
const RISK_INT_RANGES: &[(&str, i64, i64)] = &[
    ("indicator_flip_cooldown_bars", 0, 1_000_000),
    ("indicator_min_position_hold_bars", 0, 1_000_000),
    ("indicator_reentry_cooldown_bars", 0, 1_000_000),
    ("indicator_flip_confirmation_bars", 1, 1_000_000),
    ("positions_missing_threshold", 1, 1_000_000),
    ("futures_flat_purge_miss_threshold", 1, 1_000_000),
];
const RISK_FLOAT_RANGES: &[(&str, f64, f64)] = &[
    (
        "indicator_flip_cooldown_seconds",
        0.0,
        365.0 * 24.0 * 60.0 * 60.0,
    ),
    (
        "indicator_min_position_hold_seconds",
        0.0,
        365.0 * 24.0 * 60.0 * 60.0,
    ),
    (
        "indicator_reentry_cooldown_seconds",
        0.0,
        365.0 * 24.0 * 60.0 * 60.0,
    ),
    (
        "positions_missing_grace_seconds",
        0.0,
        365.0 * 24.0 * 60.0 * 60.0,
    ),
    (
        "futures_flat_purge_grace_seconds",
        0.0,
        365.0 * 24.0 * 60.0 * 60.0,
    ),
    ("max_auto_bump_percent", 0.0, 100.0),
    ("auto_bump_percent_multiplier", 0.0, 1_000.0),
];

fn field(prefix: &str, key: &str) -> String {
    if prefix.is_empty() {
        key.to_owned()
    } else {
        format!("{prefix}.{key}")
    }
}

fn validate_allowed_keys(
    cfg: &Map<String, Value>,
    allowed: &[&str],
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    for key in cfg.keys() {
        if !allowed.contains(&key.as_str()) {
            issues.push(ServiceConfigValidationIssue::new(
                field(prefix, key),
                "is not a supported config key",
            ));
        }
    }
}

fn value_to_text(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(text) => text.clone(),
        Value::Bool(value) => value.to_string(),
        Value::Number(value) => value.to_string(),
        Value::Array(_) | Value::Object(_) => serde_json::to_string(value).unwrap_or_default(),
    }
}

fn has_control_text(text: &str) -> bool {
    text.chars()
        .any(|ch| matches!(ch, '\u{0000}'..='\u{001f}' | '\u{007f}'))
}

fn text_value(value: &Value, allow_empty: bool) -> Option<String> {
    let text = value_to_text(value).trim().to_owned();
    if (!allow_empty && text.is_empty()) || has_control_text(&text) {
        None
    } else {
        Some(text)
    }
}

fn finite_float(value: &Value) -> Option<f64> {
    if matches!(value, Value::Bool(_)) {
        return None;
    }
    let number = match value {
        Value::Number(number) => number.as_f64()?,
        Value::String(text) => text.trim().parse::<f64>().ok()?,
        _ => value_to_text(value).trim().parse::<f64>().ok()?,
    };
    number.is_finite().then_some(number)
}

fn validate_text(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    allow_empty: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    let raw_text = value_to_text(value).trim().to_owned();
    if raw_text.is_empty() && !allow_empty {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a non-empty text value",
        ));
        return;
    }
    if has_control_text(&raw_text) {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            if allow_empty {
                "must be text without control characters"
            } else {
                "must be a non-empty text value"
            },
        ));
        return;
    }
    cfg.insert(key.to_owned(), Value::String(raw_text));
}

fn validate_nullable_text(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    allow_empty: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if value.is_null() {
        return;
    }
    let text = value_to_text(value).trim().to_owned();
    if text.is_empty() && !allow_empty {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a non-empty text value",
        ));
    } else if has_control_text(&text) {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be text without control characters",
        ));
    } else {
        cfg.insert(key.to_owned(), Value::String(text));
    }
}

fn choice_value(value: &Value, choices: &[(&str, &str)]) -> Option<String> {
    let text = text_value(value, false)?;
    let key = text.trim().to_ascii_lowercase();
    choices
        .iter()
        .find_map(|(raw, normalized)| (*raw == key).then(|| (*normalized).to_owned()))
}

fn allowed_choice_text(choices: &[(&str, &str)]) -> String {
    choices
        .iter()
        .map(|(_, value)| *value)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>()
        .join(", ")
}

fn validate_choice(
    cfg: &mut Map<String, Value>,
    key: &str,
    choices: &[(&str, &str)],
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if let Some(normalized) = choice_value(value, choices) {
        cfg.insert(key.to_owned(), Value::String(normalized));
    } else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            format!("must be one of: {}", allowed_choice_text(choices)),
        ));
    }
}

fn validate_int_range(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    min: i64,
    max: i64,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    let Some(number) = finite_float(value) else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be an integer",
        ));
        return;
    };
    if number.fract() != 0.0 {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be an integer",
        ));
        return;
    }
    let integer = number as i64;
    if integer < min || integer > max {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            format!("must be between {min} and {max}"),
        ));
    } else {
        cfg.insert(key.to_owned(), Value::Number(integer.into()));
    }
}

fn validate_float_range(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    min: f64,
    max: f64,
    exclusive_min: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    let Some(number) = finite_float(value) else {
        issues.push(float_range_issue(prefix, key, min, max, exclusive_min));
        return;
    };
    let min_ok = if exclusive_min {
        number > min
    } else {
        number >= min
    };
    if !min_ok || number > max {
        issues.push(float_range_issue(prefix, key, min, max, exclusive_min));
    } else if let Some(json_number) = serde_json::Number::from_f64(number) {
        cfg.insert(key.to_owned(), Value::Number(json_number));
    }
}

fn float_range_issue(
    prefix: &str,
    key: &str,
    min: f64,
    max: f64,
    exclusive_min: bool,
) -> ServiceConfigValidationIssue {
    ServiceConfigValidationIssue::new(
        field(prefix, key),
        format!(
            "must be {} {} and <= {}",
            if exclusive_min { ">" } else { ">=" },
            format_amount(min),
            format_amount(max)
        ),
    )
}

fn coerce_bool(value: &Value, default_value: bool) -> Option<bool> {
    match value {
        Value::Bool(value) => Some(*value),
        Value::Null => Some(default_value),
        Value::String(text) => match text.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Some(true),
            "0" | "false" | "no" | "off" => Some(false),
            "" | "none" | "null" => Some(default_value),
            _ => None,
        },
        Value::Number(number) => match number.as_i64() {
            Some(0) => Some(false),
            Some(1) => Some(true),
            _ => None,
        },
        _ => None,
    }
}

fn validate_bool(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    default_value: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if let Some(value) = coerce_bool(value, default_value) {
        cfg.insert(key.to_owned(), Value::Bool(value));
    } else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a boolean",
        ));
    }
}

fn normalize_interval(value: &Value) -> Option<String> {
    let raw = value_to_text(value);
    let text = raw.trim();
    if text.is_empty() {
        return None;
    }
    let mut chars = text.chars().peekable();
    let mut number = String::new();
    while let Some(ch) = chars.peek().copied() {
        if ch.is_ascii_digit() || ch == '.' {
            number.push(ch);
            chars.next();
        } else {
            break;
        }
    }
    while matches!(chars.peek(), Some(ch) if ch.is_whitespace()) {
        chars.next();
    }
    let suffix: String = chars.collect();
    if number.is_empty() || suffix.chars().any(|ch| !ch.is_ascii_alphabetic()) {
        return None;
    }
    let amount = number.parse::<f64>().ok()?;
    if !amount.is_finite() || amount <= 0.0 {
        return None;
    }
    let lower = suffix.trim().to_ascii_lowercase();
    let unit = if suffix.trim() == "M"
        || matches!(lower.as_str(), "mo" | "mon" | "mons" | "month" | "months")
    {
        "mo"
    } else if matches!(
        lower.as_str(),
        "" | "m" | "min" | "mins" | "minute" | "minutes"
    ) {
        "m"
    } else if matches!(lower.as_str(), "s" | "sec" | "secs" | "second" | "seconds") {
        "s"
    } else if matches!(lower.as_str(), "h" | "hr" | "hrs" | "hour" | "hours") {
        "h"
    } else if matches!(lower.as_str(), "d" | "day" | "days") {
        "d"
    } else if matches!(lower.as_str(), "w" | "wk" | "wks" | "week" | "weeks") {
        "w"
    } else if matches!(lower.as_str(), "y" | "yr" | "yrs" | "year" | "years") {
        "y"
    } else {
        return None;
    };
    Some(format!("{}{}", format_amount(amount), unit))
}

fn format_amount(value: f64) -> String {
    if value.fract() == 0.0 {
        (value as i64).to_string()
    } else {
        let mut text = format!("{value}");
        while text.contains('.') && text.ends_with('0') {
            text.pop();
        }
        if text.ends_with('.') {
            text.pop();
        }
        text
    }
}

fn validate_symbol_list(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    require_non_empty: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    let values = if let Some(text) = value.as_str() {
        vec![Value::String(text.to_owned())]
    } else if let Some(items) = value.as_array() {
        items.clone()
    } else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a list of symbols",
        ));
        return;
    };
    let mut seen = BTreeSet::new();
    let mut symbols = Vec::new();
    for item in values {
        let Some(symbol) = text_value(&item, false).map(|value| value.to_ascii_uppercase()) else {
            issues.push(ServiceConfigValidationIssue::new(
                field(prefix, key),
                "contains an invalid symbol",
            ));
            continue;
        };
        if symbol.chars().any(char::is_whitespace) {
            issues.push(ServiceConfigValidationIssue::new(
                field(prefix, key),
                "contains an invalid symbol",
            ));
            continue;
        }
        if seen.insert(symbol.clone()) {
            symbols.push(Value::String(symbol));
        }
    }
    if require_non_empty && symbols.is_empty() {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must contain at least one symbol",
        ));
    } else {
        cfg.insert(key.to_owned(), Value::Array(symbols));
    }
}

fn validate_interval_list(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
    require_non_empty: bool,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    let values = if let Some(text) = value.as_str() {
        vec![Value::String(text.to_owned())]
    } else if let Some(items) = value.as_array() {
        items.clone()
    } else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a list of intervals",
        ));
        return;
    };
    let mut seen = BTreeSet::new();
    let mut intervals = Vec::new();
    for item in values {
        let Some(interval) = normalize_interval(&item) else {
            issues.push(ServiceConfigValidationIssue::new(
                field(prefix, key),
                "contains an invalid interval",
            ));
            continue;
        };
        if seen.insert(interval.clone()) {
            intervals.push(Value::String(interval));
        }
    }
    if require_non_empty && intervals.is_empty() {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must contain at least one interval",
        ));
    } else {
        cfg.insert(key.to_owned(), Value::Array(intervals));
    }
}

fn validate_stop_loss(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if !value.is_null() && !value.is_object() {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be an object",
        ));
    }
}

fn normalize_stop_loss_value(value: &Value) -> Value {
    let raw = value.as_object().cloned().unwrap_or_default();
    let mode = match raw
        .get("mode")
        .map(value_to_text)
        .unwrap_or_else(|| "usdt".to_owned())
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "percent" => "percent",
        "both" => "both",
        _ => "usdt",
    };
    let scope = match raw
        .get("scope")
        .map(value_to_text)
        .unwrap_or_else(|| "per_trade".to_owned())
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "cumulative" => "cumulative",
        "entire_account" => "entire_account",
        _ => "per_trade",
    };
    let usdt = raw
        .get("usdt")
        .and_then(finite_float)
        .unwrap_or(0.0)
        .max(0.0);
    let percent = raw
        .get("percent")
        .and_then(finite_float)
        .unwrap_or(0.0)
        .max(0.0);
    json!({
        "enabled": raw.get("enabled").and_then(|value| coerce_bool(value, false)).unwrap_or(false),
        "mode": mode,
        "usdt": usdt,
        "percent": percent,
        "scope": scope,
    })
}

fn validate_pair_list(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if value.is_null() || matches!(value, Value::String(text) if text.trim().is_empty()) {
        return;
    }
    let Some(entries) = value.as_array() else {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            "must be a list of symbol/interval objects",
        ));
        return;
    };
    for (index, entry) in entries.iter().enumerate() {
        let entry_field = format!("{}[{index}]", field(prefix, key));
        let Some(entry_object) = entry.as_object() else {
            issues.push(ServiceConfigValidationIssue::new(
                entry_field,
                "must be an object",
            ));
            continue;
        };
        let symbol = entry_object
            .get("symbol")
            .and_then(|value| text_value(value, false))
            .map(|value| value.to_ascii_uppercase());
        if symbol
            .as_ref()
            .is_none_or(|value| value.chars().any(char::is_whitespace))
        {
            issues.push(ServiceConfigValidationIssue::new(
                format!("{entry_field}.symbol"),
                "must be a non-empty symbol",
            ));
            continue;
        }
        if entry_object
            .get("interval")
            .and_then(normalize_interval)
            .is_none()
        {
            issues.push(ServiceConfigValidationIssue::new(
                format!("{entry_field}.interval"),
                "must be a valid interval",
            ));
            continue;
        }
        if let Some(controls) = entry_object.get("strategy_controls") {
            if let Some(control_object) = controls.as_object() {
                let mut controls_copy = control_object.clone();
                validate_choice(
                    &mut controls_copy,
                    "side",
                    SIDE_CHOICES,
                    issues,
                    &format!("{entry_field}.strategy_controls"),
                );
                validate_int_range(
                    &mut controls_copy,
                    "leverage",
                    issues,
                    &format!("{entry_field}.strategy_controls"),
                    1,
                    125,
                );
                if let Some(loop_value) = controls_copy.get("loop_interval_override") {
                    if !value_to_text(loop_value).trim().is_empty()
                        && normalize_interval(loop_value).is_none()
                    {
                        issues.push(ServiceConfigValidationIssue::new(
                            format!("{entry_field}.strategy_controls.loop_interval_override"),
                            "must be a valid interval",
                        ));
                    }
                }
                validate_stop_loss(
                    &mut controls_copy,
                    "stop_loss",
                    issues,
                    &format!("{entry_field}.strategy_controls"),
                );
            } else if !controls.is_null() {
                issues.push(ServiceConfigValidationIssue::new(
                    format!("{entry_field}.strategy_controls"),
                    "must be an object",
                ));
            }
        }
    }
}

fn validate_mapping(
    cfg: &Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    if let Some(value) = cfg.get(key) {
        if !value.is_object() {
            issues.push(ServiceConfigValidationIssue::new(
                field(prefix, key),
                "must be an object",
            ));
        }
    }
}

fn validate_chart_config(
    cfg: &mut Map<String, Value>,
    issues: &mut Vec<ServiceConfigValidationIssue>,
) {
    let Some(value) = cfg.get("chart") else {
        return;
    };
    let Some(chart_object) = value.as_object() else {
        issues.push(ServiceConfigValidationIssue::new(
            "chart",
            "must be an object",
        ));
        return;
    };
    let mut chart = chart_object.clone();
    validate_allowed_keys(&chart, CHART_ALLOWED_KEYS, issues, "chart");
    validate_choice(&mut chart, "market", ACCOUNT_TYPE_CHOICES, issues, "chart");
    validate_choice(
        &mut chart,
        "view_mode",
        CHART_VIEW_MODE_CHOICES,
        issues,
        "chart",
    );
    validate_bool(&mut chart, "auto_follow", issues, "chart", true);
    if let Some(symbol) = chart.get("symbol") {
        let valid = text_value(symbol, false)
            .map(|value| !value.chars().any(char::is_whitespace))
            .unwrap_or(false);
        if !valid {
            issues.push(ServiceConfigValidationIssue::new(
                "chart.symbol",
                "must be a non-empty symbol",
            ));
        }
    }
    if let Some(interval) = chart.get("interval") {
        if normalize_interval(interval).is_none() {
            issues.push(ServiceConfigValidationIssue::new(
                "chart.interval",
                "must be a valid interval",
            ));
        }
    }
}

fn validate_backtest_config(
    cfg: &mut Map<String, Value>,
    issues: &mut Vec<ServiceConfigValidationIssue>,
) {
    let Some(value) = cfg.get("backtest") else {
        return;
    };
    let Some(backtest_object) = value.as_object() else {
        issues.push(ServiceConfigValidationIssue::new(
            "backtest",
            "must be an object",
        ));
        return;
    };
    let mut backtest = backtest_object.clone();
    validate_allowed_keys(&backtest, BACKTEST_ALLOWED_KEYS, issues, "backtest");
    validate_symbol_list(&mut backtest, "symbols", issues, "backtest", true);
    validate_interval_list(&mut backtest, "intervals", issues, "backtest", true);
    validate_float_range(
        &mut backtest,
        "capital",
        issues,
        "backtest",
        0.0,
        1_000_000_000_000.0,
        true,
    );
    validate_choice(
        &mut backtest,
        "execution_backend",
        BACKTEST_EXECUTION_BACKEND_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(&mut backtest, "logic", LOGIC_CHOICES, issues, "backtest");
    validate_text(&mut backtest, "symbol_source", issues, "backtest", false);
    validate_datetime_text(&mut backtest, "start_date", issues, "backtest");
    validate_datetime_text(&mut backtest, "end_date", issues, "backtest");
    validate_float_range(
        &mut backtest,
        "position_pct",
        issues,
        "backtest",
        0.0,
        100.0,
        true,
    );
    validate_choice(&mut backtest, "side", SIDE_CHOICES, issues, "backtest");
    validate_choice(
        &mut backtest,
        "margin_mode",
        MARGIN_MODE_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(
        &mut backtest,
        "position_mode",
        POSITION_MODE_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(
        &mut backtest,
        "assets_mode",
        ASSETS_MODE_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(
        &mut backtest,
        "account_mode",
        ACCOUNT_MODE_CHOICES,
        issues,
        "backtest",
    );
    validate_text(
        &mut backtest,
        "connector_backend",
        issues,
        "backtest",
        false,
    );
    validate_int_range(&mut backtest, "leverage", issues, "backtest", 1, 125);
    validate_choice(
        &mut backtest,
        "mdd_logic",
        MDD_LOGIC_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(
        &mut backtest,
        "scan_scope",
        SCAN_SCOPE_CHOICES,
        issues,
        "backtest",
    );
    validate_int_range(&mut backtest, "scan_top_n", issues, "backtest", 1, 10_000);
    validate_float_range(
        &mut backtest,
        "scan_mdd_limit",
        issues,
        "backtest",
        0.0,
        100.0,
        false,
    );
    validate_bool(&mut backtest, "scan_auto_apply", issues, "backtest", false);
    validate_choice(
        &mut backtest,
        "optimizer_mode",
        OPTIMIZER_MODE_CHOICES,
        issues,
        "backtest",
    );
    validate_choice(
        &mut backtest,
        "optimizer_metric",
        OPTIMIZER_METRIC_CHOICES,
        issues,
        "backtest",
    );
    validate_int_range(
        &mut backtest,
        "optimizer_combo_size",
        issues,
        "backtest",
        1,
        5,
    );
    validate_int_range(
        &mut backtest,
        "optimizer_min_trades",
        issues,
        "backtest",
        0,
        1_000_000,
    );
    validate_mapping(&backtest, "template", issues, "backtest");
    validate_mapping(&backtest, "indicators", issues, "backtest");
    validate_stop_loss(&mut backtest, "stop_loss", issues, "backtest");
}

fn validate_datetime_text(
    cfg: &mut Map<String, Value>,
    key: &str,
    issues: &mut Vec<ServiceConfigValidationIssue>,
    prefix: &str,
) {
    let Some(value) = cfg.get(key) else {
        return;
    };
    if value.is_null() {
        return;
    }
    let text = value_to_text(value).trim().to_owned();
    if text.is_empty() {
        return;
    }
    if has_control_text(&text) || !looks_like_datetime(&text) {
        issues.push(ServiceConfigValidationIssue::new(
            field(prefix, key),
            if has_control_text(&text) {
                "must be text without control characters"
            } else {
                "must be an ISO date or datetime"
            },
        ));
    }
}

fn looks_like_datetime(text: &str) -> bool {
    let bytes = text.as_bytes();
    bytes.len() >= 10
        && bytes[0..4].iter().all(u8::is_ascii_digit)
        && bytes[4] == b'-'
        && bytes[5..7].iter().all(u8::is_ascii_digit)
        && bytes[7] == b'-'
        && bytes[8..10].iter().all(u8::is_ascii_digit)
}

fn normalize_symbol_list(cfg: &mut Map<String, Value>, key: &str) {
    let Some(value) = cfg.get(key).cloned() else {
        return;
    };
    if let Some(text) = value.as_str() {
        cfg.insert(
            key.to_owned(),
            Value::String(text.trim().to_ascii_uppercase()),
        );
    } else if let Some(items) = value.as_array() {
        let mut seen = BTreeSet::new();
        let values = items
            .iter()
            .filter_map(|item| text_value(item, false))
            .map(|item| item.to_ascii_uppercase())
            .filter(|item| seen.insert(item.clone()))
            .map(Value::String)
            .collect();
        cfg.insert(key.to_owned(), Value::Array(values));
    }
}

fn normalize_interval_list(cfg: &mut Map<String, Value>, key: &str) {
    let Some(value) = cfg.get(key).cloned() else {
        return;
    };
    if let Some(text) = value.as_str() {
        if let Some(interval) = normalize_interval(&Value::String(text.to_owned())) {
            cfg.insert(key.to_owned(), Value::Array(vec![Value::String(interval)]));
        }
    } else if let Some(items) = value.as_array() {
        let mut seen = BTreeSet::new();
        let values = items
            .iter()
            .filter_map(normalize_interval)
            .filter(|item| seen.insert(item.clone()))
            .map(Value::String)
            .collect();
        cfg.insert(key.to_owned(), Value::Array(values));
    }
}

fn normalize_pair_list(cfg: &mut Map<String, Value>, key: &str) {
    let Some(Value::Array(entries)) = cfg.get(key).cloned() else {
        return;
    };
    let mut out = Vec::new();
    for entry in entries {
        let Some(mut object) = entry.as_object().cloned() else {
            continue;
        };
        if let Some(symbol) = object
            .get("symbol")
            .and_then(|value| text_value(value, false))
        {
            object.insert(
                "symbol".to_owned(),
                Value::String(symbol.to_ascii_uppercase()),
            );
        }
        if let Some(interval) = object.get("interval").and_then(normalize_interval) {
            object.insert("interval".to_owned(), Value::String(interval));
        }
        if let Some(Value::Object(controls)) = object.get_mut("strategy_controls") {
            if let Some(interval) = controls
                .get("loop_interval_override")
                .and_then(normalize_interval)
            {
                controls.insert("loop_interval_override".to_owned(), Value::String(interval));
            }
            if let Some(value) = controls.get("stop_loss").cloned() {
                controls.insert("stop_loss".to_owned(), normalize_stop_loss_value(&value));
            }
        }
        out.push(Value::Object(object));
    }
    cfg.insert(key.to_owned(), Value::Array(out));
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::SystemTime;

    #[test]
    fn secret_metadata_and_payload_redact_inline_values_like_python() {
        let config = json!({
            "api_key": "exchange-key",
            "api_secret": "exchange-secret",
            "api_key_env": "BINANCE_API_KEY",
            "llm": {
                "llm_api_key": "llm-secret",
                "token_env_var": "TOKEN_ENV"
            },
            "providers": [
                {"authorization": "bearer-token"},
                {"password": ""}
            ]
        });

        let metadata = service_config_secret_metadata(&config);
        assert!(metadata.contains_secrets);
        assert_eq!(
            metadata.secret_fields,
            vec![
                "api_key".to_owned(),
                "api_secret".to_owned(),
                "llm.llm_api_key".to_owned(),
                "providers[0].authorization".to_owned(),
            ]
        );
        assert_eq!(metadata.secret_storage, "plain-json-on-disk");
        assert!(metadata.secret_storage_warning.contains("plain JSON"));

        let payload =
            build_service_config_persistence_payload(&config, "2026-06-18T12:00:00+00:00", false);
        assert_eq!(payload["kind"], SERVICE_CONFIG_FILE_KIND);
        assert_eq!(payload["format_version"], SERVICE_CONFIG_FORMAT_VERSION);
        assert_eq!(payload["inline_secrets_persisted"], false);
        assert_eq!(payload["config"]["api_key"], "");
        assert_eq!(payload["config"]["api_secret"], "");
        assert_eq!(payload["config"]["llm"]["llm_api_key"], "");
        assert_eq!(payload["config"]["providers"][0]["authorization"], "");
        assert_eq!(payload["config"]["api_key_env"], "BINANCE_API_KEY");
    }

    #[test]
    fn config_persistence_payload_can_explicitly_allow_inline_secrets() {
        let config = json!({"api_key": "exchange-key", "api_secret": "exchange-secret"});
        let payload =
            build_service_config_persistence_payload(&config, "2026-06-18T12:00:00+00:00", true);

        assert_eq!(payload["inline_secrets_persisted"], true);
        assert_eq!(payload["config"]["api_key"], "exchange-key");
        assert_eq!(payload["config"]["api_secret"], "exchange-secret");
        assert_eq!(
            payload["secret_storage_warning"],
            SERVICE_CONFIG_SECRET_STORAGE_WARNING
        );
    }

    #[test]
    fn coerce_service_config_payload_migrates_old_versions_and_rejects_future() {
        let old = json!({
            "kind": SERVICE_CONFIG_FILE_KIND,
            "format_version": 0,
            "saved_at": "2026-06-18T12:00:00+00:00",
            "config": {"symbols": ["ETHUSDT"]}
        });
        let result = coerce_service_config_persistence_payload(&old, "service-config.json")
            .expect("old version should migrate");
        assert_eq!(
            result.metadata.format_version,
            SERVICE_CONFIG_FORMAT_VERSION
        );
        assert_eq!(result.metadata.migrated_from_format_version, Some(0));
        assert_eq!(result.config["symbols"][0], "ETHUSDT");

        let future = json!({
            "kind": SERVICE_CONFIG_FILE_KIND,
            "format_version": 999,
            "config": {"symbols": ["ETHUSDT"]}
        });
        let error = coerce_service_config_persistence_payload(&future, "service-config.json")
            .expect_err("future format should be rejected");
        assert!(error.contains("unsupported format_version"));
    }

    #[test]
    fn write_load_and_status_follow_python_persistence_shape() {
        let dir = unique_temp_dir("config-persistence");
        let path = dir.join("service-config.json");
        let config = json!({"symbols": ["ETHUSDT"], "api_key": "exchange-key"});

        let saved = write_service_config_file(
            &config,
            Some(&path),
            true,
            false,
            "2026-06-18T12:00:00+00:00",
        )
        .expect("write should succeed with explicit unsafe override");
        assert_eq!(saved["exists"], true);
        assert_eq!(saved["contains_secrets"], true);
        assert_eq!(saved["inline_secrets_persisted"], false);

        let raw: Value =
            serde_json::from_str(&fs::read_to_string(&path).expect("file should exist")).unwrap();
        assert_eq!(raw["kind"], SERVICE_CONFIG_FILE_KIND);
        assert_eq!(raw["config"]["api_key"], "");

        let loaded = load_service_config_file(Some(&path)).expect("load should parse envelope");
        assert_eq!(loaded.config["symbols"][0], "ETHUSDT");
        assert_eq!(
            loaded.metadata.format_version,
            SERVICE_CONFIG_FORMAT_VERSION
        );

        let status = service_config_file_status(Some(&path));
        let runtime_status = build_service_config_persistence_status(
            &status,
            &ServiceConfigRuntimeState {
                loaded: true,
                dirty: false,
                last_loaded_at: "2026-06-18T12:05:00+00:00".to_owned(),
                last_saved_at: "2026-06-18T12:00:00+00:00".to_owned(),
                migrated_from_format_version: None,
            },
        );
        assert_eq!(runtime_status["exists"], true);
        assert_eq!(runtime_status["loaded"], true);
        assert_eq!(runtime_status["dirty"], false);
        assert_eq!(runtime_status["last_saved_at"], "2026-06-18T12:00:00+00:00");
        assert_eq!(runtime_status["contains_secrets"], true);

        let blocked = write_service_config_file(
            &config,
            Some(&path),
            false,
            false,
            "2026-06-18T12:00:00+00:00",
        )
        .expect_err("explicit path outside the safe root should require trusted override");
        assert!(blocked.contains(SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn validates_runtime_config_like_python_service_load() {
        let config = json!({
            "symbols": ["ethusdt", "ETHUSDT"],
            "intervals": ["1M", "2 hours"],
            "account_type": "futures",
            "position_pct": "2.5",
            "runtime_symbol_interval_pairs": [{
                "symbol": "btcusdt",
                "interval": "15 minutes",
                "strategy_controls": {
                    "side": "buy",
                    "leverage": 20,
                    "loop_interval_override": "1 hour",
                    "stop_loss": {"scope": "bad-scope"}
                }
            }]
        });
        let validated = validate_service_runtime_config(&config)
            .expect("Python-compatible runtime config should validate");
        assert_eq!(validated["symbols"], json!(["ETHUSDT"]));
        assert_eq!(validated["intervals"], json!(["1mo", "2h"]));
        assert_eq!(
            validated["runtime_symbol_interval_pairs"][0]["symbol"],
            "BTCUSDT"
        );
        assert_eq!(
            validated["runtime_symbol_interval_pairs"][0]["strategy_controls"]["stop_loss"]["scope"],
            "per_trade"
        );

        let invalid = json!({
            "unknown_key": true,
            "symbols": ["BAD SYMBOL"],
            "intervals": ["0m"],
            "leverage": 126,
            "stop_loss": "not-object"
        });
        let issues = service_config_validation_issues(&invalid);
        let message = format_service_config_validation_issues(&issues);
        assert!(message.contains("unknown_key: is not a supported config key"));
        assert!(message.contains("leverage: must be between 1 and 125"));
        assert!(message.contains("stop_loss: must be an object"));
    }

    #[test]
    fn tauri_shell_delegates_config_persistence_to_python_service() {
        let tauri = RUST_CONFIG_PERSISTENCE_BOUNDARIES
            .iter()
            .find(|item| item.shell == "Tauri")
            .expect("Tauri boundary should be declared");
        assert!(tauri.operational);
        assert!(tauri.persistence_owner.contains("/api/v1/config/save"));
        assert!(
            tauri
                .validation_owner
                .contains("Python validate_runtime_config")
        );

        assert_eq!(RUST_CONFIG_PERSISTENCE_BOUNDARIES.len(), 1);
    }

    fn unique_temp_dir(label: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let dir = env::temp_dir().join(format!(
            "trading-bot-core-{label}-{}-{stamp}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).expect("temp dir should be creatable");
        dir
    }
}
