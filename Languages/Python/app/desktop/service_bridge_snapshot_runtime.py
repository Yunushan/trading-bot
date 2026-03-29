from __future__ import annotations

import copy

from .service_bridge_client_runtime import _ensure_service_client

_MISSING = object()


def _sync_service_config_snapshot(self) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        client.replace_config(getattr(self, "config", None))
    except Exception:
        return


def _count_active_engines(self) -> int:
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
    except Exception:
        return 0
    count = 0
    for eng in engines.values():
        try:
            if hasattr(eng, "is_alive") and eng.is_alive():
                count += 1
        except Exception:
            continue
    return count


def _sync_service_runtime_snapshot(self, active=None, *, source: str = "desktop") -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        current_active = bool(getattr(self, "_bot_active", False)) if active is None else bool(active)
    except Exception:
        current_active = bool(active)
    try:
        active_engine_count = _count_active_engines(self)
    except Exception:
        active_engine_count = 0
    try:
        client.set_runtime_state(
            active=current_active,
            active_engine_count=active_engine_count,
            source=source,
        )
    except Exception:
        pass


def _sync_service_account_snapshot(
    self,
    total_balance=_MISSING,
    available_balance=_MISSING,
    *,
    source: str = "desktop-account",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    kwargs = {"source": source}
    if total_balance is not _MISSING:
        kwargs["total_balance"] = total_balance
    if available_balance is not _MISSING:
        kwargs["available_balance"] = available_balance
    try:
        set_account_snapshot = getattr(client, "set_account_snapshot", None)
        if callable(set_account_snapshot):
            set_account_snapshot(**kwargs)
    except Exception:
        pass


def _sync_service_portfolio_snapshot(
    self,
    *,
    active_pnl=_MISSING,
    active_margin=_MISSING,
    closed_pnl=_MISSING,
    closed_margin=_MISSING,
    source: str = "desktop-portfolio",
) -> None:
    client = _ensure_service_client(self)
    if client is None:
        return
    try:
        open_position_records = copy.deepcopy(getattr(self, "_open_position_records", {}) or {})
    except Exception:
        open_position_records = {}
    try:
        closed_position_records = copy.deepcopy(getattr(self, "_closed_position_records", []) or [])
    except Exception:
        closed_position_records = []
    try:
        closed_trade_registry = copy.deepcopy(getattr(self, "_closed_trade_registry", {}) or {})
    except Exception:
        closed_trade_registry = {}
    if (
        active_pnl is _MISSING
        or active_margin is _MISSING
        or closed_pnl is _MISSING
        or closed_margin is _MISSING
    ):
        try:
            totals = tuple(self._compute_global_pnl_totals())
        except Exception:
            totals = (None, None, None, None)
        if active_pnl is _MISSING:
            active_pnl = totals[0]
        if active_margin is _MISSING:
            active_margin = totals[1]
        if closed_pnl is _MISSING:
            closed_pnl = totals[2]
        if closed_margin is _MISSING:
            closed_margin = totals[3]
    try:
        balance_snapshot = getattr(self, "_positions_balance_snapshot", None)
    except Exception:
        balance_snapshot = None
    if not isinstance(balance_snapshot, dict):
        balance_snapshot = {}
    try:
        set_portfolio_snapshot = getattr(client, "set_portfolio_snapshot", None)
        if callable(set_portfolio_snapshot):
            set_portfolio_snapshot(
                open_position_records=open_position_records,
                closed_position_records=closed_position_records,
                closed_trade_registry=closed_trade_registry,
                active_pnl=None if active_pnl is _MISSING else active_pnl,
                active_margin=None if active_margin is _MISSING else active_margin,
                closed_pnl=None if closed_pnl is _MISSING else closed_pnl,
                closed_margin=None if closed_margin is _MISSING else closed_margin,
                total_balance=balance_snapshot.get("total"),
                available_balance=balance_snapshot.get("available"),
                source=source,
            )
    except Exception:
        pass


def _get_service_client_descriptor(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        describe = getattr(client, "describe", None)
        if callable(describe):
            result = describe()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_account_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_account_snapshot = getattr(client, "get_account_snapshot", None)
        if callable(get_account_snapshot):
            result = get_account_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_status_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_status_snapshot = getattr(client, "get_status_snapshot", None)
        if callable(get_status_snapshot):
            result = get_status_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_portfolio_snapshot(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_portfolio_snapshot = getattr(client, "get_portfolio_snapshot", None)
        if callable(get_portfolio_snapshot):
            result = get_portfolio_snapshot()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_config_summary(self) -> dict | None:
    client = _ensure_service_client(self)
    if client is None:
        return None
    try:
        get_config_summary = getattr(client, "get_config_summary", None)
        if callable(get_config_summary):
            result = get_config_summary()
            return result if isinstance(result, dict) else None
    except Exception:
        return None
    return None


def _get_service_recent_logs(self, *, limit: int = 100) -> list[dict]:
    client = _ensure_service_client(self)
    if client is None:
        return []
    try:
        get_recent_logs = getattr(client, "get_recent_logs", None)
        if callable(get_recent_logs):
            result = get_recent_logs(limit=limit)
            return list(result) if isinstance(result, (list, tuple)) else []
    except Exception:
        return []
    return []
