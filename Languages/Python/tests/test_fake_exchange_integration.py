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
    def __init__(self, *, account_type: str = "FUTURES", price: float = 100.0) -> None:
        self.account_type = account_type
        self.price = float(price)
        self.mode = "Demo/Testnet"
        self._connector_backend = "fake-exchange"
        self.orders: list[dict[str, object]] = []
        self.positions: list[dict[str, object]] = []
        self.spot_balances = {"USDT": 1000.0, "BTC": 0.25}

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
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_SHUTDOWN.clear()

    def tearDown(self) -> None:
        StrategyEngine._ORDER_MIN_SPACING = self._original_order_min_spacing
        StrategyEngine._ORDER_LAST_TS = 0.0
        StrategyEngine._BAR_GLOBAL_SIGNATURES.clear()
        StrategyEngine._SYMBOL_ORDER_STATE.clear()
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


if __name__ == "__main__":
    unittest.main()
