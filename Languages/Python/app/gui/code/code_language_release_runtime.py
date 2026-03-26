from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from .code_language_catalog import RELEASE_INFO_JSON_NAME, RELEASE_TAG_TEXT_NAME

_THIS_FILE = Path(__file__).resolve()


def version_sort_key(version_text: str | None) -> tuple[int, ...]:
    value = str(version_text or "").strip()
    if not value:
        return tuple()
    parts = re.findall(r"\d+", value)
    if not parts:
        return tuple()
    try:
        return tuple(int(part) for part in parts)
    except Exception:
        return tuple()


def extract_semver_from_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(
        r"(\d+(?:[._]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).replace("_", ".")


def http_get_text(url: str, timeout: float = 8.0) -> str | None:
    if not url:
        return None
    timeout_val = max(2.0, float(timeout or 8.0))
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
        with urllib.request.urlopen(request, timeout=timeout_val) as response:
            data = response.read()
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def http_get_json(url: str, timeout: float = 8.0):
    payload = http_get_text(url, timeout=timeout)
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None


def is_frozen_python_app() -> bool:
    return bool(getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None))


def normalize_release_tag_text(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    lower_text = text.lower()
    for prefix in ("refs/tags/", "refs/heads/"):
        if lower_text.startswith(prefix):
            text = text[len(prefix):].strip()
            lower_text = text.lower()
            break
    if not text:
        return None
    if lower_text in {"none", "null", "unknown", "n/a", "na", "-"}:
        return None
    if len(text) > 96:
        text = text[:96].strip()
    semver = extract_semver_from_text(text)
    if semver:
        return semver
    return text


def release_tag_from_json_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    candidate_keys = (
        "release_tag",
        "tag_name",
        "tag",
        "python_release_tag",
        "app_release_tag",
        "version",
    )
    for key in candidate_keys:
        tag_value = normalize_release_tag_text(payload.get(key))
        if tag_value:
            return tag_value

    nested_keys = ("python", "app", "release")
    for nested_key in nested_keys:
        nested = payload.get(nested_key)
        if not isinstance(nested, dict):
            continue
        for key in candidate_keys:
            tag_value = normalize_release_tag_text(nested.get(key))
            if tag_value:
                return tag_value
    return None


def release_tag_from_text_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue
            return normalize_release_tag_text(line)
    except Exception:
        return None
    return None


def dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = os.path.normcase(os.path.normpath(str(resolved)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def release_tag_from_metadata_dirs(directories: list[Path]) -> str | None:
    metadata_names = (
        RELEASE_INFO_JSON_NAME,
        "tb-release.json",
        RELEASE_TAG_TEXT_NAME,
        "tb-release.txt",
    )
    for directory in dedupe_paths(directories):
        for name in metadata_names:
            file_path = directory / name
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() == ".json":
                tag_value = release_tag_from_json_file(file_path)
            else:
                tag_value = release_tag_from_text_file(file_path)
            if tag_value:
                return tag_value
    return None


def python_release_metadata_dirs() -> list[Path]:
    directories: list[Path] = []
    try:
        app_dir = _THIS_FILE.parents[1]
        directories.extend([app_dir, app_dir.parent])
    except Exception:
        pass

    if is_frozen_python_app():
        meipass_raw = str(getattr(sys, "_MEIPASS", "") or "").strip()
        if meipass_raw:
            meipass_dir = Path(meipass_raw)
            directories.extend([meipass_dir, meipass_dir / "app"])
        try:
            exe_dir = Path(sys.executable).resolve().parent
            directories.extend([exe_dir, exe_dir / "app"])
        except Exception:
            pass
    return dedupe_paths(directories)


def python_runtime_release_tag() -> str | None:
    env_keys = (
        "TB_PY_RELEASE_TAG",
        "TB_PYTHON_RELEASE_TAG",
        "TB_APP_RELEASE_TAG",
        "TB_RELEASE_TAG",
        "BOT_RELEASE_TAG",
    )
    for key in env_keys:
        value = normalize_release_tag_text(os.environ.get(key))
        if value:
            return value
    return release_tag_from_metadata_dirs(python_release_metadata_dirs())
