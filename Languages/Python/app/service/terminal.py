from __future__ import annotations

import json
import shlex
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from app.security.redaction import redact_text, redact_value


@dataclass(frozen=True, slots=True)
class ServiceTerminalCommandResult:
    accepted: bool
    command: str
    exit_code: int
    output: str
    source: str
    created_at: str
    command_type: str = "service-command"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_command(command: str) -> list[str]:
    text = str(command or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=not sys.platform.startswith("win"))
    except Exception:
        return text.split()


def _json_output(payload: object) -> str:
    return json.dumps(redact_value(payload), indent=2, sort_keys=True)


def _result(
    *,
    accepted: bool,
    command: str,
    output: str,
    source: str,
    exit_code: int = 0,
) -> ServiceTerminalCommandResult:
    return ServiceTerminalCommandResult(
        accepted=bool(accepted),
        command=redact_text(str(command or "").strip()),
        exit_code=int(exit_code),
        output=redact_text(output or ""),
        source=redact_text(str(source or "terminal").strip() or "terminal"),
        created_at=_now_iso(),
    )


def _help_text() -> str:
    return "\n".join(
        [
            "Trading Bot controlled terminal commands:",
            "  help",
            "  status",
            "  runtime",
            "  dashboard",
            "  logs [limit]",
            "  start [jobs]",
            "  stop [--close-positions]",
            "  backtest status",
            "  backtest run",
            "  backtest stop",
            "  config get",
            "  config set key=value [key=value...]",
            "  config patch {json-object}",
            "  llm providers",
            "  llm config",
            "  llm set key=value [key=value...]",
            "  llm prompt <text> [--send]",
            "",
            "This terminal does not execute operating-system shell commands.",
        ]
    )


def _parse_pairs(args: list[str]) -> dict[str, object]:
    patch: dict[str, object] = {}
    for item in args:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        clean_key = key.strip()
        clean_value = value.strip()
        if not clean_key:
            continue
        if clean_value.lower() in {"true", "false"}:
            patch[clean_key] = clean_value.lower() == "true"
        else:
            patch[clean_key] = clean_value
    return patch


def run_service_terminal_command(
    service,
    command: str,
    *,
    source: str = "terminal",
) -> ServiceTerminalCommandResult:
    argv = _split_command(command)
    if not argv:
        return _result(accepted=False, command=command, output="No command provided.", source=source, exit_code=2)

    root = argv[0].lower()
    args = argv[1:]

    try:
        if root in {"help", "?"}:
            return _result(accepted=True, command=command, output=_help_text(), source=source)
        if root == "status":
            return _result(accepted=True, command=command, output=_json_output(service.get_status().to_dict()), source=source)
        if root == "runtime":
            return _result(
                accepted=True,
                command=command,
                output=_json_output(service.describe_runtime().to_dict()),
                source=source,
            )
        if root == "dashboard":
            return _result(
                accepted=True,
                command=command,
                output=_json_output(service.get_dashboard_snapshot(log_limit=30)),
                source=source,
            )
        if root == "logs":
            limit = 25
            if args:
                try:
                    limit = max(1, min(100, int(args[0])))
                except Exception:
                    limit = 25
            logs = [item.to_dict() for item in service.get_recent_logs(limit=limit)]
            return _result(accepted=True, command=command, output=_json_output(logs), source=source)
        if root == "start":
            jobs = 1
            if args:
                try:
                    jobs = max(0, int(args[0]))
                except Exception:
                    jobs = 1
            result = service.request_start(requested_job_count=jobs, source=source).to_dict()
            return _result(accepted=True, command=command, output=_json_output(result), source=source)
        if root == "stop":
            close_positions = "--close-positions" in args
            result = service.request_stop(close_positions=close_positions, source=source).to_dict()
            return _result(accepted=True, command=command, output=_json_output(result), source=source)
        if root == "backtest":
            action = str(args[0] if args else "status").lower()
            if action == "run":
                result = service.submit_backtest({}, source=source).to_dict()
            elif action == "stop":
                result = service.stop_backtest(source=source).to_dict()
            elif action == "status":
                result = service.get_backtest_snapshot().to_dict()
            else:
                return _result(
                    accepted=False,
                    command=command,
                    output="Unknown backtest command. Use: backtest status, backtest run, or backtest stop.",
                    source=source,
                    exit_code=2,
                )
            return _result(accepted=True, command=command, output=_json_output(result), source=source)
        if root == "config":
            action = str(args[0] if args else "get").lower()
            if action == "get":
                result = service.get_config_payload().to_dict()
            elif action == "set":
                patch = _parse_pairs(args[1:])
                result = service.update_config(patch).to_dict()
            elif action == "patch":
                raw_json = " ".join(args[1:]).strip()
                patch = json.loads(raw_json) if raw_json else {}
                if not isinstance(patch, dict):
                    raise ValueError("config patch expects a JSON object.")
                result = service.update_config(patch).to_dict()
            else:
                return _result(
                    accepted=False,
                    command=command,
                    output="Unknown config command. Use: config get, config set, or config patch.",
                    source=source,
                    exit_code=2,
                )
            return _result(accepted=True, command=command, output=_json_output(result), source=source)
        if root == "llm":
            action = str(args[0] if args else "config").lower()
            if action == "providers":
                result = service.get_llm_provider_catalog()
            elif action == "config":
                result = service.get_llm_config_payload()
            elif action == "set":
                result = service.update_llm_config(_parse_pairs(args[1:]))
            elif action == "prompt":
                send = "--send" in args
                prompt_parts = [item for item in args[1:] if item != "--send"]
                prompt = " ".join(prompt_parts).strip()
                result = service.call_llm(
                    prompt=prompt,
                    dry_run=not send,
                    source=source,
                )
            else:
                return _result(
                    accepted=False,
                    command=command,
                    output="Unknown llm command. Use: llm providers, llm config, llm set, or llm prompt.",
                    source=source,
                    exit_code=2,
                )
            return _result(accepted=True, command=command, output=_json_output(result), source=source)
    except Exception as exc:
        return _result(accepted=False, command=command, output=str(exc), source=source, exit_code=1)

    return _result(
        accepted=False,
        command=command,
        output=f"Unknown command: {root}. Type help for supported commands.",
        source=source,
        exit_code=2,
    )


__all__ = ["ServiceTerminalCommandResult", "run_service_terminal_command"]
