from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

try:
    import requests
except ModuleNotFoundError:  # Optional until live discovery is requested.
    requests = None  # type: ignore[assignment]

from .providers import (
    ANTHROPIC_MESSAGES_PROTOCOL,
    GEMINI_GENERATE_CONTENT_PROTOCOL,
    LLM_PROVIDER_CATALOG_REVISION,
    build_llm_config_payload,
)


def _join_url(base_url: str, path: str) -> str:
    return f"{str(base_url or '').rstrip('/')}/{str(path or '').lstrip('/')}"


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


def _api_key(config: dict[str, object], env_name: str) -> str:
    inline = str(config.get("llm_api_key") or "").strip()
    return inline or str(os.environ.get(env_name) or "").strip()


def _as_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _model_items(payload: object) -> Iterable[object]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return ()
    for key in ("data", "models", "items"):
        items = payload.get(key)
        if isinstance(items, list):
            return items
    return ()


def _model_record(item: object) -> dict[str, object] | None:
    if isinstance(item, str):
        model_id = item.strip()
        raw: dict[str, Any] = {}
    elif isinstance(item, dict):
        raw = item
        model_id = str(
            raw.get("id")
            or raw.get("name")
            or raw.get("model")
            or raw.get("model_name")
            or ""
        ).strip()
    else:
        return None
    if model_id.startswith("models/"):
        model_id = model_id[len("models/") :]
    if not model_id:
        return None

    top_provider = raw.get("top_provider") if isinstance(raw.get("top_provider"), dict) else {}
    architecture = raw.get("architecture") if isinstance(raw.get("architecture"), dict) else {}
    context_window = next(
        (
            value
            for value in (
                _as_positive_int(raw.get("context_length")),
                _as_positive_int(raw.get("context_window")),
                _as_positive_int(raw.get("input_token_limit")),
                _as_positive_int(top_provider.get("context_length")),
            )
            if value is not None
        ),
        None,
    )
    max_output_tokens = next(
        (
            value
            for value in (
                _as_positive_int(raw.get("max_output_tokens")),
                _as_positive_int(raw.get("output_token_limit")),
                _as_positive_int(top_provider.get("max_completion_tokens")),
            )
            if value is not None
        ),
        None,
    )
    capabilities = _string_list(raw.get("supported_parameters"))
    for modality in _string_list(architecture.get("input_modalities")):
        label = f"input:{modality}"
        if label not in capabilities:
            capabilities.append(label)
    for modality in _string_list(architecture.get("output_modalities")):
        label = f"output:{modality}"
        if label not in capabilities:
            capabilities.append(label)

    record: dict[str, object] = {
        "id": model_id,
        "name": str(raw.get("display_name") or raw.get("displayName") or raw.get("name") or model_id),
        "source": "discovered",
        "available": True,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "capabilities": capabilities,
    }
    description = str(raw.get("description") or "").strip()
    if description:
        record["description"] = description
    return record


def _static_model_records(payload: dict[str, object]) -> list[dict[str, object]]:
    suggestions = list(payload.get("model_suggestions") or [])
    selected = str(payload.get("model") or "").strip()
    if selected and selected not in suggestions:
        suggestions.insert(0, selected)
    return [
        {
            "id": str(model_id),
            "name": str(model_id),
            "source": "catalog",
            "available": None,
            "context_window": None,
            "max_output_tokens": None,
            "capabilities": [],
        }
        for model_id in suggestions
        if str(model_id).strip()
    ]


def _merge_models(
    discovered: Iterable[dict[str, object]],
    static: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for record in (*tuple(discovered), *tuple(static)):
        model_id = str(record.get("id") or "").strip()
        if not model_id:
            continue
        key = model_id.casefold()
        if key not in merged:
            merged[key] = dict(record)
            order.append(key)
            continue
        existing = merged[key]
        for field, value in record.items():
            if field not in existing or existing[field] in (None, "", []):
                existing[field] = value
    return [merged[key] for key in order]


def _discovery_request(
    config: dict[str, object],
    payload: dict[str, object],
) -> tuple[str, dict[str, str]]:
    base_url = str(payload.get("base_url") or "").strip()
    provider = str(payload.get("provider") or "")
    protocol = str(payload.get("provider_protocol") or payload.get("protocol") or "")
    api_key = _api_key(config, str(payload.get("api_key_env") or ""))
    headers = {"Accept": "application/json"}

    if protocol == ANTHROPIC_MESSAGES_PROTOCOL:
        url = _join_url(base_url, "v1/models")
        if api_key:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return url, headers
    if protocol == GEMINI_GENERATE_CONTENT_PROTOCOL:
        query = urlencode({"key": api_key}) if api_key else ""
        url = _join_url(base_url, "models")
        return (f"{url}?{query}" if query else url), headers

    path = str(payload.get("model_discovery_path") or "models").strip() or "models"
    url = _join_url(base_url, path)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider == "kilo":
        headers["User-Agent"] = "trading-bot-model-discovery"
    return url, headers


def _safe_error(exc: Exception, *, api_key: str) -> str:
    text = str(exc or exc.__class__.__name__).strip() or exc.__class__.__name__
    if api_key:
        text = text.replace(api_key, "********")
        text = text.replace(quote(api_key, safe=""), "********")
    return text[:500]


def discover_llm_models(
    config: dict | None,
    *,
    timeout: float | None = None,
) -> dict[str, object]:
    """Merge a provider's live model list with selectable catalog and custom IDs.

    Catalog entries are intentionally retained when an upstream list omits or retires
    them. Their ``available`` value remains unknown until the provider accepts a call.
    """

    raw_config = dict(config) if isinstance(config, dict) else {}
    payload = build_llm_config_payload(raw_config)
    static = _static_model_records(payload)
    provider = str(payload.get("provider") or "")
    base_url = str(payload.get("base_url") or "")
    mode = str(payload.get("mode") or "")
    allow_public_network = bool(payload.get("allow_public_network"))
    if mode != "cloud" and _base_url_uses_public_network(base_url) and not allow_public_network:
        return {
            "ok": False,
            "provider": provider,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "dynamic_count": 0,
            "models": static,
            "error": "Public local/custom LLM endpoints are disabled for model discovery.",
        }

    url, headers = _discovery_request(raw_config, payload)
    api_key = _api_key(raw_config, str(payload.get("api_key_env") or ""))
    request_timeout = max(1.0, float(timeout or payload.get("timeout_seconds") or 30.0))
    if requests is None:
        return {
            "ok": False,
            "provider": provider,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "dynamic_count": 0,
            "models": static,
            "error": "Live model discovery requires the optional requests dependency.",
        }
    try:
        response = requests.get(url, headers=headers, timeout=request_timeout)
        response.raise_for_status()
        response_payload = response.json()
        discovered = [
            record
            for record in (_model_record(item) for item in _model_items(response_payload))
            if record is not None
        ]
        models = _merge_models(discovered, static)
        return {
            "ok": True,
            "provider": provider,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "dynamic_count": len(discovered),
            "models": models,
            "error": "",
        }
    except (requests.RequestException, RuntimeError, TypeError, ValueError, OSError) as exc:
        return {
            "ok": False,
            "provider": provider,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "dynamic_count": 0,
            "models": static,
            "error": _safe_error(exc, api_key=api_key),
        }
