from __future__ import annotations

import os
from urllib.parse import quote, urlencode

import requests

from app.security.redaction import redact_value

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


def _execution_boundary_text() -> str:
    return (
        "Execution boundary: this LLM is advisory only. It must not place orders, "
        "claim that an order was executed, or override deterministic strategy, risk, "
        "take-profit, or stop-loss logic."
    )


def _reasoning_effort(payload: dict[str, object]) -> str:
    return str(payload.get("reasoning_effort") or "default").strip().lower().replace("_", "-")


def _count_mapping_items(value: object) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _minimal_dict(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {key: redact_value(value[key]) for key in keys if key in value}


def _cloud_safe_context(context: dict | None) -> dict[str, object] | None:
    if not isinstance(context, dict) or not context:
        return None
    runtime = context.get("runtime") if isinstance(context.get("runtime"), dict) else {}
    status = context.get("status") if isinstance(context.get("status"), dict) else {}
    execution = context.get("execution") if isinstance(context.get("execution"), dict) else {}
    config = context.get("config") if isinstance(context.get("config"), dict) else {}
    portfolio = context.get("portfolio") if isinstance(context.get("portfolio"), dict) else {}
    logs = context.get("logs") if isinstance(context.get("logs"), list) else []
    return {
        "privacy_notice": "Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.",
        "runtime": _minimal_dict(runtime, ("phase", "control_plane")),
        "status": _minimal_dict(status, ("lifecycle_phase", "runtime_active", "active_engine_count")),
        "execution": _minimal_dict(execution, ("state", "workload_kind", "active_engine_count", "last_action")),
        "config_summary": {
            "mode": redact_value(config.get("mode")),
            "selected_exchange": redact_value(config.get("selected_exchange")),
            "account_type": redact_value(config.get("account_type")),
            "symbol_count": _count_mapping_items(config.get("symbols")),
            "interval_count": _count_mapping_items(config.get("intervals")),
            "llm": redact_value(config.get("llm")) if isinstance(config.get("llm"), dict) else {},
            "raw_config_redacted": True,
        },
        "portfolio_summary": {
            "open_position_count": _count_mapping_items(portfolio.get("open_position_records")),
            "closed_position_count": _count_mapping_items(portfolio.get("closed_position_records")),
            "active_pnl": redact_value(portfolio.get("active_pnl")),
            "closed_pnl": redact_value(portfolio.get("closed_pnl")),
            "position_records_redacted": True,
        },
        "logs": {
            "count": len(logs),
            "redacted": True,
        },
    }


def _context_for_provider(context: dict | None, *, mode: str) -> dict | None:
    if str(mode or "").strip().lower() == "cloud":
        return _cloud_safe_context(context)
    return context


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
    mode = str(payload["mode"])
    base_url = str(payload["base_url"])
    model = str(payload["model"])
    reasoning_effort = _reasoning_effort(payload)
    context_for_request = _context_for_provider(context, mode=mode)
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
            {"role": "system", "content": _execution_boundary_text()},
            *_system_message(system_prompt),
            {"role": "user", "content": user_prompt},
        ]
        if context_for_request:
            messages.insert(
                len(messages) - 1,
                {"role": "system", "content": f"Trading context JSON: {context_for_request}"},
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
        system_parts = [_execution_boundary_text()]
        if system_prompt:
            system_parts.append(str(system_prompt))
        body["system"] = "\n\n".join(system_parts)
        if context_for_request:
            body["messages"].insert(0, {"role": "user", "content": f"Trading context JSON: {context_for_request}"})
        body.update(_anthropic_thinking_body(reasoning_effort))
    elif protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        if not api_key:
            raise ValueError("Google Gemini requires an API key.")
        query = urlencode({"key": api_key})
        encoded_model = quote(model, safe="")
        url = f"{_join_url(base_url, f'models/{encoded_model}:generateContent')}?{query}"
        parts: list[dict[str, str]] = []
        parts.append({"text": _execution_boundary_text()})
        if system_prompt:
            parts.append({"text": str(system_prompt)})
        if context_for_request:
            parts.append({"text": f"Trading context JSON: {context_for_request}"})
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
        "execution_policy": payload.get("execution_policy"),
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


def llm_output_policy_violations(text: str) -> tuple[str, ...]:
    lower = str(text or "").strip().lower()
    if not lower:
        return ()
    checks = (
        (
            "order_execution_claim",
            (
                "order executed",
                "trade executed",
                "i executed",
                "i placed an order",
                "i submitted an order",
                "submitted the order",
            ),
        ),
        (
            "direct_order_action",
            (
                '"action":"place_order"',
                '"action": "place_order"',
                '"action":"submit_order"',
                '"action": "submit_order"',
                "place_order",
                "submit_order",
                "execute_order",
            ),
        ),
        (
            "risk_override",
            (
                "disable stop loss",
                "disabled stop loss",
                "override risk",
                "set leverage to",
                "changed leverage",
            ),
        ),
    )
    violations = []
    for label, phrases in checks:
        if any(phrase in lower for phrase in phrases):
            violations.append(label)
    return tuple(violations)


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
            "execution_policy": request_payload.get("execution_policy"),
            "output_policy": {
                "advisory_only": True,
                "violations": [],
                "blocked": False,
            },
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
            "execution_policy": request_payload.get("execution_policy"),
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
    text = _extract_response_text(protocol, payload)
    violations = llm_output_policy_violations(text)
    return {
        "ok": not bool(violations),
        "dry_run": False,
        "status_code": response.status_code,
        "provider": request_payload.get("provider"),
        "execution_policy": request_payload.get("execution_policy"),
        "output_policy": {
            "advisory_only": True,
            "violations": list(violations),
            "blocked": bool(violations),
        },
        "text": text,
        "raw": payload,
    }
