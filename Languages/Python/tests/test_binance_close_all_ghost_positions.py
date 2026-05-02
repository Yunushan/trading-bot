import importlib.util
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


MODULE_PATH = (
    PYTHON_ROOT
    / "app"
    / "integrations"
    / "exchanges"
    / "binance"
    / "positions"
    / "close_all_runtime.py"
)
spec = importlib.util.spec_from_file_location("binance_close_all_runtime", MODULE_PATH)
close_all_runtime = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(close_all_runtime)
close_all_futures_positions = close_all_runtime.close_all_futures_positions


class _GhostClient:
    def __init__(self):
        self.margin_calls = []
        self.cancel_calls = []
        self.cleared = False

    def futures_get_position_mode(self):
        return {"dualSidePosition": False}

    def futures_cancel_all_open_orders(self, **params):
        self.cancel_calls.append(dict(params))
        return {"ok": True}

    def futures_position_information(self):
        if self.cleared:
            return []
        return [
            {
                "symbol": "DOGEUSDT",
                "positionAmt": "0",
                "positionSide": "BOTH",
                "isolatedWallet": "-25999.60",
                "isolatedMargin": "-25999.60",
                "notional": "0",
            }
        ]

    def futures_change_position_margin(self, **params):
        self.margin_calls.append(dict(params))
        self.cleared = True
        return {
            "amount": params.get("amount"),
            "code": 200,
            "msg": "Successfully modify position margin.",
            "type": params.get("type"),
        }


class _GhostWrapper:
    def __init__(self, mode="Demo/Testnet", client=None):
        self.mode = mode
        self.client = client or _GhostClient()


class _DirectFallbackClient(_GhostClient):
    def futures_change_position_margin(self, **params):
        raise AttributeError("not available")


class _DirectFallbackWrapper(_GhostWrapper):
    def __init__(self):
        super().__init__(client=_DirectFallbackClient())
        self.direct_calls = []
        self._last_futures_http_error = None

    def _futures_api_prefix(self):
        return "/fapi"

    def _http_signed_futures_request(self, method, path, params, *, prefix=None):
        self.direct_calls.append(
            {
                "method": method,
                "path": path,
                "params": dict(params),
                "prefix": prefix,
            }
        )
        self.client.cleared = True
        return {"amount": params.get("amount"), "code": 200, "msg": "ok", "type": params.get("type")}


class BinanceGhostPositionCloseAllTests(unittest.TestCase):
    def test_demo_stop_clears_zero_qty_negative_isolated_margin(self):
        wrapper = _GhostWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["symbol"], "DOGEUSDT")
        self.assertEqual(results[0]["method"], "positionMargin")
        self.assertEqual(results[0]["amount"], "25999.6")
        self.assertEqual(
            wrapper.client.margin_calls,
            [{"symbol": "DOGEUSDT", "amount": "25999.6", "type": 1}],
        )

    def test_live_mode_does_not_auto_transfer_margin_for_zero_qty_residual(self):
        wrapper = _GhostWrapper(mode="Live")

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(results, [])
        self.assertEqual(wrapper.client.margin_calls, [])

    def test_demo_cleanup_uses_signed_futures_request_fallback(self):
        wrapper = _DirectFallbackWrapper()

        results = close_all_futures_positions(wrapper, fast=True, max_workers=1)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["method"], "positionMargin")
        self.assertEqual(
            wrapper.direct_calls,
            [
                {
                    "method": "POST",
                    "path": "/v1/positionMargin",
                    "params": {"symbol": "DOGEUSDT", "amount": "25999.6", "type": 1},
                    "prefix": "/fapi",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
