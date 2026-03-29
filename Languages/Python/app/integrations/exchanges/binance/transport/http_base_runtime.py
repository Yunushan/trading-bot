from __future__ import annotations


def _is_testnet_mode(mode: str | None) -> bool:
    text = str(mode or "").lower()
    return any(tag in text for tag in ("demo", "test", "sandbox"))


def _spot_base(self) -> str:
    return "https://testnet.binance.vision/api" if _is_testnet_mode(self.mode) else "https://api.binance.com/api"


def _normalize_futures_prefix(self, prefix: str | None) -> str | None:
    text = str(prefix or "").strip().lower()
    if not text:
        return None
    if not text.startswith("/"):
        text = f"/{text}"
    if text in {"/fapi", "/dapi"}:
        return text
    return None


def _futures_api_prefix(self) -> str:
    override = self._normalize_futures_prefix(getattr(self, "_futures_api_prefix_override", None))
    if override:
        return override
    client = getattr(self, "client", None)
    for attr in ("_api_prefix", "api_prefix", "API_PREFIX"):
        try:
            candidate = self._normalize_futures_prefix(getattr(client, attr, None))
        except Exception:
            candidate = None
        if candidate:
            return candidate
    backend = str(getattr(self, "_connector_backend", "") or "").lower()
    if "coin" in backend and "future" in backend:
        return "/dapi"
    return "/fapi"


def _alternate_futures_prefix(self, prefix: str | None = None) -> str | None:
    current = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    if current == "/fapi":
        return "/dapi"
    if current == "/dapi":
        return "/fapi"
    return None


def _futures_base(self, prefix: str | None = None) -> str:
    api_prefix = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    if _is_testnet_mode(self.mode):
        host = "https://testnet.binancefuture.com"
    else:
        host = "https://dapi.binance.com" if api_prefix == "/dapi" else "https://fapi.binance.com"
    base = host.rstrip("/")
    if base.endswith(api_prefix):
        return base
    return f"{base}{api_prefix}"


def _futures_base_live(self, prefix: str | None = None) -> str:
    api_prefix = self._normalize_futures_prefix(prefix) or self._futures_api_prefix()
    host = "https://dapi.binance.com" if api_prefix == "/dapi" else "https://fapi.binance.com"
    return f"{host}{api_prefix}"
