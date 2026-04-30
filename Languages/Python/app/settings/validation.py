from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from .backtest import MDD_LOGIC_OPTIONS
from .risk import coerce_bool, normalize_stop_loss_dict


BINANCE_MAX_FUTURES_LEVERAGE = 125
MAX_LOOKBACK_BARS = 1_000_000
MAX_GTD_MINUTES = 7 * 24 * 60
MAX_SCAN_TOP_N = 10_000

_CONTROL_TEXT_RE = re.compile(r"[\x00-\x1f\x7f]")
_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]*)\s*$")
_UPPERCASE_MONTH_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*M\s*$")
_MONTH_ALIAS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mo|mon|mons|month|months)\s*$", re.IGNORECASE)
_INTERVAL_UNIT_ALIASES = {
    "": "m",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "m": "m",
    "min": "m",
    "mins": "m",
    "minute": "m",
    "minutes": "m",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "d": "d",
    "day": "d",
    "days": "d",
    "w": "w",
    "wk": "w",
    "wks": "w",
    "week": "w",
    "weeks": "w",
    "y": "y",
    "yr": "y",
    "yrs": "y",
    "year": "y",
    "years": "y",
}

_ACCOUNT_TYPE_CHOICES = {"spot": "Spot", "futures": "Futures"}
_MARGIN_MODE_CHOICES = {"isolated": "Isolated", "cross": "Cross"}
_POSITION_MODE_CHOICES = {"hedge": "Hedge", "one-way": "One-way", "oneway": "One-way"}
_ASSETS_MODE_CHOICES = {
    "single-asset": "Single-Asset",
    "single-asset mode": "Single-Asset",
    "multi-assets": "Multi-Assets",
    "multi-asset": "Multi-Assets",
    "multi-assets mode": "Multi-Assets",
}
_ACCOUNT_MODE_CHOICES = {
    "classic trading": "Classic Trading",
    "portfolio margin": "Portfolio Margin",
}
_SIDE_CHOICES = {"both": "BOTH", "buy": "BUY", "sell": "SELL"}
_ORDER_TYPE_CHOICES = {"market": "MARKET", "limit": "LIMIT"}
_TIF_CHOICES = {"gtc": "GTC", "ioc": "IOC", "fok": "FOK", "gtd": "GTD"}
_LOGIC_CHOICES = {"and": "AND", "or": "OR"}


@dataclass(frozen=True, slots=True)
class ConfigValidationIssue:
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


class ConfigValidationError(ValueError):
    def __init__(self, issues: list[ConfigValidationIssue] | tuple[ConfigValidationIssue, ...]) -> None:
        self.issues = tuple(issues)
        super().__init__(format_config_validation_issues(self.issues))

    def to_dict(self) -> dict[str, object]:
        return {
            "message": str(self),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def format_config_validation_issues(issues: tuple[ConfigValidationIssue, ...]) -> str:
    if not issues:
        return "Invalid config."
    return "Invalid config: " + "; ".join(f"{issue.field}: {issue.message}" for issue in issues)


def _field(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _format_amount(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value).rstrip("0").rstrip(".")


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip() if isinstance(value, str) else value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _string_value(value: object, *, allow_empty: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text and not allow_empty:
        return None
    if _CONTROL_TEXT_RE.search(text):
        return None
    return text


def _validate_text(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
    allow_empty: bool = False,
) -> None:
    if key not in cfg:
        return
    value = _string_value(cfg.get(key), allow_empty=allow_empty)
    if value is None:
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be a non-empty text value"))
        return
    cfg[key] = value


def _validate_choice(
    cfg: dict[str, object],
    key: str,
    choices: Mapping[str, str],
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
) -> None:
    if key not in cfg:
        return
    text = _string_value(cfg.get(key))
    if text is None:
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be a supported value"))
        return
    normalized = choices.get(text.strip().lower())
    if normalized is None:
        allowed = ", ".join(sorted(set(choices.values())))
        issues.append(ConfigValidationIssue(_field(prefix, key), f"must be one of: {allowed}"))
        return
    cfg[key] = normalized


def _validate_int_range(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    min_value: int,
    max_value: int,
    prefix: str = "",
) -> None:
    if key not in cfg:
        return
    value = _finite_float(cfg.get(key))
    if value is None or not value.is_integer():
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be an integer"))
        return
    integer = int(value)
    if integer < min_value or integer > max_value:
        issues.append(ConfigValidationIssue(_field(prefix, key), f"must be between {min_value} and {max_value}"))
        return
    cfg[key] = integer


def _validate_float_range(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    min_value: float,
    max_value: float,
    prefix: str = "",
    exclusive_min: bool = False,
) -> None:
    if key not in cfg:
        return
    value = _finite_float(cfg.get(key))
    min_ok = value is not None and (value > min_value if exclusive_min else value >= min_value)
    if value is None or not min_ok or value > max_value:
        op = ">" if exclusive_min else ">="
        issues.append(ConfigValidationIssue(_field(prefix, key), f"must be {op} {min_value:g} and <= {max_value:g}"))
        return
    cfg[key] = float(value)


def _normalize_interval(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    month_match = _UPPERCASE_MONTH_RE.fullmatch(raw)
    if month_match:
        amount = _finite_float(month_match.group(1))
        return f"{_format_amount(amount)}mo" if amount and amount > 0 else ""
    month_alias_match = _MONTH_ALIAS_RE.fullmatch(raw)
    if month_alias_match:
        amount = _finite_float(month_alias_match.group(1))
        return f"{_format_amount(amount)}mo" if amount and amount > 0 else ""
    match = _INTERVAL_RE.fullmatch(raw)
    if not match:
        return ""
    amount = _finite_float(match.group(1))
    unit = _INTERVAL_UNIT_ALIASES.get(str(match.group(2) or "").strip().lower())
    if amount is None or amount <= 0 or unit is None:
        return ""
    return f"{_format_amount(amount)}{unit}"


def _validate_symbol_list(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
    require_non_empty: bool = True,
) -> None:
    if key not in cfg:
        return
    raw_value = cfg.get(key)
    values = [raw_value] if isinstance(raw_value, str) else raw_value
    if not isinstance(values, (list, tuple, set)):
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be a list of symbols"))
        return
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_item in values:
        symbol = _string_value(raw_item)
        if symbol is None or any(part.isspace() for part in symbol):
            issues.append(ConfigValidationIssue(_field(prefix, key), "contains an invalid symbol"))
            continue
        normalized = symbol.upper()
        if normalized not in seen:
            seen.add(normalized)
            symbols.append(normalized)
    if require_non_empty and not symbols:
        issues.append(ConfigValidationIssue(_field(prefix, key), "must contain at least one symbol"))
        return
    cfg[key] = symbols


def _validate_interval_list(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
    require_non_empty: bool = True,
) -> None:
    if key not in cfg:
        return
    raw_value = cfg.get(key)
    values = [raw_value] if isinstance(raw_value, str) else raw_value
    if not isinstance(values, (list, tuple, set)):
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be a list of intervals"))
        return
    intervals: list[str] = []
    seen: set[str] = set()
    for raw_item in values:
        interval = _normalize_interval(raw_item)
        if not interval:
            issues.append(ConfigValidationIssue(_field(prefix, key), "contains an invalid interval"))
            continue
        if interval not in seen:
            seen.add(interval)
            intervals.append(interval)
    if require_non_empty and not intervals:
        issues.append(ConfigValidationIssue(_field(prefix, key), "must contain at least one interval"))
        return
    cfg[key] = intervals


def _validate_bool(cfg: dict[str, object], key: str, *, default: bool = False) -> None:
    if key in cfg:
        cfg[key] = coerce_bool(cfg.get(key), default)


def _validate_stop_loss(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
) -> None:
    if key not in cfg:
        return
    value = cfg.get(key)
    if value is not None and not isinstance(value, Mapping):
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be an object"))
        return
    cfg[key] = normalize_stop_loss_dict(value)


def _validate_pair_list(
    cfg: dict[str, object],
    key: str,
    issues: list[ConfigValidationIssue],
    *,
    prefix: str = "",
) -> None:
    if key not in cfg:
        return
    raw_value = cfg.get(key)
    if raw_value in (None, ""):
        cfg[key] = []
        return
    if not isinstance(raw_value, (list, tuple)):
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be a list of symbol/interval objects"))
        return
    normalized_entries: list[dict[str, object]] = []
    for index, raw_entry in enumerate(raw_value):
        entry_field = f"{_field(prefix, key)}[{index}]"
        if not isinstance(raw_entry, Mapping):
            issues.append(ConfigValidationIssue(entry_field, "must be an object"))
            continue
        entry = copy.deepcopy(dict(raw_entry))
        symbol = _string_value(entry.get("symbol"))
        interval = _normalize_interval(entry.get("interval"))
        if symbol is None or any(part.isspace() for part in symbol):
            issues.append(ConfigValidationIssue(f"{entry_field}.symbol", "must be a non-empty symbol"))
            continue
        if not interval:
            issues.append(ConfigValidationIssue(f"{entry_field}.interval", "must be a valid interval"))
            continue
        entry["symbol"] = symbol.upper()
        entry["interval"] = interval
        controls = entry.get("strategy_controls")
        if isinstance(controls, Mapping):
            controls_copy = copy.deepcopy(dict(controls))
            _validate_choice(controls_copy, "side", _SIDE_CHOICES, issues, prefix=f"{entry_field}.strategy_controls")
            _validate_int_range(
                controls_copy,
                "leverage",
                issues,
                min_value=1,
                max_value=BINANCE_MAX_FUTURES_LEVERAGE,
                prefix=f"{entry_field}.strategy_controls",
            )
            if "loop_interval_override" in controls_copy and controls_copy.get("loop_interval_override"):
                loop_interval = _normalize_interval(controls_copy.get("loop_interval_override"))
                if not loop_interval:
                    issues.append(
                        ConfigValidationIssue(
                            f"{entry_field}.strategy_controls.loop_interval_override",
                            "must be a valid interval",
                        )
                    )
                else:
                    controls_copy["loop_interval_override"] = loop_interval
            _validate_stop_loss(
                controls_copy,
                "stop_loss",
                issues,
                prefix=f"{entry_field}.strategy_controls",
            )
            entry["strategy_controls"] = controls_copy
        elif controls is not None:
            issues.append(ConfigValidationIssue(f"{entry_field}.strategy_controls", "must be an object"))
        normalized_entries.append(entry)
    cfg[key] = normalized_entries


def _validate_mapping(cfg: dict[str, object], key: str, issues: list[ConfigValidationIssue], *, prefix: str = "") -> None:
    if key in cfg and not isinstance(cfg.get(key), Mapping):
        issues.append(ConfigValidationIssue(_field(prefix, key), "must be an object"))


def _validate_backtest_config(cfg: dict[str, object], issues: list[ConfigValidationIssue]) -> None:
    if "backtest" not in cfg:
        return
    value = cfg.get("backtest")
    if not isinstance(value, Mapping):
        issues.append(ConfigValidationIssue("backtest", "must be an object"))
        return
    backtest_cfg = copy.deepcopy(dict(value))
    _validate_symbol_list(backtest_cfg, "symbols", issues, prefix="backtest")
    _validate_interval_list(backtest_cfg, "intervals", issues, prefix="backtest")
    _validate_float_range(backtest_cfg, "capital", issues, min_value=0.0, max_value=1_000_000_000_000.0, prefix="backtest", exclusive_min=True)
    _validate_choice(backtest_cfg, "logic", _LOGIC_CHOICES, issues, prefix="backtest")
    _validate_text(backtest_cfg, "symbol_source", issues, prefix="backtest")
    _validate_float_range(backtest_cfg, "position_pct", issues, min_value=0.0, max_value=100.0, prefix="backtest", exclusive_min=True)
    _validate_choice(backtest_cfg, "side", _SIDE_CHOICES, issues, prefix="backtest")
    _validate_choice(backtest_cfg, "margin_mode", _MARGIN_MODE_CHOICES, issues, prefix="backtest")
    _validate_choice(backtest_cfg, "position_mode", _POSITION_MODE_CHOICES, issues, prefix="backtest")
    _validate_choice(backtest_cfg, "assets_mode", _ASSETS_MODE_CHOICES, issues, prefix="backtest")
    _validate_choice(backtest_cfg, "account_mode", _ACCOUNT_MODE_CHOICES, issues, prefix="backtest")
    _validate_text(backtest_cfg, "connector_backend", issues, prefix="backtest")
    _validate_int_range(
        backtest_cfg,
        "leverage",
        issues,
        min_value=1,
        max_value=BINANCE_MAX_FUTURES_LEVERAGE,
        prefix="backtest",
    )
    if "mdd_logic" in backtest_cfg:
        mdd_choices = {item: item for item in MDD_LOGIC_OPTIONS}
        _validate_choice(backtest_cfg, "mdd_logic", mdd_choices, issues, prefix="backtest")
    _validate_int_range(backtest_cfg, "scan_top_n", issues, min_value=1, max_value=MAX_SCAN_TOP_N, prefix="backtest")
    _validate_float_range(backtest_cfg, "scan_mdd_limit", issues, min_value=0.0, max_value=100.0, prefix="backtest")
    _validate_bool(backtest_cfg, "scan_auto_apply")
    _validate_mapping(backtest_cfg, "template", issues, prefix="backtest")
    _validate_mapping(backtest_cfg, "indicators", issues, prefix="backtest")
    _validate_stop_loss(backtest_cfg, "stop_loss", issues, prefix="backtest")
    cfg["backtest"] = backtest_cfg


def validate_runtime_config(config: Mapping[str, object] | dict[str, object] | None) -> dict[str, object]:
    if not isinstance(config, Mapping):
        raise ConfigValidationError([ConfigValidationIssue("config", "must be an object")])

    issues: list[ConfigValidationIssue] = []
    cfg = copy.deepcopy(dict(config))

    _validate_text(cfg, "mode", issues)
    _validate_choice(cfg, "account_type", _ACCOUNT_TYPE_CHOICES, issues)
    _validate_choice(cfg, "margin_mode", _MARGIN_MODE_CHOICES, issues)
    _validate_symbol_list(cfg, "symbols", issues)
    _validate_interval_list(cfg, "intervals", issues)
    _validate_int_range(cfg, "lookback", issues, min_value=1, max_value=MAX_LOOKBACK_BARS)
    _validate_int_range(cfg, "leverage", issues, min_value=1, max_value=BINANCE_MAX_FUTURES_LEVERAGE)
    _validate_choice(cfg, "tif", _TIF_CHOICES, issues)
    _validate_int_range(cfg, "gtd_minutes", issues, min_value=1, max_value=MAX_GTD_MINUTES)
    _validate_choice(cfg, "position_mode", _POSITION_MODE_CHOICES, issues)
    _validate_choice(cfg, "assets_mode", _ASSETS_MODE_CHOICES, issues)
    _validate_choice(cfg, "account_mode", _ACCOUNT_MODE_CHOICES, issues)
    _validate_text(cfg, "loop_interval_override", issues, allow_empty=True)
    if cfg.get("loop_interval_override"):
        loop_interval = _normalize_interval(cfg.get("loop_interval_override"))
        if not loop_interval:
            issues.append(ConfigValidationIssue("loop_interval_override", "must be a valid interval"))
        else:
            cfg["loop_interval_override"] = loop_interval
    _validate_pair_list(cfg, "runtime_symbol_interval_pairs", issues)
    _validate_pair_list(cfg, "backtest_symbol_interval_pairs", issues)
    _validate_choice(cfg, "side", _SIDE_CHOICES, issues)
    _validate_float_range(cfg, "position_pct", issues, min_value=0.0, max_value=100.0, exclusive_min=True)
    _validate_choice(cfg, "order_type", _ORDER_TYPE_CHOICES, issues)
    _validate_bool(cfg, "live_trading_enabled")
    _validate_text(cfg, "live_trading_acknowledgement", issues, allow_empty=True)
    _validate_int_range(
        cfg,
        "live_trading_max_leverage",
        issues,
        min_value=1,
        max_value=BINANCE_MAX_FUTURES_LEVERAGE,
    )
    _validate_float_range(
        cfg,
        "live_trading_max_position_pct",
        issues,
        min_value=0.0,
        max_value=100.0,
        exclusive_min=True,
    )
    _validate_bool(cfg, "order_audit_enabled", default=True)
    _validate_text(cfg, "order_audit_log_path", issues, allow_empty=True)
    _validate_text(cfg, "connector_backend", issues)
    _validate_text(cfg, "indicator_source", issues)
    _validate_text(cfg, "code_language", issues)
    _validate_text(cfg, "selected_exchange", issues)
    _validate_text(cfg, "selected_forex_broker", issues, allow_empty=True)
    _validate_stop_loss(cfg, "stop_loss", issues)
    _validate_mapping(cfg, "indicators", issues)
    _validate_backtest_config(cfg, issues)

    if issues:
        raise ConfigValidationError(issues)
    return cfg


__all__ = [
    "BINANCE_MAX_FUTURES_LEVERAGE",
    "ConfigValidationError",
    "ConfigValidationIssue",
    "format_config_validation_issues",
    "validate_runtime_config",
]
