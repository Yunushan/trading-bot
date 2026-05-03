import json
import sys
import tempfile
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.service.runtime import TradingBotService  # noqa: E402
from app.settings import ConfigValidationError  # noqa: E402


class ServiceConfigRuntimeTests(unittest.TestCase):
    def test_service_config_patch_round_trip(self):
        service = TradingBotService()
        initial_config = service.get_config_payload().to_dict()
        self.assertEqual(initial_config["mode"], "Demo/Testnet")

        payload = service.update_config(
            {
                "mode": "Demo/Testnet",
                "symbols": ["ETHUSDT", "BTCUSDT"],
                "intervals": ["5m", "15m"],
                "leverage": 10,
                "position_pct": 4.5,
                "theme": "Dark",
                "order_audit_max_bytes": 4096,
                "order_audit_backup_count": 3,
                "connector_order_circuit_incident_log_max_bytes": 2048,
                "connector_order_circuit_incident_log_backup_count": 4,
                "operational_live_start_gate_enabled": False,
                "operational_live_order_gate_enabled": False,
            }
        ).to_dict()
        self.assertEqual(payload["mode"], "Demo/Testnet")
        self.assertEqual(payload["symbols"], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual(payload["intervals"], ["5m", "15m"])
        self.assertEqual(payload["leverage"], 10)
        self.assertEqual(payload["position_pct"], 4.5)
        self.assertEqual(payload["theme"], "Dark")
        self.assertEqual(payload["order_audit_max_bytes"], 4096)
        self.assertEqual(payload["order_audit_backup_count"], 3)
        self.assertEqual(payload["connector_order_circuit_incident_log_max_bytes"], 2048)
        self.assertEqual(payload["connector_order_circuit_incident_log_backup_count"], 4)
        self.assertFalse(payload["operational_live_start_gate_enabled"])
        self.assertFalse(payload["operational_live_order_gate_enabled"])

        summary = service.get_config_summary().to_dict()
        self.assertEqual(summary["symbol_count"], 2)
        self.assertEqual(summary["interval_count"], 2)
        self.assertEqual(summary["theme"], "Dark")
        self.assertEqual(summary["llm_provider"], "openai")
        self.assertFalse(summary["llm_enabled"])
        operational = service.get_operational_snapshot()
        self.assertEqual(4096, operational["order_audit"]["max_bytes"])
        self.assertEqual(3, operational["order_audit"]["backup_count"])
        self.assertEqual(2048, operational["connector_order_circuit_incident_log"]["max_bytes"])
        self.assertEqual(4, operational["connector_order_circuit_incident_log"]["backup_count"])

    def test_service_config_patch_rejects_invalid_values_and_preserves_previous_config(self):
        service = TradingBotService()
        previous = service.get_config_payload().to_dict()

        with self.assertRaises(ConfigValidationError) as caught:
            service.update_config(
                {
                    "symbols": [],
                    "intervals": ["bad interval"],
                    "leverage": 0,
                    "position_pct": 0,
                    "order_audit_backup_count": -1,
                    "connector_order_circuit_incident_log_backup_count": 101,
                    "connector_order_block_pause_threshold": 0,
                    "unexpected_config_key": True,
                }
            )

        fields = {issue.field for issue in caught.exception.issues}
        self.assertIn("symbols", fields)
        self.assertIn("intervals", fields)
        self.assertIn("leverage", fields)
        self.assertIn("position_pct", fields)
        self.assertIn("order_audit_backup_count", fields)
        self.assertIn("connector_order_circuit_incident_log_backup_count", fields)
        self.assertIn("connector_order_block_pause_threshold", fields)
        self.assertIn("unexpected_config_key", fields)
        self.assertEqual(previous, service.get_config_payload().to_dict())

    def test_service_config_persistence_is_explicit_and_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "service-config.json"
            service = TradingBotService(config_path=path)
            self.assertFalse(path.exists())
            self.assertFalse(service.get_config_persistence_status()["dirty"])

            service.update_config(
                {
                    "symbols": ["ETHUSDT"],
                    "intervals": ["15m"],
                    "theme": "Dark",
                    "leverage": 5,
                    "position_pct": 3.25,
                }
            )

            self.assertFalse(path.exists())
            self.assertTrue(service.get_config_persistence_status()["dirty"])

            saved = service.save_config(source="unit-test")
            self.assertTrue(path.is_file())
            self.assertFalse(saved["dirty"])
            saved_file = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("trading-bot-service-config", saved_file["kind"])
            self.assertEqual(1, saved_file["format_version"])
            self.assertEqual(["ETHUSDT"], saved_file["config"]["symbols"])
            self.assertEqual(["15m"], saved_file["config"]["intervals"])

            reloaded = TradingBotService(config_path=path, load_persisted_config=True)
            payload = reloaded.get_config_payload().to_dict()
            self.assertEqual(["ETHUSDT"], payload["symbols"])
            self.assertEqual(["15m"], payload["intervals"])
            self.assertEqual("Dark", payload["theme"])
            self.assertEqual(5, payload["leverage"])
            self.assertEqual(3.25, payload["position_pct"])
            self.assertFalse(reloaded.get_config_persistence_status()["dirty"])

    def test_service_config_load_rejects_invalid_file_without_replacing_current_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "service-config.json"
            path.write_text(
                json.dumps(
                    {
                        "kind": "trading-bot-service-config",
                        "format_version": 1,
                        "config": {"leverage": 0},
                    }
                ),
                encoding="utf-8",
            )
            service = TradingBotService(config_path=path)
            previous = service.get_config_payload().to_dict()

            with self.assertRaises(ConfigValidationError):
                service.load_config()

            self.assertEqual(previous, service.get_config_payload().to_dict())
