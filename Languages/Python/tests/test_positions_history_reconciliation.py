from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.positions.history_update_runtime import _mw_update_position_history  # noqa: E402


class _StaticCombo:
    def __init__(self, value: str) -> None:
        self._value = value

    def currentText(self) -> str:
        return self._value


class _RecordingBinance:
    def __init__(self, positions: list[dict] | None = None) -> None:
        self._positions = list(positions or [])
        self.calls: list[dict[str, object]] = []

    def list_open_futures_positions(self, *, max_age: float = 1.5, force_refresh: bool = False):
        self.calls.append({"max_age": max_age, "force_refresh": force_refresh})
        return list(self._positions)


class _HistoryWindowStub:
    def __init__(
        self,
        *,
        wrapper: _RecordingBinance,
        autoclose: bool = True,
    ) -> None:
        self.config = {
            "positions_missing_autoclose": autoclose,
            "positions_missing_threshold": 1,
            "positions_missing_grace_seconds": 0,
            "positions_closed_history_max": 500,
        }
        self.shared_binance = wrapper
        self.account_combo = _StaticCombo("Futures")
        key = ("BTCUSDT", "L")
        self._open_position_records = {
            key: {
                "symbol": "BTCUSDT",
                "side_key": "L",
                "status": "Active",
                "open_time": "-",
                "close_time": "-",
                "data": {
                    "symbol": "BTCUSDT",
                    "side_key": "L",
                    "update_time": 0,
                },
            }
        }
        self._position_missing_counts: dict[tuple[str, str], int] = {}
        self._pending_close_times: dict[tuple[str, str], str] = {key: "2026-04-05 12:00:00"}
        self._closed_position_records: list[dict] = []

    def _parse_any_datetime(self, _value):
        return None

    def _format_display_time(self, value) -> str:
        return str(value)

    def _create_binance_wrapper(self, **_kwargs):
        return self.shared_binance


class PositionsHistoryReconciliationTests(unittest.TestCase):
    def test_missing_position_uses_fresh_exchange_check_and_clears_pending_close(self):
        wrapper = _RecordingBinance(
            positions=[{"symbol": "BTCUSDT", "positionAmt": "1"}],
        )
        window = _HistoryWindowStub(wrapper=wrapper)

        _mw_update_position_history(window, {})

        key = ("BTCUSDT", "L")
        self.assertIn(key, window._open_position_records)
        self.assertEqual(0, window._position_missing_counts.get(key))
        self.assertNotIn(key, window._pending_close_times)
        self.assertEqual([{"max_age": 0.0, "force_refresh": True}], wrapper.calls)

    def test_missing_position_drop_without_autoclose_clears_pending_close(self):
        wrapper = _RecordingBinance(positions=[])
        window = _HistoryWindowStub(wrapper=wrapper, autoclose=False)

        _mw_update_position_history(window, {})

        key = ("BTCUSDT", "L")
        self.assertEqual({}, window._open_position_records)
        self.assertNotIn(key, window._position_missing_counts)
        self.assertNotIn(key, window._pending_close_times)
        self.assertEqual([], window._closed_position_records)
        self.assertEqual([{"max_age": 0.0, "force_refresh": True}], wrapper.calls)


if __name__ == "__main__":
    unittest.main()
