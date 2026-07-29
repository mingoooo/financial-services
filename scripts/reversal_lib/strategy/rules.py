from __future__ import annotations

from reversal_lib.domain.models import IndicatorContext, SignalCandidate
from reversal_lib.indicators.context import ComputedIndicatorContext
from reversal_lib.strategy.spec import StrategySpec


def _structural_r_multiple(signal: SignalCandidate) -> float | None:
    entry_price = signal.planned_entry_price
    if signal.side == 'bullish':
        risk = entry_price - signal.stop_loss
        if risk <= 0 or signal.first_target is None:
            return None
        return (signal.first_target - entry_price) / risk

    risk = signal.stop_loss - entry_price
    if risk <= 0 or signal.first_target is None:
        return None
    return (entry_price - signal.first_target) / risk


def evaluate_signal(
    signal: SignalCandidate,
    context: ComputedIndicatorContext,
    spec: StrategySpec,
) -> tuple[bool, SignalCandidate]:
    indicator_context = context.indicator_context
    allowed_patterns = spec.indicator_config.get('allowed_patterns')
    require_trend_alignment = spec.indicator_config.get('require_trend_alignment', False)
    require_location_alignment = spec.indicator_config.get('require_location_alignment', False)
    min_candlestick_quality = spec.indicator_config.get('min_candlestick_quality')

    if allowed_patterns is not None and signal.hit.pattern not in set(allowed_patterns):
        return False, signal
    if min_candlestick_quality is not None and (signal.candlestick_quality or 0.0) < float(min_candlestick_quality):
        return False, signal

    trend_ok = (
        not require_trend_alignment
        or (signal.side == 'bullish' and indicator_context.trend_context == 'bullish')
        or (signal.side == 'bearish' and indicator_context.trend_context == 'bearish')
    )
    location_ok = (
        not require_location_alignment
        or (signal.side == 'bullish' and indicator_context.location_context in {'near_support', 'near_both'})
        or (signal.side == 'bearish' and indicator_context.location_context in {'near_resistance', 'near_both'})
    )
    cross = indicator_context.sma_cross_context
    sma_cross_ok = (
        not spec.require_fresh_sma_cross_up
        or (spec.sma_cross_mode == 'either' and cross != 'none')
        or (spec.sma_cross_mode == '20' and cross in {'cross_20', 'cross_20_50'})
        or (spec.sma_cross_mode == '50' and cross in {'cross_50', 'cross_20_50'})
    )
    macd_ok = (not spec.require_macd_bullish) or indicator_context.macd_context in {'bullish', 'cross_up'}
    rsi_ok = (spec.require_rsi_above is None) or (
        indicator_context.rsi_value is not None and indicator_context.rsi_value > spec.require_rsi_above
    )
    sma200_ok = (not spec.require_above_sma200) or bool(indicator_context.above_sma200)
    uptrend_ok = (not spec.require_standard_uptrend) or indicator_context.trend_context == 'bullish'
    confirm_volume_ok = (not spec.require_confirm_volume) or context.confirm_volume_ok

    structural_r_multiple = _structural_r_multiple(signal)
    structural_r_ok = structural_r_multiple is not None and structural_r_multiple >= spec.min_r_multiple

    accepted = all([
        trend_ok,
        location_ok,
        sma_cross_ok,
        macd_ok,
        rsi_ok,
        sma200_ok,
        uptrend_ok,
        confirm_volume_ok,
        structural_r_ok,
    ])
    return accepted, SignalCandidate(**{
        **signal.__dict__,
        'indicator_context': IndicatorContext(**indicator_context.__dict__),
        'structural_r_multiple': round(structural_r_multiple, 4) if structural_r_multiple is not None else None,
    })
