"""Backward-compatible import shim for backtest worker helpers."""

from .worker_runtime import _BacktestWorker

__all__ = ["_BacktestWorker"]
