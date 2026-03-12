from __future__ import annotations

import json
import shutil
import time
from pathlib import Path


_ALLOCATIONS_FILE_NAME = ".trading_bot_allocations.json"
_ALLOCATIONS_DIR_NAME = "data"


def _get_allocations_file_path(this_file: Path) -> Path:
    python_root = this_file.parents[2]
    data_dir = python_root / _ALLOCATIONS_DIR_NAME
    primary_path = data_dir / _ALLOCATIONS_FILE_NAME
    legacy_path = python_root / _ALLOCATIONS_FILE_NAME

    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return legacy_path

    if legacy_path.is_file() and not primary_path.exists():
        try:
            legacy_path.replace(primary_path)
        except Exception:
            try:
                shutil.copy2(legacy_path, primary_path)
            except Exception:
                return legacy_path

    return primary_path


def _serialize_allocation_key(key: tuple) -> str:
    return f"{key[0]}:{key[1]}"


def _deserialize_allocation_key(key_str: str) -> tuple:
    parts = key_str.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (key_str, "")


def _is_json_serializable(value) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_serializable(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_serializable(v) for k, v in value.items())
    return False


def _make_json_serializable(obj: dict) -> dict:
    result = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if v is None or isinstance(v, (str, int, float, bool)):
            result[k] = v
        elif isinstance(v, (list, tuple)):
            result[k] = [
                _make_json_serializable(item) if isinstance(item, dict) else item
                for item in v
                if _is_json_serializable(item) or isinstance(item, dict)
            ]
        elif isinstance(v, dict):
            result[k] = _make_json_serializable(v)
        else:
            result[k] = str(v)
    return result


def save_position_allocations(
    entry_allocations: dict,
    open_position_records: dict,
    *,
    this_file: Path,
    mode: str | None = None,
) -> bool:
    try:
        file_path = _get_allocations_file_path(this_file)

        serialized_allocations = {}
        for key, entries in (entry_allocations or {}).items():
            str_key = _serialize_allocation_key(key)
            if isinstance(entries, list):
                serialized_allocations[str_key] = [
                    {k: v for k, v in e.items() if _is_json_serializable(v)}
                    for e in entries if isinstance(e, dict)
                ]
            elif isinstance(entries, dict):
                entries_list = list(entries.values())
                serialized_allocations[str_key] = [
                    {k: v for k, v in e.items() if _is_json_serializable(v)}
                    for e in entries_list if isinstance(e, dict)
                ]

        serialized_records = {}
        for key, record in (open_position_records or {}).items():
            if not isinstance(record, dict):
                continue
            if str(record.get("status", "")).lower() != "active":
                continue
            str_key = _serialize_allocation_key(key)
            serialized_records[str_key] = _make_json_serializable(record)

        data = {
            "version": 1,
            "mode": mode or "unknown",
            "timestamp": time.time(),
            "entry_allocations": serialized_allocations,
            "open_position_records": serialized_records,
        }
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        return True
    except Exception:
        return False


def load_position_allocations(
    *,
    this_file: Path,
    mode: str | None = None,
) -> tuple[dict, dict]:
    entry_allocations = {}
    open_position_records = {}

    try:
        file_path = _get_allocations_file_path(this_file)
        if not file_path.exists():
            return entry_allocations, open_position_records

        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return entry_allocations, open_position_records

        saved_mode = data.get("mode")
        if mode and saved_mode and saved_mode != mode:
            return entry_allocations, open_position_records

        saved_ts = data.get("timestamp", 0)
        if time.time() - saved_ts > 86400:
            return entry_allocations, open_position_records

        for str_key, entries in data.get("entry_allocations", {}).items():
            if not isinstance(entries, list):
                continue
            key = _deserialize_allocation_key(str_key)
            validated_entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if not isinstance(entry.get("data"), dict):
                    entry["data"] = {}
                validated_entries.append(entry)
            entry_allocations[key] = validated_entries

        for str_key, record in data.get("open_position_records", {}).items():
            if not isinstance(record, dict):
                continue
            key = _deserialize_allocation_key(str_key)
            if not isinstance(record.get("data"), dict):
                record["data"] = {}
            if not isinstance(record.get("allocations"), list):
                record["allocations"] = []
            open_position_records[key] = record
    except Exception:
        pass

    return entry_allocations, open_position_records
