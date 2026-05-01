"""State and snapshot mixin for the service bot runtime coordinator."""

from __future__ import annotations

import copy
import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.config import build_default_config, validate_runtime_config
    from app.jsonl_rotation import jsonl_backup_path, rotate_jsonl_if_needed
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
    from app.service.schemas.status import (
        DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH,
        DEFAULT_ORDER_AUDIT_DISPLAY_PATH,
        build_exchange_connector_snapshot,
    )
    from app.security.redaction import redact_text, redact_value
    from app.settings import coerce_bool, is_live_trading_mode
else:
    from ...config import build_default_config, validate_runtime_config
    from ...jsonl_rotation import jsonl_backup_path, rotate_jsonl_if_needed
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
    from ..schemas.status import (
        DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH,
        DEFAULT_ORDER_AUDIT_DISPLAY_PATH,
        build_exchange_connector_snapshot,
    )
    from ...security.redaction import redact_text, redact_value
    from ...settings import coerce_bool, is_live_trading_mode


class BotRuntimeStateMixin:
    _DEFAULT_CONNECTOR_SNAPSHOT_STALE_SECONDS = 120.0
    _DEFAULT_EXECUTION_HEARTBEAT_STALE_SECONDS = 10.0
    _DEFAULT_ACCOUNT_SNAPSHOT_STALE_SECONDS = 300.0
    _DEFAULT_PORTFOLIO_SNAPSHOT_STALE_SECONDS = 300.0

    @property
    def config(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._config)

    def replace_config(self, config: dict | None) -> None:
        with self._lock:
            next_config = build_default_config()
            if isinstance(config, dict):
                next_config = _deep_merge_mappings(next_config, copy.deepcopy(config))
            self._config = validate_runtime_config(next_config)
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
            self._exchange_connector_snapshot = build_exchange_connector_snapshot(
                config=self._config,
                snapshot=self._exchange_connector_snapshot,
                source=str(self._exchange_connector_snapshot.get("source") or "service-config"),
            )
            self._connector_order_circuit_breaker_snapshot = (
                self._build_connector_order_circuit_breaker_snapshot_unlocked(
                    self._connector_order_circuit_breaker_snapshot,
                    source=str(
                        self._connector_order_circuit_breaker_snapshot.get("source")
                        or "service-config"
                    ),
                )
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

    def set_exchange_connector_snapshot(
        self,
        snapshot: dict | None = None,
        *,
        source: str = "service",
        **updates,
    ) -> dict[str, object]:
        with self._lock:
            payload = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}
            if isinstance(updates, dict) and updates:
                payload.update(copy.deepcopy(updates))
            payload["source"] = str(source or payload.get("source") or "service")
            self._exchange_connector_snapshot = build_exchange_connector_snapshot(
                config=self._config,
                snapshot=payload,
                source=source,
            )
            return copy.deepcopy(self._exchange_connector_snapshot)

    def get_exchange_connector_snapshot(self) -> dict[str, object]:
        with self._lock:
            return copy.deepcopy(self._exchange_connector_snapshot)

    def _build_connector_order_circuit_breaker_snapshot_unlocked(
        self,
        snapshot: dict | None = None,
        *,
        source: str = "service",
    ) -> dict[str, object]:
        raw = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        raw_state = str(raw.get("state") or "").strip().lower()
        active = bool(raw.get("active", False)) or raw_state in {"open", "paused", "tripped"}
        try:
            block_count = max(0, int(raw.get("block_count") or 0))
        except Exception:
            block_count = 0
        try:
            threshold = max(
                1,
                int(raw.get("block_threshold") or self._config.get("connector_order_block_pause_threshold") or 2),
            )
        except Exception:
            threshold = 2
        try:
            window_seconds = max(
                1.0,
                float(
                    raw.get("block_window_seconds")
                    or self._config.get("connector_order_block_window_seconds")
                    or 60.0
                ),
            )
        except Exception:
            window_seconds = 60.0
        message = str(raw.get("message") or "").strip()
        if active and not message:
            message = "Connector health circuit breaker paused trading."
        payload = {
            "active": active,
            "state": "open" if active else "closed",
            "reason": str(raw.get("reason") or "").strip(),
            "message": message,
            "block_count": block_count,
            "block_threshold": threshold,
            "block_window_seconds": window_seconds,
            "tripped_at": str(raw.get("tripped_at") or (self._now_iso() if active else "")),
            "cleared_at": str(raw.get("cleared_at") or ""),
            "source": str(raw.get("source") or source or "service"),
            "symbol": str(raw.get("symbol") or "").upper(),
            "interval": str(raw.get("interval") or ""),
            "side": str(raw.get("side") or "").upper(),
            "account_type": str(raw.get("account_type") or ""),
            "connector_health": raw.get("connector_health"),
            "connector_state": raw.get("connector_state"),
            "reset_blocked": bool(raw.get("reset_blocked", False)),
            "reset_blocked_reason": str(raw.get("reset_blocked_reason") or "").strip(),
            "reset_blocked_at": str(raw.get("reset_blocked_at") or ""),
            "last_event": raw.get("last_event") if isinstance(raw.get("last_event"), dict) else None,
            "generated_at": self._now_iso(),
        }
        return redact_value({key: value for key, value in payload.items() if value not in (None, "", {}, [])})

    def _connector_order_circuit_reset_block_reason_unlocked(self) -> str:
        connector_snapshot = build_exchange_connector_snapshot(
            config=self._config,
            snapshot=self._exchange_connector_snapshot,
            source=str(self._exchange_connector_snapshot.get("source") or "service"),
        )
        health = str(connector_snapshot.get("health") or "unknown").strip().lower()
        if health != "error":
            return ""
        state = str(connector_snapshot.get("state") or "unknown").strip().lower() or "unknown"
        detail = ""
        attention = connector_snapshot.get("attention")
        if isinstance(attention, list) and attention:
            detail = str(attention[0] or "").strip()
        if not detail:
            last_error = connector_snapshot.get("last_error")
            if isinstance(last_error, dict):
                detail = str(last_error.get("message") or "").strip()
        message = f"Connector health circuit breaker reset blocked: exchange connector is still error ({state})."
        if detail:
            message = f"{message} {detail}"
        return redact_text(message)

    def _order_audit_backup_count_unlocked(self) -> int:
        raw_value = self._config.get("order_audit_backup_count")
        if raw_value in (None, ""):
            return 1
        try:
            return max(0, min(100, int(float(str(raw_value).strip()))))
        except Exception:
            return 1

    def _connector_order_circuit_incident_log_info_unlocked(self) -> tuple[str, str, str]:
        configured_path = str(self._config.get("connector_order_circuit_incident_log_path") or "").strip()
        path_source = "configured" if configured_path else "default"
        effective_path = configured_path or DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH
        return effective_path, path_source, configured_path

    def _connector_order_circuit_incident_log_max_bytes_unlocked(self) -> int:
        try:
            return max(1, int(self._config.get("connector_order_circuit_incident_log_max_bytes") or 2 * 1024 * 1024))
        except Exception:
            return 2 * 1024 * 1024

    def _connector_order_circuit_incident_log_backup_count_unlocked(self) -> int:
        raw_value = self._config.get("connector_order_circuit_incident_log_backup_count")
        if raw_value in (None, ""):
            return 1
        try:
            return max(0, min(100, int(float(str(raw_value).strip()))))
        except Exception:
            return 1

    def _record_connector_order_circuit_incident_unlocked(
        self,
        action: str,
        snapshot: dict[str, object],
        *,
        source: str,
        message: str,
    ) -> None:
        effective_path, _, _ = self._connector_order_circuit_incident_log_info_unlocked()
        event = redact_value(
            {
                "ts": self._now_iso(),
                "event": f"connector_order_circuit_{action}",
                "action": action,
                "source": str(source or "service"),
                "message": message,
                "active": bool(snapshot.get("active")),
                "state": str(snapshot.get("state") or ""),
                "reason": str(snapshot.get("reason") or ""),
                "block_count": snapshot.get("block_count"),
                "block_threshold": snapshot.get("block_threshold"),
                "symbol": str(snapshot.get("symbol") or ""),
                "interval": str(snapshot.get("interval") or ""),
                "side": str(snapshot.get("side") or ""),
                "connector_health": snapshot.get("connector_health"),
                "connector_state": snapshot.get("connector_state"),
                "circuit": copy.deepcopy(snapshot),
            }
        )
        try:
            path = Path(effective_path).expanduser()
            line = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
            path.parent.mkdir(parents=True, exist_ok=True)
            rotate_jsonl_if_needed(
                path,
                len((line + "\n").encode("utf-8")),
                max_bytes=self._connector_order_circuit_incident_log_max_bytes_unlocked(),
                backup_count=self._connector_order_circuit_incident_log_backup_count_unlocked(),
            )
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception as exc:
            error_message = redact_text(str(exc))
            self._connector_order_circuit_incident_log_last_write_error = {
                "ts": self._now_iso(),
                "message": error_message,
                "path": effective_path,
            }
            if not bool(getattr(self, "_connector_order_circuit_incident_log_warned", False)):
                self._connector_order_circuit_incident_log_warned = True
                self.record_log_event(
                    f"Connector order circuit incident log write failed: {error_message}",
                    source="connector-order-circuit",
                    level="warning",
                )
            return
        self._connector_order_circuit_incident_log_last_write_error = None
        self._connector_order_circuit_incident_log_last_write_ok_at = str(event.get("ts") or self._now_iso())
        self._connector_order_circuit_last_incident = event

    def get_connector_order_circuit_incidents(self, *, limit: int = 20) -> dict[str, object]:
        with self._lock:
            effective_path, path_source, configured_path = (
                self._connector_order_circuit_incident_log_info_unlocked()
            )
        try:
            max_items = max(1, min(200, int(limit or 20)))
        except Exception:
            max_items = 20
        path = Path(effective_path).expanduser()
        events: deque[dict[str, object]] = deque(maxlen=max_items)
        total_read = 0
        backup_count = self._connector_order_circuit_incident_log_backup_count_unlocked()
        candidate_paths = [
            jsonl_backup_path(path, index) for index in range(backup_count, 0, -1)
        ] + [path]
        exists = any(candidate_path.is_file() for candidate_path in candidate_paths)
        error_message = ""
        for candidate_path in candidate_paths:
            if not candidate_path.is_file():
                continue
            try:
                with candidate_path.open("r", encoding="utf-8") as handle:
                    for line_number, raw_line in enumerate(handle, start=1):
                        text = raw_line.strip()
                        if not text:
                            continue
                        total_read += 1
                        try:
                            decoded = json.loads(text)
                        except Exception as exc:
                            decoded = {
                                "event": "connector_order_circuit_log_parse_error",
                                "action": "parse_error",
                                "line_number": line_number,
                                "message": f"Could not parse incident log line: {redact_text(str(exc))}",
                                "raw": redact_text(text[:500]),
                            }
                        if not isinstance(decoded, dict):
                            decoded = {
                                "event": "connector_order_circuit_log_parse_error",
                                "action": "parse_error",
                                "line_number": line_number,
                                "message": "Incident log line was not a JSON object.",
                                "value": redact_value(decoded),
                            }
                        events.append(redact_value(decoded))
            except Exception as exc:
                error_message = redact_text(str(exc))
                break
        payload = {
            "path": effective_path,
            "path_source": path_source,
            "configured_path": configured_path,
            "max_bytes": self._connector_order_circuit_incident_log_max_bytes_unlocked(),
            "backup_count": backup_count,
            "exists": exists,
            "limit": max_items,
            "count": len(events),
            "total_read": total_read,
            "events": list(events),
            "last_event": events[-1] if events else None,
            "error": error_message,
        }
        return redact_value({key: value for key, value in payload.items() if value not in ("", None)})

    def set_connector_order_circuit_breaker_snapshot(
        self,
        snapshot: dict | None = None,
        *,
        source: str = "service",
        **updates,
    ) -> dict[str, object]:
        with self._lock:
            previous_active = bool(self._connector_order_circuit_breaker_snapshot.get("active"))
            payload = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else {}
            if updates:
                payload.update(copy.deepcopy(updates))
            payload["source"] = str(source or payload.get("source") or "service")
            self._connector_order_circuit_breaker_snapshot = (
                self._build_connector_order_circuit_breaker_snapshot_unlocked(payload, source=source)
            )
            if bool(self._connector_order_circuit_breaker_snapshot.get("active")):
                self._status_message = str(
                    self._connector_order_circuit_breaker_snapshot.get("message")
                    or "Connector health circuit breaker paused trading."
                )
                self._last_transition_at = self._now_iso()
                if not previous_active:
                    self.record_log_event(
                        self._status_message,
                        source="connector-order-circuit",
                        level="info",
                    )
                    self._record_connector_order_circuit_incident_unlocked(
                        "trip",
                        self._connector_order_circuit_breaker_snapshot,
                        source=source,
                        message=self._status_message,
                    )
            return copy.deepcopy(self._connector_order_circuit_breaker_snapshot)

    def reset_connector_order_circuit_breaker(
        self,
        *,
        source: str = "service",
        force: bool = False,
    ) -> dict[str, object]:
        with self._lock:
            previous = copy.deepcopy(self._connector_order_circuit_breaker_snapshot)
            block_reason = "" if force else self._connector_order_circuit_reset_block_reason_unlocked()
            if bool(previous.get("active")) and block_reason:
                payload = {
                    **previous,
                    "active": True,
                    "state": "open",
                    "message": block_reason,
                    "reset_blocked": True,
                    "reset_blocked_reason": block_reason,
                    "reset_blocked_at": self._now_iso(),
                    "source": source,
                }
                self._connector_order_circuit_breaker_snapshot = (
                    self._build_connector_order_circuit_breaker_snapshot_unlocked(payload, source=source)
                )
                self._status_message = block_reason
                self._last_transition_at = self._now_iso()
                self.record_log_event(
                    block_reason,
                    source="connector-order-circuit",
                    level="info",
                )
                self._record_connector_order_circuit_incident_unlocked(
                    "reset_blocked",
                    self._connector_order_circuit_breaker_snapshot,
                    source=source,
                    message=block_reason,
                )
                return copy.deepcopy(self._connector_order_circuit_breaker_snapshot)
            payload = {
                **previous,
                "active": False,
                "state": "closed",
                "message": "Connector health circuit breaker reset.",
                "cleared_at": self._now_iso(),
                "reset_blocked": False,
                "reset_blocked_reason": "",
                "reset_blocked_at": "",
                "source": source,
            }
            self._connector_order_circuit_breaker_snapshot = (
                self._build_connector_order_circuit_breaker_snapshot_unlocked(payload, source=source)
            )
            self._status_message = "Connector health circuit breaker reset."
            self._last_transition_at = self._now_iso()
            self.record_log_event(
                self._status_message,
                source="connector-order-circuit",
                level="info",
            )
            if bool(previous.get("active")) or bool(previous.get("reset_blocked")):
                self._record_connector_order_circuit_incident_unlocked(
                    "reset",
                    self._connector_order_circuit_breaker_snapshot,
                    source=source,
                    message=self._status_message,
                )
            return copy.deepcopy(self._connector_order_circuit_breaker_snapshot)

    def get_connector_order_circuit_breaker_snapshot(self) -> dict[str, object]:
        with self._lock:
            return copy.deepcopy(self._connector_order_circuit_breaker_snapshot)

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

    @staticmethod
    def _log_is_warning(level: str) -> bool:
        return level in {"warning", "warn"}

    @staticmethod
    def _log_is_error(level: str) -> bool:
        return level in {"error", "critical", "fatal", "exception"}

    @staticmethod
    def _timestamp_epoch(value: object) -> float | None:
        if value in (None, "", "-"):
            return None
        if isinstance(value, (int, float)):
            try:
                return float(value)
            except Exception:
                return None
        text = str(value or "").strip()
        if not text or text == "-":
            return None
        try:
            return float(text)
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    @classmethod
    def _freshness_payload(
        cls,
        *,
        timestamp: object,
        timestamp_field: str,
        now_epoch: float,
        max_age_seconds: float,
        should_warn: bool,
        state: object = "",
        source: object = "",
    ) -> dict[str, object]:
        epoch = cls._timestamp_epoch(timestamp)
        age_seconds = None if epoch is None else max(0.0, now_epoch - epoch)
        stale = bool(should_warn) and (age_seconds is None or age_seconds > max_age_seconds)
        payload: dict[str, object] = {
            "stale": stale,
            "max_age_seconds": float(max_age_seconds),
        }
        if timestamp not in (None, "", "-"):
            payload[timestamp_field] = str(timestamp)
        if age_seconds is not None:
            payload["age_seconds"] = round(age_seconds, 3)
        if state not in (None, ""):
            payload["state"] = str(state)
        if source not in (None, ""):
            payload["source"] = str(source)
        return payload

    @staticmethod
    def _freshness_attention(label: str, freshness: dict[str, object], *, timestamp_name: str = "update") -> str:
        age = freshness.get("age_seconds")
        if age is None:
            return f"{label} {timestamp_name} is missing."
        try:
            age_text = f"{float(age):.0f}s"
        except Exception:
            age_text = "unknown age"
        return f"{label} is stale (last {timestamp_name} {age_text} ago)."

    def _freshness_threshold_unlocked(self, key: str, default: float) -> float:
        try:
            value = float(self._config.get(key, default))
        except Exception:
            return float(default)
        return value if value > 0 else float(default)

    def _build_operational_snapshot_unlocked(
        self,
        *,
        require_fresh_snapshots: bool = False,
    ) -> dict[str, object]:
        now_iso = self._now_iso()
        now_epoch = self._timestamp_epoch(now_iso) or datetime.now(timezone.utc).timestamp()
        logs = list(self._recent_logs)
        by_level: dict[str, int] = {}
        warning_events: list[ServiceLogEvent] = []
        error_events: list[ServiceLogEvent] = []
        for event in logs:
            level = str(event.level or "info").strip().lower() or "info"
            by_level[level] = by_level.get(level, 0) + 1
            if self._log_is_warning(level):
                warning_events.append(event)
            if self._log_is_error(level):
                error_events.append(event)

        audit_enabled = bool(self._config.get("order_audit_enabled", True))
        audit_path = str(self._config.get("order_audit_log_path") or "").strip()
        audit_path_source = "configured" if audit_path else "default"
        effective_audit_path = audit_path or DEFAULT_ORDER_AUDIT_DISPLAY_PATH
        try:
            audit_max_bytes = max(1, int(self._config.get("order_audit_max_bytes") or 10 * 1024 * 1024))
        except Exception:
            audit_max_bytes = 10 * 1024 * 1024
        audit_backup_count = self._order_audit_backup_count_unlocked()
        incident_log_path, incident_log_path_source, incident_configured_path = (
            self._connector_order_circuit_incident_log_info_unlocked()
        )
        incident_log_max_bytes = self._connector_order_circuit_incident_log_max_bytes_unlocked()
        incident_log_backup_count = self._connector_order_circuit_incident_log_backup_count_unlocked()
        incident_log_last_write_error = copy.deepcopy(
            getattr(self, "_connector_order_circuit_incident_log_last_write_error", None)
        )
        incident_log_last_write_ok_at = str(
            getattr(self, "_connector_order_circuit_incident_log_last_write_ok_at", "") or ""
        )

        attention: list[str] = []
        if error_events:
            attention.append(f"{len(error_events)} recent error log event(s) need review.")
        if warning_events:
            attention.append(f"{len(warning_events)} recent warning log event(s) need review.")
        if not audit_enabled:
            attention.append("Order audit logging is disabled.")
        if incident_log_last_write_error:
            message = str(incident_log_last_write_error.get("message") or "unknown write error").strip()
            attention.append(f"Connector order circuit incident log write failed: {message}")
        if self._requested_action:
            attention.append(f"{self._requested_action} request is pending in phase {self._lifecycle_phase}.")
        if self._close_positions_requested:
            attention.append("Stop requested with close-all positions.")

        connector_snapshot = build_exchange_connector_snapshot(
            config=self._config,
            snapshot=self._exchange_connector_snapshot,
            source=str(self._exchange_connector_snapshot.get("source") or "service"),
        )
        reported_order_audit = (
            copy.deepcopy(connector_snapshot.get("order_audit"))
            if isinstance(connector_snapshot.get("order_audit"), dict)
            else {}
        )
        order_audit_last_write_error = (
            copy.deepcopy(reported_order_audit.get("last_write_error"))
            if isinstance(reported_order_audit.get("last_write_error"), dict)
            else None
        )
        if order_audit_last_write_error:
            message = str(order_audit_last_write_error.get("message") or "unknown write error").strip()
            attention.append(f"Order audit write failed: {message}")
        connector_health = str(connector_snapshot.get("health") or "unknown").strip().lower()
        connector_state = str(connector_snapshot.get("state") or "unknown").strip() or "unknown"
        connector_attention = connector_snapshot.get("attention")
        connector_order_circuit = self._build_connector_order_circuit_breaker_snapshot_unlocked(
            self._connector_order_circuit_breaker_snapshot,
            source=str(self._connector_order_circuit_breaker_snapshot.get("source") or "service"),
        )
        connector_order_circuit_active = bool(connector_order_circuit.get("active"))
        if connector_health in {"warning", "error"}:
            if isinstance(connector_attention, list) and connector_attention:
                attention.append(f"Exchange connector {connector_state}: {connector_attention[0]}")
            else:
                attention.append(f"Exchange connector state is {connector_state}.")
        if connector_order_circuit_active:
            circuit_message = str(
                connector_order_circuit.get("message")
                or "Connector order circuit breaker paused trading."
            )
            attention.append(circuit_message)

        execution_state = str(self._execution_state or "").strip().lower()
        runtime_needs_fresh_snapshots = bool(
            require_fresh_snapshots
            or self._runtime_active
            or self._active_engine_count > 0
            or self._execution_active_engine_count > 0
            or execution_state == "running"
        )
        account_generated_at = str(getattr(self._account_snapshot, "generated_at", "") or "")
        portfolio_generated_at = str(getattr(self._portfolio_snapshot, "generated_at", "") or "")
        connector_stale_seconds = self._freshness_threshold_unlocked(
            "operational_connector_snapshot_stale_seconds",
            self._DEFAULT_CONNECTOR_SNAPSHOT_STALE_SECONDS,
        )
        execution_stale_seconds = self._freshness_threshold_unlocked(
            "operational_execution_heartbeat_stale_seconds",
            self._DEFAULT_EXECUTION_HEARTBEAT_STALE_SECONDS,
        )
        account_stale_seconds = self._freshness_threshold_unlocked(
            "operational_account_snapshot_stale_seconds",
            self._DEFAULT_ACCOUNT_SNAPSHOT_STALE_SECONDS,
        )
        portfolio_stale_seconds = self._freshness_threshold_unlocked(
            "operational_portfolio_snapshot_stale_seconds",
            self._DEFAULT_PORTFOLIO_SNAPSHOT_STALE_SECONDS,
        )
        freshness = {
            "exchange_connector": self._freshness_payload(
                timestamp=connector_snapshot.get("generated_at"),
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=connector_stale_seconds,
                should_warn=runtime_needs_fresh_snapshots,
                state=connector_state,
                source=connector_snapshot.get("source"),
            ),
            "execution": self._freshness_payload(
                timestamp=self._execution_heartbeat_at,
                timestamp_field="heartbeat_at",
                now_epoch=now_epoch,
                max_age_seconds=execution_stale_seconds,
                should_warn=execution_state == "running",
                state=execution_state,
                source=self._execution_source,
            ),
            "account": self._freshness_payload(
                timestamp=account_generated_at,
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=account_stale_seconds,
                should_warn=runtime_needs_fresh_snapshots,
                source=getattr(self._account_snapshot, "source", ""),
            ),
            "portfolio": self._freshness_payload(
                timestamp=portfolio_generated_at,
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=portfolio_stale_seconds,
                should_warn=runtime_needs_fresh_snapshots,
                source=getattr(self._portfolio_snapshot, "source", ""),
            ),
        }
        preflight_freshness = {
            "exchange_connector": self._freshness_payload(
                timestamp=connector_snapshot.get("generated_at"),
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=connector_stale_seconds,
                should_warn=True,
                state=connector_state,
                source=connector_snapshot.get("source"),
            ),
            "execution": self._freshness_payload(
                timestamp=self._execution_heartbeat_at,
                timestamp_field="heartbeat_at",
                now_epoch=now_epoch,
                max_age_seconds=execution_stale_seconds,
                should_warn=True,
                state=execution_state,
                source=self._execution_source,
            ),
            "account": self._freshness_payload(
                timestamp=account_generated_at,
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=account_stale_seconds,
                should_warn=True,
                source=getattr(self._account_snapshot, "source", ""),
            ),
            "portfolio": self._freshness_payload(
                timestamp=portfolio_generated_at,
                timestamp_field="generated_at",
                now_epoch=now_epoch,
                max_age_seconds=portfolio_stale_seconds,
                should_warn=True,
                source=getattr(self._portfolio_snapshot, "source", ""),
            ),
        }
        stale_freshness = [
            ("Exchange connector snapshot", freshness["exchange_connector"], "update"),
            ("Execution heartbeat", freshness["execution"], "heartbeat"),
            ("Account snapshot", freshness["account"], "update"),
            ("Portfolio snapshot", freshness["portfolio"], "update"),
        ]
        for label, item, timestamp_name in stale_freshness:
            if item.get("stale"):
                attention.append(self._freshness_attention(label, item, timestamp_name=timestamp_name))

        health = "ok"
        if error_events:
            health = "error"
        if connector_order_circuit_active:
            health = "error"
        if connector_health == "error":
            health = "error"
        elif health != "error" and (warning_events or not audit_enabled):
            health = "warning"
        elif health != "error" and (incident_log_last_write_error or order_audit_last_write_error):
            health = "warning"
        elif health != "error" and connector_health == "warning":
            health = "warning"
        elif health != "error" and any(item.get("stale") for item in freshness.values()):
            health = "warning"

        live_mode = is_live_trading_mode(self._config.get("mode"))
        preflight_start_stale_labels: list[str] = []
        preflight_order_stale_labels: list[str] = []
        for key, label in (
            ("exchange_connector", "exchange connector"),
            ("account", "account"),
            ("portfolio", "portfolio"),
        ):
            item = preflight_freshness.get(key)
            if isinstance(item, dict) and bool(item.get("stale")):
                preflight_start_stale_labels.append(label)
                preflight_order_stale_labels.append(label)
        execution_freshness = preflight_freshness.get("execution")
        if isinstance(execution_freshness, dict) and bool(execution_freshness.get("stale")):
            preflight_start_stale_labels.append("execution heartbeat")

        def _preflight_issues(stale_labels: list[str]) -> list[str]:
            issues: list[str] = []
            if health == "error":
                issues.append("operational health is error")
            if stale_labels:
                issues.append("critical snapshots are stale: " + ", ".join(stale_labels))
            return issues

        def _preflight_gate(
            *,
            enabled: bool,
            issues: list[str],
            disabled_message: str,
            demo_message: str,
        ) -> dict[str, object]:
            if not enabled:
                return {
                    "allowed": True,
                    "state": "warning",
                    "gate_enabled": False,
                    "reasons": [disabled_message],
                }
            if not issues:
                return {
                    "allowed": True,
                    "state": "ok",
                    "gate_enabled": True,
                    "reasons": [],
                }
            if live_mode:
                return {
                    "allowed": False,
                    "state": "blocked",
                    "gate_enabled": True,
                    "reasons": issues,
                }
            return {
                "allowed": True,
                "state": "warning",
                "gate_enabled": True,
                "reasons": [*issues, demo_message],
            }

        preflight_start_issues = _preflight_issues(preflight_start_stale_labels)
        preflight_order_issues = _preflight_issues(preflight_order_stale_labels)
        preflight_start = _preflight_gate(
            enabled=coerce_bool(self._config.get("operational_live_start_gate_enabled"), True),
            issues=preflight_start_issues,
            disabled_message="Operational live start safety gate is disabled.",
            demo_message="Demo/test mode start remains allowed.",
        )
        preflight_orders = _preflight_gate(
            enabled=coerce_bool(self._config.get("operational_live_order_gate_enabled"), True),
            issues=preflight_order_issues,
            disabled_message="Operational live order safety gate is disabled.",
            demo_message="Demo/test mode order remains allowed.",
        )
        preflight_reasons: list[str] = []
        for gate in (preflight_start, preflight_orders):
            reasons = gate.get("reasons")
            if isinstance(reasons, list):
                for reason in reasons:
                    reason_text = str(reason or "").strip()
                    if reason_text and reason_text not in preflight_reasons:
                        preflight_reasons.append(reason_text)
        preflight_state = "ok"
        if preflight_start.get("state") == "blocked" or preflight_orders.get("state") == "blocked":
            preflight_state = "blocked"
        elif preflight_start.get("state") != "ok" or preflight_orders.get("state") != "ok":
            preflight_state = "warning"
        if preflight_state == "blocked":
            preflight_message = "Live preflight blocked. Review the reasons before starting or submitting orders."
        elif preflight_state == "warning":
            preflight_message = "Preflight has warnings. Live gate behavior depends on the enabled safety gates."
        else:
            preflight_message = "Preflight passed. Start and order gates have fresh critical snapshots."
        preflight = {
            "state": preflight_state,
            "message": preflight_message,
            "mode": str(self._config.get("mode") or ""),
            "live_mode": live_mode,
            "generated_at": now_iso,
            "start": preflight_start,
            "orders": preflight_orders,
            "freshness": preflight_freshness,
            "critical_stale": {
                "start": preflight_start_stale_labels,
                "orders": preflight_order_stale_labels,
            },
            "reasons": preflight_reasons,
        }

        last_log = logs[-1].to_dict() if logs else None
        last_warning = warning_events[-1].to_dict() if warning_events else None
        last_error = error_events[-1].to_dict() if error_events else None
        last_sequence_id = logs[-1].sequence_id if logs else 0
        order_audit_payload = {
            "enabled": audit_enabled,
            "path": effective_audit_path,
            "path_source": audit_path_source,
            "configured_path": audit_path,
            "max_bytes": audit_max_bytes,
            "backup_count": audit_backup_count,
        }
        if reported_order_audit:
            for key in (
                "state",
                "write_ok",
                "last_write_error",
                "last_write_error_at",
                "last_write_ok_at",
            ):
                if key in reported_order_audit:
                    order_audit_payload[key] = copy.deepcopy(reported_order_audit[key])

        return redact_value({
            "health": health,
            "generated_at": now_iso,
            "attention": attention,
            "freshness": freshness,
            "preflight": preflight,
            "logs": {
                "total": len(logs),
                "by_level": by_level,
                "warning_count": len(warning_events),
                "error_count": len(error_events),
                "last_sequence_id": last_sequence_id,
                "last_event": last_log,
                "last_warning": last_warning,
                "last_error": last_error,
            },
            "order_audit": order_audit_payload,
            "exchange_connector": connector_snapshot,
            "connector_order_circuit_breaker": connector_order_circuit,
            "connector_order_circuit_incident_log": {
                "path": incident_log_path,
                "path_source": incident_log_path_source,
                "configured_path": incident_configured_path,
                "max_bytes": incident_log_max_bytes,
                "backup_count": incident_log_backup_count,
                "write_ok": not bool(incident_log_last_write_error),
                "last_write_error": incident_log_last_write_error,
                "last_write_ok_at": incident_log_last_write_ok_at,
                "last_event": copy.deepcopy(self._connector_order_circuit_last_incident),
            },
            "runtime": {
                "lifecycle_phase": self._lifecycle_phase,
                "requested_action": self._requested_action,
                "runtime_active": self._runtime_active,
                "active_engine_count": self._active_engine_count,
                "execution_state": self._execution_state,
                "execution_last_action": self._execution_last_action,
                "execution_last_message": self._execution_last_message,
                "execution_heartbeat_at": self._execution_heartbeat_at,
                "control_plane_mode": self._control_plane_mode,
                "control_plane_owner": self._control_plane_owner,
            },
        })

    def get_operational_snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._build_operational_snapshot_unlocked()

    def get_dashboard_snapshot(self, *, log_limit: int = 30) -> dict[str, object]:
        with self._lock:
            return {
                "runtime": self.describe_runtime().to_dict(),
                "status": self.get_status().to_dict(),
                "operational": self.get_operational_snapshot(),
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
