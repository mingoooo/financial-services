from __future__ import annotations

import time

from .domain.models import PatternHit, SignalCandidate
from .indicators.context import build_indicator_context, prepare_indicator_context_inputs
from .models import Candle, Signal
from .patterns import (
    bearish_confirmation_reason,
    bullish_confirmation_reason,
    compute_signal_score,
    detect_bearish_pattern,
    detect_bullish_pattern,
    detect_support_resistance_levels_from_window,
    pattern_strength_label,
)
from .strategy.rules import evaluate_signal
from .strategy.spec import StrategySpec
from .strategy.trade_plan import build_trade_plan


def _to_legacy_signal(
    *,
    symbol: str,
    dates: list[str],
    candidate_index: int,
    signal_candidate: SignalCandidate,
    plan_entry_price: float,
    plan_stop_loss: float,
    first_target: float,
    second_target: float,
    pattern_strength: str,
    confirmation_reason: str,
    score: float,
    score_detail: str,
) -> Signal:
    context = signal_candidate.indicator_context
    return Signal(
        symbol=symbol,
        side=signal_candidate.side,
        pattern=signal_candidate.hit.pattern,
        candidate_index=candidate_index,
        confirm_index=candidate_index + 1,
        candidate_date=dates[candidate_index],
        confirm_date=dates[candidate_index + 1],
        confirm_close=round(signal_candidate.confirm_close, 2),
        planned_entry_price=round(signal_candidate.planned_entry_price if signal_candidate.entry_mode == 'confirm_close' else plan_entry_price, 2),
        entry_mode=signal_candidate.entry_mode,
        stop_loss=round(plan_stop_loss, 2),
        first_target=round(first_target, 2),
        second_target=round(second_target, 2),
        confirm_volume=round(signal_candidate.confirm_volume, 0),
        avg_volume_20=round(signal_candidate.avg_volume_20, 0),
        avg_dollar_volume_20=round(signal_candidate.avg_dollar_volume_20, 0),
        market_cap=signal_candidate.market_cap,
        pattern_strength=pattern_strength,
        confirmation_reason=confirmation_reason,
        score=score,
        score_detail=score_detail,
        structural_r_multiple=signal_candidate.structural_r_multiple,
        trend_context=context.trend_context if context else None,
        location_context=context.location_context if context else None,
        sma_cross_context=context.sma_cross_context if context else None,
        rsi_value=context.rsi_value if context else None,
        above_sma200=context.above_sma200 if context else None,
        macd_context=context.macd_context if context else None,
    )


def generate_signals(
    candles: list[Candle],
    symbol: str,
    side: str = 'both',
    require_confirm_volume: bool = True,
    confirm_volume_multiplier: float = 1.0,
    market_cap: float | None = None,
    min_r_multiple: float = 1.5,
    require_trend_alignment: bool = False,
    require_location_alignment: bool = False,
    location_tolerance_ratio: float = 0.02,
    allowed_patterns: set[str] | None = None,
    require_fresh_sma_cross_up: bool = False,
    sma_cross_mode: str = 'either',
    require_macd_bullish: bool = False,
    require_rsi_above: float | None = None,
    require_above_sma200: bool = False,
    entry_mode: str = 'next_open',
    stop_mode: str = 'pattern_anchor',
    target_mode: str = 'r_multiple',
) -> list[Signal]:
    signals: list[Signal] = []
    if len(candles) < 25:
        return signals

    spec = StrategySpec(
        side=side,
        min_r_multiple=min_r_multiple,
        require_confirm_volume=require_confirm_volume,
        confirm_volume_multiplier=confirm_volume_multiplier,
        require_fresh_sma_cross_up=require_fresh_sma_cross_up,
        sma_cross_mode=sma_cross_mode,
        require_standard_uptrend=require_trend_alignment,
        require_macd_bullish=require_macd_bullish,
        require_rsi_above=require_rsi_above,
        require_above_sma200=require_above_sma200,
        entry_mode=entry_mode,
        stop_mode=stop_mode,
        target_mode=target_mode,
        indicator_config={
            'require_trend_alignment': require_trend_alignment,
            'require_location_alignment': require_location_alignment,
            'location_tolerance_ratio': location_tolerance_ratio,
            'allowed_patterns': sorted(allowed_patterns) if allowed_patterns is not None else None,
        },
    )
    dates = [time.strftime('%Y-%m-%d', time.gmtime(c.ts)) for c in candles]
    context_inputs = prepare_indicator_context_inputs(candles)

    for idx in range(20, len(candles) - 2):
        candidate = candles[idx]
        confirm = candles[idx + 1]
        sr_window = candles[max(0, idx + 2 - 50):idx + 2]
        supports, resistances = detect_support_resistance_levels_from_window(sr_window)
        context = build_indicator_context(
            candles,
            idx,
            confirm.close,
            location_tolerance_ratio,
            confirm.volume,
            confirm_volume_multiplier,
            context_inputs,
        )
        avg_vol20 = context.avg_volume_20
        avg_dollar_volume_20 = context.avg_dollar_volume_20
        if avg_vol20 is None or avg_dollar_volume_20 is None:
            continue

        for trade_side, detector, confirmation_reason_fn in [
            ('bullish', detect_bullish_pattern, bullish_confirmation_reason),
            ('bearish', detect_bearish_pattern, bearish_confirmation_reason),
        ]:
            if side not in {'both', trade_side}:
                continue
            pattern, stop_anchor = detector(candles, idx)
            if pattern is None or stop_anchor is None:
                continue

            confirmed = (
                confirm.close > max(candidate.open, candidate.close)
                if trade_side == 'bullish'
                else confirm.close < min(candidate.open, candidate.close)
            )
            if not confirmed:
                continue

            signal_candidate = SignalCandidate(
                hit=PatternHit(
                    symbol=symbol,
                    pattern=pattern,
                    candidate_index=idx,
                    candidate_date=dates[idx],
                    confirm_index=idx + 1,
                    confirm_date=dates[idx + 1],
                ),
                side=trade_side,
                confirm_close=confirm.close,
                planned_entry_price=confirm.close if entry_mode == 'confirm_close' else candles[idx + 2].open,
                stop_loss=stop_anchor,
                first_target=(min(resistances) if resistances else confirm.close) if trade_side == 'bullish' else (max(supports) if supports else confirm.close),
                second_target=(resistances[1] if len(resistances) > 1 else confirm.close) if trade_side == 'bullish' else (supports[-2] if len(supports) > 1 else confirm.close),
                confirm_volume=confirm.volume,
                avg_volume_20=avg_vol20,
                avg_dollar_volume_20=avg_dollar_volume_20,
                entry_mode=entry_mode,
                market_cap=market_cap,
            )
            accepted, evaluated = evaluate_signal(signal_candidate, context, spec)
            if not accepted:
                continue

            plan = build_trade_plan(evaluated, candles, stop_mode=stop_mode, target_mode=target_mode)

            if trade_side == 'bullish':
                risk = plan.entry_price - plan.stop_loss
                first_target = plan.target_price
                second_target = evaluated.second_target if target_mode == 'nearest_resistance' else plan.entry_price + risk * 2
            else:
                risk = plan.stop_loss - plan.entry_price
                first_target = plan.target_price
                second_target = evaluated.second_target if target_mode == 'nearest_resistance' else plan.entry_price - risk * 2

            strength = pattern_strength_label(pattern, trade_side)
            score, score_detail = compute_signal_score(strength, confirm.volume, avg_vol20, market_cap, avg_dollar_volume_20)
            signals.append(_to_legacy_signal(
                symbol=symbol,
                dates=dates,
                candidate_index=idx,
                signal_candidate=evaluated,
                plan_entry_price=plan.entry_price,
                plan_stop_loss=plan.stop_loss,
                first_target=first_target,
                second_target=second_target,
                pattern_strength=strength,
                confirmation_reason=confirmation_reason_fn(pattern),
                score=score,
                score_detail=score_detail,
            ))
    return signals
