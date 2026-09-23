"""Offline order-intent storage administration; never contacts an exchange."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_provisioning import provision_order_intent_store, rearm_spot_execution_owner
from .order_intent_runtime import get_order_intent_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "initialize", "migrate", "rearm"))
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument("--audit-log-path", type=Path, help="The exact audit path used by the runtime.")
    paths.add_argument("--default-intent-path", action="store_true", help="Use only when no audit path is configured.")
    parser.add_argument("--mode", choices=("Live", "Demo/Testnet"), required=True)
    parser.add_argument("--api-key-env", required=True, help="Environment variable containing the runtime API key; never pass its value.")
    parser.add_argument("--account-type", choices=("Spot", "Futures"), default="Futures")
    parser.add_argument("--spot-account-uid-env", help="Environment variable containing the exchange-reported Spot UID.")
    parser.add_argument("--acknowledgement", default="")
    parser.add_argument("--reconciliation-reference", default="", help="Operator evidence or incident reference for Spot owner rearm.")
    args = parser.parse_args(argv)
    if args.account_type == "Futures" and not (args.audit_log_path or args.default_intent_path):
        parser.error("Futures storage administration requires an intent path selector.")
    spot_uid = None
    if args.account_type == "Spot":
        raw_uid = os.environ.get(args.spot_account_uid_env or "", "")
        try:
            spot_uid = int(raw_uid) if raw_uid.isascii() and raw_uid.isdigit() else None
        except ValueError:
            spot_uid = None
        if spot_uid is None or spot_uid <= 0:
            parser.error("Spot storage administration requires --spot-account-uid-env with a positive UID.")
    if args.account_type == "Spot" and args.mode != "Live":
        parser.error("Spot owner administration currently covers Live mode only.")
    owner = SimpleNamespace(
        _order_audit_log_path=args.audit_log_path, mode=args.mode,
        api_key=os.environ.get(args.api_key_env), account_type=args.account_type.upper(),
        _enforce_spot_execution_owner=args.account_type == "Spot",
        _operator_spot_account_uid=spot_uid,
    )
    try:
        if args.action == "status":
            result = get_order_intent_status(owner)
        elif args.action == "rearm":
            result = rearm_spot_execution_owner(
                owner, acknowledgement=args.acknowledgement,
                reconciliation_reference=args.reconciliation_reference,
            )
        else:
            result = provision_order_intent_store(owner, acknowledgement=args.acknowledgement, migrate=args.action == "migrate")
    except LiveTradingSafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
