
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
