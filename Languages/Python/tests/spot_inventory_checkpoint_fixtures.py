"""Explicit synthetic protected-store fixtures; never touches OS credentials.

The empty store permits ordinary unbound inspection only. It does not silently
seal snapshots. Fresh product fixtures call the genuine owned bootstrap before
creating intents. author_snapshot represents explicitly authored pre-existing
protected evidence in tests of historical states; it cannot replace a slot.
"""
from contextlib import ExitStack
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_inventory_checkpoint as core
from app.integrations.exchanges.binance.orders.order_intent_store import _logical_lock_path, ledger_transaction
from app.integrations.exchanges.binance.orders.spot_inventory_namespace import require_namespace


class CheckpointFixtureBackend:
    def __init__(self, *, simulate_windows=False):
        self.simulate_windows = simulate_windows
        self.store = {}
        self.read_calls = []
        self.put_calls = []
        self.authored_snapshots = []
        self.stack = ExitStack()
        self.proxy = SimpleNamespace(
            credential_store_backend=lambda: "windows-credential-manager",
            get_secret=self.get, put_secret=self.put, delete_secret=self.delete,
            _checkpoint_fixture_backend=self,
        )

    def __enter__(self):
        self.stack.enter_context(patch.object(core, "credential_store", self.proxy))
        if self.simulate_windows:
            self.stack.enter_context(patch.object(core, "_windows_read_adapter", return_value=True))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def get(self, *, scope, account):
        assert scope == core._SCOPE, "Unexpected secret scope in isolated checkpoint fixture"
        self.read_calls.append((scope, account))
        return self.store.get((scope, account), "")

    def put(self, *, scope, account, value):
        assert scope == core._SCOPE, "Unexpected secret scope in isolated checkpoint fixture"
        self.put_calls.append((scope, account, value))
        self.store[scope, account] = value

    def delete(self, **_kwargs):
        raise AssertionError("Checkpoint deletion/reset is not authorized by a test fixture")

    def author_snapshot(self, path: Path, *, namespace, revision=1):
        """Explicitly author initial synthetic historical evidence, never re-seal.

        This is a fixture action, not product bootstrap or production authority.
        Tests of missing authority must leave the fake slot empty.
        """
        path = _logical_lock_path(path)
        with ledger_transaction(path):
            raw = path.read_bytes()
            snapshot = core._snapshot(raw, core._decode(raw))
            require_namespace(snapshot, namespace)
            assert type(revision) is int and revision >= 1
            slot = (core._SCOPE, core._hash(core._source(path).encode("utf-8")))
            assert slot not in self.store, "A fixture cannot overwrite protected authority"
            record = {"version": 1, "state": "stable", "namespace": dict(namespace),
                      "source": core._source(path),
                      "head": {"revision": revision, "digest": hashlib.sha256(raw).hexdigest()}}
            value = core._compact(record)
            core._record(path, value)
            self.store[slot] = value
            self.authored_snapshots.append((str(path), record["head"]["digest"]))


def checkpoint_backend_for_case(case):
    """Use the explicitly installed isolated store, or install one for unittest."""
    backend = getattr(core.credential_store, "_checkpoint_fixture_backend", None)
    if not isinstance(backend, CheckpointFixtureBackend):
        return case.enterContext(CheckpointFixtureBackend(simulate_windows=True))
    case.enterContext(patch.object(core, "_windows_read_adapter", return_value=True))
    return backend
