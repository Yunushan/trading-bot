"""Backward-compatible import shim for strategy controls collection helpers."""

from .controls_collect_runtime import _collect_strategy_controls, _prepare_controls_snapshot

__all__ = ["_collect_strategy_controls", "_prepare_controls_snapshot"]
