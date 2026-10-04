"""Independent Windows indexed final native-probe authority controls, entirely synthetic."""
from contextlib import contextmanager
from copy import deepcopy
import sys
import unittest
from unittest.mock import patch

import test_spot_indexed_intent_hot_runtime as indexed_fixtures
from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_execution_owner as owners
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint_runtime as owned
from app.integrations.exchanges.binance.orders import spot_indexed_intent_selective as selective
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import namespace_for_owner
from app.settings.live_safety import LiveTradingSafetyError


@unittest.skipUnless(sys.platform == "win32", "Actual final Windows sharing-probe authority control")
class SpotCheckpointIndexedCommitAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f = indexed_fixtures.SpotIndexedIntentHotRuntimeTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.observed = {}
        self.posts = []
        self.enterContext(patch("requests.post", side_effect=self.forbidden_post))
        for method in ("create_order", "create_order_list_opo", "cancel_replace_order"):
            self.enterContext(patch.object(self.f.wrapper.client, method, side_effect=self.forbidden_post, create=True))

    def forbidden_post(self, *_args, **_kwargs):
        self.posts.append("unexpected synthetic order")
        raise AssertionError("No order transport is authorized by this control")

    def before(self):
        with locks.ledger_transaction(self.f.path):
            session = self.f.session()
            self.assertTrue(session.native_guarded)
            payload = runtime._read_ledger(self.f.path, expected_binding=self.f.binding)
            row = payload["intents"]["syn-list-00000000"]
            # serialize reads the complete committed image through the genuinely
            # guarded handle; a second native read handle is correctly denied.
            image = session._connection.serialize()
        backend = core.credential_store._checkpoint_fixture_backend
        return session, deepcopy(row), (image, self.f.path.read_bytes(), self.f.allocation_path.read_bytes(),
                                       deepcopy(backend.store), list(backend.put_calls))

    @contextmanager
    def revoke_at_final_probe(self, session, *, fault):
        original = session._guard
        marker = owners.owner_marker_path(self.f.path)
        observed = {"fired": False, "marker_after_fault": None}
        def probe():
            original()  # Retain the actual native share-denial proof.
            if (not observed["fired"] and session._connection.in_transaction
                    and session._connection.execute("SELECT revision FROM store_state").fetchone()[0]
                    != session.receipt.revision):
                # Only the final WRITE guard has staged a newer head while
                # retaining the original cache; earlier read probes cannot fire.
                observed["fired"] = True
                if fault == "owner-close":
                    self.f.owner.close()
                elif fault == "required-token-loss":
                    self.assertIsNotNone(core._AUTHORITY.get())
                    self.assertIsNotNone(getattr(core._EXPECTED_AUTHORITY, "token", None))
                    core._AUTHORITY.set(None)  # Keep required local token: fail closed.
                else:
                    self.fail("Unknown synthetic authority fault")
                observed["marker_after_fault"] = marker.read_bytes()
        try:
            with patch.object(session, "_guard", side_effect=probe):
                yield
        finally:
            self.assertTrue(observed["fired"], "The exact final staged-head native probe was not reached")
            self.assertEqual(observed["marker_after_fault"], marker.read_bytes())
            self.observed = {"fault": fault, "exact_final_native_probe_fired": True,
                             "marker_after_fault_preserved": True, "native_guard_was_actual": True}

    def exercise(self, *, fault, borrowed):
        session, row, before = self.before()
        namespace = namespace_for_owner(self.f.wrapper)
        marker = owners.owner_marker_path(self.f.path)
        marker_before = marker.read_bytes()
        def scope():
            if fault == "required-token-loss":
                return core._checkpoint_authority(
                    lambda: owned._assert_pin(self.f.wrapper, self.f.path, namespace, pin))
            return _ordinary_scope()
        with self.assertRaises(LiveTradingSafetyError):
            with owned._owned_lifetime(self.f.wrapper, self.f.path):
                with locks.ledger_transactions(self.f.path, self.f.allocation_path):
                    pin = owned._pin_authority(self.f.wrapper, self.f.path, namespace)
                    with scope(), self.revoke_at_final_probe(session, fault=fault):
                        if borrowed:
                            payload = runtime._read_ledger(self.f.path, expected_binding=self.f.binding)
                            payload["operator_annotation"] = "synthetic final borrowed guard candidate"
                            runtime._write_ledger(self.f.path, payload)
                        else:
                            runtime._update_order_intent_by_id(
                                self.f.wrapper, row["client_order_id"], state="accepted", expected_record=row,
                                operator_annotation="synthetic final row guard candidate")
        if fault == "owner-close":
            self.assertIsNone(self.f.owner.fd)
        else:
            self.assertEqual(marker_before, marker.read_bytes())
            self.f.owner.assert_held(uid=self.f.owner.uid, environment="live",
                                    credential_fingerprint=self.f.binding["credential_fingerprint"],
                                    owner_wrapper=self.f.wrapper)
        # The failed real transaction closes/fences its connection. Explicitly
        # close any surviving handle in the failing pre-fix control to inspect
        # actual committed bytes without weakening the native exclusion.
        selective.close_indexed_session(self.f.owner)
        backend = core.credential_store._checkpoint_fixture_backend
        after = (session.receipt.path.read_bytes(), self.f.path.read_bytes(), self.f.allocation_path.read_bytes(),
                 deepcopy(backend.store), list(backend.put_calls))
        self.assertEqual(before, after, "The indexed COMMIT persisted after final native-probe authority loss")
        self.assertEqual([], self.posts)
        self.observed.update({"borrowed_full_writer": borrowed, "complete_database_image_unchanged": True,
                              "protected_state_and_sources_unchanged": True, "order_posts": 0})

    def test_final_native_probe_owner_close_rolls_back_actual_record_update(self):
        self.exercise(fault="owner-close", borrowed=False)

    def test_final_native_probe_owner_close_rolls_back_actual_borrowed_full_writer(self):
        self.exercise(fault="owner-close", borrowed=True)

    def test_final_native_probe_required_token_loss_rolls_back_actual_record_update(self):
        self.exercise(fault="required-token-loss", borrowed=False)

    def test_final_native_probe_required_token_loss_rolls_back_actual_borrowed_full_writer(self):
        self.exercise(fault="required-token-loss", borrowed=True)


@contextmanager
def _ordinary_scope():
    yield


if __name__ == "__main__":
    unittest.main()
