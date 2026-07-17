"""Check and refresh checked-in service API contract artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
CONTRACTS_DIR = REPO_ROOT / "apps" / "service-api" / "contracts"
CLIENT_ROUTE_CONTRACT_PATHS = (
    REPO_ROOT / "apps" / "mobile-client" / "service-contract.js",
    REPO_ROOT / "apps" / "web-dashboard" / "modules" / "service-contract.js",
)

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api_contract import service_api_contract_payload  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


def _json_text(payload: object) -> str:
    return json.dumps(payload, indent=2) + "\n"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _shape(value: object) -> object:
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _mark_operational_inputs_stale(service: TradingBotService, *, seconds: int = 900) -> None:
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    service.set_exchange_connector_snapshot(
        {
            "health": "ok",
            "state": "ready",
            "generated_at": stale_at,
        },
        source="contract-sample-check",
    )
    runtime = service._runtime
    with runtime._lock:
        runtime._account_snapshot = replace(
            runtime._account_snapshot,
            source="contract-sample-check",
            generated_at=stale_at,
        )
        runtime._portfolio_snapshot = replace(
            runtime._portfolio_snapshot,
            source="contract-sample-check",
            generated_at=stale_at,
        )


def _standalone_runtime_descriptor() -> dict[str, object]:
    service = TradingBotService()
    service.enable_local_executor()
    return service.describe_runtime().to_dict()


def _blocked_preflight_payload() -> dict[str, object]:
    service = TradingBotService(
        config={
            "mode": "Live",
            "operational_connector_snapshot_stale_seconds": 60,
            "operational_account_snapshot_stale_seconds": 60,
            "operational_portfolio_snapshot_stale_seconds": 60,
        }
    )
    _mark_operational_inputs_stale(service)
    return service.get_operational_preflight()


def _assert_equal(label: str, expected: object, actual: object) -> None:
    if expected != actual:
        raise AssertionError(f"{label} is stale or invalid")


def _check_route_contract(*, write: bool) -> None:
    path = CONTRACTS_DIR / "service-api-contract.json"
    expected = service_api_contract_payload()
    if write:
        path.write_text(_json_text(expected), encoding="utf-8")
    actual = _load_json(path)
    _assert_equal(str(path.relative_to(REPO_ROOT)), expected, actual)


def _client_route_object_text() -> str:
    return "".join(
        f'  {route_name}: "{suffix}",\n'
        for route_name, suffix in service_api_contract_payload()["route_suffixes"].items()
    )


def _check_client_route_contracts(*, write: bool) -> None:
    expected = _client_route_object_text()
    pattern = re.compile(
        r"(?P<prefix>SERVICE_API_ROUTE_SUFFIXES\s*=\s*Object\.freeze\(\{\n)"
        r"(?P<routes>.*?)"
        r"(?P<suffix>\}\);)",
        re.DOTALL,
    )
    for path in CLIENT_ROUTE_CONTRACT_PATHS:
        source = path.read_text(encoding="utf-8")
        match = pattern.search(source)
        if match is None:
            raise AssertionError(f"{path.relative_to(REPO_ROOT)} has no service route registry")
        if write:
            source, replacements = pattern.subn(
                f"\\g<prefix>{expected}\\g<suffix>",
                source,
                count=1,
            )
            if replacements != 1:
                raise AssertionError(f"could not update {path.relative_to(REPO_ROOT)}")
            path.write_text(source, encoding="utf-8")
            match = pattern.search(source)
            if match is None:
                raise AssertionError(f"could not reread {path.relative_to(REPO_ROOT)}")
        _assert_equal(str(path.relative_to(REPO_ROOT)), expected, match.group("routes"))


def _check_runtime_sample() -> None:
    path = CONTRACTS_DIR / "runtime.sample.json"
    sample = _load_json(path)
    runtime = _standalone_runtime_descriptor()

    _assert_equal("runtime sample top-level keys", set(runtime), set(sample))
    _assert_equal("runtime sample shape", _shape(runtime), _shape(sample))
    for key in ("service_name", "phase", "python_entrypoint", "desktop_entrypoint"):
        _assert_equal(f"runtime sample {key}", runtime[key], sample[key])
    _assert_equal("runtime sample capabilities", runtime["capabilities"], sample["capabilities"])
    _assert_equal("runtime sample control_plane", runtime["control_plane"], sample["control_plane"])


def _check_operational_preflight_sample() -> None:
    path = CONTRACTS_DIR / "operational-preflight.sample.json"
    sample = _load_json(path)
    preflight = _blocked_preflight_payload()

    _assert_equal("operational preflight sample top-level keys", set(preflight), set(sample))
    _assert_equal("operational preflight sample shape", _shape(preflight), _shape(sample))
    _assert_equal("operational preflight gate keys", set(preflight["start"]), set(sample["start"]))
    _assert_equal(
        "operational preflight freshness keys",
        set(preflight["freshness"]),
        set(sample["freshness"]),
    )
    _assert_equal(
        "operational preflight critical_stale keys",
        set(preflight["critical_stale"]),
        set(sample["critical_stale"]),
    )
    if sample["state"] != "blocked" or sample["start"]["allowed"] is not False:
        raise AssertionError("operational preflight sample must document a blocked live start")


def check_contracts(*, write: bool = False) -> None:
    _check_route_contract(write=write)
    _check_client_route_contracts(write=write)
    _check_runtime_sample()
    _check_operational_preflight_sample()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="refresh generated API contract artifacts before checking samples",
    )
    args = parser.parse_args(argv)

    try:
        check_contracts(write=args.write)
    except Exception as exc:
        print(f"service API contract check failed: {exc}", file=sys.stderr)
        return 1
    action = "updated and checked" if args.write else "checked"
    print(f"service API contract artifacts {action}: {CONTRACTS_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
