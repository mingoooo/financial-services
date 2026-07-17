from __future__ import annotations

import pandas as pd

from scripts.oneil_scanner.event_classifier import classify_event_catalyst
from scripts.oneil_scanner.models import PatternCandidate, SymbolContext

FAMILY_NAME = 'event_driven_family'


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _volume_confirmation_label(volume_ratio: float | None) -> str:
    if volume_ratio is not None and volume_ratio >= 1.2:
        return 'confirmed'
    if volume_ratio is not None and volume_ratio >= 1.0:
        return 'watch'
    return 'dry-up'


def _pattern_type(evidence_type: str, price_pattern: str | None) -> str:
    if price_pattern == 'follow-through':
        return 'event-follow-through'
    if evidence_type in {'earnings', 'news'}:
        return f'{evidence_type}-gap-breakout'
    return 'event-gap-breakout'


def detect_event_driven_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
    earnings_payload: object | None = None,
    news_payload: object | None = None,
) -> list[PatternCandidate]:
    evidence = classify_event_catalyst(
        frame,
        earnings_payload=earnings_payload,
        news_payload=news_payload,
    )
    if not evidence.event_detected or not evidence.price_pattern_triggered:
        return []

    latest = frame.iloc[-1]
    breakout_level = evidence.breakout_level
    stop_reference = evidence.stop_reference
    if breakout_level is None or stop_reference is None:
        return []

    extension_pct = max(0.0, (float(latest['Close']) / breakout_level) - 1.0)
    quality_score = round(min(99.0, 82.0 + evidence.catalyst_confidence * 12.0 + evidence.catalyst_evidence_count), 2)
    setup_score = round(max(0.0, quality_score - extension_pct * 100.0), 2)
    trigger_volume_ratio = _float_or_none(frame.loc[frame['Date'] == pd.Timestamp(evidence.trigger_date), 'BreakoutVolumeRatio'].iloc[-1]) if evidence.trigger_date and 'Date' in frame.columns and not frame.loc[frame['Date'] == pd.Timestamp(evidence.trigger_date)].empty else _float_or_none(latest.get('BreakoutVolumeRatio'))

    return [
        PatternCandidate(
            symbol=symbol,
            pattern_family=FAMILY_NAME,
            pattern_type=_pattern_type(evidence.catalyst_type, evidence.price_pattern),
            pattern_variant=evidence.catalyst_type,
            trigger_date=evidence.trigger_date,
            breakout_level=round(breakout_level, 4),
            entry_zone_low=round(breakout_level, 4),
            entry_zone_high=round(breakout_level * 1.05, 4),
            stop_reference=round(stop_reference, 4),
            trend_template_pass=trend_template_pass,
            rs_score=_float_or_none(latest.get('RSProxy')),
            distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
            volume_confirmation=_volume_confirmation_label(trigger_volume_ratio),
            catalyst_type=evidence.catalyst_type,
            catalyst_confidence=evidence.catalyst_confidence,
            catalyst_evidence_count=evidence.catalyst_evidence_count,
            catalyst_summary=evidence.catalyst_summary,
            quality_score=quality_score,
            setup_score=setup_score,
            report_rank=None,
            secondary_signals=[],
            notes=[
                f'catalyst_summary={evidence.catalyst_summary}',
                f'catalyst_evidence_count={evidence.catalyst_evidence_count}',
                f'price_pattern={evidence.price_pattern}',
            ]
            + [f'evidence={note}' for note in evidence.evidence_notes],
            symbol_context=symbol_context,
        )
    ]
