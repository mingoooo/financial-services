from __future__ import annotations

from dataclasses import replace

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext
from scripts.vcp_lib.models import BreakoutSignal, VcpDetectionResult
from scripts.vcp_lib.vcp_detector import detect_52_week_high_breakout, detect_platform_breakout, detect_vcp

FAMILY_NAME = 'vcp_breakout_family'
_PATTERN_PRIORITY = {
    'vcp': 3,
    '52-week-high-breakout': 2,
    'platform-breakout': 1,
}


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _volume_confirmation_label(*, breakout_confirmation: bool, breakout_volume_ratio: float | None) -> str:
    if breakout_confirmation:
        return 'confirmed'
    if breakout_volume_ratio is not None and breakout_volume_ratio >= 1.0:
        return 'watch'
    return 'dry-up'


def _build_notes(
    *,
    pivot_price: float | None,
    distance_to_pivot_pct: float | None,
    volume_dry_up_quality: float | None,
    breakout_confirmation: bool,
    contraction_depths: list[float] | None = None,
    extras: list[str] | None = None,
) -> list[str]:
    notes = [
        f'pivot={pivot_price:.4f}' if pivot_price is not None else 'pivot=None',
        f'distance_to_pivot_pct={distance_to_pivot_pct:.4f}' if distance_to_pivot_pct is not None else 'distance_to_pivot_pct=None',
        f'volume_dry_up_quality={volume_dry_up_quality:.4f}' if volume_dry_up_quality is not None else 'volume_dry_up_quality=None',
        f'breakout_confirmation={breakout_confirmation}',
    ]
    if contraction_depths:
        notes.append('contraction_depths=' + ','.join(f'{value:.4f}' for value in contraction_depths))
    if extras:
        notes.extend(extras)
    return notes


def _candidate_from_vcp(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None,
    result: VcpDetectionResult,
) -> PatternCandidate | None:
    if not result.detected:
        return None
    latest = frame.iloc[-1]
    breakout_level = result.pivot_price
    entry_zone_low = breakout_level
    entry_zone_high = breakout_level * 1.05 if breakout_level is not None else None
    stop_reference = breakout_level * (1.0 - min(result.base_depth_pct or 0.1, 0.1)) if breakout_level is not None else None
    quality_score = 85.0 if result.breakout_confirmation else 80.0
    if result.volume_dry_up_quality is not None:
        quality_score += min(10.0, result.volume_dry_up_quality * 10.0)
    return PatternCandidate(
        symbol=symbol,
        pattern_family=FAMILY_NAME,
        pattern_type='vcp',
        pattern_variant='textbook',
        trigger_date=result.breakout_date or (pd.to_datetime(latest['Date']).strftime('%Y-%m-%d') if 'Date' in frame.columns else None),
        breakout_level=breakout_level,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_reference=round(stop_reference, 4) if stop_reference is not None else None,
        trend_template_pass=trend_template_pass,
        rs_score=_float_or_none(latest.get('RSProxy')),
        distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
        volume_confirmation=_volume_confirmation_label(
            breakout_confirmation=result.breakout_confirmation,
            breakout_volume_ratio=result.breakout_volume_ratio,
        ),
        catalyst_type='technical_breakout',
        catalyst_confidence=0.9 if result.breakout_confirmation else 0.78,
        quality_score=round(min(99.0, quality_score), 2),
        setup_score=round(min(99.0, quality_score - (abs(result.distance_to_pivot_pct or 0.0) * 100)), 2),
        report_rank=None,
        secondary_signals=[],
        notes=_build_notes(
            pivot_price=result.pivot_price,
            distance_to_pivot_pct=result.distance_to_pivot_pct,
            volume_dry_up_quality=result.volume_dry_up_quality,
            breakout_confirmation=result.breakout_confirmation,
            contraction_depths=result.contraction_depths,
            extras=result.notes,
        ),
        symbol_context=symbol_context,
    )


def _candidate_from_breakout_signal(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None,
    signal: BreakoutSignal,
) -> PatternCandidate | None:
    if not signal.detected:
        return None
    latest = frame.iloc[-1]
    breakout_level = signal.pivot_price
    entry_zone_low = breakout_level
    entry_zone_high = breakout_level * 1.05 if breakout_level is not None else None
    stop_reference = signal.support_level or (breakout_level * 0.93 if breakout_level is not None else None)
    base_score = 82.0 if signal.pattern_type == 'platform-breakout' else 79.0
    if signal.breakout_confirmation:
        base_score += 4.0
    if signal.volume_dry_up_quality is not None:
        base_score += min(8.0, signal.volume_dry_up_quality * 10.0)
    return PatternCandidate(
        symbol=symbol,
        pattern_family=FAMILY_NAME,
        pattern_type=signal.pattern_type,
        pattern_variant=signal.pattern_variant,
        trigger_date=signal.trigger_date,
        breakout_level=breakout_level,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_reference=round(stop_reference, 4) if stop_reference is not None else None,
        trend_template_pass=trend_template_pass,
        rs_score=_float_or_none(latest.get('RSProxy')),
        distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
        volume_confirmation=_volume_confirmation_label(
            breakout_confirmation=signal.breakout_confirmation,
            breakout_volume_ratio=signal.breakout_volume_ratio,
        ),
        catalyst_type='technical_breakout',
        catalyst_confidence=0.88 if signal.breakout_confirmation else 0.72,
        quality_score=round(min(99.0, base_score), 2),
        setup_score=round(min(99.0, base_score - (abs(signal.distance_to_pivot_pct or 0.0) * 100)), 2),
        report_rank=None,
        secondary_signals=[],
        notes=_build_notes(
            pivot_price=signal.pivot_price,
            distance_to_pivot_pct=signal.distance_to_pivot_pct,
            volume_dry_up_quality=signal.volume_dry_up_quality,
            breakout_confirmation=signal.breakout_confirmation,
            contraction_depths=signal.contraction_depths,
            extras=signal.notes,
        ),
        symbol_context=symbol_context,
    )


def _collapse_overlapping_candidates(candidates: list[PatternCandidate]) -> list[PatternCandidate]:
    if len(candidates) <= 1:
        return candidates
    grouped: dict[tuple[str | None, str], list[PatternCandidate]] = {}
    for candidate in candidates:
        key = (candidate.trigger_date, candidate.symbol)
        grouped.setdefault(key, []).append(candidate)

    collapsed: list[PatternCandidate] = []
    for group in grouped.values():
        if len(group) == 1:
            collapsed.extend(group)
            continue
        ordered = sorted(group, key=lambda item: (_PATTERN_PRIORITY.get(item.pattern_type, 0), item.setup_score or 0.0), reverse=True)
        primary = ordered[0]
        merged_secondary = list(primary.secondary_signals)
        merged_notes = list(primary.notes)
        for overlap in ordered[1:]:
            if overlap.pattern_type not in merged_secondary:
                merged_secondary.append(overlap.pattern_type)
            merged_notes.append(f'overlap={overlap.pattern_type}')
        collapsed.append(replace(primary, secondary_signals=merged_secondary, notes=merged_notes))
    collapsed.sort(key=lambda item: (item.setup_score or 0.0, item.quality_score or 0.0), reverse=True)
    return collapsed


def detect_vcp_breakout_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
) -> list[PatternCandidate]:
    vcp_result = detect_vcp(frame)
    raw_candidates = [
        _candidate_from_vcp(frame, symbol=symbol, trend_template_pass=trend_template_pass, symbol_context=symbol_context, result=vcp_result),
        _candidate_from_breakout_signal(
            frame,
            symbol=symbol,
            trend_template_pass=trend_template_pass,
            symbol_context=symbol_context,
            signal=detect_platform_breakout(frame),
        ),
        _candidate_from_breakout_signal(
            frame,
            symbol=symbol,
            trend_template_pass=trend_template_pass,
            symbol_context=symbol_context,
            signal=detect_52_week_high_breakout(frame),
        ),
    ]
    return _collapse_overlapping_candidates([candidate for candidate in raw_candidates if candidate is not None])
