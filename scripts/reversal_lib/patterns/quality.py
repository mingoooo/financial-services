from __future__ import annotations

from reversal_lib.models import Candle


def _body_size(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def _range_size(candle: Candle) -> float:
    return max(candle.high - candle.low, 1e-9)


def _upper_shadow(candle: Candle) -> float:
    return candle.high - max(candle.open, candle.close)


def _lower_shadow(candle: Candle) -> float:
    return min(candle.open, candle.close) - candle.low


def _bullish_close_strength(confirm: Candle) -> float:
    return (confirm.close - confirm.low) / _range_size(confirm)


def _bearish_close_strength(confirm: Candle) -> float:
    return (confirm.high - confirm.close) / _range_size(confirm)


def evaluate_candlestick_quality(pattern: str, side: str, candles: list[Candle], idx: int, confirm: Candle) -> tuple[float, str]:
    candidate = candles[idx]
    body_ratio = _body_size(candidate) / _range_size(candidate)
    lower_ratio = _lower_shadow(candidate) / _range_size(candidate)
    upper_ratio = _upper_shadow(candidate) / _range_size(candidate)
    close_strength = _bullish_close_strength(confirm) if side == 'bullish' else _bearish_close_strength(confirm)

    score = 0.45
    notes: list[str] = []

    if pattern == 'Hammer / 锤头线':
        if lower_ratio >= 0.5:
            score += 0.2
            notes.append('long_lower_shadow')
        if upper_ratio <= 0.15:
            score += 0.1
            notes.append('tight_upper_shadow')
        if body_ratio <= 0.35:
            score += 0.1
            notes.append('small_real_body')
    elif pattern == 'Inverted Hammer / 倒锤头线':
        if upper_ratio >= 0.5:
            score += 0.2
            notes.append('long_upper_shadow')
        if lower_ratio <= 0.15:
            score += 0.1
            notes.append('tight_lower_shadow')
        if body_ratio <= 0.35:
            score += 0.1
            notes.append('small_real_body')
    elif pattern == 'Bullish Engulfing / 看涨吞没':
        prev = candles[idx - 1]
        engulf_ratio = _body_size(candidate) / max(_body_size(prev), 1e-9)
        if engulf_ratio >= 1.2:
            score += 0.2
            notes.append('wide_engulfing_body')
        if candidate.close > candidate.open:
            score += 0.1
            notes.append('strong_bullish_body')
        if body_ratio >= 0.55:
            score += 0.1
            notes.append('expanded_real_body')
    elif pattern == 'Piercing Pattern / 刺透形态':
        prev = candles[idx - 1]
        midpoint = (prev.open + prev.close) / 2
        if candidate.close >= midpoint:
            score += 0.2
            notes.append('pierced_above_midpoint')
        if body_ratio >= 0.45:
            score += 0.1
            notes.append('meaningful_real_body')
    elif pattern == 'Morning Star / 启明星':
        if idx >= 2:
            first = candles[idx - 2]
            recovery = (candidate.close - candidate.open) / max(abs(first.open - first.close), 1e-9)
            if recovery >= 0.5:
                score += 0.2
                notes.append('third_candle_recovery')
        if candidate.close > candidate.open:
            score += 0.1
            notes.append('bullish_third_candle')
    elif pattern == 'Shooting Star / 流星线':
        if upper_ratio >= 0.5:
            score += 0.2
            notes.append('long_upper_shadow')
        if lower_ratio <= 0.15:
            score += 0.1
            notes.append('tight_lower_shadow')
        if body_ratio <= 0.35:
            score += 0.1
            notes.append('small_real_body')
    elif pattern == 'Hanging Man / 上吊线':
        if lower_ratio >= 0.5:
            score += 0.2
            notes.append('long_lower_shadow')
        if upper_ratio <= 0.15:
            score += 0.1
            notes.append('tight_upper_shadow')
        if body_ratio <= 0.35:
            score += 0.1
            notes.append('small_real_body')
    elif pattern == 'Bearish Engulfing / 看跌吞没':
        prev = candles[idx - 1]
        engulf_ratio = _body_size(candidate) / max(_body_size(prev), 1e-9)
        if engulf_ratio >= 1.2:
            score += 0.2
            notes.append('wide_engulfing_body')
        if candidate.close < candidate.open:
            score += 0.1
            notes.append('strong_bearish_body')
        if body_ratio >= 0.55:
            score += 0.1
            notes.append('expanded_real_body')
    elif pattern == 'Dark Cloud Cover / 乌云盖顶':
        prev = candles[idx - 1]
        midpoint = (prev.open + prev.close) / 2
        if candidate.close <= midpoint:
            score += 0.2
            notes.append('closed_below_midpoint')
        if body_ratio >= 0.45:
            score += 0.1
            notes.append('meaningful_real_body')
    elif pattern == 'Evening Star / 黄昏星':
        if idx >= 2:
            first = candles[idx - 2]
            rejection = (candidate.open - candidate.close) / max(abs(first.close - first.open), 1e-9)
            if rejection >= 0.5:
                score += 0.2
                notes.append('third_candle_rejection')
        if candidate.close < candidate.open:
            score += 0.1
            notes.append('bearish_third_candle')

    if close_strength >= 0.7:
        score += 0.15
        notes.append('strong_confirm_close')
    elif close_strength >= 0.55:
        score += 0.08
        notes.append('ok_confirm_close')
    else:
        notes.append('weak_confirm_close')

    return max(0.0, min(score, 1.0)), ','.join(notes)


def confirmation_close_strength_ok(side: str, confirm: Candle, min_strength: float = 0.55) -> bool:
    strength = _bullish_close_strength(confirm) if side == 'bullish' else _bearish_close_strength(confirm)
    return strength >= min_strength
