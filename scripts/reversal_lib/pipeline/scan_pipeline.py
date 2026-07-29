from __future__ import annotations

import time

from reversal_lib.data.market_data import fetch_candles
from reversal_lib.data.prefilter import resolve_prefiltered_universe
from reversal_lib.domain.models import PatternHit, SignalCandidate
from reversal_lib.domain.requests import UniverseRequest
from reversal_lib.indicators.context import build_indicator_context, prepare_indicator_context_inputs
from reversal_lib.models import Candle
from reversal_lib.patterns import (
    bearish_confirmation_reason,
    bullish_confirmation_reason,
    confirmation_close_strength_ok,
    compute_signal_score,
    detect_bearish_pattern,
    detect_bullish_pattern,
    detect_support_resistance_levels_from_window,
    evaluate_candlestick_quality,
    pattern_strength_label,
)
from reversal_lib.strategy.rules import evaluate_signal
from reversal_lib.strategy.spec import StrategySpec


def scan_candles(candles: list[Candle], *, symbol: str, market_cap: float | None, spec: StrategySpec) -> list[SignalCandidate]:
    signals: list[SignalCandidate] = []
    if len(candles) < 25:
        return signals

    dates = [time.strftime('%Y-%m-%d', time.gmtime(c.ts)) for c in candles]
    context_inputs = prepare_indicator_context_inputs(candles)
    location_tolerance_ratio = spec.indicator_config.get('location_tolerance_ratio', 0.02)
    allowed_patterns = spec.indicator_config.get('allowed_patterns')
    allowed_patterns_set = set(allowed_patterns) if allowed_patterns is not None else None
    require_confirmation_close_strength = spec.indicator_config.get('require_confirmation_close_strength', False)

    for idx in range(20, len(candles) - 2):
        confirm = candles[idx + 1]
        sr_window = candles[max(0, idx + 1 - 50):idx + 1]
        supports, resistances = detect_support_resistance_levels_from_window(sr_window)
        context = build_indicator_context(
            candles,
            idx,
            confirm.close,
            location_tolerance_ratio,
            confirm.volume,
            spec.confirm_volume_multiplier,
            inputs=context_inputs,
        )

        def maybe_append(side: str, pattern_result, confirmation_reason_builder) -> None:
            if not pattern_result:
                return
            pattern_name, stop_loss = pattern_result
            if not pattern_name or stop_loss is None:
                return
            if side == 'bullish':
                fallback_risk = confirm.close - stop_loss
                if fallback_risk <= 0:
                    return
                first_target = min(resistances) if resistances else (confirm.close + fallback_risk * 2)
                second_target = resistances[1] if len(resistances) > 1 else (confirm.close + fallback_risk * 2)
            else:
                fallback_risk = stop_loss - confirm.close
                if fallback_risk <= 0:
                    return
                first_target = max(supports) if supports else (confirm.close - fallback_risk * 2)
                second_target = supports[-2] if len(supports) > 1 else (confirm.close - fallback_risk * 2)
            if allowed_patterns_set is not None and pattern_name not in allowed_patterns_set:
                return
            if require_confirmation_close_strength and not confirmation_close_strength_ok(side, confirm):
                return
            pattern_strength = pattern_strength_label(pattern_name, side)
            confirmation_reason = confirmation_reason_builder(pattern_name)
            avg_volume_20 = sum(c.volume for c in candles[idx - 19:idx + 1]) / 20.0
            avg_dollar_volume_20 = sum(c.close * c.volume for c in candles[idx - 19:idx + 1]) / 20.0
            score, score_detail = compute_signal_score(pattern_strength, confirm.volume, avg_volume_20, market_cap, avg_dollar_volume_20)
            candlestick_quality, candlestick_notes = evaluate_candlestick_quality(pattern_name, side, candles, idx, confirm)
            candidate = SignalCandidate(
                hit=PatternHit(
                    symbol=symbol,
                    pattern=pattern_name,
                    candidate_index=idx,
                    candidate_date=dates[idx],
                    confirm_index=idx + 1,
                    confirm_date=dates[idx + 1],
                    pattern_strength=pattern_strength,
                    confirmation_reason=confirmation_reason,
                    score=score,
                    score_detail=score_detail,
                ),
                side=side,
                confirm_close=confirm.close,
                planned_entry_price=confirm.close,
                stop_loss=stop_loss,
                first_target=first_target,
                second_target=second_target,
                confirm_volume=confirm.volume,
                avg_volume_20=avg_volume_20,
                avg_dollar_volume_20=avg_dollar_volume_20,
                entry_mode=spec.entry_mode,
                market_cap=market_cap,
                candlestick_quality=candlestick_quality,
                candlestick_notes=candlestick_notes,
            )
            accepted, evaluated = evaluate_signal(candidate, context, spec)
            if accepted:
                signals.append(evaluated)

        if spec.side in {'bullish', 'both'}:
            maybe_append('bullish', detect_bullish_pattern(candles, idx), bullish_confirmation_reason)
        if spec.side in {'bearish', 'both'}:
            maybe_append('bearish', detect_bearish_pattern(candles, idx), bearish_confirmation_reason)

    return signals


def run_scan(spec: StrategySpec, universe_request: UniverseRequest, range_str: str) -> list[SignalCandidate]:
    prefiltered = resolve_prefiltered_universe(
        universe_request,
        include_etfs=bool(universe_request.include_etfs) if universe_request.include_etfs is not None else False,
        min_price=universe_request.min_price if universe_request.min_price is not None else 1.0,
        min_avg_volume=universe_request.min_avg_volume if universe_request.min_avg_volume is not None else 750_000,
        min_last_volume=universe_request.min_last_volume if universe_request.min_last_volume is not None else 50_000,
        min_market_cap=universe_request.min_market_cap if universe_request.min_market_cap is not None else 2_000_000_000,
        etf_groups=universe_request.etf_groups or None,
        range_str=range_str,
    )
    all_signals: list[SignalCandidate] = []
    for item in prefiltered:
        candles = fetch_candles(item.symbol, range_str=range_str)
        if not candles:
            continue
        all_signals.extend(scan_candles(candles, symbol=item.symbol, market_cap=item.market_cap, spec=spec))
    return all_signals


__all__ = ['run_scan', 'scan_candles']
