from __future__ import annotations

from collections.abc import Mapping, Set


def merge_extra_order_fields(
    request: dict[str, object],
    extra_order_fields: Mapping[str, object] | None,
    *,
    protected_fields: Set[str],
    provider: str,
) -> None:
    if extra_order_fields is None:
        return
    if not isinstance(extra_order_fields, Mapping):
        raise ValueError(f"{provider} extra_order_fields must be a mapping")

    invalid_names = sorted(repr(key) for key in extra_order_fields if not isinstance(key, str) or not key.strip())
    if invalid_names:
        raise ValueError(f"{provider} extra_order_fields contains invalid field names: {', '.join(invalid_names)}")

    collisions = sorted(str(key) for key in extra_order_fields if key in protected_fields)
    if collisions:
        raise ValueError(f"{provider} extra_order_fields must not override validated fields: {', '.join(collisions)}")

    request.update(extra_order_fields)


__all__ = ["merge_extra_order_fields"]
