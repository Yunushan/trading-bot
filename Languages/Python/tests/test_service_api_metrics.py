import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.api import FASTAPI_AVAILABLE, create_service_api_app  # noqa: E402
from app.service.api.metrics import (  # noqa: E402
    MAX_METRIC_ROUTE_SERIES,
    MAX_METRIC_SERIES,
    PROMETHEUS_CONTENT_TYPE,
    REQUEST_ID_HEADER,
    ServiceApiMetricsRegistry,
    normalize_route_template,
    resolve_request_id,
    resolve_route_template,
)
from app.service.api_contract import SERVICE_API_ROUTE_PATHS  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402

REPO_ROOT = PYTHON_ROOT.parents[1]
FASTAPI_TESTCLIENT_AVAILABLE = FASTAPI_AVAILABLE and importlib.util.find_spec("httpx2") is not None


def _create_test_client(app, *, raise_server_exceptions: bool = True):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


class ServiceApiMetricsRegistryTests(unittest.TestCase):
    def test_registry_renders_bounded_prometheus_histograms_and_operational_gauges(self):
        registry = ServiceApiMetricsRegistry()
        registry.request_started()
        registry.request_finished(
            method="get",
            route="/api/v1/status",
            status_code=200,
            duration_seconds=0.125,
        )
        text = registry.render_prometheus(
            operational_metrics={
                "runtime_active": True,
                "active_engine_count": 2,
                "log_warning_count": 3,
                "log_error_count": 1,
                "connector_order_circuit_open": True,
                "unresolved_order_intent_count": 4,
            },
            operational_preflight={
                "start": {"allowed": True},
                "orders": {"allowed": False},
                "freshness": {
                    "exchange_connector": {"age_seconds": 12.5, "stale": False},
                    "execution": {"age_seconds": 130.0, "stale": True},
                },
            },
            service_version='1.0"test',
            build_commit="a" * 40,
        )

        self.assertIn(
            'trading_bot_service_http_requests_total{method="GET",route="/api/v1/status",status_code="200"} 1',
            text,
        )
        self.assertIn(
            'trading_bot_service_http_request_duration_seconds_bucket{method="GET",route="/api/v1/status",le="0.1"} 0',
            text,
        )
        self.assertIn(
            'trading_bot_service_http_request_duration_seconds_bucket{method="GET",route="/api/v1/status",le="0.25"} 1',
            text,
        )
        self.assertIn("trading_bot_service_runtime_active 1", text)
        self.assertIn("trading_bot_service_connector_order_circuit_open 1", text)
        self.assertIn(
            'trading_bot_service_operational_snapshot_age_seconds{component="execution"} 130',
            text,
        )
        self.assertIn('version="1.0\\"test"', text)
        self.assertTrue(text.endswith("\n"))

    def test_registry_caps_route_and_series_cardinality_and_reports_overflow(self):
        registry = ServiceApiMetricsRegistry()
        for index in range(MAX_METRIC_ROUTE_SERIES + 32):
            registry.request_finished(
                method="GET",
                route=f"/synthetic/{index}",
                status_code=200,
                duration_seconds=0.01,
            )

        text = registry.render_prometheus()

        self.assertLessEqual(len(registry._known_routes), MAX_METRIC_ROUTE_SERIES - 1)
        self.assertLessEqual(len(registry._requests), MAX_METRIC_SERIES)
        self.assertLessEqual(len(registry._durations), MAX_METRIC_SERIES)
        self.assertIn('route="/synthetic/0"', text)
        self.assertNotIn('route="/synthetic/287"', text)
        self.assertIn('method="OTHER",route="unmatched",status_code="500"', text)
        self.assertIn("trading_bot_service_http_metrics_overflow_total 33", text)

    def test_request_ids_and_route_labels_reject_unbounded_or_sensitive_values(self):
        self.assertEqual("caller-123:worker.4", resolve_request_id("caller-123:worker.4"))
        generated = resolve_request_id("../../bad request id?token=secret")
        self.assertRegex(generated, r"^[0-9a-f]{32}$")
        self.assertEqual("/api/v1/status", normalize_route_template("/api/v1/status"))
        self.assertEqual("unmatched", normalize_route_template("/orders/123?token=secret"))
        self.assertEqual(
            "/api/v1/positions/{position_id}",
            resolve_route_template(
                "/positions/{position_id}",
                "/api/v1/positions/account-secret",
                api_prefixes=("/api/v1", "/api"),
            ),
        )
        self.assertEqual(
            "/livez",
            resolve_route_template("/livez", "/livez", api_prefixes=("/api/v1", "/api")),
        )


@unittest.skipUnless(
    FASTAPI_TESTCLIENT_AVAILABLE,
    "FastAPI TestClient optional dependencies are not installed",
)
class ServiceApiPrometheusHttpTests(unittest.TestCase):
    def test_authenticated_prometheus_route_exports_instrumented_requests_without_query_values(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")
        client = _create_test_client(app)
        headers = {"Authorization": "Bearer token-123", REQUEST_ID_HEADER: "operator-check-1"}

        unauthorized = client.get(SERVICE_API_ROUTE_PATHS["status"])
        self.assertEqual(401, unauthorized.status_code)
        self.assertRegex(unauthorized.headers[REQUEST_ID_HEADER], r"^[0-9a-f]{32}$")

        status_response = client.get(
            SERVICE_API_ROUTE_PATHS["status"],
            params={"probe": "do-not-export-this-value"},
            headers=headers,
        )
        self.assertEqual(200, status_response.status_code)
        self.assertEqual("operator-check-1", status_response.headers[REQUEST_ID_HEADER])

        metrics_path = SERVICE_API_ROUTE_PATHS["prometheus_metrics"]
        self.assertEqual(401, client.get(metrics_path).status_code)
        response = client.get(metrics_path, headers=headers)

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.headers["content-type"].startswith(PROMETHEUS_CONTENT_TYPE))
        self.assertIn("# TYPE trading_bot_service_http_requests_total counter", response.text)
        self.assertIn('route="/api/v1/status"', response.text)
        self.assertIn('status_code="401"', response.text)
        self.assertIn('status_code="200"', response.text)
        self.assertNotIn("do-not-export-this-value", response.text)
        self.assertNotIn("token-123", response.text)

    def test_unhandled_route_failure_is_counted_as_500(self):
        app = create_service_api_app(service=TradingBotService(), api_token="token-123")

        @app.get("/test-only-failure", include_in_schema=False)
        def _test_only_failure():
            raise RuntimeError("expected test failure")

        client = _create_test_client(app, raise_server_exceptions=False)
        response = client.get("/test-only-failure")
        self.assertEqual(500, response.status_code)

        metrics = client.get(
            SERVICE_API_ROUTE_PATHS["prometheus_metrics"],
            headers={"Authorization": "Bearer token-123"},
        ).text
        self.assertIn(
            'trading_bot_service_http_requests_total{method="GET",route="/test-only-failure",status_code="500"} 1',
            metrics,
        )


class PrometheusAlertContractTests(unittest.TestCase):
    def test_checked_in_alert_rules_cover_authoritative_slo_and_safety_thresholds(self):
        path = REPO_ROOT / "docker" / "monitoring" / "prometheus-alerts.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rules = [rule for group in payload["groups"] for rule in group["rules"]]
        by_name = {rule["alert"]: rule for rule in rules}

        self.assertEqual(len(rules), len(by_name))
        self.assertEqual(
            {
                "TradingBotServiceUnavailable",
                "TradingBotServiceReadErrorRateHigh",
                "TradingBotServiceReadLatencyHigh",
                "TradingBotServiceMetricsCardinalityOverflow",
                "TradingBotOperationalSnapshotStale",
                "TradingBotConnectorOrderCircuitOpen",
                "TradingBotUnresolvedOrderIntent",
                "TradingBotOperationalOrderPreflightBlocked",
            },
            set(by_name),
        )
        self.assertRegex(by_name["TradingBotServiceReadErrorRateHigh"]["expr"], re.escape("> 0.001"))
        self.assertRegex(by_name["TradingBotServiceReadLatencyHigh"]["expr"], re.escape("> 0.5"))
        self.assertIn(
            "trading_bot_service_http_metrics_overflow_total",
            by_name["TradingBotServiceMetricsCardinalityOverflow"]["expr"],
        )
        self.assertRegex(by_name["TradingBotOperationalSnapshotStale"]["expr"], re.escape("> 120"))
        error_expr = by_name["TradingBotServiceReadErrorRateHigh"]["expr"]
        self.assertIn('status_code!~"401|403"', error_expr)
        self.assertIn('route!="/api/v1/metrics/prometheus"', error_expr)
        self.assertIn("0.000000001", error_expr)
        self.assertIn(
            "trading_bot_service_operational_snapshot_stale",
            by_name["TradingBotOperationalSnapshotStale"]["expr"],
        )
        self.assertIn(
            "absent(trading_bot_service_operational_snapshot_age_seconds)",
            by_name["TradingBotOperationalSnapshotStale"]["expr"],
        )
        self.assertIn(
            "absent(trading_bot_service_operational_snapshot_stale)",
            by_name["TradingBotOperationalSnapshotStale"]["expr"],
        )
        self.assertTrue(all(rule.get("for") for rule in rules))
        self.assertTrue(all(rule.get("labels", {}).get("severity") in {"warning", "critical"} for rule in rules))


if __name__ == "__main__":
    unittest.main()
