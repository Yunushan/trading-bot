from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.security.redaction import REDACTED_TEXT, is_sensitive_key, redact_text, redact_value  # noqa: E402


class SecretRedactionTests(unittest.TestCase):
    def test_redact_value_masks_nested_secret_keys_and_secret_text(self):
        payload = {
            "api_key": "exchange-key",
            "safe": "BTCUSDT",
            "nested": {
                "authorization": "Bearer auth-token",
                "message": "signature=signature-value api_secret=exchange-secret",
            },
            "items": [
                {"llm_api_key": "llm-key"},
                "token=plain-token",
            ],
        }

        redacted = redact_value(payload)
        rendered = json.dumps(redacted, sort_keys=True)

        self.assertEqual(REDACTED_TEXT, redacted["api_key"])
        self.assertEqual("BTCUSDT", redacted["safe"])
        self.assertIn(REDACTED_TEXT, rendered)
        for secret in ("exchange-key", "auth-token", "signature-value", "exchange-secret", "llm-key", "plain-token"):
            self.assertNotIn(secret, rendered)

    def test_redact_text_masks_assignments_and_bearer_tokens(self):
        text = (
            "Authorization: Bearer header-token api_key=exchange-key "
            "api_secret='exchange-secret' signature=signature-value token:plain-token"
        )

        redacted = redact_text(text)

        self.assertIn("Authorization: Bearer <redacted>", redacted)
        self.assertIn("api_key=<redacted>", redacted)
        self.assertIn("api_secret='<redacted>'", redacted)
        self.assertIn("signature=<redacted>", redacted)
        self.assertIn("token:<redacted>", redacted)
        for secret in ("header-token", "exchange-key", "exchange-secret", "signature-value", "plain-token"):
            self.assertNotIn(secret, redacted)

    def test_sensitive_key_detection_avoids_non_secret_api_metadata(self):
        self.assertTrue(is_sensitive_key("api_secret"))
        self.assertTrue(is_sensitive_key("X-MBX-APIKEY"))
        self.assertTrue(is_sensitive_key("llm_api_key"))
        self.assertFalse(is_sensitive_key("api_key_env"))
        self.assertFalse(is_sensitive_key("api_key_present"))
        self.assertFalse(is_sensitive_key("api_base_path"))
        self.assertFalse(is_sensitive_key("selected_exchange"))


if __name__ == "__main__":
    unittest.main()
