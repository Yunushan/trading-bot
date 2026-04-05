from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .auth import AuthSettings
from .backtest import BacktestSettings
from .connectors import ConnectorSettings
from .execution import ExecutionSettings
from .indicators import build_runtime_indicator_defaults
from .risk import RiskManagementSettings
from .ui import UserInterfaceSettings


@dataclass(frozen=True, slots=True)
class AppSettings:
    auth: AuthSettings = field(default_factory=AuthSettings.from_env)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    connectors: ConnectorSettings = field(default_factory=ConnectorSettings)
    ui: UserInterfaceSettings = field(default_factory=UserInterfaceSettings)
    risk: RiskManagementSettings = field(default_factory=RiskManagementSettings)
    indicators: dict[str, dict[str, object]] = field(default_factory=build_runtime_indicator_defaults)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)

    def to_config_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        payload.update(self.auth.to_config_dict())
        payload.update(self.execution.to_config_dict())
        payload.update(self.connectors.to_config_dict())
        payload.update(self.ui.to_config_dict())
        payload.update(self.risk.to_config_dict())
        payload["indicators"] = copy.deepcopy(self.indicators)
        payload["backtest"] = self.backtest.to_config_dict()
        return payload


def build_default_settings() -> AppSettings:
    return AppSettings()


def build_default_config() -> dict[str, object]:
    return build_default_settings().to_config_dict()


def build_default_backtest_config() -> dict[str, object]:
    return BacktestSettings().to_config_dict()


DEFAULT_SETTINGS = build_default_settings()
DEFAULT_CONFIG = DEFAULT_SETTINGS.to_config_dict()
