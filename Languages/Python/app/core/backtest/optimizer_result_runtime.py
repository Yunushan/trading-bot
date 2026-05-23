from __future__ import annotations

import heapq
from dataclasses import asdict, is_dataclass
from typing import Any

from .optimizer_limits_runtime import MAX_BACKTEST_OPTIMIZER_TABLE_ROWS

OPTIMIZER_METRIC_VALUES = {
    "roi_percent",
    "roi_percent_mdd",
    "roi_drawdown",
    "roi_value",
}


def _clean_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _coerce_number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def normalize_optimizer_metric(value: object) -> str:
    text = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    return text if text in OPTIMIZER_METRIC_VALUES else "roi_percent"


def run_to_mapping(run: object) -> dict[str, object]:
    if is_dataclass(run):
        return asdict(run)
    if isinstance(run, dict):
        return dict(run)
    return {
        "symbol": getattr(run, "symbol", ""),
        "interval": getattr(run, "interval", ""),
        "indicator_keys": getattr(run, "indicator_keys", []),
        "trades": getattr(run, "trades", 0),
        "roi_percent": getattr(run, "roi_percent", 0.0),
        "roi_value": getattr(run, "roi_value", 0.0),
        "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
        "mdd_logic": getattr(run, "mdd_logic", None),
    }


def optimizer_score(
    run: object,
    *,
    metric: str,
    mdd_limit: float,
    min_trades: int,
) -> tuple[float, ...] | None:
    data = run_to_mapping(run)
    trades = _coerce_int(data.get("trades", 0), 0)
    if trades < max(0, int(min_trades or 0)):
        return None
    mdd = _coerce_number(data.get("max_drawdown_percent", 0.0), 0.0)
    limit = _coerce_number(mdd_limit, 0.0)
    if limit > 0.0 and mdd > limit:
        return None
    roi_pct = _coerce_number(data.get("roi_percent", 0.0), 0.0)
    roi_val = _coerce_number(data.get("roi_value", 0.0), 0.0)
    metric_norm = normalize_optimizer_metric(metric)
    if metric_norm == "roi_value":
        return (roi_val, roi_pct, float(trades), -mdd)
    if metric_norm == "roi_drawdown":
        return (roi_pct / max(abs(mdd), 1.0), roi_pct, roi_val, float(trades), -mdd)
    return (roi_pct, roi_val, float(trades), -mdd)


def optimizer_rejection_reasons(
    run: object,
    *,
    mdd_limit: float,
    min_trades: int,
) -> list[str]:
    data = run_to_mapping(run)
    trades = _coerce_int(data.get("trades", 0), 0)
    mdd = _coerce_number(data.get("max_drawdown_percent", 0.0), 0.0)
    trade_floor = max(0, int(min_trades or 0))
    limit = _coerce_number(mdd_limit, 0.0)
    reasons: list[str] = []
    if trades < trade_floor:
        reasons.append(f"trades {trades} < {trade_floor}")
    if limit > 0.0 and mdd > limit:
        reasons.append(f"MDD {mdd:.2f}% > {limit:.2f}%")
    return reasons


def _assign_run_value(run: object, key: str, value: object) -> None:
    if isinstance(run, dict):
        run[key] = value
        return
    try:
        setattr(run, key, value)
    except Exception:
        pass


class OptimizerTopResultCollector:
    def __init__(
        self,
        *,
        limit: int,
        metric: str,
        mdd_limit: float,
        min_trades: int,
        mode: str,
        scope: str,
        run_count: int,
    ) -> None:
        self.limit = max(1, int(limit or MAX_BACKTEST_OPTIMIZER_TABLE_ROWS))
        self.metric = normalize_optimizer_metric(metric)
        self.mdd_limit = max(0.0, _coerce_number(mdd_limit, 0.0))
        self.min_trades = max(0, _coerce_int(min_trades, 0))
        self.mode = _clean_text(mode)
        self.scope = _clean_text(scope)
        self.run_count = max(0, _coerce_int(run_count, 0))
        self.candidate_count = 0
        self.eligible_count = 0
        self.filtered_count = 0
        self._eligible_heap: list[tuple[tuple[float, ...], int, int, object]] = []
        self._rejected_samples: list[tuple[int, object]] = []

    @classmethod
    def from_request(cls, request: object) -> "OptimizerTopResultCollector | None":
        limit = _coerce_int(getattr(request, "optimizer_result_limit", 0), 0)
        run_count = _coerce_int(getattr(request, "optimizer_run_count", 0), 0)
        if limit <= 0 or run_count <= limit:
            return None
        return cls(
            limit=limit,
            metric=getattr(request, "optimizer_metric", "roi_percent"),
            mdd_limit=getattr(request, "optimizer_mdd_limit", 0.0),
            min_trades=getattr(request, "optimizer_min_trades", 0),
            mode=getattr(request, "optimizer_mode", ""),
            scope=getattr(request, "optimizer_scope", ""),
            run_count=run_count,
        )

    def add(self, run: object) -> None:
        original_index = self.candidate_count
        self.candidate_count += 1
        score = optimizer_score(
            run,
            metric=self.metric,
            mdd_limit=self.mdd_limit,
            min_trades=self.min_trades,
        )
        if score is None:
            self.filtered_count += 1
            if len(self._rejected_samples) < self.limit:
                self._rejected_samples.append((original_index, run))
            return
        self.eligible_count += 1
        entry = (tuple(score), -original_index, original_index, run)
        if len(self._eligible_heap) < self.limit:
            heapq.heappush(self._eligible_heap, entry)
        elif entry[:2] > self._eligible_heap[0][:2]:
            heapq.heapreplace(self._eligible_heap, entry)

    def _annotate(
        self,
        run: object,
        *,
        rank: int | None,
        score: tuple[float, ...] | None,
        eligible: bool,
    ) -> None:
        _assign_run_value(run, "optimizer_rank", rank)
        _assign_run_value(run, "optimizer_metric", self.metric)
        _assign_run_value(run, "optimizer_primary_score", float(score[0]) if score else None)
        _assign_run_value(run, "optimizer_eligible", eligible)
        _assign_run_value(run, "optimizer_mode", self.mode)
        _assign_run_value(run, "optimizer_scope", self.scope)
        _assign_run_value(run, "optimizer_mdd_limit", self.mdd_limit)
        _assign_run_value(run, "optimizer_min_trades", self.min_trades)
        _assign_run_value(run, "optimizer_candidate_count", self.candidate_count)
        _assign_run_value(run, "optimizer_eligible_count", self.eligible_count)
        _assign_run_value(run, "optimizer_filtered_count", self.filtered_count)
        _assign_run_value(run, "optimizer_run_count", self.run_count or self.candidate_count)
        _assign_run_value(
            run,
            "optimizer_rejection_reason",
            ""
            if eligible
            else "; ".join(
                optimizer_rejection_reasons(
                    run,
                    mdd_limit=self.mdd_limit,
                    min_trades=self.min_trades,
                )
            ),
        )

    def finish(self) -> list[Any]:
        eligible_entries = sorted(
            self._eligible_heap,
            key=lambda entry: (entry[0], entry[1]),
            reverse=True,
        )
        if eligible_entries:
            results: list[Any] = []
            for rank, (score, _negative_index, _original_index, run) in enumerate(
                eligible_entries,
                start=1,
            ):
                self._annotate(run, rank=rank, score=score, eligible=True)
                results.append(run)
            return results

        results = []
        for _original_index, run in self._rejected_samples:
            self._annotate(run, rank=None, score=None, eligible=False)
            results.append(run)
        return results
