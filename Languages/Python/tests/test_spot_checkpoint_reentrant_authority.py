"""Actual owner revocation during nested protected reads cannot persist intent transitions."""
from copy import deepcopy
from contextlib import contextmanager
import unittest
from unittest.mock import patch

import test_spot_checkpoint_product_integration as product_fixtures
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders.spot_execution_owner import owner_marker_path
from app.settings.live_safety import LiveTradingSafetyError


class SpotCheckpointReentrantAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.product = product_fixtures.SpotCheckpointProductIntegrationTests("runTest")
        self.product.setUp()
        self.addCleanup(self.product.doCleanups)
        self.f, self.backend = self.product.f, self.product.backend
        self.observed = {}

    def published(self, *, confirmed=False):
        account = self.product.fresh()
        record = self.product.author_buy(account)
        self.assertTrue(self.product.publish_buy(account, record))
        if confirmed:
            with self.f.account_home(account):
                account.wrapper._mark_order_intent_portfolio_reconciled(
                    record["client_order_id"], portfolio_signature=self.product.fill["signature"],
                    portfolio_quantity=self.product.fill["net_qty"],
                )
        return account, record

    def before(self, account):
        return (self.f.path.read_bytes(), account.path.read_bytes(),
                deepcopy(self.backend.store), list(self.backend.put_calls))

    @contextmanager
    def close_during_read(self, account, *, selected_read):
        observed = {"reads": 0, "closed": False, "marker_after_close": None}
        def read(*, scope, account: str):
            value = self.backend.get(scope=scope, account=account)
            observed["reads"] += 1
            if observed["reads"] == selected_read:
                owner.close()
                observed["closed"] = True
                observed["marker_after_close"] = marker.read_bytes()
            return value
        owner, marker = account.owner, owner_marker_path(account.path)
        self.assertIsNotNone(owner.fd)
        with patch.object(core.credential_store, "get_secret", side_effect=read):
            yield observed
        self.assertTrue(observed["closed"], "The intended protected-read callback was not reached")
        self.assertIsNone(owner.fd)
        self.assertEqual(observed["marker_after_close"], marker.read_bytes(),
                         "The legitimate close marker changed again after revocation")
        self.observed = {"selected_read": selected_read, "protected_reads": observed["reads"],
                         "owner_closed": True, "post_close_marker_preserved": True,
                         "order_attempts": len(self.f.order_calls)}

    def assert_unchanged(self, account, before):
        self.assertEqual(before, self.before(account),
                         "Inventory, full intent bytes or protected state changed after owner revocation")
        self.assertEqual([], self.f.order_calls)

    def test_nested_buy_confirmation_read_revocation_preserves_portfolio_marker(self):
        account, record = self.published()
        before = self.before(account)
        self.assertFalse(self.f.ledger(account)["intents"][record["client_order_id"]]["portfolio_reconciled"])
        with self.f.account_home(account), self.close_during_read(account, selected_read=4):
            with self.assertRaises(LiveTradingSafetyError):
                account.wrapper._mark_order_intent_portfolio_reconciled(
                    record["client_order_id"], portfolio_signature=self.product.fill["signature"],
                    portfolio_quantity=self.product.fill["net_qty"],
                )
        self.assert_unchanged(account, before)
        self.assertFalse(self.f.ledger(account)["intents"][record["client_order_id"]]["portfolio_reconciled"])

    def test_direct_buy_admission_read_revocation_does_not_create_pending_intent(self):
        account, _record = self.published(confirmed=True)
        params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.02",
                  "newClientOrderId": "reentrant-admission-buy"}
        self.assertIsNone(getattr(account.wrapper, "_desktop_spot_entry_capture", None))
        before = self.before(account)
        with self.f.account_home(account), self.close_during_read(account, selected_read=1):
            with self.assertRaises(LiveTradingSafetyError):
                account.wrapper._begin_order_intent(params, market="spot", source="offline-reentrant-control")
        self.assert_unchanged(account, before)
        self.assertNotIn(params["newClientOrderId"], self.f.ledger(account)["intents"])

    def test_direct_buy_submission_read_revocation_preserves_pending_intent(self):
        account, _record = self.published(confirmed=True)
        params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.02",
                  "newClientOrderId": "reentrant-submission-buy"}
        self.assertIsNone(getattr(account.wrapper, "_desktop_spot_entry_capture", None))
        with self.f.account_home(account):
            pending = account.wrapper._begin_order_intent(params, market="spot", source="offline-reentrant-control")
        self.assertEqual("pending", pending["state"])
        before = self.before(account)
        with self.f.account_home(account), self.close_during_read(account, selected_read=1):
            with self.assertRaises(LiveTradingSafetyError):
                account.wrapper._mark_order_intent_submitted(params, via="offline-reentrant-control")
        self.assert_unchanged(account, before)
        self.assertEqual("pending", self.f.ledger(account)["intents"][params["newClientOrderId"]]["state"])


if __name__ == "__main__":
    unittest.main()
