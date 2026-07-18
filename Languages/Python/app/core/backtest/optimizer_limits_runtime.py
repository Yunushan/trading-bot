from __future__ import annotations

# This is an admission ceiling for an explicitly confirmed research job. The UI
# must surface the conservative duration estimate before dispatch; it is not an
# interactive-workload target. Long-running research is handled with progress,
# cancellation, and result-table bounds rather than a misleading small cap.
MAX_BACKTEST_OPTIMIZER_RUNS = 100_000_000_000
BACKTEST_OPTIMIZER_LARGE_RUN_WARNING = 50_000
BACKTEST_OPTIMIZER_INTERACTIVE_RUN_WARNING = 5_000
MAX_BACKTEST_OPTIMIZER_TABLE_ROWS = 5_000
MAX_BACKTEST_EXPECTED_RUN_TRACKING = 50_000
BACKTEST_OPTIMIZER_PROGRESS_EVERY = 1_000
BACKTEST_OPTIMIZER_ESTIMATED_SECONDS_PER_RUN = 0.05
BACKTEST_OPTIMIZER_MIN_DURATION_SECONDS = 60
BACKTEST_OPTIMIZER_DEFAULT_DURATION_SECONDS = 4 * 60 * 60
BACKTEST_OPTIMIZER_MAX_DURATION_SECONDS = 7 * 24 * 60 * 60


def normalize_optimizer_duration_seconds(value: object) -> int:
    if not isinstance(value, (str, int, float)):
        seconds = BACKTEST_OPTIMIZER_DEFAULT_DURATION_SECONDS
    else:
        try:
            seconds = int(float(value))
        except (ValueError, OverflowError):
            seconds = BACKTEST_OPTIMIZER_DEFAULT_DURATION_SECONDS
    return max(
        BACKTEST_OPTIMIZER_MIN_DURATION_SECONDS,
        min(BACKTEST_OPTIMIZER_MAX_DURATION_SECONDS, seconds),
    )


def estimate_optimizer_duration_seconds(
    run_count: int,
    *,
    seconds_per_run: float = BACKTEST_OPTIMIZER_ESTIMATED_SECONDS_PER_RUN,
) -> float:
    return max(0.0, float(max(0, int(run_count or 0))) * max(0.001, float(seconds_per_run or 0.0)))


def format_optimizer_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds or 0.0))))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h {minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}h"


def format_optimizer_progress(
    processed_count: int,
    total_count: int,
    *,
    elapsed_seconds: float,
) -> str:
    processed = max(0, int(processed_count or 0))
    total = max(processed, int(total_count or 0))
    elapsed = max(0.0, float(elapsed_seconds or 0.0))
    if processed <= 0 or elapsed <= 0.0:
        eta = "estimating"
    else:
        rate = processed / elapsed
        remaining = max(0, total - processed)
        eta = format_optimizer_duration(remaining / max(rate, 0.001))
    return f"Optimized {processed:,}/{total:,} candidate run(s); elapsed {format_optimizer_duration(elapsed)}, ETA {eta}..."
