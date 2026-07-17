from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext

FAMILY_NAME = 'momentum_continuation_family'
_PATTERN_PRIORITY = {
    'high-tight-flag': 2,
    'continuation-breakout': 1,
}


@dataclass
class _ContinuationHit:
    pattern_type: str
    pattern_variant: str
    pivot_price: float
    stop_reference: float
    prior_advance_pct: float
    consolidation_depth_pct: float
    consolidation_days: int
    breakout_volume_ratio: float | None
    extension_pct: float
    quality_score: float
    setup_score: float
    notes: list[str]


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)



def _format_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).strftime('%Y-%m-%d')



def _breakout_volume_ratio(frame: pd.DataFrame) -> float | None:
    latest = frame.iloc[-1]
    volume_ratio = _float_or_none(latest.get('BreakoutVolumeRatio'))
    if volume_ratio is not None:
        return volume_ratio
    avg_volume = _float_or_none(latest.get('AvgVolume20'))
    if avg_volume in (None, 0.0):
        avg_volume = _float_or_none(frame['Volume'].tail(20).mean())
    latest_volume = _float_or_none(latest.get('Volume'))
    if avg_volume in (None, 0.0) or latest_volume is None:
        return None
    return latest_volume / avg_volume



def _volume_confirmation_label(volume_ratio: float | None) -> str:
    if volume_ratio is not None and volume_ratio >= 1.2:
        return 'confirmed'
    if volume_ratio is not None and volume_ratio >= 1.0:
        return 'watch'
    return 'dry-up'



def _build_candidate(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None,
    hit: _ContinuationHit,
) -> PatternCandidate:
    latest = frame.iloc[-1]
    return PatternCandidate(
        symbol=symbol,
        pattern_family=FAMILY_NAME,
        pattern_type=hit.pattern_type,
        pattern_variant=hit.pattern_variant,
        trigger_date=_format_date(latest.get('Date')),
        breakout_level=round(hit.pivot_price, 4),
        entry_zone_low=round(hit.pivot_price, 4),
        entry_zone_high=round(hit.pivot_price * 1.05, 4),
        stop_reference=round(hit.stop_reference, 4),
        trend_template_pass=trend_template_pass,
        rs_score=_float_or_none(latest.get('RSProxy')),
        distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
        volume_confirmation=_volume_confirmation_label(hit.breakout_volume_ratio),
        catalyst_type='technical_breakout',
        catalyst_confidence=0.88,
        quality_score=round(min(hit.quality_score, 99.0), 2),
        setup_score=round(min(hit.setup_score, 99.0), 2),
        report_rank=None,
        secondary_signals=[],
        notes=hit.notes,
        symbol_context=symbol_context,
    )



def _evaluate_continuation_window(
    frame: pd.DataFrame,
    *,
    breakout_span: int,
    consolidation_len: int,
    prior_lookback: int,
    min_prior_advance_pct: float,
    max_consolidation_depth_pct: float,
    max_extension_pct: float,
    min_breakout_volume_ratio: float,
    max_flag_volume_ratio: float,
    pattern_type: str,
    pattern_variant: str,
    quality_base: float,
    depth_note_name: str,
) -> _ContinuationHit | None:
    latest_close = float(frame.iloc[-1]['Close'])
    latest_volume_ratio = _breakout_volume_ratio(frame)
    if latest_volume_ratio is None or latest_volume_ratio < min_breakout_volume_ratio:
        return None

    pre_breakout = frame.iloc[:-breakout_span]
    if len(pre_breakout) < consolidation_len + prior_lookback:
        return None

    consolidation = pre_breakout.iloc[-consolidation_len:]
    prior_context = pre_breakout.iloc[-(consolidation_len + prior_lookback) : -consolidation_len]
    if prior_context.empty:
        return None

    pivot_series = consolidation['High'].reset_index(drop=True)
    pivot_pos = int(pivot_series.idxmax())
    if pivot_pos > consolidation_len - 3:
        return None

    pivot_price = float(pivot_series.iloc[pivot_pos])
    consolidation_low = float(consolidation['Low'].min())
    if pivot_price <= 0.0:
        return None

    if float(pre_breakout.iloc[-1]['Close']) > pivot_price:
        return None

    prior_low = float(prior_context['Low'].min())
    if prior_low <= 0.0:
        return None

    prior_advance_pct = pivot_price / prior_low - 1.0
    if prior_advance_pct < min_prior_advance_pct:
        return None

    consolidation_depth_pct = 1.0 - consolidation_low / pivot_price
    if consolidation_depth_pct <= 0.0 or consolidation_depth_pct > max_consolidation_depth_pct:
        return None

    extension_pct = latest_close / pivot_price - 1.0
    if latest_close <= pivot_price or extension_pct <= 0.0 or extension_pct > max_extension_pct:
        return None

    flag_volume_ratio = float(consolidation['Volume'].mean()) / max(float(prior_context['Volume'].mean()), 1.0)
    if flag_volume_ratio > max_flag_volume_ratio:
        return None

    full_range_pct = (float(consolidation['High'].max()) - consolidation_low) / pivot_price
    if full_range_pct > max_consolidation_depth_pct * 1.15:
        return None

    closing_range = max(pivot_price - consolidation_low, 1e-6)
    close_position = (float(consolidation.iloc[-1]['Close']) - consolidation_low) / closing_range
    if close_position < 0.45:
        return None

    quality_score = (
        quality_base
        + min(8.0, max(prior_advance_pct - min_prior_advance_pct, 0.0) * 20.0)
        + min(4.0, max(max_consolidation_depth_pct - consolidation_depth_pct, 0.0) * 40.0)
        + min(4.0, max(latest_volume_ratio - min_breakout_volume_ratio, 0.0) * 8.0)
    )
    setup_score = quality_score - extension_pct * 100.0 - max(flag_volume_ratio - 0.7, 0.0) * 10.0

    return _ContinuationHit(
        pattern_type=pattern_type,
        pattern_variant=pattern_variant,
        pivot_price=pivot_price,
        stop_reference=consolidation_low,
        prior_advance_pct=prior_advance_pct,
        consolidation_depth_pct=consolidation_depth_pct,
        consolidation_days=consolidation_len,
        breakout_volume_ratio=latest_volume_ratio,
        extension_pct=extension_pct,
        quality_score=quality_score,
        setup_score=setup_score,
        notes=[
            f'pivot={pivot_price:.4f}',
            f'prior_advance_pct={prior_advance_pct:.4f}',
            f'{depth_note_name}={consolidation_depth_pct:.4f}',
            f'consolidation_days={consolidation_len}',
            f'breakout_volume_ratio={latest_volume_ratio:.4f}',
            f'extension_pct={extension_pct:.4f}',
            f'flag_volume_ratio={flag_volume_ratio:.4f}',
        ],
    )



def _detect_high_tight_flag(frame: pd.DataFrame) -> _ContinuationHit | None:
    if len(frame) < 45:
        return None

    best_hit: _ContinuationHit | None = None
    for breakout_span in range(1, 6):
        for consolidation_len in range(8, 19):
            hit = _evaluate_continuation_window(
                frame,
                breakout_span=breakout_span,
                consolidation_len=consolidation_len,
                prior_lookback=35,
                min_prior_advance_pct=0.85,
                max_consolidation_depth_pct=0.16,
                max_extension_pct=0.08,
                min_breakout_volume_ratio=1.3,
                max_flag_volume_ratio=0.82,
                pattern_type='high-tight-flag',
                pattern_variant='textbook',
                quality_base=90.0,
                depth_note_name='flag_depth_pct',
            )
            if hit is None:
                continue
            if best_hit is None or hit.setup_score > best_hit.setup_score:
                best_hit = hit
    return best_hit



def _detect_continuation_breakout(frame: pd.DataFrame) -> _ContinuationHit | None:
    if len(frame) < 40:
        return None

    best_hit: _ContinuationHit | None = None
    for breakout_span in range(1, 6):
        for consolidation_len in range(10, 27):
            hit = _evaluate_continuation_window(
                frame,
                breakout_span=breakout_span,
                consolidation_len=consolidation_len,
                prior_lookback=45,
                min_prior_advance_pct=0.40,
                max_consolidation_depth_pct=0.18,
                max_extension_pct=0.06,
                min_breakout_volume_ratio=1.15,
                max_flag_volume_ratio=0.9,
                pattern_type='continuation-breakout',
                pattern_variant='momentum',
                quality_base=84.0,
                depth_note_name='consolidation_depth_pct',
            )
            if hit is None:
                continue
            if best_hit is None or hit.setup_score > best_hit.setup_score:
                best_hit = hit
    return best_hit



def detect_momentum_continuation_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
) -> list[PatternCandidate]:
    raw_hits = [
        _detect_high_tight_flag(frame),
        _detect_continuation_breakout(frame),
    ]
    hits = [hit for hit in raw_hits if hit is not None]
    if not hits:
        return []

    best_hit = sorted(
        hits,
        key=lambda item: (_PATTERN_PRIORITY.get(item.pattern_type, 0), item.setup_score, item.quality_score),
        reverse=True,
    )[0]
    return [
        _build_candidate(
            frame,
            symbol=symbol,
            trend_template_pass=trend_template_pass,
            symbol_context=symbol_context,
            hit=best_hit,
        )
    ]
