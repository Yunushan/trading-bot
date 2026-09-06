from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import service_bridge_snapshot_runtime as bridge  # noqa: E402
from app.desktop.adapters.service_client import EmbeddedDesktopServiceClient  # noqa: E402
from app.gui.positions import build_runtime, record_build_runtime, table_render_prepare_runtime, worker_runtime  # noqa: E402
from app.integrations.exchanges.binance.account import account_balance_runtime  # noqa: E402
from app.gui.runtime.window.portfolio_runtime import _update_positions_balance_labels  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


OLD = "2020-01-01T00:00:00+00:00"


class DesktopSnapshotObservationTests(unittest.TestCase):
    def worker(self, account="FUTURES", positions=None):
        worker = worker_runtime._PositionsWorker("unit-key", "unit-secret", "Live", account)
        wrapper = Mock()
        wrapper.list_open_futures_positions.return_value = [] if positions is None else positions
        wrapper.get_balances.return_value = [] if positions is None else positions
        wrapper.get_last_price.return_value = 100.0
        wrapper.get_spot_position_cost.return_value = None
        wrapper.get_spot_symbol_filters.return_value = {}
        worker._wrapper = wrapper
        return worker

    def futures_row(self, symbol="BTCUSDT"):
        return {
            "symbol": symbol, "positionAmt": "0.1", "positionSide": "LONG",
            "markPrice": "100", "entryPrice": "90", "notional": "10",
            "leverage": "2", "unRealizedProfit": "1",
        }

    def publish_owner(self, worker):
        service = TradingBotService(config={"mode": "Live"})
        owner = SimpleNamespace(
            _pos_worker=worker, service=service, _open_position_records={}, _pos_symbol_filter=None,
            _compute_global_pnl_totals=lambda: (0.0, 0.0, 0.0, 0.0),
            _position_stop_loss_enabled=lambda *_args: False, log=Mock(),
        )
        owner._update_position_history = lambda records: setattr(owner, "_open_position_records", records)
        owner._sync_service_portfolio_snapshot = lambda **kwargs: bridge._sync_service_portfolio_snapshot(owner, **kwargs)
        owner._render_positions_table = lambda: owner._sync_service_portfolio_snapshot()
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: service)
        return owner, client

    def test_valid_nonempty_futures_and_spot_observations_reach_the_service(self):
        for account, rows in (
            ("FUTURES", [self.futures_row()]),
            ("SPOT", [{"asset": "BTC", "free": "0.1", "locked": "0"}]),
        ):
            with self.subTest(account=account):
                worker = self.worker(account, rows)
                owner, client = self.publish_owner(worker)
                emitted, errors = [], []
                worker.positions_ready.connect(lambda *args: emitted.append(args))
                worker.error.connect(errors.append)
                worker._tick()
                self.assertEqual([], errors)
                self.assertEqual(1, len(emitted))
                self.assertIn("roi_percent", emitted[0][0][0])
                with patch.object(bridge, "_ensure_service_client", return_value=client):
                    build_runtime._gui_on_positions_ready(owner, *emitted[0])
                owner.log.assert_not_called()
                snapshot = owner.service.get_portfolio_snapshot()
                self.assertEqual(1, snapshot.open_position_count)
                self.assertEqual("BTCUSDT", snapshot.positions[0].symbol)
                self.assertEqual(0.1, snapshot.positions[0].quantity)
                self.assertTrue(snapshot.generated_at)

    def test_whole_position_observation_fails_when_any_row_is_malformed(self):
        cases = [{}, {"symbol": "BTCUSDT"}, dict(self.futures_row(), positionSide="SHORT")]
        for field, values in (
            ("symbol", (None, "", 1, "UNKNOWN", "BTC USDT")),
            ("positionAmt", (None, "", "bad", True, float("nan"), float("inf"))),
            ("markPrice", ("bad", True, float("nan"), float("inf"))),
        ):
            cases.extend(dict(self.futures_row(), **{field: value}) for value in values)
        for bad in cases:
            with self.subTest(bad=bad):
                worker = self.worker(positions=[self.futures_row("ETHUSDT"), bad])
                emitted, failures = [], []
                worker.positions_ready.connect(lambda *args: emitted.append(args))
                worker.observation_failed.connect(failures.append)
                worker._tick()
                worker._tick()
                self.assertEqual([], emitted)
                self.assertEqual([0, 0], failures)
                self.assertFalse(worker._busy)

    def test_spot_adapter_cannot_hide_a_bad_row_before_the_worker_validates(self):
        worker = self.worker("SPOT")
        wrapper = worker._wrapper
        wrapper.account_type = "SPOT"
        wrapper._spot_account_dict.return_value = {"balances": [
            {"asset": "BTC", "free": "0.1", "locked": "0"},
            {"asset": "ETH", "free": "bad", "locked": "0"},
        ]}
        wrapper.get_balances.side_effect = lambda: account_balance_runtime.get_balances(wrapper)
        emitted, failures = [], []
        worker.positions_ready.connect(lambda *args: emitted.append(args))
        worker.observation_failed.connect(failures.append)
        worker._tick()
        self.assertEqual([], emitted)
        self.assertEqual([0], failures)

    def test_failed_refresh_keeps_positions_but_removes_service_freshness(self):
        worker = self.worker(positions=[self.futures_row()])
        owner, client = self.publish_owner(worker)
        worker.positions_ready.connect(lambda *args: build_runtime._gui_on_positions_ready(owner, *args))
        worker.observation_failed.connect(lambda generation: build_runtime._gui_on_positions_observation_failed(owner, generation))
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            worker._tick()
            before = owner.service.get_portfolio_snapshot()
            self.assertTrue(before.generated_at)
            worker._wrapper.list_open_futures_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "bad"}]
            worker._tick()
            after = owner.service.get_portfolio_snapshot()
        self.assertEqual(before.positions, after.positions)
        self.assertEqual("", after.generated_at)
        self.assertFalse(owner.service.get_operational_preflight()["orders"]["allowed"])

    def test_reconfiguration_during_fetch_discards_old_result_and_old_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                worker = self.worker()
                def fetch(**kwargs):
                    worker.configure(api_key="new-unit-key")
                    if fail:
                        raise RuntimeError("old failure")
                    return []
                worker._wrapper.list_open_futures_positions.side_effect = fetch
                emitted, failures = [], []
                worker.positions_ready.connect(lambda *args: emitted.append(args))
                worker.observation_failed.connect(failures.append)
                worker._tick()
                self.assertEqual([], emitted)
                self.assertEqual([], failures)
                self.assertFalse(worker._busy)
                worker._wrapper = Mock()
                worker._wrapper.list_open_futures_positions.return_value = []
                worker._tick()
                self.assertEqual(1, len(emitted))
                self.assertEqual(1, emitted[0][3])

    def test_queued_result_and_failure_cannot_replace_new_generation(self):
        for stop in (False, True):
            with self.subTest(stop=stop):
                worker = self.worker()
                emitted = []
                worker.positions_ready.connect(lambda *args: emitted.append(args))
                worker._tick()
                if stop:
                    worker.stop_timer()
                else:
                    worker.configure(api_key="new-key")
                owner = SimpleNamespace(
                    _pos_worker=worker, _positions_observed_at=OLD,
                    _update_position_history=Mock(), _render_positions_table=Mock(),
                    _sync_service_portfolio_snapshot=Mock(), log=Mock(),
                )
                build_runtime._gui_on_positions_ready(owner, *emitted[0])
                build_runtime._gui_on_positions_observation_failed(owner, emitted[0][3])
                self.assertEqual(OLD, owner._positions_observed_at)
                owner._update_position_history.assert_not_called()
                owner._sync_service_portfolio_snapshot.assert_not_called()

    def test_failed_record_conversion_cannot_publish_a_partial_portfolio(self):
        for publisher in (build_runtime, record_build_runtime):
            with self.subTest(publisher=publisher.__name__):
                owner = SimpleNamespace(
                    _positions_observed_at=OLD, _open_position_records={},
                    _update_position_history=Mock(), _render_positions_table=Mock(),
                    _sync_service_portfolio_snapshot=Mock(), log=Mock(),
                )
                with patch.object(build_runtime, "_seed_positions_map_from_rows", return_value={}):
                    publisher._gui_on_positions_ready(owner, [{"symbol": "BTCUSDT", "side_key": "L", "qty": 1}], "FUTURES", OLD)
                self.assertEqual("", owner._positions_observed_at)
                owner._update_position_history.assert_not_called()
                owner._render_positions_table.assert_not_called()
                owner._sync_service_portfolio_snapshot.assert_called_once()

    def test_symbol_filter_changes_only_display_not_account_snapshot(self):
        worker = self.worker(positions=[self.futures_row(), self.futures_row("ETHUSDT")])
        wrapper = worker._wrapper
        worker.configure(symbols=["BTCUSDT"])
        worker._wrapper = wrapper
        emitted = []
        worker.positions_ready.connect(lambda *args: emitted.append(args))
        worker._tick()
        self.assertEqual({"BTCUSDT", "ETHUSDT"}, {row["symbol"] for row in emitted[0][0]})
        owner, client = self.publish_owner(worker)
        owner._pos_symbol_filter = ["BTCUSDT"]
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            build_runtime._gui_on_positions_ready(owner, *emitted[0])
        self.assertEqual(2, owner.service.get_portfolio_snapshot().open_position_count)
        for view in ("per_trade", "cumulative"):
            with self.subTest(view=view):
                owner._positions_records_per_trade = lambda opened, closed: list(opened.values()) + closed
                with patch.object(
                    table_render_prepare_runtime.table_render_state_runtime,
                    "_positions_records_cumulative", side_effect=lambda _owner, opened, closed: opened + closed,
                ):
                    display = table_render_prepare_runtime._resolve_display_records(owner, owner._open_position_records, [], view)
                self.assertEqual(["BTCUSDT"], [row["symbol"] for row in display])
                self.assertEqual(2, len(owner._open_position_records))

    def test_balance_repaint_and_failure_keep_original_observation_time(self):
        service = TradingBotService(config={"mode": "Live"})
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: service)
        owner = SimpleNamespace()
        owner._sync_service_account_snapshot = lambda **kwargs: bridge._sync_service_account_snapshot(owner, **kwargs)
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            _update_positions_balance_labels(owner, 100.0, 90.0, observed_at=OLD)
            _update_positions_balance_labels(owner, None, None)
            _update_positions_balance_labels(owner, None, None)
        self.assertEqual(OLD, service.get_account_snapshot().generated_at)
        self.assertEqual(100.0, service.get_account_snapshot().total_balance)
        self.assertTrue(service.get_operational_preflight()["freshness"]["account"]["stale"])

    def test_balance_placeholder_cannot_initialize_account_freshness(self):
        service = TradingBotService(config={"mode": "Live"})
        owner = SimpleNamespace()
        owner._sync_service_account_snapshot = service.set_account_snapshot
        _update_positions_balance_labels(owner, None, None)
        self.assertEqual("", service.get_account_snapshot().generated_at)

    def test_real_position_fetch_preserves_timestamp_through_render_and_republish(self):
        service = TradingBotService(config={"mode": "Live"})
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: service)
        worker = worker_runtime._PositionsWorker("unit-key", "unit-secret", "Live", "FUTURES")
        worker._wrapper = Mock()
        worker._wrapper.list_open_futures_positions.return_value = []
        emitted = []
        worker.positions_ready.connect(lambda *args: emitted.append(args))
        with patch.object(worker_runtime, "datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(OLD)
            worker._tick()
        worker._wrapper.list_open_futures_positions.assert_called_once_with(max_age=0.0, force_refresh=True)
        self.assertEqual([([], "FUTURES", OLD, 0)], emitted)
        owner = SimpleNamespace(
            _pos_worker=worker,
            _open_position_records={}, _compute_global_pnl_totals=lambda: (0.0, 0.0, 0.0, 0.0),
            _update_position_history=lambda _records: None,
            log=lambda message: self.fail(message),
        )
        owner._render_positions_table = lambda: bridge._sync_service_portfolio_snapshot(owner)
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            build_runtime._gui_on_positions_ready(owner, *emitted[0])
            owner._render_positions_table()
        self.assertEqual(OLD, service.get_portfolio_snapshot().generated_at)
        self.assertTrue(service.get_operational_preflight()["freshness"]["portfolio"]["stale"])
        self.assertEqual(0, service.get_portfolio_snapshot().open_position_count)

    def test_unavailable_position_fetch_does_not_emit_confirmed_flat_snapshot(self):
        for account, method in (("FUTURES", "list_open_futures_positions"), ("SPOT", "get_balances")):
            for invalid in (None, {}, "bad", [None]):
                with self.subTest(account=account, invalid=invalid):
                    worker = worker_runtime._PositionsWorker("key", "secret", "Live", account)
                    worker._wrapper = Mock()
                    getattr(worker._wrapper, method).return_value = invalid
                    emitted, errors = [], []
                    worker.positions_ready.connect(lambda *args: emitted.append(args))
                    worker.error.connect(errors.append)
                    worker._tick()
                    self.assertEqual([], emitted)
                    self.assertTrue(errors)
                    self.assertFalse(worker._busy)

    def test_new_position_fetch_can_make_live_portfolio_fresh(self):
        service = TradingBotService(config={"mode": "Live"})
        client = EmbeddedDesktopServiceClient(service_cls=lambda **_kwargs: service)
        owner = SimpleNamespace(
            _open_position_records={}, _compute_global_pnl_totals=lambda: (0.0, 0.0, 0.0, 0.0),
            _update_position_history=lambda _records: None, log=lambda message: self.fail(message),
        )
        owner._render_positions_table = lambda: bridge._sync_service_portfolio_snapshot(owner)
        now = datetime.now(timezone.utc).isoformat()
        with patch.object(bridge, "_ensure_service_client", return_value=client):
            build_runtime._gui_on_positions_ready(owner, [], "FUTURES", now)
        self.assertEqual(now, service.get_portfolio_snapshot().generated_at)
        self.assertFalse(service.get_operational_preflight()["freshness"]["portfolio"]["stale"])


if __name__ == "__main__":
    unittest.main()
