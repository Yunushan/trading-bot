from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.clients import call_llm  # noqa: E402
from app.integrations.llm.discovery import discover_llm_models  # noqa: E402
from app.security.network_url import url_uses_public_network, validate_http_url  # noqa: E402


class LLMUrlSecurityTests(unittest.TestCase):
    def test_inference_rejects_unsafe_base_urls_before_any_provider_request(self):
        provider_styles = (
            ("openai", "chat-completions"),
            ("openai", "responses"),
            ("anthropic", "messages"),
            ("gemini", "gemini"),
            ("local", "chat-completions"),
        )
        unsafe_urls = (
            "http://public.example.test/v1",
            "https://user:secret@example.test/v1",
            "https://example.test/v1#fragment",
            "https://example.test/v1 has-space",
            "https://example.test:",
            "https://[::1",
        )

        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            for provider, api_style in provider_styles:
                for base_url in unsafe_urls:
                    with self.subTest(provider=provider, api_style=api_style, base_url=base_url):
                        with self.assertRaises(ValueError):
                            call_llm(
                                {
                                    "llm_provider": provider,
                                    "llm_api_style": api_style,
                                    "llm_model": "synthetic-model",
                                    "llm_api_key": "synthetic-key",
                                    "llm_base_url": base_url,
                                    # Public-network consent must not weaken HTTPS.
                                    "llm_allow_public_network": True,
                                },
                                prompt="Explain the risk.",
                                dry_run=False,
                            )

        post.assert_not_called()

    def test_discovery_rejects_unsafe_base_urls_before_get(self):
        provider_styles = (
            ("openai", "chat-completions"),
            ("anthropic", "messages"),
            ("gemini", "gemini"),
            ("local", "chat-completions"),
        )
        unsafe_urls = (
            "http://public.example.test/v1",
            "https://user:secret@example.test/v1",
            "https://example.test/v1#fragment",
            "https://example.test/v1 has-space",
            "https://example.test:",
            "https://[::1",
        )

        with mock.patch("app.integrations.llm.discovery.requests.get") as get:
            for provider, api_style in provider_styles:
                for base_url in unsafe_urls:
                    with self.subTest(provider=provider, api_style=api_style, base_url=base_url):
                        result = discover_llm_models(
                            {
                                "llm_provider": provider,
                                "llm_api_style": api_style,
                                "llm_model": "synthetic-model",
                                "llm_api_key": "synthetic-key",
                                "llm_base_url": base_url,
                                "llm_allow_public_network": True,
                            }
                        )
                        self.assertFalse(result["ok"])
                        self.assertEqual(0, result["dynamic_count"])
                        self.assertTrue(result["error"])

        get.assert_not_called()

    def test_loopback_http_and_approved_https_remain_supported(self):
        self.assertEqual(
            "http://worker.localhost:1234/v1",
            validate_http_url(
                "http://worker.localhost:1234/v1",
                field_name="LLM base URL",
                allow_loopback_http=True,
            ),
        )
        self.assertFalse(url_uses_public_network("http://worker.localhost:1234/v1"))
        self.assertFalse(url_uses_public_network("https://192.168.1.20:8443/v1"))
        self.assertTrue(url_uses_public_network("https://approved.example.test/v1"))

        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            response = mock.Mock(status_code=200)
            response.headers = {}
            response.iter_content.return_value = [
                json.dumps({"choices": [{"message": {"content": "Advisory."}}]}).encode("utf-8")
            ]
            post.return_value = response
            result = call_llm(
                {
                    "llm_provider": "open-source",
                    "llm_model": "synthetic-model",
                    "llm_base_url": "https://approved.example.test/v1",
                    "llm_allow_public_network": True,
                },
                prompt="Explain the risk.",
                dry_run=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual("https://approved.example.test/v1/chat/completions", post.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
