from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import requests

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.llm.clients import build_llm_chat_request, call_llm  # noqa: E402
from app.integrations.llm.discovery import discover_llm_models  # noqa: E402
from app.integrations.llm.transport_limits import (  # noqa: E402
    LLMResourceLimitError,
    MAX_LLM_CONTEXT_BYTES,
    MAX_LLM_DISCOVERY_BYTES,
    MAX_LLM_PROMPT_BYTES,
    MAX_LLM_REQUEST_BYTES,
    MAX_LLM_RESPONSE_BYTES,
    MAX_LLM_HEADER_BYTES,
    MAX_LLM_SYSTEM_PROMPT_BYTES,
)


_LOCAL = {"llm_provider": "local", "llm_model": "local-test-model"}


class _StreamResponse:
    status_code = 200

    def __init__(self, chunks, *, status_code=200, headers=None):
        self.chunks = chunks
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False
        self.json = mock.Mock(side_effect=AssertionError("The response must be streamed."))

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        yield from self.chunks

    def raise_for_status(self):
        return None

    def close(self):
        self.closed = True


class LLMResourceBoundsTests(unittest.TestCase):
    def test_prompt_and_advanced_json_rejected_before_transport(self):
        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            prompt_result = call_llm(_LOCAL, prompt="x" * (MAX_LLM_PROMPT_BYTES + 1), dry_run=False)
            multibyte_result = call_llm(_LOCAL, prompt="é" * (MAX_LLM_PROMPT_BYTES // 2 + 1), dry_run=False)
            invalid_utf8_result = call_llm(_LOCAL, prompt="\ud800", dry_run=False)
            system_result = call_llm(
                _LOCAL, prompt="Explain risk.", system_prompt="x" * (MAX_LLM_SYSTEM_PROMPT_BYTES + 1), dry_run=False
            )
            option_result = call_llm(
                {**_LOCAL, "llm_request_options": {"metadata": "x" * MAX_LLM_REQUEST_BYTES}},
                prompt="Explain risk.",
                dry_run=False,
            )
        self.assertFalse(prompt_result["ok"])
        self.assertIn("prompt", prompt_result["error"].lower())
        self.assertFalse(multibyte_result["ok"])
        self.assertFalse(invalid_utf8_result["ok"])
        self.assertIn("UTF-8", invalid_utf8_result["error"])
        self.assertFalse(system_result["ok"])
        self.assertIn("system prompt", system_result["error"].lower())
        self.assertFalse(option_result["ok"])
        self.assertIn("request", option_result["error"].lower())
        post.assert_not_called()

    def test_context_has_absolute_byte_cap_without_model_window(self):
        request = build_llm_chat_request(
            {**_LOCAL, "llm_context_window": 0},
            prompt="Explain risk.",
            context={"large": "x" * (MAX_LLM_CONTEXT_BYTES * 2)},
        )
        encoded = json.dumps(request["json"], ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(len(encoded), MAX_LLM_REQUEST_BYTES)
        self.assertIn("context_truncated", str(request["json"]))

    def test_cyclic_json_is_bounded_before_encoding(self):
        cyclic_list = []
        cyclic_list.append(cyclic_list)
        with mock.patch("app.integrations.llm.clients.requests.post") as post:
            options_result = call_llm(
                {**_LOCAL, "llm_request_options": {"metadata": cyclic_list}},
                prompt="Explain risk.",
                dry_run=False,
            )
        self.assertFalse(options_result["ok"])
        self.assertIn("cycle", options_result["error"].lower())
        post.assert_not_called()

        context_request = build_llm_chat_request(
            _LOCAL, prompt="Explain risk.", context={"cyclic": cyclic_list}
        )
        self.assertIn("context_truncated", str(context_request["json"]))

    def test_oversized_credentials_are_rejected_before_transport(self):
        config = {**_LOCAL, "llm_api_key": "synthetic-key-" + "x" * MAX_LLM_HEADER_BYTES}
        with (
            mock.patch("app.integrations.llm.clients.requests.post") as post,
            mock.patch("app.integrations.llm.discovery.requests.get") as get,
        ):
            call_result = call_llm(config, prompt="Explain risk.", dry_run=False)
            discovery_result = discover_llm_models(config)
        self.assertFalse(call_result["ok"])
        self.assertFalse(discovery_result["ok"])
        self.assertIn("headers", call_result["error"].lower())
        self.assertIn("headers", discovery_result["error"].lower())
        self.assertNotIn("synthetic-key-", str(call_result) + str(discovery_result))
        post.assert_not_called()
        get.assert_not_called()

    def test_response_content_length_and_stream_are_bounded_and_closed(self):
        oversized_header = _StreamResponse([], headers={"Content-Length": str(MAX_LLM_RESPONSE_BYTES + 1)})
        oversized_stream = _StreamResponse([b"x" * (MAX_LLM_RESPONSE_BYTES + 1)])
        with mock.patch("app.integrations.llm.clients.requests.post", side_effect=[oversized_header, oversized_stream]) as post:
            header_result = call_llm(_LOCAL, prompt="Explain risk.", dry_run=False)
            stream_result = call_llm(_LOCAL, prompt="Explain risk.", dry_run=False)
        self.assertFalse(header_result["ok"])
        self.assertFalse(stream_result["ok"])
        self.assertIn("response", header_result["error"].lower())
        self.assertIn("response", stream_result["error"].lower())
        self.assertTrue(oversized_header.closed)
        self.assertTrue(oversized_stream.closed)
        self.assertTrue(post.call_args.kwargs["stream"])

    def test_discovery_body_is_bounded_and_catalog_is_retained(self):
        response = _StreamResponse([b"x" * (MAX_LLM_DISCOVERY_BYTES + 1)])
        with mock.patch("app.integrations.llm.discovery.requests.get", return_value=response) as get:
            result = discover_llm_models(_LOCAL)
        self.assertFalse(result["ok"])
        self.assertEqual(0, result["dynamic_count"])
        self.assertIn("local-test-model", {item["id"] for item in result["models"]})
        self.assertIn("response", result["error"].lower())
        self.assertTrue(response.closed)
        self.assertTrue(get.call_args.kwargs["stream"])

    def test_configured_hour_timeout_is_capped_with_connect_and_read_bounds(self):
        response = _StreamResponse([b'{"choices":[{"message":{"content":"Wait."}}]}'])
        with mock.patch("app.integrations.llm.clients.requests.post", return_value=response) as post:
            result = call_llm({**_LOCAL, "llm_timeout_seconds": 3600}, prompt="Explain risk.", dry_run=False)
        self.assertTrue(result["ok"])
        connect_timeout, read_timeout = post.call_args.kwargs["timeout"]
        self.assertLessEqual(connect_timeout, 10)
        self.assertLessEqual(read_timeout, 15)
        self.assertEqual(120, build_llm_chat_request(
            {**_LOCAL, "llm_timeout_seconds": 3600}, prompt="Explain risk."
        )["timeout_seconds"])
        self.assertEqual("local-test-model", json.loads(post.call_args.kwargs["data"])["model"])
        self.assertTrue(response.closed)

    def test_never_ending_stream_hits_total_deadline(self):
        response = _StreamResponse((b" " for _ in range(100)))
        with (
            mock.patch("app.integrations.llm.clients.requests.post", return_value=response),
            mock.patch(
                "app.integrations.llm.transport_limits.check_deadline",
                side_effect=[None, None, None, LLMResourceLimitError("LLM response exceeded its total deadline.")],
            ),
        ):
            result = call_llm(_LOCAL, prompt="Explain risk.", dry_run=False, timeout=1)
        self.assertFalse(result["ok"])
        self.assertIn("deadline", result["error"].lower())
        self.assertTrue(response.closed)

    def test_wall_deadline_returns_while_blocked_transport_keeps_its_slot(self):
        entered = threading.Event()
        release = threading.Event()
        response = _StreamResponse([b'{"choices":[{"message":{"content":"Wait."}}]}'])
        slots = threading.BoundedSemaphore(1)

        def blocked_post(*args, **kwargs):
            entered.set()
            release.wait(timeout=5)
            return response

        with (
            mock.patch("app.integrations.llm.transport_limits._call_slots", slots),
            mock.patch("app.integrations.llm.clients.requests.post", side_effect=blocked_post) as post,
        ):
            start = time.monotonic()
            timed_out = call_llm(_LOCAL, prompt="First.", dry_run=False, timeout=1)
            elapsed = time.monotonic() - start
            self.assertTrue(entered.is_set())
            self.assertFalse(timed_out["ok"])
            self.assertIn("deadline", timed_out["error"].lower())
            self.assertLess(elapsed, 2)
            busy = call_llm(_LOCAL, prompt="Second.", dry_run=False)
            self.assertFalse(busy["ok"])
            self.assertIn("capacity", busy["error"].lower())
            self.assertEqual(1, post.call_count)
            release.set()
            for _ in range(100):
                if slots.acquire(blocking=False):
                    slots.release()
                    break
                time.sleep(0.01)
            else:
                self.fail("The transport did not release capacity after it ended.")
        self.assertTrue(response.closed)

    def test_concurrent_call_rejected_and_capacity_released_after_error(self):
        entered = threading.Event()
        release = threading.Event()
        result_holder = []

        class BlockingResponse(_StreamResponse):
            def iter_content(self, chunk_size):
                entered.set()
                release.wait(timeout=5)
                raise requests.ReadTimeout("synthetic timeout")
                yield b""  # pragma: no cover

        response = BlockingResponse([])
        success = _StreamResponse([b'{"choices":[{"message":{"content":"Wait."}}]}'])
        with (
            mock.patch("app.integrations.llm.transport_limits._call_slots", threading.BoundedSemaphore(1)),
            mock.patch("app.integrations.llm.clients.requests.post", side_effect=[response, success]) as post,
            mock.patch("app.integrations.llm.discovery.requests.get") as get,
        ):
            worker = threading.Thread(
                target=lambda: result_holder.append(call_llm(_LOCAL, prompt="First.", dry_run=False))
            )
            worker.start()
            self.assertTrue(entered.wait(timeout=5))
            busy = call_llm(_LOCAL, prompt="Second.", dry_run=False)
            busy_discovery = discover_llm_models(_LOCAL)
            release.set()
            worker.join(timeout=5)
            after_error = call_llm(_LOCAL, prompt="Third.", dry_run=False)
        self.assertFalse(busy["ok"])
        self.assertIn("capacity", busy["error"].lower())
        self.assertFalse(busy_discovery["ok"])
        self.assertIn("capacity", busy_discovery["error"].lower())
        get.assert_not_called()
        self.assertFalse(result_holder[0]["ok"])
        self.assertTrue(response.closed)
        self.assertTrue(after_error["ok"])
        self.assertEqual(2, post.call_count)

    def test_cancellation_closes_response_and_releases_capacity(self):
        class CancelledResponse(_StreamResponse):
            def iter_content(self, chunk_size):
                raise KeyboardInterrupt()
                yield b""  # pragma: no cover

        cancelled = CancelledResponse([])
        success = _StreamResponse([b'{"choices":[{"message":{"content":"Wait."}}]}'])
        with (
            mock.patch("app.integrations.llm.transport_limits._call_slots", threading.BoundedSemaphore(1)),
            mock.patch("app.integrations.llm.clients.requests.post", side_effect=[cancelled, success]),
        ):
            with self.assertRaises(KeyboardInterrupt):
                call_llm(_LOCAL, prompt="First.", dry_run=False)
            after_cancel = call_llm(_LOCAL, prompt="Second.", dry_run=False)
        self.assertTrue(cancelled.closed)
        self.assertTrue(after_cancel["ok"])


if __name__ == "__main__":
    unittest.main()
