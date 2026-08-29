from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import ssl
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from uuid import uuid4

import requests

from ...security.redaction import redact_text, redact_value
from ...settings.exchange_support import (
    METATRADER4_BRIDGE_BROKERS,
    METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES,
    build_exchange_support_payload,
)


MT4_BRIDGE_PROTOCOL_VERSION = "1"
MT4_BRIDGE_METAQUOTES_SOURCES = (
    "https://docs.mql4.com/common/webrequest",
    "https://docs.mql4.com/trading/ordersend",
    "https://docs.mql4.com/trading/orderclose",
    "https://docs.mql4.com/trading/orderdelete",
)
MT4_BRIDGE_PROVIDERS: tuple[str, ...] = METATRADER4_BRIDGE_BROKERS
MT4_BRIDGE_DEFAULT_URL = "http://127.0.0.1:8765"
MT4_BRIDGE_TOKEN_HEADER = "X-MT4-Bridge-Token"  # noqa: S105 - header name, not a credential
MT4_BRIDGE_ALLOWED_OPERATIONS = frozenset(
    {
        "account_snapshot",
        "market_snapshot",
        "open_positions_snapshot",
        "open_orders_snapshot",
        "market_order",
        "cancel_order",
        "close_position",
    }
)

_TERMINAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_MAX_BODY_BYTES = 1_048_576
MT4_BRIDGE_MAX_TOKEN_UTF8_BYTES = 512
MT4_BRIDGE_MAX_REQUEST_TIMEOUT_SECONDS = 300.0
MT4_BRIDGE_MAX_OPERATION_TIMEOUT_SECONDS = 1_800.0
MT4_BRIDGE_MAX_POLL_INTERVAL_SECONDS = 60.0
MT4_BRIDGE_MAX_COMMAND_PAYLOAD_FIELDS = 128
MT4_BRIDGE_MAX_FORM_FIELDS = 16
MT4_BRIDGE_MAX_ERROR_MESSAGE_UTF8_BYTES = 4_096
MT4_BRIDGE_MAX_COMMANDS = 10_000


def _provider_key(value: object) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


_PROVIDERS_BY_KEY = {_provider_key(provider): provider for provider in MT4_BRIDGE_PROVIDERS}


def _canonical_provider(value: object) -> str:
    provider = _PROVIDERS_BY_KEY.get(_provider_key(value), "")
    if provider:
        return provider
    supported = ", ".join(MT4_BRIDGE_PROVIDERS)
    raise ValueError(f"provider must be one of: {supported}")


def _clean_terminal_id(value: object) -> str:
    terminal_id = str(value or "").strip()
    if not _TERMINAL_ID_PATTERN.fullmatch(terminal_id):
        raise ValueError("terminal_id must contain 1-64 ASCII letters, digits, dots, underscores, or hyphens")
    return terminal_id


def _is_loopback_host(hostname: str | None) -> bool:
    host = str(hostname or "").strip().lower().strip("[]")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if host.startswith("127.") or host == "::1":
        return True
    return False


def _clean_bridge_url(value: object, *, allow_insecure_remote: bool) -> str:
    text = _clean_protocol_text(
        value or MT4_BRIDGE_DEFAULT_URL,
        field_name="bridge_url",
        max_utf8_bytes=2_048,
        required=True,
    ).rstrip("/")
    if "\\" in text:
        raise ValueError("bridge_url must not contain backslashes")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("bridge_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("bridge_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("bridge_url must not contain a query string or fragment")
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname) and not allow_insecure_remote:
        raise ValueError("remote MT4 bridge URLs must use HTTPS")
    return text


def _positive_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive number")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a positive number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return parsed


def _bounded_positive_float(value: object, *, field_name: str, maximum: float) -> float:
    parsed = _positive_float(value, field_name=field_name)
    if parsed > maximum:
        raise ValueError(f"{field_name} must be at most {maximum:g}")
    return parsed


def _optional_positive_float(value: object | None, *, field_name: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _positive_float(value, field_name=field_name)


def _nonnegative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0 or str(value).strip() not in {str(parsed), f"+{parsed}"}:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


def _positive_ticket(value: object) -> int:
    ticket = _nonnegative_int(value, field_name="ticket")
    if ticket == 0:
        raise ValueError("ticket must be a positive integer")
    return ticket


def _clean_protocol_text(
    value: object,
    *,
    field_name: str,
    max_utf8_bytes: int,
    required: bool = False,
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field_name} is required")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(f"{field_name} must not contain control characters")
    if len(text.encode("utf-8")) > max_utf8_bytes:
        raise ValueError(f"{field_name} must contain at most {max_utf8_bytes} UTF-8 bytes")
    return text


def _clean_bridge_token(value: object, *, required: bool = False) -> str:
    token = _clean_protocol_text(
        value,
        field_name="bridge token",
        max_utf8_bytes=MT4_BRIDGE_MAX_TOKEN_UTF8_BYTES,
        required=required,
    )
    if token and len(token) < 16:
        raise ValueError("bridge token must contain at least 16 characters")
    return token


def _primitive_payload(payload: object) -> dict[str, str | int | float | bool | None]:
    if not isinstance(payload, dict):
        raise ValueError("command payload must be a JSON object")
    if len(payload) > MT4_BRIDGE_MAX_COMMAND_PAYLOAD_FIELDS:
        raise ValueError(
            f"command payload must contain at most {MT4_BRIDGE_MAX_COMMAND_PAYLOAD_FIELDS} fields"
        )
    clean: dict[str, str | int | float | bool | None] = {}
    for raw_key, value in payload.items():
        key = str(raw_key or "").strip()
        if not key or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
            raise ValueError("command payload keys must be lower-case identifier names")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"command payload field '{key}' must be a scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"command payload field '{key}' must be finite")
        clean[key] = value
    return clean


@dataclass
class _BridgeCommand:
    command_id: str
    terminal_id: str
    provider: str
    operation: str
    payload: dict[str, str | int | float | bool | None]
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "queued"
    dispatch_attempts: int = 0
    lease_until: float = 0.0
    result: object = None
    error_code: int = 0
    error_message: str = ""

    def snapshot(self) -> dict[str, object]:
        return {
            "protocol_version": MT4_BRIDGE_PROTOCOL_VERSION,
            "command_id": self.command_id,
            "terminal_id": self.terminal_id,
            "provider": self.provider,
            "operation": self.operation,
            "payload": dict(self.payload),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "dispatch_attempts": self.dispatch_attempts,
            "result": self.result,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    def agent_payload(self) -> dict[str, str]:
        values = {
            "protocol": MT4_BRIDGE_PROTOCOL_VERSION,
            "command_id": self.command_id,
            "provider": self.provider,
            "operation": self.operation,
        }
        values.update(
            {
                key: "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in self.payload.items()
            }
        )
        return values


class MetaTrader4BridgeState:
    """Thread-safe command queue shared by the bridge HTTP host and MT4 agents."""

    def __init__(
        self,
        *,
        command_lease_seconds: float = 15.0,
        retention_seconds: float = 3_600.0,
        max_commands: int = 1_000,
    ) -> None:
        self.command_lease_seconds = _positive_float(
            command_lease_seconds,
            field_name="command_lease_seconds",
        )
        self.retention_seconds = _positive_float(retention_seconds, field_name="retention_seconds")
        self.max_commands = _nonnegative_int(max_commands, field_name="max_commands")
        if self.max_commands == 0:
            raise ValueError("max_commands must be a positive integer")
        if self.max_commands > MT4_BRIDGE_MAX_COMMANDS:
            raise ValueError(f"max_commands must be at most {MT4_BRIDGE_MAX_COMMANDS}")
        self._commands: dict[str, _BridgeCommand] = {}
        self._lock = threading.RLock()

    def _purge(self, now: float) -> None:
        expired = [
            command_id
            for command_id, command in self._commands.items()
            if command.status in {"completed", "failed"} and now - command.updated_at >= self.retention_seconds
        ]
        for command_id in expired:
            self._commands.pop(command_id, None)

    def enqueue(
        self,
        *,
        terminal_id: object,
        provider: object,
        operation: object,
        payload: object,
    ) -> dict[str, object]:
        clean_terminal = _clean_terminal_id(terminal_id)
        clean_provider = _canonical_provider(provider)
        clean_operation = str(operation or "").strip().lower()
        if clean_operation not in MT4_BRIDGE_ALLOWED_OPERATIONS:
            choices = ", ".join(sorted(MT4_BRIDGE_ALLOWED_OPERATIONS))
            raise ValueError(f"operation must be one of: {choices}")
        clean_payload = _primitive_payload(payload)
        now = time.time()
        with self._lock:
            self._purge(now)
            active_count = sum(command.status not in {"completed", "failed"} for command in self._commands.values())
            if active_count >= self.max_commands:
                raise RuntimeError("MT4 bridge command queue is full")
            command = _BridgeCommand(
                command_id=uuid4().hex,
                terminal_id=clean_terminal,
                provider=clean_provider,
                operation=clean_operation,
                payload=clean_payload,
            )
            self._commands[command.command_id] = command
            return command.snapshot()

    def claim_next(self, terminal_id: object) -> dict[str, str] | None:
        clean_terminal = _clean_terminal_id(terminal_id)
        now = time.time()
        with self._lock:
            self._purge(now)
            for command in self._commands.values():
                if command.terminal_id != clean_terminal:
                    continue
                if command.status == "dispatched" and command.lease_until <= now:
                    command.status = "queued"
                if command.status != "queued":
                    continue
                command.status = "dispatched"
                command.dispatch_attempts += 1
                command.lease_until = now + self.command_lease_seconds
                command.updated_at = now
                return command.agent_payload()
        return None

    def complete(
        self,
        *,
        terminal_id: object,
        command_id: object,
        status: object,
        result: object,
        error_code: object = 0,
        error_message: object = "",
    ) -> dict[str, object]:
        clean_terminal = _clean_terminal_id(terminal_id)
        clean_command_id = str(command_id or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{32}", clean_command_id):
            raise ValueError("command_id must be a 32-character hexadecimal identifier")
        clean_status = str(status or "").strip().lower()
        if clean_status not in {"completed", "failed"}:
            raise ValueError("result status must be 'completed' or 'failed'")
        clean_error_code = _nonnegative_int(error_code, field_name="error_code")
        clean_error_message = _clean_protocol_text(
            error_message,
            field_name="error_message",
            max_utf8_bytes=MT4_BRIDGE_MAX_ERROR_MESSAGE_UTF8_BYTES,
        )
        with self._lock:
            command = self._commands.get(clean_command_id)
            if command is None:
                raise KeyError("unknown command_id")
            if command.terminal_id != clean_terminal:
                raise PermissionError("command belongs to a different terminal")
            if command.status in {"completed", "failed"}:
                return command.snapshot()
            if command.status != "dispatched":
                raise RuntimeError("command has not been dispatched")
            command.status = clean_status
            command.result = result
            command.error_code = clean_error_code
            command.error_message = clean_error_message
            command.updated_at = time.time()
            command.lease_until = 0.0
            return command.snapshot()

    def command_snapshot(self, command_id: object) -> dict[str, object]:
        clean_command_id = str(command_id or "").strip().lower()
        with self._lock:
            command = self._commands.get(clean_command_id)
            if command is None:
                raise KeyError("unknown command_id")
            return command.snapshot()

    def health_snapshot(self) -> dict[str, object]:
        with self._lock:
            counts = {status: 0 for status in ("queued", "dispatched", "completed", "failed")}
            for command in self._commands.values():
                counts[command.status] = counts.get(command.status, 0) + 1
        return {
            "service": "metatrader4-bridge",
            "protocol_version": MT4_BRIDGE_PROTOCOL_VERSION,
            "status": "ok",
            "command_counts": counts,
            "supported_operations": sorted(MT4_BRIDGE_ALLOWED_OPERATIONS),
        }


def _bridge_handler(
    state: MetaTrader4BridgeState,
    token: str,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "TradingBotMT4Bridge/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _authorized(self) -> bool:
            provided = str(self.headers.get(MT4_BRIDGE_TOKEN_HEADER, ""))
            return bool(provided) and secrets.compare_digest(provided, token)

        def _send_bytes(
            self,
            status_code: int,
            body: bytes = b"",
            *,
            content_type: str = "application/json; charset=utf-8",
        ) -> None:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _send_json(self, status_code: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self._send_bytes(status_code, body)

        def _send_error_json(self, status_code: int, message: object) -> None:
            self._send_json(status_code, {"error": redact_text(str(message or "request failed"))})

        def _read_body(self) -> bytes:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Content-Length must be an integer") from exc
            if length < 0 or length > _MAX_BODY_BYTES:
                raise ValueError("request body is too large")
            return self.rfile.read(length) if length else b""

        def _read_json_object(self) -> dict[str, object]:
            body = self._read_body()
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _read_agent_result(self) -> dict[str, object]:
            body = self._read_body()
            content_type = str(self.headers.get("Content-Type", "")).lower()
            if "application/json" in content_type:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("agent result must be valid UTF-8 JSON") from exc
                if not isinstance(payload, dict):
                    raise ValueError("agent result must be a JSON object")
                return payload
            values = parse_qs(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=MT4_BRIDGE_MAX_FORM_FIELDS,
            )
            payload_json = values.get("payload_json", ["null"])[0]
            try:
                result = json.loads(payload_json)
            except json.JSONDecodeError as exc:
                raise ValueError("payload_json must be valid JSON") from exc
            return {
                "command_id": values.get("command_id", [""])[0],
                "status": values.get("status", [""])[0],
                "result": result,
                "error_code": values.get("error_code", ["0"])[0],
                "error_message": values.get("error_message", [""])[0],
            }

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self._send_error_json(HTTPStatus.UNAUTHORIZED, "invalid bridge token")
            return False

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            path = urlsplit(self.path).path.rstrip("/") or "/"
            try:
                if path == "/v1/health":
                    self._send_json(HTTPStatus.OK, state.health_snapshot())
                    return
                command_prefix = "/v1/commands/"
                if path.startswith(command_prefix):
                    command_id = unquote(path[len(command_prefix) :])
                    self._send_json(HTTPStatus.OK, state.command_snapshot(command_id))
                    return
                agent_prefix = "/v1/agents/"
                agent_suffix = "/next"
                if path.startswith(agent_prefix) and path.endswith(agent_suffix):
                    terminal_id = unquote(path[len(agent_prefix) : -len(agent_suffix)]).strip("/")
                    command = state.claim_next(terminal_id)
                    if command is None:
                        self._send_bytes(HTTPStatus.NO_CONTENT)
                        return
                    body = urlencode(command).encode("ascii")
                    self._send_bytes(
                        HTTPStatus.OK,
                        body,
                        content_type="application/x-www-form-urlencoded; charset=utf-8",
                    )
                    return
                self._send_error_json(HTTPStatus.NOT_FOUND, "route not found")
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, exc.args[0])
            except (PermissionError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, exc)
            except (OSError, TypeError) as exc:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, exc)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            path = urlsplit(self.path).path.rstrip("/") or "/"
            try:
                if path == "/v1/commands":
                    payload = self._read_json_object()
                    command = state.enqueue(
                        terminal_id=payload.get("terminal_id"),
                        provider=payload.get("provider"),
                        operation=payload.get("operation"),
                        payload=payload.get("payload", {}),
                    )
                    self._send_json(HTTPStatus.ACCEPTED, command)
                    return
                agent_prefix = "/v1/agents/"
                agent_suffix = "/results"
                if path.startswith(agent_prefix) and path.endswith(agent_suffix):
                    terminal_id = unquote(path[len(agent_prefix) : -len(agent_suffix)]).strip("/")
                    payload = self._read_agent_result()
                    command = state.complete(
                        terminal_id=terminal_id,
                        command_id=payload.get("command_id"),
                        status=payload.get("status"),
                        result=payload.get("result"),
                        error_code=payload.get("error_code", 0),
                        error_message=payload.get("error_message", ""),
                    )
                    self._send_json(HTTPStatus.OK, command)
                    return
                self._send_error_json(HTTPStatus.NOT_FOUND, "route not found")
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, exc.args[0])
            except PermissionError as exc:
                self._send_error_json(HTTPStatus.FORBIDDEN, exc)
            except (RuntimeError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, exc)
            except (OSError, TypeError) as exc:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, exc)

    return Handler


class _BridgeHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MetaTrader4BridgeServer:
    """Included token-authenticated host polled by the MT4 Expert Advisor."""

    def __init__(
        self,
        *,
        token: str,
        host: str = "127.0.0.1",
        port: int = 8765,
        certfile: str = "",
        keyfile: str = "",
        advertised_host: str = "",
        state: MetaTrader4BridgeState | None = None,
    ) -> None:
        self.token = _clean_bridge_token(token, required=True)
        self.host = _clean_protocol_text(
            host or "127.0.0.1",
            field_name="host",
            max_utf8_bytes=255,
            required=True,
        )
        self.port = _nonnegative_int(port, field_name="port")
        if self.port > 65_535:
            raise ValueError("port must be at most 65535")
        self.certfile = _clean_protocol_text(
            certfile,
            field_name="certfile",
            max_utf8_bytes=4_096,
        )
        self.keyfile = _clean_protocol_text(
            keyfile,
            field_name="keyfile",
            max_utf8_bytes=4_096,
        )
        if bool(self.certfile) != bool(self.keyfile):
            raise ValueError("certfile and keyfile must be provided together")
        if not _is_loopback_host(self.host) and not self.certfile:
            raise ValueError("non-loopback MT4 bridge hosts require certfile and keyfile")
        self.advertised_host = _clean_protocol_text(
            advertised_host or self.host,
            field_name="advertised_host",
            max_utf8_bytes=255,
            required=True,
        )
        self.state = state or MetaTrader4BridgeState()
        self._server: _BridgeHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def base_url(self) -> str:
        if self._server is None:
            port = self.port
        else:
            port = int(self._server.server_address[1])
        scheme = "https" if self.certfile else "http"
        host = self.advertised_host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{scheme}://{host}:{port}"

    def start(self) -> MetaTrader4BridgeServer:
        if self.running:
            return self
        handler = _bridge_handler(self.state, self.token)
        server = _BridgeHttpServer((self.host, self.port), handler)
        if self.certfile:
            certfile = Path(self.certfile).expanduser().resolve(strict=True)
            keyfile = Path(self.keyfile).expanduser().resolve(strict=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certfile=str(certfile), keyfile=str(keyfile))
            server.socket = context.wrap_socket(server.socket, server_side=True)
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="metatrader4-bridge",
            daemon=True,
        )
        self._thread.start()
        return self

    def close(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5.0)

    def __enter__(self) -> MetaTrader4BridgeServer:
        return self.start()

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


class MetaTrader4BridgeConnector:
    """Guarded client for the included MT4 local/remote Expert Advisor bridge."""

    def __init__(
        self,
        *,
        provider: str,
        terminal_id: str,
        token: str = "",
        bridge_url: str = MT4_BRIDGE_DEFAULT_URL,
        request_timeout: float = 10.0,
        operation_timeout: float = 30.0,
        poll_interval: float = 0.1,
        verify_tls: bool | str = True,
        allow_insecure_remote: bool = False,
        session: Any | None = None,
    ) -> None:
        self.provider = _canonical_provider(provider)
        self.terminal_id = _clean_terminal_id(terminal_id)
        self.token = _clean_bridge_token(token)
        self.bridge_url = _clean_bridge_url(
            bridge_url,
            allow_insecure_remote=bool(allow_insecure_remote),
        )
        self.request_timeout = _bounded_positive_float(
            request_timeout,
            field_name="request_timeout",
            maximum=MT4_BRIDGE_MAX_REQUEST_TIMEOUT_SECONDS,
        )
        self.operation_timeout = _bounded_positive_float(
            operation_timeout,
            field_name="operation_timeout",
            maximum=MT4_BRIDGE_MAX_OPERATION_TIMEOUT_SECONDS,
        )
        self.poll_interval = _bounded_positive_float(
            poll_interval,
            field_name="poll_interval",
            maximum=MT4_BRIDGE_MAX_POLL_INTERVAL_SECONDS,
        )
        self.verify_tls = verify_tls
        self.session = session or requests.Session()

    def support_payload(self) -> dict[str, object]:
        return build_exchange_support_payload(
            config={
                "selected_exchange": "",
                "connector_backend": "metatrader4-bridge",
                "selected_forex_broker": self.provider,
            }
        )

    def build_capability_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                "selected_broker": self.provider,
                "selected_forex_broker": self.provider,
                "connector_backend": "metatrader4-bridge",
                "official_transport_source": METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES[self.provider],
                "bridge_protocol_sources": list(MT4_BRIDGE_METAQUOTES_SOURCES),
                "bridge_protocol_version": MT4_BRIDGE_PROTOCOL_VERSION,
                "bridge_url": self.bridge_url,
                "terminal_id": self.terminal_id,
                "token_present": bool(self.token),
                "request_timeout": self.request_timeout,
                "operation_timeout": self.operation_timeout,
                "verify_tls": bool(self.verify_tls),
                "supported_operations": sorted(MT4_BRIDGE_ALLOWED_OPERATIONS),
                "support": self.support_payload(),
            }
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            MT4_BRIDGE_TOKEN_HEADER: self.token,
        }

    def _require_token(self) -> None:
        if len(self.token) < 16:
            raise RuntimeError("MT4 bridge requests require a token containing at least 16 characters")

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        accepted_statuses: tuple[int, ...] = (HTTPStatus.OK,),
    ) -> dict[str, object]:
        self._require_token()
        response = self.session.request(
            method,
            f"{self.bridge_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=payload,
            timeout=self.request_timeout,
            verify=self.verify_tls,
            allow_redirects=False,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"MT4 bridge returned non-JSON HTTP {status_code}: {redact_text(str(exc))}") from exc
        if not isinstance(response_payload, dict):
            raise RuntimeError("MT4 bridge response must be a JSON object")
        if status_code not in {int(status) for status in accepted_statuses}:
            raise RuntimeError(f"MT4 bridge request failed with HTTP {status_code}: {redact_value(response_payload)}")
        return response_payload

    def fetch_bridge_snapshot(self) -> dict[str, object]:
        health = self._request("GET", "/v1/health")
        return redact_value({**self.build_capability_snapshot(), "bridge": health})

    def _execute(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        queued = self._request(
            "POST",
            "/v1/commands",
            payload={
                "terminal_id": self.terminal_id,
                "provider": self.provider,
                "operation": operation,
                "payload": payload,
            },
            accepted_statuses=(HTTPStatus.ACCEPTED,),
        )
        command_id = str(queued.get("command_id", "")).strip()
        if not re.fullmatch(r"[0-9a-f]{32}", command_id):
            raise RuntimeError("MT4 bridge did not return a valid command_id")
        deadline = time.monotonic() + self.operation_timeout
        while True:
            command = self._request("GET", f"/v1/commands/{quote(command_id, safe='')}")
            status = str(command.get("status", "")).strip().lower()
            if status == "completed":
                return command
            if status == "failed":
                error_code = command.get("error_code", 0)
                error_message = redact_text(str(command.get("error_message", "MT4 command failed")))
                raise RuntimeError(f"MT4 command failed ({error_code}): {error_message}")
            if status not in {"queued", "dispatched"}:
                raise RuntimeError(f"MT4 bridge returned unknown command status '{status}'")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"MT4 command {command_id} timed out after {self.operation_timeout:g} seconds")
            time.sleep(self.poll_interval)

    def _snapshot_result(self, operation: str, payload: dict[str, object]) -> object:
        command = self._execute(operation, payload)
        return redact_value(command.get("result"))

    def fetch_account_snapshot(self) -> dict[str, object]:
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "account": self._snapshot_result("account_snapshot", {}),
            }
        )

    def fetch_market_snapshot(self, symbol: str) -> dict[str, object]:
        clean_symbol = _clean_protocol_text(
            symbol,
            field_name="symbol",
            max_utf8_bytes=64,
            required=True,
        )
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "market": self._snapshot_result("market_snapshot", {"symbol": clean_symbol}),
            }
        )

    def fetch_open_positions_snapshot(self, symbol: str = "") -> dict[str, object]:
        clean_symbol = _clean_protocol_text(
            symbol,
            field_name="symbol",
            max_utf8_bytes=64,
        )
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "positions": self._snapshot_result(
                    "open_positions_snapshot",
                    {"symbol": clean_symbol},
                ),
            }
        )

    def fetch_open_orders_snapshot(self, symbol: str = "") -> dict[str, object]:
        clean_symbol = _clean_protocol_text(
            symbol,
            field_name="symbol",
            max_utf8_bytes=64,
        )
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "symbol": clean_symbol,
                "orders": self._snapshot_result(
                    "open_orders_snapshot",
                    {"symbol": clean_symbol},
                ),
            }
        )

    def submit_market_order(
        self,
        *,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "trading-bot",
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        clean_symbol = _clean_protocol_text(
            symbol,
            field_name="symbol",
            max_utf8_bytes=64,
            required=True,
        )
        clean_side = str(side or "").strip().lower()
        if clean_side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        clean_comment = _clean_protocol_text(
            comment,
            field_name="comment",
            max_utf8_bytes=31,
        )
        command_payload: dict[str, object] = {
            "symbol": clean_symbol,
            "side": clean_side,
            "volume": _positive_float(volume, field_name="volume"),
            "stop_loss": _optional_positive_float(stop_loss, field_name="stop_loss") or 0.0,
            "take_profit": _optional_positive_float(take_profit, field_name="take_profit") or 0.0,
            "deviation": _nonnegative_int(deviation, field_name="deviation"),
            "magic": _nonnegative_int(magic, field_name="magic"),
            "comment": clean_comment,
        }
        if dry_run:
            return redact_value(
                {
                    **self.build_capability_snapshot(),
                    "status": "dry_run",
                    "operation": "market_order",
                    "request": command_payload,
                    "order": None,
                }
            )
        if not allow_live:
            raise RuntimeError("live MT4 order submission requires allow_live=True")
        order = self._snapshot_result("market_order", command_payload)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "submitted",
                "operation": "market_order",
                "request": command_payload,
                "order": order,
            }
        )

    def cancel_order(
        self,
        *,
        ticket: int,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        command_payload = {"ticket": _positive_ticket(ticket)}
        if dry_run:
            return redact_value(
                {
                    **self.build_capability_snapshot(),
                    "status": "dry_run",
                    "operation": "cancel_order",
                    "request": command_payload,
                    "order": None,
                }
            )
        if not allow_live:
            raise RuntimeError("live MT4 order cancellation requires allow_live=True")
        order = self._snapshot_result("cancel_order", command_payload)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "cancelled",
                "operation": "cancel_order",
                "request": command_payload,
                "order": order,
            }
        )

    def close_position(
        self,
        *,
        ticket: int,
        volume: float | None = None,
        deviation: int = 20,
        dry_run: bool = True,
        allow_live: bool = False,
    ) -> dict[str, object]:
        command_payload = {
            "ticket": _positive_ticket(ticket),
            "volume": _optional_positive_float(volume, field_name="volume") or 0.0,
            "deviation": _nonnegative_int(deviation, field_name="deviation"),
        }
        if dry_run:
            return redact_value(
                {
                    **self.build_capability_snapshot(),
                    "status": "dry_run",
                    "operation": "close_position",
                    "request": command_payload,
                    "order": None,
                }
            )
        if not allow_live:
            raise RuntimeError("live MT4 position close requires allow_live=True")
        order = self._snapshot_result("close_position", command_payload)
        return redact_value(
            {
                **self.build_capability_snapshot(),
                "status": "closed",
                "operation": "close_position",
                "request": command_payload,
                "order": order,
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the token-authenticated MetaTrader 4 bridge host")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile", default="")
    parser.add_argument("--keyfile", default="")
    parser.add_argument("--advertised-host", default="")
    parser.add_argument("--token-file", default="")
    args = parser.parse_args(argv)

    token = str(os.getenv("TRADING_BOT_MT4_BRIDGE_TOKEN", "")).strip()
    if args.token_file:
        token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
    if len(token) < 16:
        parser.error("set TRADING_BOT_MT4_BRIDGE_TOKEN or --token-file to a token containing at least 16 characters")

    server = MetaTrader4BridgeServer(
        token=token,
        host=args.host,
        port=args.port,
        certfile=args.certfile,
        keyfile=args.keyfile,
        advertised_host=args.advertised_host,
    ).start()
    print(f"MetaTrader 4 bridge listening on {server.base_url}")
    try:
        while server.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0
    finally:
        server.close()
    return 0


__all__ = [
    "MT4_BRIDGE_ALLOWED_OPERATIONS",
    "MT4_BRIDGE_DEFAULT_URL",
    "MT4_BRIDGE_MAX_COMMAND_PAYLOAD_FIELDS",
    "MT4_BRIDGE_MAX_COMMANDS",
    "MT4_BRIDGE_MAX_ERROR_MESSAGE_UTF8_BYTES",
    "MT4_BRIDGE_MAX_FORM_FIELDS",
    "MT4_BRIDGE_MAX_OPERATION_TIMEOUT_SECONDS",
    "MT4_BRIDGE_MAX_POLL_INTERVAL_SECONDS",
    "MT4_BRIDGE_MAX_REQUEST_TIMEOUT_SECONDS",
    "MT4_BRIDGE_MAX_TOKEN_UTF8_BYTES",
    "MT4_BRIDGE_METAQUOTES_SOURCES",
    "MT4_BRIDGE_PROTOCOL_VERSION",
    "MT4_BRIDGE_PROVIDERS",
    "MT4_BRIDGE_TOKEN_HEADER",
    "MetaTrader4BridgeConnector",
    "MetaTrader4BridgeServer",
    "MetaTrader4BridgeState",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
