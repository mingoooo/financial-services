from __future__ import annotations

import time

from .models import Candle, Signal
from .patterns import (
    bullish_confirmation_reason,
    bearish_confirmation_reason,
    compute_signal_score,
    detect_bullish_pattern,
    detect_bearish_pattern,
    detect_support_resistance_levels,
    pattern_strength_label,
)
from .strategy_filters import macd_context as _macd_context, rsi_value as _rsi_value, sma as _sma, sma_cross_context as _sma_cross_context


def _is_near_level(price: float, level: float | None, tolerance_ratio: float = 0.02) -> bool:
    if level is None or price <= 0:
        return False
    return abs(price - level) / price <= tolerance_ratio


def _location_context(confirm_close: float, nearest_support: float | None, nearest_resistance: float | None, tolerance_ratio: float = 0.02) -> str:
    near_support = _is_near_level(confirm_close, nearest_support, tolerance_ratio)
    near_resistance = _is_near_level(confirm_close, nearest_resistance, tolerance_ratio)
    if near_support and not near_resistance:
        return 'near_support'
    if near_resistance and not near_support:
        return 'near_resistance'
    if near_support and near_resistance:
        return 'near_both'
    return 'neutral'


def _trend_context(candles: list[Candle], idx: int) -> str | None:
    closes = [c.close for c in candles[:idx + 1]]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    if sma20 is None or sma50 is None:
        return None
    price = closes[-1]
    if price > sma20 > sma50:
        return 'bullish'
    if price < sma20 < sma50:
        return 'bearish'
    return 'neutral'


def generate_signals(
    candles: list[Candle],
    symbol: str,
    side: str = 'both',
    require_confirm_volume: bool = True,
    market_cap: float | None = None,
    min_r_multiple: float = 2.0,
    require_trend_alignment: bool = False,
    require_location_alignment: bool = False,
    location_tolerance_ratio: float = 0.02,
    allowed_patterns: set[str] | None = None,
    require_fresh_sma_cross_up: bool = False,
    sma_cross_mode: str = 'either',
    require_macd_bullish: bool = False,
    require_rsi_above: float | None = None,
    require_above_sma200: bool = False,
) -> list[Signal]:
    signals: list[Signal] = []
    if len(candles) < 25:
        return signals

    for idx in range(20, len(candles) - 2):
        candidate = candles[idx]
        confirm = candles[idx + 1]
        entry = candles[idx + 2]
        avg_vol20 = sum(c.volume for c in candles[idx - 19:idx + 1]) / 20
        avg_dollar_volume_20 = sum(c.close * c.volume for c in candles[idx - 19:idx + 1]) / 20

        supports, resistances = detect_support_resistance_levels(candles[:idx + 2], lookback=50)
        nearest_support = max(supports) if supports else None
        nearest_resistance = min(resistances) if resistances else None
        trend = _trend_context(candles, idx + 1)
        location = _location_context(confirm.close, nearest_support, nearest_resistance, location_tolerance_ratio)
        sma_cross = _sma_cross_context(candles, idx + 1)
        macd_context = _macd_context(candles, idx + 1)
        rsi_value = _rsi_value(candles, idx + 1)
        sma200 = _sma([c.close for c in candles[:idx + 2]], 200)
        above_sma200 = sma200 is not None and confirm.close > sma200
        sma_cross_ok = (
            not require_fresh_sma_cross_up
            or (sma_cross_mode == 'either' and sma_cross != 'none')
            or (sma_cross_mode == '20' and sma_cross in {'cross_20', 'cross_20_50'})
            or (sma_cross_mode == '50' and sma_cross in {'cross_50', 'cross_20_50'})
        )

        if side in {'both', 'bullish'}:
            pattern, stop_anchor = detect_bullish_pattern(candles, idx)
            if pattern and stop_anchor is not None:
                if allowed_patterns is not None and pattern not in allowed_patterns:
                    continue
                confirmed = confirm.close > max(candidate.open, candidate.close)
                if require_confirm_volume:
                    confirmed = confirmed and confirm.volume >= avg_vol20
                if confirmed and (not require_trend_alignment or trend == 'bullish') and (not require_location_alignment or location in {'near_support', 'near_both'}) and sma_cross_ok and (not require_macd_bullish or macd_context in {'bullish', 'cross_up'}) and (require_rsi_above is None or (rsi_value is not None and rsi_value > require_rsi_above)) and (not require_above_sma200 or above_sma200):
                    risk = entry.open - stop_anchor
                    structural_target = min(resistances) if resistances else None
                    structural_reward = (structural_target - confirm.close) if structural_target is not None else None
                    structural_rr = (structural_reward / risk) if (structural_reward is not None and risk > 0) else None
                    if risk > 0 and (structural_rr is not None and structural_rr >= min_r_multiple):
                        strength = pattern_strength_label(pattern, 'bullish')
                        score, score_detail = compute_signal_score(strength, confirm.volume, avg_vol20, market_cap, avg_dollar_volume_20)
                        signals.append(Signal(
                            symbol=symbol,
                            side='bullish',
                            pattern=pattern,
                            candidate_index=idx,
                            confirm_index=idx + 1,
                            candidate_date=time.strftime('%Y-%m-%d', time.gmtime(candidate.ts)),
                            confirm_date=time.strftime('%Y-%m-%d', time.gmtime(confirm.ts)),
                            confirm_close=round(confirm.close, 2),
                            stop_loss=round(stop_anchor, 2),
                            first_target=round(entry.open + risk, 2),
                            second_target=round(entry.open + risk * 2, 2),
                            confirm_volume=round(confirm.volume, 0),
                            avg_volume_20=round(avg_vol20, 0),
                            avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                            market_cap=market_cap,
                            pattern_strength=strength,
                            confirmation_reason=bullish_confirmation_reason(pattern),
                            score=score,
                            score_detail=score_detail,
                            structural_r_multiple=round(structural_rr, 4) if structural_rr is not None else None,
                            trend_context=trend,
                            location_context=location,
                            sma_cross_context=sma_cross,
                            macd_context=macd_context,
                            rsi_value=round(rsi_value, 4) if rsi_value is not None else None,
                            above_sma200=above_sma200,
                        ))

        if side in {'both', 'bearish'}:
            pattern, stop_anchor = detect_bearish_pattern(candles, idx)
            if pattern and stop_anchor is not None:
                if allowed_patterns is not None and pattern not in allowed_patterns:
                    continue
                confirmed = confirm.close < min(candidate.open, candidate.close)
                if require_confirm_volume:
                    confirmed = confirmed and confirm.volume >= avg_vol20
                if confirmed and (not require_trend_alignment or trend == 'bearish') and (not require_location_alignment or location in {'near_resistance', 'near_both'}):
                    risk = stop_anchor - entry.open
                    structural_target = max(supports) if supports else None
                    structural_reward = (confirm.close - structural_target) if structural_target is not None else None
                    structural_rr = (structural_reward / risk) if (structural_reward is not None and risk > 0) else None
                    if risk > 0 and (structural_rr is not None and structural_rr >= min_r_multiple):
                        strength = pattern_strength_label(pattern, 'bearish')
                        score, score_detail = compute_signal_score(strength, confirm.volume, avg_vol20, market_cap, avg_dollar_volume_20)
                        signals.append(Signal(
                            symbol=symbol,
                            side='bearish',
                            pattern=pattern,
                            candidate_index=idx,
                            confirm_index=idx + 1,
                            candidate_date=time.strftime('%Y-%m-%d', time.gmtime(candidate.ts)),
                            confirm_date=time.strftime('%Y-%m-%d', time.gmtime(confirm.ts)),
                            confirm_close=round(confirm.close, 2),
                            stop_loss=round(stop_anchor, 2),
                            first_target=round(entry.open - risk, 2),
                            second_target=round(entry.open - risk * 2, 2),
                            confirm_volume=round(confirm.volume, 0),
                            avg_volume_20=round(avg_vol20, 0),
                            avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                            market_cap=market_cap,
                            pattern_strength=strength,
                            confirmation_reason=bearish_confirmation_reason(pattern),
                            score=score,
                            score_detail=score_detail,
                            structural_r_multiple=round(structural_rr, 4) if structural_rr is not None else None,
                            trend_context=trend,
                            location_context=location,
                            sma_cross_context=sma_cross,
                            macd_context=macd_context,
                            rsi_value=round(rsi_value, 4) if rsi_value is not None else None,
                            above_sma200=above_sma200,
                        ))
    return signals
