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
    sma200 = sma([c.close for c in candles[:idx + 2]], 200)
    above_sma200 = sma200 is not None and signal.confirm_close > sma200
    return {
        'sma_cross_context': cross,
        'macd_context': macd,
        'rsi_value': round(rsi, 4) if rsi is not None else None,
        'above_sma200': above_sma200,
    }


def signal_passes_filters(
    signal: Signal,
    candles: list[Candle],
    require_fresh_sma_cross_up: bool = False,
    sma_cross_mode: str = 'either',
    require_macd_bullish: bool = False,
    require_rsi_above: float | None = None,
    require_above_sma200: bool = False,
) -> tuple[bool, dict]:
    meta = filter_context(signal, candles)
    cross = meta['sma_cross_context']
    macd = meta['macd_context']
    rsi = meta['rsi_value']
    above_sma200 = meta['above_sma200']

    sma_cross_ok = (
        not require_fresh_sma_cross_up
        or (sma_cross_mode == 'either' and cross != 'none')
        or (sma_cross_mode == '20' and cross in {'cross_20', 'cross_20_50'})
        or (sma_cross_mode == '50' and cross in {'cross_50', 'cross_20_50'})
    )
    macd_ok = (not require_macd_bullish) or macd in {'bullish', 'cross_up'}
    rsi_ok = (require_rsi_above is None) or (rsi is not None and rsi > require_rsi_above)
    sma200_ok = (not require_above_sma200) or above_sma200

    return sma_cross_ok and macd_ok and rsi_ok and sma200_ok, meta
