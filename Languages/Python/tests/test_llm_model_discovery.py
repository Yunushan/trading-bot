from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.discovery import discover_llm_models  # noqa: E402


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class LLMModelDiscoveryTests(unittest.TestCase):
    def test_kilo_live_models_merge_with_historical_and_custom_ids(self):
        with mock.patch("app.integrations.llm.discovery.requests.get") as get:
            get.return_value = _Response(
                {
                    "data": [
                        {
                            "id": "vendor/future-model-v9",
                            "name": "Future Model V9",
                            "context_length": 1_000_000,
                            "top_provider": {"max_completion_tokens": 65_536},
                            "supported_parameters": ["reasoning", "temperature"],
                            "architecture": {
                                "input_modalities": ["text", "image"],
                                "output_modalities": ["text"],
                            },
                        },
                        {"id": "kilo-auto/frontier", "context_window": 262_144},
                    ]
                }
            )
            result = discover_llm_models(
                {
                    "llm_provider": "kilo",
                    "llm_model": "vendor/legacy-model",
                    "llm_api_key": "kilo-secret-token",
                    "llm_timeout_seconds": 17,
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual("kilo", result["provider"])
        self.assertEqual(2, result["dynamic_count"])
        by_id = {item["id"]: item for item in result["models"]}
        self.assertIn("vendor/future-model-v9", by_id)
        self.assertIn("vendor/legacy-model", by_id)
        self.assertIn("kilo-auto/frontier", by_id)
        self.assertIn("openai/gpt-5.5", by_id)
        self.assertEqual(1_000_000, by_id["vendor/future-model-v9"]["context_window"])
        self.assertEqual(65_536, by_id["vendor/future-model-v9"]["max_output_tokens"])
        self.assertIn("input:image", by_id["vendor/future-model-v9"]["capabilities"])
        self.assertTrue(by_id["kilo-auto/frontier"]["available"])
        self.assertEqual("https://api.kilo.ai/api/gateway/models", get.call_args.args[0])
        self.assertEqual("Bearer kilo-secret-token", get.call_args.kwargs["headers"]["Authorization"])
        self.assertEqual("trading-bot-model-discovery", get.call_args.kwargs["headers"]["User-Agent"])
        self.assertEqual(17.0, get.call_args.kwargs["timeout"])

    def test_discovery_failure_retains_static_models_and_redacts_key(self):
        with mock.patch(
            "app.integrations.llm.discovery.requests.get",
            side_effect=RuntimeError("request failed for secret-key"),
        ):
            result = discover_llm_models(
                {
                    "llm_provider": "kilo",
                    "llm_api_key": "secret-key",
                }
            )

        self.assertFalse(result["ok"])
        self.assertEqual(0, result["dynamic_count"])
        self.assertIn("kilo-auto/frontier", {item["id"] for item in result["models"]})
        self.assertNotIn("secret-key", result["error"])
        self.assertIn("********", result["error"])

    def test_public_custom_discovery_requires_explicit_network_consent(self):
        with mock.patch("app.integrations.llm.discovery.requests.get") as get:
            result = discover_llm_models(
                {
                    "llm_provider": "local",
                    "llm_base_url": "https://models.example.test/v1",
                    "llm_allow_public_network": False,
                }
            )

        self.assertFalse(result["ok"])
        self.assertIn("disabled", result["error"])
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
