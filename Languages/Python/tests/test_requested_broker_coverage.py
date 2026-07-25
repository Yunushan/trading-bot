from __future__ import annotations

import unittest

from app.settings.exchange_support import (
    BROKER_INTEGRATION_DISPOSITIONS,
    REQUESTED_BROKER_TARGETS,
    SUPPORTED_BROKERS,
    broker_integration_coverage,
    build_exchange_support_payload,
    build_requested_broker_coverage,
)


class RequestedBrokerCoverageTests(unittest.TestCase):
    def test_every_requested_name_has_an_explicit_source_backed_outcome(self):
        coverage = build_requested_broker_coverage()

        self.assertEqual(49, len(REQUESTED_BROKER_TARGETS))
        self.assertEqual(49, len(coverage))
        self.assertEqual(44, sum(item["implemented"] is True for item in coverage))
        self.assertEqual(
            39,
            sum(item["implemented"] is True and item["forex_order_routing_supported"] is True for item in coverage),
        )
        self.assertEqual(
            5,
            sum(item["implemented"] is True and item["forex_order_routing_supported"] is False for item in coverage),
        )

        for item in coverage:
            with self.subTest(requested_name=item["requested_name"]):
                self.assertTrue(str(item["official_source"]).startswith("https://"))
                self.assertNotEqual("unknown-broker-request", item["status"])
                if item["implemented"]:
                    self.assertIn(item["canonical_name"], SUPPORTED_BROKERS)
                    self.assertTrue(item["backend"])
                    self.assertTrue(item["live_evidence_required"])
                else:
                    self.assertIn(item["canonical_name"], BROKER_INTEGRATION_DISPOSITIONS)
                    self.assertNotIn(item["canonical_name"], SUPPORTED_BROKERS)
                    self.assertTrue(str(item["status"]).startswith("blocked-"))
                    self.assertTrue(item["blocking_requirement"])

    def test_request_typos_and_provider_names_resolve_to_canonical_routes(self):
        expected = {
            "cmc markes": "CMC Markets",
            "philipsecurities": "PhillipCapital (Phillip Nova)",
            "ai gold": "AI Gold Securities",
            "forex.com": "FOREX.com",
        }
        for requested_name, canonical_name in expected.items():
            with self.subTest(requested_name=requested_name):
                item = broker_integration_coverage(requested_name)
                self.assertEqual(canonical_name, item["canonical_name"])
                self.assertTrue(item["implemented"])

    def test_private_or_proprietary_routes_are_not_falsely_reported_supported(self):
        self.assertEqual(
            {"Mitrade", "AXPM", "Jefferies", "Marex", "Spreadex"},
            set(BROKER_INTEGRATION_DISPOSITIONS),
        )
        for broker in BROKER_INTEGRATION_DISPOSITIONS:
            with self.subTest(broker=broker):
                coverage = broker_integration_coverage(broker)
                support = build_exchange_support_payload(
                    config={
                        "selected_exchange": "",
                        "connector_backend": "Unknown",
                        "selected_forex_broker": broker,
                    }
                )
                self.assertFalse(coverage["implemented"])
                self.assertFalse(support["broker_supported"])
                self.assertFalse(support["order_execution_supported"])


if __name__ == "__main__":
    unittest.main()
