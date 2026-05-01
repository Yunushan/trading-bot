from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeExchangeWrapper:
    def __init__(
        self,
        *,
        account_type: str = "FUTURES",
        price: float = 100.0,
        futures_error: BaseException | None = None,
        connector_health: dict[str, object] | None = None,
    ) -> None:
        self.account_type = account_type
        self.price = float(price)
        self.mode = "Demo/Testnet"
        self._connector_backend = "fake-exchange"
        self.orders: list[dict[str, object]] = []
        self.positions: list[dict[str, object]] = []
        self.spot_balances = {"USDT": 1000.0, "BTC": 0.25}
        self.futures_error = futures_error
        self.connector_health = connector_health or {
            "health": "ok",
            "state": "ready",
            "rate_limit": {"active": False, "seconds_until_unban": 0.0},
            "network": {"offline": False, "offline_hits": 0},
        }

    def get_connector_health_snapshot(self) -> dict[str, object]:
        return dict(self.connector_health)

    def get_total_usdt_value(self) -> float:
        if self.account_type == "SPOT":
            return float(self.spot_balances.get("USDT", 0.0))
        return 1000.0

    def get_futures_balance_snapshot(self, force_refresh=False):  # noqa: ARG002
        return {"total": "1000", "wallet": "1000", "available": "1000"}

    def get_futures_balance_usdt(self) -> float:
        return 1000.0

    def get_total_wallet_balance(self) -> float:
        return 1000.0

    def get_futures_symbol_filters(self, _symbol: str) -> dict[str, float]:
        return {"minNotional": 0.0, "minQty": 0.0, "stepSize": 0.001}

    def _ceil_to_step(self, qty: float, step: float) -> float:
        if step <= 0.0:
            return float(qty)
        steps = int(float(qty) / float(step))
        if steps * step < float(qty):
            steps += 1
        return steps * step

    def adjust_qty_to_filters_futures(self, _symbol: str, qty: float, _price: float):
        return float(qty), None

    def get_futures_dual_side(self) -> bool:
        return False

    def get_net_futures_position_amt(self, _symbol: str) -> float:
        return 0.0

    def list_open_futures_positions(self, *args, **kwargs):  # noqa: ARG002
        return list(self.positions)

    def place_futures_market_order(
        self,
        symbol: str,
        side: str,
        *,
        leverage: int,
        quantity: float,
        price: float | None = None,
        reduce_only: bool = False,
        position_side: str | None = None,
        **kwargs,
    ) -> dict[str, object]:
        if self.futures_error is not None:
            raise self.futures_error
        fill_price = float(price or self.price)
        qty = float(quantity)
        order = {
            "market": "futures",
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "price": fill_price,
            "leverage": int(leverage),
            "reduce_only": bool(reduce_only),
            "position_side": position_side,
            "kwargs": dict(kwargs),
        }
        self.orders.append(order)
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "computed": {"qty": qty, "px": fill_price, "lev": int(leverage)},
            "info": {
                "orderId": len(self.orders),
                "origQty": str(qty),
                "executedQty": str(qty),
                "avgPrice": str(fill_price),
                "leverage": int(leverage),
            },
            "fills": {
                "order_id": len(self.orders),
                "trade_count": 1,
                "filled_qty": qty,
                "avg_price": fill_price,
                "commission_usdt": 0.01,
                "net_realized": 0.0,
            },
        }

    def get_spot_symbol_filters(self, _symbol: str) -> dict[str, float]:
        return {"minNotional": 5.0}

    def get_spot_balance(self, asset: str) -> float:
        return float(self.spot_balances.get(str(asset).upper(), 0.0))

    def get_base_quote_assets(self, symbol: str) -> tuple[str, str]:  # noqa: ARG002
        return "BTC", "USDT"

    def place_spot_market_order(
        self,
        symbol: str,
        side: str,
        *,
        quantity: float,
        price: float,
        use_quote: bool = False,
        quote_amount: float | None = None,
    ) -> dict[str, object]:
        fill_price = float(price or self.price)
        qty = float(quote_amount or 0.0) / fill_price if use_quote else float(quantity)
        order = {
            "market": "spot",
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "price": fill_price,
            "use_quote": bool(use_quote),
            "quote_amount": float(quote_amount or 0.0),
        }
        self.orders.append(order)
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "origQty": str(qty),
            "executedQty": str(qty),
            "computed": {"qty": qty, "px": fill_price},
            "info": {
                "orderId": len(self.orders),
                "origQty": str(qty),
                "executedQty": str(qty),
                "avgPrice": str(fill_price),
            },
        }


def _build_engine(*, wrapper: _FakeExchangeWrapper, logs: list, trades: list) -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = wrapper.account_type
    config["side"] = "BOTH"
    config["leverage"] = 5
    config["position_pct"] = 25
    config["position_pct_units"] = "percent"
    config["allow_opposite_positions"] = True
    config["order_rate_min_spacing"] = 0.05
    return StrategyEngine(
        wrapper,
        config,
        log_callback=logs.append,
        trade_callback=trades.append,
    )


def _signal_order_kwargs(engine: StrategyEngine, *, side: str, price: float, marker: int) -> dict[str, object]:
    cw = dict(engine.config)
    cw["price"] = price
    cw["trade_on_signal"] = True
    return {
        "cw": cw,
        "order_side": side,
        "indicator_labels": ["rsi"],
        "order_signature": ("rsi",),
        "origin_timestamp": None,
        "order_trigger_desc": "RSI -> BUY" if side == "BUY" else "RSI -> SELL",
        "order_trigger_actions": {"rsi": side.lower()},
        "last_price": price,
        "current_bar_marker": marker,
        "positions_cache_holder": {"value": []},
        "order_batch_state": {"counter": 0, "total": 1},
    }


class FakeExchangeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_order_min_spacing = StrategyEngine._ORDER_MIN_SPACING
        StrategyEngine._ORDER_MIN_SPACING = 0.0
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()

    def tearDown(self) -> None:
        StrategyEngine._ORDER_MIN_SPACING = self._original_order_min_spacing
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()

    def test_futures_signal_order_uses_fake_exchange_and_records_ledger_entry(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(account_type="FUTURES", price=100.0)
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=1001))

        self.assertEqual(1, len(wrapper.orders), logs)
        order = wrapper.orders[0]
        self.assertEqual("futures", order["market"])
        self.assertEqual("BUY", order["side"])
        self.assertAlmostEqual(12.5, float(order["quantity"]))
        self.assertEqual(5, order["leverage"])
        self.assertFalse(order["reduce_only"])

        leg_entries = engine._leg_entries(("BTCUSDT", "1m", "BUY"))
        self.assertEqual(1, len(leg_entries))
        self.assertAlmostEqual(12.5, float(leg_entries[0]["qty"]))
        self.assertAlmostEqual(250.0, float(leg_entries[0]["margin_usdt"]))
        self.assertIn("rsi", leg_entries[0]["trigger_signature"])
        self.assertTrue(any(event.get("status") == "placed" and event.get("side") == "BUY" for event in trades))

    def test_spot_buy_signal_order_uses_quote_amount_from_position_percent(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(account_type="SPOT", price=100.0)
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=2001))

        self.assertEqual(1, len(wrapper.orders), logs)
        order = wrapper.orders[0]
        self.assertEqual("spot", order["market"])
        self.assertEqual("BUY", order["side"])
        self.assertTrue(order["use_quote"])
        self.assertAlmostEqual(250.0, float(order["quote_amount"]))
        self.assertAlmostEqual(2.5, float(order["quantity"]))
        self.assertTrue(any(event.get("status") == "placed" and event.get("side") == "BUY" for event in trades))

    def test_futures_signal_order_blocks_when_connector_health_is_error(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(
            account_type="FUTURES",
            price=100.0,
            connector_health={
                "health": "error",
                "state": "auth_error",
                "last_error": {
                    "category": "auth",
                    "message": "Invalid API key api_secret=leaked",
                    "retryable": False,
                },
                "rate_limit": {"active": False, "seconds_until_unban": 0.0},
                "network": {"offline": False, "offline_hits": 0},
            },
        )
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=2101))

        self.assertEqual([], wrapper.orders)
        self.assertEqual([], trades)
        self.assertEqual([], engine._leg_entries(("BTCUSDT", "1m", "BUY")))
        joined_logs = "\n".join(str(item) for item in logs)
        self.assertIn("signal order blocked by connector health", joined_logs)
        self.assertIn("connector_state=auth_error", joined_logs)
        self.assertIn("<redacted>", joined_logs)
        self.assertNotIn("leaked", joined_logs)

    def test_spot_signal_order_blocks_while_connector_is_rate_limited(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(
            account_type="SPOT",
            price=100.0,
            connector_health={
                "health": "warning",
                "state": "rate_limited",
                "last_error": {
                    "category": "rate_limited",
                    "message": "Too many requests.",
                    "retryable": True,
                },
                "rate_limit": {"active": True, "seconds_until_unban": 15.0},
                "network": {"offline": False, "offline_hits": 0},
            },
        )
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=2102))

        self.assertEqual([], wrapper.orders)
        self.assertEqual([], trades)
        joined_logs = "\n".join(str(item) for item in logs)
        self.assertIn("signal order blocked by connector health", joined_logs)
        self.assertIn("rate limited for 15s", joined_logs)

    def test_repeated_connector_health_order_blocks_pause_trading(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(
            account_type="FUTURES",
            price=100.0,
            connector_health={
                "health": "error",
                "state": "network_offline",
                "last_error": {
                    "category": "network",
                    "message": "network offline",
                    "retryable": True,
                },
                "rate_limit": {"active": False, "seconds_until_unban": 0.0},
                "network": {"offline": True, "offline_hits": 2},
            },
        )
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)
        circuit_snapshots: list[dict[str, object]] = []
        engine.connector_order_circuit_breaker_callback = circuit_snapshots.append
        engine.config["connector_order_block_pause_threshold"] = 2
        engine.config["connector_order_block_window_seconds"] = 30.0

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=2201))
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertEqual([], circuit_snapshots)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="SELL", price=100.0, marker=2202))

        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertEqual(1, len(circuit_snapshots))
        self.assertTrue(circuit_snapshots[0]["active"])
        self.assertEqual("open", circuit_snapshots[0]["state"])
        self.assertEqual("connector_order_block", circuit_snapshots[0]["reason"])
        self.assertEqual(2, circuit_snapshots[0]["block_count"])
        self.assertEqual([], wrapper.orders)
        self.assertEqual([], trades)
        joined_logs = "\n".join(str(item) for item in logs)
        self.assertIn("connector health circuit breaker paused trading", joined_logs)
        self.assertIn("block_count=2", joined_logs)
        self.assertIn("connector_state=network_offline", joined_logs)

    def test_futures_order_exception_logs_structured_context_with_plain_callback(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(
            account_type="FUTURES",
            price=100.0,
            futures_error=RuntimeError("exchange rejected test order"),
        )
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=3001))

        self.assertEqual([], wrapper.orders)
        self.assertEqual([], engine._leg_entries(("BTCUSDT", "1m", "BUY")))
        joined_logs = "\n".join(str(item) for item in logs)
        self.assertIn("futures order failed", joined_logs)
        self.assertIn("symbol=BTCUSDT", joined_logs)
        self.assertIn("interval=1m", joined_logs)
        self.assertIn("account_type=FUTURES", joined_logs)
        self.assertIn("side=BUY", joined_logs)
        self.assertIn("backend=fake-exchange", joined_logs)
        self.assertIn("exception=RuntimeError: exchange rejected test order", joined_logs)
        self.assertIn("traceback=", joined_logs)

    def test_futures_order_exception_log_redacts_secret_text(self):
        logs: list = []
        trades: list[dict[str, object]] = []
        wrapper = _FakeExchangeWrapper(
            account_type="FUTURES",
            price=100.0,
            futures_error=RuntimeError(
                "Authorization: Bearer exchange-token api_key=exchange-key api_secret=exchange-secret"
            ),
        )
        engine = _build_engine(wrapper=wrapper, logs=logs, trades=trades)

        engine._execute_signal_order(**_signal_order_kwargs(engine, side="BUY", price=100.0, marker=3002))

        joined_logs = "\n".join(str(item) for item in logs)
        self.assertIn("<redacted>", joined_logs)
        for secret in ("exchange-token", "exchange-key", "exchange-secret"):
            self.assertNotIn(secret, joined_logs)


if __name__ == "__main__":
    unittest.main()
