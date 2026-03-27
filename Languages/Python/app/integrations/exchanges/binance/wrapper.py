
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import math
import threading
import time
import urllib.parse
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from typing import Any
import requests

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from .account import bind_binance_account_data
from .clients import (
    CcxtBinanceAdapter,
    CcxtConnectorError,
    OfficialConnectorAdapter,
    OfficialConnectorError,
    _normalize_connector_choice,
)
from .metadata import bind_binance_exchange_metadata
from .positions import bind_binance_futures_positions
from .orders import (
    bind_binance_futures_orders,
    bind_binance_order_fallback_runtime,
    bind_binance_order_sizing_runtime,
)
from .runtime import (
    bind_binance_futures_mode_runtime,
    bind_binance_futures_settings,
    bind_binance_operational_runtime,
)
from .transport import (
    _coerce_interval_seconds,
    _coerce_int,
    _env_flag,
    _env_float,
    _is_binance_error_payload,
    _requests_timeout,
    bind_binance_http_runtime,
    bind_binance_rate_limit_runtime,
    bind_binance_ws_runtime,
    normalize_margin_ratio,
)
from .market import bind_binance_market_data
from .clients import (
    BinanceSDKCoinFuturesClient,
    BinanceSDKSpotClient,
    BinanceSDKUsdsFuturesClient,
)


class NetworkConnectivityError(RuntimeError):
    """Raised when outbound HTTP connectivity to the exchange is unavailable."""
    pass

MAX_FUTURES_LEVERAGE = 150

def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


DEFAULT_CONNECTOR_BACKEND = "binance-sdk-derivatives-trading-usds-futures"

class BinanceWrapper:

    _limiter_lock = threading.Lock()
    _limiter_pool = {}
    _ban_state_lock = threading.Lock()
    _ban_until_epoch = {}

    def _log(self, msg: str, lvl: str = "info"):
        """
        Lightweight logger shim used by helper methods.
        Falls back to print if no .logger attribute is present.
        """
        try:
            lg = getattr(self, "logger", None)
            if lg is not None and hasattr(lg, lvl):
                getattr(lg, lvl)(msg)
            elif lg is not None and hasattr(lg, "info"):
                lg.info(msg)
            else:
                print(f"[BinanceWrapper][{lvl}] {msg}")
        except Exception:
            try:
                print(f"[BinanceWrapper][{lvl}] {msg}")
            except Exception:
                pass
    def _build_client(self):
        backend = _normalize_connector_choice(getattr(self, "_connector_backend", DEFAULT_CONNECTOR_BACKEND))
        if backend == "binance-connector":
            try:
                return OfficialConnectorAdapter(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"Official connector unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        if backend == "ccxt":
            try:
                return CcxtBinanceAdapter(
                    self.api_key,
                    self.api_secret,
                    mode=self.mode,
                    account_type=self.account_type,
                )
            except Exception as exc:
                self._log(f"ccxt connector unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        if backend == "binance-sdk-derivatives-trading-usds-futures":
            try:
                return BinanceSDKUsdsFuturesClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"USDⓈ futures SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        elif backend == "binance-sdk-derivatives-trading-coin-futures":
            try:
                return BinanceSDKCoinFuturesClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"COIN-M futures SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        elif backend == "binance-sdk-spot":
            try:
                return BinanceSDKSpotClient(self.api_key, self.api_secret, mode=self.mode)
            except Exception as exc:
                self._log(f"Spot SDK unavailable ({exc}); falling back to python-binance.", lvl="warn")
                self._connector_backend = "python-binance"
        requests_params = {"timeout": _requests_timeout()}
        try:
            return Client(
                self.api_key,
                self.api_secret,
                testnet=_is_testnet_mode(self.mode),
                requests_params=requests_params,
                ping=False,  # avoid slow startup when ping route is impaired
            )
        except TypeError:
            # Older python-binance builds may not accept `requests_params` in the constructor.
            try:
                client = Client(self.api_key, self.api_secret, testnet=_is_testnet_mode(self.mode), ping=False)
            except TypeError:
                client = Client(self.api_key, self.api_secret, testnet=_is_testnet_mode(self.mode))
            try:
                setattr(client, "requests_params", requests_params)
            except Exception:
                pass
            return client

    def __init__(self, api_key="", api_secret="", mode="Demo/Testnet", account_type="Spot", *, default_leverage: int | None = None, default_margin_mode: str | None = None, connector_backend: str | None = None):
        self.api_key = (api_key or "").strip()
        self.api_secret = (api_secret or "").strip()
        self.mode = (mode or "Demo/Testnet").strip()
        initial_leverage = int(default_leverage) if (default_leverage is not None) else 20
        if initial_leverage < 1:
            initial_leverage = 1
        if initial_leverage > MAX_FUTURES_LEVERAGE:
            initial_leverage = MAX_FUTURES_LEVERAGE
        self._requested_default_leverage = initial_leverage
        self._default_leverage = initial_leverage
        self.futures_leverage = initial_leverage
        self._default_margin_mode = str((default_margin_mode or "ISOLATED")).upper()
        self.account_type = (account_type or "Spot").strip().upper()  # "SPOT" or "FUTURES"
        if self.account_type.startswith("FUT"):
            self.indicator_source = "Binance futures"
        else:
            self.indicator_source = "Binance spot"
        self._max_auto_bump_percent = 5.0
        self._auto_bump_percent_multiplier = 10.0
        self.recv_window = 5000  # ms for futures calls
        self._futures_max_leverage_cache = {}
        self._leverage_cap_notified = set()
        self._connector_backend = _normalize_connector_choice(connector_backend)
        # Optional override for testnet reliability. Off by default; enable via env if needed.
        try:
            if (
                _env_flag("BINANCE_TESTNET_FORCE_PYBINANCE", False)
                and _is_testnet_mode(self.mode)
                and self.account_type.startswith("FUT")
                and "sdk" in self._connector_backend
            ):
                self._log(
                    f"Switching connector backend to python-binance for testnet reliability (was {self._connector_backend}).",
                    lvl="warn",
                )
                self._connector_backend = "python-binance"
        except Exception:
            pass
        env_tag = self._environment_tag(self.mode)
        acct_tag = self._account_tag(self.account_type)
        self._limiter_key = f"{env_tag}:{acct_tag}"
        limiter_settings = self._limiter_settings_for(env_tag, acct_tag)
        self._request_limiter = self._acquire_rate_limiter(self._limiter_key, limiter_settings)
        # Demo/testnet fast-path to reduce per-order overhead; can disable via env.
        self._fast_order_mode = _env_flag("BINANCE_FAST_TESTNET_ORDERS", _is_testnet_mode(self.mode))
        self._fast_order_cache_ttl = _env_float("BINANCE_FAST_ORDER_CACHE_TTL", 75.0)
        self._futures_settings_cache = {}
        self._futures_settings_cache_lock = threading.Lock()
        self._fast_positions_cache_ttl = _env_float("BINANCE_FAST_POSITIONS_CACHE_TTL", 1.2)

        # Set base URLs BEFORE creating Client (supports older python-binance builds too).
        # Note: python-binance will prefer *_TESTNET_URL when `testnet=True`, but we set both
        # families explicitly for consistency across versions and modes.
        is_testnet = _is_testnet_mode(self.mode)
        spot_rest = "https://testnet.binance.vision/api" if is_testnet else "https://api.binance.com/api"
        futures_rest = "https://testnet.binancefuture.com/fapi" if is_testnet else "https://fapi.binance.com/fapi"
        try:
            Client.API_URL = spot_rest
            if hasattr(Client, "API_TESTNET_URL") and is_testnet:
                Client.API_TESTNET_URL = spot_rest  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            Client.FUTURES_URL = futures_rest
            if hasattr(Client, "FUTURES_TESTNET_URL") and is_testnet:
                Client.FUTURES_TESTNET_URL = futures_rest  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            futures_data_rest = (
                "https://testnet.binancefuture.com/futures/data"
                if is_testnet
                else "https://fapi.binance.com/futures/data"
            )
            if hasattr(Client, "FUTURES_DATA_URL"):
                Client.FUTURES_DATA_URL = futures_data_rest  # type: ignore[attr-defined]
            if hasattr(Client, "FUTURES_DATA_TESTNET_URL") and is_testnet:
                Client.FUTURES_DATA_TESTNET_URL = futures_data_rest  # type: ignore[attr-defined]
        except Exception:
            pass

        self.client = self._build_client()
        try:
            if hasattr(self.client, "_bw_throttled"):
                setattr(self.client, "_bw_throttle", self._throttle_request)
        except Exception:
            pass
        self._install_request_throttler()
        self._symbol_info_cache_spot = {}
        self._symbol_info_cache_futures = None
        self._futures_dual_side_cache = None
        self._futures_dual_side_cache_ts = 0.0
        self._kline_cache = {}
        self._kline_cache_lock = threading.Lock()
        self._positions_cache = None
        self._positions_cache_ts = 0.0
        self._positions_cache_lock = threading.Lock()
        self._futures_account_cache = None
        self._futures_account_cache_ts = 0.0
        self._futures_account_balance_cache = None
        self._live_fut_symbols_cache = set()
        self._live_fut_symbols_ts = 0.0
        self._ws_enabled = _env_flag("BINANCE_WS_INDICATORS", False)
        self._ws_twm = None
        self._ws_streams = {}
        self._ws_kline_cache = {}
        self._ws_lock = threading.Lock()
        self._futures_account_balance_cache_ts = 0.0
        self._futures_account_cache_lock = threading.Lock()
        self._last_ban_log = 0.0
        self._last_network_error_log = 0.0
        self._last_price_cache: dict[str, tuple[float, float]] = {}
        self._emergency_closer_lock = threading.Lock()
        self._emergency_closer_thread = None
        self._emergency_close_requested = False
        self._emergency_close_info = {}
        self._network_offline = False
        self._network_offline_since = 0.0
        self._network_offline_hits = 0
        self._network_emergency_dispatched = False
        self._futures_time_offset_ms = 0
        self._futures_time_offset_ts = 0.0
        self._last_futures_http_error: dict | None = None
        self._fallback_py_client = None  # testnet-only python-binance order fallback
        self._testnet_key_scope: str | None = None
        self._testnet_key_scope_ts = 0.0
        self._futures_api_prefix_override: str | None = None
        getcontext().prec = 28

bind_binance_http_runtime(BinanceWrapper)
bind_binance_order_fallback_runtime(BinanceWrapper)
bind_binance_order_sizing_runtime(BinanceWrapper)
bind_binance_operational_runtime(BinanceWrapper)
bind_binance_rate_limit_runtime(BinanceWrapper)
bind_binance_ws_runtime(BinanceWrapper)
bind_binance_account_data(BinanceWrapper)
bind_binance_exchange_metadata(BinanceWrapper, max_futures_leverage=MAX_FUTURES_LEVERAGE)
bind_binance_futures_mode_runtime(BinanceWrapper)
bind_binance_futures_settings(BinanceWrapper, max_futures_leverage=MAX_FUTURES_LEVERAGE)
bind_binance_futures_positions(BinanceWrapper)
bind_binance_futures_orders(BinanceWrapper, default_mode="flex")
bind_binance_market_data(BinanceWrapper, network_error_cls=NetworkConnectivityError)
