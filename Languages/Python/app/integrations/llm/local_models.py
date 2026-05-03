from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import requests


@dataclass(frozen=True, slots=True)
class LocalModelStatus:
    model: str
    base_url: str
    server_kind: str
    installed: bool
    can_download: bool
    available_models: tuple[str, ...] = ()
    error: str = ""


def _join_url(base_url: str, path: str) -> str:
    return f"{str(base_url or '').rstrip('/')}/{str(path or '').lstrip('/')}"


def _server_kind(base_url: str) -> str:
    parsed = urlsplit(str(base_url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"} and parsed.port == 11434:
        return "ollama"
    return "openai-compatible"


def _ollama_base_url(base_url: str) -> str:
    parsed = urlsplit(str(base_url or "").strip())
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    elif path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _model_ids(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    data = payload.get("data")
    if not isinstance(data, list):
        return ()
    ids: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            ids.append(model_id)
    return tuple(sorted(set(ids)))


def _model_installed(model: str, available_models: tuple[str, ...]) -> bool:
    requested = str(model or "").strip()
    if not requested:
        return True
    if requested in available_models:
        return True
    if ":" not in requested and f"{requested}:latest" in available_models:
        return True
    return False


def get_local_model_status(
    base_url: str,
    model: str,
    *,
    timeout: float = 3.0,
    request_get: Callable[..., Any] = requests.get,
) -> LocalModelStatus:
    clean_base_url = str(base_url or "").strip()
    clean_model = str(model or "").strip()
    kind = _server_kind(clean_base_url)
    try:
        response = request_get(_join_url(clean_base_url, "models"), timeout=max(1.0, float(timeout or 3.0)))
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        payload = response.json() if hasattr(response, "json") else {}
        available_models = _model_ids(payload)
        return LocalModelStatus(
            model=clean_model,
            base_url=clean_base_url,
            server_kind=kind,
            installed=_model_installed(clean_model, available_models),
            can_download=kind == "ollama",
            available_models=available_models,
        )
    except Exception as exc:
        return LocalModelStatus(
            model=clean_model,
            base_url=clean_base_url,
            server_kind=kind,
            installed=False,
            can_download=False,
            error=str(exc),
        )


def pull_ollama_model(
    base_url: str,
    model: str,
    *,
    timeout: float = 1800.0,
    request_post: Callable[..., Any] = requests.post,
) -> None:
    clean_model = str(model or "").strip()
    if not clean_model:
        raise ValueError("Local model name cannot be empty.")
    if _server_kind(base_url) != "ollama":
        raise ValueError("Automatic local model downloads are only supported for Ollama on localhost:11434.")
    response = request_post(
        _join_url(_ollama_base_url(base_url), "api/pull"),
        json={"model": clean_model, "stream": False},
        timeout=max(1.0, float(timeout or 1800.0)),
    )
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
