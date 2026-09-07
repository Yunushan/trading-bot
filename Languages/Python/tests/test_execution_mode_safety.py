from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config, validate_runtime_config  # noqa: E402
from app.settings.execution_mode import (  # noqa: E402
    LIVE_MODE_VALUES,
    TESTNET_MODE_VALUES,
    InvalidExecutionModeError,
    execution_environment,
    is_live_trading_mode,
    is_testnet_trading_mode,
)
from app.settings.live_safety import LiveTradingSafetyError, validate_live_trading_safety  # noqa: E402
from app.settings.validation import ConfigValidationError  # noqa: E402
from app.integrations.exchanges.binance.wrapper import BinanceWrapper  # noqa: E402
from test_binance_package_split_smoke import _GuardedFuturesAuditWrapper, _live_ack_config  # noqa: E402


INVALID_MODES = (None, "", " ", "Paper", "Paper Local", "paper trading", "contest", "my-demo-mode", "Live/test", "unknown", 0, False, [], {})
TRANSPORT_MODULES = (
    "wrapper", "account.account_cache_runtime", "clients.connector_clients",
    "clients.sdk_common_runtime", "orders.order_fallback_runtime",
    "transport.http_base_runtime", "transport.ws_runtime",
)


class ExecutionModeSafetyTests(unittest.TestCase):
    def test_all_aliases_agree_across_safety_validation_and_transport(self):
        for aliases, environment in ((LIVE_MODE_VALUES, "live"), (TESTNET_MODE_VALUES, "testnet")):
            for alias in aliases:
                mode = f"  {alias.upper()}  "
                with self.subTest(mode=mode):
                    self.assertEqual(environment, execution_environment(mode))
                    self.assertEqual(environment == "live", is_live_trading_mode(mode))
                    config = build_default_config()
                    config["mode"] = mode
                    self.assertEqual(mode.strip(), validate_runtime_config(config)["mode"])
                    for path in TRANSPORT_MODULES:
                        module = importlib.import_module(f"app.integrations.exchanges.binance.{path}")
                        self.assertEqual(environment == "testnet", module._is_testnet_mode(mode), path)

    def test_unknown_modes_are_not_production_transport_fallbacks(self):
        for mode in INVALID_MODES:
            with self.subTest(mode=mode):
                self.assertTrue(is_live_trading_mode(mode))
                with self.assertRaises(InvalidExecutionModeError):
                    is_testnet_trading_mode(mode)
                config = build_default_config()
                config["mode"] = mode
                with self.assertRaises(ConfigValidationError):
                    validate_runtime_config(config)
                for path in TRANSPORT_MODULES:
                    module = importlib.import_module(f"app.integrations.exchanges.binance.{path}")
                    with self.assertRaises(InvalidExecutionModeError, msg=path):
                        module._is_testnet_mode(mode)

    def test_acknowledgement_cannot_authorize_an_unsupported_mode(self):
        for mode in INVALID_MODES:
            with self.subTest(mode=mode), self.assertRaisesRegex(LiveTradingSafetyError, "unsupported execution mode"):
                validate_live_trading_safety(
                    mode=mode, api_key="unit-api-key", api_secret="unit-api-secret",
                    leverage=1, position_pct=2, config=_live_ack_config(), env={},
                )

    def test_wrapper_rejects_invalid_mode_before_client_construction(self):
        for mode in INVALID_MODES:
            with self.subTest(mode=mode), patch.object(BinanceWrapper, "_build_client") as build:
                with self.assertRaisesRegex(LiveTradingSafetyError, "unsupported execution mode"):
                    BinanceWrapper("unit-api-key", "unit-api-secret", mode=mode)
                build.assert_not_called()

    def test_existing_client_mode_cannot_be_changed_to_bypass_acknowledgement(self):
        wrapper = BinanceWrapper.__new__(BinanceWrapper)
        wrapper._mode = "Live"
        for mode in ("Demo", "Paper", "Testnet"):
            with self.subTest(mode=mode), self.assertRaises(AttributeError):
                wrapper.mode = mode
        self.assertEqual("Live", wrapper.mode)

    def test_order_submission_revalidates_mode_before_exchange_side_effect(self):
        for mode in INVALID_MODES:
            with self.subTest(mode=mode):
                wrapper = _GuardedFuturesAuditWrapper(live_safety_config=_live_ack_config())
                self.addCleanup(wrapper.close)
                wrapper.mode = mode
                with self.assertRaisesRegex(LiveTradingSafetyError, "unsupported execution mode"):
                    wrapper._futures_create_order_with_fallback({
                        "symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1",
                    })
                self.assertEqual([], wrapper.client.orders)

    def test_supported_modes_preserve_live_acknowledgement_boundary(self):
        with patch.dict(os.environ, {
            "BOT_ENABLE_LIVE_TRADING": "false", "BOT_LIVE_TRADING_ACKNOWLEDGEMENT": "", "BOT_LIVE_TRADING_ACK": "",
        }):
            for mode in (*LIVE_MODE_VALUES, *TESTNET_MODE_VALUES):
                with self.subTest(mode=mode):
                    wrapper = _GuardedFuturesAuditWrapper(live_safety_config={}, mode=mode)
                    self.addCleanup(wrapper.close)
                    params = {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
                    if mode in LIVE_MODE_VALUES:
                        with self.assertRaises(LiveTradingSafetyError):
                            wrapper._futures_create_order_with_fallback(params)
                        self.assertEqual([], wrapper.client.orders)
                    else:
                        order, _ = wrapper._futures_create_order_with_fallback(params)
                        self.assertEqual("FILLED", order["status"])


if __name__ == "__main__":
    unittest.main()
