from __future__ import annotations

import unittest
from pathlib import Path

from app.integrations.brokers.metatrader4_bridge import (
    MT4_BRIDGE_ALLOWED_OPERATIONS,
    MT4_BRIDGE_METAQUOTES_SOURCES,
    MT4_BRIDGE_PROVIDERS,
)
from app.settings.exchange_support import METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES


class MetaTrader4BridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[3]
        cls.ea_path = cls.repo_root / "Languages" / "MQL4" / "Experts" / "TradingBotBridge.mq4"
        cls.source = cls.ea_path.read_text(encoding="utf-8")

    def test_companion_expert_advisor_covers_the_python_protocol(self):
        self.assertTrue(self.ea_path.is_file())
        self.assertIn("#property strict", self.source)
        self.assertIn("X-MT4-Bridge-Token", self.source)
        self.assertIn("WebRequest(", self.source)
        self.assertIn("payload_json", self.source)
        for operation in MT4_BRIDGE_ALLOWED_OPERATIONS:
            with self.subTest(operation=operation):
                self.assertIn(f'operation == "{operation}"', self.source)

    def test_companion_expert_advisor_has_independent_live_and_replay_guards(self):
        self.assertIn("input bool EnableLiveOrders = false", self.source)
        self.assertIn("if(IsMutation(operation) && !EnableLiveOrders)", self.source)
        guard_offset = self.source.index('SaveReceipt(command_id, "failed", 9001')
        execution_offset = self.source.index("ExecuteCommand(response")
        self.assertLess(guard_offset, execution_offset)
        self.assertIn("LoadReceipt(command_id", self.source)
        self.assertIn("FILE_COMMON", self.source)

    def test_companion_decodes_form_values_as_utf8_bytes(self):
        self.assertIn("uchar output_bytes[]", self.source)
        self.assertIn(
            "CharArrayToString(output_bytes, 0, output_size, CP_UTF8)",
            self.source,
        )

    def test_provider_and_metaquotes_sources_are_official_https_pages(self):
        self.assertEqual(set(MT4_BRIDGE_PROVIDERS), set(METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES))
        for source in (*METATRADER4_BRIDGE_BROKER_OFFICIAL_SOURCES.values(), *MT4_BRIDGE_METAQUOTES_SOURCES):
            with self.subTest(source=source):
                self.assertTrue(source.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
