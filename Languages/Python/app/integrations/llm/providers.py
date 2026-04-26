from __future__ import annotations

import copy
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class LLMProviderSpec:
    key: str
    label: str
    mode: str
    protocol: str
    default_base_url: str
    default_model: str
    api_key_env: str
    model_suggestions: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ("default",)
    default_reasoning_effort: str = "default"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["model_suggestions"] = list(self.model_suggestions)
        payload["reasoning_efforts"] = list(self.reasoning_efforts)
        payload["notes"] = list(self.notes)
        return payload


OPENAI_COMPATIBLE_PROTOCOL = "openai-chat-completions"
ANTHROPIC_MESSAGES_PROTOCOL = "anthropic-messages"
GEMINI_GENERATE_CONTENT_PROTOCOL = "gemini-generate-content"

_PROVIDER_SPECS: tuple[LLMProviderSpec, ...] = (
    LLMProviderSpec(
        key="openai",
        label="OpenAI / ChatGPT",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-5.5",
        api_key_env="OPENAI_API_KEY",
        model_suggestions=(
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
        ),
        reasoning_efforts=("default", "none", "minimal", "low", "medium", "high", "xhigh"),
        notes=("Uses the OpenAI-compatible chat completions endpoint.",),
    ),
    LLMProviderSpec(
        key="anthropic",
        label="Anthropic Claude",
        mode="cloud",
        protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        default_base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-5-20250929",
        api_key_env="ANTHROPIC_API_KEY",
        model_suggestions=(
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
        ),
        reasoning_efforts=("default", "disabled", "enabled", "low", "medium", "high"),
        notes=("Uses the Anthropic messages endpoint with the 2023-06-01 API version header.",),
    ),
    LLMProviderSpec(
        key="gemini",
        label="Google Gemini",
        mode="cloud",
        protocol=GEMINI_GENERATE_CONTENT_PROTOCOL,
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-3-flash-preview",
        api_key_env="GEMINI_API_KEY",
        model_suggestions=(
            "gemini-3-flash-preview",
            "gemini-3-pro-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ),
        reasoning_efforts=("default", "minimal", "low", "medium", "high"),
        notes=("Uses the Gemini generateContent endpoint.",),
    ),
    LLMProviderSpec(
        key="deepseek",
        label="DeepSeek",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        model_suggestions=("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"),
        reasoning_efforts=("default", "disabled", "enabled", "high", "max"),
        notes=("DeepSeek documents an OpenAI-compatible chat completions surface.",),
    ),
    LLMProviderSpec(
        key="grok",
        label="xAI Grok",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.x.ai/v1",
        default_model="grok-4.20",
        api_key_env="XAI_API_KEY",
        model_suggestions=(
            "grok-4.20",
            "grok-4.20-reasoning",
            "grok-4.20-non-reasoning",
            "grok-4-fast-reasoning",
            "grok-4-fast-non-reasoning",
        ),
        reasoning_efforts=("default", "low", "medium", "high"),
        notes=("xAI documents OpenAI-compatible chat completions at /v1/chat/completions.",),
    ),
    LLMProviderSpec(
        key="qwen",
        label="Alibaba Qwen / DashScope",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3-max",
        api_key_env="DASHSCOPE_API_KEY",
        model_suggestions=(
            "qwen3-max",
            "qwen3-max-2026-01-23",
            "qwen3-max-preview",
            "qwen3.5-plus",
            "qwen3.5-flash",
        ),
        reasoning_efforts=("default", "low", "medium", "high"),
        notes=("DashScope provides OpenAI-compatible endpoints for Qwen models.",),
    ),
    LLMProviderSpec(
        key="local",
        label="Local / Custom OpenAI-Compatible",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:11434/v1",
        default_model="llama3.3",
        api_key_env="LOCAL_LLM_API_KEY",
        model_suggestions=("llama3.3", "qwen3", "mistral-small3.2", "gpt-oss:20b", "custom-model"),
        reasoning_efforts=("default", "none", "low", "medium", "high", "xhigh"),
        notes=("Use this for local LLM servers or private/public IP endpoints.",),
    ),
)

_PROVIDER_BY_KEY = {provider.key: provider for provider in _PROVIDER_SPECS}
_PROVIDER_ALIASES = {
    "": "openai",
    "chatgpt": "openai",
    "openai-chatgpt": "openai",
    "claude": "anthropic",
    "anthropic-claude": "anthropic",
    "google": "gemini",
    "google-gemini": "gemini",
    "xai": "grok",
    "xai-grok": "grok",
    "dashscope": "qwen",
    "alibaba": "qwen",
    "alibaba-qwen": "qwen",
    "ollama": "local",
    "local-openai": "local",
    "local-openai-compatible": "local",
    "custom": "local",
}

_LLM_CONFIG_KEYS = {
    "llm_enabled",
    "llm_provider",
    "llm_model",
    "llm_base_url",
    "llm_api_key",
    "llm_api_key_env",
    "llm_use_for",
    "llm_allow_public_network",
    "llm_reasoning_effort",
}


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def normalize_llm_provider_key(value: str | None) -> str:
    raw_key = str(value or "").strip().lower().replace("_", "-")
    normalized = _PROVIDER_ALIASES.get(raw_key, raw_key)
    return normalized if normalized in _PROVIDER_BY_KEY else "openai"


def llm_provider_spec_for_key(value: str | None) -> LLMProviderSpec:
    return _PROVIDER_BY_KEY[normalize_llm_provider_key(value)]


def list_llm_provider_specs() -> list[dict[str, object]]:
    return [provider.to_dict() for provider in _PROVIDER_SPECS]


def _masked_key_present(config: dict[str, object], env_name: str) -> bool:
    inline_key = str(config.get("llm_api_key") or "").strip()
    env_key = str(os.environ.get(env_name) or "").strip()
    return bool(inline_key or env_key)


def _normalize_reasoning_effort(provider: LLMProviderSpec, value: object) -> str:
    raw_value = str(value or "").strip().lower().replace("_", "-")
    efforts = tuple(str(item).strip().lower() for item in provider.reasoning_efforts if str(item).strip())
    if not efforts:
        return "default"
    default_effort = str(provider.default_reasoning_effort or efforts[0]).strip().lower() or efforts[0]
    aliases = {
        "": default_effort,
        "auto": "default",
        "off": "none" if "none" in efforts else "disabled",
        "no": "none" if "none" in efforts else "disabled",
        "false": "none" if "none" in efforts else "disabled",
        "extra-high": "xhigh",
        "extra_high": "xhigh",
    }
    normalized = aliases.get(raw_value, raw_value)
    return normalized if normalized in efforts else default_effort


def build_llm_config_payload(config: dict | None) -> dict[str, object]:
    cfg = config if isinstance(config, dict) else {}
    provider = llm_provider_spec_for_key(str(cfg.get("llm_provider") or "openai"))
    api_key_env = str(cfg.get("llm_api_key_env") or provider.api_key_env).strip() or provider.api_key_env
    base_url = str(cfg.get("llm_base_url") or provider.default_base_url).strip() or provider.default_base_url
    model = str(cfg.get("llm_model") or provider.default_model).strip()
    reasoning_effort = _normalize_reasoning_effort(provider, cfg.get("llm_reasoning_effort"))
    return {
        "enabled": _coerce_bool(cfg.get("llm_enabled"), False),
        "provider": provider.key,
        "provider_label": provider.label,
        "mode": provider.mode,
        "protocol": provider.protocol,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "api_key_present": _masked_key_present(cfg, api_key_env),
        "use_for": str(cfg.get("llm_use_for") or "advisory").strip() or "advisory",
        "allow_public_network": _coerce_bool(cfg.get("llm_allow_public_network"), False),
        "reasoning_effort": reasoning_effort,
        "default_reasoning_effort": provider.default_reasoning_effort,
        "reasoning_efforts": list(provider.reasoning_efforts),
        "model_suggestions": list(provider.model_suggestions),
        "notes": list(provider.notes),
    }


def update_llm_config(config: dict | None, patch: dict | None) -> dict[str, object]:
    updated = copy.deepcopy(config if isinstance(config, dict) else {})
    values = patch if isinstance(patch, dict) else {}
    for key, value in values.items():
        if key not in _LLM_CONFIG_KEYS:
            continue
        if key == "llm_provider":
            updated[key] = normalize_llm_provider_key(str(value or ""))
        elif key in {"llm_enabled", "llm_allow_public_network"}:
            updated[key] = _coerce_bool(value, False)
        elif key == "llm_reasoning_effort":
            provider = llm_provider_spec_for_key(str(updated.get("llm_provider") or "openai"))
            updated[key] = _normalize_reasoning_effort(provider, value)
        elif key == "llm_api_key" and str(value or "").strip() in {"", "********"}:
            updated.pop(key, None)
        else:
            updated[key] = str(value or "").strip()
    if "llm_provider" not in updated:
        updated["llm_provider"] = "openai"
    if "llm_reasoning_effort" in updated:
        provider = llm_provider_spec_for_key(str(updated.get("llm_provider") or "openai"))
        updated["llm_reasoning_effort"] = _normalize_reasoning_effort(provider, updated.get("llm_reasoning_effort"))
    return updated
