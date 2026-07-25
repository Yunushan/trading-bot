from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.security import network_url


class NetworkUrlSecurityTests(unittest.TestCase):
    def test_https_and_explicit_loopback_http_are_accepted(self):
        self.assertEqual(
            "https://downloads.example.com/archive.zip?version=1",
            network_url.validate_http_url("https://downloads.example.com/archive.zip?version=1"),
        )
        for value in (
            "http://127.0.0.1:8000",
            "http://[::1]:8000",
            "http://worker.localhost:8000",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    value,
                    network_url.validate_http_url(value, allow_loopback_http=True),
                )

    def test_unsafe_or_ambiguous_urls_are_rejected(self):
        invalid_urls = (
            "http://downloads.example.com/archive.zip",
            "file:///tmp/archive.zip",
            "ftp://downloads.example.com/archive.zip",
            "https://user:secret@downloads.example.com/archive.zip",
            "https://downloads.example.com/archive.zip#section",
            "https://downloads.example.com:invalid/archive.zip",
            "https://downloads.example.com\\@attacker.example/archive.zip",
            "https://downloads.example.com/archive zip",
        )
        for value in invalid_urls:
            with self.subTest(value=value), self.assertRaises(ValueError):
                network_url.validate_http_url(value)

        with self.assertRaisesRegex(ValueError, "query string"):
            network_url.validate_http_url(
                "https://service.example.com?redirect=attacker",
                allow_query=False,
            )

    def test_open_uses_validated_request_and_can_disable_redirects(self):
        response = object()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(network_url.urllib.request, "build_opener", return_value=opener) as build:
            result = network_url.open_validated_url(
                "http://127.0.0.1:8000/api/v1/status",
                timeout=10,
                headers={"Authorization": "Bearer secret"},
                allow_loopback_http=True,
                allow_redirects=False,
            )

        self.assertIs(response, result)
        request = opener.open.call_args.args[0]
        self.assertEqual("http://127.0.0.1:8000/api/v1/status", request.full_url)
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        redirect_handler = build.call_args.args[0]
        self.assertIsNone(
            redirect_handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://other.example.com/status",
            )
        )

    def test_redirect_handler_rejects_https_downgrade(self):
        opener = MagicMock()
        with patch.object(network_url.urllib.request, "build_opener", return_value=opener) as build:
            network_url.open_validated_url("https://downloads.example.com/archive.zip", timeout=10)

        request = opener.open.call_args.args[0]
        redirect_handler = build.call_args.args[0]
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            redirect_handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://downloads.example.com/archive.zip",
            )

    def test_non_finite_and_non_positive_timeouts_are_rejected_before_open(self):
        for timeout in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                network_url.open_validated_url("https://example.com", timeout=timeout)


if __name__ == "__main__":
    unittest.main()
