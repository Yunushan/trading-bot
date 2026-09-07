from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import requests

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.clients import call_llm  # noqa: E402
from app.integrations.llm.discovery import discover_llm_models  # noqa: E402
from app.integrations.llm.local_models import (  # noqa: E402
    delete_ollama_model,
    get_local_model_status,
    pull_ollama_model,
)


_KEY = "synthetic-redirect-test-key"
_CONTEXT = "synthetic-private-local-context"
_REDIRECTS = (301, 302, 303, 307, 308)


@contextmanager
def _redirect_transport(status_code, location):
    """Keep Requests' redirect engine real while forbidding actual network I/O."""
    sent = []
    responses = []

    def send(_adapter, request, **_kwargs):
        sent.append(request)
        response = requests.Response()
        response.request = request
        response.url = request.url
        response.status_code = status_code if len(sent) == 1 else 200
        if len(sent) == 1:
            response.headers["Location"] = location
        response._content = json.dumps({
            "choices": [{"message": {"content": "Advisory text."}}],
            "content": [{"type": "text", "text": "Advisory text."}],
            "data": [{"id": "redirected-model"}],
            "error": _KEY,
        }).encode()
        response.close = mock.Mock(wraps=response.close)
        response.json = mock.Mock(wraps=response.json)
        responses.append(response)
        return response

    with (
        tempfile.TemporaryDirectory() as home,
        mock.patch("requests.adapters.HTTPAdapter.send", new=send),
        mock.patch("requests.sessions.get_netrc_auth", return_value=None),
        mock.patch.dict("os.environ", {"HOME": home, "USERPROFILE": home}, clear=True),
        mock.patch("socket.socket.connect", side_effect=AssertionError("Network is forbidden")),
        mock.patch("socket.create_connection", side_effect=AssertionError("Network is forbidden")),
    ):
        yield sent, responses


class LLMRedirectSafetyTests(unittest.TestCase):
    def test_public_network_opt_in_does_not_authorize_provider_redirects(self):
        for provider, style in (("openai", "chat-completions"), ("openai", "responses"), ("anthropic", "messages"), ("gemini", "gemini")):
            for status in _REDIRECTS:
                with self.subTest(provider=provider, style=style, status=status):
                    with _redirect_transport(status, f"https://unapproved.example.invalid/{_KEY}") as (sent, responses):
                        result = call_llm({
                            "llm_provider": provider,
                            "llm_api_style": style,
                            "llm_model": "future-user-selected-model",
                            "llm_api_key": _KEY,
                            "llm_allow_public_network": True,
                        }, prompt="Explain risk.", dry_run=False)
                    self.assertEqual(1, len(sent))
                    self.assertFalse(result["ok"])
                    self.assertEqual(status, result["status_code"])
                    self.assertNotIn(_KEY, json.dumps(result))
                    responses[0].json.assert_not_called()
                    responses[0].close.assert_called()

    def test_chat_rejects_redirects_before_forwarding_context_or_credentials(self):
        for style in ("chat-completions", "responses", "messages", "gemini"):
            for status in _REDIRECTS:
                for location in (
                    "/same-origin-redirect",
                    "https://unapproved.example.invalid/redirect",
                    "http://unapproved.example.invalid/redirect",
                ):
                    with self.subTest(style=style, status=status, location=location):
                        with _redirect_transport(status, location) as (sent, responses):
                            result = call_llm({
                                "llm_provider": "local",
                                "llm_api_style": style,
                                "llm_base_url": "http://127.0.0.1:11434",
                                "llm_model": "local-test-model",
                                "llm_api_key": _KEY,
                                "llm_allow_public_network": False,
                            }, prompt="Explain risk.", context={"custom": _CONTEXT}, dry_run=False)
                        self.assertEqual(1, len(sent))
                        self.assertFalse(result["ok"])
                        self.assertEqual(status, result["status_code"])
                        self.assertIn("redirect", result["error"].lower())
                        self.assertNotIn(_KEY, json.dumps(result))
                        self.assertNotIn(_CONTEXT, json.dumps(result))
                        responses[0].json.assert_not_called()
                        responses[0].close.assert_called()

    def test_discovery_rejects_redirects_and_preserves_catalog_models(self):
        for provider in ("local", "kilo", "anthropic", "gemini"):
            for status in _REDIRECTS:
                with self.subTest(provider=provider, status=status):
                    with _redirect_transport(status, f"https://unapproved.example.invalid/{_KEY}") as (sent, responses):
                        result = discover_llm_models({
                            "llm_provider": provider,
                            "llm_base_url": "http://127.0.0.1:11434",
                            "llm_model": "retained-user-model",
                            "llm_api_key": _KEY,
                        })
                    self.assertEqual(1, len(sent))
                    self.assertFalse(result["ok"])
                    self.assertEqual(0, result["dynamic_count"])
                    self.assertIn("retained-user-model", {item["id"] for item in result["models"]})
                    self.assertNotIn("redirected-model", {item["id"] for item in result["models"]})
                    self.assertNotIn(_KEY, json.dumps(result))
                    self.assertIn("redirect", result["error"].lower())
                    responses[0].json.assert_not_called()
                    responses[0].close.assert_called()

    def test_local_model_status_cannot_follow_redirect_to_remote_server(self):
        for status in _REDIRECTS:
            with self.subTest(status=status):
                with _redirect_transport(status, "https://unapproved.example.invalid/models") as (sent, responses):
                    result = get_local_model_status("http://127.0.0.1:11434/v1", "redirected-model")
                self.assertEqual(1, len(sent))
                self.assertFalse(result.installed)
                self.assertIn("redirect", result.error.lower())
                responses[0].json.assert_not_called()
                responses[0].close.assert_called()

    def test_local_model_mutations_never_follow_redirects_or_report_success(self):
        for operation in ("pull", "streaming-pull", "delete"):
            for status in _REDIRECTS:
                with self.subTest(operation=operation, status=status):
                    progress = []
                    with _redirect_transport(status, "https://unapproved.example.invalid/mutation") as (sent, responses):
                        with self.assertRaisesRegex(ValueError, "redirect"):
                            if operation == "delete":
                                delete_ollama_model("http://127.0.0.1:11434", "test-model")
                            else:
                                pull_ollama_model(
                                    "http://127.0.0.1:11434", "test-model",
                                    progress_callback=progress.append if operation == "streaming-pull" else None,
                                )
                    self.assertEqual(1, len(sent))
                    self.assertEqual([], progress)
                    responses[0].json.assert_not_called()
                    responses[0].close.assert_called()

    def test_non_followable_3xx_is_not_a_successful_chat_response(self):
        for status in (300, 304, 305, 306, 399):
            with self.subTest(status=status):
                with _redirect_transport(status, "/unused") as (sent, responses):
                    result = call_llm({"llm_provider": "local", "llm_model": "test-model"}, prompt="Explain.", dry_run=False)
                self.assertEqual(1, len(sent))
                self.assertFalse(result["ok"])
                self.assertEqual(status, result["status_code"])
                responses[0].json.assert_not_called()
                responses[0].close.assert_called()


if __name__ == "__main__":
    unittest.main()
