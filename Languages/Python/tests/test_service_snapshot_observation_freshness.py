from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.orders.operational_snapshot import operational_snapshot_issues  # noqa: E402
from app.desktop import service_bridge_snapshot_runtime as bridge  # noqa: E402
from app.desktop.adapters.service_client import EmbeddedDesktopServiceClient  # noqa: E402
from app.service.api import create_service_api_app  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402
from app.service.schemas.positions import build_portfolio_snapshot  # noqa: E402


NOW = 1_780_000_000.0


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


class SnapshotObservationFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.service = TradingBotService(config={"mode": "Live"})
        self.clock = patch.object(self.service._runtime, "_now_iso", return_value=iso(NOW))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.service.set_exchange_connector_snapshot({
            "health": "ok", "state": "ready", "generated_at": iso(NOW),
        })

    def issues(self):
        return operational_snapshot_issues(
            self.service.get_operational_snapshot(), self.service._runtime.config, now_epoch=NOW,
        )

    def observe(self, epoch=NOW):
        self.service.set_account_snapshot(
            total_balance=1000.0, available_balance=900.0, observed_at=iso(epoch),
        )
        self.service.set_portfolio_snapshot(open_position_records={}, observed_at=iso(epoch))

    def test_bootstrap_and_metadata_only_updates_cannot_authorize_orders(self):
        self.service.set_account_snapshot(source="metadata")
        self.service.set_portfolio_snapshot(active_pnl=0.0, closed_position_records=[], source="metadata")
        self.service.replace_config(self.service._runtime.config)
        self.assertEqual("", self.service.get_account_snapshot().generated_at)
        self.assertEqual("", self.service.get_portfolio_snapshot().generated_at)
        self.assertTrue(any("account" in issue for issue in self.issues()))
        self.assertTrue(any("portfolio" in issue for issue in self.issues()))
        self.assertFalse(self.service.get_operational_preflight()["orders"]["allowed"])

    def test_config_refresh_preserves_observation_times_and_staleness(self):
        self.observe(NOW - 901)
        config = self.service._runtime.config
        config["theme"] = "Light"
        self.service.replace_config(config)
        self.assertEqual(iso(NOW - 901), self.service.get_account_snapshot().generated_at)
        self.assertEqual(iso(NOW - 901), self.service.get_portfolio_snapshot().generated_at)
        self.assertIn("account snapshot is stale", self.issues())
        self.assertIn("portfolio snapshot is stale", self.issues())

    def test_metadata_and_partial_updates_do_not_reage_cached_observations(self):
        self.observe(NOW - 901)
        self.service.set_account_snapshot(total_balance=1100.0)
        self.service.set_portfolio_snapshot(active_pnl=10.0, total_balance=1100.0)
        self.assertEqual(iso(NOW - 901), self.service.get_account_snapshot().generated_at)
        self.assertEqual(iso(NOW - 901), self.service.get_portfolio_snapshot().generated_at)
        self.assertTrue(self.issues())

    def test_complete_observations_authorize_even_zero_balance_and_flat_portfolio(self):
        self.service.set_account_snapshot(total_balance=0.0, available_balance=0.0)
        self.service.set_portfolio_snapshot(open_position_records={})
        self.assertEqual(iso(NOW), self.service.get_account_snapshot().generated_at)
        self.assertEqual(iso(NOW), self.service.get_portfolio_snapshot().generated_at)
        self.assertEqual([], self.issues())
        self.assertTrue(self.service.get_operational_preflight()["orders"]["allowed"])

    def test_missing_or_invalid_observations_invalidate_previous_freshness(self):
        for bad in (None, "bad", float("nan"), float("inf"), True):
            with self.subTest(balance=bad):
                self.observe()
                self.service.set_account_snapshot(total_balance=bad, available_balance=900.0)
                self.assertEqual("", self.service.get_account_snapshot().generated_at)
                self.assertTrue(self.issues())
        for bad in (None, [], {"bad": None}):
            with self.subTest(positions=bad):
                self.observe()
                self.service.set_portfolio_snapshot(open_position_records=bad)
                self.assertEqual("", self.service.get_portfolio_snapshot().generated_at)
                self.assertTrue(self.issues())

    def test_explicit_old_missing_and_future_timestamps_never_become_receipt_time(self):
        for stamp in (iso(NOW - 901), "", None, "bad", iso(NOW + 60)):
            with self.subTest(observed_at=stamp):
                self.service.set_account_snapshot(total_balance=1.0, available_balance=1.0, observed_at=stamp)
                self.service.set_portfolio_snapshot(open_position_records={}, observed_at=stamp)
                self.assertNotEqual(iso(NOW), self.service.get_account_snapshot().generated_at)
                self.assertNotEqual(iso(NOW), self.service.get_portfolio_snapshot().generated_at)
                self.assertTrue(self.issues())

    def test_malformed_position_rows_invalidate_the_whole_observation_and_preserve_last_known(self):
        good = {"symbol": "BTCUSDT", "side_key": "L", "data": {"qty": "0.1", "mark": 100.0}}
        invalid = [{}, {"data": {}}, {**good, "data": None}]
        for key in ("symbol", "side_key"):
            for value in (None, "", "Unknown", True, 42, {}, "BTC USDT"):
                invalid.append({**good, key: value})
        for value in (None, "", "bad", -1, True, float("nan"), float("inf"), "-Infinity"):
            invalid.append({**good, "data": {"qty": value}})
        invalid.append({**good, "data": {"qty": 1, "symbol": "ETHUSDT"}})
        for key in ("mark", "size_usdt", "margin_usdt", "pnl_value", "roi_percent", "leverage"):
            invalid.append({**good, "data": {"qty": 1, key: "NaN"}})
        for bad in invalid:
            with self.subTest(record=bad):
                self.observe()
                before = self.service.set_portfolio_snapshot(open_position_records={"known": good})
                snapshot = self.service.set_portfolio_snapshot(open_position_records={"known": good, "bad": bad})
                self.assertEqual(before.positions, snapshot.positions)
                self.assertEqual("", snapshot.generated_at)
                self.assertTrue(any("portfolio" in issue for issue in self.issues()))
                self.assertFalse(self.service.get_operational_preflight()["orders"]["allowed"])
                self.service.set_portfolio_snapshot(active_pnl=0.0)
                self.assertEqual("", self.service.get_portfolio_snapshot().generated_at)
                repaired = self.service.set_portfolio_snapshot(open_position_records={"known": good})
                self.assertEqual(iso(NOW), repaired.generated_at)
                self.assertEqual([], self.issues())

    def test_valid_position_shapes_and_confirmed_empty_can_reestablish_freshness(self):
        self.observe()
        for side in ("L", "S", "SPOT"):
            for quantity in (0.0, "0.1", 1):
                for nested in (False, True):
                    with self.subTest(side=side, quantity=quantity, nested=nested):
                        identity = {"symbol": "BTCUSDT", "side_key": side}
                        record = {"data": {"qty": quantity, **identity}} if nested else {**identity, "data": {"qty": quantity}}
                        snapshot = self.service.set_portfolio_snapshot(open_position_records={"position": record})
                        self.assertEqual(iso(NOW), snapshot.generated_at)
                        self.assertEqual(float(quantity), snapshot.positions[0].quantity)
                        self.assertEqual([], self.issues())
        snapshot = self.service.set_portfolio_snapshot(open_position_records={})
        self.assertEqual(0, snapshot.open_position_count)
        self.assertEqual(iso(NOW), snapshot.generated_at)

    def test_schema_builder_cannot_grant_freshness_to_malformed_records(self):
        for records in (None, [], {"bad": {}}, {"bad": None}, {"bad": {"symbol": "BTCUSDT", "side_key": "L", "data": {"qty": "NaN"}}}):
            with self.subTest(records=records):
                snapshot = build_portfolio_snapshot(config={}, open_position_records=records, generated_at=iso(NOW))
                self.assertEqual("", snapshot.generated_at)
                for position in snapshot.positions:
                    self.assertIsNone(position.quantity)

    def test_http_invalid_portfolio_does_not_replace_last_known_positions_or_allow_orders(self):
        from fastapi.testclient import TestClient

        self.observe()
        good = {"symbol": "BTCUSDT", "side_key": "L", "data": {"qty": 0.1}}
        with TestClient(create_service_api_app(self.service, api_token="unit-token")) as client:
            headers = {"Authorization": "Bearer unit-token"}
            response = client.put("/api/v1/portfolio", json={"open_position_records": {"known": good}}, headers=headers)
            self.assertEqual(200, response.status_code)
            before = response.json()["positions"]
            for bad in ({}, {**good, "data": {"qty": "NaN"}}, {**good, "data": {"qty": True}}):
                response = client.put("/api/v1/portfolio", json={"open_position_records": {"bad": bad}}, headers=headers)
                self.assertEqual(200, response.status_code)
                self.assertEqual("", response.json()["generated_at"])
                self.assertEqual(before, response.json()["positions"])
                self.assertTrue(self.issues())
            response = client.put("/api/v1/portfolio", json={"open_position_records": {}}, headers=headers)
            self.assertEqual(iso(NOW), response.json()["generated_at"])
            self.assertEqual([], response.json()["positions"])

    def test_exchange_identity_change_requires_new_observations(self):
        for key, value in (("mode", "Demo/Testnet"), ("account_type", "SPOT"), ("api_key", "different-key")):
            with self.subTest(key=key):
                self.observe()
                config = self.service._runtime.config
                config[key] = value
                self.service.replace_config(config)
                self.assertEqual("", self.service.get_account_snapshot().generated_at)
                self.assertEqual("", self.service.get_portfolio_snapshot().generated_at)

    def test_http_metadata_updates_preserve_omission_and_observation_timestamp(self):
        from fastapi.testclient import TestClient

        with TestClient(create_service_api_app(self.service, api_token="unit-token")) as client:
            headers = {"Authorization": "Bearer unit-token"}
            for route, payload in (
                ("account", {"total_balance": 1000.0, "available_balance": 900.0}),
                ("portfolio", {"open_position_records": {}}),
            ):
                response = client.put(f"/api/v1/{route}", json={**payload, "observed_at": iso(NOW - 901)}, headers=headers)
                self.assertEqual(200, response.status_code)
                self.assertEqual(iso(NOW - 901), response.json()["generated_at"])
                response = client.put(f"/api/v1/{route}", json={"source": "metadata"}, headers=headers)
                self.assertEqual(iso(NOW - 901), response.json()["generated_at"])
            self.assertTrue(self.issues())

    def test_desktop_portfolio_republish_preserves_original_observation(self):
        self.observe()
        owner = SimpleNamespace(
            _open_position_records={}, _closed_position_records=[], _closed_trade_registry={},
            _positions_observed_at=iso(NOW - 901),
            _compute_global_pnl_totals=lambda: (0.0, 0.0, 0.0, 0.0),
        )
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: self.service)
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            bridge._sync_service_portfolio_snapshot(owner)
            bridge._sync_service_portfolio_snapshot(owner, source="desktop-pnl")
        self.assertEqual(iso(NOW - 901), self.service.get_portfolio_snapshot().generated_at)
        self.assertIn("portfolio snapshot is stale", self.issues())

    def test_desktop_bootstrap_cannot_publish_empty_cache_as_fresh_positions(self):
        owner = SimpleNamespace(_compute_global_pnl_totals=lambda: (None, None, None, None))
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: self.service)
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            bridge._sync_service_portfolio_snapshot(owner, source="desktop-bootstrap")
        self.assertEqual("", self.service.get_portfolio_snapshot().generated_at)


if __name__ == "__main__":
    unittest.main()
