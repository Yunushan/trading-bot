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
    llm_reasoning_effort: str = "default"

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
            "llm_reasoning_effort": self.llm_reasoning_effort,
        }
