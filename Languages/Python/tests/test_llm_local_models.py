from __future__ import annotations

# ruff: noqa: E402

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.local_models import (
    delete_ollama_model,
    estimate_ollama_model_size_gb,
    estimate_ollama_model_size_label,
    get_local_model_status,
    ollama_model_storage_hint,
    ollama_model_storage_paths,
    pull_ollama_model,
    start_ollama_server,
)


class _Response:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {}
        self.closed = False

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for item in self.payload.get("lines", []):
            yield item

    def close(self):
        self.closed = True


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
        self.assertIn(".ollama", status.storage_hint)
        self.assertTrue(status.storage_paths)
        self.assertIn("GB", status.estimated_size_label)
        self.assertEqual(5.0, status.recommended_free_disk_gb / 1.25)
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

    def test_unreachable_ollama_reports_start_capability_when_cli_exists(self):
        def fake_get(url, **kwargs):  # noqa: ARG001
            raise OSError("connection refused")

        def fake_which(command):
            return "C:/Program Files/Ollama/ollama.exe" if command == "ollama" else None

        status = get_local_model_status(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_get=fake_get,
            command_finder=fake_which,
        )

        self.assertFalse(status.installed)
        self.assertTrue(status.can_download)
        self.assertTrue(status.can_start)
        self.assertIn("connection refused", status.error)

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

    def test_ollama_pull_streams_progress_when_callback_is_supplied(self):
        calls = []
        progress = []

        def fake_post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response(
                {
                    "lines": [
                        json.dumps({"status": "pulling manifest"}).encode("utf-8"),
                        json.dumps({"status": "downloading", "completed": 5, "total": 10}),
                    ]
                }
            )

        pull_ollama_model(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_post=fake_post,
            progress_callback=progress.append,
        )

        self.assertEqual(calls[0]["url"], "http://127.0.0.1:11434/api/pull")
        self.assertTrue(calls[0]["stream"])
        self.assertEqual(calls[0]["json"], {"model": "qwen3:8b", "stream": True})
        self.assertEqual("pulling manifest", progress[0]["status"])
        self.assertEqual(5, progress[1]["completed"])

    def test_ollama_pull_can_be_cancelled_between_progress_events(self):
        progress = []
        response = _Response(
            {
                "lines": [
                    json.dumps({"status": "downloading", "completed": 5, "total": 10}),
                    json.dumps({"status": "verifying"}),
                ]
            }
        )

        def fake_post(url, **kwargs):  # noqa: ARG001
            return response

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            pull_ollama_model(
                "http://127.0.0.1:11434/v1",
                "qwen3:8b",
                request_post=fake_post,
                progress_callback=progress.append,
                cancel_callback=lambda: len(progress) >= 1,
            )

        self.assertEqual(1, len(progress))
        self.assertEqual("downloading", progress[0]["status"])
        self.assertTrue(response.closed)

    def test_ollama_pull_falls_back_for_request_adapters_without_stream_keyword(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            if "stream" in kwargs:
                raise TypeError("unexpected keyword argument 'stream'")
            return _Response({"lines": [json.dumps({"status": "ok"})]})

        pull_ollama_model(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_post=fake_post,
            progress_callback=lambda _payload: None,
        )

        self.assertEqual(2, len(calls))
        self.assertNotIn("stream", calls[1])

    def test_ollama_delete_uses_native_api_without_v1_suffix(self):
        calls = []

        def fake_delete(url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Response({})

        delete_ollama_model(
            "http://127.0.0.1:11434/v1",
            "qwen3:8b",
            request_delete=fake_delete,
        )

        self.assertEqual(calls[0]["url"], "http://127.0.0.1:11434/api/delete")
        self.assertEqual(calls[0]["json"], {"model": "qwen3:8b"})

    def test_start_ollama_server_invokes_serve_when_cli_exists(self):
        calls = []

        def fake_which(command):
            return "C:/Program Files/Ollama/ollama.exe" if command == "ollama" else None

        def fake_popen(args, **kwargs):
            calls.append({"args": args, **kwargs})
            return object()

        result = start_ollama_server(
            "http://127.0.0.1:11434/v1",
            command_finder=fake_which,
            popen=fake_popen,
        )

        self.assertTrue(result.started)
        self.assertEqual(result.server_kind, "ollama")
        self.assertEqual(calls[0]["args"], ["C:/Program Files/Ollama/ollama.exe", "serve"])

    def test_start_ollama_server_reports_missing_cli(self):
        result = start_ollama_server(
            "http://127.0.0.1:11434/v1",
            command_finder=lambda _command: None,
        )

        self.assertFalse(result.started)
        self.assertIn("not installed", result.error)

    def test_ollama_storage_and_size_hints_are_user_visible(self):
        self.assertIn("outside this project", ollama_model_storage_hint())
        self.assertTrue(ollama_model_storage_paths()[0])
        self.assertIn("5 GB", estimate_ollama_model_size_label("qwen3:8b"))
        self.assertEqual(5.0, estimate_ollama_model_size_gb("qwen3:8b"))
        self.assertIn("2 GB", estimate_ollama_model_size_label("qwen3:1.7b"))
        self.assertEqual(20.0, estimate_ollama_model_size_gb("qwen3:32b"))
        self.assertIn("varies", estimate_ollama_model_size_label("custom-local-model"))

    def test_ollama_storage_path_honors_ollama_models_env(self):
        with mock.patch.dict("os.environ", {"OLLAMA_MODELS": "~/custom-ollama-models"}, clear=False):
            path = ollama_model_storage_paths()[0].replace("\\", "/")

        self.assertTrue(path.endswith("/custom-ollama-models"))

    def test_ollama_status_warns_when_disk_space_is_low(self):
        def fake_get(url, **kwargs):  # noqa: ARG001
            return _Response({"data": []})

        with mock.patch("app.integrations.llm.local_models.shutil.disk_usage") as disk_usage:
            disk_usage.return_value = mock.Mock(free=1 * 1024 ** 3)
            status = get_local_model_status(
                "http://127.0.0.1:11434/v1",
                "qwen3:8b",
                request_get=fake_get,
            )

        self.assertEqual(1.0, round(status.free_disk_gb or 0, 1))
        self.assertEqual(6.25, status.recommended_free_disk_gb)
        self.assertIn("Low disk space", status.disk_space_warning)


if __name__ == "__main__":
    unittest.main()
