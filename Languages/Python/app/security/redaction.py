from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


REDACTED_TEXT = "<redacted>"

_SENSITIVE_KEY_PARTS = (
    "apikey",
    "apisecret",
    "authorization",
    "bearer",
    "passphrase",
    "password",
    "privatekey",
    "secret",
    "signature",
    "token",
    "xmbxapikey",
)
_SAFE_SENSITIVE_KEY_SUFFIXES = ("env", "environment", "present")

_SECRET_WORD = (
    r"x-mbx-apikey|api[_-]?key|api[_-]?secret|llm[_-]?api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|token|secret|signature|password|passphrase|private[_-]?key"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)(['\"]?\bauthorization\b['\"]?\s*[:=]\s*)(bearer\s+)?([^\s,;&}]+)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?i)(['\"]?\b(?:{_SECRET_WORD})\b['\"]?\s*[:=]\s*)(['\"]?)([^'\"\s,;&}}]+)(\2)"
)
_BARE_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def _normalized_key(value: object) -> str:
    text = str(value or "").strip().lower()
    return "".join(char for char in text if char.isalnum())


def is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    if normalized.endswith(_SAFE_SENSITIVE_KEY_SUFFIXES):
        return False
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return text
    text = _AUTH_HEADER_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2) or ''}{REDACTED_TEXT}",
        text,
    )
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED_TEXT}{match.group(4)}", text)
    text = _BARE_BEARER_RE.sub(f"Bearer {REDACTED_TEXT}", text)
    return text


def _json_safe_fallback(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return redact_text(str(value))


def redact_value(value: Any, *, _depth: int = 0, _seen: set[int] | None = None) -> Any:
    if _seen is None:
        _seen = set()
    if _depth > 8:
        return "..."

    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in _seen:
            return "..."
        _seen.add(object_id)
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if is_sensitive_key(key_text):
                out[key_text] = REDACTED_TEXT if item not in (None, "") else ""
            else:
                out[key_text] = redact_value(item, _depth=_depth + 1, _seen=_seen)
        _seen.discard(object_id)
        return out

    if isinstance(value, (list, tuple, set, frozenset)):
        object_id = id(value)
        if object_id in _seen:
            return "..."
        _seen.add(object_id)
        out = [redact_value(item, _depth=_depth + 1, _seen=_seen) for item in value]
        _seen.discard(object_id)
        return out

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _json_safe_fallback(value)
