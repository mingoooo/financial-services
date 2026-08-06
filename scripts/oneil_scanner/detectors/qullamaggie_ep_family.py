from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext
from scripts.oneil_scanner.qullamaggie import resolve_qullamaggie_entry_trigger

FAMILY_NAME = 'qullamaggie_ep_family'


@dataclass(frozen=True)
class _CatalystEvidence:
    catalyst_type: str
    confidence: float
    evidence_count: int
    summary: str


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).strftime('%Y-%m-%d')


def _volume_confirmation_label(volume_ratio: float | None) -> str:
    if volume_ratio is not None and volume_ratio >= 1.5:
        return 'confirmed'
    if volume_ratio is not None and volume_ratio >= 1.1:
        return 'watch'
    return 'dry-up'


def _day_volume_ratio(frame: pd.DataFrame) -> float | None:
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


def _as_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).date()


def _within_catalyst_window(event_date: object, trigger_date: date) -> bool:
    parsed = _as_date(event_date)
    if parsed is None:
        return False
    return abs((trigger_date - parsed).days) <= 3


def _validate_earnings_catalyst(payload: object, *, trigger_date: date) -> _CatalystEvidence | None:
    if not isinstance(payload, dict):
        return None
    events = payload.get('events')
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict) or not _within_catalyst_window(event.get('date'), trigger_date):
            continue
        if not (event.get('reported') or event.get('confirmed') or event.get('headline')):
            continue
        confidence = 0.9
        if _float_or_none(event.get('eps_surprise_pct')) not in (None, 0.0):
            confidence = min(0.98, confidence + 0.05)
        return _CatalystEvidence(
            catalyst_type='earnings',
            confidence=confidence,
            evidence_count=2 if event.get('headline') else 1,
            summary='Earnings catalyst aligned with episodic pivot gap',
        )
    return None


def _validate_news_catalyst(payload: object, *, trigger_date: date) -> _CatalystEvidence | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get('items')
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or not _within_catalyst_window(item.get('date'), trigger_date):
            continue
        headline = str(item.get('headline') or '').strip()
        if not headline:
            continue
        confidence = 0.78 if item.get('source') else 0.72
        return _CatalystEvidence(
            catalyst_type='news',
            confidence=confidence,
            evidence_count=2 if item.get('source') else 1,
            summary='News catalyst aligned with episodic pivot gap',
        )
    return None


def _resolve_catalyst(
    *,
    trigger_date: date,
    earnings_payload: object | None,
    news_payload: object | None,
) -> _CatalystEvidence | None:
    return _validate_earnings_catalyst(earnings_payload, trigger_date=trigger_date) or _validate_news_catalyst(news_payload, trigger_date=trigger_date)


def detect_qullamaggie_ep_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
    earnings_payload: object | None = None,
    news_payload: object | None = None,
    execution_metadata: Mapping[str, object] | None = None,
) -> list[PatternCandidate]:
    if len(frame) < 25:
        return []

    latest = frame.iloc[-1]
    previous_close = _float_or_none(frame.iloc[-2].get('Close')) if len(frame) >= 2 else None
    latest_open = _float_or_none(latest.get('Open'))
    latest_high = _float_or_none(latest.get('High'))
    latest_low = _float_or_none(latest.get('Low'))
    latest_close = _float_or_none(latest.get('Close'))
    if previous_close in (None, 0.0) or latest_open is None or latest_high is None or latest_low is None or latest_close is None:
        return []

    gap_pct = _float_or_none(latest.get('GapPct'))
    if gap_pct is None:
        gap_pct = latest_open / previous_close - 1.0
    if gap_pct < 0.07:
        return []

    volume_ratio = _day_volume_ratio(frame)
    if volume_ratio is None or volume_ratio < 1.5:
        return []

    intraday_close_position = (latest_close - latest_low) / max(latest_high - latest_low, 1e-6)
    if latest_close <= latest_open or intraday_close_position < 0.6:
        return []

    trigger_date = _as_date(latest.get('Date'))
    if trigger_date is None:
        return []
    catalyst = _resolve_catalyst(trigger_date=trigger_date, earnings_payload=earnings_payload, news_payload=news_payload)
    if catalyst is None:
        return []

    breakout_level = latest_high
    candidate = PatternCandidate(
        symbol=symbol,
        pattern_family=FAMILY_NAME,
        pattern_type='episodic-pivot',
        pattern_variant=f'{catalyst.catalyst_type}-gap',
        trigger_date=_format_date(latest.get('Date')),
        breakout_level=round(breakout_level, 4),
        entry_zone_low=round(latest_open, 4),
        entry_zone_high=round(latest_high, 4),
        stop_reference=round(latest_low, 4),
        trend_template_pass=trend_template_pass,
        rs_score=_float_or_none(latest.get('RSProxy')),
        distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
        volume_confirmation=_volume_confirmation_label(volume_ratio),
        catalyst_type=catalyst.catalyst_type,
        catalyst_confidence=catalyst.confidence,
        catalyst_evidence_count=catalyst.evidence_count,
        catalyst_summary=catalyst.summary,
        quality_score=round(min(99.0, 84.0 + gap_pct * 35.0 + min(6.0, (volume_ratio - 1.5) * 4.0) + catalyst.confidence * 4.0), 2),
        setup_score=round(min(99.0, 82.0 + gap_pct * 30.0 + min(5.0, (volume_ratio - 1.5) * 3.0) + (intraday_close_position - 0.6) * 10.0), 2),
        report_rank=None,
        secondary_signals=[],
        notes=[],
        symbol_context=symbol_context,
    )
    entry_trigger = resolve_qullamaggie_entry_trigger(candidate, execution_metadata=execution_metadata)

    notes = [
        f'gap_pct={gap_pct:.4f}',
        f'catalyst_type={catalyst.catalyst_type}',
        f'catalyst_confidence={catalyst.confidence:.4f}',
        f'opening_drive_volume_ratio={volume_ratio:.4f}',
        f'entry_trigger_type={entry_trigger["entry_trigger"]}',
        f'entry_price_reference={float(entry_trigger["entry_price_reference"]):.4f}' if entry_trigger.get('entry_price_reference') is not None else 'entry_price_reference=',
        f'stop_type=low_of_day',
        f'stop_reference={latest_low:.4f}',
    ]
    if entry_trigger.get('orh_window_minutes') is not None:
        notes.append(f'or_window_used={int(entry_trigger["orh_window_minutes"])}')
    candidate.notes = notes
    return [candidate]


__all__ = ['FAMILY_NAME', 'detect_qullamaggie_ep_family']
