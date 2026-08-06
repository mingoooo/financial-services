from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext

FAMILY_NAME = 'qullamaggie_breakout_family'


@dataclass
class _BreakoutHit:
    pivot_price: float
    stop_reference: float
    prior_runup_pct: float
    base_length_bars: int
    base_depth_pct: float
    range_tightness_score: float
    breakout_volume_ratio: float | None
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


def _evaluate_breakout_window(frame: pd.DataFrame, *, base_length_bars: int) -> _BreakoutHit | None:
    if len(frame) < base_length_bars + 30:
        return None

    latest = frame.iloc[-1]
    pre_breakout = frame.iloc[:-1]
    base = pre_breakout.iloc[-base_length_bars:].reset_index(drop=True)
    prior_context = pre_breakout.iloc[: -base_length_bars].tail(60).reset_index(drop=True)
    if len(base) < base_length_bars or prior_context.empty:
        return None

    pivot_price = float(base['High'].max())
    base_low = float(base['Low'].min())
    prior_low = float(prior_context['Low'].min())
    if pivot_price <= 0.0 or base_low <= 0.0 or prior_low <= 0.0:
        return None

    prior_runup_pct = pivot_price / prior_low - 1.0
    if prior_runup_pct < 0.30:
        return None

    base_depth_pct = 1.0 - (base_low / pivot_price)
    if base_depth_pct <= 0.0 or base_depth_pct > 0.18:
        return None

    midpoint = max(base_length_bars // 2, 1)
    first_half = base.iloc[:midpoint]
    second_half = base.iloc[midpoint:]
    if second_half.empty:
        return None

    first_half_range_pct = ((first_half['High'] - first_half['Low']) / first_half['Close'].clip(lower=1e-6)).mean()
    second_half_range_pct = ((second_half['High'] - second_half['Low']) / second_half['Close'].clip(lower=1e-6)).mean()
    range_contraction_score = 1.0 - min(second_half_range_pct / max(first_half_range_pct, 1e-6), 1.0)
    higher_lows_score = min(1.0, max(float(second_half['Low'].min() / first_half['Low'].min() - 1.0), 0.0) * 8.0)
    shallow_base_score = min(1.0, max(0.10 - base_depth_pct, 0.0) * 2.0)
    range_tightness_score = round(min(1.0, range_contraction_score + higher_lows_score + shallow_base_score), 4)
    if range_tightness_score < 0.40:
        return None

    last_close_in_base = float(base.iloc[-1]['Close'])
    close_position = (last_close_in_base - base_low) / max(pivot_price - base_low, 1e-6)
    if close_position < 0.55:
        return None

    latest_close = float(latest['Close'])
    distance_to_pivot_pct = latest_close / pivot_price - 1.0
    if latest_close <= pivot_price or distance_to_pivot_pct > 0.06:
        return None

    breakout_volume_ratio = _breakout_volume_ratio(frame)
    if breakout_volume_ratio is None or breakout_volume_ratio < 1.2:
        return None

    quality_score = min(
        99.0,
        78.0
        + min(8.0, max(prior_runup_pct - 0.30, 0.0) * 18.0)
        + min(7.0, range_tightness_score * 10.0)
        + min(5.0, max(0.18 - base_depth_pct, 0.0) * 35.0)
        + min(4.0, max(breakout_volume_ratio - 1.2, 0.0) * 6.0),
    )
    setup_score = quality_score - max(distance_to_pivot_pct, 0.0) * 100.0
    volume_confirmation = _volume_confirmation_label(breakout_volume_ratio)

    return _BreakoutHit(
        pivot_price=pivot_price,
        stop_reference=base_low,
        prior_runup_pct=prior_runup_pct,
        base_length_bars=base_length_bars,
        base_depth_pct=base_depth_pct,
        range_tightness_score=range_tightness_score,
        breakout_volume_ratio=breakout_volume_ratio,
        quality_score=quality_score,
        setup_score=setup_score,
        notes=[
            f'prior_runup_pct={prior_runup_pct:.4f}',
            f'base_length_bars={base_length_bars}',
            f'base_depth_pct={base_depth_pct:.4f}',
            f'range_tightness_score={range_tightness_score:.4f}',
            f'breakout_level={pivot_price:.4f}',
            f'volume_confirmation={volume_confirmation}',
            f'breakout_volume_ratio={breakout_volume_ratio:.4f}',
        ],
    )


def detect_qullamaggie_breakout_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
) -> list[PatternCandidate]:
    if len(frame) < 45:
        return []

    best_hit: _BreakoutHit | None = None
    max_base_length = min(20, len(frame) - 25)
    for base_length_bars in range(max_base_length, 9, -1):
        hit = _evaluate_breakout_window(frame, base_length_bars=base_length_bars)
        if hit is None:
            continue
        if best_hit is None or (hit.setup_score, hit.quality_score) > (best_hit.setup_score, best_hit.quality_score):
            best_hit = hit

    if best_hit is None:
        return []

    latest = frame.iloc[-1]
    volume_confirmation = _volume_confirmation_label(best_hit.breakout_volume_ratio)
    return [
        PatternCandidate(
            symbol=symbol,
            pattern_family=FAMILY_NAME,
            pattern_type='qullamaggie-breakout',
            pattern_variant='tight-base',
            trigger_date=_format_date(latest.get('Date')),
            breakout_level=round(best_hit.pivot_price, 4),
            entry_zone_low=round(best_hit.pivot_price, 4),
            entry_zone_high=round(best_hit.pivot_price * 1.03, 4),
            stop_reference=round(best_hit.stop_reference, 4),
            trend_template_pass=trend_template_pass,
            rs_score=_float_or_none(latest.get('RSProxy')),
            distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
            volume_confirmation=volume_confirmation,
            catalyst_type='technical_breakout',
            catalyst_confidence=0.86 if volume_confirmation == 'confirmed' else 0.72,
            quality_score=round(best_hit.quality_score, 2),
            setup_score=round(best_hit.setup_score, 2),
            report_rank=None,
            secondary_signals=[],
            notes=best_hit.notes,
            symbol_context=symbol_context,
        )
    ]


__all__ = ['FAMILY_NAME', 'detect_qullamaggie_breakout_family']
