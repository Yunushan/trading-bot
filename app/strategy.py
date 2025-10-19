
import time, copy, traceback, math, threading, os
from datetime import datetime, timezone

import pandas as pd
from .config import STOP_LOSS_MODE_ORDER, STOP_LOSS_SCOPE_OPTIONS, normalize_stop_loss_dict
from .binance_wrapper import NetworkConnectivityError, normalize_margin_ratio
from .indicators import (
    sma,
    ema,
    bollinger_bands,
    rsi as rsi_fallback,
    macd as macd_fallback,
    stoch_rsi as stoch_rsi_fallback,
    williams_r as williams_r_fallback,
    parabolic_sar as psar_fallback,
    ultimate_oscillator as uo_fallback,
    dmi as dmi_fallback,
    adx as adx_fallback,
    supertrend as supertrend_fallback,
    stochastic as stochastic_fallback,
)
from .preamble import PANDAS_TA_AVAILABLE, PANDAS_VERSION, PANDAS_TA_VERSION

def _interval_to_seconds(iv:str)->int:
    try:
        if iv.endswith('m'): return int(iv[:-1])*60
        if iv.endswith('s'): return int(iv[:-1])
        if iv.endswith('h'): return int(iv[:-1])*3600
        if iv.endswith('d'): return int(iv[:-1])*86400
    except Exception:
        pass
    return 60


_MAX_PARALLEL_RUNS = max(2, min(4, (os.cpu_count() or 4)))


class StrategyEngine:
    _RUN_GATE = threading.BoundedSemaphore(_MAX_PARALLEL_RUNS)
    _MAX_ACTIVE = _MAX_PARALLEL_RUNS

    @classmethod
    def concurrent_limit(cls):
        return cls._MAX_ACTIVE

    def __init__(self, binance_wrapper, config, log_callback, trade_callback=None, loop_interval_override=None, can_open_callback=None):
        self.config = copy.deepcopy(config)
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.binance = binance_wrapper
        self.log = log_callback
        self.trade_cb = trade_callback
        self.loop_override = loop_interval_override
        self._leg_ledger = {}
        self._last_order_time = {}  # (symbol, interval, side)->{'qty': float, 'timestamp': float}
        self._last_bar_key = set()  # prevent multi entries within same bar per (symbol, interval, side)
        self.can_open_cb = can_open_callback
        self._stop = False
        key = f"{str(self.config.get('symbol') or '').upper()}@{str(self.config.get('interval') or '').lower()}"
        h = abs(hash(key)) if key.strip('@') else 0
        self._phase_seed = (h % 997) / 997.0 if key.strip('@') else 0.0
        self._phase_offset = self._phase_seed * 25.0
        self._thread = None
        self._offline_backoff = 0.0
        self._last_network_log = 0.0
        self._emergency_close_triggered = False

    def _notify_interval_closed(self, symbol: str, interval: str, position_side: str):
        if not self.trade_cb:
            return
        try:
            info = {
                'symbol': symbol,
                'interval': interval,
                'side': position_side,
                'position_side': position_side,
                'event': 'close_interval',
                'status': 'closed',
                'ok': True,
                'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')
            }
            self.trade_cb(info)
        except Exception:
            pass

    def stop(self):
        self._stop = True

    def stopped(self):
        return self._stop

    def is_alive(self):
        try:
            thread = getattr(self, '_thread', None)
            return bool(thread) and bool(getattr(thread, 'is_alive', lambda: False)())
        except Exception:
            return False

    def join(self, timeout=None):
        try:
            thread = getattr(self, '_thread', None)
            if thread and thread.is_alive():
                thread.join(timeout)
        except Exception:
            pass

    def _close_opposite_position(self, symbol: str, interval: str, next_side: str) -> bool:
        """Ensure no net exposure in the opposite direction before opening a new leg."""
        try:
            positions = self.binance.list_open_futures_positions() or []
        except Exception as e:
            self.log(f"{symbol}@{interval} read positions failed: {e}")
            return False
        desired = (next_side or '').upper()
        if desired not in ('BUY', 'SELL'):
            return True
        try:
            dual = bool(self.binance.get_futures_dual_side())
        except Exception:
            dual = False
        opp = 'SELL' if desired == 'BUY' else 'BUY'
        opp_key = (symbol, interval, opp)

        if dual:
            entry = self._leg_ledger.get(opp_key) if hasattr(self, '_leg_ledger') else None
            try:
                qty_to_close = float(entry.get('qty', 0.0)) if entry else 0.0
            except Exception:
                qty_to_close = 0.0
            if qty_to_close <= 0:
                return True
            pos_side = 'SHORT' if opp == 'SELL' else 'LONG'
            reduce_only_missing = False
            res = None
            try:
                res = self.binance.close_futures_leg_exact(symbol, qty_to_close, side=desired, position_side=pos_side)
            except Exception as exc:
                msg = str(exc)
                if "-2022" in msg or "ReduceOnly" in msg or "reduceonly" in msg.lower():
                    reduce_only_missing = True
                else:
                    self.log(f"{symbol}@{interval} close-opposite exception: {exc}")
                    return False
            if isinstance(res, dict) and not res.get('ok', True):
                err_msg = str(res.get('error') or "")
                if "-2022" in err_msg or "reduceonly" in err_msg.lower():
                    reduce_only_missing = True
                else:
                    self.log(f"{symbol}@{interval} close-opposite failed: {res}")
                    return False
            if not reduce_only_missing:
                self._notify_interval_closed(symbol, interval, opp)
            self._leg_ledger.pop(opp_key, None)
            if hasattr(self, '_last_order_time'):
                self._last_order_time.pop(opp_key, None)
            return True

        closed_any = False
        for p in positions:
            try:
                if str(p.get('symbol') or '').upper() != symbol:
                    continue
                amt = float(p.get('positionAmt') or 0.0)
                if desired == 'BUY' and amt < 0:
                    qty = abs(amt)
                    res = self.binance.close_futures_leg_exact(symbol, qty, side='BUY', position_side=None)
                    self._notify_interval_closed(symbol, interval, 'SELL')
                    if not (isinstance(res, dict) and res.get('ok')):
                        self.log(f"{symbol}@{interval} close-short failed: {res}")
                        return False
                    closed_any = True
                elif desired == 'SELL' and amt > 0:
                    qty = abs(amt)
                    res = self.binance.close_futures_leg_exact(symbol, qty, side='SELL', position_side=None)
                    self._notify_interval_closed(symbol, interval, 'BUY')
                    if not (isinstance(res, dict) and res.get('ok')):
                        self.log(f"{symbol}@{interval} close-long failed: {res}")
                        return False
                    closed_any = True
            except Exception as exc:
                self.log(f"{symbol}@{interval} close-opposite exception: {exc}")
                return False
        if closed_any:
            try:
                import time as _t
                _t.sleep(0.05)
            except Exception:
                pass
            for key in list(self._leg_ledger.keys()):
                if key[0] == symbol and key[2] == opp:
                    self._leg_ledger.pop(key, None)
        return True
    # ---- indicator computation (uses pandas_ta when available)
    def compute_indicators(self, df):
        cfg = self.config['indicators']
        ind = {}
        if df.empty:
            return ind
        try:
            import pandas_ta as ta  # optional
            has_accessor = hasattr(df['close'], 'ta')
        except Exception:
            ta = None
            has_accessor = False

        # MA
        ma_cfg = cfg.get('ma', {})
        if ma_cfg.get('enabled'):
            if has_accessor and cfg['ma'].get('type','SMA').upper()=='SMA':
                ind['ma'] = df['close'].ta.sma(length=int(cfg['ma']['length']))
            elif has_accessor:
                ind['ma'] = df['close'].ta.ema(length=int(cfg['ma']['length']))
            else:
                if cfg['ma'].get('type','SMA').upper()=='SMA':
                    ind['ma'] = sma(df['close'], int(cfg['ma']['length']))
                else:
                    ind['ma'] = ema(df['close'], int(cfg['ma']['length']))

        ema_cfg = cfg.get('ema', {})
        if ema_cfg.get('enabled'):
            length = int(ema_cfg.get('length') or 20)
            if has_accessor:
                try:
                    ind['ema'] = df['close'].ta.ema(length=length)
                except Exception:
                    ind['ema'] = ema(df['close'], length)
            else:
                ind['ema'] = ema(df['close'], length)

        # BB
        bb_cfg = cfg.get('bb', {})
        if bb_cfg.get('enabled'):
            if has_accessor:
                try:
                    bb = df['close'].ta.bbands(length=int(cfg['bb']['length']), std=float(cfg['bb']['std']))
                    ind['bb_upper'] = bb.iloc[:,0]; ind['bb_mid'] = bb.iloc[:,1]; ind['bb_lower'] = bb.iloc[:,2]
                except Exception:
                    upper, mid, lower = bollinger_bands(df, int(cfg['bb']['length']), float(cfg['bb']['std']))
                    ind['bb_upper'], ind['bb_mid'], ind['bb_lower'] = upper, mid, lower
            else:
                upper, mid, lower = bollinger_bands(df, int(cfg['bb']['length']), float(cfg['bb']['std']))
                ind['bb_upper'], ind['bb_mid'], ind['bb_lower'] = upper, mid, lower

        # RSI
        if cfg.get('rsi', {}).get('enabled'):
            if has_accessor:
                ind['rsi'] = df['close'].ta.rsi(length=int(cfg['rsi']['length']))
            else:
                ind['rsi'] = rsi_fallback(df['close'], length=int(cfg['rsi']['length']))

        # Stochastic RSI
        stoch_rsi_cfg = cfg.get('stoch_rsi', {})
        if stoch_rsi_cfg.get('enabled'):
            length = int(stoch_rsi_cfg.get('length') or 14)
            smooth_k = int(stoch_rsi_cfg.get('smooth_k') or 3)
            smooth_d = int(stoch_rsi_cfg.get('smooth_d') or 3)
            k_series = None
            d_series = None
            if has_accessor:
                try:
                    srsi_df = df['close'].ta.stochrsi(length=length, rsi_length=length, k=smooth_k, d=smooth_d)
                    cols = list(srsi_df.columns) if srsi_df is not None else []
                    if cols:
                        k_series = srsi_df[cols[0]]
                        if len(cols) > 1:
                            d_series = srsi_df[cols[1]]
                except Exception:
                    k_series = None
                    d_series = None
            if k_series is None or d_series is None:
                k_series, d_series = stoch_rsi_fallback(df['close'], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            ind['stoch_rsi'] = k_series
            ind['stoch_rsi_k'] = k_series
            ind['stoch_rsi_d'] = d_series

        # Williams %R
        if cfg.get('willr', {}).get('enabled'):
            try:
                length = int(cfg['willr'].get('length') or 14)
            except Exception:
                length = 14
            length = max(1, length)
            if has_accessor:
                try:
                    ind['willr'] = df.ta.willr(length=length)
                except Exception:
                    ind['willr'] = williams_r_fallback(df, length=length)
            else:
                ind['willr'] = williams_r_fallback(df, length=length)

        # MACD (kept for completeness)
        if cfg.get('macd', {}).get('enabled'):
            if has_accessor:
                macd_df = df['close'].ta.macd(fast=int(cfg['macd']['fast']), slow=int(cfg['macd']['slow']), signal=int(cfg['macd']['signal']))
                ind['macd_line'] = macd_df.iloc[:,0]; ind['macd_signal'] = macd_df.iloc[:,1]
            else:
                macdl, macds, _ = macd_fallback(df['close'], int(cfg['macd']['fast']), int(cfg['macd']['slow']), int(cfg['macd']['signal']))
                ind['macd_line'], ind['macd_signal'] = macdl, macds

        if cfg.get('uo', {}).get('enabled'):
            short = int(cfg['uo'].get('short') or 7)
            medium = int(cfg['uo'].get('medium') or 14)
            long = int(cfg['uo'].get('long') or 28)
            ind['uo'] = uo_fallback(df, short=short, medium=medium, long=long)

        if cfg.get('adx', {}).get('enabled'):
            length = int(cfg['adx'].get('length') or 14)
            if has_accessor:
                try:
                    adx_df = df.ta.adx(length=length)
                    adx_cols = [c for c in adx_df.columns if 'ADX' in c.upper()]
                    ind['adx'] = adx_df[adx_cols[0]] if adx_cols else adx_fallback(df, length=length)
                except Exception:
                    ind['adx'] = adx_fallback(df, length=length)
            else:
                ind['adx'] = adx_fallback(df, length=length)

        if cfg.get('dmi', {}).get('enabled'):
            length = int(cfg['dmi'].get('length') or 14)
            plus_series = minus_series = None
            if has_accessor:
                try:
                    dmi_df = df.ta.dmi(length=length)
                    cols = list(dmi_df.columns)
                    if len(cols) >= 2:
                        plus_series = dmi_df[cols[0]]
                        minus_series = dmi_df[cols[1]]
                except Exception:
                    plus_series = minus_series = None
            if plus_series is None or minus_series is None:
                plus_series, minus_series, _ = dmi_fallback(df, length=length)
            ind['dmi_plus'] = plus_series
            ind['dmi_minus'] = minus_series
            ind['dmi'] = (plus_series - minus_series)

        if cfg.get('supertrend', {}).get('enabled'):
            atr_period = int(cfg['supertrend'].get('atr_period') or 10)
            multiplier = float(cfg['supertrend'].get('multiplier') or 3.0)
            ind['supertrend'] = supertrend_fallback(df, atr_period=atr_period, multiplier=multiplier)

        if cfg.get('stochastic', {}).get('enabled'):
            length = int(cfg['stochastic'].get('length') or 14)
            smooth_k = int(cfg['stochastic'].get('smooth_k') or 3)
            smooth_d = int(cfg['stochastic'].get('smooth_d') or 3)
            k_series = None
            d_series = None
            if has_accessor:
                try:
                    stoch_df = df.ta.stoch(k=length, d=smooth_d, smooth_k=smooth_k)
                    cols = list(stoch_df.columns)
                    if cols:
                        k_series = stoch_df[cols[0]]
                        if len(cols) > 1:
                            d_series = stoch_df[cols[1]]
                except Exception:
                    k_series = None
                    d_series = None
            if k_series is None or d_series is None:
                k_series, d_series = stochastic_fallback(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            ind['stochastic'] = k_series
            ind['stochastic_k'] = k_series
            ind['stochastic_d'] = d_series

        return ind

    def _interval_seconds(self, interval: str) -> int:
        try:
            if interval.endswith('s'): return int(interval[:-1])
            if interval.endswith('m'): return int(interval[:-1]) * 60
            if interval.endswith('h'): return int(interval[:-1]) * 3600
            if interval.endswith('d'): return int(interval[:-1]) * 86400
            if interval.endswith('w'): return int(interval[:-1]) * 7 * 86400
            return int(interval)
        except Exception:
            return 60

    def generate_signal(self, df, ind):
        cfg = self.config
        if df.empty or len(df) < 2:
            return None, "no data", None

        last_close = float(df['close'].iloc[-1])
        prev_close = float(df['close'].iloc[-2])

        signal = None
        trigger_desc = []

        # --- RSI thresholds as primary triggers ---
        rsi_cfg = cfg['indicators'].get('rsi', {})
        rsi_enabled = bool(rsi_cfg.get('enabled', False))
        if rsi_enabled and 'rsi' in ind and not ind['rsi'].dropna().empty:
            try:
                r = float(ind['rsi'].iloc[-2])
                if math.isfinite(r):
                    trigger_desc.append(f"RSI={r:.2f}")
                    buy_th = float(rsi_cfg.get('buy_value', 30) or 30)
                    sell_th = float(rsi_cfg.get('sell_value', 70) or 70)
                    if r <= buy_th and cfg['side'] in ('BUY','BOTH'):
                        signal = 'BUY'; trigger_desc.append(f"RSI <= {buy_th:.2f} → BUY")
                    elif r >= sell_th and cfg['side'] in ('SELL','BOTH'):
                        signal = 'SELL'; trigger_desc.append(f"RSI >= {sell_th:.2f} → SELL")
                else:
                    trigger_desc.append("RSI=NaN/inf skipped")
            except Exception as e:
                trigger_desc.append(f"RSI error:{e!r}")

        # --- Stochastic RSI thresholds ---
        stoch_rsi_cfg = cfg['indicators'].get('stoch_rsi', {})
        stoch_rsi_enabled = bool(stoch_rsi_cfg.get('enabled', False))
        if stoch_rsi_enabled and 'stoch_rsi_k' in ind and ind['stoch_rsi_k'] is not None:
            try:
                srsi_series = ind['stoch_rsi_k'].dropna()
                if not srsi_series.empty:
                    srsi_val = float(srsi_series.iloc[-2])
                    trigger_desc.append(f"StochRSI %K={srsi_val:.2f}")
                    buy_th = stoch_rsi_cfg.get('buy_value')
                    sell_th = stoch_rsi_cfg.get('sell_value')
                    buy_limit = float(buy_th if buy_th is not None else 20.0)
                    sell_limit = float(sell_th if sell_th is not None else 80.0)
                    if signal is None and cfg['side'] in ('BUY', 'BOTH') and srsi_val <= buy_limit:
                        signal = 'BUY'; trigger_desc.append(f"StochRSI %K <= {buy_limit:.2f} → BUY")
                    elif signal is None and cfg['side'] in ('SELL', 'BOTH') and srsi_val >= sell_limit:
                        signal = 'SELL'; trigger_desc.append(f"StochRSI %K >= {sell_limit:.2f} → SELL")
            except Exception as e:
                trigger_desc.append(f"StochRSI error:{e!r}")

        # --- Williams %R thresholds ---
        willr_cfg = cfg['indicators'].get('willr', {})
        willr_enabled = bool(willr_cfg.get('enabled', False))
        if willr_enabled and 'willr' in ind and not ind['willr'].dropna().empty:
            try:
                wr = float(ind['willr'].iloc[-2])
                if math.isfinite(wr):
                    trigger_desc.append(f"Williams %R={wr:.2f}")
                    buy_val = willr_cfg.get('buy_value')
                    sell_val = willr_cfg.get('sell_value')
                    buy_th = float(buy_val if buy_val is not None else -80.0)
                    sell_th = float(sell_val if sell_val is not None else -20.0)
                    buy_upper = max(-100.0, min(0.0, buy_th))
                    buy_lower = -100.0
                    sell_lower = max(-100.0, min(0.0, sell_th))
                    sell_upper = 0.0
                    if signal is None and cfg['side'] in ('BUY','BOTH') and buy_lower <= wr <= buy_upper:
                        signal = 'BUY'; trigger_desc.append(f"Williams %R in [{buy_lower:.2f}, {buy_upper:.2f}] → BUY")
                    elif signal is None and cfg['side'] in ('SELL','BOTH') and sell_lower <= wr <= sell_upper:
                        signal = 'SELL'; trigger_desc.append(f"Williams %R in [{sell_lower:.2f}, {sell_upper:.2f}] → SELL")
                else:
                    trigger_desc.append("Williams %R=NaN/inf skipped")
            except Exception as e:
                trigger_desc.append(f"Williams %R error:{e!r}")

        # --- MA crossover (optional alternative trigger) ---
        ma_cfg = cfg['indicators'].get('ma', {})
        ma_enabled = bool(ma_cfg.get('enabled', False))
        if ma_enabled and 'ma' in ind:
            ma = ind['ma']
            ma_valid = len(ma.dropna()) >= 2
            if ma_valid:
                last_ma = float(ma.iloc[-1]); prev_ma = float(ma.iloc[-2])
                trigger_desc.append(f"MA_prev={prev_ma:.8f},MA_last={last_ma:.8f}")
                if signal is None:
                    if prev_close < prev_ma and last_close > last_ma and cfg['side'] in ('BUY','BOTH'):
                        signal = 'BUY'; trigger_desc.append("MA crossover → BUY")
                    elif prev_close > prev_ma and last_close < last_ma and cfg['side'] in ('SELL','BOTH'):
                        signal = 'SELL'; trigger_desc.append("MA crossover → SELL")

        # --- BB context (informational)
        if cfg['indicators'].get('bb', {}).get('enabled', False) and 'bb_upper' in ind and not ind['bb_upper'].isnull().all():
            try:
                bu = float(ind['bb_upper'].iloc[-1]); bm = float(ind['bb_mid'].iloc[-1]); bl = float(ind['bb_lower'].iloc[-1])
                trigger_desc.append(f"BB_up={bu:.8f},BB_mid={bm:.8f},BB_low={bl:.8f}")
            except Exception:
                pass

        if not trigger_desc:
            trigger_desc = ["No triggers evaluated"]

        trigger_price = last_close if signal else None
        return signal, " | ".join(trigger_desc), trigger_price

    def run_once(self):
        cw = self.config
        stop_cfg = normalize_stop_loss_dict(cw.get("stop_loss"))
        stop_mode = str(stop_cfg.get("mode") or "usdt").lower()
        if stop_mode not in STOP_LOSS_MODE_ORDER:
            stop_mode = STOP_LOSS_MODE_ORDER[0]
        stop_usdt_limit = max(0.0, float(stop_cfg.get("usdt", 0.0) or 0.0))
        stop_percent_limit = max(0.0, float(stop_cfg.get("percent", 0.0) or 0.0))
        scope = str(stop_cfg.get("scope") or "per_trade").lower()
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        stop_enabled = bool(stop_cfg.get("enabled", False))
        apply_usdt_limit = stop_enabled and stop_mode in ("usdt", "both") and stop_usdt_limit > 0.0
        apply_percent_limit = stop_enabled and stop_mode in ("percent", "both") and stop_percent_limit > 0.0
        stop_enabled = apply_usdt_limit or apply_percent_limit
        account_type = str((self.config.get("account_type") or self.binance.account_type)).upper()
        is_cumulative = stop_enabled and scope == "cumulative"
        is_entire_account = stop_enabled and scope == "entire_account"
        if is_entire_account and account_type == "FUTURES":
            total_unrealized = 0.0
            try:
                total_unrealized = float(self.binance.get_total_unrealized_pnl())
            except Exception:
                total_unrealized = 0.0
            triggered = False
            reason = None
            if apply_usdt_limit and total_unrealized <= -stop_usdt_limit:
                triggered = True
                reason = f"entire-account-usdt-limit ({total_unrealized:.2f})"
            if not triggered and apply_percent_limit:
                total_wallet = 0.0
                try:
                    total_wallet = float(self.binance.get_total_wallet_balance())
                except Exception:
                    total_wallet = 0.0
                if total_wallet > 0.0 and total_unrealized < 0.0:
                    loss_pct = (abs(total_unrealized) / total_wallet) * 100.0
                    if loss_pct >= stop_percent_limit:
                        triggered = True
                        reason = f"entire-account-percent-limit ({loss_pct:.2f}%)"
            if triggered:
                try:
                    self.log(f"{cw['symbol']}@{cw.get('interval')} entire account stop-loss triggered: {reason}.")
                except Exception:
                    pass
                self._trigger_emergency_close(cw['symbol'], cw.get('interval'), reason or "entire_account_stop")
                return
        elif is_entire_account:
            stop_enabled = False
        df = self.binance.get_klines(cw['symbol'], cw['interval'], limit=cw.get('lookback', 200))
        ind = self.compute_indicators(df)
        signal, trigger_desc, trigger_price = self.generate_signal(df, ind)
        
        # --- RSI guard-close (interval-scoped) ---
        try:
            rsi_series = ind.get('rsi') or ind.get('RSI') or None
            last_rsi = float(rsi_series.iloc[-2]) if rsi_series is not None and len(rsi_series.dropna()) else None
        except Exception:
            last_rsi = None

        # Open-state via internal ledger (per symbol, interval, side)
        key_short = (cw['symbol'], cw.get('interval'), 'SELL')
        key_long  = (cw['symbol'], cw.get('interval'), 'BUY')
        short_open = bool(self._leg_ledger.get(key_short, {}).get('qty', 0) > 0)
        long_open  = bool(self._leg_ledger.get(key_long,  {}).get('qty', 0) > 0)

        # Exit thresholds
        try:
            rsi_cfg = cw.get('indicators',{}).get('rsi',{})
            exit_up = float(rsi_cfg.get('sell_value', 70))
            exit_dn = float(rsi_cfg.get('buy_value', 30))
        except Exception:
            exit_up, exit_dn = 70.0, 30.0

        if last_rsi is not None:
            # Close LONG when RSI >= sell threshold (e.g., 70)
            if long_open and last_rsi >= exit_up:
                try:
                    leg = self._leg_ledger.get(key_long)
                    qty = float(leg.get('qty', 0)) if leg else 0.0
                    if qty > 0:
                        desired_ps = ('LONG' if self.binance.get_futures_dual_side() else None)
                        res = self.binance.close_futures_leg_exact(cw['symbol'], qty, side='BUY', position_side=desired_ps)
                        if isinstance(res, dict) and res.get('ok'):
                            self._leg_ledger.pop(key_long, None)
                            try:
                                if hasattr(self.guard, 'mark_closed'): self.guard.mark_closed(cw['symbol'], cw.get('interval'), 'BUY')
                            except Exception:
                                pass
                            self._notify_interval_closed(cw['symbol'], cw.get('interval'), 'BUY')
                            self.log(f"Closed LONG for {cw['symbol']}@{cw.get('interval')} (RSI ≥ {exit_up}).")
                except Exception:
                    pass
            # Close SHORT when RSI <= buy threshold (e.g., 30)
            if short_open and last_rsi <= exit_dn:
                try:
                    leg = self._leg_ledger.get(key_short)
                    qty = float(leg.get('qty', 0)) if leg else 0.0
                    if qty > 0:
                        desired_ps = ('SHORT' if self.binance.get_futures_dual_side() else None)
                        res = self.binance.close_futures_leg_exact(cw['symbol'], qty, side='SELL', position_side=desired_ps)
                        if isinstance(res, dict) and res.get('ok'):
                            self._leg_ledger.pop(key_short, None)
                            try:
                                if hasattr(self.guard, 'mark_closed'): self.guard.mark_closed(cw['symbol'], cw.get('interval'), 'SELL')
                            except Exception:
                                pass
                            self._notify_interval_closed(cw['symbol'], cw.get('interval'), 'SELL')
                            self.log(f"Closed SHORT for {cw['symbol']}@{cw.get('interval')} (RSI ≤ {exit_dn}).")
                except Exception:
                    pass

        last_price = float(df['close'].iloc[-1]) if not df.empty else None

        dual_side = False
        if account_type == "FUTURES":
            try:
                dual_side = bool(self.binance.get_futures_dual_side())
            except Exception:
                dual_side = False
        positions_cache = None

        if stop_enabled and last_price is not None and account_type == "FUTURES":
            def _ensure_entry_price(leg_key, expect_long: bool):
                nonlocal positions_cache
                leg = self._leg_ledger.get(leg_key, {}) or {}
                qty_val = float(leg.get("qty") or 0.0)
                entry_px = float(leg.get("entry_price") or 0.0)
                matched_pos = None
                if qty_val > 0.0 and entry_px <= 0.0:
                    if positions_cache is None:
                        try:
                            positions_cache = self.binance.list_open_futures_positions() or []
                        except Exception:
                            positions_cache = []
                    for pos in positions_cache or []:
                        try:
                            if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                                continue
                            pos_side = str(pos.get("positionSide") or "").upper()
                            amt = float(pos.get("positionAmt") or 0.0)
                            if dual_side:
                                if expect_long and pos_side != "LONG":
                                    continue
                                if (not expect_long) and pos_side != "SHORT":
                                    continue
                                qty_candidate = abs(float(pos.get("positionAmt") or 0.0))
                                if qty_candidate <= 0.0:
                                    continue
                                entry_px = float(pos.get("entryPrice") or 0.0)
                                matched_pos = pos
                                break
                            else:
                                if expect_long and amt <= 0.0:
                                    continue
                                if (not expect_long) and amt >= 0.0:
                                    continue
                                entry_px = float(pos.get("entryPrice") or 0.0)
                                matched_pos = pos
                                break
                        except Exception:
                            continue
                    if entry_px > 0.0:
                        leg["entry_price"] = entry_px
                        self._leg_ledger[leg_key] = leg
                if matched_pos is None and positions_cache:
                    try:
                        for pos in positions_cache:
                            if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                                continue
                            if dual_side:
                                side_str = str(pos.get("positionSide") or "").upper()
                                if expect_long and side_str != "LONG":
                                    continue
                                if (not expect_long) and side_str != "SHORT":
                                    continue
                            matched_pos = pos
                            break
                    except Exception:
                        matched_pos = None
                return leg, qty_val, entry_px, matched_pos

            leg_long, qty_long, entry_price_long, pos_long = _ensure_entry_price(key_long, True)
            leg_short, qty_short, entry_price_short, pos_short = _ensure_entry_price(key_short, False)

            if is_cumulative:
                if positions_cache is None:
                    try:
                        positions_cache = self.binance.list_open_futures_positions() or []
                    except Exception:
                        positions_cache = []
                totals = {
                    "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                    "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
                }
                for pos in positions_cache or []:
                    try:
                        if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                            continue
                        pos_side = str(pos.get("positionSide") or "").upper()
                        amt = float(pos.get("positionAmt") or 0.0)
                        entry_px = float(pos.get("entryPrice") or 0.0)
                        if entry_px <= 0.0:
                            continue
                        if dual_side:
                            if pos_side == "LONG":
                                qty_pos = max(0.0, float(pos.get("positionAmt") or 0.0))
                                side_key = "LONG"
                            elif pos_side == "SHORT":
                                qty_pos = max(0.0, abs(float(pos.get("positionAmt") or 0.0)))
                                side_key = "SHORT"
                            else:
                                continue
                        else:
                            if amt > 0.0:
                                qty_pos = amt
                                side_key = "LONG"
                            elif amt < 0.0:
                                qty_pos = abs(amt)
                                side_key = "SHORT"
                            else:
                                continue
                        if qty_pos <= 0.0:
                            continue
                        margin_val = float(pos.get("isolatedWallet") or 0.0)
                        if margin_val <= 0.0:
                            margin_val = float(pos.get("initialMargin") or 0.0)
                        if margin_val <= 0.0:
                            notional_val = abs(float(pos.get("notional") or 0.0))
                            lev = float(pos.get("leverage") or 1.0) or 1.0
                            if lev > 0.0:
                                margin_val = notional_val / lev
                        if side_key == "LONG":
                            loss_val = max(0.0, (entry_px - last_price) * qty_pos)
                        else:
                            loss_val = max(0.0, (last_price - entry_px) * qty_pos)
                        totals[side_key]["qty"] += qty_pos
                        totals[side_key]["loss"] += loss_val
                        totals[side_key]["margin"] += max(0.0, margin_val)
                    except Exception:
                        continue
                cumulative_triggered = False
                for side_key in ("LONG", "SHORT"):
                    data = totals[side_key]
                    if data["qty"] <= 0.0:
                        continue
                    triggered = False
                    if apply_usdt_limit and data["loss"] >= stop_usdt_limit:
                        triggered = True
                    if (
                        not triggered
                        and apply_percent_limit
                        and data["margin"] > 0.0
                        and (data["loss"] / data["margin"] * 100.0) >= stop_percent_limit
                    ):
                        triggered = True
                    if not triggered:
                        continue
                    cumulative_triggered = True
                    close_side = "BUY" if side_key == "LONG" else "SELL"
                    position_side = side_key if dual_side else None
                    try:
                        res = self.binance.close_futures_leg_exact(
                            cw["symbol"], data["qty"], side=close_side, position_side=position_side
                        )
                    except Exception as exc:
                        try:
                            self.log(f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
                        except Exception:
                            pass
                        continue
                    if isinstance(res, dict) and res.get("ok"):
                        target_side_label = "BUY" if side_key == "LONG" else "SELL"
                        for leg_key in list(self._leg_ledger.keys()):
                            if leg_key[0] == cw["symbol"] and leg_key[2] == target_side_label:
                                self._leg_ledger.pop(leg_key, None)
                                self._last_order_time.pop(leg_key, None)
                        try:
                            if hasattr(self.guard, "mark_closed"):
                                self.guard.mark_closed(cw["symbol"], cw.get("interval"), target_side_label)
                        except Exception:
                            pass
                        self._notify_interval_closed(cw["symbol"], cw.get("interval"), target_side_label)
                        try:
                            margin_val = data["margin"] or 0.0
                            pct_loss = (data["loss"] / margin_val * 100.0) if margin_val > 0.0 else 0.0
                            self.log(
                                f"Cumulative stop-loss closed {target_side_label} for {cw['symbol']}@{cw.get('interval')} "
                                f"(loss {data['loss']:.4f} USDT / {pct_loss:.2f}%)."
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            self.log(
                                f"Cumulative stop-loss close failed for {cw['symbol']} ({side_key}): {res}"
                            )
                        except Exception:
                            pass
                if cumulative_triggered:
                    position_open = False
                    units = 0.0
                    position_margin = 0.0
                    direction = ""
                    long_open = False
                    short_open = False
            else:
                if qty_long > 0.0 and entry_price_long > 0.0:
                    loss_usdt_long = max(0.0, (entry_price_long - last_price) * qty_long)
                    denom_long = entry_price_long * qty_long
                    loss_pct_long = (loss_usdt_long / denom_long * 100.0) if denom_long > 0 else 0.0
                    ratio_long = normalize_margin_ratio((pos_long or {}).get("marginRatio"))
                    triggered_long = False
                    if apply_usdt_limit and loss_usdt_long >= stop_usdt_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and loss_pct_long >= stop_percent_limit:
                        triggered_long = True
                    if not triggered_long and apply_percent_limit and ratio_long >= stop_percent_limit:
                        triggered_long = True
                        if ratio_long > loss_pct_long:
                            loss_pct_long = ratio_long
                    if triggered_long:
                        desired_ps = "LONG" if dual_side else None
                        try:
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_long, side="BUY", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                self._leg_ledger.pop(key_long, None)
                                self._last_order_time.pop(key_long, None)
                                long_open = False
                                try:
                                    if hasattr(self.guard, "mark_closed"):
                                        self.guard.mark_closed(cw["symbol"], cw.get("interval"), "BUY")
                                except Exception:
                                    pass
                                self._notify_interval_closed(cw["symbol"], cw.get("interval"), "BUY")
                                try:
                                    self.log(
                                        f"Stop-loss closed BUY for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_long:.4f} USDT / {loss_pct_long:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (BUY): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                self.log(
                                    f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (BUY): {exc}"
                                )
                            except Exception:
                                pass
                if qty_short > 0.0 and entry_price_short > 0.0:
                    loss_usdt_short = max(0.0, (last_price - entry_price_short) * qty_short)
                    denom_short = entry_price_short * qty_short
                    loss_pct_short = (loss_usdt_short / denom_short * 100.0) if denom_short > 0 else 0.0
                    ratio_short = normalize_margin_ratio((pos_short or {}).get("marginRatio"))
                    triggered_short = False
                    if apply_usdt_limit and loss_usdt_short >= stop_usdt_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and loss_pct_short >= stop_percent_limit:
                        triggered_short = True
                    if not triggered_short and apply_percent_limit and ratio_short >= stop_percent_limit:
                        triggered_short = True
                        if ratio_short > loss_pct_short:
                            loss_pct_short = ratio_short
                    if triggered_short:
                        desired_ps = "SHORT" if dual_side else None
                        try:
                            res = self.binance.close_futures_leg_exact(
                                cw["symbol"], qty_short, side="SELL", position_side=desired_ps
                            )
                            if isinstance(res, dict) and res.get("ok"):
                                self._leg_ledger.pop(key_short, None)
                                self._last_order_time.pop(key_short, None)
                                short_open = False
                                try:
                                    if hasattr(self.guard, "mark_closed"):
                                        self.guard.mark_closed(cw["symbol"], cw.get("interval"), "SELL")
                                except Exception:
                                    pass
                                self._notify_interval_closed(cw["symbol"], cw.get("interval"), "SELL")
                                try:
                                    self.log(
                                        f"Stop-loss closed SELL for {cw['symbol']}@{cw.get('interval')} "
                                        f"(loss {loss_usdt_short:.4f} USDT / {loss_pct_short:.2f}%)."
                                    )
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.log(
                                        f"Stop-loss close failed for {cw['symbol']}@{cw.get('interval')} (SELL): {res}"
                                    )
                                except Exception:
                                    pass
                        except Exception as exc:
                            try:
                                self.log(
                                    f"Stop-loss close error for {cw['symbol']}@{cw.get('interval')} (SELL): {exc}"
                                )
                            except Exception:
                                pass

        thresholds = []
        try:
            if cw['indicators']['ma']['enabled'] and 'ma' in ind and not ind['ma'].isnull().all(): 
                thresholds.append(f"MA={float(ind['ma'].iloc[-1]):.8f}")
        except Exception: 
            pass

        ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"{ts}", f"{cw['symbol']}@{cw['interval']}",
                 f"Price={last_price:.8f}" if last_price is not None else "Price=None",
                 f"Signal={signal if signal else 'None'}"]
        if trigger_price is not None: parts.append(f"TriggerPrice={trigger_price:.8f}")
        if thresholds: parts.append("Thresholds:" + ",".join(thresholds))
        parts.append("Details:" + trigger_desc)
        self.log(" | ".join(parts))

        # Duplicate-open guard: skip if the same side is already open for this symbol@interval
        try:
            key_dup = (cw['symbol'], cw.get('interval'), str(signal).upper())
            leg_dup = self._leg_ledger.get(key_dup)
            if signal and leg_dup and float(leg_dup.get('qty',0))>0:
                position_amt = 0.0
                try:
                    position_amt = float(self.binance.get_net_futures_position_amt(cw['symbol']))
                except Exception:
                    position_amt = 0.0
                if abs(position_amt) <= 0.0:
                    try:
                        self._leg_ledger.pop(key_dup, None)
                    except Exception:
                        pass
                else:
                    self.log(f"{cw['symbol']}@{cw.get('interval')} duplicate {str(signal).upper()} open prevented (position still active).")
                    signal = None
        except Exception:
            pass
        if signal and cw.get('trade_on_signal', True):
            try:
                account_type = str((self.config.get('account_type') or self.binance.account_type)).upper()
                usdt_bal = self.binance.get_total_usdt_value()
                pct_raw = float(cw.get('position_pct', 100.0))
                pct = pct_raw/100.0 if pct_raw > 1.0 else pct_raw
                pct = max(0.0001, min(1.0, pct))
                use_usdt = usdt_bal * pct
                price = last_price or 0.0

                if account_type == "FUTURES":
                    lev = max(1, int(cw.get('leverage', 1)))
                    qty_est = (use_usdt * lev / price) if price > 0 else 0.0
                    # FLIP_GUARD (optional via add_only): in one-way mode, avoid crossing zero and block opposite opens
                    reduce_only = False
                    if bool(self.config.get('add_only', False)):
                        dual = self.binance.get_futures_dual_side()
                        if not dual:
                            try:
                                net_amt = float(self.binance.get_net_futures_position_amt(cw['symbol']))
                            except Exception:
                                net_amt = 0.0
                            if (net_amt > 0 and signal.upper() == 'SELL'):
                                qty_est = min(qty_est, abs(net_amt)); reduce_only = True
                            elif (net_amt < 0 and signal.upper() == 'BUY'):
                                qty_est = min(qty_est, abs(net_amt)); reduce_only = True
                            if qty_est <= 0:
                                self.log(f"{cw['symbol']}@{cw['interval']} Opposite open blocked (one-way add-only). net={net_amt}")
                                return

                    desired_ps = None
                    if self.binance.get_futures_dual_side():
                        desired_ps = 'LONG' if signal.upper() == 'BUY' else 'SHORT'
                        # HEDGE_ADD_GUARD removed: allow stacking adds across intervals

                    # Prevent stacking entries within the same candle: debounce by interval length
                    try:
                        key_bar = (cw['symbol'], cw.get('interval'), signal.upper())
                        now_ts = time.time()
                        secs = _interval_to_seconds(str(cw.get('interval') or '1m'))
                        last_ts = self._last_order_time.get(key_bar, 0)
                        if now_ts - last_ts < max(5, secs * 0.9):
                            return  # wait for bar close (no re-entry within same candle)
                    except Exception:
                        pass

                    # Close prior leg for the same (symbol, interval) on opposite signal
                    if not self._close_opposite_position(cw['symbol'], cw.get('interval'), signal.upper()):
                        return

                    if callable(self.can_open_cb):
                        if not self.can_open_cb(cw['symbol'], cw.get('interval'), signal.upper()):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} Duplicate guard: {signal.upper()} already open - skipping.")
                            return
                    order_res = self.binance.place_futures_market_order(
                        cw['symbol'], signal,
                        percent_balance=(pct*100.0),
                        leverage=lev,
                        reduce_only=(False if self.binance.get_futures_dual_side() else reduce_only),
                        position_side=desired_ps,
                        price=cw.get('price'),
                        strict=True,
                        timeInForce=self.config.get('tif','GTC'),
                        gtd_minutes=int(self.config.get('gtd_minutes',30)),
                        interval=cw.get('interval'),
                        max_auto_bump_percent=float(self.config.get('max_auto_bump_percent', 5.0)),
                        auto_bump_percent_multiplier=float(self.config.get('auto_bump_percent_multiplier', 10.0)),
                    )
                    # Emit trade callback (futures) for UI/guard
                    try:
                        qty_emit = float(order_res.get('computed',{}).get('qty') or 0.0)
                        if qty_emit <= 0:
                            qty_emit = float(order_res.get('info',{}).get('origQty') or 0.0)
                        if self.trade_cb:
                            self.trade_cb({
                                'symbol': cw['symbol'],
                                'interval': cw.get('interval'),
                                'side': signal,
                                'qty': qty_emit,
                                'price': cw.get('price'),
                                'time': datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S'),
                                'status': 'placed',
                                'ok': bool(order_res.get('ok', True))
                            })
                    except Exception:
                        pass
                    # Emit trade callback (futures) so UI can show Entry TF
                    try:
                        qty_emit = float(order_res.get('computed',{}).get('qty') or 0.0)
                        if qty_emit <= 0:
                            qty_emit = float(order_res.get('info',{}).get('origQty') or 0.0)
                        if self.trade_cb:
                            self.trade_cb({
                                "symbol": cw['symbol'],
                                "interval": cw.get('interval'),
                                "side": signal,
                                "qty": qty_emit,
                                "price": cw.get('price'),
                                "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                                "status": "placed",
                                "ok": bool(order_res.get('ok', True))
                            })
                    except Exception:
                        pass
                    try:
                        try:
                            if (not order_res.get('ok')) and callable(self.trade_cb):
                                self.trade_cb({
                                    'symbol': cw['symbol'],
                                    'interval': cw.get('interval'),
                                    'side': signal,
                                    'qty': float(order_res.get('computed',{}).get('qty') or 0.0),
                                    'price': cw.get('price'),
                                    'time': datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                                    'status': 'error',
                                    'ok': False
                                })
                        except Exception:
                            pass
                        if order_res.get('ok'):
                            key = (cw['symbol'], cw.get('interval'), signal.upper())
                            qty = float(order_res.get('info',{}).get('origQty') or order_res.get('computed',{}).get('qty') or 0)
                            if qty > 0:
                                entry_price_est = price
                                try:
                                    avg_px = (order_res.get('info', {}) or {}).get('avgPrice')
                                    if avg_px:
                                        entry_price_est = float(avg_px)
                                    else:
                                        computed_px = (order_res.get('computed', {}) or {}).get('px')
                                        if computed_px:
                                            entry_price_est = float(computed_px)
                                except Exception:
                                    entry_price_est = price
                                self._leg_ledger[key] = {
                                    'qty': qty,
                                    'timestamp': time.time(),
                                    'entry_price': float(entry_price_est or price),
                                }
                                self._last_order_time[key] = time.time()
                    except Exception:
                        pass
                    qty_display = order_res.get('executedQty') or order_res.get('origQty') or qty_est

                else:
                    # SPOT logic: BUY uses quote amount (USDT); SELL requires existing base balance
                    filters = self.binance.get_spot_symbol_filters(cw['symbol'])
                    min_notional = float(filters.get('minNotional', 0.0) or 0.0)
                    price = float(last_price or 0.0)
                    if signal.upper() == 'BUY':
                        # Spend pct of total USDT, but ensure >= minNotional when possible
                        total_usdt = float(self.binance.get_spot_balance('USDT') or 0.0)
                        use_usdt = total_usdt * pct
                        if min_notional > 0 and use_usdt < min_notional:
                            # try to bump to min_notional if funds allow
                            if total_usdt >= min_notional:
                                use_usdt = min_notional
                        order_res = self.binance.place_spot_market_order(
                            cw['symbol'], 'BUY', quantity=0.0, price=price, use_quote=True, quote_amount=use_usdt
                        )
                        qty_display = order_res.get('executedQty') or order_res.get('origQty')
                    else:
                        # SELL only if we hold the base asset
                        base_asset, _ = self.binance.get_base_quote_assets(cw['symbol'])
                        base_free = float(self.binance.get_spot_balance(base_asset) or 0.0)
                        if base_free <= 0:
                            self.log(f"Skip SELL for {cw['symbol']}: no {base_asset} balance. Spot cannot open shorts with USDT. Switch Account Type to FUTURES to short.")
                            return
                        est_notional = base_free * (price or 0.0) * pct
                        if min_notional > 0 and est_notional < min_notional:
                            self.log(f"Skip SELL for {cw['symbol']}: position value {est_notional:.8f} < minNotional {min_notional:.8f}.")
                            return
                        qty_to_sell = base_free * pct
                        order_res = self.binance.place_spot_market_order(
                            cw['symbol'], 'SELL', quantity=qty_to_sell, price=price, use_quote=False
                        )
                        qty_display = order_res.get('executedQty') or order_res.get('origQty') or qty_to_sell

                order_info = {
                    "symbol": cw['symbol'], "interval": cw['interval'], "side": signal,
                    "qty": float(qty_display) if qty_display else 0.0, "price": price,
                    "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "placed"
                }
                if self.trade_cb:
                    self.trade_cb(order_info)
                self.log(f"{cw['symbol']}@{cw['interval']} Order placed: {order_res}")
            except Exception as e:
                self.log(f"{cw['symbol']}@{cw['interval']} Order failed: {e}")

    def _trigger_emergency_close(self, sym: str, interval: str, reason: str):
        if self._emergency_close_triggered:
            return
        self._emergency_close_triggered = True
        try:
            self.log(f"{sym}@{interval} connectivity lost ({reason}); scheduling emergency close of all positions.")
        except Exception:
            pass
        try:
            closer = getattr(self.binance, "trigger_emergency_close_all", None)
            if callable(closer):
                closer(reason=f"{sym}@{interval}: {reason}", source="strategy")
            else:
                from .close_all import close_all_futures_positions as _close_all_fut
                def _do_close():
                    try:
                        _close_all_fut(self.binance)
                    except Exception:
                        pass
                threading.Thread(target=_do_close, name=f"EmergencyClose-{sym}@{interval}", daemon=True).start()
        except Exception as exc:
            try:
                self.log(f"{sym}@{interval} emergency close scheduling failed: {exc}")
            except Exception:
                pass
        finally:
            try:
                self.stop()
            except Exception:
                self._stop = True

    def _handle_network_outage(self, sym: str, interval: str, exc: Exception) -> float:
        prev = getattr(self, "_offline_backoff", 0.0) or 0.0
        backoff = 5.0 if prev <= 0.0 else min(90.0, max(prev * 1.5, 5.0))
        self._offline_backoff = backoff
        now = time.time()
        reason_txt = str(exc)
        if reason_txt.startswith("network_offline"):
            parts = reason_txt.split(":", 2)
            if len(parts) >= 2:
                reason_txt = parts[-1] or "network_offline"
        if (now - getattr(self, "_last_network_log", 0.0)) >= 8.0:
            self._last_network_log = now
            try:
                self.log(f"{sym}@{interval} network offline ({reason_txt}); emergency close queued; retrying in {backoff:.0f}s.")
            except Exception:
                pass
        self._trigger_emergency_close(sym, interval, reason_txt)
        return backoff

    def run_loop(self):
        sym = self.config.get('symbol', '(unknown)')
        interval = self.config.get('interval', '(unknown)')
        self.log(f"Loop start for {sym} @ {interval}.")
        if self.loop_override:
            interval_seconds = max(1, int(self._interval_seconds(self.loop_override)))
        else:
            interval_seconds = max(1, int(self._interval_seconds(self.config['interval'])))
        phase_span = max(5.0, min(interval_seconds * 0.85, 45.0))
        phase = self._phase_seed * phase_span
        if phase > 0:
            waited = 0.0
            while waited < phase and not self.stopped():
                chunk = min(0.5, phase - waited)
                time.sleep(chunk)
                waited += chunk
        while not self.stopped():
            got_gate = False
            sleep_override = None
            try:
                if self.stopped():
                    break
                got_gate = StrategyEngine._RUN_GATE.acquire(timeout=1.0)
                if not got_gate:
                    continue
                self.run_once()
                self._offline_backoff = 0.0
                self._last_network_log = 0.0
            except NetworkConnectivityError as e:
                sleep_override = self._handle_network_outage(sym, interval, e)
            except Exception as e:
                self.log(f"Error in {sym}@{interval} loop: {repr(e)}")
                try:
                    self.log(traceback.format_exc())
                except Exception:
                    pass
            finally:
                if got_gate:
                    try:
                        StrategyEngine._RUN_GATE.release()
                    except Exception:
                        pass
            sleep_remaining = interval_seconds if sleep_override is None else float(max(0.0, sleep_override))
            if sleep_override is None and interval_seconds > 1:
                jitter = self._phase_seed * min(3.0, max(0.5, interval_seconds * 0.2))
                sleep_remaining += jitter
            while sleep_remaining > 0 and not self.stopped():
                chunk = min(1.0, sleep_remaining)
                time.sleep(chunk)
                sleep_remaining -= chunk
        self.log(f"Loop stopped for {sym} @ {interval}.")

    def set_guard(self, guard):
        """Attach/replace risk guard (hedge gate)."""
        self.guard = guard
        return self

    def start(self):
        """Start the strategy loop in a daemon thread."""
        t = threading.Thread(
            target=self.run_loop,
            name=f"StrategyLoop-{self.config.get('symbol','?')}@{self.config.get('interval','?')} ",
            daemon=True,
        )
        t.start()
        self._thread = t
        return t
