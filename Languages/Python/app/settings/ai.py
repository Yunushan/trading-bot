from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AISettings:
    llm_enabled: bool = False
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_api_key_env: str = ""
    llm_use_for: str = "advisory"
    llm_allow_public_network: bool = False
    llm_api_style: str = "provider-default"
    llm_reasoning_effort: str = "default"
    llm_speed: str = "default"
    llm_context_window: int = 0
    llm_max_output_tokens: int = 0
    llm_verbosity: str = "default"
    llm_temperature: float | None = None
    llm_top_p: float | None = None
    llm_timeout_seconds: int = 30
    llm_request_options: dict[str, object] | None = None

    def to_config_dict(self) -> dict[str, object]:
        return {
            "llm_enabled": self.llm_enabled,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "llm_api_key": self.llm_api_key,
            "llm_api_key_env": self.llm_api_key_env,
            "llm_use_for": self.llm_use_for,
            "llm_allow_public_network": self.llm_allow_public_network,
            "llm_api_style": self.llm_api_style,
            "llm_reasoning_effort": self.llm_reasoning_effort,
            "llm_speed": self.llm_speed,
            "llm_context_window": self.llm_context_window,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "llm_verbosity": self.llm_verbosity,
            "llm_temperature": self.llm_temperature,
            "llm_top_p": self.llm_top_p,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "llm_request_options": dict(self.llm_request_options or {}),
        }
