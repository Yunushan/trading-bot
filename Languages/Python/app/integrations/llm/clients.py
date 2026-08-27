from __future__ import annotations

import copy
import ipaddress
import json
import os
from urllib.parse import quote, urlencode, urlsplit

import requests

from app.security.redaction import redact_text, redact_value

from .providers import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    OPENAI_COMPATIBLE_PROTOCOL,
    OPENAI_RESPONSES_PROTOCOL,
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


def _context_json_text(context: dict) -> str:
    """Serialize the already-redacted context consistently across native clients."""

    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bounded_context_json_text(
    context: dict,
    *,
    context_window: int,
    max_output_tokens: int,
    prompt: str,
    system_prompt: str,
) -> str:
    serialized = _context_json_text(context)
    if context_window <= 0:
        return serialized
    fixed_characters = len(prompt) + len(system_prompt) + len(_execution_boundary_text())
    fixed_tokens = max(256, (fixed_characters + 3) // 4)
    output_reserve = max_output_tokens if max_output_tokens > 0 else min(4096, max(256, context_window // 8))
    available_tokens = max(0, context_window - fixed_tokens - output_reserve)
    character_budget = available_tokens * 4
    if len(serialized) <= character_budget:
        return serialized
    if character_budget < 160:
        return json.dumps(
            {
                "context_truncated": True,
                "original_characters": len(serialized),
                "excerpt": "",
            },
            separators=(",", ":"),
        )
    excerpt_budget = max(32, character_budget - 120)
    prefix_length = max(16, excerpt_budget * 2 // 3)
    suffix_length = max(16, excerpt_budget - prefix_length)
    return json.dumps(
        {
            "context_truncated": True,
            "original_characters": len(serialized),
            "prefix": serialized[:prefix_length],
            "suffix": serialized[-suffix_length:],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


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


def _context_for_provider(context: dict | None, *, mode: str, allow_public_network: bool = False) -> dict | None:
    if str(mode or "").strip().lower() == "cloud" or bool(allow_public_network):
        return _cloud_safe_context(context)
    return context


def _base_url_uses_public_network(base_url: str) -> bool:
    host = str(urlsplit(str(base_url or "").strip()).hostname or "").strip()
    if not host:
        return False
    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local)


def _openai_compatible_reasoning_body(provider: str, model: str, effort: str) -> dict[str, object]:
    if effort in {"", "default"}:
        return {}
    if provider == "deepseek":
        if effort in {"none", "disabled", "off"}:
            return {"thinking": {"type": "disabled"}}
        body: dict[str, object] = {"thinking": {"type": "enabled"}}
        if effort in {"high", "max", "xhigh", "low", "medium"}:
            body["reasoning_effort"] = "max" if effort in {"max", "xhigh"} else effort
        return body
    if provider == "qwen":
        return {"enable_thinking": effort not in {"none", "disabled", "off"}}
    if provider == "moonshot":
        normalized_model = str(model or "").strip().lower()
        if normalized_model.startswith("kimi-k3"):
            return {"reasoning_effort": "max"} if effort == "max" else {}
        if normalized_model.startswith(("kimi-k2.5", "kimi-k2.6")):
            if effort in {"none", "disabled", "off"}:
                return {"thinking": {"type": "disabled"}}
            if effort in {"enabled", "low", "medium", "high", "max", "xhigh"}:
                return {"thinking": {"type": "enabled"}}
            return {}
        # Kimi K2.7 Code always reasons and rejects a thinking override.
        return {}
    return {"reasoning_effort": effort}


def _anthropic_thinking_body(effort: str, *, max_output_tokens: int = 0) -> dict[str, object]:
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
    if max_output_tokens > 0:
        budget_tokens = min(budget_tokens, max(0, max_output_tokens - 1))
        if budget_tokens <= 0:
            return {"max_tokens": max_output_tokens}
        return {
            "max_tokens": max_output_tokens,
            "thinking": {"type": "enabled", "budget_tokens": budget_tokens},
        }
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


_RESERVED_REQUEST_OPTION_KEYS = {
    "contents",
    "functions",
    "input",
    "instructions",
    "messages",
    "model",
    "stream",
    "system",
    "tool_choice",
    "tools",
}


def _request_options(payload: dict[str, object]) -> dict[str, object]:
    options = payload.get("request_options")
    if not isinstance(options, dict):
        return {}
    return {
        str(key): copy.deepcopy(value)
        for key, value in options.items()
        if str(key).strip().lower() not in _RESERVED_REQUEST_OPTION_KEYS
    }


def _merge_mapping(target: dict[str, object], values: dict[str, object]) -> None:
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            nested = dict(target[key])
            _merge_mapping(nested, value)
            target[key] = nested
        else:
            target[key] = copy.deepcopy(value)


def _service_tier_for_speed(speed: str) -> str:
    normalized = str(speed or "default").strip().lower().replace("_", "-")
    aliases = {
        "balanced": "default",
        "economy": "flex",
        "fast": "priority",
        "quality": "default",
    }
    return aliases.get(normalized, normalized)


def _uses_modern_openai_output_limit(provider: str, model: str) -> bool:
    if provider != "openai":
        return False
    normalized = str(model or "").strip().lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))


def _apply_configured_request_options(
    body: dict[str, object],
    *,
    payload: dict[str, object],
    provider: str,
    model: str,
    protocol: str,
) -> None:
    max_output_tokens = int(payload.get("max_output_tokens") or 0)
    temperature = payload.get("temperature")
    top_p = payload.get("top_p")
    speed = str(payload.get("speed") or "default")
    verbosity = str(payload.get("verbosity") or "default")

    if protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        generation_config = body.get("generationConfig")
        if not isinstance(generation_config, dict):
            generation_config = {}
        if max_output_tokens > 0:
            generation_config["maxOutputTokens"] = max_output_tokens
        if temperature is not None:
            generation_config["temperature"] = temperature
        if top_p is not None:
            generation_config["topP"] = top_p
        if generation_config:
            body["generationConfig"] = generation_config
    else:
        if max_output_tokens > 0:
            if protocol == OPENAI_RESPONSES_PROTOCOL:
                body["max_output_tokens"] = max_output_tokens
            elif protocol == ANTHROPIC_MESSAGES_PROTOCOL:
                body["max_tokens"] = max_output_tokens
            elif _uses_modern_openai_output_limit(provider, model):
                body["max_completion_tokens"] = max_output_tokens
            else:
                body["max_tokens"] = max_output_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p

    if protocol in {OPENAI_COMPATIBLE_PROTOCOL, OPENAI_RESPONSES_PROTOCOL} and speed not in {"", "default"}:
        body["service_tier"] = _service_tier_for_speed(speed)
    if protocol == OPENAI_RESPONSES_PROTOCOL and verbosity not in {"", "default", "auto"}:
        text_options = body.get("text") if isinstance(body.get("text"), dict) else {}
        text_options["verbosity"] = verbosity
        body["text"] = text_options
    elif protocol == OPENAI_COMPATIBLE_PROTOCOL and verbosity not in {"", "default", "auto"}:
        body["verbosity"] = verbosity

    _merge_mapping(body, _request_options(payload))


def _openai_responses_reasoning_body(effort: str) -> dict[str, object]:
    if effort in {"", "default", "auto"}:
        return {}
    normalized = "none" if effort in {"disabled", "off"} else effort
    return {"reasoning": {"effort": normalized}}


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
    context_window = int(payload.get("context_window") or 0)
    max_output_tokens = int(payload.get("max_output_tokens") or 0)
    allow_public_network = bool(payload.get("allow_public_network"))
    base_url_uses_public_network = _base_url_uses_public_network(base_url)
    if mode != "cloud" and base_url_uses_public_network and not allow_public_network:
        raise ValueError(
            "Public local/custom LLM endpoints are disabled. Enable the public network endpoint control before using this base URL."
        )
    public_network = allow_public_network or base_url_uses_public_network
    context_for_request = _context_for_provider(
        context,
        mode=mode,
        allow_public_network=public_network,
    )
    user_prompt = str(prompt or "").strip()
    if not user_prompt:
        raise ValueError("LLM prompt cannot be empty.")
    if not model:
        raise ValueError(f"Select an LLM model before calling {payload['provider_label']}.")

    api_key = _api_key_for_config(raw_config, str(payload["api_key_env"]))
    headers: dict[str, str] = {"Content-Type": "application/json"}
    body: dict[str, object]
    url: str
    context_text = (
        _bounded_context_json_text(
            context_for_request,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        if context_for_request
        else ""
    )

    if protocol == OPENAI_COMPATIBLE_PROTOCOL:
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = _join_url(base_url, "chat/completions")
        messages = [
            {"role": "system", "content": _execution_boundary_text()},
            *_system_message(system_prompt),
            {"role": "user", "content": user_prompt},
        ]
        if context_text:
            messages.insert(
                len(messages) - 1,
                {
                    "role": "system",
                    "content": f"Trading context JSON: {context_text}",
                },
            )
        body = {"model": model, "messages": messages}
        body.update(_openai_compatible_reasoning_body(provider, model, reasoning_effort))
    elif protocol == OPENAI_RESPONSES_PROTOCOL:
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = _join_url(base_url, "responses")
        instruction_parts = [_execution_boundary_text()]
        if system_prompt:
            instruction_parts.append(str(system_prompt))
        if context_text:
            instruction_parts.append(f"Trading context JSON: {context_text}")
        body = {
            "model": model,
            "instructions": "\n\n".join(instruction_parts),
            "input": user_prompt,
        }
        body.update(_openai_responses_reasoning_body(reasoning_effort))
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
        if context_text:
            body["messages"].insert(
                0,
                {
                    "role": "user",
                    "content": f"Trading context JSON: {context_text}",
                },
            )
        body.update(_anthropic_thinking_body(reasoning_effort, max_output_tokens=max_output_tokens))
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
        if context_text:
            parts.append({"text": f"Trading context JSON: {context_text}"})
        parts.append({"text": user_prompt})
        body = {"contents": [{"parts": parts}]}
        generation_config = _gemini_generation_config(reasoning_effort, model)
        if generation_config:
            body["generationConfig"] = generation_config
    else:
        raise ValueError(f"Unsupported LLM protocol for provider {provider}: {protocol}")

    _apply_configured_request_options(
        body,
        payload=payload,
        provider=provider,
        model=model,
        protocol=protocol,
    )

    return {
        "provider": provider,
        "mode": str(payload["mode"]),
        "protocol": protocol,
        "url": url,
        "headers": headers,
        "json": body,
        "timeout_seconds": int(payload.get("timeout_seconds") or 30),
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
    if protocol == OPENAI_RESPONSES_PROTOCOL:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        output = payload.get("output")
        if isinstance(output, list):
            text_parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts).strip()
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


_OUTPUT_POLICY_VIOLATION_ORDER = (
    "order_execution_claim",
    "direct_order_action",
    "risk_override",
)


def _ordered_policy_violations(violations: set[str]) -> tuple[str, ...]:
    return tuple(label for label in _OUTPUT_POLICY_VIOLATION_ORDER if label in violations)


def _json_candidates_from_text(text: str) -> tuple[object, ...]:
    raw = str(text or "").strip()
    if not raw:
        return ()
    candidates = [raw]
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            candidates.append("\n".join(lines[1:-1]).strip())
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(raw[first : last + 1])
    first = raw.find("[")
    last = raw.rfind("]")
    if first >= 0 and last > first:
        candidates.append(raw[first : last + 1])

    parsed = []
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed.append(json.loads(candidate))
        except (TypeError, ValueError):
            continue
    return tuple(parsed)


def _scan_structured_policy_value(value: object, violations: set[str]) -> None:
    direct_order_actions = {
        "cancel_order",
        "change_leverage",
        "close_position",
        "create_order",
        "execute_order",
        "market_buy",
        "market_sell",
        "open_position",
        "place_order",
        "set_leverage",
        "submit_order",
    }
    risk_override_actions = {
        "change_leverage",
        "disable_stop_loss",
        "override_risk",
        "set_leverage",
    }
    executed_states = {"executed", "filled", "order_executed", "placed", "submitted"}

    if isinstance(value, dict):
        for raw_key, raw_item in value.items():
            key = str(raw_key or "").strip().lower()
            item = str(raw_item or "").strip().lower()
            if key in {"action", "command", "intent", "operation", "tool"}:
                if item in direct_order_actions:
                    violations.add("direct_order_action")
                if item in risk_override_actions:
                    violations.add("risk_override")
            if key in {"execution_status", "order_status", "status"} and item in executed_states:
                violations.add("order_execution_claim")
            if key in {"disable_stop_loss", "risk_override", "override_risk"} and item in {"1", "true", "yes", "on"}:
                violations.add("risk_override")
            if key == "stop_loss_enabled" and item in {"0", "false", "no", "off"}:
                violations.add("risk_override")
            _scan_structured_policy_value(raw_item, violations)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _scan_structured_policy_value(item, violations)


def llm_output_policy_violations(text: str) -> tuple[str, ...]:
    lower = str(text or "").strip().lower()
    if not lower:
        return ()
    violations: set[str] = set()
    for candidate in _json_candidates_from_text(text):
        _scan_structured_policy_value(candidate, violations)
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
    for label, phrases in checks:
        if any(phrase in lower for phrase in phrases):
            violations.add(label)
    return _ordered_policy_violations(violations)


def call_llm(
    config: dict | None,
    *,
    prompt: str,
    system_prompt: str = "",
    context: dict | None = None,
    dry_run: bool = True,
    timeout: float | None = None,
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
    has_header_credentials = bool(headers.get("Authorization") or headers.get("x-api-key"))
    has_gemini_query_credentials = (
        request_payload.get("protocol") == GEMINI_GENERATE_CONTENT_PROTOCOL
        and "?key=" in str(request_payload.get("url") or "")
    )
    if request_payload.get("mode") == "cloud" and not (has_header_credentials or has_gemini_query_credentials):
        return {
            "ok": False,
            "dry_run": False,
            "error": "Cloud LLM provider requires an API key or configured API key environment variable.",
            "provider": request_payload.get("provider"),
            "execution_policy": request_payload.get("execution_policy"),
        }

    try:
        response = requests.post(
            str(request_payload["url"]),
            headers=headers,
            json=request_payload["json"],
            timeout=max(1.0, float(timeout or request_payload.get("timeout_seconds") or 30.0)),
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "dry_run": False,
            "provider": request_payload.get("provider"),
            "execution_policy": request_payload.get("execution_policy"),
            "error": redact_text(f"LLM provider request failed: {exc}"),
        }
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
