from __future__ import annotations

import unittest

from app.integrations.llm.local_models import get_local_model_status, pull_ollama_model


class _Response:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class LocalLLMModelTests(unittest.TestCase):
    def test_ollama_status_detects_installed_model(self):
        calls = []

        def fake_get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response({"data": [{"id": "qwen3:8b"}, {"id": "llama3.3"}]})

        status = get_local_model_status(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_get=fake_get,
        )

        self.assertTrue(status.installed)
        self.assertTrue(status.can_download)
        self.assertEqual(status.server_kind, "ollama")
        self.assertEqual(status.available_models, ("llama3.3", "qwen3:8b"))
        self.assertEqual(calls[0]["url"], "http://127.0.0.1:11434/v1/models")

    def test_missing_non_ollama_model_cannot_auto_download(self):
        def fake_get(url, **kwargs):  # noqa: ARG001
            return _Response({"data": [{"id": "loaded-local-model"}]})

        status = get_local_model_status(
            "http://127.0.0.1:1234/v1",
            "qwen3:8b",
            request_get=fake_get,
        )

        self.assertFalse(status.installed)
        self.assertFalse(status.can_download)
        self.assertEqual(status.server_kind, "openai-compatible")

    def test_ollama_pull_uses_native_api_without_v1_suffix(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response({"status": "success"})

        pull_ollama_model(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_post=fake_post,
        )

        self.assertEqual(calls[0]["url"], "http://127.0.0.1:11434/api/pull")
        self.assertEqual(calls[0]["json"], {"model": "qwen3:8b", "stream": False})


if __name__ == "__main__":
    unittest.main()
