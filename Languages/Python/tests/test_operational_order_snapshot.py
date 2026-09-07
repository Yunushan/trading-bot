from __future__ import annotations

import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.core.strategy.orders.operational_snapshot import operational_snapshot_issues  # noqa: E402
from app.core.strategy.orders.strategy_signal_order_submit_runtime import (  # noqa: E402
    _evaluate_operational_order_guard,
)
from app.service.runtime import TradingBotService  # noqa: E402


NOW = 1_780_000_000.0


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _snapshot() -> dict:
    return {
        "health": "ok",
        "generated_at": _iso(NOW),
        "freshness": {
            key: {
                "stale": False,
                "generated_at": _iso(NOW - 1),
                "age_seconds": 1.0,
                "max_age_seconds": limit,
            }
            for key, limit in (("exchange_connector", 120.0), ("account", 300.0), ("portfolio", 300.0))
        },
    }


class OperationalOrderSnapshotTests(unittest.TestCase):
    def test_accepts_complete_fresh_snapshots(self):
        for health in ("ok", "warning"):
            for timestamp in (_iso(NOW - 1), _iso(NOW - 1).replace("+00:00", "Z"), NOW - 1, str(NOW - 1)):
                with self.subTest(health=health, timestamp=timestamp):
                    snapshot = _snapshot()
                    snapshot["health"] = health
                    snapshot["freshness"]["account"]["generated_at"] = timestamp
                    self.assertEqual([], operational_snapshot_issues(snapshot, {}, now_epoch=NOW))

    def test_rejects_unavailable_and_malformed_snapshots(self):
        for snapshot in (None, {}, [], "ok", False, {"health": "ok"}, {"freshness": {}}, {"health": ["ok"]}):
            with self.subTest(snapshot=snapshot):
                self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
        for field in ("health", "generated_at", "freshness"):
            snapshot = _snapshot()
            del snapshot[field]
            with self.subTest(missing=field):
                self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
        for health in ("error", "unknown", "", None, True):
            snapshot = _snapshot()
            snapshot["health"] = health
            with self.subTest(health=health):
                self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))

    def test_requires_complete_valid_freshness_for_every_critical_component(self):
        invalid_fields = {
            "stale": (None, "false", 0, [], True),
            "age_seconds": (None, "bad", True, -1, float("nan"), float("inf")),
            "max_age_seconds": (None, "bad", True, 0, -1, float("nan"), float("inf")),
            "generated_at": (None, "bad", True, -1, "NaN", "inf", "2026-01-01T00:00:00"),
        }
        for component in _snapshot()["freshness"]:
            for item in (None, [], "fresh", {}):
                snapshot = _snapshot()
                snapshot["freshness"][component] = item
                with self.subTest(component=component, item=item):
                    self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
            for field, values in invalid_fields.items():
                snapshot = _snapshot()
                del snapshot["freshness"][component][field]
                with self.subTest(component=component, missing=field):
                    self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
                for value in values:
                    snapshot = _snapshot()
                    snapshot["freshness"][component][field] = value
                    with self.subTest(component=component, field=field, value=value):
                        self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))

    def test_reages_cached_snapshots_instead_of_trusting_stale_flag(self):
        snapshot = _snapshot()
        self.assertEqual([], operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
        self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW + 121))
        for component in snapshot["freshness"]:
            for field, value in (("generated_at", _iso(NOW - 301)), ("age_seconds", 301.0)):
                snapshot = _snapshot()
                snapshot["freshness"][component][field] = value
                with self.subTest(component=component, field=field):
                    self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
        snapshot = _snapshot()
        snapshot["generated_at"] = _iso(NOW - 301)
        self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))

    def test_rejects_future_timestamps_but_tolerates_small_clock_skew(self):
        for key in (None, "exchange_connector", "account", "portfolio"):
            snapshot = _snapshot()
            item = snapshot if key is None else snapshot["freshness"][key]
            item["generated_at"] = _iso(NOW + 5)
            with self.subTest(component=key):
                self.assertEqual([], operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
                item["generated_at"] = _iso(NOW + 6)
                self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))

    def test_remote_limit_cannot_relax_configured_limit(self):
        snapshot = _snapshot()
        snapshot["freshness"]["account"]["max_age_seconds"] = 1000.0
        snapshot["freshness"]["account"]["age_seconds"] = 400.0
        self.assertTrue(operational_snapshot_issues(snapshot, {}, now_epoch=NOW))
        config = {"operational_account_snapshot_stale_seconds": 500.0}
        self.assertEqual([], operational_snapshot_issues(snapshot, config, now_epoch=NOW))
        snapshot["freshness"]["account"]["max_age_seconds"] = 300.0
        self.assertTrue(operational_snapshot_issues(snapshot, config, now_epoch=NOW))

    def test_rejects_invalid_configured_limits_and_clock(self):
        for value in (None, True, 0, -1, "bad", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertTrue(operational_snapshot_issues(
                    _snapshot(), {"operational_account_snapshot_stale_seconds": value}, now_epoch=NOW,
                ))
        for now in (float("nan"), float("inf"), -1):
            with self.subTest(now=now):
                self.assertTrue(operational_snapshot_issues(_snapshot(), {}, now_epoch=now))

    def test_service_published_snapshot_matches_submission_contract(self):
        service = TradingBotService()
        service.set_account_snapshot(total_balance=1000.0, available_balance=900.0, source="unit-test")
        service.set_portfolio_snapshot(open_position_records={}, source="unit-test")
        now = datetime.now(timezone.utc).timestamp()
        service.set_exchange_connector_snapshot({
            "health": "ok", "state": "ready", "generated_at": _iso(now),
        })
        snapshot = service.get_operational_snapshot()
        self.assertEqual([], operational_snapshot_issues(snapshot, {}, now_epoch=now))
        missing = copy.deepcopy(snapshot)
        del missing["freshness"]["account"]["generated_at"]
        self.assertTrue(operational_snapshot_issues(missing, {}, now_epoch=now))

    def test_missing_provider_cannot_disable_live_guard(self):
        for config_mode, wrapper_mode in (("Live", "Live"), ("Demo", "Live"), ("Live", "Demo"), (None, "Live")):
            with self.subTest(config_mode=config_mode, wrapper_mode=wrapper_mode):
                engine = SimpleNamespace(config={"mode": config_mode})
                allowed, message, level, _ = _evaluate_operational_order_guard(
                    engine, SimpleNamespace(mode=wrapper_mode),
                )
                self.assertFalse(allowed)
                self.assertIn("snapshot is unavailable", message)
                self.assertEqual("error", level)


if __name__ == "__main__":
    unittest.main()
