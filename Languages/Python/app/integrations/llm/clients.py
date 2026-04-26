from __future__ import annotations

import os
from urllib.parse import quote, urlencode

import requests

from .providers import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    OPENAI_COMPATIBLE_PROTOCOL,
    build_llm_config_payload,
)


def _join_url(base_url: str, path: str) -> str:
    return f"{str(base_url or '').rstrip('/')}/{str(path or '').lstrip('/')}"


def _api_key_for_config(config: dict[str, object], api_key_env: str) -> str:
    inline_key = str(config.get("llm_api_key") or "").strip()
    if inline_key:
        return inline_key
    return str(os.environ.get(api_key_env) or "").strip()


def _system_message(system_prompt: str) -> list[dict[str, str]]:
    text = str(system_prompt or "").strip()
    return [{"role": "system", "content": text}] if text else []


def _reasoning_effort(payload: dict[str, object]) -> str:
    return str(payload.get("reasoning_effort") or "default").strip().lower().replace("_", "-")


def _openai_compatible_reasoning_body(provider: str, effort: str) -> dict[str, object]:
    if effort in {"", "default"}:
        return {}
    if provider == "deepseek":
        if effort in {"none", "disabled", "off"}:
            return {"thinking": {"type": "disabled"}}
        body: dict[str, object] = {"thinking": {"type": "enabled"}}
        if effort in {"high", "max", "xhigh", "low", "medium"}:
            body["reasoning_effort"] = "max" if effort in {"max", "xhigh"} else effort
        return body
    return {"reasoning_effort": effort}


def _anthropic_thinking_body(effort: str) -> dict[str, object]:
    if effort in {"", "default"}:
        return {}
    if effort in {"none", "disabled", "off"}:
        return {"thinking": {"type": "disabled"}}
    budgets = {
        "enabled": 2048,
        "low": 2048,
        "medium": 4096,
        "high": 8192,
    }
    budget_tokens = budgets.get(effort)
    if not budget_tokens:
        return {}
    return {
        "max_tokens": max(1024, budget_tokens + 1024),
        "thinking": {"type": "enabled", "budget_tokens": budget_tokens},
    }


def _gemini_generation_config(effort: str, model: str) -> dict[str, object]:
    if effort in {"", "default"}:
        return {}
    thinking_level = "minimal" if effort in {"none", "disabled", "minimal"} else effort
    if str(model or "").startswith("gemini-3-pro") and thinking_level in {"minimal", "medium"}:
        thinking_level = "low" if thinking_level == "minimal" else "high"
    if thinking_level not in {"minimal", "low", "medium", "high"}:
        return {}
    return {"thinkingConfig": {"thinkingLevel": thinking_level}}


def build_llm_chat_request(
    config: dict | None,
    *,
    prompt: str,
    system_prompt: str = "",
    context: dict | None = None,
) -> dict[str, object]:
    payload = build_llm_config_payload(config)
    raw_config = config if isinstance(config, dict) else {}
    provider = str(payload["provider"])
    protocol = str(payload["protocol"])
    base_url = str(payload["base_url"])
    model = str(payload["model"])
    reasoning_effort = _reasoning_effort(payload)
    user_prompt = str(prompt or "").strip()
    if not user_prompt:
        raise ValueError("LLM prompt cannot be empty.")
    if not model:
        raise ValueError(f"Select an LLM model before calling {payload['provider_label']}.")

    api_key = _api_key_for_config(raw_config, str(payload["api_key_env"]))
    headers: dict[str, str] = {"Content-Type": "application/json"}
    body: dict[str, object]
    url: str

    if protocol == OPENAI_COMPATIBLE_PROTOCOL:
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = _join_url(base_url, "chat/completions")
        messages = [
            *_system_message(system_prompt),
            {"role": "user", "content": user_prompt},
        ]
        if context:
            messages.insert(
                len(messages) - 1,
                {"role": "system", "content": f"Trading context JSON: {context}"},
            )
        body = {"model": model, "messages": messages}
        body.update(_openai_compatible_reasoning_body(provider, reasoning_effort))
    elif protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        if not api_key:
            raise ValueError("Anthropic Claude requires an API key.")
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        url = _join_url(base_url, "v1/messages")
        body = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            body["system"] = str(system_prompt)
        if context:
            body["messages"].insert(0, {"role": "user", "content": f"Trading context JSON: {context}"})
        body.update(_anthropic_thinking_body(reasoning_effort))
    elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        if not api_key:
            raise ValueError("Google Gemini requires an API key.")
        query = urlencode({"key": api_key})
        encoded_model = quote(model, safe="")
        url = f"{_join_url(base_url, f'models/{encoded_model}:generateContent')}?{query}"
        parts: list[dict[str, str]] = []
        if system_prompt:
            parts.append({"text": str(system_prompt)})
        if context:
            parts.append({"text": f"Trading context JSON: {context}"})
        parts.append({"text": user_prompt})
        body = {"contents": [{"parts": parts}]}
        generation_config = _gemini_generation_config(reasoning_effort, model)
        if generation_config:
            body["generationConfig"] = generation_config
    else:
        raise ValueError(f"Unsupported LLM protocol for provider {provider}: {protocol}")

    return {
        "provider": provider,
        "mode": str(payload["mode"]),
        "protocol": protocol,
        "url": url,
        "headers": headers,
        "json": body,
    }


def _sanitize_request_for_display(request_payload: dict[str, object]) -> dict[str, object]:
    sanitized = dict(request_payload)
    headers = dict(sanitized.get("headers") or {})
    for key in list(headers):
        if key.lower() in {"authorization", "x-api-key"}:
            headers[key] = "********"
    sanitized["headers"] = headers
    url = str(sanitized.get("url") or "")
    if "key=" in url:
        sanitized["url"] = url.split("key=", 1)[0] + "key=********"
    return sanitized


def _extract_response_text(protocol: str, payload: object) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    if protocol == OPENAI_COMPATIBLE_PROTOCOL:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    return str(message.get("content") or "").strip()
    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        content = payload.get("content")
        if isinstance(content, list):
            text_parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "\n".join(part for part in text_parts if part).strip()
    if protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        candidates = payload.get("candidates")
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list):
                return "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    return ""


def call_llm(
    config: dict | None,
    *,
    prompt: str,
    system_prompt: str = "",
    context: dict | None = None,
    dry_run: bool = True,
    timeout: float = 30.0,
) -> dict[str, object]:
    request_payload = build_llm_chat_request(
        config,
        prompt=prompt,
        system_prompt=system_prompt,
        context=context,
    )
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "request": _sanitize_request_for_display(request_payload),
            "text": "",
        }
    headers = dict(request_payload["headers"])
    if request_payload.get("mode") == "cloud" and not (
        headers.get("Authorization") or headers.get("x-api-key")
    ):
        return {
            "ok": False,
            "dry_run": False,
            "error": "Cloud LLM provider requires an API key or configured API key environment variable.",
            "provider": request_payload.get("provider"),
        }

    response = requests.post(
        str(request_payload["url"]),
        headers=headers,
        json=request_payload["json"],
        timeout=max(1.0, float(timeout or 30.0)),
    )
    try:
        payload = response.json()
    except Exception:
        payload = {"text": response.text}
    if response.status_code >= 400:
        return {
            "ok": False,
            "dry_run": False,
            "status_code": response.status_code,
            "error": payload,
        }
    protocol = str(request_payload.get("protocol") or "")
    return {
        "ok": True,
        "dry_run": False,
        "status_code": response.status_code,
        "provider": request_payload.get("provider"),
        "text": _extract_response_text(protocol, payload),
        "raw": payload,
    }
