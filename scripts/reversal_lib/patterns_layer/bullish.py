from __future__ import annotations

from reversal_lib.domain.models import PatternHit
from reversal_lib.models import Candle


def is_small_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    body = abs(candle.close - candle.open)
    return rng > 0 and body / rng <= 0.35


def real_body(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def body_top(candle: Candle) -> float:
    return max(candle.open, candle.close)


def body_bottom(candle: Candle) -> float:
    return min(candle.open, candle.close)


def is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def is_long_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng >= 0.55


def is_doji(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng <= 0.1


def is_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    top = max(candle.open, candle.close)
    bottom = min(candle.open, candle.close)
    lower_shadow = bottom - candle.low
    upper_shadow = candle.high - top
    body = top - bottom
    return lower_shadow >= body * 2 and upper_shadow <= body * 0.5 and top >= candle.low + rng * 0.6


def is_inverted_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    top = max(candle.open, candle.close)
    bottom = min(candle.open, candle.close)
    lower_shadow = bottom - candle.low
    upper_shadow = candle.high - top
    body = top - bottom
    return upper_shadow >= body * 2 and lower_shadow <= body * 0.5 and bottom <= candle.low + rng * 0.4


def is_bullish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bearish(prev_candle)
        and is_bullish(candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and body_top(candle) >= body_top(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_piercing_pattern(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bearish(first)
        and is_long_body(first)
        and is_bullish(second)
        and second.open < first.low + (first.high - first.low) * 0.25
        and second.close > midpoint
        and second.close < first.open
    )


def is_morning_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bearish(first)
        and is_long_body(first)
        and small_second
        and is_bullish(third)
        and third.close > midpoint
    )


def is_bullish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bearish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bullish(second)
    )


def has_prior_downtrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] < closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] < closes[i - 1]) >= 2


def detect_bullish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_hammer(candle):
        return 'Hammer / 锤头线', candle.low
    if is_inverted_hammer(candle):
        return 'Inverted Hammer / 倒锤头线', candle.low
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bullish_engulfing(prev_candle, candle):
            return 'Bullish Engulfing / 看涨吞没', min(prev_candle.low, candle.low)
        if is_piercing_pattern(prev_candle, candle):
            return 'Piercing Pattern / 刺透形态', min(prev_candle.low, candle.low)
        if is_bullish_harami(prev_candle, candle):
            return 'Bullish Harami / 看涨孕线', min(prev_candle.low, candle.low)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_morning_star(first, second, third):
            return 'Morning Star / 启明星', min(first.low, second.low, third.low)
    return None, None


def detect_bullish_pattern_hit(candles: list[Candle], idx: int, *, symbol: str, candidate_date: str) -> PatternHit | None:
    pattern, _ = detect_bullish_pattern(candles, idx)
    if pattern is None:
        return None
    return PatternHit(symbol=symbol, pattern=pattern, candidate_index=idx, candidate_date=candidate_date)
