from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


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
LLM_PROVIDER_CATALOG_REVISION = "2026-05-11"
LLM_MODEL_CATALOG_PATH_ENV = "BOT_LLM_MODEL_CATALOG_PATH"

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
            "gpt-5.5-2026-04-23",
            "gpt-5.5-pro",
            "gpt-5.5-pro-2026-04-23",
            "gpt-5.4",
            "gpt-5.4-2026-03-05",
            "gpt-5.4-pro",
            "gpt-5.4-pro-2026-03-05",
            "gpt-5.4-mini",
            "gpt-5.4-mini-2026-03-17",
            "gpt-5.4-nano",
            "gpt-5.4-nano-2026-03-17",
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
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
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
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-opus-4-5",
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
            "gemini-3.1-pro-preview",
            "gemini-3.1-pro-preview-customtools",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-preview-09-2025",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite-preview-09-2025",
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
        key="mistral",
        label="Mistral AI",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.mistral.ai/v1",
        default_model="mistral-small-latest",
        api_key_env="MISTRAL_API_KEY",
        model_suggestions=(
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "codestral-latest",
            "open-mistral-nemo",
        ),
        reasoning_efforts=("default", "low", "medium", "high"),
        notes=("Mistral exposes an OpenAI-compatible chat completions API.",),
    ),
    LLMProviderSpec(
        key="grok",
        label="xAI Grok",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.x.ai/v1",
        default_model="grok-4.3",
        api_key_env="XAI_API_KEY",
        model_suggestions=(
            "grok-4.3",
            "grok-4.3-latest",
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
        default_model="qwen3.6-plus",
        api_key_env="DASHSCOPE_API_KEY",
        model_suggestions=(
            "qwen3.6-max-preview",
            "qwen3.6-plus",
            "qwen3.6-plus-2026-04-02",
            "qwen3.6-flash",
            "qwen3.6-flash-2026-04-16",
            "qwen3-max",
            "qwen3-max-2026-01-23",
            "qwen3-max-2025-09-23",
            "qwen3-max-preview",
            "qwen3.5-plus",
            "qwen3.5-plus-2026-02-15",
            "qwen3.5-flash",
            "qwen3.5-flash-2026-02-23",
            "qwen3-coder-plus",
            "qwen3-coder-flash",
            "qwen-plus-us",
            "qwen-flash-us",
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
        default_model="qwen3:8b",
        api_key_env="LOCAL_LLM_API_KEY",
        model_suggestions=(
            "qwen3:0.6b",
            "qwen3:1.7b",
            "qwen3:4b",
            "qwen3:8b",
            "qwen3:14b",
            "qwen3:30b-a3b",
            "qwen3:32b",
            "qwen3",
            "gpt-oss:20b",
            "gpt-oss:latest",
            "llama3.3",
            "llama3.1:8b",
            "llama3.2:3b",
            "llama3.2:1b",
            "mistral-small3.2",
            "deepseek-r1:8b",
            "gemma3:4b",
            "custom-model",
        ),
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
    "mistral-ai": "mistral",
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


def _extra_model_suggestions(provider_key: str) -> tuple[str, ...]:
    env_name = f"BOT_LLM_EXTRA_MODELS_{str(provider_key or '').upper().replace('-', '_')}"
    raw = str(os.environ.get(env_name) or "").strip()
    if not raw:
        return ()
    values = []
    for item in raw.replace(";", ",").split(","):
        text = item.strip()
        if text and text not in values:
            values.append(text)
    return tuple(values)


def _catalog_path() -> Path:
    raw = str(os.environ.get(LLM_MODEL_CATALOG_PATH_ENV) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("~/.trading-bot/llm-models.json").expanduser()


def _file_model_suggestions(provider_key: str) -> tuple[str, ...]:
    path = _catalog_path()
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    raw_models = payload.get(provider_key)
    if raw_models is None:
        raw_models = payload.get("providers", {}).get(provider_key) if isinstance(payload.get("providers"), dict) else None
    if not isinstance(raw_models, list):
        return ()
    values: list[str] = []
    for item in raw_models:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return tuple(values)


def _model_suggestions_for_provider(provider: LLMProviderSpec) -> list[str]:
    suggestions = list(provider.model_suggestions)
    for model in _extra_model_suggestions(provider.key):
        if model not in suggestions:
            suggestions.append(model)
    for model in _file_model_suggestions(provider.key):
        if model not in suggestions:
            suggestions.append(model)
    return suggestions


def list_llm_provider_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for provider in _PROVIDER_SPECS:
        payload = provider.to_dict()
        payload["model_suggestions"] = _model_suggestions_for_provider(provider)
        payload["catalog_revision"] = LLM_PROVIDER_CATALOG_REVISION
        payload["custom_models_env"] = f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}"
        payload["custom_models_path_env"] = LLM_MODEL_CATALOG_PATH_ENV
        payload["catalog_path"] = str(_catalog_path())
        payload["catalog_note"] = (
            "Static defaults can drift; add local overrides with custom_models_env or custom_models_path_env."
        )
        specs.append(payload)
    return specs


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
        "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
        "catalog_path": str(_catalog_path()),
        "custom_models_env": f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}",
        "custom_models_path_env": LLM_MODEL_CATALOG_PATH_ENV,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "api_key_present": _masked_key_present(cfg, api_key_env),
        "use_for": str(cfg.get("llm_use_for") or "advisory").strip() or "advisory",
        "allow_public_network": _coerce_bool(cfg.get("llm_allow_public_network"), False),
        "reasoning_effort": reasoning_effort,
        "default_reasoning_effort": provider.default_reasoning_effort,
        "reasoning_efforts": list(provider.reasoning_efforts),
        "model_suggestions": _model_suggestions_for_provider(provider),
        "notes": list(provider.notes),
        "execution_policy": {
            "advisory_only": True,
            "can_execute_orders": False,
            "owner": "strategy_and_risk_runtime",
        },
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
