from __future__ import annotations

import math


def generate_signal(self, df, ind):
    cfg = self.config
    use_live = bool(getattr(self, "_indicator_use_live_values", False))
    min_bars = 2 if use_live else 3
    if df is None or df.empty or len(df) < min_bars:
        return None, "no data", None, [], {}

    sig_idx = -1 if use_live else -2
    prev_idx = sig_idx - 1
    try:
        sig_close = float(df["close"].iloc[sig_idx])
        prev_close = float(df["close"].iloc[prev_idx])
    except Exception:
        return None, "no data", None, [], {}

    signal = None
    trigger_desc = []
    trigger_sources: list[str] = []
    trigger_actions: dict[str, str] = {}

    rsi_cfg = cfg["indicators"].get("rsi", {})
    rsi_enabled = bool(rsi_cfg.get("enabled", False))
    if rsi_enabled and "rsi" in ind and not ind["rsi"].dropna().empty:
        try:
            _, _, r = self._indicator_prev_live_signal_values(ind["rsi"])
            if math.isfinite(r):
                trigger_desc.append(f"RSI={r:.2f}")
                buy_th = float(rsi_cfg.get("buy_value", 30) or 30)
                sell_th = float(rsi_cfg.get("sell_value", 70) or 70)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and r <= buy_th:
                    trigger_actions["rsi"] = "buy"
                    trigger_desc.append(f"RSI <= {buy_th:.2f} -> BUY")
                    trigger_sources.append("rsi")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and r >= sell_th:
                    trigger_actions["rsi"] = "sell"
                    trigger_desc.append(f"RSI >= {sell_th:.2f} -> SELL")
                    trigger_sources.append("rsi")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("RSI=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"RSI error:{e!r}")

    stoch_rsi_cfg = cfg["indicators"].get("stoch_rsi", {})
    stoch_rsi_enabled = bool(stoch_rsi_cfg.get("enabled", False))
    if stoch_rsi_enabled and "stoch_rsi_k" in ind and ind["stoch_rsi_k"] is not None:
        try:
            prev_srsi, live_srsi, srsi_val = self._indicator_prev_live_signal_values(ind["stoch_rsi_k"])
            trigger_desc.append(f"StochRSI %K={srsi_val:.2f} (prev={prev_srsi:.2f}, live={live_srsi:.2f})")
            buy_th = stoch_rsi_cfg.get("buy_value")
            sell_th = stoch_rsi_cfg.get("sell_value")
            buy_limit = float(buy_th if buy_th is not None else 20.0)
            sell_limit = float(sell_th if sell_th is not None else 80.0)
            buy_allowed = cfg["side"] in ("BUY", "BOTH")
            sell_allowed = cfg["side"] in ("SELL", "BOTH")
            if buy_allowed and srsi_val <= buy_limit:
                trigger_actions["stoch_rsi"] = "buy"
                trigger_desc.append(f"StochRSI %K <= {buy_limit:.2f} -> BUY")
                trigger_sources.append("stoch_rsi")
                if signal is None:
                    signal = "BUY"
            elif sell_allowed and srsi_val >= sell_limit:
                trigger_actions["stoch_rsi"] = "sell"
                trigger_desc.append(f"StochRSI %K >= {sell_limit:.2f} -> SELL")
                trigger_sources.append("stoch_rsi")
                if signal is None:
                    signal = "SELL"
        except Exception as e:
            trigger_desc.append(f"StochRSI error:{e!r}")

    willr_cfg = cfg["indicators"].get("willr", {})
    willr_enabled = bool(willr_cfg.get("enabled", False))
    if willr_enabled and "willr" in ind:
        try:
            prev_wr, live_wr, wr_signal = self._indicator_prev_live_signal_values(ind["willr"])
            trigger_desc.append(f"Williams %R(prev={prev_wr:.2f}, live={live_wr:.2f}) -> using {wr_signal:.2f}")
            buy_val = willr_cfg.get("buy_value")
            sell_val = willr_cfg.get("sell_value")
            buy_th = float(buy_val if buy_val is not None else -80.0)
            sell_th = float(sell_val if sell_val is not None else -20.0)
            buy_upper = max(-100.0, min(0.0, buy_th))
            buy_lower = -100.0
            sell_lower = max(-100.0, min(0.0, sell_th))
            sell_upper = 0.0
            buy_allowed = cfg["side"] in ("BUY", "BOTH")
            sell_allowed = cfg["side"] in ("SELL", "BOTH")
            if buy_allowed and buy_lower <= wr_signal <= buy_upper:
                trigger_actions["willr"] = "buy"
                trigger_desc.append(f"Williams %R in [{buy_lower:.2f}, {buy_upper:.2f}] -> BUY")
                trigger_sources.append("willr")
                if signal is None:
                    signal = "BUY"
            elif sell_allowed and sell_lower <= wr_signal <= sell_upper:
                trigger_actions["willr"] = "sell"
                trigger_desc.append(f"Williams %R in [{sell_lower:.2f}, {sell_upper:.2f}] -> SELL")
                trigger_sources.append("willr")
                if signal is None:
                    signal = "SELL"
        except Exception as e:
            trigger_desc.append(f"Williams %R error:{e!r}")

    ma_cfg = cfg["indicators"].get("ma", {})
    ma_enabled = bool(ma_cfg.get("enabled", False))
    if ma_enabled and "ma" in ind:
        ma = ind["ma"]
        ma_valid = len(ma.dropna()) >= 2
        if ma_valid:
            last_ma = float(ma.iloc[sig_idx])
            prev_ma = float(ma.iloc[prev_idx])
            trigger_desc.append(f"MA_prev={prev_ma:.8f},MA_last={last_ma:.8f}")
            buy_allowed = cfg["side"] in ("BUY", "BOTH")
            sell_allowed = cfg["side"] in ("SELL", "BOTH")
            if buy_allowed and prev_close < prev_ma and sig_close > last_ma:
                trigger_actions["ma"] = "buy"
                trigger_desc.append("MA crossover -> BUY")
                trigger_sources.append("ma")
                if signal is None:
                    signal = "BUY"
            elif sell_allowed and prev_close > prev_ma and sig_close < last_ma:
                trigger_actions["ma"] = "sell"
                trigger_desc.append("MA crossover -> SELL")
                trigger_sources.append("ma")
                if signal is None:
                    signal = "SELL"

    if cfg["indicators"].get("bb", {}).get("enabled", False) and "bb_upper" in ind and not ind["bb_upper"].isnull().all():
        try:
            bu = float(ind["bb_upper"].iloc[sig_idx])
            bm = float(ind["bb_mid"].iloc[sig_idx])
            bl = float(ind["bb_lower"].iloc[sig_idx])
            trigger_desc.append(f"BB_up={bu:.8f},BB_mid={bm:.8f},BB_low={bl:.8f}")
        except Exception:
            pass

    if not trigger_desc:
        trigger_desc = ["No triggers evaluated"]

    trigger_price = sig_close if signal else None
    trigger_sources = list(dict.fromkeys(trigger_sources))
    return signal, " | ".join(trigger_desc), trigger_price, trigger_sources, trigger_actions


def bind_strategy_signal_generation(strategy_cls) -> None:
    strategy_cls.generate_signal = generate_signal
