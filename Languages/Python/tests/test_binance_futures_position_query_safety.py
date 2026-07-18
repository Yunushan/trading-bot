# ruff: noqa: E402

import math
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.positions import futures_position_query_runtime as positions_runtime


class _PositionClient:
    def __init__(self, *, risk=None, information=None, dual_side=None):
        self.risk = risk
        self.information = information
        self.dual_side = dual_side
        self.risk_calls = 0
        self.info_calls = 0
        self.dual_calls = 0

    def futures_position_risk(self):
        self.risk_calls += 1
        if isinstance(self.risk, Exception):
            raise self.risk
        return self.risk

    def futures_position_information(self):
        self.info_calls += 1
        if isinstance(self.information, Exception):
            raise self.information
        return self.information

    def futures_get_position_mode(self):
        self.dual_calls += 1
        if isinstance(self.dual_side, Exception):
            raise self.dual_side
        return self.dual_side


class _PositionHarness:
    def __init__(self, client, *, cached=None, account=None):
        self.client = client
        self.cached = cached
        self.account = dict(account or {})
        self.cached_args = []
        self.stored = []
        self._fast_order_mode = False
        self._fast_positions_cache_ttl = 0.0
        self._futures_dual_side_cache = None
        self._futures_dual_side_cache_ts = 0.0

    def _get_cached_futures_positions(self, max_age):
        self.cached_args.append(max_age)
        return self.cached

    def _store_futures_positions_cache(self, value):
        self.stored.append(value)

    def _get_futures_account_cached(self, *, force_refresh=False):
        self.account_force_refresh = force_refresh
        return dict(self.account)


class BinanceFuturesPositionQuerySafetyTests(unittest.TestCase):
    def test_query_skips_nonfinite_positions_and_normalizes_finite_risk_values(self):
        client = _PositionClient(
            risk=[
                {"symbol": "BTCUSDT", "positionAmt": "nan", "marginRatio": "10"},
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "2",
                    "positionSide": "LONG",
                    "walletBalance": "20",
                    "maintMargin": "1",
                    "openOrderInitialMargin": "1",
                    "unRealizedProfit": "-2",
                    "marginRatio": "nan",
                    "entryPrice": "2000",
                    "markPrice": "2010",
                    "leverage": "5",
                },
            ]
        )
        harness = _PositionHarness(client)

        result = positions_runtime.list_open_futures_positions(harness, force_refresh=True)

        self.assertEqual(1, len(result))
        row = result[0]
        self.assertEqual("ETHUSDT", row["symbol"])
        self.assertEqual(2.0, row["positionAmt"])
        self.assertEqual(5, row["leverage"])
        self.assertEqual(20.0, row["walletBalance"])
        self.assertEqual(20.0, row["marginRatioCalc"])
        self.assertEqual(20.0, row["marginRatio"])
        self.assertTrue(all(math.isfinite(float(value)) for key, value in row.items() if key != "marginType" and isinstance(value, (int, float))))

    def test_query_uses_information_when_risk_endpoint_fails(self):
        client = _PositionClient(
            risk=RuntimeError("risk endpoint unavailable"),
            information=[{"symbol": "BTCUSDT", "positionAmt": "-0.25", "positionSide": "BOTH"}],
        )
        harness = _PositionHarness(client)

        result = positions_runtime.list_open_futures_positions(harness, force_refresh=True)

        self.assertEqual(-0.25, result[0]["positionAmt"])
        self.assertEqual(1, client.risk_calls)
        self.assertEqual(1, client.info_calls)

    def test_query_uses_futures_account_fallback_when_client_returns_no_positions(self):
        client = _PositionClient(risk=[], information=[])
        harness = _PositionHarness(
            client,
            account={
                "positions": [
                    {"symbol": "BTCUSDT", "positionAmt": "0"},
                    {"symbol": "ETHUSDT", "positionAmt": "1.5", "walletBalance": "3"},
                ]
            },
        )

        result = positions_runtime.list_open_futures_positions(harness, force_refresh=True)

        self.assertEqual(["ETHUSDT"], [row["symbol"] for row in result])
        self.assertTrue(harness.account_force_refresh)
        self.assertEqual(1, len(harness.stored))

    def test_query_returns_unknown_when_every_position_snapshot_source_is_unavailable(self):
        client = _PositionClient(
            risk=RuntimeError("risk endpoint unavailable"),
            information=RuntimeError("position endpoint unavailable"),
        )
        harness = _PositionHarness(client)
        harness._get_futures_account_cached = lambda *, force_refresh=False: (_ for _ in ()).throw(
            RuntimeError("account endpoint unavailable")
        )

        result = positions_runtime.list_open_futures_positions(harness, force_refresh=True)

        self.assertIsNone(result)
        self.assertEqual([], harness.stored)

    def test_query_discards_tiny_ghost_positions_like_native_clients(self):
        client = _PositionClient(
            risk=[
                {"symbol": "BTCUSDT", "positionAmt": "0.00000000001"},
                {"symbol": "ETHUSDT", "positionAmt": "-0.00000000001"},
                {"symbol": "SOLUSDT", "positionAmt": "0.00000000011"},
            ]
        )
        harness = _PositionHarness(client)

        result = positions_runtime.list_open_futures_positions(harness, force_refresh=True)

        self.assertEqual(["SOLUSDT"], [row["symbol"] for row in result])

    def test_query_returns_cached_snapshot_without_contacting_exchange(self):
        client = _PositionClient(risk=RuntimeError("should not be called"))
        cached = [{"symbol": "BTCUSDT", "positionAmt": 1.0}]
        harness = _PositionHarness(client, cached=cached)

        result = positions_runtime.list_open_futures_positions(harness, max_age=4.0)

        self.assertIs(cached, result)
        self.assertEqual([4.0], harness.cached_args)
        self.assertEqual(0, client.risk_calls)

    def test_net_position_rejects_nonfinite_amount_then_uses_risk_fallback(self):
        client = _PositionClient(
            information=RuntimeError("information endpoint unavailable"),
            risk=[
                {"symbol": "BTCUSDT", "positionAmt": "nan"},
                {"symbol": "BTCUSDT", "positionAmt": "-0.75"},
            ],
        )
        harness = _PositionHarness(client)

        result = positions_runtime.get_net_futures_position_amt(harness, "btcusdt")

        self.assertEqual(-0.75, result)

    def test_net_position_sums_hedge_rows_and_discards_tiny_residuals(self):
        client = _PositionClient(
            information=[
                {"symbol": "BTCUSDT", "positionAmt": "0.25", "positionSide": "LONG"},
                {"symbol": "BTCUSDT", "positionAmt": "-0.40", "positionSide": "SHORT"},
                {"symbol": "BTCUSDT", "positionAmt": "0.00000000001"},
            ]
        )
        harness = _PositionHarness(client)

        result = positions_runtime.get_net_futures_position_amt(harness, "btcusdt")

        self.assertAlmostEqual(-0.15, result)

    def test_dual_side_result_is_cached_after_first_successful_read(self):
        client = _PositionClient(dual_side={"dualSidePosition": "true"})
        harness = _PositionHarness(client)

        self.assertTrue(positions_runtime.get_futures_dual_side(harness))
        client.dual_side = RuntimeError("must use cache")
        self.assertTrue(positions_runtime.get_futures_dual_side(harness))
        self.assertEqual(1, client.dual_calls)


if __name__ == "__main__":
    unittest.main()
