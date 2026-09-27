from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.gui.shared.allocation_persistence import load_position_allocations, save_position_allocations


class AllocationPersistenceTests(unittest.TestCase):
    def test_live_allocations_are_not_dropped_after_one_day_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            this_file = Path(tmp) / "Languages" / "Python" / "app" / "gui" / "window_shell.py"
            this_file.parent.mkdir(parents=True)
            entry = {
                "symbol": "BTCUSDT", "side_key": "L", "qty": 0.1,
                "entry_price": 20000.0, "status": "Active", "client_order_id": "fill-A",
            }
            record = {
                "symbol": "BTCUSDT", "side_key": "L", "status": "Active",
                "data": {"symbol": "BTCUSDT", "side_key": "L"}, "allocations": [entry],
            }
            with patch("app.gui.shared.allocation_persistence.time.time", return_value=1000.0):
                self.assertTrue(save_position_allocations(
                    {("BTCUSDT", "L"): [entry]},
                    {("BTCUSDT", "L"): record},
                    this_file=this_file,
                    mode="Live",
                ))
            with patch("app.gui.shared.allocation_persistence.time.time", return_value=100000.0):
                allocations, records = load_position_allocations(this_file=this_file, mode="Live")

            self.assertEqual("fill-A", allocations[("BTCUSDT", "L")][0]["client_order_id"])
            self.assertEqual("Active", records[("BTCUSDT", "L")]["status"])


if __name__ == "__main__":
    unittest.main()
