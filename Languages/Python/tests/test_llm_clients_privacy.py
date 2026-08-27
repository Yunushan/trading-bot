from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.clients import (  # noqa: E402
    _sanitize_request_for_display,
    build_llm_chat_request,
    call_llm,
    llm_output_policy_violations,
)


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class LLMClientPrivacyTests(unittest.TestCase):
    def test_cloud_llm_context_is_minimized_before_request_build(self):
        request = build_llm_chat_request(
            {
                "llm_provider": "openai",
                "llm_model": "gpt-5.4-nano",
                "llm_api_key": "cloud-secret-token",
                "llm_allow_public_network": True,
            },
            prompt="Explain risk.",
            context={
                "runtime": {"phase": "test", "control_plane": {"mode": "desktop"}},
                "config": {
                    "mode": "Live",
                    "api_key": "exchange-key",
                    "api_secret": "exchange-secret",
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "intervals": ["1m"],
                },
                "portfolio": {
                    "open_position_records": {"BTCUSDT": {"entry": 100}},
                    "closed_position_records": [{"secret": "trade-secret"}],
                    "active_pnl": 12.5,
                },
                "logs": [{"message": "Authorization: Bearer leaked-token"}],
            },
        )

        body_text = str(request["json"])
        self.assertIn("Cloud LLM context minimized", body_text)
        self.assertIn("symbol_count", body_text)
        self.assertNotIn("exchange-key", body_text)
        self.assertNotIn("exchange-secret", body_text)
        self.assertNotIn("trade-secret", body_text)
        self.assertNotIn("leaked-token", body_text)
        self.assertNotIn("open_position_records", body_text)
        self.assertTrue(request["execution_policy"]["advisory_only"])
        self.assertFalse(request["execution_policy"]["can_execute_orders"])
        self.assertIn("advisory only", body_text)
        self.assertIn("must not place orders", body_text)
        self.assertEqual("strategy_and_risk_runtime", request["execution_policy"]["owner"])

    def test_local_llm_context_is_not_minimized(self):
        request = build_llm_chat_request(
            {
                "llm_provider": "local",
                "llm_model": "qwen3:8b",
                "llm_base_url": "http://127.0.0.1:11434/v1",
            },
            prompt="Explain risk.",
            context={"custom": {"local_detail": "kept-for-local-model"}},
        )

        self.assertIn("kept-for-local-model", str(request["json"]))
        self.assertIn("advisory only", str(request["json"]))

    def test_public_custom_open_source_endpoint_uses_minimized_context(self):
        request = build_llm_chat_request(
            {
                "llm_provider": "open-source",
                "llm_model": "RWKV/rwkv-6-world",
                "llm_base_url": "https://llm.example.com/v1",
                "llm_allow_public_network": True,
            },
            prompt="Explain risk.",
            context={
                "config": {
                    "api_key": "exchange-key",
                    "api_secret": "exchange-secret",
                    "symbols": ["BTCUSDT"],
                },
                "custom": {"local_detail": "should-not-leave-private-runtime"},
            },
        )

        body_text = str(request["json"])
        self.assertIn("Cloud LLM context minimized", body_text)
        self.assertIn("symbol_count", body_text)
        self.assertNotIn("exchange-key", body_text)
        self.assertNotIn("exchange-secret", body_text)
        self.assertNotIn("should-not-leave-private-runtime", body_text)

    def test_public_llm_endpoint_requires_explicit_network_consent(self):
        with self.assertRaisesRegex(ValueError, "Public local/custom LLM endpoints are disabled"):
            build_llm_chat_request(
                {
                    "llm_provider": "open-source",
                    "llm_model": "RWKV/rwkv-6-world",
                    "llm_base_url": "https://llm.example.com/v1",
                    "llm_allow_public_network": False,
                },
                prompt="Explain risk.",
            )

    def test_current_cloud_reasoning_options_use_provider_specific_request_fields(self):
        openai_request = build_llm_chat_request(
            {
                "llm_provider": "openai",
                "llm_model": "gpt-5.6-terra",
                "llm_api_key": "cloud-secret-token",
                "llm_reasoning_effort": "max",
            },
            prompt="Explain risk.",
        )
        self.assertEqual("max", openai_request["json"]["reasoning_effort"])

        qwen_request = build_llm_chat_request(
            {
                "llm_provider": "qwen",
                "llm_model": "qwen3.7-max",
                "llm_api_key": "cloud-secret-token",
                "llm_reasoning_effort": "enabled",
            },
            prompt="Explain risk.",
        )
        self.assertTrue(qwen_request["json"]["enable_thinking"])

        kimi_k3_request = build_llm_chat_request(
            {
                "llm_provider": "moonshot",
                "llm_model": "kimi-k3",
                "llm_api_key": "cloud-secret-token",
                "llm_reasoning_effort": "max",
            },
            prompt="Explain risk.",
        )
        self.assertEqual("max", kimi_k3_request["json"]["reasoning_effort"])

        kimi_k2_request = build_llm_chat_request(
            {
                "llm_provider": "moonshot",
                "llm_model": "kimi-k2.6",
                "llm_api_key": "cloud-secret-token",
                "llm_reasoning_effort": "disabled",
            },
            prompt="Explain risk.",
        )
        self.assertEqual({"type": "disabled"}, kimi_k2_request["json"]["thinking"])

    def test_kilo_responses_supports_dynamic_options_and_protects_advisory_fields(self):
        request = build_llm_chat_request(
            {
                "llm_provider": "kilo",
                "llm_model": "vendor/future-model-v9",
                "llm_api_key": "kilo-secret-token",
                "llm_api_style": "responses",
                "llm_reasoning_effort": "turbo",
                "llm_speed": "fast",
                "llm_context_window": 1_024,
                "llm_max_output_tokens": 256,
                "llm_verbosity": "high",
                "llm_temperature": 0.2,
                "llm_top_p": 0.8,
                "llm_timeout_seconds": 45,
                "llm_request_options": json.dumps(
                    {
                        "seed": 7,
                        "metadata": {"compatibility": "kilo"},
                        "text": {"format": {"type": "text"}},
                        "model": "unsafe-model-override",
                        "input": "unsafe prompt override",
                        "instructions": "unsafe instructions override",
                        "tools": [{"type": "computer"}],
                        "stream": True,
                    }
                ),
            },
            prompt="Explain risk.",
            system_prompt="Be concise.",
            context={"config": {"llm": {"large_context": "x" * 10_000}}},
        )

        body = request["json"]
        self.assertEqual("kilo", request["provider"])
        self.assertEqual("openai-responses", request["protocol"])
        self.assertEqual("https://api.kilo.ai/api/gateway/responses", request["url"])
        self.assertEqual("vendor/future-model-v9", body["model"])
        self.assertEqual("Explain risk.", body["input"])
        self.assertIn("Execution boundary", body["instructions"])
        self.assertIn("context_truncated", body["instructions"])
        self.assertEqual({"effort": "turbo"}, body["reasoning"])
        self.assertEqual("priority", body["service_tier"])
        self.assertEqual(256, body["max_output_tokens"])
        self.assertEqual(0.2, body["temperature"])
        self.assertEqual(0.8, body["top_p"])
        self.assertEqual("high", body["text"]["verbosity"])
        self.assertEqual({"type": "text"}, body["text"]["format"])
        self.assertEqual(7, body["seed"])
        self.assertNotIn("tools", body)
        self.assertNotIn("stream", body)
        self.assertEqual(45, request["timeout_seconds"])

    def test_historical_openai_chat_model_uses_legacy_output_limit(self):
        request = build_llm_chat_request(
            {
                "llm_provider": "openai",
                "llm_model": "gpt-3.5-turbo",
                "llm_api_key": "cloud-secret-token",
                "llm_api_style": "chat-completions",
                "llm_max_output_tokens": 512,
            },
            prompt="Explain risk.",
        )

        self.assertEqual(512, request["json"]["max_tokens"])
        self.assertNotIn("max_completion_tokens", request["json"])

    def test_kilo_responses_text_is_extracted(self):
        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            post.return_value = _Response(
                {
                    "output": [
                        {
                            "content": [
                                {"type": "output_text", "text": "Keep deterministic risk controls."}
                            ]
                        }
                    ]
                }
            )
            result = call_llm(
                {
                    "llm_provider": "kilo",
                    "llm_model": "kilo-auto/frontier",
                    "llm_api_key": "kilo-secret-token",
                    "llm_api_style": "responses",
                },
                prompt="Explain risk.",
                dry_run=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual("Keep deterministic risk controls.", result["text"])
        self.assertEqual(30, post.call_args.kwargs["timeout"])

    def test_llm_transport_failure_is_structured_and_redacted(self):
        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            post.side_effect = requests.ConnectionError(
                "HTTPSConnectionPool(host='generativelanguage.googleapis.com', "
                "url='/v1beta/models/test:generateContent?key=gemini-key')"
            )
            result = call_llm(
                {
                    "llm_provider": "gemini",
                    "llm_model": "gemini-2.5-flash",
                    "llm_api_key": "gemini-key",
                },
                prompt="Explain risk.",
                dry_run=False,
            )

        self.assertFalse(result["ok"])
        self.assertEqual("gemini", result["provider"])
        self.assertIn("LLM provider request failed", result["error"])
        self.assertNotIn("gemini-key", result["error"])
        self.assertIn("key=<redacted>", result["error"])
        self.assertEqual(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=gemini-key",
            post.call_args.args[0],
        )

    def test_llm_output_policy_detects_execution_boundary_violations(self):
        self.assertIn(
            "direct_order_action",
            llm_output_policy_violations('{"action": "place_order", "symbol": "BTCUSDT"}'),
        )
        self.assertIn(
            "direct_order_action",
            llm_output_policy_violations('```json\n{"tool": "submit_order", "symbol": "ETHUSDT"}\n```'),
        )
        self.assertIn(
            "order_execution_claim",
            llm_output_policy_violations("Order executed successfully."),
        )
        self.assertIn(
            "risk_override",
            llm_output_policy_violations("Disable stop loss and override risk checks."),
        )
        self.assertIn(
            "risk_override",
            llm_output_policy_violations('{"risk_controls": {"disable_stop_loss": true}}'),
        )

    def test_llm_output_policy_allows_structured_advice(self):
        self.assertEqual(
            (),
            llm_output_policy_violations(
                '{"action": "advise", "recommendation": "wait", "risk": "keep stop loss enabled"}'
            ),
        )

    def test_llm_call_blocks_output_that_tries_to_execute_orders(self):
        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            post.return_value = _Response(
                {"choices": [{"message": {"content": '{"action": "place_order"}'}}]}
            )
            result = call_llm(
                {
                    "llm_provider": "local",
                    "llm_model": "qwen3:8b",
                    "llm_base_url": "http://127.0.0.1:11434/v1",
                },
                prompt="What should I do?",
                dry_run=False,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["output_policy"]["blocked"])
        self.assertEqual(["direct_order_action"], result["output_policy"]["violations"])

    def test_dry_run_exposes_output_policy_metadata(self):
        result = call_llm(
            {
                "llm_provider": "local",
                "llm_model": "qwen3:8b",
                "llm_base_url": "http://127.0.0.1:11434/v1",
            },
            prompt="Explain risk.",
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["output_policy"]["blocked"])

    def test_dry_run_sanitizes_query_credentials_without_truncating_url(self):
        result = _sanitize_request_for_display(
            {
                "url": "https://example.test/generate?KEY=gemini-key&trace=abc",
                "headers": {"x-api-key": "header-key"},
                "json": {},
            }
        )

        self.assertEqual("https://example.test/generate?KEY=********&trace=abc", result["url"])
        self.assertEqual("********", result["headers"]["x-api-key"])
        self.assertNotIn("gemini-key", str(result))


if __name__ == "__main__":
    unittest.main()
