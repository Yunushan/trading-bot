from __future__ import annotations

from uuid import uuid4

from binance.client import Client
from app.settings.live_safety import LiveTradingSafetyError

from ..clients.connector_clients import _normalize_connector_choice
from ..transport.helpers import _is_binance_error_payload, _requests_timeout


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _ensure_binance_client_order_id(params: dict) -> dict:
    """Return a submission payload with one stable Binance client order ID.

    A fallback must retry the same exchange request identifier: generating a new
    identifier after an uncertain transport failure can create a duplicate order.
    Binance accepts up to 36 characters for ``newClientOrderId``; the generated
    value is 35 ASCII characters and leaves caller-supplied identifiers intact.
    """
    payload = dict(params or {})
    existing = str(payload.get("newClientOrderId") or "").strip()
    if existing:
        payload["newClientOrderId"] = existing
        return payload
    payload["newClientOrderId"] = f"tb-{uuid4().hex}"
    return payload


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
    params = _ensure_binance_client_order_id(params)
    order_via = "primary"
    audit = getattr(self, "_audit_order_event", None)
    guard = getattr(self, "_guard_live_order_submit", None)
    begin_intent = getattr(self, "_begin_order_intent", None)
    mark_submitted = getattr(self, "_mark_order_intent_submitted", None)
    mark_accepted = getattr(self, "_mark_order_intent_accepted", None)
    mark_unknown = getattr(self, "_mark_order_intent_unknown", None)
    intent_started = False

    def _audit(event: str, *, order_params: dict, result=None, error=None, via: str | None = None) -> None:
        if not callable(audit):
            return
        audit(
            event,
            symbol=order_params.get("symbol"),
            side=order_params.get("side"),
            market="futures",
            params=order_params,
            result=result if isinstance(result, dict) else None,
            error=error,
            via=via,
            source="_futures_create_order_with_fallback",
        )

    def _guard_order_submit(*, via: str) -> None:
        if callable(guard):
            guard(market="futures", params=params, source=f"_futures_create_order_with_fallback:{via}")

    def _record_submit(*, via: str) -> None:
        nonlocal intent_started
        if not intent_started and callable(begin_intent):
            begin_intent(params, market="futures", source="_futures_create_order_with_fallback")
            intent_started = True
        if callable(mark_submitted):
            mark_submitted(params, via=via)

    def _record_accepted(*, via: str, result: object) -> None:
        if callable(mark_accepted) and intent_started:
            mark_accepted(params, via=via, result=result)

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
            _raise_from_last_error("order rejected: malformed response")
        if not isinstance(order_obj, dict):
            _raise_from_last_error("order rejected: malformed response")
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
            if _order_has_id(data_obj):
                order_obj.clear()
                order_obj.update(data_obj)
        if not _order_has_id(order_obj):
            _raise_from_last_error("order rejected: response has no order identifier")

    try:
        _audit("exchange_order_request", order_params=params, via=order_via)
        _guard_order_submit(via=order_via)
        _record_submit(via=order_via)
        order = self.client.futures_create_order(**params)
        _raise_if_error_payload(order)
        _record_accepted(via=order_via, result=order)
        _audit("exchange_order_response", order_params=params, result=order, via=order_via)
        return order, order_via
    except Exception as primary_err:
        _audit("exchange_order_error", order_params=params, error=primary_err, via=order_via)
        if isinstance(primary_err, LiveTradingSafetyError):
            raise
        fb_client = self._testnet_order_fallback_client()
        fb_err = None
        if fb_client is not None:
            try:
                _audit("exchange_order_request", order_params=params, via="fallback-pybinance")
                _guard_order_submit(via="fallback-pybinance")
                _record_submit(via="fallback-pybinance")
                order = fb_client.futures_create_order(**params)
                _raise_if_error_payload(order)
                order_via = "fallback-pybinance"
                _record_accepted(via=order_via, result=order)
                _audit("exchange_order_response", order_params=params, result=order, via=order_via)
                return order, order_via
            except Exception as exc:
                fb_err = exc
                _audit("exchange_order_error", order_params=params, error=exc, via="fallback-pybinance")

        rest_err = None
        if _is_testnet_mode(self.mode):
            try:
                self._clear_futures_http_error()
                _audit("exchange_order_request", order_params=params, via="fallback-rest")
                _guard_order_submit(via="fallback-rest")
                _record_submit(via="fallback-rest")
                order = self._http_signed_futures_request(
                    "POST",
                    "/v1/order",
                    params,
                    prefix=self._futures_api_prefix(),
                )
                _raise_if_error_payload(order, allow_last_error=True)
                order_via = "fallback-rest"
                _record_accepted(via=order_via, result=order)
                _audit("exchange_order_response", order_params=params, result=order, via=order_via)
                return order, order_via
            except Exception as exc:
                rest_err = exc
                _audit("exchange_order_error", order_params=params, error=exc, via="fallback-rest")
                try:
                    last_err = getattr(self, "_last_futures_http_error", None)
                    err_code = last_err.get("code") if isinstance(last_err, dict) else None
                except Exception:
                    err_code = None
                alt_prefix = self._alternate_futures_prefix() if err_code in (-2014, -2015) else None
                if alt_prefix:
                    try:
                        self._clear_futures_http_error()
                        _audit("exchange_order_request", order_params=params, via="fallback-rest-alt")
                        _guard_order_submit(via="fallback-rest-alt")
                        _record_submit(via="fallback-rest-alt")
                        order = self._http_signed_futures_request(
                            "POST",
                            "/v1/order",
                            params,
                            prefix=alt_prefix,
                        )
                        _raise_if_error_payload(order, allow_last_error=True)
                        self._futures_api_prefix_override = alt_prefix
                        order_via = "fallback-rest-alt"
                        _record_accepted(via=order_via, result=order)
                        _audit("exchange_order_response", order_params=params, result=order, via=order_via)
                        return order, order_via
                    except Exception as alt_exc:
                        rest_err = alt_exc
                        _audit("exchange_order_error", order_params=params, error=alt_exc, via="fallback-rest-alt")

        msg = str(primary_err)
        if fb_err is not None:
            msg += f"; fallback failed: {fb_err}"
        if rest_err is not None:
            msg += f"; rest fallback failed: {rest_err}"
        if callable(mark_unknown) and intent_started:
            mark_unknown(params, error=msg)
        raise RuntimeError(msg) from (rest_err or fb_err or primary_err)


def bind_binance_order_fallback_runtime(wrapper_cls) -> None:
    wrapper_cls._testnet_order_fallback_client = _testnet_order_fallback_client
    wrapper_cls._futures_create_order_with_fallback = _futures_create_order_with_fallback
    wrapper_cls._ensure_binance_client_order_id = staticmethod(_ensure_binance_client_order_id)
