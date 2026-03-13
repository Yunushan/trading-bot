from __future__ import annotations

from binance.client import Client

from app.binance_connector_clients import _normalize_connector_choice
from app.binance_transport_helpers import _is_binance_error_payload, _requests_timeout


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _testnet_order_fallback_client(self):
    try:
        if not _is_testnet_mode(self.mode):
            return None
        backend = _normalize_connector_choice(getattr(self, "_connector_backend", ""))
        if "sdk" not in backend:
            return None
    except Exception:
        return None
    if self._fallback_py_client is None:
        try:
            requests_params = {"timeout": _requests_timeout()}
            try:
                self._fallback_py_client = Client(
                    self.api_key,
                    self.api_secret,
                    testnet=True,
                    requests_params=requests_params,
                    ping=False,
                )
            except TypeError:
                try:
                    self._fallback_py_client = Client(self.api_key, self.api_secret, testnet=True, ping=False)
                except TypeError:
                    self._fallback_py_client = Client(self.api_key, self.api_secret, testnet=True)
                try:
                    setattr(self._fallback_py_client, "requests_params", requests_params)
                except Exception:
                    pass
            setattr(self._fallback_py_client, "_bw_throttled", True)
        except Exception:
            self._fallback_py_client = None
    return self._fallback_py_client


def _futures_create_order_with_fallback(self, params: dict):
    order_via = "primary"

    def _order_has_id(order_obj: dict) -> bool:
        return any(
            order_obj.get(key)
            for key in ("orderId", "order_id", "id", "clientOrderId", "client_order_id", "clientOrderID")
        )

    def _raise_if_error_payload(order_obj, *, allow_last_error: bool = False):
        def _raise_from_last_error(default_msg: str) -> None:
            if allow_last_error:
                try:
                    err = getattr(self, "_last_futures_http_error", None)
                except Exception:
                    err = None
                if isinstance(err, dict):
                    err_msg = str(err.get("message") or "").strip()
                    err_code = err.get("code")
                    if err_msg:
                        if err_code is None:
                            raise RuntimeError(f"order rejected: {err_msg}")
                        raise RuntimeError(f"order rejected (code={err_code}): {err_msg}")
            raise RuntimeError(default_msg)

        if order_obj is None:
            _raise_from_last_error("order rejected: empty response")
        if isinstance(order_obj, (list, tuple)):
            if not order_obj:
                _raise_from_last_error("order rejected: empty response")
            return
        if not isinstance(order_obj, dict):
            return
        err_obj = order_obj.get("error")
        if isinstance(err_obj, dict) and _is_binance_error_payload(err_obj):
            code = err_obj.get("code")
            msg = err_obj.get("msg") or err_obj.get("message") or "order rejected"
            raise RuntimeError(f"order rejected (code={code}): {msg}")
        if _is_binance_error_payload(order_obj):
            code = order_obj.get("code")
            msg = order_obj.get("msg") or order_obj.get("message") or "order rejected"
            raise RuntimeError(f"order rejected (code={code}): {msg}")
        success_val = order_obj.get("success")
        if isinstance(success_val, str):
            success_val = success_val.strip().lower() in ("true", "1", "yes")
        if success_val is False:
            msg = order_obj.get("msg") or order_obj.get("message") or "order rejected"
            raise RuntimeError(f"order rejected: {msg}")
        status = str(order_obj.get("status") or "").upper()
        if status in {"REJECTED", "EXPIRED", "CANCELED"}:
            msg = order_obj.get("msg") or order_obj.get("message") or status.lower()
            raise RuntimeError(f"order rejected (status={status}): {msg}")
        data_obj = order_obj.get("data")
        if isinstance(data_obj, dict):
            if _is_binance_error_payload(data_obj):
                code = data_obj.get("code")
                msg = data_obj.get("msg") or data_obj.get("message") or "order rejected"
                raise RuntimeError(f"order rejected (code={code}): {msg}")
            if _order_has_id(data_obj) or data_obj.get("status"):
                order_obj.clear()
                order_obj.update(data_obj)
        if not _order_has_id(order_obj) and not order_obj.get("status"):
            _raise_from_last_error("order rejected: empty response")

    try:
        order = self.client.futures_create_order(**params)
        _raise_if_error_payload(order)
        return order, order_via
    except Exception as primary_err:
        fb_client = self._testnet_order_fallback_client()
        fb_err = None
        if fb_client is not None:
            try:
                order = fb_client.futures_create_order(**params)
                _raise_if_error_payload(order)
                order_via = "fallback-pybinance"
                return order, order_via
            except Exception as exc:
                fb_err = exc

        rest_err = None
        if _is_testnet_mode(self.mode):
            try:
                self._clear_futures_http_error()
                order = self._http_signed_futures_request(
                    "POST",
                    "/v1/order",
                    params,
                    prefix=self._futures_api_prefix(),
                )
                _raise_if_error_payload(order, allow_last_error=True)
                order_via = "fallback-rest"
                return order, order_via
            except Exception as exc:
                rest_err = exc
                try:
                    last_err = getattr(self, "_last_futures_http_error", None)
                    err_code = last_err.get("code") if isinstance(last_err, dict) else None
                except Exception:
                    err_code = None
                alt_prefix = self._alternate_futures_prefix() if err_code in (-2014, -2015) else None
                if alt_prefix:
                    try:
                        self._clear_futures_http_error()
                        order = self._http_signed_futures_request(
                            "POST",
                            "/v1/order",
                            params,
                            prefix=alt_prefix,
                        )
                        _raise_if_error_payload(order, allow_last_error=True)
                        self._futures_api_prefix_override = alt_prefix
                        order_via = "fallback-rest-alt"
                        return order, order_via
                    except Exception as alt_exc:
                        rest_err = alt_exc

        msg = str(primary_err)
        if fb_err is not None:
            msg += f"; fallback failed: {fb_err}"
        if rest_err is not None:
            msg += f"; rest fallback failed: {rest_err}"
        raise RuntimeError(msg) from (rest_err or fb_err or primary_err)


def bind_binance_order_fallback_runtime(wrapper_cls) -> None:
    wrapper_cls._testnet_order_fallback_client = _testnet_order_fallback_client
    wrapper_cls._futures_create_order_with_fallback = _futures_create_order_with_fallback
