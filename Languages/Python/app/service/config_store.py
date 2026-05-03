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
DEFAULT_SERVICE_CONFIG_PATH = Path("~/.trading-bot/service-config.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        if version_number != SERVICE_CONFIG_FORMAT_VERSION:
            raise ValueError(
                f"Service config file {path} uses unsupported format_version {version_number}."
            )
        config_payload = raw_payload.get("config")
        metadata = {
            "kind": str(raw_payload.get("kind") or SERVICE_CONFIG_FILE_KIND),
            "format_version": version_number,
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
    }


def write_service_config_file(
    config: Mapping[str, object] | None,
    path: str | Path | None = None,
) -> dict[str, object]:
    resolved_path = resolve_service_config_path(path)
    validated_config = validate_runtime_config(
        merge_service_config(build_default_config(), config if isinstance(config, Mapping) else {})
    )
    saved_at = _now_iso()
    payload = {
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
        "saved_at": saved_at,
        "config": validated_config,
    }
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
    return {
        "path": str(resolved_path),
        "exists": True,
        "saved_at": saved_at,
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
    }


def service_config_file_status(path: str | Path | None = None) -> dict[str, object]:
    resolved_path = resolve_service_config_path(path)
    exists = resolved_path.is_file()
    modified_at = ""
    if exists:
        try:
            modified_at = datetime.fromtimestamp(
                resolved_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        except Exception:
            modified_at = ""
    return {
        "path": str(resolved_path),
        "exists": exists,
        "modified_at": modified_at,
        "kind": SERVICE_CONFIG_FILE_KIND,
        "format_version": SERVICE_CONFIG_FORMAT_VERSION,
    }


__all__ = [
    "DEFAULT_SERVICE_CONFIG_PATH",
    "SERVICE_CONFIG_ENV_PATH",
    "SERVICE_CONFIG_FILE_KIND",
    "SERVICE_CONFIG_FORMAT_VERSION",
    "load_service_config_file",
    "merge_service_config",
    "resolve_service_config_path",
    "service_config_file_status",
    "write_service_config_file",
]
