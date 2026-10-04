"""Genuine owned authority for protected inventory publication primitives.

The ordinary product callers must still validate the canonical fill/candidate.
This boundary does not make a caller-selected namespace or detached token into
execution authority. It performs no venue request or portfolio marker callback.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import threading

from app.settings.live_safety import LiveTradingSafetyError

from . import spot_inventory_checkpoint as checkpoints
from .order_intent_store import current_ledger_deadline, ledger_transactions
from .spot_inventory_namespace import ACCOUNT_NAMESPACE_KEY, is_strictly_empty_live_snapshot
from .spot_inventory_namespace_runtime import namespace_for_ledger, namespace_for_owner


_PROCESS_ID = os.getpid()


def _fail() -> LiveTradingSafetyError:
    return LiveTradingSafetyError("Protected Spot inventory requires its original owned publication authority.")


def _canonical_paths(wrapper, allocation_path: Path) -> Path:
    from app.gui.shared.allocation_persistence import get_position_allocations_path
    from .order_intent_runtime import _intent_path
    app_root = Path(__file__).resolve().parents[4]
    if _PROCESS_ID != os.getpid() or allocation_path != get_position_allocations_path(app_root / "gui" / "window_shell.py"):
        raise _fail()
    path = _intent_path(wrapper)
    if not isinstance(path, Path):
        raise _fail()
    return path


@contextmanager
def _owned_lifetime(wrapper, intent_path: Path) -> Iterator[None]:
    """Retain real owner exclusion without waiting in an inverted storage order."""
    from .spot_execution_owner import SpotExecutionOwner, assert_owner_administration_held
    if _PROCESS_ID != os.getpid():
        raise _fail()
    owner = getattr(wrapper, "_spot_execution_owner", None)
    if owner is None:
        assert_owner_administration_held(intent_path)
        yield
        assert_owner_administration_held(intent_path)
        return
    if not isinstance(owner, SpotExecutionOwner) or owner.pid != os.getpid():
        raise _fail()
    # Some canonical callers already hold storage locks. Waiting for a submitter
    # that needs those locks would invert the existing owner->storage order.
    lock = owner._submission_lock
    if not lock.acquire(blocking=False):
        raise LiveTradingSafetyError("Spot publication owner is busy; reconciliation is required.")
    try:
        if getattr(wrapper, "_spot_execution_owner", None) is not owner:
            raise _fail()
        namespace_for_owner(wrapper)
        yield
        if getattr(wrapper, "_spot_execution_owner", None) is not owner:
            raise _fail()
        namespace_for_owner(wrapper)
    finally:
        lock.release()


def _read_owned(wrapper, allocation_path: Path):
    from app.gui.shared.allocation_persistence import _decode, _read_receipt
    from .order_intent_runtime import _intent_binding, _read_ledger
    path = _canonical_paths(wrapper, allocation_path)
    current_ledger_deadline(path, allocation_path)
    ledger = _read_ledger(path, expected_binding=_intent_binding(wrapper))
    namespace = namespace_for_ledger(wrapper, ledger)
    if namespace is None:
        raise _fail()
    raw, _identity = _read_receipt(allocation_path)
    snapshot = _decode(raw, "Live") if raw is not None else None
    return path, ledger, namespace, raw, snapshot


@dataclass(frozen=True, repr=False)
class _AuthorityPin:
    owner: object
    administration: object
    generation: int
    binding: dict = field(repr=False)
    context: tuple = field(repr=False)
    client: object = field(repr=False)


def _pin_authority(wrapper, path: Path, namespace: Mapping) -> _AuthorityPin:
    from .order_intent_runtime import _intent_binding
    from .spot_execution_owner import _ADMINISTRATION, _read_marker, owner_marker_path
    owner = getattr(wrapper, "_spot_execution_owner", None)
    administration = _ADMINISTRATION.get() if owner is None else None
    context = getattr(wrapper, "_verified_spot_account_context", None)
    if not isinstance(context, tuple) or len(context) != 5 or context[3] is not getattr(wrapper, "client", None):
        raise _fail()
    generation = (getattr(owner, "generation", None) if owner is not None else
                  _read_marker(owner_marker_path(path), uid=namespace["account_uid"], environment="live",
                               store_id=str(namespace["store_id"]))["generation"])
    if type(generation) is not int or owner is None and administration is None:
        raise _fail()
    return _AuthorityPin(owner, administration, generation, deepcopy(_intent_binding(wrapper)), context,
                         getattr(wrapper, "client", None))


def _assert_pin(wrapper, path: Path, namespace: Mapping, pin: _AuthorityPin) -> None:
    from .order_intent_runtime import _intent_binding
    from .spot_execution_owner import (
        _ADMINISTRATION, _read_marker, owner_marker_path, assert_owner_administration_held, SpotExecutionOwner,
    )
    context = getattr(wrapper, "_verified_spot_account_context", None)
    if (getattr(wrapper, "_spot_execution_owner", None) is not pin.owner
            or getattr(wrapper, "client", None) is not pin.client or not isinstance(context, tuple)
            or len(context) != 5 or context[:3] != pin.context[:3]
            or context[3] is not pin.context[3] or context[4] != pin.context[4]
            or _intent_binding(wrapper) != pin.binding):
        raise _fail()
    if pin.owner is not None:
        if not isinstance(pin.owner, SpotExecutionOwner) or pin.owner.generation != pin.generation:
            raise _fail()
        pin.owner.assert_held(uid=namespace["account_uid"], environment=pin.binding["environment"],
                              credential_fingerprint=pin.binding["credential_fingerprint"], owner_wrapper=wrapper)
    elif (_ADMINISTRATION.get() is not pin.administration
          or _read_marker(owner_marker_path(path), uid=namespace["account_uid"], environment="live",
                          store_id=str(namespace["store_id"]))["generation"] != pin.generation):
        raise _fail()
    if pin.owner is None:
        assert_owner_administration_held(path)


def _assert_history(wrapper, path: Path, allocation_path: Path, namespace: Mapping,
                    pin: _AuthorityPin, record: Mapping | None = None) -> None:
    """Recheck the original complete history at each native publication phase."""
    from .order_intent_runtime import _intent_binding, _read_ledger
    _assert_pin(wrapper, path, namespace, pin)
    current_ledger_deadline(path, allocation_path)
    if _canonical_paths(wrapper, allocation_path) != path:
        raise _fail()
    ledger = _read_ledger(path, expected_binding=_intent_binding(wrapper))
    records = ledger.get("intents")
    if (namespace_for_ledger(wrapper, ledger) != namespace or not isinstance(records, dict)
            or (records != {} if record is None else records.get(record.get("client_order_id")) != record)):
        raise _fail()
    _assert_pin(wrapper, path, namespace, pin)


def _canonical_execution_fill(fill: Mapping, *, side: str) -> dict:
    """Validate the retained summary; raw order/trade summarizers remain the caller boundary."""
    from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
    from .spot_fill_recovery_runtime import _amount, _canonical_amount
    import re
    if "version" in fill and (type(fill["version"]) is not int or fill["version"] != 1):
        raise _fail()
    if side == "BUY":
        proof = canonical_spot_buy_metadata(fill)
    else:
        # The SELL summary conserves consumed base and net quote proceeds rather
        # than BUY acquisition cost. No raw trade rows are reconstructed here.
        base, quote = fill.get("base_asset"), fill.get("quote_asset")
        trades, commissions = fill.get("trade_ids"), fill.get("commissions")
        if (not isinstance(base, str) or not base.isascii() or not base.isalnum() or base != base.upper()
                or quote != "USDT" or base == quote or fill.get("side") != "SELL"
                or not isinstance(trades, list) or not trades
                or any(type(item) is not int or item <= 0 for item in trades)
                or len(set(trades)) != len(trades) or type(fill.get("trade_count")) is not int
                or fill["trade_count"] != len(trades) or not isinstance(commissions, list)):
            raise _fail()
        fees = {}
        for row in commissions:
            if not isinstance(row, Mapping) or set(row) != {"asset", "amount"}:
                raise _fail()
            asset = row["asset"]
            if asset not in {base, quote} or asset in fees:
                raise _fail()
            fees[asset] = _amount(row["amount"], "commission")
        gross = _amount(fill.get("gross_qty"), "gross quantity", positive=True)
        quantity = _amount(fill.get("net_qty"), "consumed quantity", positive=True)
        gross_quote = _amount(fill.get("gross_quote_qty"), "gross quote", positive=True)
        proceeds = _amount(fill.get("net_quote_proceeds"), "net quote proceeds", positive=True)
        if (quantity != gross + fees.get(base, 0) or proceeds != gross_quote - fees.get(quote, 0)
                or _amount(fill.get("portfolio_qty"), "portfolio quantity", positive=True) != quantity
                or _amount(fill.get("net_quote_cost"), "net quote cost") != 0
                or _amount(fill.get("average_price"), "average price", positive=True) != proceeds / quantity):
            raise _fail()
        proof = {"trade_ids": list(trades), "trade_count": len(trades), "gross_qty": _canonical_amount(gross),
                 "net_qty": _canonical_amount(quantity), "gross_quote_qty": _canonical_amount(gross_quote),
                 "net_quote_proceeds": _canonical_amount(proceeds), "base_asset": base, "quote_asset": quote,
                 "commissions": [{"asset": asset, "amount": _canonical_amount(amount)}
                                 for asset, amount in sorted(fees.items())],
                 "signature": fill.get("signature"), "order_id": fill.get("order_id"),
                 "exchange_client_order_id": fill.get("exchange_client_order_id", fill.get("client_order_id"))}
    client, symbol = fill.get("client_order_id"), fill.get("symbol")
    if (not isinstance(client, str) or not client or not isinstance(symbol, str)
            or symbol != str(proof["base_asset"]) + str(proof["quote_asset"])
            or type(proof["order_id"]) is not int or proof["order_id"] <= 0
            or not isinstance(proof["exchange_client_order_id"], str) or not proof["exchange_client_order_id"]
            or not isinstance(proof["signature"], str) or re.fullmatch(r"[0-9a-f]{64}", proof["signature"]) is None
            or type(fill.get("fill_time_ms")) is not int or fill["fill_time_ms"] <= 0
            or ("side" in fill and fill["side"] != side)):
        raise _fail()
    for name, expected in (("base_fee_qty", sum(_amount(row["amount"], "commission")
            for row in proof["commissions"] if row["asset"] == proof["base_asset"])),
            ("quote_fee_qty", sum(_amount(row["amount"], "commission")
            for row in proof["commissions"] if row["asset"] == proof["quote_asset"])),
            ("portfolio_qty", _amount(proof["net_qty"], "portfolio quantity", positive=True))):
        if name in fill and _amount(fill[name], name) != expected:
            raise _fail()
    proof.update(symbol=symbol, client_order_id=client, side=side)
    # Execution signatures already omit query/update clocks. Original retained
    # primary metadata is checked separately, including its original fill time.
    proof.pop("fill_time_ms", None)
    proof["trade_ids"] = sorted(proof["trade_ids"])
    proof["commissions"] = [{"asset": row["asset"], "amount": _canonical_amount(_amount(row["amount"], "commission"))}
                            for row in sorted(proof["commissions"], key=lambda row: row["asset"])]
    return proof


def _require_event_provenance(fill: Mapping, allowed: set[str]) -> None:
    for name in fill:
        if (not isinstance(name, str) or (name.startswith(("opo_", "entry_", "residual_stop_", "pre_order_"))
                and name not in allowed) or name == "pending_order_qty" and name not in allowed):
            raise _fail()


def _event_identity(record: Mapping, fill: Mapping) -> tuple[str, dict]:
    """Closed dispatch from the current full ledger record, never historical ID membership."""
    from .spot_allocation_generation_runtime import canonical_spot_buy_metadata
    from .spot_buy_admin_recovery_runtime import _validate_terminal_fill
    from .spot_fill_recovery_runtime import _amount, _canonical_amount
    from .spot_opo_runtime import (validate_spot_opo_request_payload, validate_spot_opo_cancel_replace_request,
                                  validate_spot_opo_strategy_exit_order, validate_spot_opo_residual_stop_request,
                                  validate_spot_opo_residual_stop_order)
    import re
    if record.get("market") != "spot" or not isinstance(record.get("client_order_id"), str):
        raise _fail()
    parent = record["client_order_id"]
    if record.get("type") == "MARKET":
        side = record.get("side")
        if side not in {"BUY", "SELL"} or record.get("state") not in {"accepted", "unknown"}:
            raise _fail()
        proof = _canonical_execution_fill(fill, side=side)
        if (proof["client_order_id"] != parent or proof["exchange_client_order_id"] != parent
                or proof["symbol"] != record.get("symbol")
                or str(proof["order_id"]) != str(record.get("exchange_order_id"))
                or record.get("exchange_status") not in {"FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED"}
                or _amount(record.get("executed_qty"), "record execution", positive=True) != _amount(proof["gross_qty"], "gross quantity")
                or ("type" in fill and fill["type"] != "MARKET")
                ):
            raise _fail()
        _require_event_provenance(fill, set() if side == "BUY" else
                                  {"pre_order_portfolio_signature", "pre_order_portfolio_qty"})
        if side == "SELL":
            signature = fill.get("pre_order_portfolio_signature")
            baseline = _amount(fill.get("pre_order_portfolio_qty"), "SELL baseline", positive=True)
            if (not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None
                    or signature != record.get("portfolio_pre_order_signature")
                    or baseline != _amount(record.get("portfolio_pre_order_qty"), "SELL baseline", positive=True)
                    or _amount(proof["net_qty"], "SELL consumption", positive=True) > baseline):
                raise _fail()
            proof.update(pre_order_portfolio_signature=signature, pre_order_portfolio_qty=_canonical_amount(baseline))
        if side == "BUY":
            metadata = canonical_spot_buy_metadata(fill)
            _validate_terminal_fill(record, {**fill, "portfolio_qty": fill.get("portfolio_qty", fill["net_qty"])}, metadata)
        proof["terminal_status"] = record["exchange_status"]
        return "market-" + side.lower(), proof
    request = validate_spot_opo_request_payload(record.get("request"))
    if (record.get("type") != "OPO" or record.get("side") != "BUY" or parent != request["listClientOrderId"]
            or record.get("symbol") != request["symbol"]
            or type(record.get("exchange_order_list_id")) is not int or record["exchange_order_list_id"] < 0):
        raise _fail()
    child = fill.get("exchange_client_order_id", fill.get("client_order_id"))
    side = "BUY" if child == request["workingClientOrderId"] else "SELL"
    proof = _canonical_execution_fill(fill, side=side)
    proof["order_list_id"] = record["exchange_order_list_id"]
    if side == "BUY":
        if (record.get("state") not in {"accepted", "unknown"}
                or record.get("protection_state") not in {"active", "triggered", "lost", "unverified"}
                or record.get("working_status") != "FILLED" or record.get("list_status") not in {"EXEC_STARTED", "ALL_DONE"}
                or proof["client_order_id"] != parent or proof["symbol"] != request["symbol"]
                or proof["order_id"] != record.get("working_order_id")
                or _amount(proof["gross_qty"], "working fill", positive=True) != _amount(request["workingQuantity"], "working quantity", positive=True)
                or _amount(record.get("working_executed_qty"), "working execution", positive=True) != _amount(proof["gross_qty"], "working fill")
                or _amount(fill.get("pending_order_qty"), "linked stop quantity", positive=True) != _amount(record.get("pending_original_qty"), "linked stop quantity", positive=True)
                or ("type" in fill and fill["type"] != "LIMIT")):
            raise _fail()
        _require_event_provenance(fill, {"pending_order_qty"})
        proof["terminal_status"] = "FILLED"
        return "opo-working-buy", proof
    if (fill.get("opo_list_client_order_id") != parent or proof["symbol"] != request["symbol"]
            or record.get("entry_reconciled") is not True):
        raise _fail()
    entry = _amount(record.get("entry_portfolio_quantity"), "entry quantity", positive=True)
    if child == request["pendingClientOrderId"]:
        _require_event_provenance(fill, {"opo_list_client_order_id", "opo_pending_client_order_id", "opo_order_list_id",
                                       "entry_recovery_signature", "entry_portfolio_quantity",
                                       "entry_working_client_order_id", "entry_working_order_id"})
        if (record.get("state") not in {"accepted", "unknown"} or record.get("protection_state") != "triggered"
                or record.get("list_status") != "ALL_DONE" or record.get("working_status") != "FILLED"
                or record.get("pending_status") != "FILLED" or fill.get("type") != "STOP_LOSS"
                or proof["client_order_id"] != parent or proof["order_id"] != record.get("pending_order_id")
                or fill.get("opo_pending_client_order_id") != child
                or type(fill.get("opo_order_list_id")) is not int
                or fill.get("opo_order_list_id") != record["exchange_order_list_id"]
                or fill.get("entry_working_client_order_id") != request["workingClientOrderId"]
                or type(fill.get("entry_working_order_id")) is not int or fill["entry_working_order_id"] <= 0
                or fill.get("entry_working_order_id") != record.get("working_order_id")
                or not isinstance(fill.get("entry_recovery_signature"), str)
                or re.fullmatch(r"[0-9a-f]{64}", fill["entry_recovery_signature"]) is None
                or fill.get("entry_recovery_signature") != record.get("entry_recovery_signature")
                or _amount(fill.get("entry_portfolio_quantity"), "entry quantity", positive=True) != entry
                or _amount(record.get("pending_original_qty"), "original stop quantity", positive=True) != entry
                or _amount(record.get("pending_executed_qty"), "stop execution", positive=True) != entry
                or _amount(proof["gross_qty"], "stop execution", positive=True) != entry
                or _amount(proof["net_qty"], "stop consumption", positive=True) != entry):
            raise _fail()
        proof.update(terminal_status="FILLED", entry_recovery_signature=fill["entry_recovery_signature"],
                     entry_portfolio_quantity=fill["entry_portfolio_quantity"],
                     entry_working_client_order_id=fill["entry_working_client_order_id"],
                     entry_working_order_id=fill["entry_working_order_id"])
        return "opo-original-stop", proof
    if record.get("cancel_state") != "confirmed" or record.get("protection_state") != "cancelled":
        raise _fail()
    if child == record.get("strategy_exit_client_order_id"):
        _require_event_provenance(fill, {"opo_list_client_order_id", "opo_entry_portfolio_quantity",
                                       "pre_order_portfolio_signature", "pre_order_portfolio_qty"})
        exit_request = validate_spot_opo_cancel_replace_request(record.get("strategy_exit_request"))
        evidence = validate_spot_opo_strategy_exit_order({
            "symbol": record.get("symbol"), "clientOrderId": child, "side": "SELL", "type": "MARKET",
            "orderListId": -1, "orderId": record.get("strategy_exit_order_id"),
            "status": record.get("strategy_exit_status"), "origQty": exit_request["quantity"],
            "executedQty": record.get("strategy_exit_executed_qty"),
        }, exit_request)
        if (record.get("state") not in {"accepted", "unknown"} or record.get("strategy_exit_state") not in {"sell_accepted", "unknown"}
                or record.get("strategy_exit_new_order_accepted") is not True or record.get("strategy_exit_cancel_confirmed") is not True
                or exit_request["newClientOrderId"] != child or exit_request["symbol"] != request["symbol"]
                or exit_request["cancelOrderId"] != record.get("pending_order_id")
                or exit_request["cancelOrigClientOrderId"] != request["pendingClientOrderId"]
                or _amount(exit_request["quantity"], "strategy request quantity", positive=True) != entry
                or _amount(record.get("pending_original_qty"), "linked stop quantity", positive=True) != entry
                or not evidence["terminal"]
                or proof["client_order_id"] != child or proof["order_id"] != evidence["order_id"] or fill.get("type") != "MARKET"
                or _amount(proof["gross_qty"], "strategy execution", positive=True) != _amount(evidence["executed_quantity"], "strategy execution", positive=True)
                or fill.get("pre_order_portfolio_signature") != record.get("strategy_exit_pre_order_signature")
                or _amount(fill.get("pre_order_portfolio_qty"), "strategy baseline", positive=True) != entry
                or _amount(record.get("strategy_exit_pre_order_quantity"), "strategy baseline", positive=True) != entry
                or _amount(fill.get("opo_entry_portfolio_quantity"), "entry quantity", positive=True) != entry):
            raise _fail()
        proof.update(terminal_status=evidence["status"], pre_order_portfolio_signature=fill["pre_order_portfolio_signature"],
                     pre_order_portfolio_qty=fill["pre_order_portfolio_qty"], opo_entry_portfolio_quantity=fill["opo_entry_portfolio_quantity"])
        kind = "opo-strategy-sell"
    else:
        _require_event_provenance(fill, {"opo_list_client_order_id", "opo_entry_portfolio_quantity",
                                       "residual_stop_client_order_id", "residual_stop_pre_order_signature",
                                       "residual_stop_pre_order_quantity", "pre_order_portfolio_signature",
                                       "pre_order_portfolio_qty"})
        stop_request = validate_spot_opo_residual_stop_request(record.get("residual_stop_request"))
        evidence = validate_spot_opo_residual_stop_order({
            "symbol": record.get("symbol"), "clientOrderId": stop_request["newClientOrderId"],
            "side": "SELL", "type": "STOP_LOSS", "orderListId": -1, "orderId": record.get("residual_stop_order_id"),
            "status": record.get("residual_stop_status"), "origQty": stop_request["quantity"],
            "executedQty": record.get("residual_stop_executed_qty"), "stopPrice": stop_request["stopPrice"],
        }, stop_request)
        before = _amount(record.get("residual_stop_pre_order_quantity"), "residual baseline", positive=True)
        # The canonical residual producer adds this exact pair for the shared SELL
        # writer. It remains an alias of the original residual baseline, not new proof.
        if "pre_order_portfolio_signature" in fill or "pre_order_portfolio_qty" in fill:
            if ("pre_order_portfolio_signature" not in fill or "pre_order_portfolio_qty" not in fill
                    or fill["pre_order_portfolio_signature"] != fill.get("residual_stop_pre_order_signature")
                    or _amount(fill["pre_order_portfolio_qty"], "normalized residual baseline", positive=True) != before):
                raise _fail()
        if (record.get("state") != "accepted" or record.get("residual_stop_state") not in {"active", "triggered", "unknown"}
                or record.get("residual_stop_query_verified") is not True or not evidence["terminal"]
                or stop_request["symbol"] != record.get("symbol") or child != stop_request["newClientOrderId"]
                or _amount(stop_request["stopPrice"], "residual stop price", positive=True) != _amount(request["pendingStopPrice"], "linked stop price", positive=True)
                or proof["client_order_id"] != child or proof["order_id"] != evidence["order_id"] or fill.get("type") != "STOP_LOSS"
                or fill.get("residual_stop_client_order_id") != child
                or _amount(proof["gross_qty"], "residual execution", positive=True) != _amount(evidence["executed_quantity"], "residual execution", positive=True)
                or fill.get("residual_stop_pre_order_signature") != record.get("residual_stop_pre_order_signature")
                or _amount(fill.get("residual_stop_pre_order_quantity"), "residual baseline", positive=True) != before
                or _amount(stop_request["quantity"], "residual request quantity", positive=True) != before or before > entry
                or _amount(fill.get("opo_entry_portfolio_quantity"), "entry quantity", positive=True) != entry):
            raise _fail()
        proof.update(terminal_status=evidence["status"], residual_stop_pre_order_signature=fill["residual_stop_pre_order_signature"],
                     residual_stop_pre_order_quantity=fill["residual_stop_pre_order_quantity"], opo_entry_portfolio_quantity=fill["opo_entry_portfolio_quantity"])
        kind = "opo-residual-stop"
    signature = proof.get("pre_order_portfolio_signature", proof.get("residual_stop_pre_order_signature"))
    if not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None:
        raise _fail()
    return kind, proof


def _event_operation(namespace: Mapping, record: Mapping, fill: Mapping) -> str:
    from .spot_inventory_namespace import validate_namespace
    kind, proof = _event_identity(record, fill)
    value = {"version": 2, "namespace": validate_namespace(namespace), "logical_client_order_id": record["client_order_id"],
             "kind": kind, "execution": proof}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inventory_publication_operation_hash(namespace: Mapping, record: Mapping, fill: Mapping) -> str:
    """Compute the exact protected operation hash; this pure classifier grants no authority."""
    return checkpoints._operation(_event_operation(namespace, record, fill))


def _bootstrap_operation(namespace: Mapping) -> str:
    encoded = json.dumps({"version": 1, "kind": "empty-bootstrap", "namespace": dict(namespace)},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bootstrap_owned_inventory_checkpoint(wrapper, *, allocation_path: Path) -> bool:
    """Bind only actual fresh empty history; never adopt existing bound state."""
    path = _canonical_paths(wrapper, allocation_path)
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
        if namespace_for_owner(wrapper) != namespace:
            raise _fail()
        pin = _pin_authority(wrapper, path, namespace)
        if checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
            _assert_pin(wrapper, path, namespace, pin)
            return False
        if ledger.get("intents") != {} or not is_strictly_empty_live_snapshot(snapshot):
            raise LiveTradingSafetyError("Protected Spot inventory bootstrap requires complete empty history.")
        candidate = deepcopy(snapshot) if snapshot is not None else {
            "version": 1, "mode": "Live", "entry_allocations": {}, "open_position_records": {},
        }
        candidate[ACCOUNT_NAMESPACE_KEY] = namespace
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin)):
            checkpoints._bootstrap_inventory_checkpoint(
                allocation_path, raw, snapshot, candidate, namespace, _bootstrap_operation(namespace),
            )
        _assert_pin(wrapper, path, namespace, pin)
        _read_owned(wrapper, allocation_path)
        return True


def recover_owned_inventory_bootstrap(wrapper, *, allocation_path: Path) -> bool:
    """Explicitly finish the pinned first empty write; do not reconstruct or clear it."""
    path = _canonical_paths(wrapper, allocation_path)
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, _raw, _snapshot = _read_owned(wrapper, allocation_path)
        if namespace_for_owner(wrapper) != namespace or ledger.get("intents") != {}:
            raise _fail()
        pin = _pin_authority(wrapper, path, namespace)
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin)):
            result = checkpoints._recover_inventory_checkpoint(allocation_path, namespace, _bootstrap_operation(namespace))
        _assert_pin(wrapper, path, namespace, pin)
        _read_owned(wrapper, allocation_path)
        if type(result) is not bool:
            raise _fail()
        return bool(result)


@dataclass(repr=False)
class _Publication:
    wrapper: object = field(repr=False)
    allocation_path: Path
    intent_path: Path
    namespace: dict = field(repr=False)
    record: dict = field(repr=False)
    operation: str = field(repr=False)
    authority: _AuthorityPin = field(repr=False)
    pid: int
    thread: int
    active: bool = True
    written: bool = False


_ACTIVE: ContextVar[_Publication | None] = ContextVar("spot_protected_inventory_publication", default=None)


def _assert_publication(value: _Publication, allocation_path: Path) -> None:
    if (not value.active or value.pid != os.getpid() or value.thread != threading.get_ident()
            or _ACTIVE.get() is not value or value.allocation_path != allocation_path):
        raise _fail()
    _assert_pin(value.wrapper, value.intent_path, value.namespace, value.authority)
    path, ledger, namespace, _raw, _snapshot = _read_owned(value.wrapper, allocation_path)
    records = ledger.get("intents")
    if (path != value.intent_path or namespace != value.namespace or not isinstance(records, dict)
            or records.get(value.record.get("client_order_id")) != value.record):
        raise _fail()


@contextmanager
def owned_inventory_publication(wrapper, *, allocation_path: Path, expected_record: Mapping, fill: Mapping) -> Iterator[None]:
    """Keep exact original record authority under both locks, including prepared recovery."""
    path = _canonical_paths(wrapper, allocation_path)
    record, original_fill = deepcopy(dict(expected_record)), deepcopy(dict(fill))
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, _raw, _snapshot = _read_owned(wrapper, allocation_path)
        records = ledger.get("intents")
        if not isinstance(records, dict) or records.get(record.get("client_order_id")) != record or _ACTIVE.get() is not None:
            raise _fail()
        operation = _event_operation(namespace, record, original_fill)
        pin = _pin_authority(wrapper, path, namespace)
        with checkpoints._checkpoint_authority(lambda: _assert_history(wrapper, path, allocation_path, namespace, pin, record)):
            checkpoints._recover_inventory_checkpoint(allocation_path, namespace, operation)
            _assert_pin(wrapper, path, namespace, pin)
            _path, _ledger, _namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
            if not checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
                raise _fail()
            value = _Publication(wrapper, allocation_path, path, deepcopy(namespace), record, operation, pin, os.getpid(), threading.get_ident())
            token = _ACTIVE.set(value)
            try:
                _assert_publication(value, allocation_path)
                yield
                _assert_publication(value, allocation_path)
                _path, _ledger, _namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
                if not checkpoints.verify_inventory_checkpoint(allocation_path, raw, snapshot, expected_namespace=namespace):
                    raise _fail()
            finally:
                value.active = False
                _ACTIVE.reset(token)


def write_owned_inventory_checkpoint(allocation_path: Path, candidate: dict) -> None:
    """Advance one prevalidated candidate using the active real owned record."""
    value = _ACTIVE.get()
    if value is None:
        raise _fail()
    _assert_publication(value, allocation_path)
    if value.written:
        raise _fail()
    _path, _ledger, _namespace, raw, snapshot = _read_owned(value.wrapper, allocation_path)
    # A failed native/protected write can have committed; retry needs a new
    # verified context and the protocol's exact prepared recovery.
    value.written = True
    checkpoints._publish_inventory_checkpoint(allocation_path, raw, snapshot, candidate, value.namespace, value.operation)


def publish_owned_inventory_candidate(wrapper, allocation_path: Path, candidate: dict, *,
                                      expected_record: Mapping, fill: Mapping) -> None:
    """Publish one already semantically validated candidate using actual original authority."""
    with owned_inventory_publication(wrapper, allocation_path=allocation_path, expected_record=expected_record, fill=fill):
        write_owned_inventory_checkpoint(allocation_path, candidate)


def assert_owned_inventory_publication(allocation_path: Path, *, fill: Mapping | None = None) -> None:
    """Require the actual original publication before a producer's replay shortcut."""
    value = _ACTIVE.get()
    if value is None:
        raise _fail()
    _assert_publication(value, allocation_path)
    if fill is not None and _event_operation(value.namespace, value.record, fill) != value.operation:
        raise _fail()


def inspect_owned_pending_inventory_operation(wrapper, allocation_path: Path) -> str | None:
    """Inspect a prepared operation without granting snapshot authority or publishing it."""
    from .order_intent_runtime import _intent_binding, _read_ledger
    from .spot_inventory_namespace import require_namespace
    path = _canonical_paths(wrapper, allocation_path)
    with _owned_lifetime(wrapper, path), ledger_transactions(path, allocation_path):
        _path, ledger, namespace, raw, snapshot = _read_owned(wrapper, allocation_path)
        original_ledger = deepcopy(dict(ledger))
        pin = _pin_authority(wrapper, path, namespace)
        def guard():
            _assert_pin(wrapper, path, namespace, pin)
            current_ledger_deadline(path, allocation_path)
            if _canonical_paths(wrapper, allocation_path) != path:
                raise _fail()
            current = _read_ledger(path, expected_binding=_intent_binding(wrapper))
            if dict(current) != original_ledger or namespace_for_ledger(wrapper, current) != namespace:
                raise _fail()
            _assert_pin(wrapper, path, namespace, pin)
        with checkpoints._checkpoint_authority(guard), checkpoints._errors():
            source, deadline = checkpoints._context(allocation_path)
            protected = checkpoints._get(source, deadline)
            if not protected:
                raise _fail()
            record = checkpoints._record(source, protected)
            if record["namespace"] != namespace:
                raise _fail()
            checkpoints._assert_source(source, deadline, raw)
            if record["state"] == "stable":
                if not checkpoints.verify_inventory_checkpoint(source, raw, snapshot, expected_namespace=namespace):
                    raise _fail()
                return None
            digest = checkpoints._hash(raw) if raw is not None else None
            if digest not in {record["previous"]["digest"], record["target"]["digest"]}:
                raise _fail()
            target = checkpoints._read(checkpoints._journal(source, record), deadline)
            if target is None or checkpoints._hash(target) != record["target"]["digest"]:
                raise _fail()
            require_namespace(checkpoints._snapshot(target, checkpoints._decode(target)), namespace)
            if checkpoints._get(source, deadline) != protected:
                raise _fail()
            checkpoints._assert_source(source, deadline, raw)
            return str(record["operation_hash"])


def recover_owned_inventory_publication(wrapper, allocation_path: Path, *, expected_record: Mapping, fill: Mapping) -> None:
    """Finish only the exact prepared current event; issue no additional candidate."""
    with owned_inventory_publication(wrapper, allocation_path=allocation_path, expected_record=expected_record, fill=fill):
        pass
