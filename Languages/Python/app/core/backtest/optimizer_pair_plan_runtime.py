from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from .models import PairOverride
from .optimizer_limits_runtime import MAX_BACKTEST_EXPECTED_RUN_TRACKING


@dataclass(frozen=True)
class OptimizerPairOverridePlan(Iterable[PairOverride]):
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    indicator_groups: tuple[tuple[str, ...], ...]

    def __bool__(self) -> bool:
        return bool(self.symbols and self.intervals and self.indicator_groups)

    def __len__(self) -> int:
        return len(self.symbols) * len(self.intervals) * len(self.indicator_groups)

    def __iter__(self) -> Iterator[PairOverride]:
        for symbol in self.symbols:
            for interval in self.intervals:
                for indicator_group in self.indicator_groups:
                    yield PairOverride(
                        symbol=symbol,
                        interval=interval,
                        indicators=list(indicator_group),
                    )


def _text_tuple(values: Sequence[object], *, uppercase: bool = False) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        text = str(raw or "").strip()
        if not text:
            continue
        if uppercase:
            text = text.upper()
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _group_tuple(values: Sequence[Sequence[object]]) -> tuple[tuple[str, ...], ...]:
    groups: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for group in values or ():
        normalized = tuple(_text_tuple(list(group)))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        groups.append(normalized)
    return tuple(groups)


def build_optimizer_pair_override_collection(
    *,
    symbols: Sequence[object],
    intervals: Sequence[object],
    indicator_groups: Sequence[Sequence[object]],
    lazy_threshold: int = MAX_BACKTEST_EXPECTED_RUN_TRACKING,
) -> list[PairOverride] | OptimizerPairOverridePlan:
    symbol_values = _text_tuple(symbols, uppercase=True)
    interval_values = _text_tuple(intervals)
    group_values = _group_tuple(indicator_groups)
    run_count = len(symbol_values) * len(interval_values) * len(group_values)
    if run_count > max(0, int(lazy_threshold or 0)):
        return OptimizerPairOverridePlan(
            symbols=symbol_values,
            intervals=interval_values,
            indicator_groups=group_values,
        )
    return list(
        OptimizerPairOverridePlan(
            symbols=symbol_values,
            intervals=interval_values,
            indicator_groups=group_values,
        )
    )


def pair_override_symbols(pair_overrides: object) -> list[str]:
    if isinstance(pair_overrides, OptimizerPairOverridePlan):
        return list(pair_overrides.symbols)
    return list(dict.fromkeys(item.symbol for item in (pair_overrides or [])))


def pair_override_intervals(pair_overrides: object) -> list[str]:
    if isinstance(pair_overrides, OptimizerPairOverridePlan):
        return list(pair_overrides.intervals)
    return list(dict.fromkeys(item.interval for item in (pair_overrides or [])))
