from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.clients import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
