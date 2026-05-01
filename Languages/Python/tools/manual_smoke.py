from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


@dataclass
class SmokeStep:
    name: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class SmokeReport:
    steps: list[SmokeStep]

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "steps": [step.to_dict() for step in self.steps],
        }


def _python_env() -> dict[str, str]:
    env = dict(os.environ)
    existing_path = env.get("PYTHONPATH", "")
    paths = [str(PYTHON_ROOT)]
    if existing_path:
        paths.append(existing_path)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_step(steps: list[SmokeStep], name: str, func) -> None:
    try:
        detail = str(func() or "")
    except Exception as exc:
        steps.append(SmokeStep(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"))
        return
    steps.append(SmokeStep(name=name, ok=True, detail=detail))


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _http_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=str(method or "GET").upper(),
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw
        return int(exc.code), body


def _check_desktop_import() -> str:
    from app.desktop import EmbeddedDesktopServiceClient, create_desktop_service_client
    from app.desktop.product_main import main as desktop_main

    if not callable(desktop_main):
        raise RuntimeError("desktop product main is not callable")
    client = create_desktop_service_client(config={"mode": "Demo/Testnet"})
    if not isinstance(client, EmbeddedDesktopServiceClient):
        raise RuntimeError(f"unexpected desktop service client: {type(client).__name__}")
    descriptor = client.describe()
    if descriptor.get("client_mode") != "embedded":
        raise RuntimeError(f"unexpected client mode: {descriptor.get('client_mode')}")
    return "desktop entrypoint imports and embedded service client initializes"


def _check_service_healthcheck(timeout: float) -> str:
    command = [
        sys.executable,
        "-m",
        "app.service.product_main",
        "--healthcheck",
    ]
    result = subprocess.run(
        command,
        cwd=PYTHON_ROOT,
        env=_python_env(),
        text=True,
        capture_output=True,
        timeout=max(1.0, timeout),
        check=False,
    )
    output = result.stdout.strip()
    if result.returncode != 0 or output != "ok":
        stderr = result.stderr.strip()
        raise RuntimeError(f"healthcheck failed rc={result.returncode} stdout={output!r} stderr={stderr!r}")
    return "service launcher --healthcheck returned ok"


def _read_process_output(process: subprocess.Popen[str]) -> str:
    try:
        stdout, stderr = process.communicate(timeout=2.0)
    except Exception:
        return ""
    return "\n".join(part.strip() for part in (stdout, stderr) if part and part.strip())


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def _start_service_process(host: str, port: int, token: str) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "app.service.product_main",
        "--serve",
        "--host",
        host,
        "--port",
        str(port),
        "--api-token",
        token,
    ]
    return subprocess.Popen(
        command,
        cwd=PYTHON_ROOT,
        env=_python_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_for_service(base_url: str, process: subprocess.Popen[str], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(1.0, timeout)
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = _read_process_output(process)
            raise RuntimeError(f"service exited early rc={process.returncode} output={output}")
        try:
            status, payload = _http_json(base_url, "/health", timeout=1.0)
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return payload
            last_error = f"unexpected health payload status={status} payload={payload!r}"
        except URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.1)
    raise RuntimeError(f"service did not become healthy: {last_error}")


def _check_service_http(*, host: str, port: int, token: str, timeout: float) -> str:
    from app.service.api_contract import service_api_route

    selected_port = int(port or _find_free_port(host))
    base_url = f"http://{host}:{selected_port}"
    process = _start_service_process(host, selected_port, token)
    try:
        health = _wait_for_service(base_url, process, timeout)
        if health.get("auth_required") is not True:
            raise RuntimeError(f"expected auth_required=true, got {health.get('auth_required')!r}")

        status, _payload = _http_json(base_url, service_api_route("status"), timeout=timeout)
        if status != 401:
            raise RuntimeError(f"unauthenticated status request returned {status}, expected 401")

        status, _payload = _http_json(
            base_url,
            service_api_route("status"),
            token="wrong-token",
            timeout=timeout,
        )
        if status != 401:
            raise RuntimeError(f"wrong-token status request returned {status}, expected 401")

        status, payload = _http_json(base_url, service_api_route("status"), token=token, timeout=timeout)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"authenticated status request failed status={status} payload={payload!r}")
        if payload.get("mode") != "Demo/Testnet":
            raise RuntimeError(f"unexpected service mode: {payload.get('mode')!r}")

        status, invalid_payload = _http_json(
            base_url,
            service_api_route("config"),
            method="PATCH",
            token=token,
            payload={"config": {"leverage": 0, "position_pct": 0}},
            timeout=timeout,
        )
        if status != 422:
            raise RuntimeError(f"invalid config patch returned {status}, expected 422: {invalid_payload!r}")

        status, config_payload = _http_json(
            base_url,
            service_api_route("config"),
            method="PATCH",
            token=token,
            payload={
                "config": {
                    "mode": "Demo/Testnet",
                    "symbols": ["BTCUSDT"],
                    "intervals": ["1m"],
                    "leverage": 5,
                    "position_pct": 2.5,
                }
            },
            timeout=timeout,
        )
        if status != 200 or not isinstance(config_payload, dict):
            raise RuntimeError(f"valid config patch failed status={status} payload={config_payload!r}")
        if config_payload.get("symbols") != ["BTCUSDT"] or config_payload.get("intervals") != ["1m"]:
            raise RuntimeError(f"config patch response did not preserve target symbol/interval: {config_payload!r}")

        return f"service API ok on {base_url} with auth and config validation"
    finally:
        _stop_process(process)


class _ManualSmokeFakeExchange:
    account_type = "FUTURES"
    mode = "Demo/Testnet"
    _connector_backend = "manual-smoke-fake"

    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []

    def get_total_usdt_value(self) -> float:
        return 1000.0

    def get_futures_balance_snapshot(self, force_refresh=False):  # noqa: ARG002
        return {"total": "1000", "wallet": "1000", "available": "1000"}

    def get_futures_balance_usdt(self) -> float:
        return 1000.0

    def get_total_wallet_balance(self) -> float:
        return 1000.0

    def get_futures_symbol_filters(self, _symbol: str) -> dict[str, float]:
        return {"minNotional": 0.0, "minQty": 0.0, "stepSize": 0.001}

    def _ceil_to_step(self, qty: float, step: float) -> float:
        if step <= 0.0:
            return float(qty)
        steps = int(float(qty) / float(step))
        if steps * step < float(qty):
            steps += 1
        return steps * step

    def adjust_qty_to_filters_futures(self, _symbol: str, qty: float, _price: float):
        return float(qty), None

    def get_futures_dual_side(self) -> bool:
        return False

    def get_net_futures_position_amt(self, _symbol: str) -> float:
        return 0.0

    def list_open_futures_positions(self, *args, **kwargs):  # noqa: ARG002
        return []

    def place_futures_market_order(
        self,
        symbol: str,
        side: str,
        *,
        leverage: int,
        quantity: float,
        price: float | None = None,
        **kwargs,
    ) -> dict[str, object]:
        fill_price = float(price or 100.0)
        qty = float(quantity)
        self.orders.append(
            {
                "symbol": symbol,
                "side": side,
                "leverage": int(leverage),
                "quantity": qty,
                "price": fill_price,
                "kwargs": dict(kwargs),
            }
        )
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "computed": {"qty": qty, "px": fill_price, "lev": int(leverage)},
            "info": {
                "orderId": len(self.orders),
                "origQty": str(qty),
                "executedQty": str(qty),
                "avgPrice": str(fill_price),
                "leverage": int(leverage),
            },
            "fills": {
                "order_id": len(self.orders),
                "trade_count": 1,
                "filled_qty": qty,
                "avg_price": fill_price,
                "commission_usdt": 0.0,
                "net_realized": 0.0,
            },
        }


def _check_fake_order_path() -> str:
    from app.config import build_default_config
    from app.core.strategy import StrategyEngine

    wrapper = _ManualSmokeFakeExchange()
    logs: list[str] = []
    trades: list[dict[str, object]] = []
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = "FUTURES"
    config["side"] = "BOTH"
    config["leverage"] = 5
    config["position_pct"] = 25
    config["position_pct_units"] = "percent"
    config["allow_opposite_positions"] = True
    config["order_rate_min_spacing"] = 0.05

    original_spacing = StrategyEngine._ORDER_MIN_SPACING
    try:
        StrategyEngine._ORDER_MIN_SPACING = 0.0
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()

        engine = StrategyEngine(wrapper, config, log_callback=logs.append, trade_callback=trades.append)
        cw = dict(engine.config)
        cw["price"] = 100.0
        cw["trade_on_signal"] = True
        engine._execute_signal_order(
            cw=cw,
            order_side="BUY",
            indicator_labels=["rsi"],
            order_signature=("rsi",),
            origin_timestamp=None,
            order_trigger_desc="RSI -> BUY",
            order_trigger_actions={"rsi": "buy"},
            last_price=100.0,
            current_bar_marker=int(time.time()),
            positions_cache_holder={"value": []},
            order_batch_state={"counter": 0, "total": 1},
        )
    finally:
        StrategyEngine._ORDER_MIN_SPACING = original_spacing
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()

    if len(wrapper.orders) != 1:
        raise RuntimeError(f"expected one fake futures order, got {len(wrapper.orders)}; logs={logs!r}")
    order = wrapper.orders[0]
    if order.get("side") != "BUY":
        raise RuntimeError(f"unexpected fake order side: {order!r}")
    qty = float(order.get("quantity") or 0.0)
    if abs(qty - 12.5) > 1e-9:
        raise RuntimeError(f"unexpected fake order qty: {qty}")
    if not any(event.get("status") == "placed" for event in trades):
        raise RuntimeError("fake order did not emit a placed trade event")
    return "fake futures order path placed deterministic demo order"


def run_manual_smoke(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    api_token: str = "manual-smoke-token",
    timeout: float = 10.0,
    skip_http: bool = False,
    skip_fake_order: bool = False,
) -> SmokeReport:
    steps: list[SmokeStep] = []
    _run_step(steps, "desktop import", _check_desktop_import)
    _run_step(steps, "service launcher healthcheck", lambda: _check_service_healthcheck(timeout))
    if not skip_http:
        _run_step(
            steps,
            "service HTTP API",
            lambda: _check_service_http(host=host, port=port, token=api_token, timeout=timeout),
        )
    if not skip_fake_order:
        _run_step(steps, "fake exchange order path", _check_fake_order_path)
    return SmokeReport(steps=steps)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a local manual smoke check for desktop imports, service API, auth, config validation, and fake order flow.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for the temporary service API. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Port for the temporary service API. Default: auto-pick")
    parser.add_argument(
        "--api-token",
        default="manual-smoke-token",
        help="Temporary bearer token for the service API smoke run.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout in seconds for each external check.")
    parser.add_argument("--skip-http", action="store_true", help="Skip launching the temporary HTTP API server.")
    parser.add_argument("--skip-fake-order", action="store_true", help="Skip the in-memory fake exchange order path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_manual_smoke(
        host=args.host,
        port=args.port,
        api_token=args.api_token,
        timeout=args.timeout,
        skip_http=args.skip_http,
        skip_fake_order=args.skip_fake_order,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for step in report.steps:
            status = "PASS" if step.ok else "FAIL"
            detail = f" - {step.detail}" if step.detail else ""
            print(f"[{status}] {step.name}{detail}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
