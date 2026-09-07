"""Preserve unavailable exchange constraints instead of turning them off."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import math


def filter_number(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be a finite number >= 0")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number >= 0") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{name} must be a finite number >= 0")
    converted = float(number)
    if not math.isfinite(converted) or (converted == 0 and number != 0):
        raise ValueError(f"{name} is outside supported numeric range")
    return number


def validated_symbol_filters(filters: object) -> dict[str, Decimal]:
    if not isinstance(filters, Mapping):
        raise ValueError("symbol filters must be an object")
    values = {}
    for name in ("stepSize", "minQty", "minNotional", "maxQty"):
        if name not in filters:
            raise ValueError(f"symbol filters missing {name}")
        values[name] = filter_number(filters[name], name)
    values["tickSize"] = filter_number(filters["tickSize"], "tickSize") if "tickSize" in filters else Decimal(0)
    market_keys = ("marketMinQty", "marketMaxQty", "marketStepSize")
    if any(name in filters for name in market_keys):
        for name in market_keys:
            if name not in filters:
                raise ValueError(f"symbol filters missing {name}")
            values[name] = filter_number(filters[name], name)
    for minimum, maximum, _ in quantity_filter_fields(values, "MARKET"):
        if values[minimum] > values[maximum]:
            raise ValueError(f"symbol filters {minimum} exceeds {maximum}")
    return values


def quantity_filter_fields(filters: Mapping, order_type: str) -> tuple[tuple[str, str, str], ...]:
    fields = (("minQty", "maxQty", "stepSize"),)
    if str(order_type).strip().upper() == "MARKET" and "marketMaxQty" in filters:
        fields += (("marketMinQty", "marketMaxQty", "marketStepSize"),)
    return fields


def parse_symbol_filters(info: object, symbol: str, *, futures: bool) -> dict[str, float]:
    if not isinstance(info, Mapping) or info.get("symbol") != symbol.upper():
        raise ValueError("symbol metadata does not match the requested symbol")
    rows = info.get("filters")
    if not isinstance(rows, list) or not rows:
        raise ValueError("symbol metadata missing filters")
    by_type = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("filterType"), str) or not row["filterType"]:
            raise ValueError("symbol metadata contains an invalid filter")
        kind = row["filterType"]
        if kind in by_type:
            raise ValueError(f"symbol metadata contains duplicate {kind} filters")
        by_type[kind] = row
    lot = by_type.get("LOT_SIZE")
    if lot is None:
        raise ValueError("symbol metadata missing LOT_SIZE")
    values = {name: filter_number(lot.get(name), name) for name in ("stepSize", "minQty", "maxQty")}
    market_lot = by_type.get("MARKET_LOT_SIZE")
    if market_lot is not None:
        for name in ("minQty", "maxQty", "stepSize"):
            key = f"market{name[0].upper()}{name[1:]}"
            values[key] = filter_number(market_lot.get(name), key)
    # Absence of a notional rule in a valid rule set differs from a present
    # rule with missing fields. If both forms exist, enforce both minima.
    minima = [Decimal(0)]
    for kind in ("MIN_NOTIONAL", "NOTIONAL"):
        row = by_type.get(kind)
        if row is not None:
            name = "notional" if futures and "notional" in row else "minNotional"
            minima.append(filter_number(row.get(name), "minNotional"))
    values["minNotional"] = max(minima)
    price = by_type.get("PRICE_FILTER")
    if price is not None:
        values["tickSize"] = filter_number(price.get("tickSize"), "tickSize")
    elif futures:
        raise ValueError("symbol metadata missing PRICE_FILTER")
    return {name: float(number) for name, number in validated_symbol_filters(values).items()}
