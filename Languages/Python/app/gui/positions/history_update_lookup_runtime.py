from __future__ import annotations

import time


def collect_missing_candidates(
    self,
    positions_map: dict,
    prev_records: dict,
    missing_counts: dict,
    pending_close_map,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    try:
        missing_grace_seconds = float(
            self.config.get("positions_missing_grace_seconds", 30) or 0.0
        )
    except Exception:
        missing_grace_seconds = 0.0
    missing_grace_seconds = max(0.0, missing_grace_seconds)

    for key, prev in prev_records.items():
        if key in positions_map:
            missing_counts.pop(key, None)
            continue
        count = missing_counts.get(key, 0) + 1
        missing_counts[key] = count
        try:
            threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
        except Exception:
            threshold = 2
        threshold = max(1, threshold)
        try:
            if isinstance(pending_close_map, dict) and key in pending_close_map:
                threshold = 1
        except Exception:
            try:
                threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
            except Exception:
                threshold = 2
        if count < threshold:
            continue
        if missing_grace_seconds > 0 and not (
            isinstance(pending_close_map, dict) and key in pending_close_map
        ):
            open_val = None
            if isinstance(prev, dict):
                open_val = prev.get("open_time")
                if not open_val:
                    open_val = (prev.get("data") or {}).get("open_time")
                if not open_val:
                    open_val = (prev.get("data") or {}).get("update_time")
            dt_obj = self._parse_any_datetime(open_val)
            if dt_obj is not None:
                try:
                    age_seconds = time.time() - dt_obj.timestamp()
                except Exception:
                    age_seconds = None
                if age_seconds is not None and 0 <= age_seconds < missing_grace_seconds:
                    continue
        candidates.append(key)
    return candidates


def resolve_live_keys(self, candidates: list[tuple[str, str]]) -> set[tuple[str, str]] | None:
    if not candidates:
        return set()
    try:
        bw = getattr(self, "shared_binance", None)
        if bw is None:
            api_key = ""
            api_secret = ""
            try:
                api_key = (self.api_key_edit.text() or "").strip()
                api_secret = (self.api_secret_edit.text() or "").strip()
            except Exception:
                pass
            if api_key and api_secret:
                try:
                    bw = self._create_binance_wrapper(
                        api_key=api_key,
                        api_secret=api_secret,
                        mode=self.mode_combo.currentText(),
                        account_type=self.account_combo.currentText(),
                        default_leverage=int(self.leverage_spin.value() or 1),
                        default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
                    )
                    self.shared_binance = bw
                except Exception:
                    bw = None
        if bw is None:
            return None
        live = set()
        try:
            acct_text = self.account_combo.currentText()
        except Exception:
            acct_text = str(self.config.get("account_type") or "")
        acct_upper = str(acct_text or "").upper()
        acct_is_futures = acct_upper.startswith("FUT")
        acct_is_spot = acct_upper.startswith("SPOT")

        need_futures = acct_is_futures and any(side in ("L", "S") for _, side in candidates)
        need_spot = acct_is_spot and any(side in ("L", "S", "SPOT") for _, side in candidates)
        if need_futures:
            try:
                for pos in bw.list_open_futures_positions() or []:
                    sym = str(pos.get("symbol") or "").strip().upper()
                    if not sym:
                        continue
                    amt = float(pos.get("positionAmt") or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    side_key = "L" if amt > 0 else "S"
                    live.add((sym, side_key))
            except Exception:
                return None
        if need_spot:
            try:
                balances = bw.get_balances() or []
                for bal in balances:
                    asset = bal.get("asset")
                    free = float(bal.get("free") or 0.0)
                    locked = float(bal.get("locked") or 0.0)
                    total = free + locked
                    if not asset or total <= 0:
                        continue
                    sym = f"{asset}USDT"
                    sym_upper = sym.strip().upper()
                    live.add((sym_upper, "SPOT"))
                    live.add((sym_upper, "L"))
            except Exception:
                pass
        return live
    except Exception:
        return None


def lookup_force_liquidation(
    self,
    symbol: str,
    side_key: str,
    update_hint_ms: int | None = None,
) -> dict | None:
    try:
        bw = getattr(self, "shared_binance", None)
        if bw is None or not hasattr(bw, "get_recent_force_orders"):
            return None
        params: dict[str, object] = {"symbol": symbol, "limit": 20}
        if update_hint_ms:
            try:
                params["start_time"] = max(0, int(update_hint_ms) - 900_000)
            except Exception:
                pass
        orders = bw.get_recent_force_orders(**params) or []
        if not orders:
            return None
        expected_side = "SELL" if side_key == "L" else "BUY"
        now_ms = int(time.time() * 1000)
        for order in reversed(orders):
            if not isinstance(order, dict):
                continue
            order_side = str(order.get("side") or "").upper()
            if order_side != expected_side:
                continue
            try:
                order_time = int(float(order.get("updateTime") or order.get("time") or 0))
            except Exception:
                order_time = 0
            if order_time and abs(now_ms - order_time) > 900_000:
                continue
            qty_val = 0.0
            for qty_key in ("executedQty", "origQty"):
                val = order.get(qty_key)
                if val in (None, "", 0, 0.0):
                    continue
                try:
                    qty_val = abs(float(val))
                except Exception:
                    qty_val = 0.0
                if qty_val > 0:
                    break
            if qty_val <= 0.0:
                continue
            price_val = 0.0
            for price_key in ("avgPrice", "price"):
                val = order.get(price_key)
                if val in (None, "", 0, 0.0):
                    continue
                try:
                    price_val = float(val)
                except Exception:
                    price_val = 0.0
                if price_val > 0.0:
                    break
            if price_val <= 0.0:
                continue
            return {
                "close_price": price_val,
                "qty": qty_val,
                "time": order_time or now_ms,
                "raw": order,
            }
    except Exception:
        return None
    return None
