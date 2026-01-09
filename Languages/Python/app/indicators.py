
import pandas as pd

def sma(series, length):
    return series.rolling(length).mean()

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def donchian_high(df, length):
    return df['high'].rolling(length).max()

def donchian_low(df, length):
    return df['low'].rolling(length).min()

def bollinger_bands(df, length=20, std=2):
    ma = df['close'].rolling(length).mean()
    sd = df['close'].rolling(length).std()
    upper = ma + std * sd
    lower = ma - std * sd
    return upper, ma, lower

def rsi(series, length=14):
    """
    Wilder's RSI on CLOSE prices.
    Matches TradingView/Binance default when computed on *closed* candles.
    Falls back to pandas if pandas_ta is unavailable.
    """
    try:
        import pandas_ta as ta
        return ta.rsi(series, length=length)
    except Exception:
        delta = series.diff()
        up = delta.clip(lower=0.0)
        down = (-delta).clip(lower=0.0)
        roll_up = up.ewm(alpha=1/float(length), adjust=False).mean()
        roll_down = down.ewm(alpha=1/float(length), adjust=False).mean()
        rs = roll_up / roll_down
        return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def williams_r(df, length=14):
    highest_high = df['high'].rolling(length).max()
    lowest_low = df['low'].rolling(length).min()
    return (highest_high - df['close']) / (highest_high - lowest_low) * -100

def stoch_rsi(series, length=14, smooth_k=3, smooth_d=3):
    rsi_vals = rsi(series, length)
    min_rsi = rsi_vals.rolling(length).min()
    max_rsi = rsi_vals.rolling(length).max()
    stoch = 100 * (rsi_vals - min_rsi) / (max_rsi - min_rsi)
    k = stoch.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d

def parabolic_sar(df, af=0.02, max_af=0.2):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    length = len(df)
    if length == 0:
        return pd.Series(dtype=float)
    psar = close.copy()
    bull = True
    af_i = af
    ep = high[0]
    psar[0] = low[0]
    for i in range(1, length):
        prev = psar[i - 1]
        psar[i] = prev + af_i * (ep - prev)
        if bull:
            if low[i] < psar[i]:
                bull = False
                psar[i] = ep
                af_i = af
                ep = low[i]
            else:
                if high[i] > ep:
                    ep = high[i]
                    af_i = min(af_i + af, max_af)
        else:
            if high[i] > psar[i]:
                bull = True
                psar[i] = ep
                af_i = af
                ep = high[i]
            else:
                if low[i] < ep:
                    ep = low[i]
                    af_i = min(af_i + af, max_af)
    return pd.Series(psar, index=df.index)

def atr(df, length=14):
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)
    tr_components = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1)
    true_range = tr_components.max(axis=1)
    return true_range.ewm(alpha=1/float(length), adjust=False).mean()

def dmi(df, length=14):
    high = df['high']
    low = df['low']
    close = df['close']

    up_move = high.diff()
    down_move = (-low.diff())

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0).fillna(0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0).fillna(0.0)

    atr_series = atr(df, length)
    plus_smoothed = plus_dm.ewm(alpha=1/float(length), adjust=False).mean()
    minus_smoothed = minus_dm.ewm(alpha=1/float(length), adjust=False).mean()

    atr_nonzero = atr_series.replace(0, pd.NA)
    plus_di = (100.0 * (plus_smoothed / atr_nonzero)).fillna(0.0)
    minus_di = (100.0 * (minus_smoothed / atr_nonzero)).fillna(0.0)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100.0
    dx = dx.fillna(0.0)
    adx = dx.ewm(alpha=1/float(length), adjust=False).mean().fillna(0.0)
    return plus_di, minus_di, adx

def adx(df, length=14):
    _, _, adx_series = dmi(df, length=length)
    return adx_series

def ultimate_oscillator(df, short=7, medium=14, long=28):
    close = df['close']
    high = df['high']
    low = df['low']

    prev_close = close.shift(1).fillna(close)
    true_low = pd.concat([low, prev_close], axis=1).min(axis=1)
    true_high = pd.concat([high, prev_close], axis=1).max(axis=1)

    bp = close - true_low
    tr = true_high - true_low
    tr = tr.replace(0, pd.NA).fillna(0)

    def _rolling_sum(series, length):
        return series.rolling(length, min_periods=1).sum()

    avg_short = _rolling_sum(bp, short) / _rolling_sum(tr, short).replace(0, pd.NA)
    avg_medium = _rolling_sum(bp, medium) / _rolling_sum(tr, medium).replace(0, pd.NA)
    avg_long = _rolling_sum(bp, long) / _rolling_sum(tr, long).replace(0, pd.NA)

    uo = 100 * ((4 * avg_short) + (2 * avg_medium) + avg_long) / 7.0
    return uo.fillna(0.0)

def supertrend(df, atr_period=10, multiplier=3.0):
    if len(df) == 0:
        return pd.Series(dtype=float)
    high = df['high']
    low = df['low']
    close = df['close']
    atr_series = atr(df, length=atr_period)
    hl2 = (high + low) / 2.0

    basic_upper = hl2 + multiplier * atr_series
    basic_lower = hl2 - multiplier * atr_series

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()

    for i in range(1, len(df)):
        if close.iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = min(basic_upper.iloc[i], final_upper.iloc[i - 1])

        if close.iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = max(basic_lower.iloc[i], final_lower.iloc[i - 1])

    supertrend_line = pd.Series(index=df.index, dtype=float)
    supertrend_line.iloc[0] = hl2.iloc[0]
    for i in range(1, len(df)):
        prev = supertrend_line.iloc[i - 1]
        if prev == final_upper.iloc[i - 1]:
            if close.iloc[i] <= final_upper.iloc[i]:
                supertrend_line.iloc[i] = final_upper.iloc[i]
            else:
                supertrend_line.iloc[i] = final_lower.iloc[i]
        else:
            if close.iloc[i] >= final_lower.iloc[i]:
                supertrend_line.iloc[i] = final_lower.iloc[i]
            else:
                supertrend_line.iloc[i] = final_upper.iloc[i]
    return (close - supertrend_line).fillna(0.0)

def stochastic(df, length=14, smooth_k=3, smooth_d=3):
    if len(df) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    highest_high = df['high'].rolling(length).max()
    lowest_low = df['low'].rolling(length).min()
    k = 100 * (df['close'] - lowest_low) / (highest_high - lowest_low).replace(0, pd.NA)
    k = k.rolling(smooth_k, min_periods=1).mean()
    d = k.rolling(smooth_d, min_periods=1).mean()
    return k.fillna(0.0), d.fillna(0.0)
