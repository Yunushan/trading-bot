use trading_bot_contracts::AppIdentity;

pub fn app_banner(shell: &str) -> String {
    format!("Trading Bot Rust scaffold -> {shell}")
}

pub fn default_identity(shell: &str) -> AppIdentity {
    AppIdentity::new(shell)
}

pub fn supported_frameworks() -> &'static [&'static str] {
    &[
        "Tauri",
        "Slint",
        "egui",
        "Iced",
        "Dioxus Desktop",
    ]
}

pub struct LlmProviderOption {
    pub key: &'static str,
    pub label: &'static str,
    pub mode: &'static str,
    pub default_base_url: &'static str,
    pub api_key_env: &'static str,
    pub model_suggestions: &'static [&'static str],
    pub reasoning_efforts: &'static [&'static str],
}

pub fn llm_provider_options() -> &'static [LlmProviderOption] {
    &[
        LlmProviderOption {
            key: "openai",
            label: "OpenAI / ChatGPT",
            mode: "cloud",
            default_base_url: "https://api.openai.com/v1",
            api_key_env: "OPENAI_API_KEY",
            model_suggestions: &[
                "gpt-5.5",
                "gpt-5.4",
                "gpt-5.4-mini",
                "gpt-5.4-nano",
                "gpt-5.3-chat-latest",
                "gpt-5.3-codex",
                "gpt-5.2",
                "gpt-5.2-codex",
                "gpt-5.2-chat-latest",
                "gpt-5.2-pro",
                "gpt-5.1",
                "gpt-5-codex",
                "gpt-5-mini",
                "gpt-5-nano",
            ],
            reasoning_efforts: &[
                "default", "none", "minimal", "low", "medium", "high", "xhigh",
            ],
        },
        LlmProviderOption {
            key: "anthropic",
            label: "Anthropic Claude",
            mode: "cloud",
            default_base_url: "https://api.anthropic.com",
            api_key_env: "ANTHROPIC_API_KEY",
            model_suggestions: &[
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5-20251001",
                "claude-opus-4-1-20250805",
                "claude-opus-4-20250514",
                "claude-sonnet-4-20250514",
                "claude-sonnet-4-5",
                "claude-haiku-4-5",
                "claude-opus-4-1",
                "claude-opus-4-0",
                "claude-sonnet-4-0",
            ],
            reasoning_efforts: &[
                "default", "disabled", "enabled", "low", "medium", "high",
            ],
        },
        LlmProviderOption {
            key: "gemini",
            label: "Google Gemini",
            mode: "cloud",
            default_base_url: "https://generativelanguage.googleapis.com/v1beta",
            api_key_env: "GEMINI_API_KEY",
            model_suggestions: &[
                "gemini-3-flash-preview",
                "gemini-3-pro-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ],
            reasoning_efforts: &["default", "minimal", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "deepseek",
            label: "DeepSeek",
            mode: "cloud",
            default_base_url: "https://api.deepseek.com",
            api_key_env: "DEEPSEEK_API_KEY",
            model_suggestions: &[
                "deepseek-v4-flash",
                "deepseek-v4-pro",
                "deepseek-chat",
                "deepseek-reasoner",
            ],
            reasoning_efforts: &["default", "disabled", "enabled", "high", "max"],
        },
        LlmProviderOption {
            key: "grok",
            label: "xAI Grok",
            mode: "cloud",
            default_base_url: "https://api.x.ai/v1",
            api_key_env: "XAI_API_KEY",
            model_suggestions: &[
                "grok-4.20",
                "grok-4.20-reasoning",
                "grok-4.20-non-reasoning",
                "grok-4-fast-reasoning",
                "grok-4-fast-non-reasoning",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "qwen",
            label: "Alibaba Qwen / DashScope",
            mode: "cloud",
            default_base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env: "DASHSCOPE_API_KEY",
            model_suggestions: &[
                "qwen3-max",
                "qwen3-max-2026-01-23",
                "qwen3-max-preview",
                "qwen3.5-plus",
                "qwen3.5-flash",
            ],
            reasoning_efforts: &["default", "low", "medium", "high"],
        },
        LlmProviderOption {
            key: "local",
            label: "Local / Custom OpenAI-Compatible",
            mode: "local",
            default_base_url: "http://127.0.0.1:11434/v1",
            api_key_env: "LOCAL_LLM_API_KEY",
            model_suggestions: &[
                "llama3.3",
                "qwen3",
                "mistral-small3.2",
                "gpt-oss:20b",
                "custom-model",
            ],
            reasoning_efforts: &["default", "none", "low", "medium", "high", "xhigh"],
        },
    ]
}
