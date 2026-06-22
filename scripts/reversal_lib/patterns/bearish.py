from __future__ import annotations

from reversal_lib.domain.models import PatternHit
from reversal_lib.models import Candle
from reversal_lib.patterns.bullish import body_bottom, body_top, is_bullish, is_hammer, is_long_body, is_small_body, real_body


def is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def is_shooting_star(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    upper_shadow = candle.high - body_top(candle)
    lower_shadow = body_bottom(candle) - candle.low
    return upper_shadow >= real_body(candle) * 2 and lower_shadow <= max(real_body(candle) * 0.5, rng * 0.1)


def is_hanging_man(candle: Candle) -> bool:
    return is_hammer(candle)


def is_bearish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bullish(prev_candle)
        and is_bearish(candle)
        and body_top(candle) >= body_top(prev_candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_dark_cloud_cover(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bullish(first)
        and is_long_body(first)
        and is_bearish(second)
        and second.open > first.high - (first.high - first.low) * 0.25
        and second.close < midpoint
        and second.close > first.open
    )


def is_evening_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bullish(first)
        and is_long_body(first)
        and small_second
        and is_bearish(third)
        and third.close < midpoint
    )


def is_bearish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bullish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bearish(second)
    )


def has_prior_uptrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] > closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1]) >= 2


def detect_bearish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_shooting_star(candle):
        return 'Shooting Star / 流星线', candle.high
    if is_hanging_man(candle):
        return 'Hanging Man / 上吊线', candle.high
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bearish_engulfing(prev_candle, candle):
            return 'Bearish Engulfing / 看跌吞没', max(prev_candle.high, candle.high)
        if is_dark_cloud_cover(prev_candle, candle):
            return 'Dark Cloud Cover / 乌云盖顶', max(prev_candle.high, candle.high)
        if is_bearish_harami(prev_candle, candle):
            return 'Bearish Harami / 看跌孕线', max(prev_candle.high, candle.high)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_evening_star(first, second, third):
            return 'Evening Star / 黄昏星', max(first.high, second.high, third.high)
    return None, None


def detect_bearish_pattern_hit(candles: list[Candle], idx: int, *, symbol: str, candidate_date: str) -> PatternHit | None:
    pattern, _ = detect_bearish_pattern(candles, idx)
    if pattern is None:
        return None
    return PatternHit(symbol=symbol, pattern=pattern, candidate_index=idx, candidate_date=candidate_date)
