from __future__ import annotations

from reversal_lib.models import Candle
from reversal_lib.patterns_layer.bullish import body_bottom, body_top


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_signal_score(pattern_strength: str | None, confirm_volume: float, avg_volume_20: float, market_cap: float | None, avg_dollar_volume_20: float) -> tuple[float, str]:
    strength_points = {'strong': 40.0, 'medium': 28.0, 'standard': 20.0}.get(pattern_strength or 'standard', 20.0)
    volume_ratio = (confirm_volume / avg_volume_20) if avg_volume_20 > 0 else 1.0
    if volume_ratio >= 2.0:
        volume_points = 25.0
    elif volume_ratio >= 1.5:
        volume_points = 20.0
    elif volume_ratio >= 1.1:
        volume_points = 14.0
    elif volume_ratio >= 1.0:
        volume_points = 10.0
    else:
        volume_points = 4.0

    if market_cap is None:
        market_cap_points = 6.0
    elif market_cap >= 200_000_000_000:
        market_cap_points = 18.0
    elif market_cap >= 10_000_000_000:
        market_cap_points = 14.0
    elif market_cap >= 2_000_000_000:
        market_cap_points = 10.0
    else:
        market_cap_points = 6.0

    if avg_dollar_volume_20 >= 500_000_000:
        liquidity_points = 17.0
    elif avg_dollar_volume_20 >= 100_000_000:
        liquidity_points = 13.0
    elif avg_dollar_volume_20 >= 25_000_000:
        liquidity_points = 9.0
    else:
        liquidity_points = 5.0

    score = clamp_score(strength_points + volume_points + market_cap_points + liquidity_points)
    detail = f'strength={strength_points:.0f}, volume={volume_points:.0f}, mcap={market_cap_points:.0f}, liquidity={liquidity_points:.0f}'
    return score, detail


def pattern_strength_label(pattern: str, side: str) -> str:
    strong = {
        'Bullish Engulfing / 看涨吞没',
        'Bearish Engulfing / 看跌吞没',
        'Morning Star / 启明星',
        'Evening Star / 黄昏星',
        'Dark Cloud Cover / 乌云盖顶',
        'Piercing Pattern / 刺透形态',
    }
    medium = {
        'Hammer / 锤头线',
        'Inverted Hammer / 倒锤头线',
        'Shooting Star / 流星线',
        'Hanging Man / 上吊线',
        'Bullish Harami / 看涨孕线',
        'Bearish Harami / 看跌孕线',
    }
    if pattern in strong:
        return 'strong'
    if pattern in medium:
        return 'medium'
    return 'standard'


def bullish_confirmation_reason(pattern: str) -> str:
    mapping = {
        'Hammer / 锤头线': '确认日收盘站上候选实体上沿',
        'Inverted Hammer / 倒锤头线': '确认日收盘站上候选实体上沿',
        'Bullish Engulfing / 看涨吞没': '确认日收盘突破候选K线高点',
        'Bullish Harami / 看涨孕线': '确认日收盘突破候选K线高点',
        'Piercing Pattern / 刺透形态': '确认日继续上破候选高点与前阴线关键位',
        'Morning Star / 启明星': '确认日继续强化三K线底部反转',
    }
    return mapping.get(pattern, '确认日满足看涨确认条件')


def bearish_confirmation_reason(pattern: str) -> str:
    mapping = {
        'Shooting Star / 流星线': '确认日收盘跌破候选实体下沿',
        'Hanging Man / 上吊线': '确认日收盘跌破候选实体下沿',
        'Bearish Engulfing / 看跌吞没': '确认日收盘跌破候选K线低点',
        'Bearish Harami / 看跌孕线': '确认日收盘跌破候选K线低点',
        'Dark Cloud Cover / 乌云盖顶': '确认日继续下破候选低点并强化顶部反转',
        'Evening Star / 黄昏星': '确认日继续强化三K线顶部反转',
    }
    return mapping.get(pattern, '确认日满足看跌确认条件')


def bullish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {'Hammer / 锤头线', 'Inverted Hammer / 倒锤头线'}:
        return confirm.close > body_top(candidate)
    if pattern in {'Bullish Engulfing / 看涨吞没', 'Bullish Harami / 看涨孕线'}:
        return confirm.close > candidate.high
    if pattern == 'Piercing Pattern / 刺透形态':
        prev_candle = candles[idx - 1]
        return confirm.close > max(candidate.high, body_top(prev_candle))
    if pattern == 'Morning Star / 启明星':
        first = candles[idx - 2]
        return confirm.close > max(candidate.high, body_top(first))
    return confirm.close > body_top(candidate)


def bearish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {'Shooting Star / 流星线', 'Hanging Man / 上吊线'}:
        return confirm.close < body_bottom(candidate)
    if pattern in {'Bearish Engulfing / 看跌吞没', 'Bearish Harami / 看跌孕线'}:
        return confirm.close < candidate.low
    if pattern == 'Dark Cloud Cover / 乌云盖顶':
        prev_candle = candles[idx - 1]
        return confirm.close < min(candidate.low, body_bottom(prev_candle))
    if pattern == 'Evening Star / 黄昏星':
        first = candles[idx - 2]
        return confirm.close < min(candidate.low, body_bottom(first))
    return confirm.close < body_bottom(candidate)
