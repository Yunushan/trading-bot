"""
Status schemas for the service facade.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ...security.redaction import redact_text, redact_value
from ...settings.exchange_support import build_exchange_support_payload


DEFAULT_ORDER_AUDIT_DISPLAY_PATH = "~/.trading-bot/order_audit.jsonl"
DEFAULT_CONNECTOR_ORDER_CIRCUIT_INCIDENT_DISPLAY_PATH = (
    "~/.trading-bot/connector_order_circuit_incidents.jsonl"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except Exception:
        return None


def _mapping_or_empty(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_health(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"ok", "warning", "error", "unknown"} else "unknown"


def build_exchange_connector_snapshot(
    *,
    config: Mapping[str, object] | None = None,
    snapshot: Mapping[str, object] | None = None,
    source: str = "service",
) -> dict[str, object]:
    cfg = _mapping_or_empty(config)
    raw = _mapping_or_empty(snapshot)
    rate_limit_raw = _mapping_or_empty(raw.get("rate_limit"))
    network_raw = _mapping_or_empty(raw.get("network"))
    last_error_raw = _mapping_or_empty(raw.get("last_error"))
    order_audit_raw = _mapping_or_empty(raw.get("order_audit"))
    support = build_exchange_support_payload(config=cfg, snapshot=raw)

    seconds_until_unban = _safe_float(
        rate_limit_raw.get("seconds_until_unban", raw.get("seconds_until_unban"))
    )
    seconds_until_unban = max(0.0, float(seconds_until_unban or 0.0))
    ban_until = _safe_float(rate_limit_raw.get("ban_until", raw.get("ban_until")))
    rate_limit_active = bool(rate_limit_raw.get("active", raw.get("rate_limited", False))) or seconds_until_unban > 0.0

    network_offline = bool(network_raw.get("offline", raw.get("network_offline", False)))
    network_offline_since = _safe_float(network_raw.get("offline_since", raw.get("network_offline_since")))
    network_offline_hits = _safe_int(network_raw.get("offline_hits", raw.get("network_offline_hits"))) or 0

    last_error = redact_value(last_error_raw) if last_error_raw else None
    last_error_category = ""
    last_error_retryable = None
    last_error_message = ""
    if isinstance(last_error, dict):
        last_error_category = str(last_error.get("category") or "").strip().lower()
        last_error_retryable = last_error.get("retryable")
        last_error_message = str(last_error.get("message") or "").strip()

    health = _normalize_health(raw.get("health"))
    state = str(raw.get("state") or "").strip().lower()
    if network_offline:
        health = "error"
        state = "network_offline"
    elif rate_limit_active:
        health = "warning" if health != "error" else health
        state = "rate_limited"
    elif isinstance(last_error, dict):
        if last_error_category == "auth":
            health = "error"
            state = "auth_error"
        elif last_error_category == "rate_limited":
            health = "warning" if health != "error" else health
            state = "rate_limited"
        elif last_error_retryable is True:
            health = "warning" if health == "unknown" else health
            state = state or last_error_category or "exchange_warning"
        else:
            health = "error" if health == "unknown" else health
            state = state or last_error_category or "exchange_error"
    elif not state:
        state = "ready" if health == "ok" else "unknown"
    if not support["trading_supported"]:
        health = "error"
        if not support["exchange_supported"]:
            state = "unsupported_exchange"
        elif not support["connector_backend_supported"]:
            state = "unsupported_connector_backend"
        elif not support["broker_supported"]:
            state = "unsupported_broker"

    order_audit_error = _mapping_or_empty(order_audit_raw.get("last_write_error"))
    if order_audit_error and health != "error":
        health = "warning"
        if state in {"ready", "missing_credentials", "unknown"}:
            state = "order_audit_write_failed"

    attention = []
    if health in {"warning", "error"}:
        if last_error_message:
            attention.append(last_error_message)
        elif state == "rate_limited" and seconds_until_unban > 0.0:
            attention.append(f"Exchange connector is rate limited for {seconds_until_unban:.0f}s.")
        elif state == "network_offline":
            attention.append("Exchange connector reports network connectivity loss.")
    if order_audit_error:
        message = str(order_audit_error.get("message") or "unknown write error").strip()
        attention.append(f"Order audit write failed: {message}")
    attention.extend(str(reason) for reason in support["unsupported_reasons"])

    payload = {
        "health": health,
        "state": state,
        "generated_at": str(raw.get("generated_at") or _utc_now_iso()),
        "source": redact_text(raw.get("source") or source or "service"),
        "selected_exchange": str(support["selected_exchange"]),
        "connector_backend": str(support["connector_backend"]),
        "selected_forex_broker": str(support["selected_forex_broker"]),
        "account_type": str(raw.get("account_type") or cfg.get("account_type") or "Unknown"),
        "mode": str(raw.get("mode") or cfg.get("mode") or "Unknown"),
        "support": support,
        "rate_limit": {
            "active": rate_limit_active,
            "seconds_until_unban": seconds_until_unban,
            "ban_until": ban_until,
        },
        "network": {
            "offline": network_offline,
            "offline_since": network_offline_since,
            "offline_hits": max(0, int(network_offline_hits)),
        },
        "last_error": last_error,
        "attention": attention,
    }
    if order_audit_raw:
        payload["order_audit"] = redact_value(order_audit_raw)
    return redact_value(payload)


@dataclass(frozen=True, slots=True)
class BotStatusSnapshot:
    state: str
    lifecycle_phase: str
    requested_action: str
    close_positions_requested: bool
    status_message: str
    last_transition_at: str
    service_mode: str
    generated_at: str
    api_enabled: bool
    docker_required: bool
    runtime_source: str
    active_engine_count: int
    account_type: str
    mode: str
    selected_exchange: str
    connector_backend: str
    connector_health: str
    exchange_connector: dict[str, object]
    operational_health: str
    operational: dict[str, object]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["exchange_connector"] = redact_value(payload["exchange_connector"])
        payload["operational"] = redact_value(payload["operational"])
        payload["notes"] = list(self.notes)
        return payload


def make_initial_status(
    *,
    state: str = "idle",
    lifecycle_phase: str = "idle",
    requested_action: str = "",
    close_positions_requested: bool = False,
    status_message: str = "Service initialized.",
    last_transition_at: str | None = None,
    runtime_source: str = "service",
    active_engine_count: int = 0,
    account_type: str,
    mode: str,
    selected_exchange: str,
    connector_backend: str,
    operational: dict[str, object] | None = None,
) -> BotStatusSnapshot:
    operational_payload = dict(operational or {})
    operational_health = str(operational_payload.get("health") or "unknown").strip() or "unknown"
    exchange_connector = _mapping_or_empty(operational_payload.get("exchange_connector"))
    connector_health = str(exchange_connector.get("health") or "unknown").strip() or "unknown"
    return BotStatusSnapshot(
        state=str(state or "idle"),
        lifecycle_phase=str(lifecycle_phase or "idle"),
        requested_action=str(requested_action or ""),
        close_positions_requested=bool(close_positions_requested),
        status_message=redact_text(status_message or "Service initialized."),
        last_transition_at=str(last_transition_at or _utc_now_iso()),
        service_mode="local-headless",
        generated_at=_utc_now_iso(),
        api_enabled=False,
        docker_required=False,
        runtime_source=redact_text(runtime_source or "service"),
        active_engine_count=max(0, int(active_engine_count or 0)),
        account_type=str(account_type or "").strip() or "Unknown",
        mode=str(mode or "").strip() or "Unknown",
        selected_exchange=str(selected_exchange or "").strip() or "Unknown",
        connector_backend=str(connector_backend or "").strip() or "Unknown",
        connector_health=connector_health,
        exchange_connector=exchange_connector,
        operational_health=operational_health,
        operational=operational_payload,
        notes=(
            "Service state is available to embedded desktop clients and the optional HTTP API.",
            "Desktop mode remains the primary user path while the service layer grows.",
        ),
    )
