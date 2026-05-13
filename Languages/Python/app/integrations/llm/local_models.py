from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

try:
    import requests as _requests
except ImportError:  # pragma: no cover - exercised by lean CI smoke environments
    _requests = None


OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/windows"
OLLAMA_MODEL_STORAGE_HINT = (
    "Ollama stores downloaded models outside this project in its own model cache "
    "(commonly ~/.ollama/models on Linux/macOS and %USERPROFILE%\\.ollama\\models on Windows)."
)
OLLAMA_MODELS_ENV = "OLLAMA_MODELS"
_OLLAMA_SIZE_HINTS = {
    "qwen3:0.6b": "about 1 GB",
    "qwen3:1.7b": "about 2 GB",
    "qwen3:4b": "about 3 GB",
    "qwen3:8b": "about 5 GB",
    "qwen3:14b": "about 9 GB",
    "qwen3:30b-a3b": "about 19 GB",
    "qwen3:32b": "about 20 GB",
    "llama3.1:8b": "about 5 GB",
    "llama3.2:3b": "about 2 GB",
    "llama3.2:1b": "about 1 GB",
    "deepseek-r1:8b": "about 5 GB",
    "gemma3:4b": "about 3 GB",
    "gpt-oss:20b": "about 13 GB",
}
_OLLAMA_SIZE_GB_HINTS = {
    "qwen3:0.6b": 1.0,
    "qwen3:1.7b": 2.0,
    "qwen3:4b": 3.0,
    "qwen3:8b": 5.0,
    "qwen3:14b": 9.0,
    "qwen3:30b-a3b": 19.0,
    "qwen3:32b": 20.0,
    "llama3.1:8b": 5.0,
    "llama3.2:3b": 2.0,
    "llama3.2:1b": 1.0,
    "deepseek-r1:8b": 5.0,
    "gemma3:4b": 3.0,
    "gpt-oss:20b": 13.0,
}


@dataclass(frozen=True, slots=True)
class LocalModelStatus:
    model: str
    base_url: str
    server_kind: str
    installed: bool
    can_download: bool
    can_start: bool = False
    available_models: tuple[str, ...] = ()
    error: str = ""
    storage_hint: str = ""
    storage_paths: tuple[str, ...] = ()
    estimated_size_label: str = ""
    free_disk_gb: float | None = None
    recommended_free_disk_gb: float | None = None
    disk_space_warning: str = ""


@dataclass(frozen=True, slots=True)
class LocalModelServerStartResult:
    started: bool
    server_kind: str
    executable: str = ""
    error: str = ""


def _join_url(base_url: str, path: str) -> str:
    return f"{str(base_url or '').rstrip('/')}/{str(path or '').lstrip('/')}"


def _requests_dependency_error(action: str) -> RuntimeError:
    return RuntimeError(f"requests is not installed; install the Python service dependencies to {action}.")


def _default_request_get(*args: Any, **kwargs: Any) -> Any:
    if _requests is None:
        raise _requests_dependency_error("check local LLM model status")
    return _requests.get(*args, **kwargs)


def _default_request_post(*args: Any, **kwargs: Any) -> Any:
    if _requests is None:
        raise _requests_dependency_error("download local LLM models")
    return _requests.post(*args, **kwargs)


def _default_request_delete(*args: Any, **kwargs: Any) -> Any:
    if _requests is None:
        raise _requests_dependency_error("remove local LLM models")
    return _requests.delete(*args, **kwargs)


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


def ollama_model_storage_hint() -> str:
    return OLLAMA_MODEL_STORAGE_HINT


def ollama_model_storage_paths() -> tuple[str, ...]:
    env_path = str(os.environ.get(OLLAMA_MODELS_ENV) or "").strip()
    if env_path:
        return (os.path.abspath(os.path.expanduser(env_path)),)
    return (os.path.abspath(os.path.expanduser("~/.ollama/models")),)


def estimate_ollama_model_size_label(model: str) -> str:
    clean = str(model or "").strip().lower()
    if not clean:
        return "unknown size"
    if clean in _OLLAMA_SIZE_HINTS:
        return _OLLAMA_SIZE_HINTS[clean]
    if ":" not in clean:
        tagged = f"{clean}:latest"
        if tagged in _OLLAMA_SIZE_HINTS:
            return _OLLAMA_SIZE_HINTS[tagged]
    return "size varies by model and quantization"


def estimate_ollama_model_size_gb(model: str) -> float | None:
    clean = str(model or "").strip().lower()
    if not clean:
        return None
    if clean in _OLLAMA_SIZE_GB_HINTS:
        return _OLLAMA_SIZE_GB_HINTS[clean]
    if ":" not in clean:
        return _OLLAMA_SIZE_GB_HINTS.get(f"{clean}:latest")
    return None


def _disk_space_status(model: str) -> tuple[float | None, float | None, str]:
    estimated = estimate_ollama_model_size_gb(model)
    recommended = None if estimated is None else max(2.0, estimated * 1.25)
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        free_gb = usage.free / (1024 ** 3)
    except OSError:
        free_gb = None
    warning = ""
    if recommended is not None and free_gb is not None and free_gb < recommended:
        warning = f"Low disk space: about {recommended:.1f} GB free is recommended for this model."
    return free_gb, recommended, warning


def ollama_executable_path(command_finder: Callable[[str], str | None] = shutil.which) -> str:
    return str(command_finder("ollama") or "").strip()


def get_local_model_status(
    base_url: str,
    model: str,
    *,
    timeout: float = 3.0,
    request_get: Callable[..., Any] = _default_request_get,
    command_finder: Callable[[str], str | None] = shutil.which,
) -> LocalModelStatus:
    clean_base_url = str(base_url or "").strip()
    clean_model = str(model or "").strip()
    kind = _server_kind(clean_base_url)
    can_start = kind == "ollama" and bool(ollama_executable_path(command_finder))
    free_disk_gb, recommended_free_disk_gb, disk_space_warning = (
        _disk_space_status(clean_model) if kind == "ollama" else (None, None, "")
    )
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
            can_start=can_start,
            available_models=available_models,
            storage_hint=OLLAMA_MODEL_STORAGE_HINT if kind == "ollama" else "",
            storage_paths=ollama_model_storage_paths() if kind == "ollama" else (),
            estimated_size_label=estimate_ollama_model_size_label(clean_model) if kind == "ollama" else "",
            free_disk_gb=free_disk_gb,
            recommended_free_disk_gb=recommended_free_disk_gb,
            disk_space_warning=disk_space_warning,
        )
    except Exception as exc:
        return LocalModelStatus(
            model=clean_model,
            base_url=clean_base_url,
            server_kind=kind,
            installed=False,
            can_download=kind == "ollama",
            can_start=can_start,
            error=str(exc),
            storage_hint=OLLAMA_MODEL_STORAGE_HINT if kind == "ollama" else "",
            storage_paths=ollama_model_storage_paths() if kind == "ollama" else (),
            estimated_size_label=estimate_ollama_model_size_label(clean_model) if kind == "ollama" else "",
            free_disk_gb=free_disk_gb,
            recommended_free_disk_gb=recommended_free_disk_gb,
            disk_space_warning=disk_space_warning,
        )


def start_ollama_server(
    base_url: str,
    *,
    command_finder: Callable[[str], str | None] = shutil.which,
    popen: Callable[..., Any] = subprocess.Popen,
) -> LocalModelServerStartResult:
    kind = _server_kind(base_url)
    if kind != "ollama":
        return LocalModelServerStartResult(
            started=False,
            server_kind=kind,
            error="Automatic local model server startup is only supported for Ollama on localhost:11434.",
        )

    executable = ollama_executable_path(command_finder)
    if not executable:
        return LocalModelServerStartResult(
            started=False,
            server_kind=kind,
            error="Ollama is not installed or the ollama command is not on PATH.",
        )

    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        popen([executable, "serve"], **kwargs)
    except Exception as exc:
        return LocalModelServerStartResult(started=False, server_kind=kind, executable=executable, error=str(exc))

    return LocalModelServerStartResult(started=True, server_kind=kind, executable=executable)


def pull_ollama_model(
    base_url: str,
    model: str,
    *,
    timeout: float = 1800.0,
    request_post: Callable[..., Any] = _default_request_post,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> None:
    def _raise_if_cancelled() -> None:
        if callable(cancel_callback) and bool(cancel_callback()):
            raise RuntimeError("Ollama model download cancelled.")

    clean_model = str(model or "").strip()
    if not clean_model:
        raise ValueError("Local model name cannot be empty.")
    if _server_kind(base_url) != "ollama":
        raise ValueError("Automatic local model downloads are only supported for Ollama on localhost:11434.")
    _raise_if_cancelled()
    stream = progress_callback is not None or cancel_callback is not None
    request_kwargs = {
        "json": {"model": clean_model, "stream": stream},
        "timeout": max(1.0, float(timeout or 1800.0)),
        "stream": stream,
    }
    url = _join_url(_ollama_base_url(base_url), "api/pull")
    try:
        response = request_post(url, **request_kwargs)
    except TypeError as exc:
        if "stream" not in str(exc):
            raise
        request_kwargs.pop("stream", None)
        response = request_post(url, **request_kwargs)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    if not stream:
        return
    iter_lines = getattr(response, "iter_lines", None)
    if not callable(iter_lines):
        return
    import json

    try:
        for raw_line in iter_lines():
            _raise_if_cancelled()
            if not raw_line:
                continue
            try:
                text = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
                payload = json.loads(text)
            except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
                payload = {"status": str(raw_line)}
            if isinstance(payload, dict) and progress_callback is not None:
                progress_callback(payload)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def delete_ollama_model(
    base_url: str,
    model: str,
    *,
    timeout: float = 60.0,
    request_delete: Callable[..., Any] = _default_request_delete,
) -> None:
    clean_model = str(model or "").strip()
    if not clean_model:
        raise ValueError("Local model name cannot be empty.")
    if _server_kind(base_url) != "ollama":
        raise ValueError("Automatic local model removal is only supported for Ollama on localhost:11434.")
    response = request_delete(
        _join_url(_ollama_base_url(base_url), "api/delete"),
        json={"model": clean_model},
        timeout=max(1.0, float(timeout or 60.0)),
    )
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
