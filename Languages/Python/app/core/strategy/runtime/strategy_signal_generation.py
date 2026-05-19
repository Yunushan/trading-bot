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
    coerce_enabled = getattr(self, "_strategy_coerce_bool", None)
    if not callable(coerce_enabled):
        def coerce_enabled(value, default=False):
            return bool(default if value is None else value)

    rsi_cfg = cfg["indicators"].get("rsi", {})
    rsi_enabled = coerce_enabled(rsi_cfg.get("enabled"), False)
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
    stoch_rsi_enabled = coerce_enabled(stoch_rsi_cfg.get("enabled"), False)
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
    willr_enabled = coerce_enabled(willr_cfg.get("enabled"), False)
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

    atr_cfg = cfg["indicators"].get("atr", {})
    atr_enabled = coerce_enabled(atr_cfg.get("enabled"), False)
    if atr_enabled and "atr" in ind and not ind["atr"].dropna().empty:
        try:
            _prev_atr, _live_atr, atr_val = self._indicator_prev_live_signal_values(ind["atr"])
            if math.isfinite(atr_val):
                trigger_desc.append(f"ATR={atr_val:.8f}")
            else:
                trigger_desc.append("ATR=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"ATR error:{e!r}")

    natr_cfg = cfg["indicators"].get("natr", {})
    natr_enabled = coerce_enabled(natr_cfg.get("enabled"), False)
    if natr_enabled and "natr" in ind and not ind["natr"].dropna().empty:
        try:
            _, _, natr_val = self._indicator_prev_live_signal_values(ind["natr"])
            if math.isfinite(natr_val):
                trigger_desc.append(f"NATR={natr_val:.4f}")
                buy_raw = natr_cfg.get("buy_value")
                sell_raw = natr_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and natr_val >= float(buy_raw):
                    trigger_actions["natr"] = "buy"
                    trigger_desc.append(f"NATR >= {float(buy_raw):.4f} -> BUY")
                    trigger_sources.append("natr")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and natr_val <= float(sell_raw):
                    trigger_actions["natr"] = "sell"
                    trigger_desc.append(f"NATR <= {float(sell_raw):.4f} -> SELL")
                    trigger_sources.append("natr")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("NATR=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"NATR error:{e!r}")

    vwap_cfg = cfg["indicators"].get("vwap", {})
    vwap_enabled = coerce_enabled(vwap_cfg.get("enabled"), False)
    if vwap_enabled and "vwap" in ind and not ind["vwap"].dropna().empty:
        try:
            prev_vwap, live_vwap, vwap_val = self._indicator_prev_live_signal_values(ind["vwap"])
            if math.isfinite(vwap_val):
                side_label = "above" if sig_close >= vwap_val else "below"
                trigger_desc.append(
                    f"VWAP={vwap_val:.8f} (prev={prev_vwap:.8f}, live={live_vwap:.8f}, close {side_label})"
                )
            else:
                trigger_desc.append("VWAP=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"VWAP error:{e!r}")

    mfi_cfg = cfg["indicators"].get("mfi", {})
    mfi_enabled = coerce_enabled(mfi_cfg.get("enabled"), False)
    if mfi_enabled and "mfi" in ind and not ind["mfi"].dropna().empty:
        try:
            _, _, mfi_val = self._indicator_prev_live_signal_values(ind["mfi"])
            if math.isfinite(mfi_val):
                trigger_desc.append(f"MFI={mfi_val:.2f}")
                buy_th = float(mfi_cfg.get("buy_value", 20) or 20)
                sell_th = float(mfi_cfg.get("sell_value", 80) or 80)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and mfi_val <= buy_th:
                    trigger_actions["mfi"] = "buy"
                    trigger_desc.append(f"MFI <= {buy_th:.2f} -> BUY")
                    trigger_sources.append("mfi")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and mfi_val >= sell_th:
                    trigger_actions["mfi"] = "sell"
                    trigger_desc.append(f"MFI >= {sell_th:.2f} -> SELL")
                    trigger_sources.append("mfi")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("MFI=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"MFI error:{e!r}")

    obv_cfg = cfg["indicators"].get("obv", {})
    obv_enabled = coerce_enabled(obv_cfg.get("enabled"), False)
    if obv_enabled and "obv" in ind and not ind["obv"].dropna().empty:
        try:
            prev_obv, live_obv, obv_val = self._indicator_prev_live_signal_values(ind["obv"])
            if math.isfinite(obv_val):
                if live_obv > prev_obv:
                    trend = "rising"
                elif live_obv < prev_obv:
                    trend = "falling"
                else:
                    trend = "flat"
                trigger_desc.append(
                    f"OBV={obv_val:.2f} (prev={prev_obv:.2f}, live={live_obv:.2f}, {trend})"
                )
                buy_raw = obv_cfg.get("buy_value")
                sell_raw = obv_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and obv_val >= float(buy_raw):
                    trigger_actions["obv"] = "buy"
                    trigger_desc.append(f"OBV >= {float(buy_raw):.2f} -> BUY")
                    trigger_sources.append("obv")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and obv_val <= float(sell_raw):
                    trigger_actions["obv"] = "sell"
                    trigger_desc.append(f"OBV <= {float(sell_raw):.2f} -> SELL")
                    trigger_sources.append("obv")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("OBV=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"OBV error:{e!r}")

    rvol_cfg = cfg["indicators"].get("rvol", {})
    rvol_enabled = coerce_enabled(rvol_cfg.get("enabled"), False)
    if rvol_enabled and "rvol" in ind and not ind["rvol"].dropna().empty:
        try:
            _, _, rvol_val = self._indicator_prev_live_signal_values(ind["rvol"])
            if math.isfinite(rvol_val):
                trigger_desc.append(f"RVOL={rvol_val:.4f}")
                buy_raw = rvol_cfg.get("buy_value")
                sell_raw = rvol_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and rvol_val >= float(buy_raw):
                    trigger_actions["rvol"] = "buy"
                    trigger_desc.append(f"RVOL >= {float(buy_raw):.4f} -> BUY")
                    trigger_sources.append("rvol")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and rvol_val <= float(sell_raw):
                    trigger_actions["rvol"] = "sell"
                    trigger_desc.append(f"RVOL <= {float(sell_raw):.4f} -> SELL")
                    trigger_sources.append("rvol")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("RVOL=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"RVOL error:{e!r}")

    cmf_cfg = cfg["indicators"].get("cmf", {})
    cmf_enabled = coerce_enabled(cmf_cfg.get("enabled"), False)
    if cmf_enabled and "cmf" in ind and not ind["cmf"].dropna().empty:
        try:
            prev_cmf, live_cmf, cmf_val = self._indicator_prev_live_signal_values(ind["cmf"])
            if math.isfinite(cmf_val):
                flow_state = "accumulation" if cmf_val > 0 else "distribution" if cmf_val < 0 else "neutral"
                trigger_desc.append(
                    f"CMF={cmf_val:.4f} (prev={prev_cmf:.4f}, live={live_cmf:.4f}, {flow_state})"
                )
                buy_raw = cmf_cfg.get("buy_value")
                sell_raw = cmf_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and cmf_val >= float(buy_raw):
                    trigger_actions["cmf"] = "buy"
                    trigger_desc.append(f"CMF >= {float(buy_raw):.4f} -> BUY")
                    trigger_sources.append("cmf")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and cmf_val <= float(sell_raw):
                    trigger_actions["cmf"] = "sell"
                    trigger_desc.append(f"CMF <= {float(sell_raw):.4f} -> SELL")
                    trigger_sources.append("cmf")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("CMF=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"CMF error:{e!r}")

    cci_cfg = cfg["indicators"].get("cci", {})
    cci_enabled = coerce_enabled(cci_cfg.get("enabled"), False)
    if cci_enabled and "cci" in ind and not ind["cci"].dropna().empty:
        try:
            _, _, cci_val = self._indicator_prev_live_signal_values(ind["cci"])
            if math.isfinite(cci_val):
                trigger_desc.append(f"CCI={cci_val:.2f}")
                buy_raw = cci_cfg.get("buy_value")
                sell_raw = cci_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else -100.0)
                sell_th = float(sell_raw if sell_raw is not None else 100.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and cci_val <= buy_th:
                    trigger_actions["cci"] = "buy"
                    trigger_desc.append(f"CCI <= {buy_th:.2f} -> BUY")
                    trigger_sources.append("cci")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and cci_val >= sell_th:
                    trigger_actions["cci"] = "sell"
                    trigger_desc.append(f"CCI >= {sell_th:.2f} -> SELL")
                    trigger_sources.append("cci")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("CCI=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"CCI error:{e!r}")

    roc_cfg = cfg["indicators"].get("roc", {})
    roc_enabled = coerce_enabled(roc_cfg.get("enabled"), False)
    if roc_enabled and "roc" in ind and not ind["roc"].dropna().empty:
        try:
            _, _, roc_val = self._indicator_prev_live_signal_values(ind["roc"])
            if math.isfinite(roc_val):
                trigger_desc.append(f"ROC={roc_val:.2f}")
                buy_raw = roc_cfg.get("buy_value")
                sell_raw = roc_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 0.0)
                sell_th = float(sell_raw if sell_raw is not None else 0.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and roc_val >= buy_th:
                    trigger_actions["roc"] = "buy"
                    trigger_desc.append(f"ROC >= {buy_th:.2f} -> BUY")
                    trigger_sources.append("roc")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and roc_val <= sell_th:
                    trigger_actions["roc"] = "sell"
                    trigger_desc.append(f"ROC <= {sell_th:.2f} -> SELL")
                    trigger_sources.append("roc")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("ROC=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"ROC error:{e!r}")

    trix_cfg = cfg["indicators"].get("trix", {})
    trix_enabled = coerce_enabled(trix_cfg.get("enabled"), False)
    if trix_enabled and "trix" in ind and not ind["trix"].dropna().empty:
        try:
            _, _, trix_val = self._indicator_prev_live_signal_values(ind["trix"])
            if math.isfinite(trix_val):
                trigger_desc.append(f"TRIX={trix_val:.4f}")
                buy_raw = trix_cfg.get("buy_value")
                sell_raw = trix_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 0.0)
                sell_th = float(sell_raw if sell_raw is not None else 0.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and trix_val >= buy_th:
                    trigger_actions["trix"] = "buy"
                    trigger_desc.append(f"TRIX >= {buy_th:.4f} -> BUY")
                    trigger_sources.append("trix")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and trix_val <= sell_th:
                    trigger_actions["trix"] = "sell"
                    trigger_desc.append(f"TRIX <= {sell_th:.4f} -> SELL")
                    trigger_sources.append("trix")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("TRIX=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"TRIX error:{e!r}")

    bbw_cfg = cfg["indicators"].get("bbw", {})
    bbw_enabled = coerce_enabled(bbw_cfg.get("enabled"), False)
    if bbw_enabled and "bbw" in ind and not ind["bbw"].dropna().empty:
        try:
            _, _, bbw_val = self._indicator_prev_live_signal_values(ind["bbw"])
            if math.isfinite(bbw_val):
                trigger_desc.append(f"BBW={bbw_val:.4f}")
                buy_raw = bbw_cfg.get("buy_value")
                sell_raw = bbw_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and bbw_val >= float(buy_raw):
                    trigger_actions["bbw"] = "buy"
                    trigger_desc.append(f"BBW >= {float(buy_raw):.4f} -> BUY")
                    trigger_sources.append("bbw")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and bbw_val <= float(sell_raw):
                    trigger_actions["bbw"] = "sell"
                    trigger_desc.append(f"BBW <= {float(sell_raw):.4f} -> SELL")
                    trigger_sources.append("bbw")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("BBW=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"BBW error:{e!r}")

    ppo_cfg = cfg["indicators"].get("ppo", {})
    ppo_enabled = coerce_enabled(ppo_cfg.get("enabled"), False)
    if ppo_enabled and "ppo_hist" in ind and not ind["ppo_hist"].dropna().empty:
        try:
            _, _, ppo_val = self._indicator_prev_live_signal_values(ind["ppo"])
            _, _, ppo_signal = self._indicator_prev_live_signal_values(ind["ppo_signal"])
            _, _, ppo_hist = self._indicator_prev_live_signal_values(ind["ppo_hist"])
            if math.isfinite(ppo_hist):
                trigger_desc.append(f"PPO={ppo_val:.4f},PPO_signal={ppo_signal:.4f},hist={ppo_hist:.4f}")
                buy_raw = ppo_cfg.get("buy_value")
                sell_raw = ppo_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 0.0)
                sell_th = float(sell_raw if sell_raw is not None else 0.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and ppo_hist >= buy_th:
                    trigger_actions["ppo"] = "buy"
                    trigger_desc.append(f"PPO hist >= {buy_th:.4f} -> BUY")
                    trigger_sources.append("ppo")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and ppo_hist <= sell_th:
                    trigger_actions["ppo"] = "sell"
                    trigger_desc.append(f"PPO hist <= {sell_th:.4f} -> SELL")
                    trigger_sources.append("ppo")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("PPO=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"PPO error:{e!r}")

    ao_cfg = cfg["indicators"].get("ao", {})
    ao_enabled = coerce_enabled(ao_cfg.get("enabled"), False)
    if ao_enabled and "ao" in ind and not ind["ao"].dropna().empty:
        try:
            _, _, ao_val = self._indicator_prev_live_signal_values(ind["ao"])
            if math.isfinite(ao_val):
                trigger_desc.append(f"AO={ao_val:.4f}")
                buy_raw = ao_cfg.get("buy_value")
                sell_raw = ao_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 0.0)
                sell_th = float(sell_raw if sell_raw is not None else 0.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and ao_val >= buy_th:
                    trigger_actions["ao"] = "buy"
                    trigger_desc.append(f"AO >= {buy_th:.4f} -> BUY")
                    trigger_sources.append("ao")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and ao_val <= sell_th:
                    trigger_actions["ao"] = "sell"
                    trigger_desc.append(f"AO <= {sell_th:.4f} -> SELL")
                    trigger_sources.append("ao")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("AO=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"AO error:{e!r}")

    kst_cfg = cfg["indicators"].get("kst", {})
    kst_enabled = coerce_enabled(kst_cfg.get("enabled"), False)
    if kst_enabled and "kst_hist" in ind and not ind["kst_hist"].dropna().empty:
        try:
            _, _, kst_val = self._indicator_prev_live_signal_values(ind["kst"])
            _, _, kst_signal = self._indicator_prev_live_signal_values(ind["kst_signal"])
            _, _, kst_spread = self._indicator_prev_live_signal_values(ind["kst_hist"])
            if math.isfinite(kst_spread):
                trigger_desc.append(f"KST={kst_val:.4f},KST_signal={kst_signal:.4f},spread={kst_spread:.4f}")
                buy_raw = kst_cfg.get("buy_value")
                sell_raw = kst_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 0.0)
                sell_th = float(sell_raw if sell_raw is not None else 0.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and kst_spread >= buy_th:
                    trigger_actions["kst"] = "buy"
                    trigger_desc.append(f"KST spread >= {buy_th:.4f} -> BUY")
                    trigger_sources.append("kst")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and kst_spread <= sell_th:
                    trigger_actions["kst"] = "sell"
                    trigger_desc.append(f"KST spread <= {sell_th:.4f} -> SELL")
                    trigger_sources.append("kst")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("KST=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"KST error:{e!r}")

    aroon_cfg = cfg["indicators"].get("aroon", {})
    aroon_enabled = coerce_enabled(aroon_cfg.get("enabled"), False)
    if aroon_enabled and "aroon" in ind and not ind["aroon"].dropna().empty:
        try:
            _, _, aroon_val = self._indicator_prev_live_signal_values(ind["aroon"])
            up_series = ind.get("aroon_up")
            down_series = ind.get("aroon_down")
            _prev_up, _live_up, up_val = self._indicator_prev_live_signal_values(up_series)
            _prev_down, _live_down, down_val = self._indicator_prev_live_signal_values(down_series)
            if math.isfinite(aroon_val):
                trigger_desc.append(
                    f"Aroon={aroon_val:.2f} (up={up_val:.2f}, down={down_val:.2f})"
                )
                buy_raw = aroon_cfg.get("buy_value")
                sell_raw = aroon_cfg.get("sell_value")
                buy_th = float(buy_raw if buy_raw is not None else 50.0)
                sell_th = float(sell_raw if sell_raw is not None else -50.0)
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_allowed and aroon_val >= buy_th:
                    trigger_actions["aroon"] = "buy"
                    trigger_desc.append(f"Aroon >= {buy_th:.2f} -> BUY")
                    trigger_sources.append("aroon")
                    if signal is None:
                        signal = "BUY"
                elif sell_allowed and aroon_val <= sell_th:
                    trigger_actions["aroon"] = "sell"
                    trigger_desc.append(f"Aroon <= {sell_th:.2f} -> SELL")
                    trigger_sources.append("aroon")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("Aroon=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"Aroon error:{e!r}")

    chop_cfg = cfg["indicators"].get("chop", {})
    chop_enabled = coerce_enabled(chop_cfg.get("enabled"), False)
    if chop_enabled and "chop" in ind and not ind["chop"].dropna().empty:
        try:
            _, _, chop_val = self._indicator_prev_live_signal_values(ind["chop"])
            if math.isfinite(chop_val):
                trigger_desc.append(f"CHOP={chop_val:.4f}")
                buy_raw = chop_cfg.get("buy_value")
                sell_raw = chop_cfg.get("sell_value")
                buy_allowed = cfg["side"] in ("BUY", "BOTH")
                sell_allowed = cfg["side"] in ("SELL", "BOTH")
                if buy_raw is not None and buy_allowed and chop_val <= float(buy_raw):
                    trigger_actions["chop"] = "buy"
                    trigger_desc.append(f"CHOP <= {float(buy_raw):.4f} -> BUY")
                    trigger_sources.append("chop")
                    if signal is None:
                        signal = "BUY"
                elif sell_raw is not None and sell_allowed and chop_val >= float(sell_raw):
                    trigger_actions["chop"] = "sell"
                    trigger_desc.append(f"CHOP >= {float(sell_raw):.4f} -> SELL")
                    trigger_sources.append("chop")
                    if signal is None:
                        signal = "SELL"
            else:
                trigger_desc.append("CHOP=NaN/inf skipped")
        except Exception as e:
            trigger_desc.append(f"CHOP error:{e!r}")

    ma_cfg = cfg["indicators"].get("ma", {})
    ma_enabled = coerce_enabled(ma_cfg.get("enabled"), False)
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

    if (
        coerce_enabled(cfg["indicators"].get("bb", {}).get("enabled"), False)
        and "bb_upper" in ind
        and not ind["bb_upper"].isnull().all()
    ):
        try:
            bu = float(ind["bb_upper"].iloc[sig_idx])
            bm = float(ind["bb_mid"].iloc[sig_idx])
            bl = float(ind["bb_lower"].iloc[sig_idx])
            trigger_desc.append(f"BB_up={bu:.8f},BB_mid={bm:.8f},BB_low={bl:.8f}")
        except Exception:
            pass

    if (
        coerce_enabled(cfg["indicators"].get("keltner", {}).get("enabled"), False)
        and "keltner_upper" in ind
        and not ind["keltner_upper"].isnull().all()
    ):
        try:
            ku = float(ind["keltner_upper"].iloc[sig_idx])
            km = float(ind["keltner_mid"].iloc[sig_idx])
            kl = float(ind["keltner_lower"].iloc[sig_idx])
            if sig_close > ku:
                channel_state = "above upper"
            elif sig_close < kl:
                channel_state = "below lower"
            else:
                channel_state = "inside channel"
            trigger_desc.append(
                f"KC_up={ku:.8f},KC_mid={km:.8f},KC_low={kl:.8f},close {channel_state}"
            )
        except Exception:
            pass

    ichimoku_cfg = cfg["indicators"].get("ichimoku", {})
    if (
        coerce_enabled(ichimoku_cfg.get("enabled"), False)
        and "ichimoku_tenkan" in ind
        and "ichimoku_kijun" in ind
        and not ind["ichimoku_tenkan"].dropna().empty
        and not ind["ichimoku_kijun"].dropna().empty
    ):
        try:
            tenkan = float(ind["ichimoku_tenkan"].iloc[sig_idx])
            kijun = float(ind["ichimoku_kijun"].iloc[sig_idx])
            spread = tenkan - kijun
            span_a_series = ind.get("ichimoku_span_a")
            span_b_series = ind.get("ichimoku_span_b")
            span_a = float(span_a_series.iloc[sig_idx]) if span_a_series is not None else math.nan
            span_b = float(span_b_series.iloc[sig_idx]) if span_b_series is not None else math.nan
            cloud_top = max(span_a, span_b) if math.isfinite(span_a) and math.isfinite(span_b) else math.nan
            cloud_bottom = min(span_a, span_b) if math.isfinite(span_a) and math.isfinite(span_b) else math.nan
            if math.isfinite(cloud_top) and sig_close > cloud_top:
                cloud_state = "above cloud"
            elif math.isfinite(cloud_bottom) and sig_close < cloud_bottom:
                cloud_state = "below cloud"
            elif math.isfinite(cloud_top) and math.isfinite(cloud_bottom):
                cloud_state = "inside cloud"
            else:
                cloud_state = "cloud unavailable"
            trigger_desc.append(
                f"IC_tenkan={tenkan:.8f},IC_kijun={kijun:.8f},"
                f"IC_span_a={span_a:.8f},IC_span_b={span_b:.8f},spread={spread:.8f},close {cloud_state}"
            )
            buy_raw = ichimoku_cfg.get("buy_value")
            sell_raw = ichimoku_cfg.get("sell_value")
            buy_allowed = cfg["side"] in ("BUY", "BOTH")
            sell_allowed = cfg["side"] in ("SELL", "BOTH")
            if buy_raw is not None and buy_allowed and spread >= float(buy_raw):
                trigger_actions["ichimoku"] = "buy"
                trigger_desc.append(f"IC spread >= {float(buy_raw):.2f} -> BUY")
                trigger_sources.append("ichimoku")
                if signal is None:
                    signal = "BUY"
            elif sell_raw is not None and sell_allowed and spread <= float(sell_raw):
                trigger_actions["ichimoku"] = "sell"
                trigger_desc.append(f"IC spread <= {float(sell_raw):.2f} -> SELL")
                trigger_sources.append("ichimoku")
                if signal is None:
                    signal = "SELL"
        except Exception as e:
            trigger_desc.append(f"Ichimoku error:{e!r}")

    if not trigger_desc:
        trigger_desc = ["No triggers evaluated"]

    trigger_price = sig_close if signal else None
    trigger_sources = list(dict.fromkeys(trigger_sources))
    return signal, " | ".join(trigger_desc), trigger_price, trigger_sources, trigger_actions


def bind_strategy_signal_generation(strategy_cls) -> None:
    strategy_cls.generate_signal = generate_signal
