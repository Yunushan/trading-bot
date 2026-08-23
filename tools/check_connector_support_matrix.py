#!/usr/bin/env python3
"""Validate connector support declarations against the Python source of truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
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
ALLOWED_EVIDENCE_SCOPES = ("sandbox", "testnet", "approved-live-paper")
ORDER_CAPABILITY_FRAGMENTS = ("order-execution", "order-routing", "order-cancellation")
SAFE_REDACTED_VALUES = {"", "***", "<redacted>", "[redacted]", "redacted", "...", "none", "null"}
SAFE_SECRET_METADATA_KEYS = {
    "credentials_present",
    "secrets_in_artifact",
    "secrets_redacted",
}
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|api[_-]?secret|password|token|signature|authorization)\b\s*[:=]\s*([^\s,;&]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+([^\s,;&]+)")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def _current_source_tree_clean() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", "."],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not result.stdout.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target_contract_sha256(target: dict[str, Any]) -> str:
    payload = {
        key: target[key]
        for key in (
            "id",
            "group",
            "venue",
            "backend",
            "status",
            "capabilities_required",
            "capabilities_gated",
        )
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_timestamp(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SAFE_SECRET_METADATA_KEYS or normalized.endswith("_present"):
        return False
    return any(
        fragment in normalized
        for fragment in ("api_key", "apikey", "api_secret", "secret", "password", "token", "signature", "authorization")
    )


def _validate_secret_free(value: Any, artifact_path: Path, issues: list[str], *, key: str = "") -> None:
    if key and _is_sensitive_key(key):
        if isinstance(value, str):
            if value.strip().lower() not in SAFE_REDACTED_VALUES:
                issues.append(f"{artifact_path} contains unredacted secret field: {key}")
        elif isinstance(value, bool):
            pass
        elif value not in (None, ""):
            issues.append(f"{artifact_path} contains non-redacted secret field: {key}")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _validate_secret_free(child_value, artifact_path, issues, key=str(child_key))
    elif isinstance(value, list):
        for child_value in value:
            _validate_secret_free(child_value, artifact_path, issues)
    elif isinstance(value, str):
        for match in SECRET_ASSIGNMENT_PATTERN.finditer(value):
            secret_value = match.group(2).strip().strip("\"'").lower()
            if secret_value not in SAFE_REDACTED_VALUES:
                issues.append(f"{artifact_path} contains unredacted secret assignment for {match.group(1)}")
        for match in BEARER_PATTERN.finditer(value):
            bearer_value = match.group(1).strip().strip("\"'").lower()
            if bearer_value not in SAFE_REDACTED_VALUES:
                issues.append(f"{artifact_path} contains unredacted bearer token text")


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


def _validate_evidence(
    targets: list[dict[str, Any]],
    evidence_dir: Path,
    *,
    matrix_sha256: str,
    require_current_commit: bool,
    require_clean_source: bool,
) -> list[str]:
    issues: list[str] = []
    current_commit = _current_git_commit()
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
        if artifact.get("group") != target["group"]:
            issues.append(f"{artifact_path} group must be {target['group']}")
        if artifact.get("schema_version") != 1:
            issues.append(f"{artifact_path} schema_version must be 1")
        if artifact.get("evidence_id") != target["id"]:
            issues.append(f"{artifact_path} evidence_id must be {target['id']}")
        if artifact.get("passed") is not True:
            issues.append(f"{artifact_path} passed must be true")
        if artifact.get("status") != "passed":
            issues.append(f"{artifact_path} status must be passed")
        if not _valid_timestamp(artifact.get("generated_at")):
            issues.append(f"{artifact_path} generated_at must be a timezone-aware ISO-8601 timestamp")
        if not str(artifact.get("command") or "").strip():
            issues.append(f"{artifact_path} command is required")
        artifact_commit = str(artifact.get("commit") or "").strip()
        if not artifact_commit:
            issues.append(f"{artifact_path} commit is required")
        if require_current_commit and artifact_commit != current_commit:
            issues.append(
                f"{artifact_path} commit must match current git commit {current_commit or '<unresolved>'}; "
                f"observed {artifact_commit or '<empty>'}"
            )
        if not isinstance(artifact.get("source_tree_clean"), bool):
            issues.append(f"{artifact_path} source_tree_clean must be boolean")
        if require_clean_source and artifact.get("source_tree_clean") is not True:
            issues.append(f"{artifact_path} source_tree_clean must be true for promotion evidence")
        if artifact.get("matrix_sha256") != matrix_sha256:
            issues.append(f"{artifact_path} matrix_sha256 must match the current connector support matrix")
        target_hash = _target_contract_sha256(target)
        if artifact.get("target_contract_sha256") != target_hash:
            issues.append(f"{artifact_path} target_contract_sha256 must match the current target contract")
        scope = str(artifact.get("evidence_scope") or "").strip()
        if scope not in ALLOWED_EVIDENCE_SCOPES:
            issues.append(f"{artifact_path} evidence_scope must be one of {list(ALLOWED_EVIDENCE_SCOPES)}")
        if artifact.get("secrets_redacted") is not True:
            issues.append(f"{artifact_path} secrets_redacted must be true")
        if artifact.get("secrets_in_artifact") is not False:
            issues.append(f"{artifact_path} secrets_in_artifact must be false")
        if artifact.get("runtime_ready_claimed") is not False:
            issues.append(f"{artifact_path} runtime_ready_claimed must be false")
        environment = artifact.get("environment")
        if not isinstance(environment, dict) or not environment:
            issues.append(f"{artifact_path} environment must be a non-empty object")

        capabilities_tested = artifact.get("capabilities_tested")
        expected_capabilities = list(target["capabilities_required"])
        if capabilities_tested != expected_capabilities:
            issues.append(
                f"{artifact_path} capabilities_tested must exactly match {expected_capabilities}"
            )
        suite_results = artifact.get("suite_results")
        suite_by_name: dict[str, dict[str, Any]] = {}
        if not isinstance(suite_results, list) or not suite_results:
            issues.append(f"{artifact_path} suite_results must be a non-empty list")
        else:
            for index, row in enumerate(suite_results):
                if not isinstance(row, dict):
                    issues.append(f"{artifact_path} suite_results[{index}] must be an object")
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    issues.append(f"{artifact_path} suite_results[{index}].name is required")
                elif name in suite_by_name:
                    issues.append(f"{artifact_path} suite_results contains duplicate name: {name}")
                else:
                    suite_by_name[name] = row
            for capability in expected_capabilities:
                row = suite_by_name.get(capability)
                if row is None:
                    issues.append(f"{artifact_path} suite_results must include {capability}")
                elif row.get("status") != "passed":
                    issues.append(f"{artifact_path} suite_results[{capability}].status must be passed")

        order_capability_required = any(
            any(fragment in capability for fragment in ORDER_CAPABILITY_FRAGMENTS)
            for capability in expected_capabilities
        )
        if order_capability_required:
            lifecycle = artifact.get("order_lifecycle")
            if not isinstance(lifecycle, dict):
                issues.append(f"{artifact_path} order_lifecycle must be an object")
            else:
                if lifecycle.get("mode") != scope:
                    issues.append(f"{artifact_path} order_lifecycle.mode must match evidence_scope")
                for field in ("submission_attempted", "acknowledged", "cleanup_confirmed", "order_identifier_redacted"):
                    if lifecycle.get(field) is not True:
                        issues.append(f"{artifact_path} order_lifecycle.{field} must be true")
                if lifecycle.get("production_funds_at_risk") is not False:
                    issues.append(f"{artifact_path} order_lifecycle.production_funds_at_risk must be false")
        _validate_secret_free(artifact, artifact_path, issues)
    return issues


def validate(
    matrix_path: Path,
    *,
    require_evidence: bool,
    require_current_commit: bool = False,
    require_clean_source: bool = False,
    evidence_dir_override: Path | None = None,
) -> dict[str, Any]:
    matrix = _load_json(matrix_path)
    matrix_sha256 = _sha256_file(matrix_path)
    current_commit = _current_git_commit()
    current_source_tree_clean = _current_source_tree_clean()
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
        if policy.get("evidence_must_match_current_commit") is not True:
            issues.append("policy.evidence_must_match_current_commit must be true")
        if policy.get("evidence_requires_clean_source") is not True:
            issues.append("policy.evidence_requires_clean_source must be true")
        if policy.get("secrets_must_be_redacted") is not True:
            issues.append("policy.secrets_must_be_redacted must be true")
        if policy.get("order_lifecycle_required") is not True:
            issues.append("policy.order_lifecycle_required must be true")
        if policy.get("allowed_evidence_scopes") != list(ALLOWED_EVIDENCE_SCOPES):
            issues.append(f"policy.allowed_evidence_scopes must be {list(ALLOWED_EVIDENCE_SCOPES)}")
        evidence_dir = Path(
            str(policy.get("evidence_artifact_dir") or "connector-support-evidence")
        )
    if evidence_dir_override is not None:
        evidence_dir = evidence_dir_override

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
    if require_current_commit and current_commit is None:
        issues.append("could not resolve current git commit for connector promotion evidence")
    if require_clean_source and not current_source_tree_clean:
        issues.append("current source tree must be clean for connector promotion evidence")
    if require_evidence and targets:
        resolved_evidence_dir = evidence_dir if evidence_dir.is_absolute() else _repo_root() / evidence_dir
        issues.extend(
            _validate_evidence(
                targets,
                resolved_evidence_dir,
                matrix_sha256=matrix_sha256,
                require_current_commit=require_current_commit,
                require_clean_source=require_clean_source,
            )
        )
    else:
        resolved_evidence_dir = evidence_dir if evidence_dir.is_absolute() else _repo_root() / evidence_dir

    return {
        "ok": not issues,
        "schema_version": matrix.get("schema_version"),
        "matrix_path": str(matrix_path),
        "matrix_sha256": matrix_sha256,
        "evidence_dir": str(resolved_evidence_dir),
        "current_commit": current_commit,
        "current_source_tree_clean": current_source_tree_clean,
        "target_count": len(targets),
        "request_coverage": request_counts,
        "evidence_required": bool(require_evidence),
        "require_current_commit": bool(require_current_commit),
        "require_clean_source": bool(require_clean_source),
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
    parser.add_argument("--require-current-commit", action="store_true", help="Require evidence for the checked-out commit.")
    parser.add_argument("--require-clean-source", action="store_true", help="Require clean-source promotion evidence.")
    parser.add_argument("--evidence-dir", help="Override the connector evidence directory.")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    args = parser.parse_args(argv)

    require_evidence = bool(args.require_evidence and not args.schema_only)
    result = validate(
        Path(args.matrix),
        require_evidence=require_evidence,
        require_current_commit=bool(args.require_current_commit),
        require_clean_source=bool(args.require_clean_source),
        evidence_dir_override=Path(args.evidence_dir) if args.evidence_dir else None,
    )
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
