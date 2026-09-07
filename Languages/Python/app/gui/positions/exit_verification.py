"""Read-only, account-bound checks before a close-on-exit request may finish."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from app.integrations.exchanges.binance.positions.close_all_runtime import _gather_positions


def validate_exit_stop_result(result: object, account_type: str) -> None:
    if not isinstance(result, Mapping) or result.get("ok") is not True or result.get("error"):
        raise ValueError("The stop operation did not complete successfully.")
    if result.get("engines_stopped") is not True:
        raise ValueError("Strategy engines have not all been confirmed stopped.")
    warnings = result.get("warnings", [])
    if not isinstance(warnings, (list, tuple)) or warnings:
        raise ValueError("The stop operation reported warnings; review them before exiting.")
    details = result.get("close_all_result")
    if not isinstance(details, (list, tuple)):
        raise ValueError("The close-all result is unavailable or malformed.")
    for detail in details:
        if (not isinstance(detail, Mapping) or detail.get("ok") is not True
                or detail.get("skipped", False) is not False
                or (detail.get("error") and detail.get("reconciled") is not True)):
            raise ValueError("At least one close was unsuccessful, skipped, or unverified.")
    if account_type.upper().startswith("FUT"):
        cancellation = result.get("cancel_open_orders_after_close")
        if not isinstance(cancellation, Mapping) or cancellation.get("ok") is not True:
            raise ValueError("Post-close order cancellation was not confirmed.")


def _spot_exposure_assets(snapshot: object) -> list[str]:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("balances"), (list, tuple)):
        raise ValueError("Spot balance snapshot is unavailable or malformed.")
    remaining = set()
    for row in snapshot["balances"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("asset"), str) or not row["asset"].strip():
            raise ValueError("Spot balance snapshot contains an invalid asset.")
        asset = row["asset"].strip().upper()
        for field in ("free", "locked"):
            try:
                if isinstance(row.get(field), bool):
                    raise ValueError("Boolean balance quantity")
                quantity = Decimal(str(row[field]))
            except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("Spot balance snapshot contains an invalid quantity.") from exc
            if not quantity.is_finite() or quantity < 0:
                raise ValueError("Spot balance snapshot contains a nonfinite or negative quantity.")
            # Close-all sells non-USDT holdings; locked amounts and dust remain exposure.
            if asset != "USDT" and quantity > 0:
                remaining.add(asset)
    return sorted(remaining)


def verify_flat_exit(wrapper, account_type: str) -> None:
    """Raise unless fresh exchange and durable intent state authorize automatic exit."""
    account_type = account_type.strip().upper()
    if account_type.startswith("FUT"):
        orders = wrapper.client.futures_get_open_orders()
        positions, available = _gather_positions(wrapper)
        if not available:
            raise ValueError("Futures position snapshot is unavailable or malformed.")
        remaining = sorted({row["symbol"] for row in positions})
    elif account_type == "SPOT":
        orders = wrapper.client.get_open_orders()
        remaining = _spot_exposure_assets(wrapper.client.get_account())
    else:
        raise ValueError("The account type cannot be verified for close-on-exit.")
    if not isinstance(orders, (list, tuple)):
        raise ValueError("Open-order snapshot is unavailable or malformed.")
    if orders:
        raise ValueError("Open orders remain on the account; automatic exit is withheld.")
    if remaining:
        raise ValueError("Exposure remains on the account: " + ", ".join(remaining))
    status = wrapper.get_order_intent_status()
    if (not isinstance(status, Mapping) or status.get("storage_ready") is not True
            or type(status.get("unresolved_count")) is not int or status["unresolved_count"] != 0):
        raise ValueError("Order intent state is unavailable or still requires reconciliation.")
