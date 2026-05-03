"""
Canonical importable service product entrypoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.api import run_service_api_server
    from app.service.api_contract import SERVICE_API_BASE_PATH, service_api_route
    from app.service.runtime import TradingBotService
    from app.service.schemas.control import make_start_request, make_stop_request
    from app.settings import ConfigValidationError
else:
    from .api import run_service_api_server
    from .api_contract import SERVICE_API_BASE_PATH, service_api_route
    from .runtime import TradingBotService
    from .schemas.control import make_start_request, make_stop_request
    from ..settings import ConfigValidationError


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-bot-service",
        description="Phase-1 headless service entrypoint for Trading Bot.",
    )
    control_group = parser.add_mutually_exclusive_group()
    parser.add_argument("--json", action="store_true", help="Print service descriptor and status as JSON.")
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Return a simple ok line for future process/container checks.",
    )
    parser.add_argument("--serve", action="store_true", help="Run the optional HTTP service API.")
    parser.add_argument("--host", default="127.0.0.1", help="Host binding for --serve. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Port for --serve. Default: 8000")
    parser.add_argument(
        "--api-token",
        default="",
        help="Bearer token for the HTTP API; required when --host binds outside loopback.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Remote service API base URL for CLI control of an already running desktop/service host.",
    )
    parser.add_argument("--status", action="store_true", help="Print the current service status snapshot.")
    parser.add_argument(
        "--config-summary",
        action="store_true",
        help="Print the current sanitized config summary.",
    )
    parser.add_argument(
        "--config-persistence",
        action="store_true",
        help="Print durable service config file status.",
    )
    parser.add_argument("--account-snapshot", action="store_true", help="Print the current account snapshot.")
    parser.add_argument(
        "--portfolio-snapshot",
        action="store_true",
        help="Print the current portfolio snapshot.",
    )
    parser.add_argument(
        "--execution-snapshot",
        action="store_true",
        help="Print the current execution snapshot.",
    )
    parser.add_argument(
        "--backtest-snapshot",
        action="store_true",
        help="Print the current backtest snapshot.",
    )
    parser.add_argument("--logs", action="store_true", help="Print recent service log events.")
    parser.add_argument("--record-log", help="Record a single service log message before printing output.")
    parser.add_argument(
        "--terminal",
        help="Run one controlled service terminal command, for example: --terminal \"status\".",
    )
    parser.add_argument("--config-patch", help="Patch local service config with a JSON object before printing output.")
    parser.add_argument(
        "--config-path",
        default="",
        help="Durable service config JSON path. Defaults to ~/.trading-bot/service-config.json.",
    )
    parser.add_argument(
        "--load-config",
        action="store_true",
        help="Load durable service config before serving or applying local CLI patches.",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Persist the current local service config after applying CLI or terminal changes.",
    )
    parser.add_argument("--llm-providers", action="store_true", help="Print supported cloud/local LLM providers.")
    parser.add_argument("--llm-config", action="store_true", help="Print sanitized LLM configuration.")
    control_group.add_argument(
        "--request-start",
        action="store_true",
        help="Record a start request against the local service runtime skeleton.",
    )
    control_group.add_argument(
        "--request-stop",
        action="store_true",
        help="Record a stop request against the local service runtime skeleton.",
    )
    parser.add_argument("--jobs", type=int, default=0, help="Requested job count for --request-start.")
    parser.add_argument(
        "--close-positions",
        action="store_true",
        help="Flag close-all intent for --request-stop.",
    )
    return parser


def _remote_json_request(base_url: str, path: str, *, api_token: str = "", payload: dict | None = None):
    url = f"{str(base_url or '').rstrip('/')}{path}"
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    return json.loads(raw) if raw else None


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    if args.healthcheck:
        print("ok")
        return 0

    if args.serve:
        try:
            run_service_api_server(
                host=args.host,
                port=args.port,
                api_token=args.api_token,
                config_path=args.config_path or None,
                load_persisted_config=args.load_config,
            )
        except (ConfigValidationError, FileNotFoundError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0

    if args.base_url and args.terminal:
        try:
            remote_result = _remote_json_request(
                args.base_url,
                service_api_route("terminal_run"),
                api_token=args.api_token,
                payload={"command": args.terminal, "source": "service-cli-remote"},
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(remote_result, indent=2, sort_keys=True))
        else:
            print(str((remote_result or {}).get("output") or ""))
        return int((remote_result or {}).get("exit_code") or 0)

    try:
        service = TradingBotService(
            config_path=args.config_path or None,
            load_persisted_config=args.load_config,
        )
    except (ConfigValidationError, FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    service.enable_local_executor()
    if args.config_patch:
        try:
            config_patch = json.loads(args.config_patch)
        except Exception as exc:
            print(f"Invalid --config-patch JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(config_patch, dict):
            print("--config-patch expects a JSON object.", file=sys.stderr)
            return 2
        try:
            service.update_config(config_patch)
        except ConfigValidationError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    descriptor = service.describe_runtime()
    status = service.get_status()
    config_summary = service.get_config_summary()
    account_snapshot = service.get_account_snapshot()
    portfolio_snapshot = service.get_portfolio_snapshot()
    execution_snapshot = service.get_execution_snapshot()
    backtest_snapshot = service.get_backtest_snapshot()
    control_result = None
    log_event = None
    logs = []
    if args.record_log:
        log_event = service.record_log_event(args.record_log, source="service-cli", level="info")
    if args.request_start:
        control_result = service.request_start(
            make_start_request(requested_job_count=args.jobs, source="service-cli")
        )
        status = service.get_status()
        execution_snapshot = service.get_execution_snapshot()
    elif args.request_stop:
        control_result = service.request_stop(
            make_stop_request(close_positions=args.close_positions, source="service-cli")
        )
        status = service.get_status()
        execution_snapshot = service.get_execution_snapshot()
    if args.logs:
        logs = [item.to_dict() for item in service.get_recent_logs(limit=50)]
    terminal_result = None
    if args.terminal:
        terminal_result = service.run_terminal_command(args.terminal, source="service-cli-terminal")
    config_persistence_result = None
    if args.save_config:
        try:
            config_persistence_result = service.save_config(source="service-cli")
        except (ConfigValidationError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
    config_summary = service.get_config_summary()
    if args.json:
        payload = {
            "account_snapshot": account_snapshot.to_dict(),
            "config_summary": config_summary.to_dict(),
            "config_persistence": service.get_config_persistence_status(),
            "control_result": control_result.to_dict() if control_result else None,
            "execution_snapshot": execution_snapshot.to_dict(),
            "log_event": log_event.to_dict() if log_event else None,
            "logs": logs,
            "backtest_snapshot": backtest_snapshot.to_dict(),
            "portfolio_snapshot": portfolio_snapshot.to_dict(),
            "runtime": descriptor.to_dict(),
            "status": status.to_dict(),
            "terminal_result": terminal_result.to_dict() if terminal_result else None,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if terminal_result is not None:
        print(terminal_result.output)
        return int(terminal_result.exit_code)
    if args.llm_providers:
        print(json.dumps(service.get_llm_provider_catalog(), indent=2, sort_keys=True))
        return 0
    if args.llm_config:
        print(json.dumps(service.get_llm_config_payload(), indent=2, sort_keys=True))
        return 0

    if args.status:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.config_summary:
        print(json.dumps(config_summary.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.config_persistence or (args.save_config and config_persistence_result is not None):
        print(
            json.dumps(
                config_persistence_result or service.get_config_persistence_status(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.account_snapshot:
        print(json.dumps(account_snapshot.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.portfolio_snapshot:
        print(json.dumps(portfolio_snapshot.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.execution_snapshot:
        print(json.dumps(execution_snapshot.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.backtest_snapshot:
        print(json.dumps(backtest_snapshot.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.logs:
        print(json.dumps(logs, indent=2, sort_keys=True))
        return 0
    if control_result is not None:
        print(json.dumps(control_result.to_dict(), indent=2, sort_keys=True))
        return 0
    if log_event is not None:
        print(json.dumps(log_event.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Trading Bot service skeleton is available.")
    print(f"Phase: {descriptor.phase}")
    print(f"Python entrypoint: {descriptor.python_entrypoint}")
    print(f"Desktop entrypoint: {descriptor.desktop_entrypoint}")
    print(f"Docker optional: {descriptor.capabilities.docker_optional}")
    print(f"Control mode: {descriptor.control_plane.mode}")
    print(f"Control owner: {descriptor.control_plane.owner}")
    print(f"Execution scope: {descriptor.control_plane.execution_scope}")
    print(f"Trading execution supported: {descriptor.control_plane.trading_execution_supported}")
    print(f"Current mode: {status.mode}")
    print(f"Account type: {status.account_type}")
    print(f"Exchange: {status.selected_exchange}")
    print(f"Configured symbols: {config_summary.symbol_count}")
    print(f"Enabled indicators: {config_summary.enabled_indicator_count}")
    print("Remote API: available via --serve")
    print("Web dashboard: /ui/ when the API server is running")
    print("Standalone start/stop: lifecycle heartbeat only; no trading engines are launched.")
    print("Trading runtime: use desktop-hosted API mode until a headless trading executor is implemented.")
    print(
        "Backtest API: "
        f"{service_api_route('backtest')} plus "
        f"{service_api_route('backtest_run')} and "
        f"{service_api_route('backtest_stop')}"
    )
    print(f"Versioned API base path: {SERVICE_API_BASE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
