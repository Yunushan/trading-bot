"""Keep inventory checkpoint tests isolated from real OS protected credentials."""
import pytest
from spot_inventory_checkpoint_fixtures import CheckpointFixtureBackend


@pytest.fixture(autouse=True)
def isolated_inventory_checkpoint_backend():
    # Empty per-test storage grants no bound authority and performs no auto-seal.
    # Explicit protocol fixtures may install their own nested synthetic backend.
    with CheckpointFixtureBackend() as backend:
        yield backend
