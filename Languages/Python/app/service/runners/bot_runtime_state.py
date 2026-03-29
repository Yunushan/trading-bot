"""State and snapshot mixin for the service bot runtime coordinator."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.config import DEFAULT_CONFIG
    from app.service.runners.bot_runtime_shared import _MISSING, _deep_merge_mappings
    from app.service.schemas.account import ServiceAccountSnapshot, build_account_snapshot
    from app.service.schemas.backtest import ServiceBacktestSnapshot, build_backtest_snapshot
    from app.service.schemas.config import (
        ServiceConfigSummary,
        ServiceEditableConfig,
        build_config_summary,
        build_editable_config,
    )
    from app.service.schemas.logs import ServiceLogEvent, make_log_event
    from app.service.schemas.positions import ServicePortfolioSnapshot, build_portfolio_snapshot
else:
    from ...config import DEFAULT_CONFIG
    from .bot_runtime_shared import _MISSING, _deep_merge_mappings
    from ..schemas.account import ServiceAccountSnapshot, build_account_snapshot
    from ..schemas.backtest import ServiceBacktestSnapshot, build_backtest_snapshot
    from ..schemas.config import (
        ServiceConfigSummary,
        ServiceEditableConfig,
        build_config_summary,
        build_editable_config,
    )
    from ..schemas.logs import ServiceLogEvent, make_log_event
    from ..schemas.positions import ServicePortfolioSnapshot, build_portfolio_snapshot


class BotRuntimeStateMixin:
    @property
    def config(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._config)

    def replace_config(self, config: dict | None) -> None:
        with self._lock:
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            if isinstance(config, dict):
                self._config.update(copy.deepcopy(config))
            self._account_snapshot = build_account_snapshot(
                config=self._config,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source="service-config",
            )
            self._portfolio_snapshot = build_portfolio_snapshot(
                config=self._config,
                open_position_records=self._open_position_records,
                closed_position_records=self._closed_position_records,
                closed_trade_registry=self._closed_trade_registry,
                active_pnl=self._active_pnl,
                active_margin=self._active_margin,
                closed_pnl=self._closed_pnl,
                closed_margin=self._closed_margin,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source="service-config",
            )

    def get_config_summary(self) -> ServiceConfigSummary:
        with self._lock:
            return build_config_summary(self._config)

    def get_config_payload(self) -> ServiceEditableConfig:
        with self._lock:
            return build_editable_config(self._config)

    def update_config(self, config_patch: dict | None) -> ServiceEditableConfig:
        with self._lock:
            if isinstance(config_patch, dict) and config_patch:
                merged_config = _deep_merge_mappings(self._config, config_patch)
                self.replace_config(merged_config)
            return self.get_config_payload()

    def set_account_snapshot(
        self,
        *,
        total_balance=_MISSING,
        available_balance=_MISSING,
        source: str = "service",
    ) -> ServiceAccountSnapshot:
        with self._lock:
            if total_balance is not _MISSING:
                try:
                    self._account_total_balance = None if total_balance is None else float(total_balance)
                except Exception:
                    self._account_total_balance = None
            if available_balance is not _MISSING:
                try:
                    self._account_available_balance = None if available_balance is None else float(available_balance)
                except Exception:
                    self._account_available_balance = None
            self._account_snapshot = build_account_snapshot(
                config=self._config,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source=source,
            )
            return self._account_snapshot

    def get_account_snapshot(self) -> ServiceAccountSnapshot:
        with self._lock:
            return self._account_snapshot

    def set_portfolio_snapshot(
        self,
        *,
        open_position_records=_MISSING,
        closed_position_records=_MISSING,
        closed_trade_registry=_MISSING,
        active_pnl=_MISSING,
        active_margin=_MISSING,
        closed_pnl=_MISSING,
        closed_margin=_MISSING,
        total_balance=_MISSING,
        available_balance=_MISSING,
        source: str = "service",
    ) -> ServicePortfolioSnapshot:
        with self._lock:
            if open_position_records is not _MISSING:
                self._open_position_records = (
                    copy.deepcopy(open_position_records) if isinstance(open_position_records, dict) else {}
                )
            if closed_position_records is not _MISSING:
                self._closed_position_records = (
                    copy.deepcopy(list(closed_position_records))
                    if isinstance(closed_position_records, (list, tuple))
                    else []
                )
            if closed_trade_registry is not _MISSING:
                self._closed_trade_registry = (
                    copy.deepcopy(closed_trade_registry) if isinstance(closed_trade_registry, dict) else {}
                )
            if active_pnl is not _MISSING:
                try:
                    self._active_pnl = None if active_pnl is None else float(active_pnl)
                except Exception:
                    self._active_pnl = None
            if active_margin is not _MISSING:
                try:
                    self._active_margin = None if active_margin is None else float(active_margin)
                except Exception:
                    self._active_margin = None
            if closed_pnl is not _MISSING:
                try:
                    self._closed_pnl = None if closed_pnl is None else float(closed_pnl)
                except Exception:
                    self._closed_pnl = None
            if closed_margin is not _MISSING:
                try:
                    self._closed_margin = None if closed_margin is None else float(closed_margin)
                except Exception:
                    self._closed_margin = None
            if total_balance is not _MISSING:
                try:
                    self._account_total_balance = None if total_balance is None else float(total_balance)
                except Exception:
                    self._account_total_balance = None
            if available_balance is not _MISSING:
                try:
                    self._account_available_balance = None if available_balance is None else float(available_balance)
                except Exception:
                    self._account_available_balance = None
            self._portfolio_snapshot = build_portfolio_snapshot(
                config=self._config,
                open_position_records=self._open_position_records,
                closed_position_records=self._closed_position_records,
                closed_trade_registry=self._closed_trade_registry,
                active_pnl=self._active_pnl,
                active_margin=self._active_margin,
                closed_pnl=self._closed_pnl,
                closed_margin=self._closed_margin,
                total_balance=self._account_total_balance,
                available_balance=self._account_available_balance,
                source=source,
            )
            return self._portfolio_snapshot

    def get_portfolio_snapshot(self) -> ServicePortfolioSnapshot:
        with self._lock:
            return self._portfolio_snapshot

    def record_log_event(
        self,
        message: str,
        *,
        source: str = "service",
        level: str = "info",
    ) -> ServiceLogEvent:
        with self._lock:
            self._log_sequence += 1
            event = make_log_event(
                message=message,
                source=source,
                level=level,
                sequence_id=self._log_sequence,
            )
            self._recent_logs.append(event)
            return event

    def get_recent_logs(self, *, limit: int = 100) -> tuple[ServiceLogEvent, ...]:
        with self._lock:
            try:
                max_items = max(1, int(limit))
            except Exception:
                max_items = 100
            items = list(self._recent_logs)
            return tuple(items[-max_items:])

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        with self._lock:
            return {
                "runtime": self.describe_runtime().to_dict(),
                "status": self.get_status().to_dict(),
                "config": self.get_config_payload().to_dict(),
                "config_summary": self.get_config_summary().to_dict(),
                "execution": self.get_execution_snapshot().to_dict(),
                "backtest": self.get_backtest_snapshot().to_dict(),
                "account": self.get_account_snapshot().to_dict(),
                "portfolio": self.get_portfolio_snapshot().to_dict(),
                "logs": [item.to_dict() for item in self.get_recent_logs(limit=log_limit)],
            }

    def set_backtest_snapshot(self, snapshot: ServiceBacktestSnapshot) -> ServiceBacktestSnapshot:
        with self._lock:
            if not isinstance(snapshot, ServiceBacktestSnapshot):
                snapshot = build_backtest_snapshot(source="service-runtime")
            self._backtest_snapshot = snapshot
            return self._backtest_snapshot

    def get_backtest_snapshot(self) -> ServiceBacktestSnapshot:
        with self._lock:
            return self._backtest_snapshot
