import math

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

def bollinger_band_width(df, length=20, std=2):
    upper, mid, lower = bollinger_bands(df, length=length, std=std)
    width = ((upper - lower) / mid.where(mid != 0)) * 100.0
    return width.fillna(0.0)

def rsi(series, length=14):
    """
    Wilder's RSI on CLOSE prices.
    Matches TradingView/Binance default when computed on closed candles.
    """
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1 / float(length), adjust=False).mean()
    roll_down = down.ewm(alpha=1 / float(length), adjust=False).mean()
    rs = roll_up / roll_down
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def ppo(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    ppo_line = ((ema_fast - ema_slow) / ema_slow.where(ema_slow != 0)) * 100.0
    signal_line = ppo_line.ewm(span=signal, adjust=False).mean()
    hist = ppo_line - signal_line
    return ppo_line.fillna(0.0), signal_line.fillna(0.0), hist.fillna(0.0)

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

def natr(df, length=14):
    atr_series = atr(df, length=length)
    close = df['close']
    return ((atr_series / close.where(close != 0)) * 100.0).fillna(0.0)

def choppiness_index(df, length=14):
    window = max(2, int(length or 14))
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
    tr_sum = true_range.rolling(window, min_periods=window).sum()
    high_low_range = high.rolling(window, min_periods=window).max() - low.rolling(window, min_periods=window).min()
    ratio = tr_sum / high_low_range.where(high_low_range != 0)
    chop = 100.0 * ratio.apply(lambda value: math.log10(value) if value and value > 0 else float("nan"))
    return (chop / math.log10(window)).fillna(0.0)

def keltner_channels(df, length=20, atr_length=10, multiplier=2.0):
    window = max(1, int(length or 20))
    atr_window = max(1, int(atr_length or 10))
    mult = float(multiplier or 2.0)
    middle = ema(df['close'], window)
    range_series = atr(df, length=atr_window)
    upper = middle + (range_series * mult)
    lower = middle - (range_series * mult)
    return upper, middle, lower

def ichimoku_cloud(df, conversion_length=9, base_length=26, span_b_length=52, displacement=26):
    high = df['high']
    low = df['low']
    close = df['close']
    conversion_window = max(1, int(conversion_length or 9))
    base_window = max(1, int(base_length or 26))
    span_b_window = max(1, int(span_b_length or 52))
    offset = max(0, int(displacement or 26))

    conversion_line = (
        high.rolling(conversion_window).max() + low.rolling(conversion_window).min()
    ) / 2.0
    base_line = (high.rolling(base_window).max() + low.rolling(base_window).min()) / 2.0
    leading_span_a = ((conversion_line + base_line) / 2.0).shift(offset)
    leading_span_b = (
        (high.rolling(span_b_window).max() + low.rolling(span_b_window).min()) / 2.0
    ).shift(offset)
    lagging_span = close.shift(-offset) if offset else close
    return conversion_line, base_line, leading_span_a, leading_span_b, lagging_span

def vwap(df, length=20):
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    typical_price = (high + low + close) / 3.0
    weighted_price = typical_price * volume
    window = max(1, int(length or 20))
    volume_sum = volume.rolling(window, min_periods=1).sum()
    weighted_sum = weighted_price.rolling(window, min_periods=1).sum()
    return weighted_sum / volume_sum.where(volume_sum != 0)

def relative_volume(df, length=20):
    volume = df['volume']
    window = max(1, int(length or 20))
    average_volume = volume.rolling(window, min_periods=1).mean()
    return (volume / average_volume.where(average_volume != 0)).fillna(0.0)

def mfi(df, length=14):
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    typical_price = (high + low + close) / 3.0
    raw_money_flow = typical_price * volume
    direction = typical_price.diff()
    positive_flow = raw_money_flow.where(direction > 0, 0.0)
    negative_flow = raw_money_flow.where(direction < 0, 0.0)
    window = max(1, int(length or 14))
    positive_sum = positive_flow.rolling(window, min_periods=1).sum()
    negative_sum = negative_flow.rolling(window, min_periods=1).sum()
    money_ratio = positive_sum / negative_sum.where(negative_sum != 0)
    result = 100 - (100 / (1 + money_ratio))
    result = result.where(negative_sum != 0, 100.0)
    result = result.where(positive_sum != 0, 0.0)
    result = result.where((positive_sum != 0) | (negative_sum != 0), 50.0)
    return result.fillna(50.0)

def obv(df):
    close = df['close']
    volume = df['volume']
    direction = close.diff()
    signed_volume = pd.Series(0.0, index=df.index)
    signed_volume = signed_volume.mask(direction > 0, volume)
    signed_volume = signed_volume.mask(direction < 0, -volume)
    return signed_volume.fillna(0.0).cumsum()

def chaikin_money_flow(df, length=20):
    high = df['high']
    low = df['low']
    close = df['close']
    volume = df['volume']
    price_range = high - low
    money_flow_multiplier = ((close - low) - (high - close)) / price_range.where(price_range != 0)
    money_flow_volume = money_flow_multiplier.fillna(0.0) * volume
    window = max(1, int(length or 20))
    volume_sum = volume.rolling(window, min_periods=1).sum()
    money_flow_sum = money_flow_volume.rolling(window, min_periods=1).sum()
    return (money_flow_sum / volume_sum.where(volume_sum != 0)).fillna(0.0)

def cci(df, length=20, constant=0.015):
    high = df['high']
    low = df['low']
    close = df['close']
    typical_price = (high + low + close) / 3.0
    window = max(1, int(length or 20))
    factor = float(constant or 0.015)
    average = typical_price.rolling(window, min_periods=1).mean()
    mean_deviation = typical_price.rolling(window, min_periods=1).apply(
        lambda values: abs(values - values.mean()).mean(),
        raw=True,
    )
    denominator = factor * mean_deviation.where(mean_deviation != 0)
    return ((typical_price - average) / denominator).fillna(0.0)

def roc(series, length=12):
    window = max(1, int(length or 12))
    prior = series.shift(window)
    return (((series - prior) / prior.where(prior != 0)) * 100.0).fillna(0.0)

def trix(series, length=15):
    window = max(1, int(length or 15))
    ema_one = ema(series, window)
    ema_two = ema(ema_one, window)
    ema_three = ema(ema_two, window)
    return (ema_three.pct_change() * 100.0).fillna(0.0)

def awesome_oscillator(df, fast=5, slow=34):
    median_price = (df['high'] + df['low']) / 2.0
    fast_window = max(1, int(fast or 5))
    slow_window = max(1, int(slow or 34))
    fast_sma = median_price.rolling(fast_window, min_periods=1).mean()
    slow_sma = median_price.rolling(slow_window, min_periods=1).mean()
    return (fast_sma - slow_sma).fillna(0.0)

def kst(series, roc1=10, roc2=15, roc3=20, roc4=30, sma1=10, sma2=10, sma3=10, sma4=15, signal=9):
    roc_1 = roc(series, length=roc1).rolling(max(1, int(sma1 or 10)), min_periods=1).mean()
    roc_2 = roc(series, length=roc2).rolling(max(1, int(sma2 or 10)), min_periods=1).mean()
    roc_3 = roc(series, length=roc3).rolling(max(1, int(sma3 or 10)), min_periods=1).mean()
    roc_4 = roc(series, length=roc4).rolling(max(1, int(sma4 or 15)), min_periods=1).mean()
    kst_line = roc_1 + (2.0 * roc_2) + (3.0 * roc_3) + (4.0 * roc_4)
    signal_line = kst_line.rolling(max(1, int(signal or 9)), min_periods=1).mean()
    spread = kst_line - signal_line
    return kst_line.fillna(0.0), signal_line.fillna(0.0), spread.fillna(0.0)

def aroon(df, length=25):
    high = df['high']
    low = df['low']
    window = max(1, int(length or 25))

    def _latest_extreme_position(values, *, find_high: bool):
        if len(values) <= 1:
            return 100.0
        reversed_values = values[::-1]
        reverse_index = reversed_values.argmax() if find_high else reversed_values.argmin()
        index = len(values) - 1 - int(reverse_index)
        return 100.0 * float(index) / float(len(values) - 1)

    up = high.rolling(window, min_periods=1).apply(
        lambda values: _latest_extreme_position(values, find_high=True),
        raw=True,
    )
    down = low.rolling(window, min_periods=1).apply(
        lambda values: _latest_extreme_position(values, find_high=False),
        raw=True,
    )
    oscillator = up - down
    return up.fillna(0.0), down.fillna(0.0), oscillator.fillna(0.0)

def dmi(df, length=14):
    high = df['high']
    low = df['low']

    up_move = high.diff()
    down_move = (-low.diff())

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0).fillna(0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0).fillna(0.0)

    atr_series = atr(df, length)
    plus_smoothed = plus_dm.ewm(alpha=1/float(length), adjust=False).mean()
    minus_smoothed = minus_dm.ewm(alpha=1/float(length), adjust=False).mean()

    atr_nonzero = atr_series.where(atr_series != 0)
    plus_di = (100.0 * (plus_smoothed / atr_nonzero)).fillna(0.0)
    minus_di = (100.0 * (minus_smoothed / atr_nonzero)).fillna(0.0)

    di_sum = plus_di + minus_di
    dx = ((plus_di - minus_di).abs() / di_sum.where(di_sum != 0)) * 100.0
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

    def _rolling_sum(series, length):
        return series.rolling(length, min_periods=1).sum()

    tr_short = _rolling_sum(tr, short)
    tr_medium = _rolling_sum(tr, medium)
    tr_long = _rolling_sum(tr, long)

    avg_short = _rolling_sum(bp, short) / tr_short.where(tr_short != 0)
    avg_medium = _rolling_sum(bp, medium) / tr_medium.where(tr_medium != 0)
    avg_long = _rolling_sum(bp, long) / tr_long.where(tr_long != 0)

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
    price_range = highest_high - lowest_low
    k = 100 * (df['close'] - lowest_low) / price_range.where(price_range != 0)
    k = k.rolling(smooth_k, min_periods=1).mean()
    d = k.rolling(smooth_d, min_periods=1).mean()
    return k.fillna(0.0), d.fillna(0.0)
