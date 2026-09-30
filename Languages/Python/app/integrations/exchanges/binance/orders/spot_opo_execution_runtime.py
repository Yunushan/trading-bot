"""Guarded submission boundary for Binance Spot OPO entries."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError, is_live_trading_mode

from .order_audit_runtime import audit_order_method
from .spot_fill_recovery_runtime import spot_opo_allocation_baseline
from .spot_exchange_errors import SPOT_EXCHANGE_ERRORS
from .spot_opo_runtime import build_spot_opo_cancel_replace_request, build_spot_opo_request


def _new_opo_client_ids() -> tuple[str, str, str]:
    suffix = uuid4().hex
    return f"ol{suffix[:34]}", f"ow{suffix[:34]}", f"op{suffix[:34]}"


def place_spot_opo_entry(
    self,
    symbol: str,
    side: str,
    working_price: object,
    working_quantity: object,
    pending_stop_price: object,
    *,
    list_client_order_id: str | None = None,
    working_client_order_id: str | None = None,
    pending_client_order_id: str | None = None,
) -> dict[str, object]:
    """Submit one FOK LIMIT BUY with its exchange-resident OPO stop leg.

    This primitive does not update the desktop portfolio. A successful return
    therefore always reports whether exact exchange reconciliation succeeded
    and that the BUY allocation still needs the dedicated recovery workflow.
    """
    symbol_text = str(symbol or "").strip().upper()
    side_text = str(side or "").strip().upper()
    if getattr(self, "account_type", None) != "SPOT":
        return {"ok": False, "error": "account_type != SPOT"}
    if side_text != "BUY":
        return {"ok": False, "error": "Spot OPO entries support BUY only"}
    if not symbol_text or not symbol_text.isascii() or not symbol_text.isalnum():
        return {"ok": False, "error": "Spot OPO symbol is invalid"}

    transport = getattr(getattr(self, "client", None), "create_order_list_opo", None)
    begin_intent = getattr(self, "_begin_spot_opo_intent", None)
    mark_submitted = getattr(self, "_mark_spot_opo_submitted", None)
    mark_accepted = getattr(self, "_mark_spot_opo_accepted", None)
    mark_unknown = getattr(self, "_mark_spot_opo_unknown", None)
    reconcile = getattr(self, "reconcile_spot_opo_intent", None)
    owner_submission = getattr(self, "_spot_execution_submission", None)
    owner_required = is_live_trading_mode(getattr(self, "mode", None)) or bool(
        getattr(self, "_spot_owner_initial_live", False)
    )
    if not callable(transport):
        return {"ok": False, "error": "Binance Spot OPO submission transport is unavailable"}
    if not all(callable(operation) for operation in (begin_intent, mark_submitted, mark_accepted, mark_unknown, reconcile)):
        return {"ok": False, "error": "Durable Spot OPO intent and reconciliation are unavailable"}
    guard = getattr(self, "_guard_live_order_submit", None)
    if owner_required and (not callable(owner_submission) or not callable(guard)):
        return {"ok": False, "error": "Live Spot execution owner or submission guard is unavailable; OPO submission is blocked"}

    generated_ids = _new_opo_client_ids()
    list_id = list_client_order_id or generated_ids[0]
    working_id = working_client_order_id or generated_ids[1]
    pending_id = pending_client_order_id or generated_ids[2]
    intent_started = False
    exchange_response_received = False
    acknowledgement_validated = False
    request: dict[str, str] | None = None
    try:
        symbol_info = self.get_symbol_info_spot(symbol_text)
        request = build_spot_opo_request(
            symbol=symbol_text,
            symbol_info=symbol_info,
            working_price=working_price,
            working_quantity=working_quantity,
            pending_stop_price=pending_stop_price,
            list_client_order_id=list_id,
            working_client_order_id=working_id,
            pending_client_order_id=pending_id,
        )

        if callable(guard):
            guard(
                market="spot",
                params={
                    "symbol": symbol_text,
                    "side": "BUY",
                    "type": "LIMIT",
                    "timeInForce": "FOK",
                    "price": request["workingPrice"],
                    "quantity": request["workingQuantity"],
                    "newClientOrderId": request["workingClientOrderId"],
                    "newOrderRespType": "FULL",
                },
                source="place_spot_opo_entry",
            )

        begin_intent(request, source="place_spot_opo_entry")
        intent_started = True
        via = "primary"
        mark_submitted(request["listClientOrderId"], via=via)
        if owner_required:
            with owner_submission():
                response = transport(**request)
        else:
            response = transport(**request)
        exchange_response_received = True

        mark_accepted(request, via=via, result=response)
        acknowledgement_validated = True
        observation = reconcile(request["listClientOrderId"], force=True)
        protection_state = observation.get("protection_state") if isinstance(observation, Mapping) else None
        query_observed = (
            isinstance(observation, Mapping)
            and not observation.get("error")
            and observation.get("state") in {"accepted", "rejected"}
            and protection_state in {"active", "triggered", "cancelled", "none", "lost"}
        )
        active_child_observed = (
            query_observed
            and observation.get("state") == "accepted"
            and protection_state == "active"
        )
        return {
            "ok": active_child_observed,
            "accepted": True,
            "exchange_response_received": True,
            "order_list_client_id": request["listClientOrderId"],
            "protection_state": protection_state or "unverified",
            "exchange_reconciled": bool(query_observed),
            "active_child_observed": bool(active_child_observed),
            "entry_reconciled": False,
            "strategy_ready": False,
            "requires_portfolio_recovery": True,
            "info": response if isinstance(response, Mapping) else {},
            "error": None if active_child_observed else (
                "OPO was submitted but an active pending stop was not verified; do not retry. "
                "Reconcile this order-list client ID and recover its BUY allocation."
            ),
        }
    except SPOT_EXCHANGE_ERRORS as exc:
        if intent_started and request is not None:
            unknown_persisted = True
            try:
                mark_unknown(request["listClientOrderId"], error=exc)
            except SPOT_EXCHANGE_ERRORS:
                unknown_persisted = False
            return {
                "ok": False,
                "accepted": acknowledgement_validated,
                "exchange_response_received": exchange_response_received,
                "order_list_client_id": request["listClientOrderId"],
                "protection_state": "unverified",
                "exchange_reconciled": False,
                "active_child_observed": False,
                "entry_reconciled": False,
                "strategy_ready": False,
                "requires_portfolio_recovery": True,
                "error": (
                    (redact_text(exc) or "Spot OPO submission outcome is uncertain; do not retry.")
                    if unknown_persisted else
                    "Spot OPO submission outcome is uncertain; the durable intent remains blocking. Reconcile it before retrying."
                ),
            }
        return {"ok": False, "error": redact_text(exc) or "Spot OPO request was rejected before submission"}


def _new_opo_exit_client_id() -> str:
    return f"sx{uuid4().hex[:34]}"


def _live_allocation_path() -> Path:
    from app.gui.shared.allocation_persistence import get_position_allocations_path

    app_root = Path(__file__).resolve().parents[4]
    return get_position_allocations_path(app_root / "gui" / "window_shell.py")


def place_spot_opo_strategy_exit(
    self, list_client_order_id: str, *, new_order_client_id: str | None = None,
) -> dict[str, object]:
    """Replace one recovered OPO stop with its exact full-quantity MARKET SELL.

    This primitive deliberately does not update the desktop portfolio. It
    returns strategy_ready=False until the explicit recovery action verifies
    order trades and the matching OPO allocation.
    """
    list_id = str(list_client_order_id or "").strip()
    if getattr(self, "account_type", None) != "SPOT" or not is_live_trading_mode(getattr(self, "mode", None)):
        return {"ok": False, "error": "Linked Spot OPO exits are supported only for Live Spot accounts"}
    client = getattr(self, "client", None)
    cancel_replace = getattr(client, "cancel_replace_order", None)
    check_exit_id = getattr(self, "_check_spot_opo_strategy_exit_client_id", None)
    begin_exit = getattr(self, "_begin_spot_opo_strategy_exit", None)
    mark_response = getattr(self, "_mark_spot_opo_strategy_exit_response", None)
    mark_unknown = getattr(self, "_mark_spot_opo_strategy_exit_unknown", None)
    mark_order_observed = getattr(self, "_mark_spot_opo_strategy_exit_order_observed", None)
    reconcile = getattr(self, "reconcile_spot_opo_intent", None)
    get_intent = getattr(self, "_get_order_intent_record", None)
    owner_submission = getattr(self, "_spot_execution_submission", None)
    guard = getattr(self, "_guard_live_order_submit", None)
    if not list_id or not all(callable(operation) for operation in (
        cancel_replace, check_exit_id, begin_exit, mark_response, mark_unknown,
        mark_order_observed, reconcile, get_intent, owner_submission, guard,
    )):
        return {"ok": False, "error": "Live Spot linked exit boundary is unavailable"}

    intent_started = False
    response_received = False
    request: dict[str, object] | None = None
    begun: Mapping[str, object] | None = None
    request_id = new_order_client_id or _new_opo_exit_client_id()
    try:
        check_exit_id(list_id, new_order_client_id=request_id)
        initial = reconcile(list_id, force=True)
        intent = get_intent(list_id)
        if (
            not isinstance(initial, Mapping)
            or initial.get("error")
            or not isinstance(intent, Mapping)
            or intent.get("state") != "accepted"
            or intent.get("protection_state") != "active"
            or intent.get("entry_reconciled") is not True
        ):
            raise LiveTradingSafetyError("Linked Spot SELL requires an exactly active recovered OPO stop.")
        expected_quantity = intent.get("entry_portfolio_quantity")
        allocation_path = _live_allocation_path()
        baseline = spot_opo_allocation_baseline(
            allocation_path,
            symbol=str(intent.get("symbol") or ""),
            list_client_order_id=list_id,
            expected_quantity=expected_quantity,
        )
        request = build_spot_opo_cancel_replace_request(
            intent, new_order_client_id=request_id,
        )
        guard(
            market="spot",
            params={
                "symbol": request["symbol"],
                "side": "SELL",
                "type": "MARKET",
                "quantity": request["quantity"],
                "newClientOrderId": request["newClientOrderId"],
            },
            source="place_spot_opo_strategy_exit",
        )
        begun = begin_exit(
            list_id,
            new_order_client_id=request_id,
            pre_order_portfolio_signature=baseline["signature"],
            pre_order_portfolio_quantity=baseline["quantity"],
            allocation_path=allocation_path,
            expected_record=intent,
        )
        intent_started = True
        request_value = begun.get("strategy_exit_request") if isinstance(begun, Mapping) else None
        if not isinstance(request_value, Mapping):
            raise LiveTradingSafetyError("Durable linked SELL request was not returned by the intent ledger.")
        if dict(request_value) != request:
            raise LiveTradingSafetyError("Persisted linked SELL request differs from the preflight request.")
        with owner_submission():
            response = cancel_replace(**request)
        response_received = True
        evidence = mark_response(list_id, response=response, expected_record=begun)
        exact_opo = reconcile(list_id, force=True)
        if not isinstance(exact_opo, Mapping) or exact_opo.get("error"):
            raise LiveTradingSafetyError("Linked SELL outcome needs exact OPO list and child reconciliation.")
        if evidence.get("outcome") == "cancel_failed":
            current = get_intent(list_id)
            no_effect = isinstance(current, Mapping) and current.get("strategy_exit_state") == "no_effect"
            return {
                "ok": bool(no_effect),
                "accepted": False,
                "exchange_response_received": True,
                "exchange_reconciled": bool(no_effect),
                "order_list_client_id": list_id,
                "strategy_exit_state": current.get("strategy_exit_state") if isinstance(current, Mapping) else "unknown",
                "protection_state": current.get("protection_state") if isinstance(current, Mapping) else "unverified",
                "strategy_ready": False,
                "requires_portfolio_recovery": not bool(no_effect),
                "requires_stop_rearm": False,
                "error": None if no_effect else "Cancel failure did not preserve a verified active stop; keep trading blocked.",
            }
        if evidence.get("outcome") == "stop_canceled_exit_rejected":
            return {
                "ok": False,
                "accepted": False,
                "exchange_response_received": True,
                "exchange_reconciled": exact_opo.get("protection_state") == "cancelled",
                "order_list_client_id": list_id,
                "strategy_exit_state": "stop_cancelled",
                "protection_state": exact_opo.get("protection_state"),
                "strategy_ready": False,
                "requires_portfolio_recovery": True,
                "requires_stop_rearm": True,
                "error": "Binance canceled the OPO stop but rejected the MARKET SELL; recovery and protection are required.",
            }
        current = get_intent(list_id)
        if (
            not isinstance(current, Mapping)
            or exact_opo.get("protection_state") != "cancelled"
            or current.get("strategy_exit_state") != "sell_accepted"
        ):
            raise LiveTradingSafetyError("Accepted linked SELL lacks exact canceled-stop reconciliation.")
        order = client.get_order(
            symbol=str(request["symbol"]),
            origClientOrderId=str(request["newClientOrderId"]),
        )
        order_evidence = mark_order_observed(list_id, order_response=order)
        return {
            "ok": bool(order_evidence.get("terminal") and order_evidence.get("status") == "FILLED"),
            "accepted": True,
            "exchange_response_received": True,
            "exchange_reconciled": True,
            "order_list_client_id": list_id,
            "replacement_client_order_id": request["newClientOrderId"],
            "replacement_order_status": order_evidence.get("status"),
            "replacement_executed_quantity": order_evidence.get("executed_quantity"),
            "protection_state": "cancelled",
            "strategy_ready": False,
            "requires_portfolio_recovery": True,
            "requires_stop_rearm": order_evidence.get("status") != "FILLED",
            "error": None if order_evidence.get("status") == "FILLED" else (
                "The linked SELL is not a verified full fill; keep trading blocked pending recovery."
            ),
        }
    except SPOT_EXCHANGE_ERRORS as exc:
        if intent_started:
            unknown_persisted = True
            try:
                current = get_intent(list_id)
                if (
                    isinstance(current, Mapping)
                    and current.get("strategy_exit_state") in {"submitted", "unknown"}
                    and current.get("strategy_exit_outcome") is None
                ):
                    mark_unknown(list_id, error=exc, expected_record=begun)
            except SPOT_EXCHANGE_ERRORS:
                unknown_persisted = False
            return {
                "ok": False,
                "accepted": False,
                "exchange_response_received": response_received,
                "exchange_reconciled": False,
                "order_list_client_id": list_id,
                "replacement_client_order_id": request.get("newClientOrderId") if request else new_order_client_id,
                "strategy_ready": False,
                "requires_portfolio_recovery": True,
                "error": (
                    (redact_text(exc) or "Linked Spot SELL outcome is uncertain; do not retry.")
                    if unknown_persisted else
                    "Linked Spot SELL outcome is uncertain; its durable intent remains blocking. Reconcile it before retrying."
                ),
            }
        return {"ok": False, "error": redact_text(exc) or "Linked Spot SELL was rejected before submission"}


def bind_binance_spot_opo_execution_runtime(wrapper_cls) -> None:
    wrapper_cls.place_spot_opo_entry = audit_order_method(place_spot_opo_entry, market="spot")
    wrapper_cls.place_spot_opo_strategy_exit = audit_order_method(place_spot_opo_strategy_exit, market="spot")
