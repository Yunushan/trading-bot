from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.transport import http_request_runtime, rate_limit_runtime  # noqa: E402


class _Limiter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.weights: list[float] = []

    def acquire(self, weight: float) -> None:
        self.weights.append(weight)
        if self.error is not None:
            raise self.error


class _Harness:
    def __init__(self, limiter: _Limiter | None = None) -> None:
        self._request_limiter = limiter
        self.logs: list[tuple[str, str]] = []

    def _log(self, message: str, lvl: str = "info") -> None:
        self.logs.append((lvl, message))


class BinanceTransportHardeningTests(unittest.TestCase):
    def test_request_weight_failure_uses_conservative_weight(self):
        limiter = _Limiter()
        harness = _Harness(limiter)
        harness._estimate_request_weight = lambda _path: (_ for _ in ()).throw(RuntimeError("bad path"))

        rate_limit_runtime._throttle_request(harness, "/fapi/v1/order")

        self.assertEqual([10.0], limiter.weights)
        self.assertTrue(any("weight estimation failed" in message for _level, message in harness.logs))

    def test_limiter_failure_blocks_exchange_request(self):
        harness = _Harness(_Limiter(RuntimeError("limiter unavailable")))
        harness._estimate_request_weight = rate_limit_runtime._estimate_request_weight

        with self.assertRaisesRegex(RuntimeError, "rate limiting failed"):
            rate_limit_runtime._throttle_request(harness, "/fapi/v1/order")

        self.assertTrue(any(level == "error" for level, _message in harness.logs))

    def test_ban_state_failure_applies_conservative_cooldown(self):
        harness = _Harness()
        harness._seconds_until_unban = lambda: (_ for _ in ()).throw(RuntimeError("ban state unavailable"))

        delay = http_request_runtime._seconds_until_direct_futures_request_allowed(harness)

        self.assertEqual(8.0, delay)
        self.assertTrue(any("conservative cooldown" in message for _level, message in harness.logs))

    def test_direct_http_throttle_failure_propagates_before_network_request(self):
        harness = _Harness()
        harness._throttle_request = lambda _path: (_ for _ in ()).throw(RuntimeError("limiter unavailable"))

        with self.assertRaisesRegex(RuntimeError, "throttling failed"):
            http_request_runtime._throttle_direct_futures_request(harness, "/fapi/v1/order")


if __name__ == "__main__":
    unittest.main()
