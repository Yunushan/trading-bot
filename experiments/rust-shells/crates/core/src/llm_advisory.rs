use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::generated_python_parity::{
    PYTHON_LLM_PROVIDERS, PYTHON_SERVICE_ROUTES, PythonLlmProvider,
};
use crate::order_audit::{redact_text, redact_value};

pub const LLM_EXECUTION_BOUNDARY: &str = "Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.";
pub const OLLAMA_MODEL_STORAGE_HINT: &str = "Ollama stores downloaded models outside this project in its own model cache (commonly ~/.ollama/models on Linux/macOS and %USERPROFILE%\\.ollama\\models on Windows).";

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LlmConfigInput {
    pub llm_enabled: bool,
    pub llm_provider: String,
    pub llm_model: String,
    pub llm_base_url: String,
    pub llm_api_key: String,
    pub llm_api_key_env: String,
    pub llm_use_for: String,
    pub llm_allow_public_network: bool,
    pub llm_reasoning_effort: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LlmExecutionPolicy {
    pub advisory_only: bool,
    pub can_execute_orders: bool,
    pub owner: String,
}

impl Default for LlmExecutionPolicy {
    fn default() -> Self {
        Self {
            advisory_only: true,
            can_execute_orders: false,
            owner: "strategy_and_risk_runtime".to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LlmConfigPayload {
    pub enabled: bool,
    pub provider: String,
    pub provider_label: String,
    pub mode: String,
    pub protocol: String,
    pub model: String,
    pub base_url: String,
    pub api_key_env: String,
    pub api_key_present: bool,
    pub use_for: String,
    pub allow_public_network: bool,
    pub reasoning_effort: String,
    pub default_reasoning_effort: String,
    pub reasoning_efforts: Vec<String>,
    pub model_suggestions: Vec<String>,
    pub execution_policy: LlmExecutionPolicy,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LlmHttpRequest {
    pub provider: String,
    pub mode: String,
    pub protocol: String,
    pub url: String,
    pub headers: BTreeMap<String, String>,
    pub json: Value,
    pub execution_policy: LlmExecutionPolicy,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct LocalModelStatus {
    pub model: String,
    pub base_url: String,
    pub server_kind: String,
    pub installed: bool,
    pub can_download: bool,
    pub can_start: bool,
    pub available_models: Vec<String>,
    pub error: String,
    pub storage_hint: String,
    pub storage_paths: Vec<String>,
    pub estimated_size_label: String,
    pub free_disk_gb: Option<f64>,
    pub recommended_free_disk_gb: Option<f64>,
    pub disk_space_warning: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocalModelRouteRequest {
    pub route_name: String,
    pub method: String,
    pub path: String,
    pub query: BTreeMap<String, String>,
    pub json: Value,
}

pub fn normalize_llm_provider_key(value: impl AsRef<str>) -> String {
    let raw = value.as_ref().trim().to_lowercase().replace('_', "-");
    let normalized = match raw.as_str() {
        "openai-chatgpt" => "openai",
        "claude" | "anthropic-claude" => "anthropic",
        "google" | "google-gemini" => "gemini",
        "xai" | "xai-grok" => "grok",
        "dashscope" | "alibaba" | "alibaba-qwen" => "qwen",
        "ollama" | "local-openai" | "local-openai-compatible" | "custom" => "local",
        other => other,
    };
    provider_by_key(normalized)
        .map(|provider| provider.key.to_owned())
        .unwrap_or_else(|| "openai".to_owned())
}

pub fn provider_by_key(value: impl AsRef<str>) -> Option<&'static PythonLlmProvider> {
    let key = value.as_ref().trim();
    PYTHON_LLM_PROVIDERS
        .iter()
        .find(|provider| provider.key == key)
}

pub fn build_llm_config_payload(input: &LlmConfigInput) -> LlmConfigPayload {
    let provider_key = normalize_llm_provider_key(&input.llm_provider);
    let provider = provider_by_key(&provider_key)
        .or_else(|| provider_by_key("openai"))
        .expect("generated Python LLM provider catalog should include openai");
    let api_key_env = non_empty_or(&input.llm_api_key_env, provider.api_key_env);
    LlmConfigPayload {
        enabled: input.llm_enabled,
        provider: provider.key.to_owned(),
        provider_label: provider.label.to_owned(),
        mode: provider.mode.to_owned(),
        protocol: provider.protocol.to_owned(),
        model: non_empty_or(&input.llm_model, provider.default_model),
        base_url: non_empty_or(&input.llm_base_url, provider.default_base_url),
        api_key_env: api_key_env.clone(),
        api_key_present: !input.llm_api_key.trim().is_empty()
            || std::env::var(&api_key_env)
                .map(|value| !value.trim().is_empty())
                .unwrap_or(false),
        use_for: non_empty_or(&input.llm_use_for, "advisory"),
        allow_public_network: input.llm_allow_public_network,
        reasoning_effort: normalize_reasoning_effort(provider, &input.llm_reasoning_effort),
        default_reasoning_effort: provider.default_reasoning_effort.to_owned(),
        reasoning_efforts: provider
            .reasoning_efforts
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        model_suggestions: provider
            .model_suggestions
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        execution_policy: LlmExecutionPolicy::default(),
    }
}

pub fn build_llm_chat_request(
    input: &LlmConfigInput,
    prompt: impl AsRef<str>,
    system_prompt: impl AsRef<str>,
    context: Option<&Value>,
) -> Result<LlmHttpRequest, String> {
    let payload = build_llm_config_payload(input);
    let user_prompt = prompt.as_ref().trim();
    if user_prompt.is_empty() {
        return Err("LLM prompt cannot be empty.".to_owned());
    }
    if payload.model.trim().is_empty() {
        return Err(format!(
            "Select an LLM model before calling {}.",
            payload.provider_label
        ));
    }

    let api_key = non_empty_or(
        &input.llm_api_key,
        &std::env::var(&payload.api_key_env).unwrap_or_default(),
    );
    let context_for_request = context_for_provider(context, &payload.mode);
    let mut headers = BTreeMap::from([("Content-Type".to_owned(), "application/json".to_owned())]);
    let url;
    let body;

    match payload.protocol.as_str() {
        "openai-compatible" | "openai-chat-completions" => {
            if !api_key.is_empty() {
                headers.insert("Authorization".to_owned(), format!("Bearer {api_key}"));
            }
            url = join_url(&payload.base_url, "chat/completions");
            let mut messages = vec![json!({"role": "system", "content": LLM_EXECUTION_BOUNDARY})];
            let system_prompt = system_prompt.as_ref().trim();
            if !system_prompt.is_empty() {
                messages.push(json!({"role": "system", "content": system_prompt}));
            }
            if let Some(context) = context_for_request {
                messages.push(json!({"role": "system", "content": format!("Trading context JSON: {context}")}));
            }
            messages.push(json!({"role": "user", "content": user_prompt}));
            let mut object = Map::from_iter([
                ("model".to_owned(), Value::String(payload.model.clone())),
                ("messages".to_owned(), Value::Array(messages)),
            ]);
            for (key, value) in
                openai_compatible_reasoning_body(&payload.provider, &payload.reasoning_effort)
            {
                object.insert(key, value);
            }
            body = Value::Object(object);
        }
        "anthropic-messages" => {
            if api_key.is_empty() {
                return Err("Anthropic Claude requires an API key.".to_owned());
            }
            headers.insert("x-api-key".to_owned(), api_key);
            headers.insert("anthropic-version".to_owned(), "2023-06-01".to_owned());
            url = join_url(&payload.base_url, "v1/messages");
            let mut messages = vec![json!({"role": "user", "content": user_prompt})];
            if let Some(context) = context_for_request {
                messages.insert(
                    0,
                    json!({"role": "user", "content": format!("Trading context JSON: {context}")}),
                );
            }
            let mut system_parts = vec![LLM_EXECUTION_BOUNDARY.to_owned()];
            let system_prompt = system_prompt.as_ref().trim();
            if !system_prompt.is_empty() {
                system_parts.push(system_prompt.to_owned());
            }
            let mut object = Map::from_iter([
                ("model".to_owned(), Value::String(payload.model.clone())),
                ("max_tokens".to_owned(), json!(1024)),
                ("messages".to_owned(), Value::Array(messages)),
                (
                    "system".to_owned(),
                    Value::String(system_parts.join("\n\n")),
                ),
            ]);
            for (key, value) in anthropic_thinking_body(&payload.reasoning_effort) {
                object.insert(key, value);
            }
            body = Value::Object(object);
        }
        "gemini-generate-content" => {
            if api_key.is_empty() {
                return Err("Google Gemini requires an API key.".to_owned());
            }
            url = format!(
                "{}?key={}",
                join_url(
                    &payload.base_url,
                    &format!(
                        "models/{}:generateContent",
                        percent_encode_model(&payload.model)
                    ),
                ),
                api_key
            );
            let mut parts = vec![json!({"text": LLM_EXECUTION_BOUNDARY})];
            let system_prompt = system_prompt.as_ref().trim();
            if !system_prompt.is_empty() {
                parts.push(json!({"text": system_prompt}));
            }
            if let Some(context) = context_for_request {
                parts.push(json!({"text": format!("Trading context JSON: {context}")}));
            }
            parts.push(json!({"text": user_prompt}));
            let mut object = Map::from_iter([("contents".to_owned(), json!([{"parts": parts}]))]);
            if let Some(generation_config) =
                gemini_generation_config(&payload.reasoning_effort, &payload.model)
            {
                object.insert("generationConfig".to_owned(), generation_config);
            }
            body = Value::Object(object);
        }
        other => {
            return Err(format!(
                "Unsupported LLM protocol for provider {}: {other}",
                payload.provider
            ));
        }
    }

    Ok(LlmHttpRequest {
        provider: payload.provider,
        mode: payload.mode,
        protocol: payload.protocol,
        url,
        headers,
        json: body,
        execution_policy: payload.execution_policy,
    })
}

pub fn sanitize_llm_request_for_display(request: &LlmHttpRequest) -> LlmHttpRequest {
    let mut sanitized = request.clone();
    for (key, value) in &mut sanitized.headers {
        if matches!(
            key.to_ascii_lowercase().as_str(),
            "authorization" | "x-api-key"
        ) {
            *value = "********".to_owned();
        }
    }
    if let Some((prefix, _secret)) = sanitized.url.split_once("key=") {
        sanitized.url = format!("{prefix}key=********");
    }
    sanitized
}

pub fn llm_output_policy_violations(text: impl AsRef<str>) -> Vec<String> {
    let lower = text.as_ref().trim().to_lowercase();
    if lower.is_empty() {
        return Vec::new();
    }
    let mut violations = BTreeSet::<String>::new();
    if let Ok(value) = serde_json::from_str::<Value>(text.as_ref()) {
        scan_structured_policy_value(&value, &mut violations);
    }
    for (label, phrases) in [
        (
            "order_execution_claim",
            [
                "order executed",
                "trade executed",
                "i executed",
                "i placed an order",
                "i submitted an order",
                "submitted the order",
            ]
            .as_slice(),
        ),
        (
            "direct_order_action",
            [
                "\"action\":\"place_order\"",
                "\"action\": \"place_order\"",
                "\"action\":\"submit_order\"",
                "\"action\": \"submit_order\"",
                "place_order",
                "submit_order",
                "execute_order",
            ]
            .as_slice(),
        ),
        (
            "risk_override",
            [
                "disable stop loss",
                "disabled stop loss",
                "override risk",
                "set leverage to",
                "changed leverage",
            ]
            .as_slice(),
        ),
    ] {
        if phrases.iter().any(|phrase| lower.contains(phrase)) {
            violations.insert(label.to_owned());
        }
    }
    ordered_policy_violations(violations)
}

pub fn server_kind(base_url: impl AsRef<str>) -> String {
    let text = base_url.as_ref().trim().to_lowercase();
    if text.contains("://127.0.0.1:11434")
        || text.contains("://localhost:11434")
        || text.contains("://[::1]:11434")
    {
        "ollama".to_owned()
    } else {
        "openai-compatible".to_owned()
    }
}

pub fn ollama_base_url(base_url: impl AsRef<str>) -> String {
    let mut text = base_url.as_ref().trim().trim_end_matches('/').to_owned();
    if text.ends_with("/v1") {
        text.truncate(text.len() - 3);
        text = text.trim_end_matches('/').to_owned();
    }
    text
}

pub fn estimate_ollama_model_size_label(model: impl AsRef<str>) -> String {
    match model.as_ref().trim().to_lowercase().as_str() {
        "" => "unknown size".to_owned(),
        "qwen3:0.6b" | "llama3.2:1b" => "about 1 GB".to_owned(),
        "qwen3:1.7b" | "llama3.2:3b" => "about 2 GB".to_owned(),
        "qwen3:4b" | "gemma3:4b" => "about 3 GB".to_owned(),
        "qwen3:8b" | "llama3.1:8b" | "deepseek-r1:8b" => "about 5 GB".to_owned(),
        "qwen3:14b" => "about 9 GB".to_owned(),
        "gpt-oss:20b" => "about 13 GB".to_owned(),
        "qwen3:30b-a3b" => "about 19 GB".to_owned(),
        "qwen3:32b" => "about 20 GB".to_owned(),
        _ => "size varies by model and quantization".to_owned(),
    }
}

pub fn build_local_model_route_request(
    route_name: impl AsRef<str>,
    base_url: impl AsRef<str>,
    model: impl AsRef<str>,
    source: impl AsRef<str>,
) -> Option<LocalModelRouteRequest> {
    let route_name = route_name.as_ref().trim();
    let route = PYTHON_SERVICE_ROUTES
        .iter()
        .find(|route| route.name == route_name)?;
    let clean_base = base_url.as_ref().trim().to_owned();
    let clean_model = model.as_ref().trim().to_owned();
    if route.methods.contains(&"GET") {
        return Some(LocalModelRouteRequest {
            route_name: route.name.to_owned(),
            method: "GET".to_owned(),
            path: route.path.to_owned(),
            query: BTreeMap::from([
                ("base_url".to_owned(), clean_base),
                ("model".to_owned(), clean_model),
            ]),
            json: Value::Null,
        });
    }
    Some(LocalModelRouteRequest {
        route_name: route.name.to_owned(),
        method: "POST".to_owned(),
        path: route.path.to_owned(),
        query: BTreeMap::new(),
        json: json!({
            "base_url": clean_base,
            "model": clean_model,
            "source": non_empty_or(source.as_ref(), "native-llm"),
        }),
    })
}

pub fn describe_local_model_status(
    status: &LocalModelStatus,
    fallback_model: impl AsRef<str>,
) -> String {
    let model = non_empty_or(&status.model, fallback_model.as_ref());
    let installed = if status.installed {
        "installed"
    } else {
        "not installed"
    };
    let size = if status.estimated_size_label.trim().is_empty() {
        String::new()
    } else {
        format!(", estimated {}", status.estimated_size_label.trim())
    };
    let storage = if !status.storage_paths.is_empty() {
        status.storage_paths.join("; ")
    } else {
        non_empty_or(
            &status.storage_hint,
            "Ollama model cache outside this project.",
        )
    };
    let warning = if status.disk_space_warning.trim().is_empty() {
        String::new()
    } else {
        format!(" {}", status.disk_space_warning.trim())
    };
    let error = if status.error.trim().is_empty() {
        String::new()
    } else {
        format!(" Server check: {}", redact_text(&status.error))
    };
    format!(
        "Local model '{model}' is {installed} on {}{size}. Storage: {storage}.{warning}{error}",
        non_empty_or(&status.server_kind, "local server")
    )
}

fn context_for_provider(context: Option<&Value>, mode: &str) -> Option<Value> {
    let context = context?;
    if mode.trim().eq_ignore_ascii_case("cloud") {
        return Some(cloud_safe_context(context));
    }
    Some(redact_value(context.clone()))
}

fn cloud_safe_context(context: &Value) -> Value {
    let object = context.as_object();
    json!({
        "privacy_notice": "Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.",
        "runtime": minimal_dict(object.and_then(|ctx| ctx.get("runtime")), &["phase", "control_plane"]),
        "status": minimal_dict(object.and_then(|ctx| ctx.get("status")), &["lifecycle_phase", "runtime_active", "active_engine_count"]),
        "execution": minimal_dict(object.and_then(|ctx| ctx.get("execution")), &["state", "workload_kind", "active_engine_count", "last_action"]),
        "config_summary": config_summary(object.and_then(|ctx| ctx.get("config"))),
        "portfolio_summary": portfolio_summary(object.and_then(|ctx| ctx.get("portfolio"))),
        "logs": {
            "count": object.and_then(|ctx| ctx.get("logs")).and_then(Value::as_array).map(|items| items.len()).unwrap_or(0),
            "redacted": true,
        },
    })
}

fn minimal_dict(value: Option<&Value>, keys: &[&str]) -> Value {
    let Some(map) = value.and_then(Value::as_object) else {
        return json!({});
    };
    let mut output = Map::new();
    for key in keys {
        if let Some(value) = map.get(*key) {
            output.insert((*key).to_owned(), redact_value(value.clone()));
        }
    }
    Value::Object(output)
}

fn config_summary(value: Option<&Value>) -> Value {
    let map = value.and_then(Value::as_object);
    json!({
        "mode": map.and_then(|cfg| cfg.get("mode")).cloned().map(redact_value).unwrap_or(Value::Null),
        "selected_exchange": map.and_then(|cfg| cfg.get("selected_exchange")).cloned().map(redact_value).unwrap_or(Value::Null),
        "account_type": map.and_then(|cfg| cfg.get("account_type")).cloned().map(redact_value).unwrap_or(Value::Null),
        "symbol_count": count_items(map.and_then(|cfg| cfg.get("symbols"))),
        "interval_count": count_items(map.and_then(|cfg| cfg.get("intervals"))),
        "llm": map.and_then(|cfg| cfg.get("llm")).cloned().map(redact_value).unwrap_or_else(|| json!({})),
        "raw_config_redacted": true,
    })
}

fn portfolio_summary(value: Option<&Value>) -> Value {
    let map = value.and_then(Value::as_object);
    json!({
        "open_position_count": count_items(map.and_then(|portfolio| portfolio.get("open_position_records"))),
        "closed_position_count": count_items(map.and_then(|portfolio| portfolio.get("closed_position_records"))),
        "active_pnl": map.and_then(|portfolio| portfolio.get("active_pnl")).cloned().map(redact_value).unwrap_or(Value::Null),
        "closed_pnl": map.and_then(|portfolio| portfolio.get("closed_pnl")).cloned().map(redact_value).unwrap_or(Value::Null),
        "position_records_redacted": true,
    })
}

fn count_items(value: Option<&Value>) -> usize {
    match value {
        Some(Value::Array(items)) => items.len(),
        Some(Value::Object(items)) => items.len(),
        _ => 0,
    }
}

fn normalize_reasoning_effort(provider: &PythonLlmProvider, value: &str) -> String {
    let raw = value.trim().to_lowercase().replace('_', "-");
    let efforts = provider.reasoning_efforts;
    let default = if provider.default_reasoning_effort.trim().is_empty() {
        efforts.first().copied().unwrap_or("default")
    } else {
        provider.default_reasoning_effort
    };
    let normalized = match raw.as_str() {
        "" | "auto" => default,
        "off" | "no" | "false" => {
            if efforts.contains(&"none") {
                "none"
            } else {
                "disabled"
            }
        }
        "extra-high" | "extra_high" => "xhigh",
        other => other,
    };
    if efforts.contains(&normalized) {
        normalized.to_owned()
    } else {
        default.to_owned()
    }
}

fn openai_compatible_reasoning_body(provider: &str, effort: &str) -> BTreeMap<String, Value> {
    if matches!(effort, "" | "default") {
        return BTreeMap::new();
    }
    if provider == "deepseek" {
        if matches!(effort, "none" | "disabled" | "off") {
            return BTreeMap::from([("thinking".to_owned(), json!({"type": "disabled"}))]);
        }
        let mut body = BTreeMap::from([("thinking".to_owned(), json!({"type": "enabled"}))]);
        if matches!(effort, "high" | "max" | "xhigh" | "low" | "medium") {
            body.insert(
                "reasoning_effort".to_owned(),
                json!(if matches!(effort, "max" | "xhigh") {
                    "max"
                } else {
                    effort
                }),
            );
        }
        return body;
    }
    BTreeMap::from([("reasoning_effort".to_owned(), json!(effort))])
}

fn anthropic_thinking_body(effort: &str) -> BTreeMap<String, Value> {
    if matches!(effort, "" | "default") {
        return BTreeMap::new();
    }
    if matches!(effort, "none" | "disabled" | "off") {
        return BTreeMap::from([("thinking".to_owned(), json!({"type": "disabled"}))]);
    }
    let budget = match effort {
        "enabled" | "low" => 2048,
        "medium" => 4096,
        "high" => 8192,
        _ => return BTreeMap::new(),
    };
    BTreeMap::from([
        ("max_tokens".to_owned(), json!(budget + 1024)),
        (
            "thinking".to_owned(),
            json!({"type": "enabled", "budget_tokens": budget}),
        ),
    ])
}

fn gemini_generation_config(effort: &str, model: &str) -> Option<Value> {
    if matches!(effort, "" | "default") {
        return None;
    }
    let mut level = if matches!(effort, "none" | "disabled" | "minimal") {
        "minimal"
    } else {
        effort
    };
    if model.starts_with("gemini-3-pro") && matches!(level, "minimal" | "medium") {
        level = if level == "minimal" { "low" } else { "high" };
    }
    matches!(level, "minimal" | "low" | "medium" | "high")
        .then(|| json!({"thinkingConfig": {"thinkingLevel": level}}))
}

fn scan_structured_policy_value(value: &Value, violations: &mut BTreeSet<String>) {
    match value {
        Value::Object(map) => {
            for (key, raw_item) in map {
                let item = raw_item
                    .as_str()
                    .map(|value| value.trim().to_lowercase())
                    .unwrap_or_else(|| raw_item.to_string().trim().to_lowercase());
                if key == "action"
                    && matches!(
                        item.as_str(),
                        "place_order" | "submit_order" | "execute_order"
                    )
                {
                    violations.insert("direct_order_action".to_owned());
                }
                if matches!(key.as_str(), "execution_status" | "order_status" | "status")
                    && matches!(item.as_str(), "executed" | "filled" | "submitted")
                {
                    violations.insert("order_execution_claim".to_owned());
                }
                if matches!(
                    key.as_str(),
                    "disable_stop_loss" | "risk_override" | "override_risk"
                ) && matches!(item.as_str(), "1" | "true" | "yes" | "on")
                {
                    violations.insert("risk_override".to_owned());
                }
                if key == "stop_loss_enabled"
                    && matches!(item.as_str(), "0" | "false" | "no" | "off")
                {
                    violations.insert("risk_override".to_owned());
                }
                scan_structured_policy_value(raw_item, violations);
            }
        }
        Value::Array(items) => {
            for item in items {
                scan_structured_policy_value(item, violations);
            }
        }
        _ => {}
    }
}

fn ordered_policy_violations(violations: BTreeSet<String>) -> Vec<String> {
    [
        "direct_order_action",
        "order_execution_claim",
        "risk_override",
    ]
    .into_iter()
    .filter(|label| violations.contains(*label))
    .map(str::to_owned)
    .collect()
}

fn non_empty_or(value: &str, fallback: &str) -> String {
    let text = value.trim();
    if text.is_empty() {
        fallback.trim().to_owned()
    } else {
        text.to_owned()
    }
}

fn join_url(base_url: &str, path: &str) -> String {
    format!(
        "{}/{}",
        base_url.trim().trim_end_matches('/'),
        path.trim().trim_start_matches('/')
    )
}

fn percent_encode_model(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| {
            if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'~') {
                vec![byte as char]
            } else {
                format!("%{byte:02X}").chars().collect()
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn provider_config_normalizes_aliases_and_reasoning_like_python() {
        let payload = build_llm_config_payload(&LlmConfigInput {
            llm_provider: "ollama".to_owned(),
            llm_reasoning_effort: "extra-high".to_owned(),
            ..Default::default()
        });
        assert_eq!(payload.provider, "local");
        assert_eq!(payload.base_url, "http://127.0.0.1:11434/v1");
        assert_eq!(payload.model, "qwen3:8b");
        assert_eq!(payload.reasoning_effort, "xhigh");
        assert!(payload.execution_policy.advisory_only);
        assert!(!payload.execution_policy.can_execute_orders);
    }

    #[test]
    fn openai_request_includes_advisory_boundary_and_cloud_safe_context() {
        let request = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "openai".to_owned(),
                llm_model: "gpt-5.5".to_owned(),
                llm_api_key: "secret-key".to_owned(),
                llm_reasoning_effort: "high".to_owned(),
                ..Default::default()
            },
            "Summarize risk",
            "Be concise",
            Some(&json!({
                "runtime": {"phase": "running"},
                "config": {
                    "mode": "Live",
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "llm": {"llm_api_key": "do-not-send"}
                },
                "portfolio": {
                    "open_position_records": {"BTCUSDT:L": {"secret": "raw"}},
                    "active_pnl": 12.5
                },
                "logs": [{"message": "api_key=secret"}]
            })),
        )
        .expect("openai request should be built");
        assert_eq!(request.url, "https://api.openai.com/v1/chat/completions");
        assert!(request.headers["Authorization"].starts_with("Bearer "));
        let body = request.json.to_string();
        assert!(body.contains(LLM_EXECUTION_BOUNDARY));
        assert!(body.contains("Cloud LLM context minimized"));
        assert!(body.contains("position_records_redacted"));
        assert!(!body.contains("do-not-send"));
        assert!(!body.contains("api_key=secret"));
        assert_eq!(request.json["reasoning_effort"], "high");
        let sanitized = sanitize_llm_request_for_display(&request);
        assert_eq!(sanitized.headers["Authorization"], "********");
    }

    #[test]
    fn local_model_routes_and_status_follow_python_service_contract() {
        assert_eq!(server_kind("http://127.0.0.1:11434/v1"), "ollama");
        assert_eq!(
            ollama_base_url("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434"
        );
        assert_eq!(estimate_ollama_model_size_label("qwen3:8b"), "about 5 GB");
        let status_route = build_local_model_route_request(
            "llm_local_model_status",
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            "rust-test",
        )
        .expect("status route should exist");
        assert_eq!(status_route.method, "GET");
        assert_eq!(status_route.path, "/api/v1/llm/local-model/status");
        assert_eq!(status_route.query["model"], "qwen3:8b");
        let pull_route = build_local_model_route_request(
            "llm_local_model_pull",
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            "rust-test",
        )
        .expect("pull route should exist");
        assert_eq!(pull_route.method, "POST");
        assert_eq!(pull_route.json["source"], "rust-test");
        let description = describe_local_model_status(
            &LocalModelStatus {
                model: "qwen3:8b".to_owned(),
                server_kind: "ollama".to_owned(),
                installed: false,
                estimated_size_label: "about 5 GB".to_owned(),
                storage_paths: vec!["C:/Users/Yunus/.ollama/models".to_owned()],
                disk_space_warning:
                    "Low disk space: about 6.2 GB free is recommended for this model.".to_owned(),
                ..Default::default()
            },
            "",
        );
        assert!(description.contains("not installed on ollama"));
        assert!(description.contains("estimated about 5 GB"));
        assert!(description.contains("Low disk space"));
    }

    #[test]
    fn output_policy_blocks_order_claims_and_risk_overrides() {
        assert_eq!(
            llm_output_policy_violations(r#"{"action":"place_order","status":"executed"}"#),
            vec![
                "direct_order_action".to_owned(),
                "order_execution_claim".to_owned()
            ]
        );
        assert_eq!(
            llm_output_policy_violations("I executed the trade and disabled stop loss."),
            vec![
                "order_execution_claim".to_owned(),
                "risk_override".to_owned()
            ]
        );
    }
}
