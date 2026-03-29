from __future__ import annotations

from .account_balance_runtime import (
    get_balances,
    get_spot_balance,
    get_spot_position_cost,
    list_spot_non_usdt_balances,
)
from .account_cache_runtime import (
    _fallback_futures_account,
    _fallback_futures_balance,
    _get_futures_account_balance_cached,
    _get_futures_account_cached,
    _invalidate_futures_account_cache,
    _is_testnet_mode,
    _spot_account_dict,
    _try_alt_futures_prefix_on_auth_error,
)
from .account_futures_runtime import (
    get_futures_available_balance,
    get_futures_balance_snapshot,
    get_futures_balance_usdt,
    get_futures_wallet_balance,
    get_total_unrealized_pnl,
    get_total_usdt_value,
    get_total_wallet_balance,
)


def bind_binance_account_data(wrapper_cls):
    wrapper_cls._invalidate_futures_account_cache = _invalidate_futures_account_cache
    wrapper_cls._fallback_futures_account = _fallback_futures_account
    wrapper_cls._fallback_futures_balance = _fallback_futures_balance
    wrapper_cls._try_alt_futures_prefix_on_auth_error = _try_alt_futures_prefix_on_auth_error
    wrapper_cls._get_futures_account_cached = _get_futures_account_cached
    wrapper_cls._get_futures_account_balance_cached = _get_futures_account_balance_cached
    wrapper_cls._spot_account_dict = _spot_account_dict
    wrapper_cls.get_spot_position_cost = get_spot_position_cost
    wrapper_cls.get_spot_balance = get_spot_balance
    wrapper_cls.get_balances = get_balances
    wrapper_cls.list_spot_non_usdt_balances = list_spot_non_usdt_balances
    wrapper_cls.get_futures_balance_usdt = get_futures_balance_usdt
    wrapper_cls.futures_get_usdt_balance = get_futures_balance_usdt
    wrapper_cls.get_futures_balance_snapshot = get_futures_balance_snapshot
    wrapper_cls.get_futures_available_balance = get_futures_available_balance
    wrapper_cls.get_futures_wallet_balance = get_futures_wallet_balance
    wrapper_cls.get_total_usdt_value = get_total_usdt_value
    wrapper_cls.get_total_unrealized_pnl = get_total_unrealized_pnl
    wrapper_cls.get_total_wallet_balance = get_total_wallet_balance
