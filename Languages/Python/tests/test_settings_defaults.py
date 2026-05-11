from __future__ import annotations

import os
import unittest
from unittest import mock

from app.config import DEFAULT_CONFIG, build_default_config, build_default_settings
from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from app.settings import (
    BACKTEST_TEMPLATE_DEFAULT,
    BINANCE_MAX_FUTURES_LEVERAGE,
    LIVE_TRADING_ACKNOWLEDGEMENT,
    STOP_LOSS_DEFAULT,
    ConfigValidationError,
    LiveTradingSafetyError,
    StopLossSettings,
    is_live_trading_mode,
    normalize_stop_loss_dict,
    validate_runtime_config,
    validate_live_trading_safety,
)


class SettingsDefaultsTests(unittest.TestCase):
    def test_builder_returns_isolated_nested_defaults(self):
        left = build_default_config()
        right = build_default_config()

        left["indicators"]["rsi"]["enabled"] = False
        left["backtest"]["indicators"]["rsi"]["buy_value"] = 10
        left["stop_loss"]["enabled"] = True

        self.assertTrue(right["indicators"]["rsi"]["enabled"])
        self.assertEqual(30, right["backtest"]["indicators"]["rsi"]["buy_value"])
        self.assertFalse(right["stop_loss"]["enabled"])
        self.assertTrue(DEFAULT_CONFIG["indicators"]["rsi"]["enabled"])

    def test_live_trading_defaults_start_in_demo_mode(self):
        config = build_default_config()

        self.assertEqual("Demo/Testnet", config["mode"])
        self.assertEqual(1, config["leverage"])
        self.assertFalse(config["live_trading_enabled"])
        self.assertEqual("", config["live_trading_acknowledgement"])
        self.assertEqual(20, config["live_trading_max_leverage"])
        self.assertEqual(10.0, config["live_trading_max_position_pct"])
        self.assertEqual(100, config["live_trading_max_session_orders"])
        self.assertFalse(config["live_allow_auto_bump_to_min_order"])
        self.assertTrue(config["order_audit_enabled"])
        self.assertEqual("", config["order_audit_log_path"])
        self.assertEqual(10 * 1024 * 1024, config["order_audit_max_bytes"])
        self.assertEqual(1, config["order_audit_backup_count"])
        self.assertEqual("", config["connector_order_circuit_incident_log_path"])
        self.assertEqual(2 * 1024 * 1024, config["connector_order_circuit_incident_log_max_bytes"])
        self.assertEqual(1, config["connector_order_circuit_incident_log_backup_count"])
        self.assertEqual(120.0, config["operational_connector_snapshot_stale_seconds"])
        self.assertEqual(10.0, config["operational_execution_heartbeat_stale_seconds"])
        self.assertEqual(300.0, config["operational_account_snapshot_stale_seconds"])
        self.assertEqual(300.0, config["operational_portfolio_snapshot_stale_seconds"])
        self.assertTrue(config["operational_live_start_gate_enabled"])
        self.assertTrue(config["operational_live_order_gate_enabled"])

    def test_default_config_passes_runtime_validation(self):
        config = build_default_config()
        validated = validate_runtime_config(config)

        self.assertEqual(set(config), set(validated))
        self.assertEqual(set(config["backtest"]), set(validated["backtest"]))
        self.assertEqual("Demo/Testnet", validated["mode"])
        self.assertEqual(["BTCUSDT"], validated["symbols"])
        self.assertEqual(["1m"], validated["intervals"])
        self.assertEqual(1, validated["leverage"])
        self.assertEqual(2.0, validated["position_pct"])
        self.assertFalse(validated["live_allow_auto_bump_to_min_order"])
        self.assertIsNone(validated["lead_trader_profile"])

    def test_runtime_validation_accepts_live_auto_bump_opt_in(self):
        config = build_default_config()
        config["live_allow_auto_bump_to_min_order"] = True

        validated = validate_runtime_config(config)

        self.assertTrue(validated["live_allow_auto_bump_to_min_order"])

    def test_runtime_validation_rejects_unknown_config_keys(self):
        config = build_default_config()
        config["leverege"] = 3
        config["backtest"]["capital_usdt"] = 1000

        with self.assertRaises(ConfigValidationError) as caught:
            validate_runtime_config(config)

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("leverege", fields)
        self.assertIn("backtest.capital_usdt", fields)

    def test_runtime_validation_rejects_unsafe_numeric_values(self):
        config = build_default_config()
        config.update(
            {
                "leverage": 0,
                "position_pct": 250,
                "lookback": 0,
                "live_trading_max_position_pct": 0,
                "live_trading_max_session_orders": 0,
                "operational_connector_snapshot_stale_seconds": 0,
                "operational_execution_heartbeat_stale_seconds": 0,
                "operational_account_snapshot_stale_seconds": 0,
                "operational_portfolio_snapshot_stale_seconds": 0,
                "connector_order_block_pause_threshold": 0,
                "connector_order_block_window_seconds": 0,
                "indicator_flip_confirmation_bars": 0,
                "positions_missing_threshold": 0,
                "futures_flat_purge_miss_threshold": 0,
                "max_auto_bump_percent": 101,
                "auto_bump_percent_multiplier": -1,
            }
        )
        config["backtest"]["start_date"] = "not-a-date"

        with self.assertRaises(ConfigValidationError) as caught:
            validate_runtime_config(config)

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("leverage", fields)
        self.assertIn("position_pct", fields)
        self.assertIn("lookback", fields)
        self.assertIn("live_trading_max_position_pct", fields)
        self.assertIn("live_trading_max_session_orders", fields)
        self.assertIn("operational_connector_snapshot_stale_seconds", fields)
        self.assertIn("operational_execution_heartbeat_stale_seconds", fields)
        self.assertIn("operational_account_snapshot_stale_seconds", fields)
        self.assertIn("operational_portfolio_snapshot_stale_seconds", fields)
        self.assertIn("connector_order_block_pause_threshold", fields)
        self.assertIn("connector_order_block_window_seconds", fields)
        self.assertIn("indicator_flip_confirmation_bars", fields)
        self.assertIn("positions_missing_threshold", fields)
        self.assertIn("futures_flat_purge_miss_threshold", fields)
        self.assertIn("max_auto_bump_percent", fields)
        self.assertIn("auto_bump_percent_multiplier", fields)
        self.assertIn("backtest.start_date", fields)

    def test_runtime_validation_rejects_invalid_booleans_and_llm_choices(self):
        config = build_default_config()
        config.update(
            {
                "live_trading_enabled": "sometimes",
                "live_allow_auto_bump_to_min_order": "sometimes",
                "lead_trader_enabled": 2,
                "llm_enabled": "maybe",
                "llm_allow_public_network": "later",
                "llm_provider": "unknown-ai",
                "llm_use_for": "auto_trade",
                "llm_reasoning_effort": "turbo",
            }
        )

        with self.assertRaises(ConfigValidationError) as caught:
            validate_runtime_config(config)

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("live_trading_enabled", fields)
        self.assertIn("live_allow_auto_bump_to_min_order", fields)
        self.assertIn("lead_trader_enabled", fields)
        self.assertIn("llm_enabled", fields)
        self.assertIn("llm_allow_public_network", fields)
        self.assertIn("llm_provider", fields)
        self.assertIn("llm_use_for", fields)
        self.assertIn("llm_reasoning_effort", fields)

    def test_runtime_validation_rejects_leverage_above_shared_binance_limit(self):
        config = build_default_config()
        config["leverage"] = BINANCE_MAX_FUTURES_LEVERAGE + 1
        config["live_trading_max_leverage"] = BINANCE_MAX_FUTURES_LEVERAGE + 1
        config["runtime_symbol_interval_pairs"] = [
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "strategy_controls": {"leverage": BINANCE_MAX_FUTURES_LEVERAGE + 1},
            }
        ]

        with self.assertRaises(ConfigValidationError) as caught:
            validate_runtime_config(config)

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("leverage", fields)
        self.assertIn("live_trading_max_leverage", fields)
        self.assertIn("runtime_symbol_interval_pairs[0].strategy_controls.leverage", fields)

    def test_runtime_validation_normalizes_symbols_intervals_and_stop_loss(self):
        config = build_default_config()
        config.update(
            {
                "symbols": ["btcusdt", " BTCUSDT ", "ethusdt"],
                "intervals": ["60", "1H", "2months"],
                "stop_loss": {"enabled": "1", "mode": "percent", "percent": "2.5"},
                "runtime_symbol_interval_pairs": [
                    {
                        "symbol": "ethusdt",
                        "interval": "60m",
                        "strategy_controls": {"side": "buy", "leverage": "3", "loop_interval_override": "15"},
                    }
                ],
            }
        )

        validated = validate_runtime_config(config)

        self.assertEqual(["BTCUSDT", "ETHUSDT"], validated["symbols"])
        self.assertEqual(["60m", "1h", "2mo"], validated["intervals"])
        self.assertEqual(
            {"enabled": True, "mode": "percent", "usdt": 0.0, "percent": 2.5, "scope": "per_trade"},
            validated["stop_loss"],
        )
        pair = validated["runtime_symbol_interval_pairs"][0]
        self.assertEqual("ETHUSDT", pair["symbol"])
        self.assertEqual("60m", pair["interval"])
        self.assertEqual("BUY", pair["strategy_controls"]["side"])
        self.assertEqual(3, pair["strategy_controls"]["leverage"])
        self.assertEqual("15m", pair["strategy_controls"]["loop_interval_override"])

    def test_runtime_validation_rejects_invalid_pair_override(self):
        config = build_default_config()
        config["runtime_symbol_interval_pairs"] = [{"symbol": "BTCUSDT", "interval": "not-an-interval"}]

        with self.assertRaisesRegex(ConfigValidationError, "runtime_symbol_interval_pairs"):
            validate_runtime_config(config)

    def test_live_trading_mode_detection_fails_closed_for_unknown_live_endpoint_modes(self):
        self.assertFalse(is_live_trading_mode("Demo/Testnet"))
        self.assertFalse(is_live_trading_mode("sandbox"))
        self.assertTrue(is_live_trading_mode("Live"))
        self.assertTrue(is_live_trading_mode("Production"))

    def test_live_trading_requires_explicit_confirmation_and_credentials(self):
        with self.assertRaises(LiveTradingSafetyError):
            validate_live_trading_safety(
                mode="Live",
                api_key="live-api-key",
                api_secret="live-api-secret",
                account_type="Futures",
                leverage=1,
                position_pct=2.0,
                config={},
                env={},
            )

        validate_live_trading_safety(
            mode="Live",
            api_key="live-api-key",
            api_secret="live-api-secret",
            account_type="Futures",
            leverage=1,
            position_pct=2.0,
            config={
                "live_trading_enabled": True,
                "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
                "live_trading_max_leverage": 5,
                "live_trading_max_position_pct": 3.0,
            },
            env={},
        )

    def test_live_trading_blocks_placeholder_credentials_and_cap_overrides(self):
        safe_config = {
            "live_trading_enabled": True,
            "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
            "live_trading_max_leverage": 5,
            "live_trading_max_position_pct": 3.0,
        }

        with self.assertRaisesRegex(LiveTradingSafetyError, "placeholder"):
            validate_live_trading_safety(
                mode="Live",
                api_key="your_api_key",
                api_secret="live-api-secret",
                account_type="Futures",
                leverage=1,
                position_pct=2.0,
                config=safe_config,
                env={},
            )

        too_high_cap_config = {
            "live_trading_enabled": True,
            "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
            "live_trading_max_leverage": BINANCE_MAX_FUTURES_LEVERAGE + 1,
            "live_trading_max_position_pct": 3.0,
        }

        with self.assertRaisesRegex(
            LiveTradingSafetyError,
            f"live_trading_max_leverage must be between 1 and {BINANCE_MAX_FUTURES_LEVERAGE}",
        ):
            validate_live_trading_safety(
                mode="Live",
                api_key="live-api-key",
                api_secret="live-api-secret",
                account_type="Futures",
                leverage=1,
                position_pct=2.0,
                config=too_high_cap_config,
                env={},
            )

        invalid_session_cap_config = {
            "live_trading_enabled": True,
            "live_trading_acknowledgement": LIVE_TRADING_ACKNOWLEDGEMENT,
            "live_trading_max_leverage": 5,
            "live_trading_max_position_pct": 3.0,
            "live_trading_max_session_orders": 0,
        }

        with self.assertRaisesRegex(LiveTradingSafetyError, "live_trading_max_session_orders must be between"):
            validate_live_trading_safety(
                mode="Live",
                api_key="live-api-key",
                api_secret="live-api-secret",
                account_type="Futures",
                leverage=1,
                position_pct=2.0,
                config=invalid_session_cap_config,
                env={},
            )

        with self.assertRaisesRegex(LiveTradingSafetyError, "leverage 10 exceeds live cap 5"):
            validate_live_trading_safety(
                mode="Live",
                api_key="live-api-key",
                api_secret="live-api-secret",
                account_type="Futures",
                leverage=10,
                position_pct=2.0,
                config=safe_config,
                env={},
            )

        with self.assertRaisesRegex(LiveTradingSafetyError, "position_pct 4% exceeds live cap 3%"):
            validate_live_trading_safety(
                mode="Live",
                api_key="live-api-key",
                api_secret="live-api-secret",
                account_type="Spot",
                position_pct=4.0,
                config=safe_config,
                env={},
            )

    def test_live_trading_can_be_confirmed_with_environment_pair(self):
        validate_live_trading_safety(
            mode="Live",
            api_key="live-api-key",
            api_secret="live-api-secret",
            account_type="Futures",
            leverage=3,
            position_pct=2.0,
            config={},
            env={
                "BOT_ENABLE_LIVE_TRADING": "true",
                "BOT_LIVE_TRADING_ACKNOWLEDGEMENT": LIVE_TRADING_ACKNOWLEDGEMENT,
                "BOT_LIVE_MAX_LEVERAGE": "4",
                "BOT_LIVE_MAX_POSITION_PCT": "2.5",
                "BOT_LIVE_MAX_SESSION_ORDERS": "7",
            },
        )

    def test_builtin_backtest_templates_use_safe_leverage(self):
        for key, template in BACKTEST_TEMPLATE_DEFINITIONS.items():
            self.assertEqual(1, int(template.get("leverage", 1)), key)

    def test_backtest_defaults_do_not_alias_runtime_indicator_defaults(self):
        config = build_default_config()
        other = build_default_config()

        config["indicators"]["rsi"]["buy_value"] = 55

        self.assertEqual(55, config["indicators"]["rsi"]["buy_value"])
        self.assertEqual(30, config["backtest"]["indicators"]["rsi"]["buy_value"])
        self.assertTrue(config["backtest"]["indicators"]["rsi"]["enabled"])
        self.assertIsNone(other["indicators"]["rsi"]["buy_value"])

    def test_build_default_settings_reads_environment_credentials(self):
        with mock.patch.dict(
            os.environ,
            {"BINANCE_API_KEY": "env-key", "BINANCE_API_SECRET": "env-secret"},
            clear=False,
        ):
            settings = build_default_settings()
            config = settings.to_config_dict()

        self.assertEqual("env-key", settings.auth.api_key)
        self.assertEqual("env-secret", settings.auth.api_secret)
        self.assertEqual("env-key", config["api_key"])
        self.assertEqual("env-secret", config["api_secret"])

    def test_compatibility_constants_keep_expected_defaults(self):
        self.assertEqual(
            {"enabled": False, "mode": "usdt", "usdt": 0.0, "percent": 0.0, "scope": "per_trade"},
            STOP_LOSS_DEFAULT,
        )
        self.assertEqual({"enabled": False, "name": None}, BACKTEST_TEMPLATE_DEFAULT)
        self.assertEqual(STOP_LOSS_DEFAULT, normalize_stop_loss_dict({"mode": "invalid", "scope": "bad"}))

    def test_stop_loss_normalization_coerces_loose_boolean_strings(self):
        disabled = normalize_stop_loss_dict({"enabled": "false", "mode": "percent", "percent": "3.5"})
        enabled = normalize_stop_loss_dict({"enabled": "1", "mode": "usdt", "usdt": "25"})

        self.assertFalse(disabled["enabled"])
        self.assertEqual("percent", disabled["mode"])
        self.assertEqual(3.5, disabled["percent"])
        self.assertTrue(enabled["enabled"])
        self.assertEqual(25.0, enabled["usdt"])

    def test_stop_loss_settings_constructor_normalizes_non_boolean_enabled_values(self):
        normalized = StopLossSettings(enabled="0", mode="both", usdt="12.5", percent="2.5", scope="cumulative").normalized()

        self.assertFalse(normalized.enabled)
        self.assertEqual("both", normalized.mode)
        self.assertEqual(12.5, normalized.usdt)
        self.assertEqual(2.5, normalized.percent)
        self.assertEqual("cumulative", normalized.scope)


if __name__ == "__main__":
    unittest.main()
