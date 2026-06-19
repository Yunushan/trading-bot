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
        capabilities = _string_list(group.get("capabilities_required"), field=f"{name}.capabilities_required")
        parsed.append(
            {
                "group": name,
                "backend": backend,
                "status": status,
                "venues": venues,
                "capabilities_required": capabilities,
                "capabilities_gated": _string_list(group.get("capabilities_gated"), field=f"{name}.capabilities_gated")
                if "capabilities_gated" in group
                else [],
                "evidence_required": True,
            }
        )
    return parsed


def _support_payload_builder():
    python_root = _repo_root() / "Languages" / "Python"
    sys.path.insert(0, str(python_root))
    from app.settings.exchange_support import build_exchange_support_payload

    return build_exchange_support_payload


def _validate_against_python(groups: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    build_support = _support_payload_builder()
    groups_by_name = {str(group["group"]): group for group in groups}

    ccxt_group = groups_by_name.get("ccxt-crypto-order-routing")
    if not ccxt_group:
        issues.append("missing ccxt-crypto-order-routing group")
    else:
        venues = tuple(ccxt_group["venues"])
        if venues != REQUIRED_CCXT_VENUES:
            issues.append(f"ccxt-crypto-order-routing.venues must be {list(REQUIRED_CCXT_VENUES)}")
        if ccxt_group["backend"] != "ccxt":
            issues.append("ccxt-crypto-order-routing.backend must be ccxt")
        for venue in venues:
            payload = build_support(config={"selected_exchange": venue, "connector_backend": "ccxt"})
            if not payload.get("exchange_supported"):
                issues.append(f"{venue} must be exchange_supported in Python")
            if not payload.get("market_data_supported"):
                issues.append(f"{venue} must support market-data diagnostics in Python")
            if not payload.get("account_snapshot_supported"):
                issues.append(f"{venue} must support account snapshots in Python")
            if not payload.get("order_routing_supported") or not payload.get("order_execution_supported"):
                issues.append(f"{venue} must support ccxt order routing in Python")
            if payload.get("live_evidence_required") is not True:
                issues.append(f"{venue} must require live evidence before official release support")

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
        if not payload.get("trading_supported") or not payload.get("order_execution_supported"):
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
        if not payload.get("order_routing_supported") or not payload.get("order_execution_supported"):
            issues.append(f"{venue} must support broker order routing in Python")
        if payload.get("live_evidence_required") is not True:
            issues.append(f"{venue} must require live evidence before official release support")

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
        evidence_dir = Path(str(policy.get("evidence_artifact_dir") or "connector-support-evidence"))

    try:
        groups = _target_groups(matrix)
    except ValueError as exc:
        groups = []
        issues.append(str(exc))

    if groups:
        issues.extend(_validate_against_python(groups))
    targets = _expanded_targets(groups) if groups else []
    if require_evidence and targets:
        issues.extend(_validate_evidence(targets, _repo_root() / evidence_dir))

    return {
        "ok": not issues,
        "schema_version": matrix.get("schema_version"),
        "matrix_path": str(matrix_path),
        "target_count": len(targets),
        "evidence_required": bool(require_evidence),
        "issues": issues,
        "targets": targets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX_PATH), help="Connector support matrix JSON path.")
    parser.add_argument("--schema-only", action="store_true", help="Validate declarations without requiring artifacts.")
    parser.add_argument("--require-evidence", action="store_true", help="Require passed evidence artifacts.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    require_evidence = bool(args.require_evidence and not args.schema_only)
    result = validate(Path(args.matrix), require_evidence=require_evidence)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"Connector support matrix ok: {result['target_count']} targets")
    else:
        print("Connector support matrix failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
