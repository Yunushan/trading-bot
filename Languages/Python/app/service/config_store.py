"""Durable JSON storage for the headless service runtime config."""

from __future__ import annotations

import copy
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.config import build_default_config, validate_runtime_config
else:
    from ..config import build_default_config, validate_runtime_config


SERVICE_CONFIG_FILE_KIND = "trading-bot-service-config"
SERVICE_CONFIG_FORMAT_VERSION = 1
SERVICE_CONFIG_ENV_PATH = "BOT_SERVICE_CONFIG_PATH"
SERVICE_CONFIG_ALLOW_INLINE_SECRETS_ENV = "BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS"
SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV = "BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH"
DEFAULT_SERVICE_CONFIG_PATH = Path("~/.trading-bot/service-config.json")
SECRET_STORAGE_WARNING = (
    "This service config is plain JSON and contains secret-bearing fields; "
    "prefer environment variables or OS credential storage for API keys."
)
_SECRET_KEY_TOKENS = (
    "api_key",
    "api_secret",
    "apikey",
    "api-token",
    "api_token",
    "authorization",
    "bearer",
    "password",
    "secret",
    "signature",
    "token",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _deep_merge_mappings(base: Mapping[str, object], patch: Mapping[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[str(key)] = _deep_merge_mappings(merged.get(key) or {}, value)
        else:
            merged[str(key)] = copy.deepcopy(value)
    return merged


def merge_service_config(base: Mapping[str, object], patch: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(patch, Mapping):
        return copy.deepcopy(dict(base))
    return _deep_merge_mappings(base, patch)


def resolve_service_config_path(path: str | Path | None = None) -> Path:
    raw_path = path
    if raw_path in (None, ""):
        raw_path = os.environ.get(SERVICE_CONFIG_ENV_PATH) or DEFAULT_SERVICE_CONFIG_PATH
    resolved = Path(raw_path).expanduser()
    try:
        return resolved.resolve()
    except Exception:
        return resolved


def service_config_safe_root() -> Path:
    return resolve_service_config_path(DEFAULT_SERVICE_CONFIG_PATH).parent


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def ensure_service_config_path_allowed(
    path: str | Path | None,
    *,
    allow_unsafe_path: bool = False,
) -> Path:
    resolved = resolve_service_config_path(path)
    if allow_unsafe_path or _env_flag(SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV, False):
        return resolved
    safe_root = service_config_safe_root()
    if _is_relative_to(resolved, safe_root):
        return resolved
    raise PermissionError(
        f"Service config path {resolved} is outside the safe config directory {safe_root}. "
        f"Use allow_unsafe_path=true or set {SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV}=1 only for trusted local paths."
    )


def _is_secret_key(key: object) -> bool:
    text = str(key or "").strip().lower().replace("-", "_")
    if text.endswith("_env") or text.endswith("_env_var"):
        return False
    return any(token.replace("-", "_") in text for token in _SECRET_KEY_TOKENS)


def _secret_field_paths(payload: object, *, prefix: str = "") -> list[str]:
    if isinstance(payload, Mapping):
        paths: list[str] = []
        for key, value in payload.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _is_secret_key(key) and value not in (None, ""):
                paths.append(path)
                continue
            paths.extend(_secret_field_paths(value, prefix=path))
        return paths
    if isinstance(payload, list):
        paths = []
        for idx, value in enumerate(payload):
            paths.extend(_secret_field_paths(value, prefix=f"{prefix}[{idx}]"))
        return paths
    return []


def service_config_secret_metadata(config: Mapping[str, object] | None) -> dict[str, object]:
    fields = tuple(sorted(set(_secret_field_paths(config if isinstance(config, Mapping) else {}))))
    return {
        "contains_secrets": bool(fields),
        "secret_fields": list(fields),
        "secret_storage": "plain-json-on-disk",
        "secret_storage_warning": SECRET_STORAGE_WARNING if fields else "",
    }


def _without_inline_secret_values(payload: object) -> object:
    if isinstance(payload, Mapping):
        out: dict[str, object] = {}
        for key, value in payload.items():
            if _is_secret_key(key) and value not in (None, ""):
                out[str(key)] = ""
            else:
                out[str(key)] = _without_inline_secret_values(value)
        return out
    if isinstance(payload, list):
        return [_without_inline_secret_values(item) for item in payload]
    return copy.deepcopy(payload)


def _coerce_loaded_config(raw_payload: object, *, path: Path) -> tuple[dict[str, object], dict[str, object]]:
    if not isinstance(raw_payload, dict):
        raise ValueError(f"Service config file {path} must contain a JSON object.")

    metadata: dict[str, object] = {
        "kind": "legacy-config",
        "format_version": None,
        "saved_at": "",
    }
    config_payload: object = raw_payload
    if "config" in raw_payload and (
        raw_payload.get("kind") == SERVICE_CONFIG_FILE_KIND
        or "format_version" in raw_payload
        or "saved_at" in raw_payload
    ):
        version = raw_payload.get("format_version", SERVICE_CONFIG_FORMAT_VERSION)
        try:
            version_number = int(version)
        except Exception as exc:
            raise ValueError(f"Service config file {path} has an invalid format_version.") from exc
        if version_number > SERVICE_CONFIG_FORMAT_VERSION:
            raise ValueError(
                f"Service config file {path} uses unsupported format_version {version_number}."
            )
        config_payload = raw_payload.get("config")
        metadata = {
            "kind": str(raw_payload.get("kind") or SERVICE_CONFIG_FILE_KIND),
            "format_version": SERVICE_CONFIG_FORMAT_VERSION,
            "migrated_from_format_version": version_number if version_number < SERVICE_CONFIG_FORMAT_VERSION else None,
            "saved_at": str(raw_payload.get("saved_at") or ""),
        }

    if not isinstance(config_payload, dict):
        raise ValueError(f"Service config file {path} must contain a config object.")

    merged_config = merge_service_config(build_default_config(), config_payload)
    return validate_runtime_config(merged_config), metadata


def load_service_config_file(path: str | Path | None = None) -> tuple[dict[str, object], dict[str, object]]:
    resolved_path = resolve_service_config_path(path)
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Service config file not found: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8") as handle:
        raw_payload = json.load(handle)
    config, metadata = _coerce_loaded_config(raw_payload, path=resolved_path)
    loaded_at = _now_iso()
    return config, {
        "path": str(resolved_path),
        "exists": True,
        "loaded_at": loaded_at,
        "saved_at": str(metadata.get("saved_at") or ""),
        "kind": str(metadata.get("kind") or SERVICE_CONFIG_FILE_KIND),
        "format_version": metadata.get("format_version") or SERVICE_CONFIG_FORMAT_VERSION,
        "migrated_from_format_version": metadata.get("migrated_from_format_version"),
    }


def write_service_config_file(
    config: Mapping[str, object] | None,
    path: str | Path | None = None,
    *,
    allow_unsafe_path: bool = False,
) -> dict[str, object]:
    resolved_path = ensure_service_config_path_allowed(path, allow_unsafe_path=allow_unsafe_path)
    validated_config = validate_runtime_config(
        merge_service_config(build_default_config(), config if isinstance(config, Mapping) else {})
    )
    secret_metadata = service_config_secret_metadata(validated_config)
    contains_secrets = bool(secret_metadata.get("contains_secrets"))
    inline_secrets_allowed = _env_flag(SERVICE_CONFIG_ALLOW_INLINE_SECRETS_ENV, False)
    persisted_config = (
        validated_config
        if not contains_secrets or inline_secrets_allowed
        else _without_inline_secret_values(validated_config)
    )
    saved_at = _now_iso()
    payload = {
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
        "saved_at": saved_at,
        "config": persisted_config,
        "inline_secrets_persisted": bool(contains_secrets and inline_secrets_allowed),
    }
    payload.update(secret_metadata)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = resolved_path.with_name(f".{resolved_path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(resolved_path)
    try:
        os.chmod(resolved_path, 0o600)
    except Exception:
        pass
    metadata = {
        "path": str(resolved_path),
        "exists": True,
        "saved_at": saved_at,
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
    }
    metadata.update(secret_metadata)
    metadata["inline_secrets_persisted"] = bool(contains_secrets and inline_secrets_allowed)
    return metadata


def service_config_file_status(path: str | Path | None = None) -> dict[str, object]:
    resolved_path = resolve_service_config_path(path)
    exists = resolved_path.is_file()
    modified_at = ""
    secret_metadata: dict[str, object] = {}
    if exists:
        try:
            modified_at = datetime.fromtimestamp(
                resolved_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        except Exception:
            modified_at = ""
        try:
            with resolved_path.open("r", encoding="utf-8") as handle:
                raw_payload = json.load(handle)
            if isinstance(raw_payload, dict):
                secret_metadata = {
                    "contains_secrets": bool(raw_payload.get("contains_secrets")),
                    "secret_fields": list(raw_payload.get("secret_fields") or []),
                    "secret_storage": str(raw_payload.get("secret_storage") or ""),
                    "secret_storage_warning": str(raw_payload.get("secret_storage_warning") or ""),
                }
        except Exception:
            secret_metadata = {}
    payload = {
        "path": str(resolved_path),
        "exists": exists,
        "modified_at": modified_at,
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
    }
    payload.update({key: value for key, value in secret_metadata.items() if value not in ("", [], None)})
    return payload


__all__ = [
    "DEFAULT_SERVICE_CONFIG_PATH",
    "SERVICE_CONFIG_ALLOW_INLINE_SECRETS_ENV",
    "SERVICE_CONFIG_ALLOW_UNSAFE_PATH_ENV",
    "SERVICE_CONFIG_ENV_PATH",
    "SERVICE_CONFIG_FILE_KIND",
    "SERVICE_CONFIG_FORMAT_VERSION",
    "ensure_service_config_path_allowed",
    "load_service_config_file",
    "merge_service_config",
    "resolve_service_config_path",
    "service_config_safe_root",
    "service_config_file_status",
    "service_config_secret_metadata",
    "write_service_config_file",
]
