"""
Backward-compatible import shim for position guard helpers.

New code should import from ``app.core.positions``.
"""

from app.core.positions import IntervalPositionGuard

__all__ = ["IntervalPositionGuard"]
