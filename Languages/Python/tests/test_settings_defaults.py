from __future__ import annotations

import os
import unittest
from unittest import mock

from app.config import DEFAULT_CONFIG, build_default_config, build_default_settings
from app.settings import BACKTEST_TEMPLATE_DEFAULT, STOP_LOSS_DEFAULT, StopLossSettings, normalize_stop_loss_dict


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
