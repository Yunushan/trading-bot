"""Keep desktop execution callbacks attached to their pre-submit account."""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any, cast

from app.settings.live_safety import LiveTradingSafetyError, is_live_trading_mode
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import make_namespace, require_namespace


@dataclass(frozen=True, repr=False)
class TradeCallbackOrigin:
    window: Any = field(repr=False)
    wrapper: Any = field(repr=False)
    session: Any = field(repr=False)
    owner: Any = field(repr=False)
    uid: int
    environment: str
    store_id: str
    mode: str
    generation: int
    owner_generation: int
    account_generation: int
    admission_receipt: object = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "<TradeCallbackOrigin>"

    def __deepcopy__(self, memo):
        # The token retains identity; locks and wrappers must never be copied.
        return self

    @contextmanager
    def admission_handoff(self, params):
        """Validate source under the brief mutex after caller acquires storage locks."""
        with self.session._mutex:
            if not _matches_original_context(self.window, self) or not _window_maps_match_snapshot(self.window, self.session):
                raise LiveTradingSafetyError("Desktop BUY origin changed during admission.")
            require_namespace(self.session._capture()[4], make_namespace(self.uid, self.store_id))
            if self.session.check_spot_buy_admission(self.admission_receipt, params) is not True:
                raise LiveTradingSafetyError("Desktop BUY source changed during admission.")
            yield


def owned_live_spot_wrapper(wrapper) -> bool:
    return (
        getattr(wrapper, "_enforce_spot_execution_owner", False) is True
        and is_live_trading_mode(getattr(wrapper, "mode", None))
        and str(getattr(wrapper, "account_type", "")).upper() == "SPOT"
    )


def _window_maps_match_snapshot(window: Any, session: Any) -> bool:
    """Compare the two actual window maps using the publisher's key/list form."""
    return session.matches_loaded_maps(getattr(window, "_entry_allocations", None),
                                       getattr(window, "_open_position_records", None)) is True


def capture_trade_callback_origin(window: Any, wrapper: Any, params: dict | None = None) -> TradeCallbackOrigin:
    session = getattr(window, "_allocation_snapshot_session", None)
    owner = getattr(wrapper, "_spot_execution_owner", None)
    if wrapper is None or not owned_live_spot_wrapper(wrapper) or session is None:
        raise LiveTradingSafetyError("Desktop Spot callback origin is unavailable.")
    if getattr(window, "shared_binance", None) is not wrapper or session.ready is not True:
        raise LiveTradingSafetyError("Desktop Spot account or allocation snapshot changed before submission.")
    mode = window.mode_combo.currentText()
    if mode != getattr(wrapper, "mode", None):
        raise LiveTradingSafetyError("Desktop Spot execution mode changed before submission.")
    bound_wrapper = cast(Any, wrapper)
    bound_session = cast(Any, session)
    initial = bound_session._capture()
    with bound_session._mutex:
        if not _window_maps_match_snapshot(window, session):
            raise LiveTradingSafetyError("Desktop window maps differ from their loaded allocation source.")
    account_generation = getattr(window, "_account_observation_generation", 0)
    if owner is None:
        owner = bound_wrapper._ensure_spot_execution_owner()
    if (bound_session._capture() != initial
            or getattr(window, "_account_observation_generation", 0) != account_generation
            or getattr(window, "shared_binance", None) is not wrapper
            or getattr(window, "_allocation_snapshot_session", None) is not session):
        raise LiveTradingSafetyError("Desktop Spot origin changed while acquiring execution ownership.")
    with bound_session._mutex:
        if not _window_maps_match_snapshot(window, session):
            raise LiveTradingSafetyError("Desktop window maps changed while acquiring execution ownership.")
    from app.integrations.exchanges.binance.orders.spot_execution_owner import SpotExecutionOwner
    if not isinstance(owner, SpotExecutionOwner):
        raise LiveTradingSafetyError("Desktop Spot callback requires actual held execution ownership.")
    bound_owner = cast(Any, owner)
    uid = bound_wrapper._resolve_spot_account_uid()
    owner.assert_held(uid=uid, environment=owner.environment,
                      credential_fingerprint=owner.credential_fingerprint, owner_wrapper=wrapper)
    from .allocation_persistence import initialize_spot_allocation_namespace, assert_loaded_allocation_checkpoint
    from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transactions
    initialize_spot_allocation_namespace(window, wrapper)
    path = bound_session._capture()[0]
    if path is None:
        raise LiveTradingSafetyError("Desktop allocation source is unavailable.")
    with ledger_transactions(owner.ledger_path, path), bound_session._mutex:
        capture = assert_loaded_allocation_checkpoint(bound_session, expected_namespace=make_namespace(uid, owner.store_id))
        if (getattr(window, "shared_binance", None) is not wrapper
                or getattr(window, "_allocation_snapshot_session", None) is not session
                or getattr(wrapper, "_spot_execution_owner", None) is not owner
                or getattr(window, "_account_observation_generation", 0) != account_generation
                or not _window_maps_match_snapshot(window, session)
                or capture[1] != mode or type(bound_owner.generation) is not int):
            raise LiveTradingSafetyError("Desktop allocation snapshot is not ready for submission.")
        receipt = bound_session.capture_spot_buy_admission(params) if params is not None else None
        return TradeCallbackOrigin(window, wrapper, session, bound_owner, uid, bound_owner.environment,
                                   bound_owner.store_id, mode, capture[-2], bound_owner.generation, account_generation, receipt)


def _matches_original_context(window: Any, origin: TradeCallbackOrigin) -> bool:
    """Pure identity check: no exchange calls, owner I/O, logging, or storage locks."""
    wrapper, session, owner = origin.wrapper, origin.session, origin.owner
    if wrapper is None or session is None or owner is None:
        return False
    verified = getattr(wrapper, "_verified_spot_account_context", None)
    return (
        origin.window is window and owned_live_spot_wrapper(wrapper)
        and not getattr(wrapper, "_spot_execution_revoked", False)
        and getattr(window, "_account_observation_generation", 0) == origin.account_generation
        and wrapper.mode == origin.mode
        and owner.uid == origin.uid and owner.environment == origin.environment and owner.store_id == origin.store_id
        and owner.generation == origin.owner_generation and owner.fd is not None
        and isinstance(verified, tuple) and len(verified) == 5
        and verified[:3] == (wrapper.api_key, wrapper.api_secret, origin.environment)
        and verified[3] is wrapper.client and verified[4] == origin.uid
        and session.ready is True and session._generation == origin.generation
        and getattr(window, "shared_binance", None) is wrapper
        and getattr(window, "_allocation_snapshot_session", None) is session
        and getattr(wrapper, "_spot_execution_owner", None) is owner
    )


def check_trade_callback_origin(window, origin, params: dict | None = None) -> bool:
    if not isinstance(origin, TradeCallbackOrigin):
        return False
    wrapper, session, owner = origin.wrapper, origin.session, origin.owner
    try:
        if (not _matches_original_context(window, origin) or window.mode_combo.currentText() != origin.mode
                or wrapper._resolve_spot_account_uid() != origin.uid):
            return False
        owner.assert_held(uid=origin.uid, environment=origin.environment,
                          credential_fingerprint=owner.credential_fingerprint, owner_wrapper=wrapper)
        from .allocation_persistence import assert_loaded_allocation_checkpoint
        from app.integrations.exchanges.binance.orders.order_intent_store import ledger_transactions
        path = session._capture()[0]
        if path is None:
            return False
        with ledger_transactions(owner.ledger_path, path), session._mutex:
            if not _matches_original_context(window, origin):
                return False
            captured = assert_loaded_allocation_checkpoint(session,
                expected_namespace=make_namespace(origin.uid, origin.store_id))
            if captured[-2] != origin.generation:
                return False
            return params is None or session.check_spot_buy_admission(origin.admission_receipt, params) is True
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return False
