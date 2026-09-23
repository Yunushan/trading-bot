"""Process-wide hard resource limits for advisory LLM HTTP calls."""

from __future__ import annotations

import json
import math
import queue
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar


MAX_LLM_PROMPT_BYTES = 64 * 1024
MAX_LLM_SYSTEM_PROMPT_BYTES = 32 * 1024
MAX_LLM_CONTEXT_BYTES = 256 * 1024
MAX_LLM_REQUEST_BYTES = 512 * 1024
MAX_LLM_URL_BYTES = 8 * 1024
MAX_LLM_HEADER_BYTES = 8 * 1024
MAX_LLM_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LLM_DISCOVERY_BYTES = 2 * 1024 * 1024
MAX_LLM_TOTAL_SECONDS = 120.0
MAX_LLM_CONNECT_SECONDS = 10.0
MAX_LLM_READ_SECONDS = 15.0
MAX_LLM_CONCURRENT_CALLS = 4
_READ_CHUNK_BYTES = 8192
_MAX_JSON_DEPTH = 64
_call_slots = threading.BoundedSemaphore(MAX_LLM_CONCURRENT_CALLS)
_Result = TypeVar("_Result")


class LLMResourceLimitError(ValueError):
    """A safe, credential-free failure caused by a hard LLM resource bound."""


def require_text_bytes(text: str, *, label: str, maximum: int) -> str:
    # A character is at least one UTF-8 byte, so reject giant inputs before encoding.
    if len(text) > maximum:
        raise LLMResourceLimitError(f"LLM {label} exceeds the {maximum}-byte limit.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise LLMResourceLimitError(f"LLM {label} is not valid UTF-8 text.") from exc
    if size > maximum:
        raise LLMResourceLimitError(f"LLM {label} exceeds the {maximum}-byte limit.")
    return text


def require_http_request_bounds(url: str, headers: dict[str, str]) -> None:
    require_text_bytes(url, label="request URL", maximum=MAX_LLM_URL_BYTES)
    header_bytes = 0
    for name, value in headers.items():
        require_text_bytes(name, label="request headers", maximum=MAX_LLM_HEADER_BYTES)
        require_text_bytes(value, label="request headers", maximum=MAX_LLM_HEADER_BYTES)
        header_bytes += len(name.encode("utf-8")) + len(value.encode("utf-8")) + 4
        if header_bytes > MAX_LLM_HEADER_BYTES:
            raise LLMResourceLimitError(f"LLM request headers exceed the {MAX_LLM_HEADER_BYTES}-byte limit.")


def _preflight_json_size(value: object, *, label: str, maximum: int) -> None:
    """Reject giant values before JSONEncoder copies or escapes their contents."""

    remaining = maximum
    stack: list[tuple[object, bool, int]] = [(value, False, 0)]
    active_containers: set[int] = set()
    while stack:
        current, exiting, depth = stack.pop()
        if exiting:
            active_containers.remove(id(current))
            continue
        if isinstance(current, str):
            remaining -= len(current)
        elif isinstance(current, dict):
            remaining -= 2 + max(0, len(current) - 1)
        elif isinstance(current, (list, tuple)):
            remaining -= 2 + max(0, len(current) - 1)
        else:
            remaining -= 1
        if remaining < 0:
            raise LLMResourceLimitError(f"LLM {label} exceeds the {maximum}-byte limit.")
        if isinstance(current, (dict, list, tuple)):
            if depth >= _MAX_JSON_DEPTH or id(current) in active_containers:
                raise LLMResourceLimitError(f"LLM {label} has excessive nesting or a cycle.")
            active_containers.add(id(current))
            stack.append((current, True, depth))
            if isinstance(current, dict):
                for key, item in current.items():
                    stack.extend(((key, False, depth + 1), (item, False, depth + 1)))
            else:
                stack.extend((item, False, depth + 1) for item in current)


def bounded_json_bytes(value: object, *, label: str, maximum: int, sort_keys: bool = False) -> bytes:
    """Encode JSON incrementally so the full serialized body cannot grow unbounded."""

    _preflight_json_size(value, label=label, maximum=maximum)
    encoded: list[bytes] = []
    total = 0
    try:
        encoder = json.JSONEncoder(
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=sort_keys,
        )
        for part in encoder.iterencode(value):
            if len(part) > maximum - total:
                raise LLMResourceLimitError(f"LLM {label} exceeds the {maximum}-byte limit.")
            chunk = part.encode("utf-8")
            total += len(chunk)
            if total > maximum:
                raise LLMResourceLimitError(f"LLM {label} exceeds the {maximum}-byte limit.")
            encoded.append(chunk)
    except (TypeError, UnicodeError, ValueError) as exc:
        if isinstance(exc, LLMResourceLimitError):
            raise
        raise LLMResourceLimitError(f"LLM {label} cannot be encoded as JSON.") from exc
    return b"".join(encoded)


def effective_timeout_seconds(value: object) -> float:
    try:
        requested = float(str(value))
    except (TypeError, ValueError, OverflowError):
        requested = 30.0
    if not math.isfinite(requested) or requested <= 0:
        requested = 30.0
    return min(MAX_LLM_TOTAL_SECONDS, max(1.0, requested))


def socket_timeouts(total_seconds: float) -> tuple[float, float]:
    return (
        min(MAX_LLM_CONNECT_SECONDS, total_seconds),
        min(MAX_LLM_READ_SECONDS, total_seconds),
    )


def check_deadline(deadline: float, cancelled: threading.Event | None = None) -> None:
    if (cancelled is not None and cancelled.is_set()) or time.monotonic() >= deadline:
        raise LLMResourceLimitError("LLM response exceeded its total deadline.")


def run_with_total_deadline(
    operation: Callable[[float, threading.Event, Callable[[Any], None]], _Result],
    *,
    total_seconds: float,
) -> _Result:
    """Return at the wall deadline; hold capacity until the network worker exits.

    A DNS resolver or blocked socket read cannot be interrupted reliably from
    another thread. Its daemon worker keeps a semaphore slot until it actually
    stops, so stalled calls cannot spawn unbounded transport threads. The
    cancellation flag is checked whenever the worker regains control.
    """

    slots = _call_slots
    if not slots.acquire(blocking=False):
        raise LLMResourceLimitError("LLM request capacity is full; try again after an active call finishes.")
    deadline = time.monotonic() + total_seconds
    cancelled = threading.Event()
    finished: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def register_response(response: Any) -> None:
        if cancelled.is_set():
            response.close()
            raise LLMResourceLimitError("LLM response exceeded its total deadline.")

    def cancel() -> None:
        cancelled.set()

    def run() -> None:
        try:
            outcome: tuple[bool, object] = (True, operation(deadline, cancelled, register_response))
        except BaseException as exc:
            outcome = (False, exc)
        finally:
            slots.release()
        finished.put_nowait(outcome)

    try:
        threading.Thread(target=run, name="llm-http-bound", daemon=True).start()
    except BaseException:
        slots.release()
        raise
    try:
        remaining = max(0.0, deadline - time.monotonic())
        succeeded, value = finished.get(timeout=remaining)
    except queue.Empty as exc:
        cancel()
        raise LLMResourceLimitError("LLM response exceeded its total deadline.") from exc
    except BaseException:
        cancel()
        raise
    if not succeeded:
        raise value  # type: ignore[misc]
    return value  # type: ignore[return-value]


def read_bounded_json(
    response: Any,
    *,
    maximum: int,
    deadline: float,
    cancelled: threading.Event | None = None,
) -> object:
    """Read at most ``maximum`` decoded response bytes before JSON allocation."""

    headers = getattr(response, "headers", {}) or {}
    content_length = headers.get("Content-Length")
    try:
        declared_length = int(content_length) if content_length is not None else None
    except (TypeError, ValueError):
        declared_length = None
    if declared_length is not None and declared_length > maximum:
        raise LLMResourceLimitError(f"LLM response exceeds the {maximum}-byte limit.")

    body = bytearray()
    check_deadline(deadline, cancelled)
    for chunk in response.iter_content(chunk_size=_READ_CHUNK_BYTES):
        check_deadline(deadline, cancelled)
        if not isinstance(chunk, bytes):
            raise LLMResourceLimitError("LLM response contained invalid bytes.")
        if len(body) + len(chunk) > maximum:
            raise LLMResourceLimitError(f"LLM response exceeds the {maximum}-byte limit.")
        body.extend(chunk)
        check_deadline(deadline, cancelled)
    try:
        return json.loads(body)
    except (UnicodeError, ValueError) as exc:
        raise LLMResourceLimitError("LLM response was not valid JSON.") from exc
