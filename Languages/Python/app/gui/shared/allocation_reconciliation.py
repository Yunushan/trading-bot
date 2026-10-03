"""Desktop publication fences; exact fill recovery owns recovered inventory."""
from __future__ import annotations

from .allocation_persistence import is_recovery_owned_allocation


def has_recovery_owned_allocations(window, key: tuple[str, str]) -> bool:
    entries = getattr(window, "_entry_allocations", {}).get(key, [])
    if isinstance(entries, dict):
        entries = list(entries.values())
    return isinstance(entries, list) and any(is_recovery_owned_allocation(row) for row in entries)


def defer_recovery_owned_cleanup(window, key: tuple[str, str], *, source: str) -> bool:
    if not has_recovery_owned_allocations(window, key):
        return False
    pending = getattr(window, "_pending_allocation_reconciliations", None)
    if not isinstance(pending, dict):
        pending = {}
        window._pending_allocation_reconciliations = pending
    event = {"operation": "recovery_owned_cleanup", "source": source}
    events = pending.setdefault(key, [])
    if isinstance(events, list) and event not in events:
        events.append(event)
        logger = getattr(window, "log", None)
        if callable(logger):
            logger(f"{key[0]} {key[1]}: exact fill recovery is required before local inventory cleanup.")
    return True


def allocation_publication_pending(window) -> bool:
    if getattr(window, "_spot_buy_recovery_fence", False):
        return True
    if getattr(window, "_pending_allocation_reconciliations", None):
        return True
    if hasattr(window, "_allocation_snapshot_session"):
        session = window._allocation_snapshot_session
        return session is None or getattr(session, "ready", False) is not True
    return False
