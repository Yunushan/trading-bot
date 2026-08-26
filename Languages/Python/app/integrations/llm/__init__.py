from __future__ import annotations

from .providers import (
    build_llm_config_payload,
    llm_provider_choices,
    list_llm_provider_specs,
    normalize_llm_provider_key,
    update_llm_config,
)

__all__ = [
    "build_llm_chat_request",
    "build_llm_config_payload",
    "call_llm",
    "discover_llm_models",
    "llm_provider_choices",
    "list_llm_provider_specs",
    "normalize_llm_provider_key",
    "update_llm_config",
]


def __getattr__(name: str):
    if name in {"build_llm_chat_request", "call_llm"}:
        from .clients import build_llm_chat_request, call_llm

        globals()["build_llm_chat_request"] = build_llm_chat_request
        globals()["call_llm"] = call_llm
        return globals()[name]
    if name == "discover_llm_models":
        from .discovery import discover_llm_models

        globals()["discover_llm_models"] = discover_llm_models
        return discover_llm_models
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
