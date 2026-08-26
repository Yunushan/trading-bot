use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::net::IpAddr;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::generated_python_parity::{
    PYTHON_LLM_MODEL_CATALOG_PATH_ENV, PYTHON_LLM_PROVIDER_CHOICES, PYTHON_LLM_PROVIDERS,
    PYTHON_OLLAMA_MODEL_SIZE_HINTS, PYTHON_SERVICE_ROUTES, PythonLlmProvider,
};
use crate::order_audit::{redact_text, redact_value};

pub const LLM_EXECUTION_BOUNDARY: &str = "Execution boundary: this LLM is advisory only. It must not place orders, claim that an order was executed, or override deterministic strategy, risk, take-profit, or stop-loss logic.";
pub const OLLAMA_MODEL_STORAGE_HINT: &str = "Ollama stores downloaded models outside this project in its own model cache (commonly ~/.ollama/models on Linux/macOS and %USERPROFILE%\\.ollama\\models on Windows).";

#[derive(Debug, Clone, Default, PartialEq)]
pub struct LlmConfigInput {
    pub llm_enabled: bool,
    pub llm_provider: String,
    pub llm_model: String,
    pub llm_base_url: String,
    pub llm_api_key: String,
    pub llm_api_key_env: String,
    pub llm_use_for: String,
    pub llm_allow_public_network: bool,
    pub llm_api_style: String,
    pub llm_reasoning_effort: String,
    pub llm_speed: String,
    pub llm_context_window: u64,
    pub llm_max_output_tokens: u64,
    pub llm_verbosity: String,
    pub llm_temperature: Option<f64>,
    pub llm_top_p: Option<f64>,
    pub llm_timeout_seconds: u64,
    pub llm_request_options: Value,
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
    pub provider_protocol: String,
    pub api_style: String,
    pub api_styles: Vec<String>,
    pub catalog_revision: String,
    pub catalog_path: String,
    pub custom_models_env: String,
    pub custom_models_path_env: String,
    pub model: String,
    pub base_url: String,
    pub api_key_env: String,
    pub api_key_present: bool,
    pub use_for: String,
    pub allow_public_network: bool,
    pub reasoning_effort: String,
    pub default_reasoning_effort: String,
    pub reasoning_efforts: Vec<String>,
    pub speed: String,
    pub default_speed: String,
    pub speed_options: Vec<String>,
    pub context_window: u64,
    pub max_output_tokens: u64,
    pub verbosity: String,
    pub temperature: Option<f64>,
    pub top_p: Option<f64>,
    pub timeout_seconds: u64,
    pub request_options: Value,
    pub supports_model_discovery: bool,
    pub model_discovery_path: String,
    pub model_suggestions: Vec<String>,
    pub notes: Vec<String>,
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
    pub timeout_seconds: u64,
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
    let raw = normalize_provider_token(value.as_ref());
    let normalized = PYTHON_LLM_PROVIDER_CHOICES
        .iter()
        .find(|(alias, _)| *alias == raw)
        .map(|(_, provider)| *provider)
        .unwrap_or(raw.as_str());
    provider_by_key(normalized)
        .map(|provider| provider.key.to_owned())
        .unwrap_or_else(|| "openai".to_owned())
}

pub fn provider_by_key(value: impl AsRef<str>) -> Option<&'static PythonLlmProvider> {
    let key = normalize_provider_token(value.as_ref());
    PYTHON_LLM_PROVIDERS
        .iter()
        .find(|provider| provider.key == key)
}

fn normalize_provider_token(value: &str) -> String {
    value.trim().to_lowercase().replace('_', "-")
}

fn base_url_uses_public_network(base_url: &str) -> bool {
    let Ok(url) = reqwest::Url::parse(base_url.trim()) else {
        return false;
    };
    let Some(host) = url.host_str() else {
        return false;
    };
    let host = host.trim().to_lowercase();
    if host == "localhost" || host.ends_with(".local") {
        return false;
    }
    match host.parse::<IpAddr>() {
        Ok(IpAddr::V4(address)) => {
            !(address.is_loopback() || address.is_private() || address.is_link_local())
        }
        Ok(IpAddr::V6(address)) => {
            !(address.is_loopback() || address.is_unique_local() || address.is_unicast_link_local())
        }
        Err(_) => true,
    }
}

fn append_unique_model(models: &mut Vec<String>, value: impl AsRef<str>) {
    let model = value.as_ref().trim();
    if !model.is_empty() && !models.iter().any(|item| item == model) {
        models.push(model.to_owned());
    }
}

fn python_catalog_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => format!("'{}'", value.replace('\\', "\\\\").replace('\'', "\\'")),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_catalog_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| {
                    format!(
                        "{}: {}",
                        python_catalog_repr(&Value::String(key.clone())),
                        python_catalog_repr(value)
                    )
                })
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn append_catalog_model(models: &mut Vec<String>, value: &Value) {
    let text = match value {
        Value::Null | Value::Bool(false) => None,
        Value::String(value) => Some(value.clone()),
        Value::Bool(true) => Some("True".to_owned()),
        Value::Number(value) if value.as_f64() == Some(0.0) => None,
        Value::Number(value) => Some(value.to_string()),
        Value::Array(values) if values.is_empty() => None,
        Value::Object(values) if values.is_empty() => None,
        Value::Array(_) | Value::Object(_) => Some(python_catalog_repr(value)),
    };
    if let Some(text) = text {
        append_unique_model(models, text);
    }
}

fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        env::var_os("USERPROFILE")
            .filter(|value| !value.is_empty())
            .or_else(|| env::var_os("HOME").filter(|value| !value.is_empty()))
            .map(PathBuf::from)
    }
    #[cfg(not(windows))]
    {
        env::var_os("HOME")
            .filter(|value| !value.is_empty())
            .or_else(|| env::var_os("USERPROFILE").filter(|value| !value.is_empty()))
            .map(PathBuf::from)
    }
}

fn expand_user_path(path: &Path) -> PathBuf {
    let text = path.to_string_lossy();
    if text == "~" {
        return home_dir().unwrap_or_else(|| path.to_path_buf());
    }
    if let Some(rest) = text.strip_prefix("~/").or_else(|| text.strip_prefix("~\\"))
        && let Some(home) = home_dir()
    {
        return home.join(rest);
    }
    path.to_path_buf()
}

fn model_catalog_path() -> Option<PathBuf> {
    if let Ok(value) = env::var(PYTHON_LLM_MODEL_CATALOG_PATH_ENV) {
        let path = value.trim();
        if !path.is_empty() {
            return Some(expand_user_path(Path::new(path)));
        }
    }
    home_dir().map(|home| home.join(".trading-bot").join("llm-models.json"))
}

fn model_catalog_path_label() -> String {
    model_catalog_path()
        .map(|path| path.to_string_lossy().into_owned())
        .unwrap_or_else(|| {
            expand_user_path(Path::new("~/.trading-bot/llm-models.json"))
                .to_string_lossy()
                .into_owned()
        })
}

fn model_suggestions_for_provider(provider: &PythonLlmProvider) -> Vec<String> {
    let extra_models = env::var(provider.custom_models_env).ok();
    let catalog_path = model_catalog_path();
    model_suggestions_for_provider_with_sources(
        provider,
        extra_models.as_deref(),
        catalog_path.as_deref(),
    )
}

fn model_suggestions_for_provider_with_sources(
    provider: &PythonLlmProvider,
    extra_models: Option<&str>,
    catalog_path: Option<&Path>,
) -> Vec<String> {
    let mut models = provider
        .model_suggestions
        .iter()
        .map(|value| (*value).to_owned())
        .collect::<Vec<_>>();
    if let Some(raw) = extra_models {
        for value in raw.replace(';', ",").split(',') {
            append_unique_model(&mut models, value);
        }
    }
    let Some(path) = catalog_path else {
        return models;
    };
    let Ok(text) = fs::read_to_string(path) else {
        return models;
    };
    let Ok(payload) = serde_json::from_str::<Value>(&text) else {
        return models;
    };
    let raw_models = match payload.get(provider.key) {
        None | Some(Value::Null) => payload
            .get("providers")
            .and_then(|items| items.get(provider.key)),
        Some(value) => Some(value),
    };
    if let Some(Value::Array(items)) = raw_models {
        for value in items {
            append_catalog_model(&mut models, value);
        }
    }
    models
}

pub fn build_llm_config_payload(input: &LlmConfigInput) -> LlmConfigPayload {
    let provider_key = normalize_llm_provider_key(&input.llm_provider);
    let provider = provider_by_key(&provider_key)
        .or_else(|| provider_by_key("openai"))
        .expect("generated Python LLM provider catalog should include openai");
    let api_key_env = non_empty_or(&input.llm_api_key_env, provider.api_key_env);
    let (api_style, protocol) = normalize_api_style(provider, &input.llm_api_style);
    let request_options = input
        .llm_request_options
        .as_object()
        .cloned()
        .map(Value::Object)
        .unwrap_or_else(|| json!({}));
    LlmConfigPayload {
        enabled: input.llm_enabled,
        provider: provider.key.to_owned(),
        provider_label: provider.label.to_owned(),
        mode: provider.mode.to_owned(),
        protocol,
        provider_protocol: provider.protocol.to_owned(),
        api_style,
        api_styles: provider
            .api_styles
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        catalog_revision: provider.catalog_revision.to_owned(),
        catalog_path: model_catalog_path_label(),
        custom_models_env: provider.custom_models_env.to_owned(),
        custom_models_path_env: provider.custom_models_path_env.to_owned(),
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
        speed: normalize_option_token(&input.llm_speed, provider.default_speed),
        default_speed: provider.default_speed.to_owned(),
        speed_options: provider
            .speed_options
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        context_window: input.llm_context_window.min(10_000_000),
        max_output_tokens: input.llm_max_output_tokens.min(2_000_000),
        verbosity: normalize_option_token(&input.llm_verbosity, "default"),
        temperature: input
            .llm_temperature
            .filter(|value| value.is_finite())
            .map(|value| value.clamp(0.0, 2.0)),
        top_p: input
            .llm_top_p
            .filter(|value| value.is_finite())
            .map(|value| value.clamp(0.0, 1.0)),
        timeout_seconds: if input.llm_timeout_seconds == 0 {
            30
        } else {
            input.llm_timeout_seconds.clamp(1, 3_600)
        },
        request_options,
        supports_model_discovery: provider.supports_model_discovery,
        model_discovery_path: provider.model_discovery_path.to_owned(),
        model_suggestions: model_suggestions_for_provider(provider),
        notes: provider
            .notes
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
    let base_url_is_public = base_url_uses_public_network(&payload.base_url);
    if payload.mode != "cloud" && base_url_is_public && !payload.allow_public_network {
        return Err(
            "Public local/custom LLM endpoints are disabled. Enable the public network endpoint control before using this base URL."
                .to_owned(),
        );
    }

    let api_key = non_empty_or(
        &input.llm_api_key,
        &std::env::var(&payload.api_key_env).unwrap_or_default(),
    );
    let context_for_request = context_for_provider(
        context,
        &payload.mode,
        payload.allow_public_network || base_url_is_public,
    );
    let context_text = context_for_request.as_ref().map(|context| {
        bounded_context_json_text(
            context,
            payload.context_window,
            payload.max_output_tokens,
            user_prompt,
            system_prompt.as_ref(),
        )
    });
    let mut headers = BTreeMap::from([("Content-Type".to_owned(), "application/json".to_owned())]);
    let url;
    let mut body;

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
            if let Some(context) = context_text.as_ref() {
                messages.push(json!({
                    "role": "system",
                    "content": format!("Trading context JSON: {context}"),
                }));
            }
            messages.push(json!({"role": "user", "content": user_prompt}));
            let mut object = Map::from_iter([
                ("model".to_owned(), Value::String(payload.model.clone())),
                ("messages".to_owned(), Value::Array(messages)),
            ]);
            for (key, value) in openai_compatible_reasoning_body(
                &payload.provider,
                &payload.model,
                &payload.reasoning_effort,
            ) {
                object.insert(key, value);
            }
            body = Value::Object(object);
        }
        "openai-responses" => {
            if !api_key.is_empty() {
                headers.insert("Authorization".to_owned(), format!("Bearer {api_key}"));
            }
            url = join_url(&payload.base_url, "responses");
            let mut instruction_parts = vec![LLM_EXECUTION_BOUNDARY.to_owned()];
            let system_prompt = system_prompt.as_ref().trim();
            if !system_prompt.is_empty() {
                instruction_parts.push(system_prompt.to_owned());
            }
            if let Some(context) = context_text.as_ref() {
                instruction_parts.push(format!("Trading context JSON: {context}"));
            }
            let mut object = Map::from_iter([
                ("model".to_owned(), Value::String(payload.model.clone())),
                (
                    "instructions".to_owned(),
                    Value::String(instruction_parts.join("\n\n")),
                ),
                ("input".to_owned(), Value::String(user_prompt.to_owned())),
            ]);
            for (key, value) in openai_responses_reasoning_body(&payload.reasoning_effort) {
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
            if let Some(context) = context_text.as_ref() {
                messages.insert(
                    0,
                    json!({
                        "role": "user",
                        "content": format!("Trading context JSON: {context}"),
                    }),
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
            for (key, value) in
                anthropic_thinking_body(&payload.reasoning_effort, payload.max_output_tokens)
            {
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
            if let Some(context) = context_text.as_ref() {
                parts.push(json!({
                    "text": format!("Trading context JSON: {context}"),
                }));
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

    apply_configured_request_options(&mut body, &payload);

    Ok(LlmHttpRequest {
        provider: payload.provider,
        mode: payload.mode,
        protocol: payload.protocol,
        url,
        headers,
        json: body,
        timeout_seconds: payload.timeout_seconds,
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
    let raw = text.as_ref().trim();
    let lower = raw.to_lowercase();
    if lower.is_empty() {
        return Vec::new();
    }
    let mut violations = BTreeSet::<String>::new();
    for value in json_candidates_from_text(raw) {
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
    let clean = model.as_ref().trim().to_lowercase();
    if clean.is_empty() {
        return "unknown size".to_owned();
    }
    ollama_model_size_hint(&clean)
        .map(|(label, _)| label.to_owned())
        .unwrap_or_else(|| "size varies by model and quantization".to_owned())
}

pub fn estimate_ollama_model_size_gb(model: impl AsRef<str>) -> Option<f64> {
    let clean = model.as_ref().trim().to_lowercase();
    if clean.is_empty() {
        return None;
    }
    ollama_model_size_hint(&clean).and_then(|(_, size_gb)| size_gb)
}

fn ollama_model_size_hint(model: &str) -> Option<(&'static str, Option<f64>)> {
    let direct = PYTHON_OLLAMA_MODEL_SIZE_HINTS
        .iter()
        .find(|hint| hint.model == model)
        .or_else(|| {
            if model.contains(':') {
                return None;
            }
            let tagged = format!("{model}:latest");
            PYTHON_OLLAMA_MODEL_SIZE_HINTS
                .iter()
                .find(|hint| hint.model == tagged)
        })?;
    Some((direct.label, direct.size_gb))
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

fn context_for_provider(
    context: Option<&Value>,
    mode: &str,
    allow_public_network: bool,
) -> Option<Value> {
    let context = context?;
    if mode.trim().eq_ignore_ascii_case("cloud") || allow_public_network {
        if !context.as_object().is_some_and(|object| !object.is_empty()) {
            return None;
        }
        return Some(cloud_safe_context(context));
    }
    match context {
        Value::Null => None,
        Value::Object(object) if object.is_empty() => None,
        Value::Array(items) if items.is_empty() => None,
        Value::String(value) if value.is_empty() => None,
        _ => Some(context.clone()),
    }
}

fn context_json_text(context: &Value) -> String {
    serde_json::to_string(context).unwrap_or_else(|_| context.to_string())
}

fn bounded_context_json_text(
    context: &Value,
    context_window: u64,
    max_output_tokens: u64,
    prompt: &str,
    system_prompt: &str,
) -> String {
    let serialized = context_json_text(context);
    if context_window == 0 {
        return serialized;
    }
    let fixed_characters = prompt.len() + system_prompt.len() + LLM_EXECUTION_BOUNDARY.len();
    let fixed_tokens = ((fixed_characters + 3) / 4).max(256) as u64;
    let output_reserve = if max_output_tokens > 0 {
        max_output_tokens
    } else {
        (context_window / 8).clamp(256, 4096)
    };
    let character_budget = context_window
        .saturating_sub(fixed_tokens.saturating_add(output_reserve))
        .saturating_mul(4) as usize;
    if serialized.chars().count() <= character_budget {
        return serialized;
    }
    if character_budget < 160 {
        return json!({
            "context_truncated": true,
            "original_characters": serialized.chars().count(),
            "excerpt": "",
        })
        .to_string();
    }
    let excerpt_budget = character_budget.saturating_sub(120).max(32);
    let prefix_length = (excerpt_budget * 2 / 3).max(16);
    let suffix_length = excerpt_budget.saturating_sub(prefix_length).max(16);
    let prefix = serialized.chars().take(prefix_length).collect::<String>();
    let suffix = serialized
        .chars()
        .rev()
        .take(suffix_length)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<String>();
    json!({
        "context_truncated": true,
        "original_characters": serialized.chars().count(),
        "prefix": prefix,
        "suffix": suffix,
    })
    .to_string()
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
        "" => default,
        "auto" if efforts.contains(&"auto") => "auto",
        "auto" => default,
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
    if efforts.contains(&normalized) || safe_option_token(normalized) {
        normalized.to_owned()
    } else {
        default.to_owned()
    }
}

fn safe_option_token(value: &str) -> bool {
    let text = value.trim();
    !text.is_empty()
        && text.len() <= 64
        && text
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "-_./:".contains(character))
}

fn normalize_option_token(value: &str, fallback: &str) -> String {
    let normalized = value.trim().to_lowercase().replace('_', "-");
    if safe_option_token(&normalized) {
        normalized
    } else {
        fallback.to_owned()
    }
}

fn normalize_api_style(provider: &PythonLlmProvider, value: &str) -> (String, String) {
    let normalized = value.trim().to_lowercase().replace('_', "-");
    let requested = match normalized.as_str() {
        "" | "auto" | "default" | "provider" | "provider-default" => "provider-default",
        "chat" | "chat-completions" | "openai-compatible" => "openai-chat-completions",
        "response" | "responses" => "openai-responses",
        "messages" | "anthropic" => "anthropic-messages",
        "generate-content" | "gemini" => "gemini-generate-content",
        other => other,
    };
    if requested == "provider-default" {
        return (requested.to_owned(), provider.protocol.to_owned());
    }
    if matches!(
        requested,
        "openai-chat-completions"
            | "openai-responses"
            | "anthropic-messages"
            | "gemini-generate-content"
    ) {
        return (requested.to_owned(), requested.to_owned());
    }
    ("provider-default".to_owned(), provider.protocol.to_owned())
}

fn openai_compatible_reasoning_body(
    provider: &str,
    model: &str,
    effort: &str,
) -> BTreeMap<String, Value> {
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
    if provider == "qwen" {
        return BTreeMap::from([(
            "enable_thinking".to_owned(),
            json!(!matches!(effort, "none" | "disabled" | "off")),
        )]);
    }
    if provider == "moonshot" {
        let normalized_model = model.trim().to_lowercase();
        if normalized_model.starts_with("kimi-k3") {
            return if effort == "max" {
                BTreeMap::from([("reasoning_effort".to_owned(), json!("max"))])
            } else {
                BTreeMap::new()
            };
        }
        if normalized_model.starts_with("kimi-k2.5") || normalized_model.starts_with("kimi-k2.6") {
            if matches!(effort, "none" | "disabled" | "off") {
                return BTreeMap::from([("thinking".to_owned(), json!({"type": "disabled"}))]);
            }
            if matches!(
                effort,
                "enabled" | "low" | "medium" | "high" | "max" | "xhigh"
            ) {
                return BTreeMap::from([("thinking".to_owned(), json!({"type": "enabled"}))]);
            }
        }
        // Kimi K2.7 Code always reasons and rejects a thinking override.
        return BTreeMap::new();
    }
    BTreeMap::from([("reasoning_effort".to_owned(), json!(effort))])
}

fn openai_responses_reasoning_body(effort: &str) -> BTreeMap<String, Value> {
    if matches!(effort, "" | "default" | "auto") {
        return BTreeMap::new();
    }
    let normalized = if matches!(effort, "disabled" | "off") {
        "none"
    } else {
        effort
    };
    BTreeMap::from([("reasoning".to_owned(), json!({"effort": normalized}))])
}

fn anthropic_thinking_body(effort: &str, max_output_tokens: u64) -> BTreeMap<String, Value> {
    if matches!(effort, "" | "default") {
        return BTreeMap::new();
    }
    if matches!(effort, "none" | "disabled" | "off") {
        return BTreeMap::from([("thinking".to_owned(), json!({"type": "disabled"}))]);
    }
    let mut budget = match effort {
        "enabled" | "low" => 2048,
        "medium" => 4096,
        "high" => 8192,
        _ => return BTreeMap::new(),
    };
    if max_output_tokens > 0 {
        budget = budget.min(max_output_tokens.saturating_sub(1));
        if budget == 0 {
            return BTreeMap::from([("max_tokens".to_owned(), json!(max_output_tokens))]);
        }
        return BTreeMap::from([
            ("max_tokens".to_owned(), json!(max_output_tokens)),
            (
                "thinking".to_owned(),
                json!({"type": "enabled", "budget_tokens": budget}),
            ),
        ]);
    }
    BTreeMap::from([
        ("max_tokens".to_owned(), json!(budget + 1024)),
        (
            "thinking".to_owned(),
            json!({"type": "enabled", "budget_tokens": budget}),
        ),
    ])
}

fn service_tier_for_speed(speed: &str) -> &str {
    match speed {
        "balanced" | "quality" => "default",
        "economy" => "flex",
        "fast" => "priority",
        other => other,
    }
}

fn uses_modern_openai_output_limit(provider: &str, model: &str) -> bool {
    provider == "openai"
        && ["gpt-5", "o1", "o3", "o4"]
            .iter()
            .any(|prefix| model.trim().to_lowercase().starts_with(prefix))
}

fn request_option_is_reserved(key: &str) -> bool {
    matches!(
        key.trim().to_lowercase().as_str(),
        "contents"
            | "functions"
            | "input"
            | "instructions"
            | "messages"
            | "model"
            | "stream"
            | "system"
            | "tool_choice"
            | "tools"
    )
}

fn merge_json_object(target: &mut Map<String, Value>, values: &Map<String, Value>) {
    for (key, value) in values {
        match (target.get_mut(key), value) {
            (Some(Value::Object(existing)), Value::Object(incoming)) => {
                merge_json_object(existing, incoming);
            }
            _ => {
                target.insert(key.clone(), value.clone());
            }
        }
    }
}

fn apply_configured_request_options(body: &mut Value, payload: &LlmConfigPayload) {
    let Some(object) = body.as_object_mut() else {
        return;
    };
    if payload.protocol == "gemini-generate-content" {
        let generation_config = object
            .entry("generationConfig".to_owned())
            .or_insert_with(|| json!({}));
        if !generation_config.is_object() {
            *generation_config = json!({});
        }
        let generation = generation_config
            .as_object_mut()
            .expect("generationConfig was normalized to an object");
        if payload.max_output_tokens > 0 {
            generation.insert(
                "maxOutputTokens".to_owned(),
                json!(payload.max_output_tokens),
            );
        }
        if let Some(value) = payload.temperature {
            generation.insert("temperature".to_owned(), json!(value));
        }
        if let Some(value) = payload.top_p {
            generation.insert("topP".to_owned(), json!(value));
        }
        if generation.is_empty() {
            object.remove("generationConfig");
        }
    } else {
        if payload.max_output_tokens > 0 {
            let key = if payload.protocol == "openai-responses" {
                "max_output_tokens"
            } else if payload.protocol == "anthropic-messages"
                || !uses_modern_openai_output_limit(&payload.provider, &payload.model)
            {
                "max_tokens"
            } else {
                "max_completion_tokens"
            };
            object.insert(key.to_owned(), json!(payload.max_output_tokens));
        }
        if let Some(value) = payload.temperature {
            object.insert("temperature".to_owned(), json!(value));
        }
        if let Some(value) = payload.top_p {
            object.insert("top_p".to_owned(), json!(value));
        }
    }

    if matches!(
        payload.protocol.as_str(),
        "openai-chat-completions" | "openai-compatible" | "openai-responses"
    ) && !matches!(payload.speed.as_str(), "" | "default")
    {
        object.insert(
            "service_tier".to_owned(),
            json!(service_tier_for_speed(&payload.speed)),
        );
    }
    if payload.protocol == "openai-responses"
        && !matches!(payload.verbosity.as_str(), "" | "default" | "auto")
    {
        let text = object.entry("text".to_owned()).or_insert_with(|| json!({}));
        if !text.is_object() {
            *text = json!({});
        }
        text.as_object_mut()
            .expect("text was normalized to an object")
            .insert("verbosity".to_owned(), json!(payload.verbosity));
    } else if matches!(
        payload.protocol.as_str(),
        "openai-chat-completions" | "openai-compatible"
    ) && !matches!(payload.verbosity.as_str(), "" | "default" | "auto")
    {
        object.insert("verbosity".to_owned(), json!(payload.verbosity));
    }

    if let Some(options) = payload.request_options.as_object() {
        let safe = options
            .iter()
            .filter(|(key, _)| !request_option_is_reserved(key))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect::<Map<String, Value>>();
        merge_json_object(object, &safe);
    }
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

fn json_candidates_from_text(text: &str) -> Vec<Value> {
    let raw = text.trim();
    if raw.is_empty() {
        return Vec::new();
    }
    let mut candidates = vec![raw.to_owned()];
    if raw.starts_with("```") {
        let lines = raw.lines().collect::<Vec<_>>();
        if lines.len() >= 3
            && lines
                .last()
                .is_some_and(|line| line.trim().starts_with("```"))
        {
            candidates.push(lines[1..lines.len() - 1].join("\n").trim().to_owned());
        }
    }
    if let (Some(first), Some(last)) = (raw.find('{'), raw.rfind('}')) {
        if last > first {
            candidates.push(raw[first..=last].to_owned());
        }
    }
    if let (Some(first), Some(last)) = (raw.find('['), raw.rfind(']')) {
        if last > first {
            candidates.push(raw[first..=last].to_owned());
        }
    }
    let mut seen = BTreeSet::new();
    candidates
        .into_iter()
        .filter(|candidate| !candidate.is_empty() && seen.insert(candidate.clone()))
        .filter_map(|candidate| serde_json::from_str::<Value>(&candidate).ok())
        .collect()
}

fn scan_structured_policy_value(value: &Value, violations: &mut BTreeSet<String>) {
    match value {
        Value::Object(map) => {
            for (key, raw_item) in map {
                let key = key.trim().to_lowercase();
                let item = raw_item
                    .as_str()
                    .map(|value| value.trim().to_lowercase())
                    .unwrap_or_else(|| raw_item.to_string().trim().to_lowercase());
                if matches!(
                    key.as_str(),
                    "action" | "command" | "intent" | "operation" | "tool"
                ) {
                    if matches!(
                        item.as_str(),
                        "cancel_order"
                            | "change_leverage"
                            | "close_position"
                            | "create_order"
                            | "execute_order"
                            | "market_buy"
                            | "market_sell"
                            | "open_position"
                            | "place_order"
                            | "set_leverage"
                            | "submit_order"
                    ) {
                        violations.insert("direct_order_action".to_owned());
                    }
                    if matches!(
                        item.as_str(),
                        "change_leverage" | "disable_stop_loss" | "override_risk" | "set_leverage"
                    ) {
                        violations.insert("risk_override".to_owned());
                    }
                }
                if matches!(key.as_str(), "execution_status" | "order_status" | "status")
                    && matches!(
                        item.as_str(),
                        "executed" | "filled" | "order_executed" | "placed" | "submitted"
                    )
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
        "order_execution_claim",
        "direct_order_action",
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
    use crate::generated_python_parity::{
        PYTHON_LLM_CHAT_REQUEST_REFERENCE_JSON, PYTHON_LLM_OUTPUT_POLICY_REFERENCE_JSON,
    };

    #[test]
    fn provider_config_normalizes_aliases_and_reasoning_like_python() {
        let payload = build_llm_config_payload(&LlmConfigInput {
            llm_provider: "ollama".to_owned(),
            llm_reasoning_effort: "extra-high".to_owned(),
            ..Default::default()
        });
        assert_eq!(payload.provider, "ollama");
        assert_eq!(payload.base_url, "http://127.0.0.1:11434/v1");
        assert_eq!(payload.model, "qwen3:8b");
        assert_eq!(payload.reasoning_effort, "xhigh");
        assert!(payload.execution_policy.advisory_only);
        assert!(!payload.execution_policy.can_execute_orders);
    }

    #[test]
    fn every_generated_python_provider_alias_normalizes_to_its_source_value() {
        for (alias, expected) in PYTHON_LLM_PROVIDER_CHOICES {
            assert_eq!(
                normalize_llm_provider_key(alias),
                *expected,
                "provider alias should follow the generated Python mapping: {alias}"
            );
        }
    }

    #[test]
    fn every_generated_python_provider_preserves_all_catalog_options() {
        for provider in PYTHON_LLM_PROVIDERS {
            let payload = build_llm_config_payload(&LlmConfigInput {
                llm_provider: provider.key.to_owned(),
                llm_api_key_env: "__TRADING_BOT_PARITY_PROVIDER_KEY__".to_owned(),
                ..Default::default()
            });
            assert_eq!(
                payload.provider, provider.key,
                "provider key should match Python"
            );
            assert_eq!(
                payload.provider_label, provider.label,
                "provider label should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.mode, provider.mode,
                "provider mode should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.protocol, provider.protocol,
                "provider protocol should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.base_url, provider.default_base_url,
                "provider endpoint should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.model, provider.default_model,
                "provider model should match Python: {}",
                provider.key
            );
            assert_eq!(payload.api_key_env, "__TRADING_BOT_PARITY_PROVIDER_KEY__");
            assert_eq!(
                payload.reasoning_efforts,
                provider
                    .reasoning_efforts
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect::<Vec<_>>(),
                "reasoning options should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.default_reasoning_effort, provider.default_reasoning_effort,
                "default reasoning should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.api_styles,
                provider
                    .api_styles
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect::<Vec<_>>(),
                "API styles should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.speed_options,
                provider
                    .speed_options
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect::<Vec<_>>(),
                "speed options should match Python: {}",
                provider.key
            );
            assert_eq!(payload.default_speed, provider.default_speed);
            assert_eq!(
                payload.supports_model_discovery,
                provider.supports_model_discovery
            );
            assert_eq!(payload.model_discovery_path, provider.model_discovery_path);
            assert_eq!(
                payload.catalog_revision, provider.catalog_revision,
                "catalog revision should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.custom_models_env, provider.custom_models_env,
                "custom model environment should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.custom_models_path_env, provider.custom_models_path_env,
                "custom model catalog environment should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.model_suggestions,
                model_suggestions_for_provider(provider),
                "model options should match Python: {}",
                provider.key
            );
            assert_eq!(
                payload.notes,
                provider
                    .notes
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect::<Vec<_>>(),
                "provider notes should match Python: {}",
                provider.key
            );
            assert!(payload.execution_policy.advisory_only);
            assert!(!payload.execution_policy.can_execute_orders);
        }
    }

    #[test]
    fn dynamic_catalog_paths_and_values_follow_python_shape() {
        if let Some(home) = home_dir() {
            assert_eq!(
                expand_user_path(Path::new("~/.trading-bot/llm-models.json")),
                home.join(".trading-bot").join("llm-models.json")
            );
        }

        let mut models = Vec::new();
        append_catalog_model(&mut models, &json!("qwen3:32b"));
        append_catalog_model(&mut models, &json!(1));
        append_catalog_model(&mut models, &json!(0));
        append_catalog_model(&mut models, &json!(true));
        append_catalog_model(&mut models, &json!(false));
        append_catalog_model(&mut models, &json!(null));
        append_catalog_model(&mut models, &json!([1]));
        append_catalog_model(&mut models, &json!({"x": 1}));
        append_catalog_model(&mut models, &json!([]));
        append_catalog_model(&mut models, &json!({}));
        assert_eq!(models, vec!["qwen3:32b", "1", "True", "[1]", "{'x': 1}"]);
    }

    #[test]
    fn dynamic_catalog_environment_and_file_overrides_merge_like_python() {
        let provider = provider_by_key("local").expect("Python local provider should exist");
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!("trading-bot-llm-catalog-{stamp}"));
        std::fs::create_dir_all(&directory).expect("catalog test directory should be creatable");
        let path = directory.join("llm-models.json");
        std::fs::write(
            &path,
            r#"{"providers":{"local":["file-model","qwen3:32b"],"openai":["unused-openai-model"]}}"#,
        )
        .expect("catalog test file should be writable");

        let models = model_suggestions_for_provider_with_sources(
            provider,
            Some("env-model;qwen3:32b,env-model"),
            Some(&path),
        );

        assert!(models.contains(&"qwen3:8b".to_owned()));
        assert!(models.contains(&"env-model".to_owned()));
        assert!(models.contains(&"file-model".to_owned()));
        assert_eq!(
            models.iter().filter(|model| *model == "env-model").count(),
            1
        );
        assert_eq!(
            models.iter().filter(|model| *model == "qwen3:32b").count(),
            1
        );

        std::fs::write(
            &path,
            r#"{"local":null,"providers":{"local":["null-fallback-model"]}}"#,
        )
        .expect("null-precedence catalog fixture should be writable");
        let null_fallback_models =
            model_suggestions_for_provider_with_sources(provider, None, Some(&path));
        assert!(null_fallback_models.contains(&"null-fallback-model".to_owned()));

        std::fs::write(
            &path,
            r#"{"local":"not-a-list","providers":{"local":["ignored-nested-model"]}}"#,
        )
        .expect("invalid-top-level catalog fixture should be writable");
        let invalid_top_level_models =
            model_suggestions_for_provider_with_sources(provider, None, Some(&path));
        assert!(!invalid_top_level_models.contains(&"ignored-nested-model".to_owned()));

        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_dir(directory);
    }

    #[test]
    fn every_generated_python_provider_builds_its_declared_protocol_request() {
        for provider in PYTHON_LLM_PROVIDERS {
            for api_style in provider.api_styles {
                let request = build_llm_chat_request(
                    &LlmConfigInput {
                        llm_provider: provider.key.to_owned(),
                        llm_model: provider.default_model.to_owned(),
                        llm_base_url: provider.default_base_url.to_owned(),
                        llm_api_key: if provider.mode == "cloud" {
                            "parity-test-key".to_owned()
                        } else {
                            String::new()
                        },
                        llm_api_style: (*api_style).to_owned(),
                        ..Default::default()
                    },
                    "Explain risk",
                    "Be concise",
                    None,
                )
                .unwrap_or_else(|error| {
                    panic!(
                        "every Python provider/API style should build ({} / {}): {}",
                        provider.key, api_style, error
                    )
                });
                assert_eq!(request.provider, provider.key);
                assert_eq!(request.protocol, *api_style);
                assert!(request.json.to_string().contains(LLM_EXECUTION_BOUNDARY));
                match *api_style {
                    "openai-chat-completions" => {
                        assert!(request.url.ends_with("/chat/completions"));
                        assert!(request.json["messages"].is_array());
                    }
                    "openai-responses" => {
                        assert!(request.url.ends_with("/responses"));
                        assert!(request.json["instructions"].is_string());
                    }
                    "anthropic-messages" => {
                        assert!(request.url.ends_with("/v1/messages"));
                        assert_eq!(request.headers["x-api-key"], "parity-test-key");
                        assert!(request.json["messages"].is_array());
                    }
                    "gemini-generate-content" => {
                        assert!(request.url.contains(":generateContent?key="));
                        assert!(request.json["contents"].is_array());
                    }
                    protocol => panic!("unhandled Python LLM protocol in Rust: {protocol}"),
                }
            }
        }
    }

    #[test]
    fn kilo_responses_supports_future_options_and_protects_advisory_fields() {
        let request = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "kilo".to_owned(),
                llm_model: "vendor/future-model-v9".to_owned(),
                llm_api_key: "kilo-test-key".to_owned(),
                llm_api_style: "responses".to_owned(),
                llm_reasoning_effort: "turbo".to_owned(),
                llm_speed: "fast".to_owned(),
                llm_context_window: 1_024,
                llm_max_output_tokens: 256,
                llm_verbosity: "high".to_owned(),
                llm_temperature: Some(0.2),
                llm_top_p: Some(0.8),
                llm_timeout_seconds: 45,
                llm_request_options: json!({
                    "seed": 7,
                    "text": {"format": {"type": "text"}},
                    "model": "unsafe-model-override",
                    "input": "unsafe prompt override",
                    "tools": [{"type": "computer"}],
                    "stream": true,
                }),
                ..Default::default()
            },
            "Explain risk.",
            "Be concise.",
            Some(&json!({"config": {"llm": {"large_context": "x".repeat(10_000)}}})),
        )
        .expect("Kilo Responses request should build");

        assert_eq!(request.protocol, "openai-responses");
        assert_eq!(request.url, "https://api.kilo.ai/api/gateway/responses");
        assert_eq!(request.timeout_seconds, 45);
        assert_eq!(request.json["model"], "vendor/future-model-v9");
        assert_eq!(request.json["input"], "Explain risk.");
        assert!(
            request.json["instructions"]
                .as_str()
                .is_some_and(|text| text.contains("context_truncated"))
        );
        assert_eq!(request.json["reasoning"], json!({"effort": "turbo"}));
        assert_eq!(request.json["service_tier"], "priority");
        assert_eq!(request.json["max_output_tokens"], 256);
        assert_eq!(request.json["temperature"], 0.2);
        assert_eq!(request.json["top_p"], 0.8);
        assert_eq!(request.json["text"]["verbosity"], "high");
        assert_eq!(request.json["text"]["format"], json!({"type": "text"}));
        assert_eq!(request.json["seed"], 7);
        assert!(request.json.get("tools").is_none());
        assert!(request.json.get("stream").is_none());
    }

    #[test]
    fn every_generated_python_reasoning_option_is_request_buildable() {
        for provider in PYTHON_LLM_PROVIDERS {
            for effort in provider.reasoning_efforts {
                let request = build_llm_chat_request(
                    &LlmConfigInput {
                        llm_provider: provider.key.to_owned(),
                        llm_model: provider.default_model.to_owned(),
                        llm_base_url: provider.default_base_url.to_owned(),
                        llm_api_key: if provider.mode == "cloud" {
                            "parity-test-key".to_owned()
                        } else {
                            String::new()
                        },
                        llm_reasoning_effort: (*effort).to_owned(),
                        ..Default::default()
                    },
                    "Explain risk",
                    "",
                    None,
                )
                .unwrap_or_else(|error| {
                    panic!(
                        "Python reasoning option should build for {} / {}: {}",
                        provider.key, effort, error
                    )
                });
                assert_eq!(request.provider, provider.key);
            }
        }
    }

    #[test]
    fn provider_specific_reasoning_and_public_endpoint_rules_match_python() {
        let qwen = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "qwen".to_owned(),
                llm_model: "qwen3.7-max".to_owned(),
                llm_reasoning_effort: "enabled".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            None,
        )
        .expect("Qwen request should be buildable");
        assert_eq!(qwen.json["enable_thinking"], true);

        let kimi = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "moonshot".to_owned(),
                llm_model: "kimi-k2.6".to_owned(),
                llm_reasoning_effort: "disabled".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            None,
        )
        .expect("Kimi request should be buildable");
        assert_eq!(kimi.json["thinking"], json!({"type": "disabled"}));

        let error = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "open-source".to_owned(),
                llm_model: "RWKV/rwkv-6-world".to_owned(),
                llm_base_url: "https://llm.example.test/v1".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            None,
        )
        .expect_err("public custom endpoints require explicit consent");
        assert!(error.contains("Public local/custom LLM endpoints are disabled"));

        let request = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "open-source".to_owned(),
                llm_model: "RWKV/rwkv-6-world".to_owned(),
                llm_base_url: "https://llm.example.test/v1".to_owned(),
                llm_allow_public_network: true,
                ..Default::default()
            },
            "Explain risk",
            "",
            Some(&json!({"custom": {"private": "do-not-send"}})),
        )
        .expect("consented public custom endpoint should be buildable");
        let body = request.json.to_string();
        assert!(body.contains("Cloud LLM context minimized"));
        assert!(!body.contains("do-not-send"));
    }

    #[test]
    fn chat_request_serialization_matches_python_reference_cases() {
        let reference: Value = serde_json::from_str(PYTHON_LLM_CHAT_REQUEST_REFERENCE_JSON)
            .expect("Python LLM chat-request fixture should be valid JSON");
        for case in reference["cases"]
            .as_array()
            .expect("Python LLM chat-request fixture should contain cases")
        {
            let config = &case["config"];
            let string_field = |key: &str| {
                config
                    .get(key)
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned()
            };
            let input = LlmConfigInput {
                llm_enabled: config
                    .get("llm_enabled")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                llm_provider: string_field("llm_provider"),
                llm_model: string_field("llm_model"),
                llm_base_url: string_field("llm_base_url"),
                llm_api_key: string_field("llm_api_key"),
                llm_api_key_env: string_field("llm_api_key_env"),
                llm_use_for: string_field("llm_use_for"),
                llm_allow_public_network: config
                    .get("llm_allow_public_network")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                llm_reasoning_effort: string_field("llm_reasoning_effort"),
                ..Default::default()
            };
            let context = case.get("context").filter(|value| !value.is_null());
            let request = build_llm_chat_request(
                &input,
                case["prompt"]
                    .as_str()
                    .expect("Python LLM fixture prompt should be a string"),
                case["system_prompt"]
                    .as_str()
                    .expect("Python LLM fixture system prompt should be a string"),
                context,
            )
            .unwrap_or_else(|error| {
                panic!(
                    "Rust LLM request should match Python case {}: {}",
                    case["name"].as_str().unwrap_or("unknown"),
                    error
                )
            });
            let actual = serde_json::to_value(request)
                .expect("Rust LLM request should serialize for parity comparison");
            assert_eq!(
                actual,
                case["expected"],
                "Rust LLM request should match Python case {}",
                case["name"].as_str().unwrap_or("unknown")
            );
        }
    }

    #[test]
    fn local_context_matches_python_privacy_boundary_and_empty_context_behavior() {
        let local = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "local".to_owned(),
                llm_model: "qwen3:8b".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            Some(&json!({"custom": {"local_secret": "kept-on-loopback"}})),
        )
        .expect("loopback local context should be buildable");
        assert!(local.json.to_string().contains("kept-on-loopback"));

        let local_empty = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "local".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            Some(&json!({})),
        )
        .expect("empty local context should be buildable");
        assert!(
            !local_empty
                .json
                .to_string()
                .contains("Trading context JSON")
        );

        let cloud_empty = build_llm_chat_request(
            &LlmConfigInput {
                llm_provider: "openai".to_owned(),
                llm_api_key: "parity-test-key".to_owned(),
                ..Default::default()
            },
            "Explain risk",
            "",
            Some(&json!({})),
        )
        .expect("empty cloud context should be buildable");
        assert!(
            !cloud_empty
                .json
                .to_string()
                .contains("Cloud LLM context minimized")
        );
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
        for hint in PYTHON_OLLAMA_MODEL_SIZE_HINTS {
            assert_eq!(
                estimate_ollama_model_size_label(hint.model),
                hint.label,
                "Rust Ollama size label should follow the generated Python catalog: {}",
                hint.model
            );
            assert_eq!(
                estimate_ollama_model_size_gb(hint.model),
                hint.size_gb,
                "Rust Ollama size estimate should follow the generated Python catalog: {}",
                hint.model
            );
            if !hint.model.contains(':') {
                assert_eq!(
                    estimate_ollama_model_size_label(format!("{}:latest", hint.model)),
                    hint.label,
                    "Rust Ollama latest-tag lookup should follow the generated Python catalog: {}",
                    hint.model
                );
            }
        }
        assert_eq!(estimate_ollama_model_size_label("qwen3:8b"), "about 5 GB");
        assert_eq!(
            estimate_ollama_model_size_label("qwen2.5:72b"),
            "about 45 GB"
        );
        assert_eq!(
            estimate_ollama_model_size_label("gpt-oss:120b"),
            "about 75 GB"
        );
        assert_eq!(
            estimate_ollama_model_size_label("gemma3:27b"),
            "about 17 GB"
        );
        assert_eq!(estimate_ollama_model_size_gb("gpt-oss:120b"), Some(75.0));
        assert_eq!(estimate_ollama_model_size_gb("custom-local-model"), None);
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
        let reference: Value = serde_json::from_str(PYTHON_LLM_OUTPUT_POLICY_REFERENCE_JSON)
            .expect("Python LLM output-policy fixture should be valid JSON");
        for case in reference["cases"]
            .as_array()
            .expect("Python LLM output-policy fixture should contain cases")
        {
            let text = case["text"]
                .as_str()
                .expect("Python LLM output-policy fixture text should be a string");
            let expected = case["expected_violations"]
                .as_array()
                .expect("Python LLM output-policy fixture violations should be an array")
                .iter()
                .map(|value| {
                    value
                        .as_str()
                        .expect("Python LLM policy violation should be a string")
                        .to_owned()
                })
                .collect::<Vec<_>>();
            assert_eq!(
                llm_output_policy_violations(text),
                expected,
                "Rust LLM output policy should match Python case {}",
                case["name"].as_str().unwrap_or("unknown")
            );
        }
        assert_eq!(
            llm_output_policy_violations(r#"{"action":"place_order","status":"executed"}"#),
            vec![
                "order_execution_claim".to_owned(),
                "direct_order_action".to_owned()
            ]
        );
        assert_eq!(
            llm_output_policy_violations("I executed the trade and disabled stop loss."),
            vec![
                "order_execution_claim".to_owned(),
                "risk_override".to_owned()
            ]
        );
        assert_eq!(
            llm_output_policy_violations(
                "```json\n{\"tool\": \"submit_order\", \"symbol\": \"BTCUSDT\"}\n```"
            ),
            vec!["direct_order_action".to_owned()]
        );
        assert_eq!(
            llm_output_policy_violations(r#"{"operation":"change_leverage"}"#),
            vec!["direct_order_action".to_owned(), "risk_override".to_owned()]
        );
    }
}
