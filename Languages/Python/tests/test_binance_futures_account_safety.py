# ruff: noqa: E402

import math
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.account import account_futures_runtime as futures_account


class _FuturesAccountHarness:
    def __init__(self, *, balances=None, accounts=None, credentials=True):
        self.api_key = "unit-key" if credentials else ""
        self.api_secret = "unit-secret" if credentials else ""
        self.mode = "Demo/Testnet"
        self.account_type = "FUTURES"
        self._last_futures_http_error = None
        self.balance_calls: list[bool] = []
        self.account_calls: list[bool] = []
        self.sync_calls = 0
        self._balances = dict(balances or {})
        self._accounts = dict(accounts or {})
        self.spot_balance = 0.0
        self.positions: list[dict] = []

    def _get_futures_account_balance_cached(self, *, force_refresh=False):
        self.balance_calls.append(bool(force_refresh))
        return list(self._balances.get(bool(force_refresh), []))

    def _get_futures_account_cached(self, *, force_refresh=False):
        self.account_calls.append(bool(force_refresh))
        return dict(self._accounts.get(bool(force_refresh), {}))

    def _sync_futures_time_offset(self, *, force=False):
        self.sync_calls += 1

    def _diagnose_testnet_key_scope(self):
        return "spot"

    def _testnet_auth_hint(self, _code):
        return "unit testnet hint"

    def get_balances(self):
        return [{"asset": "USDT", "free": self.spot_balance}]

    def get_spot_balance(self, _asset):
        return self.spot_balance

    def list_open_futures_positions(self):
        return list(self.positions)

    def get_futures_balance_usdt(self, *, force_refresh=False):
        return futures_account.get_futures_balance_usdt(self, force_refresh=force_refresh)

    def get_futures_wallet_balance(self, *, force_refresh=False):
        return futures_account.get_futures_wallet_balance(self, force_refresh=force_refresh)

    def get_futures_available_balance(self, *, force_refresh=False):
        return futures_account.get_futures_available_balance(self, force_refresh=force_refresh)

    def get_total_usdt_value(self, *, force_refresh=False):
        return futures_account.get_total_usdt_value(self, force_refresh=force_refresh)


class BinanceFuturesAccountSafetyTests(unittest.TestCase):
    def test_available_balance_rejects_nonfinite_balance_entries(self):
        harness = _FuturesAccountHarness(
            balances={False: [{"asset": "USDT", "availableBalance": "nan"}, {"asset": "BUSD", "availableBalance": "17.5"}]}
        )

        result = futures_account.get_futures_balance_usdt(harness)

        self.assertEqual(17.5, result)
        self.assertEqual([False], harness.balance_calls)

    def test_snapshot_uses_finite_account_asset_fallback_and_preserves_asset(self):
        harness = _FuturesAccountHarness(
            balances={False: [{"asset": "USDT", "availableBalance": "nan", "walletBalance": "inf"}]},
            accounts={
                False: {
                    "assets": [
                        {"asset": "USDT", "availableBalance": "nan"},
                        {"asset": "BUSD", "availableBalance": "11.5", "walletBalance": "14.25"},
                    ]
                }
            },
        )

        result = futures_account.get_futures_balance_snapshot(harness)

        self.assertEqual({"asset": "BUSD", "available": 11.5, "wallet": 14.25, "total": 14.25}, result)
        self.assertEqual(1, harness.sync_calls)

    def test_snapshot_auth_error_keeps_diagnostic_context_without_credentials(self):
        harness = _FuturesAccountHarness(balances={False: []}, accounts={False: {}})
        harness._last_futures_http_error = {
            "message": "invalid api-key",
            "code": -2015,
            "status_code": 401,
            "path": "/v2/balance",
            "base": "https://testnet.binancefuture.com",
        }

        with self.assertRaisesRegex(RuntimeError, r"invalid api-key.*code=-2015.*http=401.*Spot Testnet keys"):
            futures_account.get_futures_balance_snapshot(harness)

    def test_available_balance_falls_back_to_spot_after_empty_futures_reads(self):
        harness = _FuturesAccountHarness()
        harness.spot_balance = 9.75

        result = futures_account.get_futures_available_balance(harness)

        self.assertEqual(9.75, result)
        self.assertEqual([False, True, True], harness.balance_calls)

    def test_wallet_and_total_wallet_reject_nonfinite_values(self):
        harness = _FuturesAccountHarness(
            balances={False: [{"asset": "USDT", "walletBalance": "nan"}, {"asset": "BUSD", "walletBalance": "4.5"}]},
            accounts={False: {"totalWalletBalance": "nan", "totalMarginBalance": "inf"}},
        )

        self.assertEqual(4.5, futures_account.get_futures_wallet_balance(harness))
        harness.get_total_usdt_value = lambda: 12.0
        self.assertEqual(12.0, futures_account.get_total_wallet_balance(harness))

    def test_unrealized_pnl_and_total_usdt_value_ignore_nonfinite_values(self):
        harness = _FuturesAccountHarness()
        harness.positions = [
            {"unRealizedProfit": "nan"},
            {"unRealizedProfit": "2.5"},
            {"unRealizedProfit": "-0.75"},
            {"unRealizedProfit": "not-a-number"},
        ]

        self.assertEqual(1.75, futures_account.get_total_unrealized_pnl(harness))
        harness.get_futures_wallet_balance = lambda *, force_refresh=False: math.nan
        harness.get_futures_balance_usdt = lambda *, force_refresh=False: 18.0
        harness.get_futures_available_balance = lambda: math.inf
        harness.spot_balance = 12.0
        self.assertEqual(18.0, futures_account.get_total_usdt_value(harness))


if __name__ == "__main__":
    unittest.main()
