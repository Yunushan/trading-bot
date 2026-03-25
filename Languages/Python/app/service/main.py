"""
Headless service entrypoint.

This entrypoint now supports both local runtime inspection and the optional
HTTP service API. Its job is to provide a stable non-GUI boundary so backend
work can grow without coupling new logic to `Languages/Python/main.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.api import run_service_api_server
    from app.service.runtime import TradingBotService
    from app.service.schemas.control import make_start_request, make_stop_request
else:
    from .api import run_service_api_server
    from .runtime import TradingBotService
    from .schemas.control import make_start_request, make_stop_request


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.service.main",
        description="Phase-1 headless service entrypoint for Trading Bot.",
    )
    control_group = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print service descriptor and status as JSON.",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Return a simple ok line for future process/container checks.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the optional HTTP service API.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host binding for --serve. Default: 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for --serve. Default: 8000",
    )
    parser.add_argument(
        "--api-token",
        default="",
        help="Optional bearer token for protecting the HTTP API.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the current service status snapshot.",
    )
    parser.add_argument(
        "--config-summary",
        action="store_true",
        help="Print the current sanitized config summary.",
    )
    parser.add_argument(
        "--account-snapshot",
        action="store_true",
        help="Print the current account snapshot.",
    )
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
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Print recent service log events.",
    )
    parser.add_argument(
        "--record-log",
        help="Record a single service log message before printing output.",
    )
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
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Requested job count for --request-start.",
    )
    parser.add_argument(
        "--close-positions",
        action="store_true",
        help="Flag close-all intent for --request-stop.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    if args.healthcheck:
        print("ok")
        return 0

    if args.serve:
        run_service_api_server(
            host=args.host,
            port=args.port,
            api_token=args.api_token,
        )
        return 0

    service = TradingBotService()
    service.enable_local_executor()
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
    elif args.request_stop:
        control_result = service.request_stop(
            make_stop_request(close_positions=args.close_positions, source="service-cli")
        )
        status = service.get_status()
    if args.logs:
        logs = [item.to_dict() for item in service.get_recent_logs(limit=50)]
    if args.json:
        payload = {
            "account_snapshot": account_snapshot.to_dict(),
            "config_summary": config_summary.to_dict(),
            "control_result": control_result.to_dict() if control_result else None,
            "execution_snapshot": execution_snapshot.to_dict(),
            "log_event": log_event.to_dict() if log_event else None,
            "logs": logs,
            "backtest_snapshot": backtest_snapshot.to_dict(),
            "portfolio_snapshot": portfolio_snapshot.to_dict(),
            "runtime": descriptor.to_dict(),
            "status": status.to_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.status:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0

    if args.config_summary:
        print(json.dumps(config_summary.to_dict(), indent=2, sort_keys=True))
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
    print(f"Current mode: {status.mode}")
    print(f"Account type: {status.account_type}")
    print(f"Exchange: {status.selected_exchange}")
    print(f"Configured symbols: {config_summary.symbol_count}")
    print(f"Enabled indicators: {config_summary.enabled_indicator_count}")
    print("Remote API: available via --serve")
    print("Web dashboard: /ui/ when the API server is running")
    print("Backtest API: /api/backtest plus /api/backtest/run and /api/backtest/stop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
