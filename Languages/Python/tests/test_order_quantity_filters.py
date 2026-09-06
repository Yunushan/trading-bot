from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.metadata import exchange_metadata as metadata
from app.integrations.exchanges.binance.metadata.filter_validation import (
    parse_symbol_filters,
    validated_symbol_filters,
)
from app.integrations.exchanges.binance.orders.order_submit_guard_runtime import _order_filter_errors
from app.settings.live_safety import LiveTradingSafetyError
from test_binance_package_split_smoke import _GuardedFuturesAuditWrapper, _live_ack_config


def symbol_info():
    return {
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MARKET_LOT_SIZE", "minQty": "0.1", "maxQty": "1", "stepSize": "0.1"},
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "MIN_NOTIONAL", "minNotional": "5", "notional": "5"},
        ],
    }


class OrderQuantityFilterTests(unittest.TestCase):
    def setUp(self):
        network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)
        environment = patch.dict("os.environ", {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def errors(self, *, quantity, market="futures", order_type="MARKET", info=None, **params):
        filters = parse_symbol_filters(info or symbol_info(), "BTCUSDT", futures=market == "futures")
        wrapper = SimpleNamespace(
            get_futures_symbol_filters=lambda _: filters,
            get_spot_symbol_filters=lambda _: filters,
            get_last_price=lambda _: 1000.0,
        )
        return _order_filter_errors(
            wrapper,
            market,
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": order_type,
                "quantity": quantity,
                **params,
            },
        )

    def test_normalization_retains_both_quantity_rules_and_spot_price_step(self):
        for futures in (False, True):
            with self.subTest(futures=futures):
                filters = parse_symbol_filters(symbol_info(), "BTCUSDT", futures=futures)
                self.assertEqual(
                    {
                        "minQty": 0.001,
                        "maxQty": 100.0,
                        "stepSize": 0.001,
                        "marketMinQty": 0.1,
                        "marketMaxQty": 1.0,
                        "marketStepSize": 0.1,
                        "tickSize": 0.01,
                        "minNotional": 5.0,
                    },
                    filters,
                )

    def test_market_boundaries_and_limit_order_rule_selection(self):
        for market in ("spot", "futures"):
            for qty, permitted in (("0.1", True), ("1", True), ("0.05", False), ("1.1", False), ("101", False)):
                with self.subTest(market=market, qty=qty):
                    self.assertEqual(permitted, not self.errors(quantity=qty, market=market))
            self.assertEqual([], self.errors(quantity="1.5", market=market, order_type="LIMIT", price="1000"))
            self.assertTrue(self.errors(quantity="101", market=market, order_type="LIMIT", price="1000"))

    def test_market_rule_never_replaces_lot_rule(self):
        info = symbol_info()
        info["filters"][0].update(minQty="0.1", maxQty="0.8", stepSize="0.02")
        info["filters"][1].update(minQty="0", maxQty="1", stepSize="0.03")
        for market in ("spot", "futures"):
            for qty, permitted in (("0.06", False), ("0.12", True), ("0.14", False), ("0.15", False), ("0.9", False)):
                with self.subTest(market=market, qty=qty):
                    self.assertEqual(permitted, not self.errors(quantity=qty, market=market, info=info))

    def test_protective_exit_exemption_does_not_remove_maximum_or_step(self):
        self.assertEqual([], self.errors(quantity="0.1", reduceOnly=True))
        self.assertTrue(self.errors(quantity="1.1", reduceOnly=True))
        self.assertTrue(self.errors(quantity="0.15", reduceOnly=True))
        info = symbol_info()
        info["filters"][1]["stepSize"] = "0"
        self.assertEqual([], self.errors(quantity="0.001", info=info, reduceOnly=True))
        info["filters"][1]["maxQty"] = "0"
        info["filters"][1]["minQty"] = "0"
        self.assertTrue(self.errors(quantity="0.001", info=info, reduceOnly=True))

    def test_zero_market_step_does_not_disable_lot_step(self):
        info = symbol_info()
        info["filters"][1]["stepSize"] = "0"
        self.assertEqual([], self.errors(quantity="0.101", info=info))
        self.assertTrue(self.errors(quantity="0.1005", info=info))

    def test_invalid_quantity_metadata_is_never_defaulted_to_disabled_rules(self):
        for futures in (False, True):
            for index in (0, 1):
                for field in ("minQty", "maxQty", "stepSize"):
                    for invalid in (None, "", "NaN", "Infinity", "-1", True, {}, []):
                        with self.subTest(futures=futures, row=index, field=field, invalid=invalid):
                            info = symbol_info()
                            info["filters"][index][field] = invalid
                            with self.assertRaises(ValueError):
                                parse_symbol_filters(info, "BTCUSDT", futures=futures)
                    info = symbol_info()
                    del info["filters"][index][field]
                    with self.assertRaises(ValueError):
                        parse_symbol_filters(info, "BTCUSDT", futures=futures)
            info = symbol_info()
            info["filters"].append(deepcopy(info["filters"][1]))
            with self.assertRaisesRegex(ValueError, "duplicate MARKET_LOT_SIZE"):
                parse_symbol_filters(info, "BTCUSDT", futures=futures)

    def test_normalized_missing_maximum_partial_market_and_reversed_ranges_block(self):
        filters = parse_symbol_filters(symbol_info(), "BTCUSDT", futures=True)
        for key in ("maxQty", "marketMinQty", "marketMaxQty", "marketStepSize"):
            incomplete = dict(filters)
            del incomplete[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, f"missing {key}"):
                validated_symbol_filters(incomplete)
        for key in ("maxQty", "marketMaxQty"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "exceeds"):
                validated_symbol_filters({**filters, key: 0})
        no_market_rule = {key: value for key, value in filters.items() if not key.startswith("market")}
        self.assertEqual(Decimal("100"), validated_symbol_filters(no_market_rule)["maxQty"])

    def test_rejected_request_never_reaches_exchange_or_consumes_budget(self):
        wrapper = _GuardedFuturesAuditWrapper(
            price=1000,
            filters=parse_symbol_filters(symbol_info(), "BTCUSDT", futures=True),
            live_safety_config=_live_ack_config(live_trading_max_session_orders=1),
        )
        self.addCleanup(wrapper.close)
        params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET"}
        for quantity in ("0.05", "1.5", "101"):
            with self.subTest(quantity=quantity), self.assertRaises(LiveTradingSafetyError):
                wrapper._futures_create_order_with_fallback({**params, "quantity": quantity})
        self.assertEqual([], wrapper.client.orders)
        self.assertEqual(0, getattr(wrapper, "_live_order_submit_attempt_count", 0))
        wrapper._futures_create_order_with_fallback({**params, "quantity": "0.1"})
        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_bad_cached_metadata_is_evicted_and_recovered(self):
        class Wrapper:
            pass

        metadata.bind_binance_exchange_metadata(Wrapper)
        for futures in (False, True):
            with self.subTest(futures=futures):
                wrapper = Wrapper()
                bad = symbol_info()
                del bad["filters"][1]["maxQty"]
                wrapper._symbol_info_cache_spot = {"BTCUSDT": bad}
                wrapper._symbol_info_cache_futures = {"symbols": [bad]}
                wrapper.client = SimpleNamespace(get_symbol_info=Mock(return_value=symbol_info()))
                wrapper._futures_call = Mock(return_value={"symbols": [symbol_info()]})
                getter = wrapper.get_futures_symbol_filters if futures else wrapper.get_spot_symbol_filters
                with self.assertRaises(ValueError):
                    getter("BTCUSDT")
                self.assertEqual(1, getter("BTCUSDT")["marketMaxQty"])
                if futures:
                    wrapper._futures_call.assert_called_once()
                else:
                    wrapper.client.get_symbol_info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
