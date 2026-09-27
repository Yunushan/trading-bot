"""Offline order-intent storage administration; never contacts an exchange."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import MethodType, SimpleNamespace

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_provisioning import (
    migrate_spot_order_intent_store,
    provision_order_intent_store,
    rearm_spot_execution_owner,
    rotate_spot_owner_credentials,
)
from .order_intent_runtime import _query_order_intent_exchange, get_order_intent_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=(
            "status", "initialize", "migrate", "migrate-spot", "rearm", "rotate-credentials",
            "reconcile-spot", "reconcile-spot-account",
        ),
    )
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument("--audit-log-path", type=Path, help="The exact audit path used by the runtime.")
    paths.add_argument("--default-intent-path", action="store_true", help="Use only when no audit path is configured.")
    parser.add_argument("--mode", choices=("Live", "Demo/Testnet"), required=True)
    parser.add_argument("--api-key-env", required=True, help="Environment variable containing the runtime API key; never pass its value.")
    parser.add_argument("--api-secret-env", help="For Spot reconciliation only: environment variable containing the HMAC API secret.")
    parser.add_argument("--account-type", choices=("Spot", "Futures"), default="Futures")
    parser.add_argument("--spot-account-uid-env", help="Environment variable containing the exchange-reported Spot UID.")
    parser.add_argument("--acknowledgement", default="")
    parser.add_argument(
        "--reconciliation-reference", default="",
        help="Operator evidence or incident reference for Spot owner rearm or credential rotation.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Maximum unresolved Spot orders to query (1–100).")
    args = parser.parse_args(argv)
    reconcile_actions = {"reconcile-spot", "reconcile-spot-account"}
    if args.action in reconcile_actions and args.account_type != "Spot":
        parser.error("Spot reconciliation requires --account-type Spot.")
    if args.account_type == "Futures" and not (args.audit_log_path or args.default_intent_path):
        parser.error("Futures storage administration requires an intent path selector.")
    spot_uid = None
    if args.account_type == "Spot":
        if args.action in reconcile_actions:
            if args.mode != "Live":
                parser.error("Spot reconciliation currently supports Live mode only.")
            if not args.api_secret_env:
                parser.error("Spot reconciliation requires --api-secret-env; pass an environment-variable name only.")
            if args.audit_log_path or args.default_intent_path or args.spot_account_uid_env:
                parser.error("Spot reconciliation discovers the UID and selects its ledger; path and UID overrides are not accepted.")
            if not 1 <= args.limit <= 100:
                parser.error("Spot reconciliation --limit must be between 1 and 100.")
        else:
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
        if args.action in reconcile_actions:
            # Import the network transport only for this explicit action so all
            # other storage administration remains offline and SDK-independent.
            from .spot_user_data_admin_runtime import SpotUserDataTransport
            from .order_intent_runtime import (
                _intent_path,
                get_spot_open_order_reconciliation_status,
                reconcile_unresolved_order_intents,
            )
            from .spot_execution_owner import owner_administration_lock

            transport = SpotUserDataTransport(owner.api_key, os.environ.get(args.api_secret_env))
            owner._operator_spot_account_uid = transport.get_account_uid()
            owner.client = transport
            owner._query_order_intent_exchange = MethodType(_query_order_intent_exchange, owner)
            with owner_administration_lock(_intent_path(owner)):
                before = get_order_intent_status(owner)
                results = reconcile_unresolved_order_intents(
                    owner, limit=args.limit, include_execution=True,
                )
                after = get_order_intent_status(owner)

            def count_unresolved(status: dict[str, object]) -> int | None:
                value = status.get("unresolved_count")
                return value if type(value) is int and value >= 0 else None

            remaining = count_unresolved(after)
            initial = count_unresolved(before)
            if args.action == "reconcile-spot":
                portfolio_pending_fill_count = sum(
                    item.get("portfolio_reconciliation_required") is True for item in results
                )
                ok = (
                    initial is not None and initial <= args.limit and remaining == 0
                    and all(item.get("reconciled") is True for item in results)
                    and portfolio_pending_fill_count == 0
                )
                print(json.dumps({
                    "ok": ok,
                    "unresolved_before": initial,
                    "result_count": len(results),
                    "unresolved_after": remaining,
                    "positive_market_fill_needs_portfolio_reconciliation_count": portfolio_pending_fill_count,
                    "results": results,
                }, indent=2))
                return 0 if ok else 1

            overview = transport.get_account_overview()
            account_identity_matches = overview.pop("account_uid", None) == owner._operator_spot_account_uid
            open_orders = transport.get_open_orders()
            open_order_status = get_spot_open_order_reconciliation_status(owner, open_orders)
            clean_local_exchange_state = (
                open_order_status["unmatched_exchange_open_order_count"] == 0
                and open_order_status["local_open_orders_missing_from_exchange_count"] == 0
                and open_order_status["local_open_order_status_conflict_count"] == 0
            )
            portfolio_pending_fill_count = sum(
                item.get("portfolio_reconciliation_required") is True for item in results
            )
            ok = (
                account_identity_matches
                and initial is not None and initial <= args.limit and remaining == 0
                and all(item.get("reconciled") is True for item in results)
                and portfolio_pending_fill_count == 0
                and clean_local_exchange_state
            )
            print(json.dumps({
                "ok": ok,
                "scope": "read-only single-key Live Spot snapshot",
                "account_identity_verified_twice": account_identity_matches,
                **overview,
                "unresolved_before": initial,
                "exact_order_result_count": len(results),
                "unresolved_after": remaining,
                "positive_market_fill_needs_portfolio_reconciliation_count": portfolio_pending_fill_count,
                **open_order_status,
                "balances_reconciled_to_strategy_state": False,
                "external_keys_users_hosts_or_executors_fenced": False,
                "automatic_rearm": False,
            }, indent=2))
            return 0 if ok else 1
        if args.action == "status":
            result = get_order_intent_status(owner)
        elif args.action == "rearm":
            result = rearm_spot_execution_owner(
                owner, acknowledgement=args.acknowledgement,
                reconciliation_reference=args.reconciliation_reference,
            )
        elif args.action == "rotate-credentials":
            result = rotate_spot_owner_credentials(
                owner, acknowledgement=args.acknowledgement,
                reconciliation_reference=args.reconciliation_reference,
            )
        elif args.action == "migrate-spot":
            result = migrate_spot_order_intent_store(
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
