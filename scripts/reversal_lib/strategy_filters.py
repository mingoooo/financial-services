from __future__ import annotations

from .models import Candle, Signal


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    multiplier = 2 / (period + 1)
    ema = None
    for value in values:
        if ema is None:
            ema = value
        else:
            ema = (value - ema) * multiplier + ema
        result.append(ema)
    return result


def rolling_sma_series(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    running = 0.0
    for idx, value in enumerate(values):
        running += value
        if idx >= period:
            running -= values[idx - period]
        if idx + 1 < period:
            result.append(None)
        else:
            result.append(running / period)
    return result


def rolling_mean_series(values: list[float], period: int) -> list[float | None]:
    return rolling_sma_series(values, period)


def trend_context_series(closes: list[float]) -> list[str | None]:
    sma20 = rolling_sma_series(closes, 20)
    sma50 = rolling_sma_series(closes, 50)
    result: list[str | None] = []
    for price, avg20, avg50 in zip(closes, sma20, sma50):
        if avg20 is None or avg50 is None:
            result.append(None)
        elif price > avg20 > avg50:
            result.append('bullish')
        elif price < avg20 < avg50:
            result.append('bearish')
        else:
            result.append('neutral')
    return result


def rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = []
    for end in range(len(values)):
        if end + 1 < period + 1:
            result.append(None)
            continue
        gains: list[float] = []
        losses: list[float] = []
        start = 0
        for idx in range(1, end + 1):
            delta = values[idx] - values[idx - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            result.append(100.0)
            continue
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))
    return result


def macd_context_series(values: list[float]) -> list[str]:
    if not values:
        return []
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    macd = [((fast or 0.0) - (slow or 0.0)) for fast, slow in zip(ema12, ema26)]
    signal = ema_series(macd, 9)
    result: list[str] = []
    for idx in range(len(values)):
        if idx + 1 < 35:
            result.append('none')
            continue
        curr_macd, curr_signal = macd[idx], signal[idx]
        prev_macd, prev_signal = macd[idx - 1], signal[idx - 1]
        if curr_signal is None or prev_signal is None:
            result.append('none')
        elif prev_macd <= prev_signal and curr_macd > curr_signal:
            result.append('cross_up')
        elif curr_macd > curr_signal:
            result.append('bullish')
        else:
            result.append('bearish')
    return result


def sma_cross_context_series(closes: list[float]) -> list[str]:
    sma20 = rolling_sma_series(closes, 20)
    sma50 = rolling_sma_series(closes, 50)
    result: list[str] = []
    for idx in range(len(closes)):
        cross20 = False
        cross50 = False
        if idx >= 1 and sma20[idx - 1] is not None and sma20[idx] is not None:
            cross20 = closes[idx - 1] <= sma20[idx - 1] and closes[idx] > sma20[idx]
        if idx >= 1 and sma50[idx - 1] is not None and sma50[idx] is not None:
            cross50 = closes[idx - 1] <= sma50[idx - 1] and closes[idx] > sma50[idx]
        if cross20 and cross50:
            result.append('cross_20_50')
        elif cross20:
            result.append('cross_20')
        elif cross50:
            result.append('cross_50')
        else:
            result.append('none')
    return result


def macd_context(candles: list[Candle], idx: int) -> str:
    closes = [c.close for c in candles[:idx + 2]]
    if len(closes) < 35:
        return 'none'
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd = [((a or 0.0) - (b or 0.0)) for a, b in zip(ema12, ema26)]
    signal = ema_series(macd, 9)
    curr_macd, curr_signal = macd[-1], signal[-1]
    prev_macd, prev_signal = macd[-2], signal[-2]
    if curr_signal is None or prev_signal is None:
        return 'none'
    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return 'cross_up'
    if curr_macd > curr_signal:
        return 'bullish'
    return 'bearish'


def rsi_value(candles: list[Candle], idx: int, period: int = 14) -> float | None:
    closes = [c.close for c in candles[:idx + 2]]
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fresh_sma_cross_up(candles: list[Candle], idx: int, period: int) -> bool:
    closes = [c.close for c in candles[:idx + 2]]
    if len(closes) < period + 1:
        return False
    prev_sma = sma(closes[:-1], period)
    curr_sma = sma(closes, period)
    if prev_sma is None or curr_sma is None:
        return False
    prev_close = closes[-2]
    curr_close = closes[-1]
    return prev_close <= prev_sma and curr_close > curr_sma


def sma_cross_context(candles: list[Candle], idx: int) -> str:
    cross20 = fresh_sma_cross_up(candles, idx, 20)
    cross50 = fresh_sma_cross_up(candles, idx, 50)
    if cross20 and cross50:
        return 'cross_20_50'
    if cross20:
        return 'cross_20'
    if cross50:
        return 'cross_50'
    return 'none'


def filter_context(signal: Signal, candles: list[Candle]) -> dict:
    idx = signal.confirm_index
    cross = sma_cross_context(candles, idx)
    macd = macd_context(candles, idx)
    rsi = rsi_value(candles, idx)
    closes = [c.close for c in candles[:idx + 2]]
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)
    above_sma200 = sma200 is not None and signal.confirm_close > sma200
    standard_uptrend = (
        sma20 is not None
        and sma50 is not None
        and signal.confirm_close > sma20 > sma50
    )
    return {
        'sma_cross_context': cross,
        'macd_context': macd,
        'rsi_value': round(rsi, 4) if rsi is not None else None,
        'above_sma200': above_sma200,
        'standard_uptrend': standard_uptrend,
    }


def signal_passes_filters(
    signal: Signal,
    candles: list[Candle],
    require_fresh_sma_cross_up: bool = False,
    sma_cross_mode: str = 'either',
    require_standard_uptrend: bool = False,
    require_macd_bullish: bool = False,
    require_rsi_above: float | None = None,
    require_above_sma200: bool = False,
) -> tuple[bool, dict]:
    meta = filter_context(signal, candles)
    cross = meta['sma_cross_context']
    macd = meta['macd_context']
    rsi = meta['rsi_value']
    above_sma200 = meta['above_sma200']
    standard_uptrend = meta['standard_uptrend']

    sma_cross_ok = (
        not require_fresh_sma_cross_up
        or (sma_cross_mode == 'either' and cross != 'none')
        or (sma_cross_mode == '20' and cross in {'cross_20', 'cross_20_50'})
        or (sma_cross_mode == '50' and cross in {'cross_50', 'cross_20_50'})
    )
    macd_ok = (not require_macd_bullish) or macd in {'bullish', 'cross_up'}
    rsi_ok = (require_rsi_above is None) or (rsi is not None and rsi > require_rsi_above)
    sma200_ok = (not require_above_sma200) or above_sma200
    uptrend_ok = (not require_standard_uptrend) or standard_uptrend

    return sma_cross_ok and macd_ok and rsi_ok and sma200_ok and uptrend_ok, meta
