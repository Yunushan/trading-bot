"""
Service runtime coordinators and future headless runners.
"""

from .bot_runtime import BotRuntimeCoordinator
from .local_executor import LocalServiceExecutionAdapter

try:
    from .backtest_executor import ServiceBacktestExecutionAdapter
except Exception:  # pragma: no cover - optional in interpreters without numeric deps
    ServiceBacktestExecutionAdapter = None

__all__ = [
    "BotRuntimeCoordinator",
    "LocalServiceExecutionAdapter",
    "ServiceBacktestExecutionAdapter",
]
