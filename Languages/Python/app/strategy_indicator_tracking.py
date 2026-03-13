from __future__ import annotations

from collections.abc import Iterable
import re


def _side_token(side: str | None) -> str:
    return "BUY" if str(side or "").upper() in {"BUY", "LONG"} else "SELL"


def _indicator_register_entry(
    self,
    symbol: str,
    interval: str,
    indicator_key: str,
    side: str,
    ledger_id: str | None,
) -> None:
    if not ledger_id:
        return
    side_norm = _side_token(side)
    state = self._indicator_state_entry(symbol, interval, indicator_key)
    with self._indicator_state_lock:
        state.setdefault(side_norm, set()).add(ledger_id)


def _indicator_unregister_entry(
    self,
    symbol: str,
    interval: str,
    indicator_key: str,
    side: str,
    ledger_id: str | None,
) -> None:
    if not ledger_id:
        return
    side_norm = _side_token(side)
    state = self._indicator_state_entry(symbol, interval, indicator_key)
    with self._indicator_state_lock:
        ids = state.get(side_norm)
        if isinstance(ids, set):
            ids.discard(ledger_id)


def _indicator_token_from_signature(
    self,
    signature: Iterable[str] | None,
    fallback_labels: Iterable[str] | None = None,
) -> str | None:
    sig_tuple = self._normalize_signature_tuple(signature)
    if not sig_tuple and fallback_labels:
        sig_tuple = self._normalize_signature_tuple(fallback_labels)
    if not sig_tuple:
        return None
    for token in sig_tuple:
        token_norm = str(token or "").strip().lower()
        if token_norm and not token_norm.startswith("slot"):
            return self._canonical_indicator_token(token_norm) or token_norm
    fallback = sig_tuple[0] if sig_tuple else None
    return self._canonical_indicator_token(fallback) or (fallback if isinstance(fallback, str) else None)


def _extract_indicator_keys(self, entry: dict | None) -> list[str]:
    if not isinstance(entry, dict):
        return []
    key_override = entry.get("indicator_keys")
    if isinstance(key_override, (list, tuple)):
        normalized = []
        for token in key_override:
            canon = self._canonical_indicator_token(token)
            if canon:
                normalized.append(canon)
        if normalized:
            return list(dict.fromkeys(normalized))
    sig = entry.get("trigger_signature") or entry.get("trigger_indicators")
    sig_tuple = self._normalize_signature_tuple(sig if isinstance(sig, Iterable) else [])
    if not sig_tuple:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for token in sig_tuple:
        token_str = str(token or "").strip().lower()
        if token_str and not token_str.startswith("slot"):
            canon = self._canonical_indicator_token(token_str) or token_str
            if canon not in seen:
                keys.append(canon)
                seen.add(canon)
    if not keys and sig_tuple:
        fallback = self._canonical_indicator_token(sig_tuple[0]) or str(sig_tuple[0]).strip().lower()
        if fallback:
            keys.append(fallback)
    return keys


def _extract_indicator_key(self, entry: dict) -> str | None:
    keys = self._extract_indicator_keys(entry)
    return keys[0] if keys else None


def _normalize_interval_token(value: str | None) -> str | None:
    token = str(value or "").strip().lower()
    if not token:
        return None
    token = token.replace(" ", "")
    replacements = {
        "minutes": "m",
        "minute": "m",
        "mins": "m",
        "min": "m",
        "seconds": "s",
        "second": "s",
        "secs": "s",
        "sec": "s",
        "hours": "h",
        "hour": "h",
        "hrs": "h",
        "hr": "h",
        "days": "d",
        "day": "d",
    }
    for src, dst in replacements.items():
        if token.endswith(src):
            token = token[: -len(src)] + dst
            break
    return token or None


def _extract_interval_tokens_from_labels(labels: Iterable[str] | None) -> set[str]:
    tokens: set[str] = set()
    if not labels:
        return tokens
    pattern = re.compile(r"@([0-9]+[smhd])", re.IGNORECASE)
    for label in labels:
        if not isinstance(label, str):
            continue
        for match in pattern.finditer(label):
            norm = _normalize_interval_token(match.group(1))
            if norm:
                tokens.add(norm)
    return tokens


def _tokenize_interval_label(interval_value: str | None) -> set[str]:
    tokens: set[str] = set()
    if interval_value is None:
        return {"-"}
    for part in str(interval_value).split(","):
        norm = _normalize_interval_token(part)
        if norm:
            tokens.add(norm)
    if not tokens:
        tokens.add("-")
    return tokens


def _bump_symbol_signature_open(
    self,
    symbol: str,
    interval: str | None,
    side: str,
    signature: Iterable[str] | None,
    delta: int,
) -> None:
    sig_tuple = self._normalize_signature_tuple(signature)
    if sig_tuple is None:
        return
    interval_norm = str(interval or "").strip().lower() or "default"
    key = (str(symbol or "").upper(), interval_norm, str(side or "").upper(), sig_tuple)
    with self._symbol_signature_lock:
        current = self._symbol_signature_open.get(key, 0) + int(delta)
        if current <= 0:
            self._symbol_signature_open.pop(key, None)
        else:
            self._symbol_signature_open[key] = current


def _symbol_signature_active(
    self,
    symbol: str,
    side: str,
    signature: Iterable[str] | None,
    interval: str | None = None,
) -> bool:
    sig_tuple = self._normalize_signature_tuple(signature)
    if sig_tuple is None:
        return False
    if len(sig_tuple) == 1:
        return False
    interval_norm = str(interval or "").strip().lower() or "default"
    key = (str(symbol or "").upper(), interval_norm, str(side or "").upper(), sig_tuple)
    with self._symbol_signature_lock:
        return self._symbol_signature_open.get(key, 0) > 0


def bind_strategy_indicator_tracking(strategy_cls) -> None:
    strategy_cls._indicator_register_entry = _indicator_register_entry
    strategy_cls._indicator_unregister_entry = _indicator_unregister_entry
    strategy_cls._indicator_token_from_signature = _indicator_token_from_signature
    strategy_cls._extract_indicator_keys = _extract_indicator_keys
    strategy_cls._extract_indicator_key = _extract_indicator_key
    strategy_cls._normalize_interval_token = staticmethod(_normalize_interval_token)
    strategy_cls._extract_interval_tokens_from_labels = staticmethod(_extract_interval_tokens_from_labels)
    strategy_cls._tokenize_interval_label = staticmethod(_tokenize_interval_label)
    strategy_cls._bump_symbol_signature_open = _bump_symbol_signature_open
    strategy_cls._symbol_signature_active = _symbol_signature_active
