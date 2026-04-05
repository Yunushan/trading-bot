from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gui.trade.signal_open_runtime import handle_non_close_trade_signal  # noqa: E402


class _OpenSignalWindowStub:
    def __init__(self) -> None:
        self._entry_allocations: dict[tuple[str, str], list[dict]] = {}
        self._pending_close_times: dict[tuple[str, str], str] = {}
        self._open_position_records: dict[tuple[str, str], dict] = {}
        self._processed_open_events = None
        self._is_stopping_engines = False

    def _parse_any_datetime(self, value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
        return None

    def _format_display_time(self, value) -> str:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat(timespec="seconds")
        return str(value)


def _normalize_interval(_self, value):
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() or None


def _side_key_from_value(value) -> str:
    return "L" if str(value).upper() in {"BUY", "LONG"} else "S"


def _resolve_trigger_indicators(raw, _desc=None):
    if isinstance(raw, (list, tuple, set)):
        return [str(token).strip().lower() for token in raw if str(token).strip()]
    return []


def _normalize_trigger_actions_map(raw):
    return dict(raw) if isinstance(raw, dict) else {}


def _ctx() -> dict:
    return {
        "sym": "BTCUSDT",
        "interval": "1m",
        "side_for_key": "BUY",
        "side_key": "L",
        "sym_upper": "BTCUSDT",
        "status": "placed",
        "ok_flag": True,
    }


def _dispatch(window: _OpenSignalWindowStub, order_info: dict) -> None:
    handle_non_close_trade_signal(
        window,
        order_info,
        _ctx(),
        alloc_map=window._entry_allocations,
        pending_close=window._pending_close_times,
        resolve_trigger_indicators=_resolve_trigger_indicators,
        normalize_trigger_actions_map=_normalize_trigger_actions_map,
        save_position_allocations=lambda *_args, **_kwargs: None,
        normalize_interval=_normalize_interval,
        side_key_from_value=_side_key_from_value,
        refresh_trade_views=lambda *_args, **_kwargs: None,
        persist_trade_allocations=lambda *_args, **_kwargs: None,
        sync_open_position_snapshot=lambda *_args, **_kwargs: None,
    )


class OpenTradeSignalBehaviorTests(unittest.TestCase):
    def test_distinct_context_slots_without_exchange_ids_preserve_live_allocations(self):
        window = _OpenSignalWindowStub()
        base_order = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "side": "BUY",
            "qty": 0.25,
            "executed_qty": 0.25,
            "avg_price": 100.0,
            "price": 100.0,
            "leverage": 5,
            "status": "placed",
            "ok": True,
            "time": "2026-04-05T12:30:00+00:00",
            "trigger_indicators": ["rsi"],
            "trigger_signature": ["rsi"],
            "trigger_desc": "rsi",
        }

        first_order = dict(base_order, context_key="1m:BUY:rsi|slot-a", slot_id="slot-a")
        second_order = dict(base_order, context_key="1m:BUY:rsi|slot-b", slot_id="slot-b")

        _dispatch(window, first_order)
        _dispatch(window, second_order)

        allocations = window._entry_allocations[("BTCUSDT", "L")]
        self.assertEqual(2, len(allocations))
        self.assertEqual({"slot-a", "slot-b"}, {entry.get("slot_id") for entry in allocations})
        self.assertEqual(
            {"1m:BUY:rsi|slot-a", "1m:BUY:rsi|slot-b"},
            {entry.get("context_key") for entry in allocations},
        )
        self.assertEqual(2, len({entry.get("trade_id") for entry in allocations}))

    def test_distinct_client_order_ids_preserve_live_allocations(self):
        window = _OpenSignalWindowStub()
        base_order = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "side": "BUY",
            "qty": 0.25,
            "executed_qty": 0.25,
            "avg_price": 100.0,
            "price": 100.0,
            "leverage": 5,
            "status": "placed",
            "ok": True,
            "time": "2026-04-05T12:31:00+00:00",
            "trigger_indicators": ["rsi"],
            "trigger_signature": ["rsi"],
            "trigger_desc": "rsi",
        }

        _dispatch(window, dict(base_order, client_order_id="client-a"))
        _dispatch(window, dict(base_order, client_order_id="client-b"))

        allocations = window._entry_allocations[("BTCUSDT", "L")]
        self.assertEqual(2, len(allocations))
        self.assertEqual({"client-a", "client-b"}, {entry.get("client_order_id") for entry in allocations})
        self.assertEqual({"client-a", "client-b"}, {entry.get("trade_id") for entry in allocations})


if __name__ == "__main__":
    unittest.main()
