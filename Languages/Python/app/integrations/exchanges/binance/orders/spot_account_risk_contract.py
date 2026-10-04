"""INERT DRAFT: pure cash Binance Live Spot accounting, never permission authority.

All observations, proofs, operator references and time are caller inputs. This
module authenticates none of them. It provides neither persistence nor protection
against restoration, transport permission, reset authorization or live activation.
Unsupported fee/cost/period/market bases reject. No operator limits have defaults.
Exact Fraction arithmetic avoids silently rounding partial cost allocations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import re
from typing import Any, NoReturn, cast
from uuid import UUID


class ContractError(ValueError):
    """Caller must fence; no state transition or permission follows this error."""


def _fail(message: str) -> NoReturn:
    raise ContractError(message)


def _fields(value: object, names: set[str]) -> dict:
    if type(value) is not dict or set(value) != names:
        _fail("Missing, unknown or non-object contract fields")
    return value


def _int(value: object, *, minimum: int = 1) -> int:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        _fail("Invalid exact integer")
    return value


def _text(value: object, *, limit: int = 128) -> str:
    if (type(value) is not str or not 0 < len(value) <= limit or value.strip() != value
            or any(not 32 <= ord(character) <= 126 for character in value)):
        _fail("Invalid contract reference")
    return value


def _decimal(value: object, *, signed: bool = False) -> Fraction:
    pattern = r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?"
    if signed:
        pattern = "-?" + pattern
    if type(value) is not str or len(value) > 64 or not re.fullmatch(pattern, value) or value == "-0":
        _fail("Amount must be a finite canonical decimal token")
    return Fraction(value)


def _uuid(value: object) -> str:
    value = _text(value, limit=36)
    try:
        if str(UUID(value)) != value:
            _fail("Noncanonical UUID")
    except ValueError as exc:
        raise ContractError("Invalid UUID") from exc
    return value


def _asset(value: object) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Z][A-Z0-9]{0,19}", value) or value == "USDT":
        _fail("Unsupported base asset")
    return value


def _time(value: object) -> int:
    value = _text(value, limit=20)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            _fail("Noncanonical UTC second")
    except ValueError as exc:
        raise ContractError("Invalid UTC second") from exc
    stamp = int(parsed.timestamp())
    if stamp < 0:
        _fail("Unsupported pre-epoch UTC time")
    return stamp


def _json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError("Invalid immutable JSON value") from exc


def decode_contract(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("Duplicate JSON key")
            result[key] = value
        return result
    if type(raw) is not bytes:
        _fail("Exact JSON bytes required")
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda value: _fail("Nonfinite JSON"),
                           parse_float=lambda value: _fail("Float JSON unsupported; canonical decimal strings required"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("Invalid JSON") from exc
    if type(value) is not dict:
        _fail("JSON object required")
    return cast(dict, value)


@dataclass(frozen=True)
class Identity:
    account_uid: int
    ledger_store_id: str


def parse_identity(raw: object) -> Identity:
    value = _fields(raw, {"version", "exchange", "market", "environment", "account_uid", "ledger_store_id"})
    if (_int(value["version"]) != 1
            or type(value["exchange"]) is not str or value["exchange"] != "binance"
            or type(value["market"]) is not str or value["market"] != "spot"
            or type(value["environment"]) is not str or value["environment"] != "live"):
        _fail("Only explicit cash Binance Live Spot identity is supported")
    return Identity(_int(value["account_uid"]), _uuid(value["ledger_store_id"]))


_BASES = {
    "quote_asset": "USDT",
    "exposure_basis": "long_asset_marks_plus_remaining_entry_max_mark_or_limit_with_fee_bound",
    "loss_basis": "cumulative_realized_plus_unrealized_inclusive_quote_fees",
    "cost_basis": "exact_weighted_average",
    "balance_basis": "total_base_external_base_locks_quote_net_external_locks",
    "fee_basis": "nonnegative_USDT_only_rate_bound_no_rebates",
    "time_basis": "caller_verified_UTC_seconds",
    "limit_semantics": "exposure_lte_loss_lt",
    "exit_semantics": "unencumbered_base_no_borrow",
    "reset_semantics": "clear_kill_only_preserve_all_accounting",
    "rollover_semantics": "fresh_reconciled_contiguous_explicit_UTC_interval_carry_all",
    "attempt_semantics": "entry_total_entry_window_all_order_handoff_window_keep_all",
}
_AMOUNTS = {"gross_limit_quote", "net_limit_quote", "asset_limit_quote", "loss_limit_quote", "max_quote_fee_rate"}
_INTS = {"position_limit", "entry_attempt_limit", "entry_rate_limit", "rate_window_seconds",
         "transport_rate_limit", "transport_rate_window_seconds", "balance_max_age_seconds",
         "mark_max_age_seconds", "max_clock_step_seconds", "future_skew_seconds"}


@dataclass(frozen=True)
class Policy:
    policy_id: str
    operator_authorizer_ref: str
    values: tuple[tuple[str, Fraction | int], ...]
    fingerprint: str

    def value(self, key: str) -> Fraction | int:
        return dict(self.values)[key]


def parse_policy(raw: object) -> Policy:
    value = _fields(raw, {"version", "policy_id", "operator_authorizer_ref"} | set(_BASES) | _AMOUNTS | _INTS)
    if _int(value["version"]) != 1 or any(type(value[key]) is not str or value[key] != token for key, token in _BASES.items()):
        _fail("Unsupported explicit operator basis/semantics")
    parsed: dict[str, Fraction | int] = {}
    for key in sorted(_AMOUNTS):
        amount = _decimal(value[key])
        if amount <= 0 and key != "max_quote_fee_rate":
            _fail("Risk limit must be positive")
        if key == "max_quote_fee_rate" and amount > 1:
            _fail("Unsupported fee envelope: no-borrow exits require quote fee rate at most one")
        parsed[key] = amount
    for key in sorted(_INTS):
        parsed[key] = _int(value[key], minimum=0 if key == "future_skew_seconds" else 1)
    if parsed["entry_rate_limit"] > parsed["entry_attempt_limit"]:
        _fail("Window entry limit cannot exceed total entry limit")
    return Policy(_uuid(value["policy_id"]), _text(value["operator_authorizer_ref"]),
                  tuple(sorted(parsed.items())), hashlib.sha256(_json(value).encode()).hexdigest())


@dataclass(frozen=True)
class Position:
    asset: str
    quantity: Fraction
    cost_quote: Fraction
    external_locked: Fraction


@dataclass(frozen=True)
class Reservation:
    request_id: str
    asset: str
    side: str
    quantity: Fraction
    remaining: Fraction
    limit_price: Fraction | None
    filled: Fraction = Fraction(0)
    status: str = "reserved"
    order_id: int | None = None
    trade_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Event:
    event_id: str
    expected_head: str
    at: int
    kind: str
    payload: str


def parse_event(raw: object) -> Event:
    value = _fields(raw, {"event_id", "expected_head", "at", "kind", "data"})
    head = value["expected_head"]
    if type(head) is not str or not re.fullmatch(r"[0-9a-f]{64}", head) or type(value["data"]) is not dict:
        _fail("Invalid immutable event/head")
    if type(value["kind"]) is not str or value["kind"] not in {"RESERVE_ENTRY", "RESERVE_EXIT", "TRANSPORT", "UNKNOWN", "FILL", "TERMINAL", "OBSERVE", "KILL", "RESET", "ROLLOVER"}:
        _fail("Unsupported event")
    return Event(_text(value["event_id"]), head, _time(value["at"]), value["kind"], _json(value["data"]))


@dataclass(frozen=True)
class State:
    identity: Identity
    policy: Policy
    positions: tuple[Position, ...]
    cash_quote: Fraction
    marks: tuple[tuple[str, Fraction], ...]
    realized_quote: Fraction
    balance_at: int | None
    balance_watermark: int
    mark_at: int | None
    at: int
    period: str
    period_start: int
    period_end: int
    period_labels: tuple[str, ...]
    opening_payload: str
    reservations: tuple[Reservation, ...] = ()
    trades: tuple[tuple[str, str], ...] = ()
    attempts: tuple[tuple[str, str, int], ...] = ()
    killed: tuple[str, str, str] | None = None
    history: tuple[Event, ...] = ()
    head: str = ""


def _digest(state: State) -> str:
    def encode(value):
        if isinstance(value, Fraction):
            return [value.numerator, value.denominator]
        raise TypeError("Unsupported state field")
    try:
        raw = asdict(state)
        raw.pop("head")
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=encode, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ContractError("Invalid immutable state serialization") from exc
    return hashlib.sha256(canonical.encode()).hexdigest()


def _seal(state: State) -> State:
    return replace(state, head=_digest(state))


def _positions(raw: object) -> tuple[Position, ...]:
    if type(raw) is not list:
        _fail("Complete positions required")
    result = []
    for row in raw:
        row = _fields(row, {"asset", "quantity", "cost_quote", "external_locked"})
        pos = Position(_asset(row["asset"]), _decimal(row["quantity"]), _decimal(row["cost_quote"]), _decimal(row["external_locked"]))
        if pos.external_locked > pos.quantity or (pos.quantity == 0) != (pos.cost_quote == 0):
            _fail("Invalid explicit position/cost/lock basis")
        result.append(pos)
    if len({pos.asset for pos in result}) != len(result):
        _fail("Duplicate asset")
    return tuple(sorted(result, key=lambda pos: pos.asset))


def _marks(raw: object, positions: tuple[Position, ...]) -> tuple[tuple[str, Fraction], ...]:
    if type(raw) is not dict or set(raw) != {pos.asset for pos in positions}:
        _fail("Complete mark set required")
    result = tuple(sorted((asset, _decimal(price)) for asset, price in raw.items()))
    if any(price <= 0 for _, price in result):
        _fail("Positive marks required")
    return result


def _observed_positions(raw: object) -> tuple[tuple[str, Fraction, Fraction], ...]:
    # Venue balances establish units/locks, never overwrite accumulated cost basis.
    if type(raw) is not list:
        _fail("Complete observed positions required")
    result = []
    for row in raw:
        row = _fields(row, {"asset", "quantity", "external_locked"})
        result.append((_asset(row["asset"]), _decimal(row["quantity"]), _decimal(row["external_locked"])))
    if len({row[0] for row in result}) != len(result) or any(locked > quantity for _, quantity, locked in result):
        _fail("Invalid complete observed positions")
    return tuple(sorted(result))


def opening_state(raw: object) -> State:
    value = _fields(raw, {"identity", "policy", "positions", "cash_quote", "marks", "realized_quote", "at", "period"})
    positions = _positions(value["positions"])
    at = _time(value["at"])
    period = _fields(value["period"], {"label", "starts_at", "ends_at"})
    label, start, end = _text(period["label"]), _time(period["starts_at"]), _time(period["ends_at"])
    if not start <= at < end:
        _fail("Opening time outside explicit half-open UTC interval")
    state = State(parse_identity(value["identity"]), parse_policy(value["policy"]), positions,
                  _decimal(value["cash_quote"]), _marks(value["marks"], positions),
                  _decimal(value["realized_quote"], signed=True), at, at, at, at, label, start, end, (label,), _json(value))
    # This supplied opening financial basis is NOT a first-use authorization.
    return _seal(_latch_breach(state, "opening", "supplied opening basis"))


def _metrics(state: State) -> dict[str, Any]:
    marks = dict(state.marks)
    assets = {pos.asset: pos.quantity * marks[pos.asset] for pos in state.positions}
    cash_bound = Fraction(0)
    for order in state.reservations:
        if order.side == "BUY" and order.status != "terminal":
            bound = order.remaining * cast(Fraction, order.limit_price) * (1 + state.policy.value("max_quote_fee_rate"))
            # Conservative at the supplied current mark; no future-price guarantee.
            assets[order.asset] += order.remaining * max(marks[order.asset], cast(Fraction, order.limit_price)) * (1 + state.policy.value("max_quote_fee_rate"))
            cash_bound += bound
    gross = sum(assets.values(), Fraction(0))
    unrealized = sum((pos.quantity * marks[pos.asset] - pos.cost_quote for pos in state.positions), Fraction(0))
    return {"gross": gross, "net": gross, "assets": assets, "positions": sum(value > 0 for value in assets.values()),
            "loss": max(Fraction(0), -(state.realized_quote + unrealized)), "cash_bound": cash_bound}


def _breaches(state: State) -> tuple[str, ...]:
    value = _metrics(state)
    return tuple(name for name, breached in (
        ("gross", value["gross"] > state.policy.value("gross_limit_quote")),
        ("net", value["net"] > state.policy.value("net_limit_quote")),
        ("asset", any(amount > state.policy.value("asset_limit_quote") for amount in value["assets"].values())),
        ("positions", value["positions"] > state.policy.value("position_limit")),
        ("loss", value["loss"] >= state.policy.value("loss_limit_quote")),
        ("cash", value["cash_bound"] > state.cash_quote),
    ) if breached)


def _latch_breach(state: State, event_id: str, reference: str) -> State:
    breaches = _breaches(state)
    return replace(state, killed=state.killed or (event_id, "limit:" + ",".join(breaches), reference)) if breaches else state


def _fresh(state: State, at: int, *, marks: bool) -> None:
    stamps = [(state.balance_at, "balance_max_age_seconds")]
    if marks:
        stamps.append((state.mark_at, "mark_max_age_seconds"))
    for stamp, key in stamps:
        if stamp is None or at - stamp > state.policy.value(key) or stamp > at + state.policy.value("future_skew_seconds"):
            _fail("Fresh complete observation required")


def _order(state: State, request_id: object) -> Reservation:
    request_id = _text(request_id, limit=36)
    for order in state.reservations:
        if order.request_id == request_id:
            return order
    _fail("Unknown request")


def _set_order(state: State, order: Reservation) -> State:
    return replace(state, reservations=tuple(order if row.request_id == order.request_id else row for row in state.reservations))


def _unique_order_id(state: State, order: Reservation, order_id: int) -> None:
    # Within this single USDT-quote scope, base identifies the venue symbol.
    if any(row.asset == order.asset and row.order_id == order_id and row.request_id != order.request_id
           for row in state.reservations):
        _fail("Historical venue order ID belongs to a different request")


def _reduce_event(state: State, event: Event) -> State:
    """Internal transition; public boundary also fully replays the original state."""
    if type(state) is not State or state.head != _digest(state) or type(event) is not Event:
        _fail("State/event integrity mismatch")
    _int(event.at, minimum=0)
    if type(event.payload) is not str:
        _fail("Invalid immutable event payload")
    data = decode_contract(event.payload.encode("utf-8"))
    try:
        at_token = datetime.fromtimestamp(event.at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError) as exc:
        raise ContractError("Invalid event time") from exc
    if parse_event({"event_id": event.event_id, "expected_head": event.expected_head, "at": at_token,
                    "kind": event.kind, "data": data}) != event:
        _fail("Noncanonical immutable event")
    for previous in state.history:
        if previous.event_id == event.event_id:
            if previous != event:
                _fail("Changed duplicate event ID")
            return state
    if event.expected_head != state.head:
        _fail("Stale CAS head")
    if event.at < state.at or event.at - state.at > state.policy.value("max_clock_step_seconds"):
        _fail("Clock regression/unsupported jump")
    original = state
    if event.kind in {"RESERVE_ENTRY", "RESERVE_EXIT"}:
        data = _fields(data, {"request_id", "asset", "quantity", "order_type", "limit_price"})
        request_id, asset, quantity = _text(data["request_id"], limit=36), _asset(data["asset"]), _decimal(data["quantity"])
        if quantity <= 0 or any(row.request_id == request_id for row in state.reservations):
            _fail("Invalid/reused request ID or quantity")
        pos = next((row for row in state.positions if row.asset == asset), None)
        if pos is None:
            _fail("Asset absent from complete opening/reconciled basis")
        buy = event.kind == "RESERVE_ENTRY"
        _fresh(state, event.at, marks=buy)
        if buy:
            if state.killed or not state.period_start <= event.at < state.period_end or data["order_type"] != "LIMIT_FOK":
                _fail("Killed/unsupported bounded entry; quantity MARKET has no hard price cap")
            price = _decimal(data["limit_price"])
            if price <= 0:
                _fail("Positive limit required")
        else:
            if data["order_type"] != "MARKET" or data["limit_price"] is not None:
                _fail("Only explicit base-reducing MARKET exit is supported")
            price = None
            reserved = sum((row.remaining for row in state.reservations if row.asset == asset and row.side == "SELL" and row.status != "terminal"), Fraction(0))
            if quantity > pos.quantity - pos.external_locked - reserved:
                _fail("Exit exceeds unencumbered base; no borrowing")
        order = Reservation(request_id, asset, "BUY" if buy else "SELL", quantity, quantity, price)
        state = replace(state, reservations=state.reservations + (order,))
        if buy and _breaches(state):
            _fail("Worst-case reservation exceeds explicit policy")
    elif event.kind in {"TRANSPORT", "UNKNOWN", "TERMINAL"}:
        names = {"request_id"}
        if event.kind == "UNKNOWN":
            names |= {"evidence_ref"}
        if event.kind == "TERMINAL":
            names |= {"status", "order_id", "executed_quantity", "trade_ids", "proof_basis", "evidence_ref"}
        data = _fields(data, names)
        order = _order(state, data["request_id"])
        if event.kind == "TRANSPORT":
            if order.status != "reserved":
                _fail("One handoff per request; ambiguous retry unsupported")
            _fresh(state, event.at, marks=order.side == "BUY")
            recent_transport = [row for row in state.attempts if event.at - row[2] < state.policy.value("transport_rate_window_seconds")]
            if len(recent_transport) >= state.policy.value("transport_rate_limit"):
                _fail("Common order transport rate safety denies handoff")
            if order.side == "BUY":
                attempts = [row for row in state.attempts if row[1] == "BUY"]
                recent = [row for row in attempts if event.at - row[2] < state.policy.value("rate_window_seconds")]
                if (state.killed or not state.period_start <= event.at < state.period_end or _breaches(state)
                        or len(attempts) >= state.policy.value("entry_attempt_limit") or len(recent) >= state.policy.value("entry_rate_limit")):
                    _fail("Entry handoff denied by kill/shared budgets")
            state = replace(state, attempts=state.attempts + ((order.request_id, order.side, event.at),),
                            balance_at=None, balance_watermark=max(state.balance_watermark, event.at))
            state = _set_order(state, replace(order, status="submitted"))
        elif event.kind == "UNKNOWN":
            if order.status not in {"submitted", "partial", "unknown"}:
                _fail("Unknown state requires actual recorded handoff")
            reference = _text(data["evidence_ref"])
            state = _set_order(state, replace(order, status="unknown"))
            state = replace(state, killed=state.killed or (event.event_id, "uncertain_execution", reference),
                            balance_at=None, balance_watermark=max(state.balance_watermark, event.at))
        else:
            if (order.status not in {"submitted", "partial", "unknown"} or type(data["status"]) is not str or data["status"] not in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
                    or data["proof_basis"] != "complete_request_bound_terminal_and_trades"):
                _fail("Unsupported exact terminal proof")
            order_id, executed = _int(data["order_id"]), _decimal(data["executed_quantity"])
            _unique_order_id(state, order, order_id)
            if type(data["trade_ids"]) is not list or any(type(value) is not int or value < 0 for value in data["trade_ids"]):
                _fail("Invalid terminal trade IDs")
            trades = tuple(data["trade_ids"])
            if trades != tuple(sorted(set(trades))) or trades != tuple(sorted(order.trade_ids)) or executed != order.filled or (order.order_id is not None and order_id != order.order_id):
                _fail("Terminal proof contradicts applied complete fills")
            if (data["status"] == "FILLED" and executed != order.quantity) or (data["status"] == "REJECTED" and executed != 0):
                _fail("Invalid terminal executed quantity")
            _text(data["evidence_ref"])
            state = _set_order(state, replace(order, remaining=Fraction(0), status="terminal", order_id=order_id))
            state = replace(state, balance_at=None, balance_watermark=max(state.balance_watermark, event.at))
    elif event.kind == "FILL":
        data = _fields(data, {"request_id", "order_id", "trade_id", "quantity", "price", "quote_quantity", "fee_quote", "proof_basis"})
        order = _order(state, data["request_id"])
        order_id, trade_id = _int(data["order_id"]), _int(data["trade_id"], minimum=0)
        _unique_order_id(state, order, order_id)
        key = f"{order.asset}:{order_id}:{trade_id}"
        proof = _json(data)
        prior = dict(state.trades).get(key)
        if prior is not None:
            if prior != proof:
                _fail("Changed duplicate venue fill")
        else:
            quantity, price, quote, fee = (_decimal(data[name]) for name in ("quantity", "price", "quote_quantity", "fee_quote"))
            if (order.status not in {"submitted", "partial", "unknown"} or data["proof_basis"] != "exact_trade_USDT_fee"
                    or quantity <= 0 or price <= 0 or quantity > order.remaining or quote != quantity * price
                    or fee > quote * state.policy.value("max_quote_fee_rate")
                    or order.order_id is not None and order.order_id != order_id):
                _fail("Unsupported/inconsistent exact fill proof")
            pos = next(row for row in state.positions if row.asset == order.asset)
            if order.side == "BUY":
                if price > cast(Fraction, order.limit_price) or quote + fee > state.cash_quote:
                    _fail("Fill exceeds enforced entry/cash bound")
                pos = replace(pos, quantity=pos.quantity + quantity, cost_quote=pos.cost_quote + quote + fee)
                state = replace(state, cash_quote=state.cash_quote - quote - fee)
            else:
                if quantity > pos.quantity - pos.external_locked or state.cash_quote + quote - fee < 0:
                    _fail("Exit consumes externally encumbered base")
                cost = pos.cost_quote * quantity / pos.quantity
                pos = replace(pos, quantity=pos.quantity - quantity, cost_quote=pos.cost_quote - cost)
                state = replace(state, cash_quote=state.cash_quote + quote - fee, realized_quote=state.realized_quote + quote - fee - cost)
            state = replace(state, positions=tuple(pos if row.asset == pos.asset else row for row in state.positions),
                            trades=state.trades + ((key, proof),), balance_at=None,
                            balance_watermark=max(state.balance_watermark, event.at))
            state = _set_order(state, replace(order, remaining=order.remaining - quantity, filled=order.filled + quantity,
                                               status="partial", order_id=order_id, trade_ids=order.trade_ids + (trade_id,)))
    elif event.kind == "OBSERVE":
        data = _fields(data, {"positions", "cash_quote", "marks", "balances_at", "marks_at", "external_open_request_ids"})
        positions = tuple((row.asset, row.quantity, row.external_locked) for row in state.positions)
        if _observed_positions(data["positions"]) != positions or _decimal(data["cash_quote"]) != state.cash_quote:
            _fail("External balance/lock change requires unsupported explicit reconciliation")
        active = sorted(row.request_id for row in state.reservations if row.status in {"submitted", "partial"} and row.remaining > 0)
        if type(data["external_open_request_ids"]) is not list or data["external_open_request_ids"] != active:
            _fail("Incomplete/untracked external open orders; unknown is not released")
        balances_at, marks_at = _time(data["balances_at"]), _time(data["marks_at"])
        if any(stamp > event.at + state.policy.value("future_skew_seconds") for stamp in (balances_at, marks_at)):
            _fail("Future observation")
        if (state.mark_at is not None and marks_at < state.mark_at) or balances_at < state.balance_watermark:
            _fail("Observation timestamp regression")
        state = replace(state, marks=_marks(data["marks"], state.positions), balance_at=balances_at,
                        balance_watermark=balances_at, mark_at=marks_at)
    elif event.kind == "KILL":
        data = _fields(data, {"reason", "evidence_ref"})
        reason, reference = _text(data["reason"]), _text(data["evidence_ref"])
        state = replace(state, killed=state.killed or (event.event_id, reason, reference))
    elif event.kind == "RESET":
        data = _fields(data, {"kill_event_id", "operator_authorizer_ref", "evidence_ref"})
        _fresh(state, event.at, marks=True)
        if (not state.period_start <= event.at < state.period_end or state.killed is None or data["kill_event_id"] != state.killed[0]
                or data["operator_authorizer_ref"] != state.policy.operator_authorizer_ref or _breaches(state)
                or any(row.status != "terminal" for row in state.reservations)):
            _fail("Reset CAS/reconciliation contract not met")
        _text(data["evidence_ref"])
        # This checks an explicit reference, NOT genuine operator authorization.
        state = replace(state, killed=None)
    elif event.kind == "ROLLOVER":
        data = _fields(data, {"next_period", "starts_at", "ends_at", "evidence_ref"})
        period = _text(data["next_period"])
        start, end = _time(data["starts_at"]), _time(data["ends_at"])
        _fresh(state, event.at, marks=True)
        if (period in state.period_labels or start != state.period_end or not start <= event.at < end
                or any(row.status == "unknown" for row in state.reservations)):
            _fail("Period reuse/time/complete reconciliation mismatch")
        _text(data["evidence_ref"])
        state = replace(state, period=period, period_start=start, period_end=end, period_labels=state.period_labels + (period,))
    state = _latch_breach(state, event.event_id, "immutable event:" + event.event_id)
    return _seal(replace(state, at=event.at, history=original.history + (event,)))


def _same_contract_value(actual: object, expected: object) -> bool:
    """Replay supplies the schema: numeric equality must never erase its types."""
    if type(actual) is not type(expected):
        return False
    kind = type(expected)
    if kind in (State, Identity, Policy, Position, Reservation, Event):
        return all(_same_contract_value(getattr(actual, field.name), getattr(expected, field.name))
                   for field in fields(cast(State | Identity | Policy | Position | Reservation | Event, expected)))
    if kind is tuple:
        return len(cast(tuple, actual)) == len(cast(tuple, expected)) and all(
            _same_contract_value(left, right) for left, right in zip(cast(tuple, actual), cast(tuple, expected)))
    if kind in (str, int, Fraction, type(None)):
        return actual == expected
    _fail("Unsupported replay field type")


def _validate_state(state: State) -> State:
    """A caller-recomputed digest is not a financial validator or an authority."""
    if type(state) is not State or type(state.opening_payload) is not str or type(state.history) is not tuple:
        _fail("Invalid full immutable state")
    if type(state.head) is not str or not re.fullmatch(r"[0-9a-f]{64}", state.head) or state.head != _digest(state):
        _fail("State integrity mismatch")
    raw = decode_contract(state.opening_payload.encode("utf-8"))
    if _json(raw) != state.opening_payload:
        _fail("Noncanonical original opening basis")
    replayed = opening_state(raw)
    for event in state.history:
        replayed = _reduce_event(replayed, event)
    if not _same_contract_value(state, replayed):
        _fail("State does not equal complete opening and event replay")
    return replayed


def apply_event(state: State, event: Event) -> State:
    """Fully validate and reduce; return accounting, never permission authority."""
    validated = _validate_state(state)
    result = _reduce_event(validated, event)
    # Exact duplicate preserves the original fully validated immutable object.
    return state if result is validated else result


def metrics(state: State) -> dict[str, Any]:
    """Validate complete history before exposing accounting projections."""
    return _metrics(_validate_state(state))
