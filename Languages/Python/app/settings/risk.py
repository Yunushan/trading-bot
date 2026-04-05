from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping


STOP_LOSS_MODE_ORDER = ["usdt", "percent", "both"]
STOP_LOSS_SCOPE_OPTIONS = ["per_trade", "cumulative", "entire_account"]


def _float_or_zero(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except Exception:
            return 0.0
    try:
        return float(str(value))
    except Exception:
        return 0.0


def coerce_bool(value, default: bool = False) -> bool:
    """
    Normalize loose user-provided values (bools/strings/ints) into a strict bool.

    We frequently persist settings as JSON, so this helper tolerates values like
    "false", "0", 0, None, etc. and falls back to the provided default.
    """
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return bool(default)
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        if text in {"none", "null"}:
            return bool(default)
        return bool(default)
    try:
        return bool(int(value))
    except Exception:
        return bool(value)


@dataclass(frozen=True, slots=True)
class StopLossSettings:
    enabled: bool = False
    mode: str = "usdt"
    usdt: float = 0.0
    percent: float = 0.0
    scope: str = "per_trade"

    def normalized(self) -> "StopLossSettings":
        mode = str(self.mode or "usdt").lower()
        if mode not in STOP_LOSS_MODE_ORDER:
            mode = STOP_LOSS_MODE_ORDER[0]
        scope = str(self.scope or "per_trade").lower()
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        try:
            usdt = max(0.0, float(self.usdt or 0.0))
        except Exception:
            usdt = 0.0
        try:
            percent = max(0.0, float(self.percent or 0.0))
        except Exception:
            percent = 0.0
        return replace(
            self,
            enabled=coerce_bool(self.enabled, False),
            mode=mode,
            usdt=usdt,
            percent=percent,
            scope=scope,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> "StopLossSettings":
        if not isinstance(value, Mapping):
            return cls().normalized()
        return cls(
            enabled=coerce_bool(value.get("enabled"), False),
            mode=str(value.get("mode") or "usdt"),
            usdt=_float_or_zero(value.get("usdt", 0.0)),
            percent=_float_or_zero(value.get("percent", 0.0)),
            scope=str(value.get("scope") or "per_trade"),
        ).normalized()

    def to_config_dict(self) -> dict[str, object]:
        normalized = self.normalized()
        return {
            "enabled": normalized.enabled,
            "mode": normalized.mode,
            "usdt": normalized.usdt,
            "percent": normalized.percent,
            "scope": normalized.scope,
        }


STOP_LOSS_DEFAULT = StopLossSettings().to_config_dict()


def normalize_stop_loss_dict(value) -> dict[str, object]:
    return StopLossSettings.from_mapping(value).to_config_dict()


@dataclass(frozen=True, slots=True)
class RiskManagementSettings:
    indicator_flip_cooldown_bars: int = 1
    indicator_flip_cooldown_seconds: float = 0.0
    indicator_use_live_values: bool = True
    indicator_min_position_hold_seconds: float = 0.0
    indicator_min_position_hold_bars: int = 1
    require_indicator_flip_signal: bool = True
    strict_indicator_flip_enforcement: bool = True
    indicator_reentry_cooldown_seconds: float = 0.0
    indicator_reentry_cooldown_bars: int = 1
    indicator_reentry_requires_signal_reset: bool = True
    auto_flip_on_close: bool = True
    allow_close_ignoring_hold: bool = False
    allow_multi_indicator_close: bool = False
    allow_indicator_close_without_signal: bool = False
    indicator_flip_confirmation_bars: int = 1
    close_on_exit: bool = False
    positions_missing_threshold: int = 2
    positions_missing_autoclose: bool = True
    positions_missing_grace_seconds: int = 30
    futures_flat_purge_miss_threshold: int = 2
    futures_flat_purge_grace_seconds: float = 12.0
    allow_opposite_positions: bool = True
    hedge_preserve_opposites: bool = False
    max_auto_bump_percent: float = 5.0
    auto_bump_percent_multiplier: float = 10.0
    stop_loss: StopLossSettings = field(default_factory=StopLossSettings)

    def to_config_dict(self) -> dict[str, object]:
        return {
            "indicator_flip_cooldown_bars": self.indicator_flip_cooldown_bars,
            "indicator_flip_cooldown_seconds": self.indicator_flip_cooldown_seconds,
            "indicator_use_live_values": self.indicator_use_live_values,
            "indicator_min_position_hold_seconds": self.indicator_min_position_hold_seconds,
            "indicator_min_position_hold_bars": self.indicator_min_position_hold_bars,
            "require_indicator_flip_signal": self.require_indicator_flip_signal,
            "strict_indicator_flip_enforcement": self.strict_indicator_flip_enforcement,
            "indicator_reentry_cooldown_seconds": self.indicator_reentry_cooldown_seconds,
            "indicator_reentry_cooldown_bars": self.indicator_reentry_cooldown_bars,
            "indicator_reentry_requires_signal_reset": self.indicator_reentry_requires_signal_reset,
            "auto_flip_on_close": self.auto_flip_on_close,
            "allow_close_ignoring_hold": self.allow_close_ignoring_hold,
            "allow_multi_indicator_close": self.allow_multi_indicator_close,
            "allow_indicator_close_without_signal": self.allow_indicator_close_without_signal,
            "indicator_flip_confirmation_bars": self.indicator_flip_confirmation_bars,
            "close_on_exit": self.close_on_exit,
            "positions_missing_threshold": self.positions_missing_threshold,
            "positions_missing_autoclose": self.positions_missing_autoclose,
            "positions_missing_grace_seconds": self.positions_missing_grace_seconds,
            "futures_flat_purge_miss_threshold": self.futures_flat_purge_miss_threshold,
            "futures_flat_purge_grace_seconds": self.futures_flat_purge_grace_seconds,
            "allow_opposite_positions": self.allow_opposite_positions,
            "hedge_preserve_opposites": self.hedge_preserve_opposites,
            "max_auto_bump_percent": self.max_auto_bump_percent,
            "auto_bump_percent_multiplier": self.auto_bump_percent_multiplier,
            "stop_loss": self.stop_loss.to_config_dict(),
        }
