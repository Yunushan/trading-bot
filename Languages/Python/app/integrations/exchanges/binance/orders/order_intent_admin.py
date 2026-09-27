"""Order-intent administration and explicit read-only Binance Spot recovery."""
from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path
from types import MethodType, SimpleNamespace
from uuid import uuid4

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_provisioning import (
    migrate_spot_order_intent_store,
    provision_order_intent_store,
    rearm_spot_execution_owner,
    rotate_spot_owner_credentials,
)
from .order_intent_runtime import _query_order_intent_exchange, get_order_intent_status
from .spot_exchange_errors import SPOT_EXCHANGE_ERRORS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=(
            "status", "initialize", "migrate", "migrate-spot", "rearm", "rotate-credentials",
            "reconcile-spot", "reconcile-spot-account", "recover-spot-market-fills", "recover-spot-opos",
            "cancel-spot-opos", "rearm-spot-opos",
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
    parser.add_argument(
        "--order-list-client-id",
        help="For cancel-spot-opos or rearm-spot-opos: one exact recovered OPO list client ID.",
    )
    args = parser.parse_args(argv)
    reconcile_actions = {
        "reconcile-spot", "reconcile-spot-account", "recover-spot-market-fills", "recover-spot-opos",
        "cancel-spot-opos", "rearm-spot-opos",
    }
    if args.action in reconcile_actions and args.account_type != "Spot":
        parser.error("Spot reconciliation requires --account-type Spot.")
    if args.account_type == "Futures" and not (args.audit_log_path or args.default_intent_path):
        parser.error("Futures storage administration requires an intent path selector.")
    if args.action in {"cancel-spot-opos", "rearm-spot-opos"} and not args.order_list_client_id:
        parser.error(f"{args.action} requires --order-list-client-id for exactly one recovered OPO.")
    if args.action not in {"cancel-spot-opos", "rearm-spot-opos"} and args.order_list_client_id:
        parser.error("--order-list-client-id is only supported by exact OPO cancel/rearm actions.")
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
                _mark_spot_opo_entry_reconciled,
                _mark_spot_opo_exit_reconciled,
                _mark_spot_opo_residual_stop_no_fill,
                _mark_spot_opo_residual_stop_order_observed,
                _mark_spot_opo_residual_stop_reconciled,
                _mark_spot_opo_residual_stop_unknown,
                _mark_spot_opo_strategy_exit_residual_required,
                _mark_spot_opo_strategy_exit_order_observed,
                _mark_spot_opo_strategy_exit_reconciled,
                _mark_spot_opo_strategy_exit_response,
                _begin_spot_opo_residual_stop,
                cancel_spot_opo_intent,
                get_spot_open_order_reconciliation_status,
                reconcile_order_intent,
                reconcile_spot_opo_intent,
                reconcile_unresolved_order_intents,
            )
            from .spot_execution_owner import owner_administration_lock
            from .spot_fill_recovery_runtime import (
                collect_spot_order_trades,
                persist_spot_buy_allocation,
                persist_spot_opo_stop_sell_allocation,
                persist_spot_opo_residual_stop_allocation,
                persist_spot_opo_strategy_sell_allocation,
                persist_spot_sell_allocation,
                summarize_spot_market_fill,
                summarize_spot_opo_buy_fill,
                summarize_spot_opo_stop_sell_fill,
                summarize_spot_opo_residual_stop_sell_fill,
                summarize_spot_opo_strategy_sell_fill,
                spot_opo_allocation_baseline,
            )

            api_secret = os.environ.get(args.api_secret_env)
            transport = SpotUserDataTransport(owner.api_key, api_secret)
            owner._operator_spot_account_uid = transport.get_account_uid()
            owner.client = transport
            if args.action == "cancel-spot-opos":
                from .spot_user_data_admin_runtime import SpotOrderListCancellationTransport

                cancellation_transport = SpotOrderListCancellationTransport(
                    owner.api_key, os.environ.get(args.api_secret_env),
                )
                owner.client = SimpleNamespace(
                    get_order_list=transport.get_order_list,
                    get_order=transport.get_order,
                    cancel_order_list=cancellation_transport.cancel_order_list,
                )
            owner._query_order_intent_exchange = MethodType(_query_order_intent_exchange, owner)
            owner._mark_order_intent_portfolio_reconciled = MethodType(
                _mark_order_intent_portfolio_reconciled, owner,
            )
            owner._mark_spot_opo_entry_reconciled = MethodType(
                _mark_spot_opo_entry_reconciled, owner,
            )
            owner._mark_spot_opo_exit_reconciled = MethodType(
                _mark_spot_opo_exit_reconciled, owner,
            )
            owner._mark_spot_opo_strategy_exit_order_observed = MethodType(
                _mark_spot_opo_strategy_exit_order_observed, owner,
            )
            owner._mark_spot_opo_strategy_exit_reconciled = MethodType(
                _mark_spot_opo_strategy_exit_reconciled, owner,
            )
            owner._mark_spot_opo_strategy_exit_response = MethodType(
                _mark_spot_opo_strategy_exit_response, owner,
            )
            owner._mark_spot_opo_strategy_exit_residual_required = MethodType(
                _mark_spot_opo_strategy_exit_residual_required, owner,
            )
            owner._begin_spot_opo_residual_stop = MethodType(_begin_spot_opo_residual_stop, owner)
            owner._mark_spot_opo_residual_stop_unknown = MethodType(_mark_spot_opo_residual_stop_unknown, owner)
            owner._mark_spot_opo_residual_stop_order_observed = MethodType(
                _mark_spot_opo_residual_stop_order_observed, owner,
            )
            owner._mark_spot_opo_residual_stop_reconciled = MethodType(
                _mark_spot_opo_residual_stop_reconciled, owner,
            )
            owner._mark_spot_opo_residual_stop_no_fill = MethodType(
                _mark_spot_opo_residual_stop_no_fill, owner,
            )
            with owner_administration_lock(_intent_path(owner)):
                before = get_order_intent_status(owner)
                if args.action == "cancel-spot-opos":
                    target_id = str(args.order_list_client_id or "")
                    intent = _get_order_intent_record(owner, target_id)
                    if not isinstance(intent, dict) or intent.get("type") != "OPO":
                        raise LiveTradingSafetyError("The exact Spot OPO list client ID was not found in local state.")
                    result = cancel_spot_opo_intent(owner, target_id)
                    identity_verified_twice = transport.get_account_uid() == owner._operator_spot_account_uid
                    after = get_order_intent_status(owner)
                    initial_value = before.get("unresolved_count")
                    remaining_value = after.get("unresolved_count")
                    initial = initial_value if type(initial_value) is int and initial_value >= 0 else None
                    remaining = remaining_value if type(remaining_value) is int and remaining_value >= 0 else None
                    ok = identity_verified_twice and result.get("cancel_confirmed") is True
                    print(json.dumps({
                        "ok": ok,
                        "scope": "one exact recovered Binance Spot OPO list cancellation",
                        "account_identity_verified_twice": identity_verified_twice,
                        "cancel_confirmed": result.get("cancel_confirmed") is True,
                        "protection_state": result.get("protection_state"),
                        "already_cancelled": result.get("already_cancelled") is True,
                        "requires_stop_fill_recovery": result.get("requires_stop_fill_recovery") is True,
                        "requires_manual_reconciliation": result.get("requires_manual_reconciliation") is True,
                        "unresolved_before": initial,
                        "unresolved_after": remaining,
                        "strategy_sell_submitted": False,
                        "automatic_rearm": False,
                        "exchange_order_lists_cancelled": 1 if result.get("cancel_confirmed") is True and not result.get("already_cancelled") else 0,
                    }, indent=2))
                    return 0 if ok else 1
                if args.action == "rearm-spot-opos":
                    from .spot_user_data_admin_runtime import SpotResidualStopTransport
                    from .spot_opo_runtime import build_spot_opo_residual_stop_request
                    from app.settings.live_safety import validate_live_trading_safety

                    target_id = str(args.order_list_client_id or "")
                    intent = _get_order_intent_record(owner, target_id)
                    if not isinstance(intent, dict) or intent.get("type") != "OPO":
                        raise LiveTradingSafetyError("The exact Spot OPO list client ID was not found in local state.")
                    unresolved_ids = before.get("unresolved_client_order_ids")
                    if not isinstance(unresolved_ids, list) or any(str(item) != target_id for item in unresolved_ids):
                        raise LiveTradingSafetyError("Other unresolved Spot intents must be reconciled before residual protection.")
                    observation = reconcile_spot_opo_intent(owner, target_id, force=True)
                    intent = _get_order_intent_record(owner, target_id)
                    if (
                        not isinstance(intent, dict)
                        or observation.get("error")
                        or observation.get("protection_state") != "cancelled"
                        or intent.get("residual_stop_state") != "rearm_required"
                    ):
                        raise LiveTradingSafetyError("Exact OPO cancellation and recovered residual allocation are required before re-arm.")
                    from app.gui.shared.allocation_persistence import get_position_allocations_path

                    app_root = Path(__file__).resolve().parents[4]
                    allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
                    baseline = spot_opo_allocation_baseline(
                        allocation_path,
                        symbol=str(intent.get("symbol") or ""),
                        list_client_order_id=target_id,
                        expected_quantity=intent.get("residual_rearm_quantity"),
                    )
                    if (
                        baseline.get("signature") != intent.get("residual_rearm_signature")
                        or Decimal(str(baseline.get("quantity"))) != Decimal(str(intent.get("residual_rearm_quantity")))
                    ):
                        raise LiveTradingSafetyError("Live Spot residual allocation changed; re-arm is blocked.")
                    symbol = str(intent.get("symbol") or "")
                    symbol_info = transport.get_symbol_info(symbol=symbol)
                    last_price = transport.get_last_price(symbol=symbol)
                    filters = symbol_info.get("filters")
                    needs_average = False
                    if isinstance(filters, list):
                        for row in filters:
                            if not isinstance(row, dict):
                                continue
                            if (
                                row.get("filterType") == "MIN_NOTIONAL" and row.get("applyToMarket") is True
                                and row.get("avgPriceMins") != 0
                            ) or (
                                row.get("filterType") == "NOTIONAL"
                                and (row.get("applyMinToMarket") is True or row.get("applyMaxToMarket") is True)
                                and row.get("avgPriceMins") != 0
                            ):
                                needs_average = True
                    average = transport.get_average_price(symbol=symbol) if needs_average else None
                    new_client_id = f"rs{uuid4().hex[:34]}"
                    request = build_spot_opo_residual_stop_request(
                        intent,
                        symbol_info=symbol_info,
                        quantity=baseline["quantity"],
                        last_price=last_price,
                        average_price=average.get("price") if average else None,
                        average_price_mins=average.get("mins") if average else None,
                        new_client_order_id=new_client_id,
                    )
                    validate_live_trading_safety(
                        mode=args.mode,
                        api_key=owner.api_key,
                        api_secret=api_secret,
                        account_type="Spot",
                        config={},
                    )
                    if transport.get_account_uid() != owner._operator_spot_account_uid:
                        raise LiveTradingSafetyError("Binance Spot account identity changed before residual-stop submission.")
                    begun = owner._begin_spot_opo_residual_stop(
                        target_id,
                        allocation_path=allocation_path,
                        request=request,
                        pre_order_portfolio_signature=baseline["signature"],
                        pre_order_portfolio_quantity=baseline["quantity"],
                    )
                    if begun.get("residual_stop_request") != request:
                        raise LiveTradingSafetyError("Persisted residual-stop request differs from the preflight request.")
                    stop_transport = SpotResidualStopTransport(owner.api_key, api_secret)
                    try:
                        acknowledgement = stop_transport.place_stop_loss_sell(request)
                    except SPOT_EXCHANGE_ERRORS as exc:
                        owner._mark_spot_opo_residual_stop_unknown(target_id, error=exc)
                        after = get_order_intent_status(owner)
                        identity_verified_twice = transport.get_account_uid() == owner._operator_spot_account_uid
                        print(json.dumps({
                            "ok": False,
                            "scope": "one exact Binance Spot OPO residual STOP_LOSS SELL submission",
                            "account_identity_verified_twice": identity_verified_twice,
                            "submission_state": "unknown",
                            "order_list_client_id": target_id,
                            "residual_stop_client_order_id": new_client_id,
                            "unresolved_after": after.get("unresolved_count"),
                            "exchange_orders_placed": 1,
                            "retry_allowed": False,
                        }, indent=2))
                        return 1
                    try:
                        owner._mark_spot_opo_residual_stop_order_observed(
                            target_id, order_response=acknowledgement, exact_query=False,
                        )
                        exact_order = transport.get_order(
                            symbol=symbol, origClientOrderId=new_client_id,
                        )
                        evidence = owner._mark_spot_opo_residual_stop_order_observed(
                            target_id, order_response=exact_order, exact_query=True,
                        )
                    except SPOT_EXCHANGE_ERRORS:
                        current = _get_order_intent_record(owner, target_id)
                        if isinstance(current, dict) and current.get("residual_stop_state") in {"submitted", "unknown"}:
                            owner._mark_spot_opo_residual_stop_unknown(
                                target_id, error="Residual stop acknowledgement or exact query was not verified.",
                            )
                        raise
                    identity_verified_twice = transport.get_account_uid() == owner._operator_spot_account_uid
                    after = get_order_intent_status(owner)
                    safe_active = evidence.get("status") == "NEW" and evidence.get("executed_quantity") == "0"
                    ok = identity_verified_twice and safe_active and after.get("unresolved_count") == 0
                    print(json.dumps({
                        "ok": ok,
                        "scope": "one exact Binance Spot OPO residual STOP_LOSS SELL submission",
                        "account_identity_verified_twice": identity_verified_twice,
                        "order_list_client_id": target_id,
                        "residual_stop_client_order_id": new_client_id,
                        "residual_stop_order_id": evidence.get("order_id"),
                        "residual_stop_status": evidence.get("status"),
                        "residual_quantity": evidence.get("original_quantity"),
                        "unresolved_after": after.get("unresolved_count"),
                        "requires_stop_fill_recovery": not safe_active,
                        "exchange_orders_placed": 1,
                    }, indent=2))
                    return 0 if ok else 1
                if args.action == "recover-spot-opos":
                    candidate_ids = before.get("spot_opo_client_order_ids")
                    if not isinstance(candidate_ids, list):
                        raise LiveTradingSafetyError("Spot order intent status is invalid.")
                    recovered_entry_count = 0
                    recovered_exit_count = 0
                    recovered_strategy_exit_count = 0
                    verified_no_fill_count = 0
                    recovered_trade_count = 0
                    unsupported_count = 0
                    failed_count = 0
                    selected_ids = candidate_ids[:args.limit]
                    for client_order_id in selected_ids:
                        intent = _get_order_intent_record(owner, str(client_order_id))
                        if not isinstance(intent, dict) or intent.get("type") != "OPO":
                            unsupported_count += 1
                            continue
                        observation = reconcile_spot_opo_intent(owner, str(client_order_id), force=True)
                        intent = _get_order_intent_record(owner, str(client_order_id))
                        if not isinstance(intent, dict):
                            failed_count += 1
                            continue
                        if (
                            intent.get("state") == "rejected"
                            and intent.get("protection_state") == "none"
                            and observation.get("reconciled") is True
                        ):
                            verified_no_fill_count += 1
                            continue
                        try:
                            if observation.get("error"):
                                raise LiveTradingSafetyError("Binance OPO state could not be verified.")
                            request = intent.get("request")
                            if not isinstance(request, dict):
                                raise LiveTradingSafetyError("Spot OPO request is missing from its intent.")
                            symbol = str(intent.get("symbol") or "")
                            from app.gui.shared.allocation_persistence import get_position_allocations_path

                            app_root = Path(__file__).resolve().parents[4]
                            allocation_path = get_position_allocations_path(app_root / "gui" / "window_shell.py")
                            if intent.get("entry_reconciled") is not True:
                                working_client_id = str(request.get("workingClientOrderId") or "")
                                working_order = transport.get_order(
                                    symbol=symbol, origClientOrderId=working_client_id,
                                )
                                working_order_id = int(str(intent.get("working_order_id") or "0"))
                                base_asset, quote_asset = transport.get_symbol_assets(symbol=symbol)
                                buy_trades = collect_spot_order_trades(
                                    transport, symbol=symbol, order_id=working_order_id,
                                )
                                buy_fill = summarize_spot_opo_buy_fill(
                                    intent, working_order, buy_trades,
                                    base_asset=base_asset, quote_asset=quote_asset,
                                )
                                persist_spot_buy_allocation(allocation_path, buy_fill)
                                refreshed = reconcile_spot_opo_intent(owner, str(client_order_id), force=True)
                                intent = _get_order_intent_record(owner, str(client_order_id))
                                if not isinstance(intent, dict) or refreshed.get("error"):
                                    raise LiveTradingSafetyError("The linked OPO state changed during BUY recovery.")
                                owner._mark_spot_opo_entry_reconciled(
                                    str(client_order_id),
                                    portfolio_signature=str(buy_fill["signature"]),
                                    portfolio_quantity=str(buy_fill["net_qty"]),
                                )
                                intent = _get_order_intent_record(owner, str(client_order_id))
                                if not isinstance(intent, dict):
                                    raise LiveTradingSafetyError("Spot OPO intent disappeared during BUY recovery.")
                                recovered_entry_count += 1
                                recovered_trade_count += int(buy_fill["trade_count"])

                            strategy_exit_state = intent.get("strategy_exit_state")
                            if strategy_exit_state == "completed":
                                continue
                            residual_state = intent.get("residual_stop_state")
                            if residual_state == "completed":
                                continue
                            if residual_state is not None:
                                if residual_state == "rearm_required":
                                    unsupported_count += 1
                                    continue
                                if residual_state not in {"submitted", "unknown", "acknowledged", "active", "triggered"}:
                                    unsupported_count += 1
                                    continue
                                residual_request = intent.get("residual_stop_request")
                                if not isinstance(residual_request, dict):
                                    raise LiveTradingSafetyError("Residual STOP_LOSS request is missing from its durable intent.")
                                residual_client_id = str(residual_request.get("newClientOrderId") or "")
                                residual_order = transport.get_order(
                                    symbol=symbol, origClientOrderId=residual_client_id,
                                )
                                if "code" in residual_order:
                                    failed_count += 1
                                    continue
                                residual_evidence = _mark_spot_opo_residual_stop_order_observed(
                                    owner,
                                    str(client_order_id),
                                    order_response=residual_order,
                                    exact_query=True,
                                )
                                intent = _get_order_intent_record(owner, str(client_order_id))
                                if not isinstance(intent, dict):
                                    raise LiveTradingSafetyError("Residual OPO stop intent disappeared during exact recovery.")
                                if residual_evidence.get("status") == "NEW":
                                    continue
                                if not residual_evidence.get("terminal"):
                                    unsupported_count += 1
                                    continue
                                residual_order_id = int(residual_evidence["order_id"])
                                residual_trades = collect_spot_order_trades(
                                    transport, symbol=symbol, order_id=residual_order_id,
                                )
                                if residual_evidence.get("executed_quantity") == "0":
                                    if residual_trades:
                                        raise LiveTradingSafetyError("Zero-execution residual stop has non-empty exact trade history.")
                                    owner._mark_spot_opo_residual_stop_no_fill(
                                        str(client_order_id),
                                        allocation_path=allocation_path,
                                        no_trades_confirmed=True,
                                    )
                                    unsupported_count += 1
                                    continue
                                base_asset, quote_asset = transport.get_symbol_assets(symbol=symbol)
                                residual_fill = summarize_spot_opo_residual_stop_sell_fill(
                                    intent,
                                    residual_order,
                                    residual_trades,
                                    base_asset=base_asset,
                                    quote_asset=quote_asset,
                                )
                                persist_spot_opo_residual_stop_allocation(allocation_path, residual_fill)
                                pre_stop_quantity = Decimal(str(intent.get("residual_stop_pre_order_quantity")))
                                remaining_quantity = pre_stop_quantity - Decimal(str(residual_fill["portfolio_qty"]))
                                if remaining_quantity < 0:
                                    raise LiveTradingSafetyError("Residual STOP_LOSS consumed more than its exact OPO allocation.")
                                owner._mark_spot_opo_residual_stop_reconciled(
                                    str(client_order_id),
                                    allocation_path=allocation_path,
                                    fill_signature=str(residual_fill["signature"]),
                                    consumed_quantity=residual_fill["portfolio_qty"],
                                    remaining_quantity=remaining_quantity,
                                    trade_ids=list(residual_fill["trade_ids"]),
                                    fill_time_ms=int(residual_fill["fill_time_ms"]),
                                )
                                recovered_exit_count += 1
                                recovered_trade_count += int(residual_fill["trade_count"])
                                if remaining_quantity > 0:
                                    unsupported_count += 1
                                continue
                            if strategy_exit_state not in (None, "no_effect"):
                                if intent.get("protection_state") != "cancelled":
                                    if strategy_exit_state == "no_effect":
                                        pass
                                    else:
                                        unsupported_count += 1
                                        continue
                                elif strategy_exit_state == "stop_cancelled":
                                    current_baseline = spot_opo_allocation_baseline(
                                        allocation_path,
                                        symbol=symbol,
                                        list_client_order_id=str(client_order_id),
                                        expected_quantity=intent.get("entry_portfolio_quantity"),
                                    )
                                    owner._mark_spot_opo_strategy_exit_residual_required(
                                        str(client_order_id),
                                        allocation_path=allocation_path,
                                        portfolio_signature=current_baseline["signature"],
                                        portfolio_quantity=current_baseline["quantity"],
                                        no_fill=True,
                                    )
                                    unsupported_count += 1
                                    continue
                                else:
                                    exit_request = intent.get("strategy_exit_request")
                                    if not isinstance(exit_request, dict):
                                        raise LiveTradingSafetyError("Linked OPO SELL request is missing from its ledger.")
                                    exit_client_id = str(intent.get("strategy_exit_client_order_id") or "")
                                    exit_order = transport.get_order(
                                        symbol=symbol, origClientOrderId=exit_client_id,
                                    )
                                    if strategy_exit_state in {"submitted", "unknown"} and intent.get("strategy_exit_outcome") is None:
                                        pending_order = transport.get_order(
                                            symbol=symbol,
                                            origClientOrderId=str(request.get("pendingClientOrderId") or ""),
                                        )
                                        if (
                                            pending_order.get("symbol") != symbol
                                            or pending_order.get("clientOrderId") != request.get("pendingClientOrderId")
                                            or pending_order.get("orderId") != intent.get("pending_order_id")
                                            or pending_order.get("orderListId") != intent.get("exchange_order_list_id")
                                            or pending_order.get("side") != "SELL"
                                            or pending_order.get("type") != "STOP_LOSS"
                                            or pending_order.get("status") != "CANCELED"
                                            or Decimal(str(pending_order.get("executedQty"))) != 0
                                        ):
                                            raise LiveTradingSafetyError("Canceled OPO stop lacks exact child-order proof.")
                                        _mark_spot_opo_strategy_exit_response(
                                            owner,
                                            str(client_order_id),
                                            response={
                                                "cancelResult": "SUCCESS",
                                                "newOrderResult": "SUCCESS",
                                                "cancelResponse": {
                                                    "symbol": symbol,
                                                    "orderId": intent.get("pending_order_id"),
                                                    "origClientOrderId": request.get("pendingClientOrderId"),
                                                    "side": "SELL",
                                                    "status": "CANCELED",
                                                    "executedQty": "0",
                                                },
                                                "newOrderResponse": exit_order,
                                            },
                                        )
                                        intent = _get_order_intent_record(owner, str(client_order_id))
                                        if not isinstance(intent, dict):
                                            raise LiveTradingSafetyError("Linked OPO SELL intent disappeared during recovery.")
                                        refreshed_exit = reconcile_spot_opo_intent(
                                            owner, str(client_order_id), force=True,
                                        )
                                        intent = _get_order_intent_record(owner, str(client_order_id))
                                        if (
                                            not isinstance(intent, dict)
                                            or refreshed_exit.get("error")
                                            or refreshed_exit.get("protection_state") != "cancelled"
                                        ):
                                            raise LiveTradingSafetyError("Canceled OPO stop changed during linked SELL recovery.")
                                        exit_order = transport.get_order(
                                            symbol=symbol, origClientOrderId=exit_client_id,
                                        )
                                    if intent.get("strategy_exit_state") != "sell_accepted":
                                        unsupported_count += 1
                                        continue
                                    exit_evidence = _mark_spot_opo_strategy_exit_order_observed(
                                        owner,
                                        str(client_order_id),
                                        order_response=exit_order,
                                    )
                                    intent = _get_order_intent_record(owner, str(client_order_id))
                                    if not isinstance(intent, dict):
                                        raise LiveTradingSafetyError("Linked OPO SELL intent disappeared during fill recovery.")
                                    if not exit_evidence.get("terminal"):
                                        unsupported_count += 1
                                        continue
                                    exit_order_id = int(exit_evidence["order_id"])
                                    exit_trades = collect_spot_order_trades(
                                        transport, symbol=symbol, order_id=exit_order_id,
                                    )
                                    if exit_evidence.get("executed_quantity") == "0":
                                        if exit_trades:
                                            raise LiveTradingSafetyError("Zero-execution linked SELL has non-empty exact trade history.")
                                        current_baseline = spot_opo_allocation_baseline(
                                            allocation_path,
                                            symbol=symbol,
                                            list_client_order_id=str(client_order_id),
                                            expected_quantity=intent.get("strategy_exit_pre_order_quantity"),
                                        )
                                        owner._mark_spot_opo_strategy_exit_residual_required(
                                            str(client_order_id),
                                            allocation_path=allocation_path,
                                            portfolio_signature=current_baseline["signature"],
                                            portfolio_quantity=current_baseline["quantity"],
                                            no_fill=True,
                                            no_trades_confirmed=True,
                                        )
                                        unsupported_count += 1
                                        continue
                                    base_asset, quote_asset = transport.get_symbol_assets(symbol=symbol)
                                    exit_fill = summarize_spot_opo_strategy_sell_fill(
                                        intent,
                                        exit_order,
                                        exit_trades,
                                        base_asset=base_asset,
                                        quote_asset=quote_asset,
                                    )
                                    entry_quantity = Decimal(str(intent.get("entry_portfolio_quantity")))
                                    consumed_quantity = Decimal(str(exit_fill["portfolio_qty"]))
                                    if (
                                        consumed_quantity <= 0
                                        or consumed_quantity >= entry_quantity
                                        and exit_evidence.get("status") != "FILLED"
                                        or exit_evidence.get("status") == "FILLED"
                                        and consumed_quantity != entry_quantity
                                    ):
                                        raise LiveTradingSafetyError("Linked SELL fee-aware execution does not leave a verifiable residual.")
                                    persist_spot_opo_strategy_sell_allocation(allocation_path, exit_fill)
                                    recovered_trade_count += int(exit_fill["trade_count"])
                                    if exit_evidence.get("status") == "FILLED":
                                        _mark_spot_opo_strategy_exit_reconciled(
                                            owner,
                                            str(client_order_id),
                                            allocation_path=allocation_path,
                                            portfolio_signature=str(exit_fill["signature"]),
                                            portfolio_quantity=exit_fill["portfolio_qty"],
                                            trade_ids=list(exit_fill["trade_ids"]),
                                            fill_time_ms=int(exit_fill["fill_time_ms"]),
                                        )
                                        recovered_strategy_exit_count += 1
                                    else:
                                        remaining_quantity = entry_quantity - consumed_quantity
                                        current_baseline = spot_opo_allocation_baseline(
                                            allocation_path,
                                            symbol=symbol,
                                            list_client_order_id=str(client_order_id),
                                            expected_quantity=remaining_quantity,
                                        )
                                        owner._mark_spot_opo_strategy_exit_residual_required(
                                            str(client_order_id),
                                            allocation_path=allocation_path,
                                            portfolio_signature=current_baseline["signature"],
                                            portfolio_quantity=current_baseline["quantity"],
                                            fill_signature=str(exit_fill["signature"]),
                                            consumed_quantity=consumed_quantity,
                                            trade_ids=list(exit_fill["trade_ids"]),
                                            fill_time_ms=int(exit_fill["fill_time_ms"]),
                                        )
                                        unsupported_count += 1
                                    continue

                            if intent.get("protection_state") == "triggered":
                                if intent.get("exit_reconciled") is True:
                                    continue
                                if intent.get("entry_reconciled") is not True:
                                    raise LiveTradingSafetyError("Triggered OPO stop has no durable entry proof.")
                                pending_client_id = str(request.get("pendingClientOrderId") or "")
                                stop_order = transport.get_order(
                                    symbol=symbol, origClientOrderId=pending_client_id,
                                )
                                stop_order_id = int(str(intent.get("pending_order_id") or "0"))
                                base_asset, quote_asset = transport.get_symbol_assets(symbol=symbol)
                                stop_trades = collect_spot_order_trades(
                                    transport, symbol=symbol, order_id=stop_order_id,
                                )
                                stop_fill = summarize_spot_opo_stop_sell_fill(
                                    intent, stop_order, stop_trades,
                                    base_asset=base_asset, quote_asset=quote_asset,
                                )
                                persist_spot_opo_stop_sell_allocation(allocation_path, stop_fill)
                                refreshed = reconcile_spot_opo_intent(owner, str(client_order_id), force=True)
                                if (
                                    refreshed.get("protection_state") != "triggered"
                                    or refreshed.get("error")
                                ):
                                    raise LiveTradingSafetyError("The OPO stop state changed during SELL recovery.")
                                owner._mark_spot_opo_exit_reconciled(
                                    str(client_order_id),
                                    portfolio_signature=str(stop_fill["signature"]),
                                    portfolio_quantity=str(stop_fill["portfolio_qty"]),
                                )
                                recovered_exit_count += 1
                                recovered_trade_count += int(stop_fill["trade_count"])
                            elif intent.get("protection_state") != "active" or intent.get("entry_reconciled") is not True:
                                unsupported_count += 1
                        except SPOT_EXCHANGE_ERRORS:
                            failed_count += 1
                    identity_verified_twice = transport.get_account_uid() == owner._operator_spot_account_uid
                    after = get_order_intent_status(owner)
                    remaining_value = after.get("unresolved_count")
                    initial_value = before.get("unresolved_count")
                    remaining = remaining_value if type(remaining_value) is int and remaining_value >= 0 else None
                    initial = initial_value if type(initial_value) is int and initial_value >= 0 else None
                    ok = (
                        identity_verified_twice
                        and len(candidate_ids) <= args.limit and remaining == 0
                        and unsupported_count == 0 and failed_count == 0
                    )
                    print(json.dumps({
                        "ok": ok,
                        "scope": "read-only Binance Spot OPO list/child/trade queries plus exact local BUY and linked stop SELL allocation recovery",
                        "account_identity_verified_twice": identity_verified_twice,
                        "unresolved_before": initial,
                        "opo_candidate_count": len(candidate_ids),
                        "recovered_entry_count": recovered_entry_count,
                        "recovered_exit_count": recovered_exit_count,
                        "recovered_strategy_exit_count": recovered_strategy_exit_count,
                        "verified_no_fill_count": verified_no_fill_count,
                        "recovered_trade_count": recovered_trade_count,
                        "unsupported_state_count": unsupported_count,
                        "failed_recovery_count": failed_count,
                        "unresolved_after": remaining,
                        "automatic_rearm": False,
                        "exchange_orders_placed": False,
                    }, indent=2))
                    return 0 if ok else 1
                if args.action == "recover-spot-market-fills":
                    unresolved_ids = before.get("unresolved_client_order_ids")
                    if not isinstance(unresolved_ids, list):
                        raise LiveTradingSafetyError("Spot order intent status is invalid.")
                    recovered_count = 0
                    recovered_sell_count = 0
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
                            or intent.get("side") not in {"BUY", "SELL"}
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
                            if intent.get("side") == "SELL":
                                fill["pre_order_portfolio_signature"] = intent.get("portfolio_pre_order_signature")
                                fill["pre_order_portfolio_qty"] = intent.get("portfolio_pre_order_qty")
                            from app.gui.shared.allocation_persistence import get_position_allocations_path

                            app_root = Path(__file__).resolve().parents[4]
                            allocation_path = get_position_allocations_path(
                                app_root / "gui" / "window_shell.py",
                            )
                            if intent.get("side") == "BUY":
                                persist_spot_buy_allocation(allocation_path, fill)
                            else:
                                persist_spot_sell_allocation(allocation_path, fill)
                            owner._mark_order_intent_portfolio_reconciled(
                                str(client_order_id),
                                portfolio_signature=str(fill["signature"]),
                                portfolio_quantity=str(fill["portfolio_qty"]),
                            )
                            recovered_count += 1
                            if intent.get("side") == "SELL":
                                recovered_sell_count += 1
                            recovered_trade_count += int(fill["trade_count"])
                        except SPOT_EXCHANGE_ERRORS:
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
                        "scope": "read-only Binance Spot queries plus local BUY/SELL allocation recovery",
                        "account_identity_verified_twice": identity_verified_twice,
                        "unresolved_before": initial,
                        "recovered_buy_fill_count": recovered_count - recovered_sell_count,
                        "recovered_sell_fill_count": recovered_sell_count,
                        "recovered_fill_count": recovered_count,
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
