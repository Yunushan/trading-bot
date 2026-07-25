#!/usr/bin/env python3
"""Validate connector support declarations against the Python source of truth."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_MATRIX_PATH = Path("docs/connector-support-matrix.json")
REQUIRED_CCXT_VENUES = (
    "Bybit",
    "OKX",
    "Bitget",
    "Gate",
    "MEXC",
    "KuCoin",
    "HTX",
    "Crypto.com Exchange",
    "Kraken",
    "Bitfinex",
)
REQUIRED_BROKER_GROUPS = {
    "oanda-broker-order-routing": ("OANDA", "oanda-rest"),
    "fxcm-broker-order-routing": ("FXCM", "fxcmpy"),
    "ig-broker-order-routing": ("IG", "ig-rest"),
}
REQUIRED_MT4_BRIDGE_GROUP = "metatrader4-bridge-order-routing"
REQUIRED_MT5_BROKER_GROUP = "metatrader5-broker-order-routing"
REQUIRED_TRADING212_GROUP = "trading212-public-api-order-routing"
REQUIRED_MOOMOO_GROUP = "moomoo-opend-order-routing"
REQUIRED_CITIC_CTP_GROUP = "citic-futures-ctp-order-routing"
REQUEST_COVERAGE_FIELD = "request_coverage"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _target_id(group: str, venue: str) -> str:
    return f"connector-{_slug(group)}-{_slug(venue)}"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only non-empty strings")
    return result


def _target_groups(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    groups = matrix.get("target_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("target_groups must be a non-empty list")
    parsed: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"target_groups[{index}] must be an object")
        name = str(group.get("group") or "").strip()
        backend = str(group.get("backend") or "").strip()
        status = str(group.get("status") or "").strip()
        if not name:
            raise ValueError(f"target_groups[{index}].group is required")
        if not backend:
            raise ValueError(f"{name}.backend is required")
        if not status:
            raise ValueError(f"{name}.status is required")
        if group.get("evidence_required") is not True:
            raise ValueError(f"{name}.evidence_required must be true")
        venues = _string_list(group.get("venues"), field=f"{name}.venues")
        capabilities = _string_list(
            group.get("capabilities_required"), field=f"{name}.capabilities_required"
        )
        parsed.append(
            {
                "group": name,
                "backend": backend,
                "status": status,
                "venues": venues,
                "capabilities_required": capabilities,
                "capabilities_gated": _string_list(
                    group.get("capabilities_gated"), field=f"{name}.capabilities_gated"
                )
                if "capabilities_gated" in group
                else [],
                "evidence_required": True,
            }
        )
    return parsed


def _support_payload_builder():
    python_root = _repo_root() / "Languages" / "Python"
    sys.path.insert(0, str(python_root))
    from app.settings.exchange_support import (
        CITIC_FUTURES_BROKER_OFFICIAL_SOURCE,
        METATRADER4_BRIDGE_BROKERS,
        METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES,
        METATRADER5_BROKERS,
        METATRADER5_BROKER_OFFICIAL_SOURCES,
        MOOMOO_BROKER_OFFICIAL_SOURCE,
        TRADING212_BROKER_OFFICIAL_SOURCE,
        build_exchange_support_payload,
    )

    return (
        build_exchange_support_payload,
        tuple(METATRADER4_BRIDGE_BROKERS),
        dict(METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES),
        tuple(METATRADER5_BROKERS),
        dict(METATRADER5_BROKER_OFFICIAL_SOURCES),
        str(TRADING212_BROKER_OFFICIAL_SOURCE),
        str(MOOMOO_BROKER_OFFICIAL_SOURCE),
        str(CITIC_FUTURES_BROKER_OFFICIAL_SOURCE),
    )


def _requested_coverage_source():
    python_root = _repo_root() / "Languages" / "Python"
    if str(python_root) not in sys.path:
        sys.path.insert(0, str(python_root))
    from app.settings.exchange_support import (
        BROKER_INTEGRATION_DISPOSITIONS,
        REQUESTED_BROKER_TARGETS,
        SUPPORTED_BROKERS,
        build_requested_broker_coverage,
    )

    return (
        dict(REQUESTED_BROKER_TARGETS),
        dict(BROKER_INTEGRATION_DISPOSITIONS),
        tuple(SUPPORTED_BROKERS),
        build_requested_broker_coverage,
    )


def _validate_request_coverage(
    matrix: dict[str, Any],
) -> tuple[list[str], dict[str, int]]:
    issues: list[str] = []
    declared = matrix.get(REQUEST_COVERAGE_FIELD)
    empty_counts = {
        "requested_target_count": 0,
        "implemented_connector_route_count": 0,
        "implemented_forex_route_count": 0,
        "implemented_non_forex_route_count": 0,
        "external_prerequisite_count": 0,
    }
    if not isinstance(declared, dict):
        return [f"{REQUEST_COVERAGE_FIELD} must be an object"], empty_counts

    try:
        requested_names = _string_list(
            declared.get("requested_names"),
            field=f"{REQUEST_COVERAGE_FIELD}.requested_names",
        )
        blocked_names = _string_list(
            declared.get("external_prerequisite_canonical_names"),
            field=(f"{REQUEST_COVERAGE_FIELD}.external_prerequisite_canonical_names"),
        )
    except ValueError as exc:
        return [str(exc)], empty_counts

    (
        requested_targets,
        dispositions,
        supported_brokers,
        build_coverage,
    ) = _requested_coverage_source()
    records = build_coverage()
    expected_names = list(requested_targets)
    if requested_names != expected_names:
        issues.append(
            f"{REQUEST_COVERAGE_FIELD}.requested_names must match Python source order"
        )

    implemented = [record for record in records if record.get("implemented") is True]
    forex = [
        record
        for record in implemented
        if record.get("forex_order_routing_supported") is True
    ]
    non_forex = [
        record
        for record in implemented
        if record.get("forex_order_routing_supported") is False
    ]
    blocked = [record for record in records if record.get("implemented") is False]
    counts = {
        "requested_target_count": len(records),
        "implemented_connector_route_count": len(implemented),
        "implemented_forex_route_count": len(forex),
        "implemented_non_forex_route_count": len(non_forex),
        "external_prerequisite_count": len(blocked),
    }
    for field, actual in counts.items():
        if declared.get(field) != actual:
            issues.append(f"{REQUEST_COVERAGE_FIELD}.{field} must be {actual}")

    actual_blocked_names = [str(record["canonical_name"]) for record in blocked]
    if blocked_names != actual_blocked_names:
        issues.append(
            f"{REQUEST_COVERAGE_FIELD}.external_prerequisite_canonical_names "
            "must match Python dispositions in request order"
        )

    supported = set(supported_brokers)
    for record in records:
        requested_name = str(record.get("requested_name") or "")
        canonical_name = str(record.get("canonical_name") or "")
        expected_canonical = requested_targets.get(requested_name)
        if canonical_name != expected_canonical:
            issues.append(
                f"requested broker '{requested_name}' must resolve to "
                f"'{expected_canonical}'"
            )
        source = str(record.get("official_source") or "")
        if not source.startswith("https://"):
            issues.append(
                f"requested broker '{requested_name}' must have an official HTTPS source"
            )
        if record.get("status") == "unknown-broker-request":
            issues.append(f"requested broker '{requested_name}' is unclassified")
        if record.get("implemented") is True:
            if canonical_name not in supported:
                issues.append(
                    f"implemented requested broker '{canonical_name}' must be in SUPPORTED_BROKERS"
                )
            if not str(record.get("backend") or ""):
                issues.append(
                    f"implemented requested broker '{canonical_name}' must name a backend"
                )
            if record.get("live_evidence_required") is not True:
                issues.append(
                    f"implemented requested broker '{canonical_name}' must remain evidence-gated"
                )
        else:
            if canonical_name not in dispositions:
                issues.append(
                    f"unimplemented requested broker '{canonical_name}' must have a disposition"
                )
            if canonical_name in supported:
                issues.append(
                    f"externally blocked broker '{canonical_name}' must not be falsely supported"
                )
            if not str(record.get("status") or "").startswith("blocked-"):
                issues.append(
                    f"externally blocked broker '{canonical_name}' must have a blocked status"
                )
            if not str(record.get("blocking_requirement") or ""):
                issues.append(
                    f"externally blocked broker '{canonical_name}' must name its prerequisite"
                )
    return issues, counts


def _validate_against_python(groups: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    (
        build_support,
        mt4_brokers,
        mt4_sources,
        mt5_brokers,
        mt5_sources,
        trading212_source,
        moomoo_source,
        citic_source,
    ) = _support_payload_builder()
    groups_by_name = {str(group["group"]): group for group in groups}

    ccxt_group = groups_by_name.get("ccxt-crypto-order-routing")
    if not ccxt_group:
        issues.append("missing ccxt-crypto-order-routing group")
    else:
        venues = tuple(ccxt_group["venues"])
        if venues != REQUIRED_CCXT_VENUES:
            issues.append(
                f"ccxt-crypto-order-routing.venues must be {list(REQUIRED_CCXT_VENUES)}"
            )
        if ccxt_group["backend"] != "ccxt":
            issues.append("ccxt-crypto-order-routing.backend must be ccxt")
        for venue in venues:
            payload = build_support(
                config={"selected_exchange": venue, "connector_backend": "ccxt"}
            )
            if not payload.get("exchange_supported"):
                issues.append(f"{venue} must be exchange_supported in Python")
            if not payload.get("market_data_supported"):
                issues.append(f"{venue} must support market-data diagnostics in Python")
            if not payload.get("account_snapshot_supported"):
                issues.append(f"{venue} must support account snapshots in Python")
            if not payload.get("order_routing_supported") or not payload.get(
                "order_execution_supported"
            ):
                issues.append(f"{venue} must support ccxt order routing in Python")
            if payload.get("live_evidence_required") is not True:
                issues.append(
                    f"{venue} must require live evidence before official release support"
                )

    binance_group = groups_by_name.get("binance")
    if not binance_group:
        issues.append("missing binance group")
    else:
        payload = build_support(
            config={
                "selected_exchange": "Binance",
                "connector_backend": str(binance_group["backend"]),
            }
        )
        if not payload.get("trading_supported") or not payload.get(
            "order_execution_supported"
        ):
            issues.append("Binance must stay full-trading supported in Python")

    for group_name, (venue, backend) in REQUIRED_BROKER_GROUPS.items():
        group = groups_by_name.get(group_name)
        if not group:
            issues.append(f"missing {group_name} group")
            continue
        venues = tuple(group["venues"])
        if venues != (venue,):
            issues.append(f"{group_name}.venues must be {[venue]}")
        if group["backend"] != backend:
            issues.append(f"{group_name}.backend must be {backend}")
        payload = build_support(
            config={
                "selected_exchange": "",
                "connector_backend": backend,
                "selected_forex_broker": venue,
            }
        )
        if not payload.get("broker_supported"):
            issues.append(f"{venue} must be marked broker_supported")
        if not payload.get("order_routing_supported") or not payload.get(
            "order_execution_supported"
        ):
            issues.append(f"{venue} must support broker order routing in Python")
        if payload.get("live_evidence_required") is not True:
            issues.append(
                f"{venue} must require live evidence before official release support"
            )

    mt4_group = groups_by_name.get(REQUIRED_MT4_BRIDGE_GROUP)
    if not mt4_group:
        issues.append(f"missing {REQUIRED_MT4_BRIDGE_GROUP} group")
    else:
        venues = tuple(mt4_group["venues"])
        if venues != mt4_brokers:
            issues.append(
                f"{REQUIRED_MT4_BRIDGE_GROUP}.venues must be {list(mt4_brokers)}"
            )
        if mt4_group["backend"] != "metatrader4-bridge":
            issues.append(
                f"{REQUIRED_MT4_BRIDGE_GROUP}.backend must be metatrader4-bridge"
            )
        required_gates = {
            "official-live-evidence",
            "MT4-terminal-required",
            "Expert-Advisor-installation-required",
            "bridge-token-required",
        }
        if not required_gates.issubset(set(mt4_group["capabilities_gated"])):
            issues.append(
                f"{REQUIRED_MT4_BRIDGE_GROUP} must preserve terminal, EA, token, and evidence gates"
            )
        for venue in venues:
            source = str(mt4_sources.get(venue) or "")
            if not source.startswith("https://"):
                issues.append(
                    f"{venue} must have an official HTTPS MetaTrader 4 source"
                )
            payload = build_support(
                config={
                    "selected_exchange": "",
                    "connector_backend": "metatrader4-bridge",
                    "selected_forex_broker": venue,
                }
            )
            if not payload.get("broker_supported"):
                issues.append(f"{venue} must be marked broker_supported")
            if not payload.get("forex_order_routing_supported"):
                issues.append(f"{venue} must expose its MT4 forex routing scope")
            if payload.get("live_evidence_required") is not True:
                issues.append(
                    f"{venue} must require live evidence before official release support"
                )

    mt5_group = groups_by_name.get(REQUIRED_MT5_BROKER_GROUP)
    if not mt5_group:
        issues.append(f"missing {REQUIRED_MT5_BROKER_GROUP} group")
    else:
        venues = tuple(mt5_group["venues"])
        if venues != mt5_brokers:
            issues.append(
                f"{REQUIRED_MT5_BROKER_GROUP}.venues must be {list(mt5_brokers)}"
            )
        if mt5_group["backend"] != "metatrader5":
            issues.append(f"{REQUIRED_MT5_BROKER_GROUP}.backend must be metatrader5")
        for venue in venues:
            source = str(mt5_sources.get(venue) or "")
            if not source.startswith("https://"):
                issues.append(
                    f"{venue} must have an official HTTPS MetaTrader 5 source"
                )
            payload = build_support(
                config={
                    "selected_exchange": "",
                    "connector_backend": "metatrader5",
                    "selected_forex_broker": venue,
                }
            )
            if not payload.get("broker_supported"):
                issues.append(f"{venue} must be marked broker_supported")
            if not payload.get("order_routing_supported") or not payload.get(
                "order_execution_supported"
            ):
                issues.append(
                    f"{venue} must support MetaTrader 5 broker order routing in Python"
                )
            if payload.get("live_evidence_required") is not True:
                issues.append(
                    f"{venue} must require live evidence before official release support"
                )

    trading212_group = groups_by_name.get(REQUIRED_TRADING212_GROUP)
    if not trading212_group:
        issues.append(f"missing {REQUIRED_TRADING212_GROUP} group")
    else:
        if tuple(trading212_group["venues"]) != ("Trading 212",):
            issues.append(f"{REQUIRED_TRADING212_GROUP}.venues must be ['Trading 212']")
        if trading212_group["backend"] != "trading212-public-api":
            issues.append(
                f"{REQUIRED_TRADING212_GROUP}.backend must be trading212-public-api"
            )
        if not trading212_source.startswith("https://docs.trading212.com/"):
            issues.append(
                "Trading 212 must have an official docs.trading212.com HTTPS source"
            )
        if (
            "forex-cfd-public-api-unavailable"
            not in trading212_group["capabilities_gated"]
        ):
            issues.append(
                f"{REQUIRED_TRADING212_GROUP} must preserve the public API forex/CFD limitation"
            )
        payload = build_support(
            config={
                "selected_exchange": "",
                "connector_backend": "trading212-public-api",
                "selected_forex_broker": "Trading 212",
            }
        )
        if not payload.get("broker_supported"):
            issues.append("Trading 212 must be marked broker_supported")
        if not payload.get("order_routing_supported") or not payload.get(
            "order_execution_supported"
        ):
            issues.append(
                "Trading 212 must support its documented equity order-routing scope"
            )
        if payload.get("forex_order_routing_supported") is not False:
            issues.append(
                "Trading 212 must not be marked forex_order_routing_supported"
            )
        if payload.get("broker_market_scope") != "invest-and-stocks-isa-equities-only":
            issues.append(
                "Trading 212 must retain its Invest/Stocks ISA equities-only scope"
            )
        if payload.get("live_evidence_required") is not True:
            issues.append(
                "Trading 212 must require live evidence before official release support"
            )

    moomoo_group = groups_by_name.get(REQUIRED_MOOMOO_GROUP)
    if not moomoo_group:
        issues.append(f"missing {REQUIRED_MOOMOO_GROUP} group")
    else:
        if tuple(moomoo_group["venues"]) != ("moomoo",):
            issues.append(f"{REQUIRED_MOOMOO_GROUP}.venues must be ['moomoo']")
        if moomoo_group["backend"] != "moomoo-opend":
            issues.append(f"{REQUIRED_MOOMOO_GROUP}.backend must be moomoo-opend")
        if not moomoo_source.startswith("https://openapi.moomoo.com/"):
            issues.append(
                "moomoo must have an official openapi.moomoo.com HTTPS source"
            )
        required_gates = {"OpenD-gateway-required", "forex-public-api-unavailable"}
        if not required_gates.issubset(set(moomoo_group["capabilities_gated"])):
            issues.append(
                f"{REQUIRED_MOOMOO_GROUP} must preserve its OpenD and forex limitations"
            )
        payload = build_support(
            config={
                "selected_exchange": "",
                "connector_backend": "moomoo-opend",
                "selected_forex_broker": "moomoo",
            }
        )
        if not payload.get("broker_supported"):
            issues.append("moomoo must be marked broker_supported")
        if not payload.get("order_routing_supported") or not payload.get(
            "order_execution_supported"
        ):
            issues.append(
                "moomoo must support its documented OpenD order-routing scope"
            )
        if payload.get("forex_order_routing_supported") is not False:
            issues.append("moomoo must not be marked forex_order_routing_supported")
        if (
            payload.get("broker_market_scope")
            != "stocks-etfs-options-futures-funds-and-supported-crypto"
        ):
            issues.append("moomoo must retain its documented multi-market scope")
        if payload.get("live_evidence_required") is not True:
            issues.append(
                "moomoo must require live evidence before official release support"
            )

    citic_group = groups_by_name.get(REQUIRED_CITIC_CTP_GROUP)
    if not citic_group:
        issues.append(f"missing {REQUIRED_CITIC_CTP_GROUP} group")
    else:
        if tuple(citic_group["venues"]) != ("CITIC Futures",):
            issues.append(
                f"{REQUIRED_CITIC_CTP_GROUP}.venues must be ['CITIC Futures']"
            )
        if citic_group["backend"] != "citic-ctp":
            issues.append(f"{REQUIRED_CITIC_CTP_GROUP}.backend must be citic-ctp")
        if not citic_source.startswith("https://www.citicsf.com/"):
            issues.append(
                "CITIC Futures must have an official citicsf.com HTTPS source"
            )
        required_gates = {"CTP-account-app-auth-required", "forex-unavailable"}
        if not required_gates.issubset(set(citic_group["capabilities_gated"])):
            issues.append(
                f"{REQUIRED_CITIC_CTP_GROUP} must preserve its CTP authorization and forex limitations"
            )
        payload = build_support(
            config={
                "selected_exchange": "",
                "connector_backend": "citic-ctp",
                "selected_forex_broker": "CITIC Futures",
            }
        )
        if not payload.get("broker_supported"):
            issues.append("CITIC Futures must be marked broker_supported")
        if not payload.get("order_routing_supported") or not payload.get(
            "order_execution_supported"
        ):
            issues.append(
                "CITIC Futures must support its documented CTP order-routing scope"
            )
        if payload.get("forex_order_routing_supported") is not False:
            issues.append(
                "CITIC Futures must not be marked forex_order_routing_supported"
            )
        if payload.get("broker_market_scope") != "china-futures-and-options":
            issues.append("CITIC Futures must retain its China futures/options scope")
        if payload.get("live_evidence_required") is not True:
            issues.append(
                "CITIC Futures must require live evidence before official release support"
            )

    return issues


def _expanded_targets(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for group in groups:
        for venue in group["venues"]:
            targets.append(
                {
                    "id": _target_id(str(group["group"]), str(venue)),
                    "group": group["group"],
                    "venue": venue,
                    "backend": group["backend"],
                    "status": group["status"],
                    "capabilities_required": group["capabilities_required"],
                    "capabilities_gated": group["capabilities_gated"],
                    "evidence_required": True,
                }
            )
    return targets


def _validate_evidence(targets: list[dict[str, Any]], evidence_dir: Path) -> list[str]:
    issues: list[str] = []
    for target in targets:
        artifact_path = evidence_dir / f"{target['id']}.json"
        if not artifact_path.exists():
            issues.append(f"missing evidence artifact: {artifact_path}")
            continue
        try:
            artifact = _load_json(artifact_path)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        if artifact.get("target_id") != target["id"]:
            issues.append(f"{artifact_path} target_id must be {target['id']}")
        if artifact.get("venue") != target["venue"]:
            issues.append(f"{artifact_path} venue must be {target['venue']}")
        if artifact.get("backend") != target["backend"]:
            issues.append(f"{artifact_path} backend must be {target['backend']}")
        if artifact.get("passed") is not True:
            issues.append(f"{artifact_path} passed must be true")
    return issues


def validate(matrix_path: Path, *, require_evidence: bool) -> dict[str, Any]:
    matrix = _load_json(matrix_path)
    issues: list[str] = []
    if matrix.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    policy = matrix.get("policy")
    if not isinstance(policy, dict):
        issues.append("policy must be an object")
        evidence_dir = Path("connector-support-evidence")
    else:
        if policy.get("no_assumed_passes") is not True:
            issues.append("policy.no_assumed_passes must be true")
        evidence_dir = Path(
            str(policy.get("evidence_artifact_dir") or "connector-support-evidence")
        )

    try:
        groups = _target_groups(matrix)
    except ValueError as exc:
        groups = []
        issues.append(str(exc))

    if groups:
        issues.extend(_validate_against_python(groups))
    request_issues, request_counts = _validate_request_coverage(matrix)
    issues.extend(request_issues)
    targets = _expanded_targets(groups) if groups else []
    if require_evidence and targets:
        issues.extend(_validate_evidence(targets, _repo_root() / evidence_dir))

    return {
        "ok": not issues,
        "schema_version": matrix.get("schema_version"),
        "matrix_path": str(matrix_path),
        "target_count": len(targets),
        "request_coverage": request_counts,
        "evidence_required": bool(require_evidence),
        "issues": issues,
        "targets": targets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        default=str(DEFAULT_MATRIX_PATH),
        help="Connector support matrix JSON path.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Validate declarations without requiring artifacts.",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="Require passed evidence artifacts.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    args = parser.parse_args(argv)

    require_evidence = bool(args.require_evidence and not args.schema_only)
    result = validate(Path(args.matrix), require_evidence=require_evidence)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        request = result["request_coverage"]
        print(
            f"Connector support matrix ok: {result['target_count']} evidence targets; "
            f"{request['requested_target_count']} requested brokers accounted "
            f"({request['implemented_connector_route_count']} implemented routes, "
            f"{request['external_prerequisite_count']} external prerequisites)"
        )
    else:
        print("Connector support matrix failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
