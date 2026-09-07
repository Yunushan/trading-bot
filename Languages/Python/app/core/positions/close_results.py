"""Select exact position keys whose close-all result proves they are flat."""

from collections.abc import Mapping


def confirmed_closed_position_keys(results: object) -> set[tuple[str, str]]:
    if isinstance(results, Mapping):
        results = [results]
    if not isinstance(results, (list, tuple)):
        return set()
    closed: set[tuple[str, str]] = set()
    unresolved: set[tuple[str, str]] = set()
    ambiguous_symbols: set[str] = set()
    for result in results:
        if not isinstance(result, Mapping):
            return set()
        symbol = str(result.get("symbol") or "").strip().upper()
        side = str(result.get("side_key") or "").strip().upper()
        if not symbol or symbol == "?":
            return set()
        if result.get("skipped", False) is not False:
            continue
        if side not in {"L", "S", "SPOT"}:
            ambiguous_symbols.add(symbol)
            continue
        key = (symbol, side)
        if result.get("ok") is True and result.get("position_closed") is True:
            closed.add(key)
        else:
            unresolved.add(key)
    return {key for key in closed - unresolved if key[0] not in ambiguous_symbols}
