"""Bounded HTTP and operational metrics for the service API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import re
import secrets
import threading
import time

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
REQUEST_ID_HEADER = "X-Request-ID"

_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_ROUTE_PATTERN = re.compile(r"/[A-Za-z0-9_./{}:-]{0,199}")
_METHOD_PATTERN = re.compile(r"[A-Z]{1,16}")
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, math.inf)
_FRESHNESS_COMPONENTS = ("exchange_connector", "execution", "account", "portfolio")
MAX_METRIC_ROUTE_SERIES = 256
MAX_METRIC_SERIES = 4096


def resolve_request_id(candidate: str | None) -> str:
    """Accept a safe caller correlation ID or return a random opaque ID."""

    value = str(candidate or "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return secrets.token_hex(16)


def normalize_route_template(candidate: str | None) -> str:
    """Bound route labels to registered templates and a single fallback value."""

    value = str(candidate or "").strip()
    return value if _ROUTE_PATTERN.fullmatch(value) else "unmatched"


def resolve_route_template(
    route_template: str | None,
    request_path: str | None,
    *,
    api_prefixes: tuple[str, ...] = (),
) -> str:
    """Restore an API router prefix without copying dynamic URL values."""

    route = str(route_template or "").strip()
    path = str(request_path or "").strip()
    for prefix in api_prefixes:
        normalized_prefix = str(prefix or "").rstrip("/")
        if not normalized_prefix:
            continue
        if path == normalized_prefix or path.startswith(f"{normalized_prefix}/"):
            if route and not route.startswith(normalized_prefix):
                route = f"{normalized_prefix}{route if route.startswith('/') else f'/{route}'}"
            break
    return normalize_route_template(route)


def _normalize_method(candidate: str | None) -> str:
    value = str(candidate or "").strip().upper()
    return value if _METHOD_PATTERN.fullmatch(value) else "OTHER"


def _normalize_status_code(candidate: object) -> int:
    if not isinstance(candidate, (str, int, float)):
        return 500
    try:
        value = int(candidate)
    except (TypeError, ValueError):
        return 500
    return value if 100 <= value <= 599 else 500


def _finite_non_negative(candidate: object) -> float | None:
    if isinstance(candidate, bool) or not isinstance(candidate, (str, int, float)):
        return None
    try:
        value = float(candidate)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0.0 else None


def _non_negative_int(candidate: object) -> int:
    if isinstance(candidate, bool):
        return int(candidate)
    if not isinstance(candidate, (str, int, float)):
        return 0
    try:
        return max(0, int(candidate))
    except (TypeError, ValueError):
        return 0


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**values: object) -> str:
    if not values:
        return ""
    rendered = ",".join(f'{key}="{_escape_label(value)}"' for key, value in values.items())
    return "{" + rendered + "}"


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf"
    return format(value, ".12g")


@dataclass
class _DurationSeries:
    bucket_counts: list[int]
    count: int = 0
    total_seconds: float = 0.0


class ServiceApiMetricsRegistry:
    """Thread-safe, process-local Prometheus metric registry with bounded labels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._in_progress = 0
        self._requests: dict[tuple[str, str, int], int] = {}
        self._durations: dict[tuple[str, str], _DurationSeries] = {}
        self._known_routes: set[str] = set()
        self._metric_overflow_count = 0

    def request_started(self) -> None:
        with self._lock:
            self._in_progress += 1

    def request_finished(
        self,
        *,
        method: str | None,
        route: str | None,
        status_code: object,
        duration_seconds: object,
    ) -> None:
        normalized_method = _normalize_method(method)
        normalized_route = normalize_route_template(route)
        normalized_status = _normalize_status_code(status_code)
        normalized_duration = _finite_non_negative(duration_seconds)
        if normalized_duration is None:
            normalized_duration = 0.0

        with self._lock:
            self._in_progress = max(0, self._in_progress - 1)
            normalized_route, route_overflowed = self._bound_route_locked(normalized_route)
            overflowed = route_overflowed
            if route_overflowed:
                normalized_method = "OTHER"
                normalized_status = 500
            request_key = (normalized_method, normalized_route, normalized_status)
            duration_key = (normalized_method, normalized_route)
            if (
                request_key not in self._requests
                and len(self._requests) >= MAX_METRIC_SERIES - 1
            ) or (
                duration_key not in self._durations
                and len(self._durations) >= MAX_METRIC_SERIES - 1
            ):
                normalized_method = "OTHER"
                normalized_route = "unmatched"
                normalized_status = 500
                request_key = (normalized_method, normalized_route, normalized_status)
                duration_key = (normalized_method, normalized_route)
                overflowed = True
            if overflowed:
                self._metric_overflow_count += 1
            self._requests[request_key] = self._requests.get(request_key, 0) + 1
            series = self._durations.get(duration_key)
            if series is None:
                series = _DurationSeries(bucket_counts=[0] * len(_DURATION_BUCKETS))
                self._durations[duration_key] = series
            series.count += 1
            series.total_seconds += normalized_duration
            for index, upper_bound in enumerate(_DURATION_BUCKETS):
                if normalized_duration <= upper_bound:
                    series.bucket_counts[index] += 1

    def _bound_route_locked(self, route: str) -> tuple[str, bool]:
        if route == "unmatched" or route in self._known_routes:
            return route, False
        if len(self._known_routes) >= MAX_METRIC_ROUTE_SERIES - 1:
            return "unmatched", True
        self._known_routes.add(route)
        return route, False

    def render_prometheus(
        self,
        *,
        operational_metrics: Mapping[str, object] | None = None,
        operational_preflight: Mapping[str, object] | None = None,
        service_version: str = "",
        build_commit: str = "",
    ) -> str:
        with self._lock:
            in_progress = self._in_progress
            started_at = self._started_at
            metric_overflow_count = self._metric_overflow_count
            requests = dict(self._requests)
            durations = {
                key: (list(value.bucket_counts), value.count, value.total_seconds)
                for key, value in self._durations.items()
            }

        now = time.time()
        lines = [
            "# HELP trading_bot_service_build_info Static service build information.",
            "# TYPE trading_bot_service_build_info gauge",
            (
                "trading_bot_service_build_info"
                f'{_labels(version=service_version or "unknown", build_commit=build_commit or "unknown")} 1'
            ),
            "# HELP trading_bot_service_process_start_time_seconds Unix timestamp when this service process started.",
            "# TYPE trading_bot_service_process_start_time_seconds gauge",
            f"trading_bot_service_process_start_time_seconds {_number(started_at)}",
            "# HELP trading_bot_service_process_uptime_seconds Seconds since this service process started.",
            "# TYPE trading_bot_service_process_uptime_seconds gauge",
            f"trading_bot_service_process_uptime_seconds {_number(max(0.0, now - started_at))}",
            "# HELP trading_bot_service_http_requests_in_progress HTTP requests currently being served.",
            "# TYPE trading_bot_service_http_requests_in_progress gauge",
            f"trading_bot_service_http_requests_in_progress {in_progress}",
            "# HELP trading_bot_service_http_requests_total Completed HTTP requests.",
            "# TYPE trading_bot_service_http_requests_total counter",
        ]
        lines.extend(
            [
                "# HELP trading_bot_service_http_metrics_overflow_total HTTP metric updates folded into the bounded overflow series.",
                "# TYPE trading_bot_service_http_metrics_overflow_total counter",
                f"trading_bot_service_http_metrics_overflow_total {metric_overflow_count}",
            ]
        )
        for (method, route, status_code), count in sorted(requests.items()):
            lines.append(
                "trading_bot_service_http_requests_total"
                f'{_labels(method=method, route=route, status_code=status_code)} {count}'
            )

        lines.extend(
            [
                "# HELP trading_bot_service_http_request_duration_seconds HTTP request duration in seconds.",
                "# TYPE trading_bot_service_http_request_duration_seconds histogram",
            ]
        )
        for (method, route), (bucket_counts, count, total_seconds) in sorted(durations.items()):
            for upper_bound, bucket_count in zip(_DURATION_BUCKETS, bucket_counts):
                lines.append(
                    "trading_bot_service_http_request_duration_seconds_bucket"
                    f'{_labels(method=method, route=route, le=_number(upper_bound))} {bucket_count}'
                )
            lines.append(
                "trading_bot_service_http_request_duration_seconds_count"
                f"{_labels(method=method, route=route)} {count}"
            )
            lines.append(
                "trading_bot_service_http_request_duration_seconds_sum"
                f"{_labels(method=method, route=route)} {_number(total_seconds)}"
            )

        self._append_operational_metrics(lines, operational_metrics or {}, operational_preflight or {})
        return "\n".join(lines) + "\n"

    @staticmethod
    def _append_operational_metrics(
        lines: list[str],
        metrics: Mapping[str, object],
        preflight: Mapping[str, object],
    ) -> None:
        gauges = (
            ("runtime_active", "Whether the trading runtime is active.", int(bool(metrics.get("runtime_active")))),
            ("active_engine_count", "Number of active strategy engines.", _non_negative_int(metrics.get("active_engine_count"))),
            ("log_warning_count", "Warnings retained in the operational log snapshot.", _non_negative_int(metrics.get("log_warning_count"))),
            ("log_error_count", "Errors retained in the operational log snapshot.", _non_negative_int(metrics.get("log_error_count"))),
            (
                "connector_order_circuit_open",
                "Whether the connector order circuit breaker is open.",
                int(bool(metrics.get("connector_order_circuit_open"))),
            ),
            (
                "unresolved_order_intent_count",
                "Number of unresolved connector order intents.",
                _non_negative_int(metrics.get("unresolved_order_intent_count")),
            ),
        )
        for suffix, help_text, value in gauges:
            name = f"trading_bot_service_{suffix}"
            lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"))

        for key, help_text in (
            ("start", "Whether operational preflight allows runtime start."),
            ("orders", "Whether operational preflight allows order submission."),
        ):
            payload = preflight.get(key)
            allowed = bool(payload.get("allowed")) if isinstance(payload, Mapping) else False
            name = f"trading_bot_service_operational_preflight_{key}_allowed"
            lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {int(allowed)}"))

        lines.extend(
            (
                "# HELP trading_bot_service_operational_snapshot_age_seconds Age of each operational snapshot.",
                "# TYPE trading_bot_service_operational_snapshot_age_seconds gauge",
                "# HELP trading_bot_service_operational_snapshot_stale Whether each operational snapshot is stale.",
                "# TYPE trading_bot_service_operational_snapshot_stale gauge",
            )
        )
        freshness = preflight.get("freshness")
        if not isinstance(freshness, Mapping):
            return
        for component in _FRESHNESS_COMPONENTS:
            payload = freshness.get(component)
            if not isinstance(payload, Mapping):
                continue
            age_seconds = _finite_non_negative(payload.get("age_seconds"))
            if age_seconds is not None:
                lines.append(
                    "trading_bot_service_operational_snapshot_age_seconds"
                    f"{_labels(component=component)} {_number(age_seconds)}"
                )
            lines.append(
                "trading_bot_service_operational_snapshot_stale"
                f"{_labels(component=component)} {int(bool(payload.get('stale')))}"
            )
