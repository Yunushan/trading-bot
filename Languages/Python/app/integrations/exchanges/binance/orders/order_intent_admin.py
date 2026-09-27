"""Order-intent administration and explicit read-only Binance Spot recovery."""
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
            "reconcile-spot", "reconcile-spot-account", "recover-spot-market-fills",
        ),
    )
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument("--audit-log-path", type=Path, help="The exact audit path used by the runtime.")
    paths.add_argument("--default-intent-path", action="store_true", help="Use only when no audit path is configured.")
    parser.add_argument("--mode", choices=("Live", "Demo/Testnet"), required=True)
    parser.add_argument("--api-key-env", required=True, help="Environment variable containing the runtime API key; never pass its value.")
    parser.add_argument("--api-secret-env", help="For Spot reconciliation/recovery: environment variable containing the HMAC API secret.")
    parser.add_argument("--account-type", choices=("Spot", "Futures"), default="Futures")
    parser.add_argument("--spot-account-uid-env", help="Environment variable containing the exchange-reported Spot UID.")
    parser.add_argument("--acknowledgement", default="")
    parser.add_argument(
        "--reconciliation-reference", default="",
        help="Operator evidence or incident reference for Spot owner rearm or credential rotation.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Maximum unresolved Spot orders to query (1–100).")
    args = parser.parse_args(argv)
    reconcile_actions = {"reconcile-spot", "reconcile-spot-account", "recover-spot-market-fills"}
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
                _get_order_intent_record,
                _intent_path,
                _mark_order_intent_portfolio_reconciled,
                get_spot_open_order_reconciliation_status,
                reconcile_order_intent,
                reconcile_unresolved_order_intents,
            )
            from .spot_execution_owner import owner_administration_lock
            from .spot_fill_recovery_runtime import (
                collect_spot_order_trades,
                persist_spot_buy_allocation,
                summarize_spot_market_fill,
            )

            transport = SpotUserDataTransport(owner.api_key, os.environ.get(args.api_secret_env))
            owner._operator_spot_account_uid = transport.get_account_uid()
            owner.client = transport
            owner._query_order_intent_exchange = MethodType(_query_order_intent_exchange, owner)
            owner._mark_order_intent_portfolio_reconciled = MethodType(
                _mark_order_intent_portfolio_reconciled, owner,
            )
            with owner_administration_lock(_intent_path(owner)):
                before = get_order_intent_status(owner)
                if args.action == "recover-spot-market-fills":
                    unresolved_ids = before.get("unresolved_client_order_ids")
                    if not isinstance(unresolved_ids, list):
                        raise LiveTradingSafetyError("Spot order intent status is invalid.")
                    recovered_count = 0
                    recovered_trade_count = 0
                    unsupported_count = 0
                    failed_count = 0
                    for client_order_id in unresolved_ids[:args.limit]:
                        observation = reconcile_order_intent(
                            owner, str(client_order_id), include_execution=True,
                        )
                        response = observation.get("order_response")
                        if not isinstance(response, dict) or observation.get("portfolio_reconciliation_required") is not True:
                            if observation.get("reconciled") is not True:
                                failed_count += 1
                            continue
                        intent = _get_order_intent_record(owner, str(client_order_id))
                        if (
                            not isinstance(intent, dict)
                            or intent.get("market") != "spot"
                            or intent.get("type") != "MARKET"
                            or intent.get("side") != "BUY"
                        ):
                            unsupported_count += 1
                            continue
                        try:
                            symbol = str(intent.get("symbol") or "")
                            order_id = int(str(intent.get("exchange_order_id") or "0"))
                            base_asset, quote_asset = transport.get_symbol_assets(symbol=symbol)
                            trades = collect_spot_order_trades(
                                transport, symbol=symbol, order_id=order_id,
                            )
                            fill = summarize_spot_market_fill(
                                intent, response, trades,
                                base_asset=base_asset, quote_asset=quote_asset,
                            )
                            from app.gui.shared.allocation_persistence import get_position_allocations_path

                            app_root = Path(__file__).resolve().parents[4]
                            allocation_path = get_position_allocations_path(
                                app_root / "gui" / "window_shell.py",
                            )
                            persist_spot_buy_allocation(allocation_path, fill)
                            owner._mark_order_intent_portfolio_reconciled(
                                str(client_order_id),
                                portfolio_signature=str(fill["signature"]),
                                portfolio_quantity=str(fill["net_qty"]),
                            )
                            recovered_count += 1
                            recovered_trade_count += int(fill["trade_count"])
                        except Exception:
                            failed_count += 1
                    identity_verified_twice = transport.get_account_uid() == owner._operator_spot_account_uid
                    after = get_order_intent_status(owner)
                    remaining_value = after.get("unresolved_count")
                    initial_value = before.get("unresolved_count")
                    remaining = remaining_value if type(remaining_value) is int and remaining_value >= 0 else None
                    initial = initial_value if type(initial_value) is int and initial_value >= 0 else None
                    ok = (
                        identity_verified_twice
                        and initial is not None and initial <= args.limit and remaining == 0
                        and unsupported_count == 0 and failed_count == 0
                    )
                    print(json.dumps({
                        "ok": ok,
                        "scope": "read-only Binance Spot queries plus local BUY allocation recovery",
                        "account_identity_verified_twice": identity_verified_twice,
                        "unresolved_before": initial,
                        "recovered_buy_fill_count": recovered_count,
                        "recovered_trade_count": recovered_trade_count,
                        "unsupported_positive_fill_count": unsupported_count,
                        "failed_recovery_count": failed_count,
                        "unresolved_after": remaining,
                        "automatic_rearm": False,
                        "exchange_orders_placed": False,
                    }, indent=2))
                    return 0 if ok else 1
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
