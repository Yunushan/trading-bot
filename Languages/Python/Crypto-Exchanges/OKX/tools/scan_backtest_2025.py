from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

try:
    import pandas as pd
except Exception as exc:  # pragma: no cover - runtime guard
    raise SystemExit(f"pandas is required to run this script: {exc}") from exc

from app.backtester import BacktestEngine, BacktestRequest, IndicatorDefinition
from app.binance_wrapper import BinanceWrapper, _coerce_interval_seconds


@dataclass
class StrategySpec:
    key: str
    label: str
    logic: str
    indicators: dict


DEFAULT_STRATEGIES = {
    "rsi_14_30_70": StrategySpec(
        key="rsi_14_30_70",
        label="RSI 14 (30/70)",
        logic="AND",
        indicators={
            "rsi": {"length": 14, "buy_value": 30, "sell_value": 70},
        },
    ),
    "stochrsi_14_20_80": StrategySpec(
        key="stochrsi_14_20_80",
        label="Stoch RSI 14 (20/80)",
        logic="AND",
        indicators={
            "stoch_rsi": {"length": 14, "smooth_k": 3, "smooth_d": 3, "buy_value": 20, "sell_value": 80},
        },
    ),
    "willr_14": StrategySpec(
        key="willr_14",
        label="Williams %R 14 (-80/-20)",
        logic="AND",
        indicators={
            "willr": {"length": 14, "buy_value": -80, "sell_value": -20},
        },
    ),
    "macd_hist_0": StrategySpec(
        key="macd_hist_0",
        label="MACD hist (0 cross)",
        logic="AND",
        indicators={
            "macd": {"fast": 12, "slow": 26, "signal": 9, "buy_value": 0.0, "sell_value": 0.0},
        },
    ),
    "supertrend_10_3": StrategySpec(
        key="supertrend_10_3",
        label="Supertrend 10/3 (0 cross)",
        logic="AND",
        indicators={
            "supertrend": {"atr_period": 10, "multiplier": 3.0, "buy_value": 0.0, "sell_value": 0.0},
        },
    ),
    "rsi_supertrend": StrategySpec(
        key="rsi_supertrend",
        label="RSI 14 (30/70) + Supertrend 10/3",
        logic="AND",
        indicators={
            "rsi": {"length": 14, "buy_value": 30, "sell_value": 70},
            "supertrend": {"atr_period": 10, "multiplier": 3.0, "buy_value": 0.0, "sell_value": 0.0},
        },
    ),
    "dmi_14": StrategySpec(
        key="dmi_14",
        label="DMI 14 (0 cross)",
        logic="AND",
        indicators={
            "dmi": {"length": 14, "buy_value": 0.0, "sell_value": 0.0},
        },
    ),
}


class SimpleLogger:
    def info(self, msg: str) -> None:
        print(msg, flush=True)

    def warn(self, msg: str) -> None:
        print(f"[warn] {msg}", flush=True)

    def error(self, msg: str) -> None:
        print(f"[error] {msg}", flush=True)


def _parse_dt(value: str) -> datetime:
    dt = pd.to_datetime(value).to_pydatetime()
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.astimezone(None).replace(tzinfo=None)
    return dt


def _build_indicator_defs(indicators: dict) -> list[IndicatorDefinition]:
    defs: list[IndicatorDefinition] = []
    for key, params in indicators.items():
        if not isinstance(params, dict):
            params = {}
        defs.append(IndicatorDefinition(key=key, params=dict(params)))
    return defs


def _max_warmup(indicator_defs: list[IndicatorDefinition]) -> int:
    engine = BacktestEngine(wrapper=None)  # type: ignore[arg-type]
    return max(engine._estimate_warmup(ind_def) for ind_def in indicator_defs) if indicator_defs else 50


def _fmt_pct(value: float) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except Exception:
        return float("nan")


def _score_summary(summary: dict) -> tuple:
    return (
        summary.get("avg_roi", float("-inf")),
        summary.get("coverage", 0.0),
        summary.get("median_roi", float("-inf")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan top USD-M futures symbols for best ROI with MDD limit.")
    parser.add_argument("--start", default="2025-01-01 00:00:00")
    parser.add_argument("--end", default="2025-12-31 23:59:59")
    parser.add_argument("--intervals", default="1h,4h")
    parser.add_argument("--top-n", type=int, default=200)
    parser.add_argument("--mdd-limit", type=float, default=10.0)
    parser.add_argument("--mdd-logic", default="entire_account", choices=["per_trade", "cumulative", "entire_account"])
    parser.add_argument("--min-coverage", type=float, default=0.6)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--position-pct", type=float, default=2.0)
    parser.add_argument("--leverage", type=int, default=5)
    parser.add_argument("--side", default="BOTH", choices=["BUY", "SELL", "BOTH"])
    parser.add_argument("--margin-mode", default="Isolated")
    parser.add_argument("--position-mode", default="Hedge")
    parser.add_argument("--assets-mode", default="Single-Asset")
    parser.add_argument("--account-mode", default="Classic Trading")
    parser.add_argument("--stop-loss-percent", type=float, default=8.0)
    parser.add_argument("--stop-loss-mode", default="percent", choices=["percent", "usdt", "both"])
    parser.add_argument("--stop-loss-usdt", type=float, default=0.0)
    parser.add_argument("--stop-loss-scope", default="per_trade", choices=["per_trade", "cumulative", "entire_account"])
    parser.add_argument("--strategies", default="all")
    parser.add_argument("--output", default="best_roi_mdd10_2025_top200.json")
    parser.add_argument("--max-symbols", type=int, default=0, help="Limit symbols for a quick sanity run.")
    args = parser.parse_args()

    start_dt = _parse_dt(args.start)
    end_dt = _parse_dt(args.end)
    if end_dt <= start_dt:
        raise SystemExit("end must be after start")

    intervals = [iv.strip() for iv in args.intervals.split(",") if iv.strip()]
    if not intervals:
        raise SystemExit("No intervals provided")

    if args.strategies.strip().lower() == "all":
        strategy_specs = list(DEFAULT_STRATEGIES.values())
    else:
        strategy_specs = []
        for key in [k.strip() for k in args.strategies.split(",") if k.strip()]:
            spec = DEFAULT_STRATEGIES.get(key)
            if not spec:
                raise SystemExit(f"Unknown strategy key: {key}")
            strategy_specs.append(spec)

    logger = SimpleLogger()
    wrapper = BinanceWrapper(
        api_key="",
        api_secret="",
        mode="Live",
        account_type="Futures",
        default_leverage=args.leverage,
        connector_backend="binance-sdk-derivatives-trading-usds-futures",
    )
    wrapper.logger = logger
    wrapper.indicator_source = "Binance futures"

    symbols = wrapper.fetch_symbols(sort_by_volume=True, top_n=args.top_n) or []
    if args.max_symbols and args.max_symbols > 0:
        symbols = symbols[: int(args.max_symbols)]
    if not symbols:
        raise SystemExit("No symbols returned from Binance")

    logger.info(f"Loaded {len(symbols)} symbols (top volume).")

    indicator_defs_map = {spec.key: _build_indicator_defs(spec.indicators) for spec in strategy_specs}
    max_warmup_by_interval = {}
    for interval in intervals:
        max_warmup = max(_max_warmup(ind_defs) for ind_defs in indicator_defs_map.values())
        max_warmup_by_interval[interval] = max_warmup

    engine = BacktestEngine(wrapper)
    indicator_cache: dict = {}
    summaries: list[dict] = []
    errors: list[dict] = []

    for interval in intervals:
        interval_seconds = _coerce_interval_seconds(interval)
        warmup_bars = max_warmup_by_interval[interval]
        warmup_seconds = warmup_bars * interval_seconds
        buffered_start = start_dt - timedelta(seconds=warmup_seconds * 2)
        logger.info(f"Interval {interval}: warmup bars={warmup_bars}, buffered start={buffered_start}")

        for symbol in symbols:
            try:
                df = wrapper.get_klines_range(symbol, interval, buffered_start, end_dt, limit=1500)
            except Exception as exc:
                errors.append({"symbol": symbol, "interval": interval, "error": str(exc)})
                continue
            if df is None or df.empty:
                errors.append({"symbol": symbol, "interval": interval, "error": "empty data"})
                continue

            for spec in strategy_specs:
                indicator_defs = indicator_defs_map[spec.key]
                if not indicator_defs:
                    continue
                try:
                    requested_leverage = max(1, int(args.leverage or 1))
                except Exception:
                    requested_leverage = 1
                try:
                    effective_leverage = int(wrapper.clamp_futures_leverage(symbol, requested_leverage))
                except Exception:
                    effective_leverage = requested_leverage

                request = BacktestRequest(
                    symbols=[symbol],
                    intervals=[interval],
                    indicators=indicator_defs,
                    logic=spec.logic,
                    symbol_source="Futures",
                    start=start_dt,
                    end=end_dt,
                    capital=float(args.capital),
                    side=args.side,
                    position_pct=float(args.position_pct),
                    position_pct_units="percent",
                    leverage=float(effective_leverage),
                    margin_mode=args.margin_mode,
                    position_mode=args.position_mode,
                    assets_mode=args.assets_mode,
                    account_mode=args.account_mode,
                    mdd_logic=args.mdd_logic,
                    stop_loss_enabled=bool(args.stop_loss_percent or args.stop_loss_usdt),
                    stop_loss_mode=args.stop_loss_mode,
                    stop_loss_usdt=float(args.stop_loss_usdt),
                    stop_loss_percent=float(args.stop_loss_percent),
                    stop_loss_scope=args.stop_loss_scope,
                )
                try:
                    run = engine._simulate(
                        symbol,
                        interval,
                        df,
                        indicator_defs,
                        request,
                        leverage_override=effective_leverage,
                        indicator_cache=indicator_cache,
                    )
                except Exception as exc:
                    errors.append({"symbol": symbol, "interval": interval, "strategy": spec.key, "error": str(exc)})
                    continue
                if run is None:
                    continue
                run.symbol = symbol
                run.interval = interval
                run.leverage = float(effective_leverage)
                summaries.append(
                    {
                        "strategy": spec.key,
                        "strategy_label": spec.label,
                        "interval": interval,
                        "symbol": symbol,
                        "roi_percent": _fmt_pct(run.roi_percent),
                        "max_drawdown_percent": _fmt_pct(run.max_drawdown_percent),
                        "trades": int(run.trades or 0),
                    }
                )

    if not summaries:
        raise SystemExit("No runs completed; check errors output.")

    summary_by_strategy_interval: dict[tuple[str, str], dict] = {}
    for entry in summaries:
        key = (entry["strategy"], entry["interval"])
        bucket = summary_by_strategy_interval.setdefault(
            key,
            {
                "strategy": entry["strategy"],
                "strategy_label": entry["strategy_label"],
                "interval": entry["interval"],
                "runs": 0,
                "eligible": 0,
                "avg_roi": float("-inf"),
                "median_roi": float("-inf"),
                "best_roi": float("-inf"),
                "worst_mdd": 0.0,
                "coverage": 0.0,
            },
        )
        bucket["runs"] += 1
        mdd_ok = entry["max_drawdown_percent"] <= args.mdd_limit
        if mdd_ok and entry.get("trades", 0) > 0:
            bucket.setdefault("_eligible_rois", []).append(entry["roi_percent"])
            bucket.setdefault("_eligible_mdds", []).append(entry["max_drawdown_percent"])
            bucket["eligible"] += 1

    for bucket in summary_by_strategy_interval.values():
        eligible_rois = bucket.pop("_eligible_rois", [])
        eligible_mdds = bucket.pop("_eligible_mdds", [])
        if eligible_rois:
            bucket["avg_roi"] = mean(eligible_rois)
            bucket["median_roi"] = median(eligible_rois)
            bucket["best_roi"] = max(eligible_rois)
            bucket["worst_mdd"] = max(eligible_mdds) if eligible_mdds else 0.0
        else:
            bucket["avg_roi"] = float("-inf")
            bucket["median_roi"] = float("-inf")
            bucket["best_roi"] = float("-inf")
            bucket["worst_mdd"] = 0.0
        bucket["coverage"] = (bucket["eligible"] / bucket["runs"]) if bucket["runs"] else 0.0

    summary_rows = list(summary_by_strategy_interval.values())
    candidates = [row for row in summary_rows if row["eligible"] > 0]
    if not candidates:
        raise SystemExit("No candidates met the MDD limit.")
    primary = [row for row in candidates if row["coverage"] >= args.min_coverage]
    best_row = max(primary or candidates, key=_score_summary)

    best_spec = DEFAULT_STRATEGIES[best_row["strategy"]]
    template = {
        "name": best_spec.key,
        "label": best_spec.label,
        "intervals": [best_row["interval"]],
        "logic": best_spec.logic,
        "position_pct": float(args.position_pct),
        "position_pct_units": "percent",
        "side": args.side,
        "stop_loss": {
            "enabled": bool(args.stop_loss_percent or args.stop_loss_usdt),
            "mode": args.stop_loss_mode,
            "percent": float(args.stop_loss_percent),
            "usdt": float(args.stop_loss_usdt),
            "scope": args.stop_loss_scope,
        },
        "start_date": start_dt.strftime("%d.%m.%Y %H:%M:%S"),
        "end_date": end_dt.strftime("%d.%m.%Y %H:%M:%S"),
        "indicators": {
            key: dict(params, **{"enabled": True}) for key, params in best_spec.indicators.items()
        },
        "margin_mode": args.margin_mode,
        "position_mode": args.position_mode,
        "assets_mode": args.assets_mode,
        "account_mode": args.account_mode,
        "leverage": int(args.leverage),
        "mdd_logic": args.mdd_logic,
        "symbol_selection": {
            "type": "top_volume",
            "count": int(args.top_n),
            "source": "Futures",
        },
    }

    output_path = Path(args.output).resolve()
    output_payload = {
        "backtest": {
            "symbols": symbols,
            "intervals": [best_row["interval"]],
            "start_date": template["start_date"],
            "end_date": template["end_date"],
            "capital": float(args.capital),
            "logic": best_spec.logic,
            "symbol_source": "Futures",
            "position_pct": float(args.position_pct),
            "position_pct_units": "percent",
            "side": args.side,
            "margin_mode": args.margin_mode,
            "position_mode": args.position_mode,
            "assets_mode": args.assets_mode,
            "account_mode": args.account_mode,
            "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
            "leverage": int(args.leverage),
            "mdd_logic": args.mdd_logic,
            "indicators": template["indicators"],
            "stop_loss": template["stop_loss"],
        },
        "template_meta": template,
        "scan_summary": {
            "selected": best_row,
            "mdd_limit": float(args.mdd_limit),
            "min_coverage": float(args.min_coverage),
            "symbols": len(symbols),
            "intervals": intervals,
            "strategies": [spec.key for spec in strategy_specs],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output_payload, fh, indent=2)

    summary_path = output_path.with_name(f"{output_path.stem}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "summaries": summary_rows,
                "errors": errors,
            },
            fh,
            indent=2,
        )

    logger.info(f"Best template: {best_spec.key} @ {best_row['interval']} avg ROI={best_row['avg_roi']:.2f}%")
    logger.info(f"Wrote template to {output_path}")
    logger.info(f"Wrote summary to {summary_path}")
    if errors:
        logger.warn(f"Completed with {len(errors)} errors; see summary for details.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
