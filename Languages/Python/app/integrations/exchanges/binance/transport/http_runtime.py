from __future__ import annotations

from .http_base_runtime import (
    _alternate_futures_prefix,
    _futures_api_prefix,
    _futures_base,
    _futures_base_live,
    _is_testnet_mode,
    _normalize_futures_prefix,
    _spot_base,
)
from .http_diagnostic_runtime import (
    _clear_futures_http_error,
    _diagnose_testnet_key_scope,
    _futures_call,
    _futures_timestamp_ms,
    _probe_testnet_key_acceptance,
    _record_futures_http_error,
    _sync_futures_time_offset,
    _testnet_auth_hint,
    futures_api_ok,
    spot_api_ok,
)
from .http_request_runtime import (
    _http_signed_futures,
    _http_signed_futures_list,
    _http_signed_futures_request,
    _http_signed_spot,
    _http_signed_spot_list,
)


def bind_binance_http_runtime(wrapper_cls) -> None:
    wrapper_cls._spot_base = _spot_base
    wrapper_cls._normalize_futures_prefix = _normalize_futures_prefix
    wrapper_cls._futures_api_prefix = _futures_api_prefix
    wrapper_cls._alternate_futures_prefix = _alternate_futures_prefix
    wrapper_cls._futures_base = _futures_base
    wrapper_cls._futures_base_live = _futures_base_live
    wrapper_cls._http_signed_spot = _http_signed_spot
    wrapper_cls._http_signed_spot_list = _http_signed_spot_list
    wrapper_cls._http_signed_futures_request = _http_signed_futures_request
    wrapper_cls._http_signed_futures = _http_signed_futures
    wrapper_cls._http_signed_futures_list = _http_signed_futures_list
    wrapper_cls._record_futures_http_error = _record_futures_http_error
    wrapper_cls._clear_futures_http_error = _clear_futures_http_error
    wrapper_cls._diagnose_testnet_key_scope = _diagnose_testnet_key_scope
    wrapper_cls._probe_testnet_key_acceptance = _probe_testnet_key_acceptance
    wrapper_cls._testnet_auth_hint = _testnet_auth_hint
    wrapper_cls._sync_futures_time_offset = _sync_futures_time_offset
    wrapper_cls._futures_timestamp_ms = _futures_timestamp_ms
    wrapper_cls._futures_call = _futures_call
    wrapper_cls.futures_api_ok = futures_api_ok
    wrapper_cls.spot_api_ok = spot_api_ok
