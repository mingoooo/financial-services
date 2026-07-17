from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


_NEWS_CATALYST_KEYWORDS = (
    'agreement',
    'approval',
    'contract',
    'deal',
    'distribution',
    'expansion',
    'guidance',
    'launch',
    'order',
    'partnership',
    'platform',
    'secures',
    'wins',
)
_STRONG_NEWS_SOURCES = ('reuters', 'bloomberg', 'dow jones', 'wall street journal', 'company', 'pr newswire')
_EARNINGS_HEADLINE_KEYWORDS = ('beat', 'beats', 'raise', 'raises', 'guidance', 'strong', 'record')


@dataclass
class CatalystEvidence:
    catalyst_type: str
    event_detected: bool
    price_pattern_triggered: bool
    catalyst_confidence: float
    catalyst_evidence_count: int
    catalyst_summary: str
    trigger_date: str | None = None
    price_pattern: str | None = None
    breakout_level: float | None = None
    stop_reference: float | None = None
    evidence_notes: list[str] = field(default_factory=list)


@dataclass
class _PricePatternState:
    triggered: bool
    pattern: str | None
    trigger_idx: int | None
    trigger_date: str | None
    breakout_level: float | None
    stop_reference: float | None
    trigger_volume_ratio: float | None


@dataclass
class _SourceEvidence:
    source_type: str
    matched: bool
    count: int
    confidence: float
    summary: str
    notes: list[str] = field(default_factory=list)


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {'true', '1', 'y', 'yes', 'confirmed', 'reported'}


def _format_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime('%Y-%m-%d')


def _date_distance_days(left: str | None, right: str | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((pd.Timestamp(left) - pd.Timestamp(right)).days)


def _event_items(payload: object, *, keys: tuple[str, ...]) -> list[dict[str, object]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _close_position(row: pd.Series) -> float | None:
    high = _float_or_none(row.get('High'))
    low = _float_or_none(row.get('Low'))
    close = _float_or_none(row.get('Close'))
    if high is None or low is None or close is None or high <= low:
        return None
    return (close - low) / (high - low)


def _is_gap_up_breakout(frame: pd.DataFrame, idx: int) -> bool:
    if idx <= 0 or idx < 20:
        return False
    row = frame.iloc[idx]
    gap_pct = _float_or_none(row.get('GapPct'))
    close = _float_or_none(row.get('Close'))
    open_price = _float_or_none(row.get('Open'))
    volume_ratio = _float_or_none(row.get('BreakoutVolumeRatio'))
    close_position = _close_position(row)
    if gap_pct is None or close is None or open_price is None:
        return False
    prior_high = _float_or_none(frame.iloc[max(0, idx - 20) : idx]['High'].max())
    if prior_high is None:
        return False
    return bool(
        gap_pct >= 0.05
        and close > prior_high
        and close >= open_price
        and (volume_ratio or 0.0) >= 1.25
        and (close_position or 0.0) >= 0.55
    )


def _detect_price_pattern(frame: pd.DataFrame, *, recent_window: int = 5) -> _PricePatternState:
    if frame.empty:
        return _PricePatternState(False, None, None, None, None, None, None)

    last_idx = len(frame) - 1
    start_idx = max(1, len(frame) - recent_window)
    qualifying_indices = [idx for idx in range(start_idx, len(frame)) if _is_gap_up_breakout(frame, idx)]
    if not qualifying_indices:
        return _PricePatternState(False, None, None, None, None, None, None)

    trigger_idx = qualifying_indices[-1]
    trigger_bar = frame.iloc[trigger_idx]
    trigger_date = _format_date(trigger_bar.get('Date'))
    trigger_volume_ratio = _float_or_none(trigger_bar.get('BreakoutVolumeRatio'))
    breakout_level = _float_or_none(trigger_bar.get('High'))
    stop_reference = _float_or_none(trigger_bar.get('Low'))

    if trigger_idx == last_idx:
        return _PricePatternState(
            True,
            'gap-up-breakout',
            trigger_idx,
            trigger_date,
            breakout_level,
            stop_reference,
            trigger_volume_ratio,
        )

    trigger_close = _float_or_none(trigger_bar.get('Close'))
    trigger_low = _float_or_none(trigger_bar.get('Low'))
    latest_close = _float_or_none(frame.iloc[-1].get('Close'))
    subsequent = frame.iloc[trigger_idx + 1 :]
    subsequent_low = _float_or_none(subsequent['Low'].min()) if not subsequent.empty else None
    if trigger_close is None or trigger_low is None or latest_close is None or subsequent_low is None:
        return _PricePatternState(False, None, None, None, None, None, None)
    if latest_close < trigger_close * 0.97:
        return _PricePatternState(False, None, None, None, None, None, None)
    if subsequent_low < trigger_low * 0.98:
        return _PricePatternState(False, None, None, None, None, None, None)

    return _PricePatternState(
        True,
        'follow-through',
        trigger_idx,
        trigger_date,
        breakout_level,
        stop_reference,
        trigger_volume_ratio,
    )


def _headline_contains_keyword(headline: str, keywords: tuple[str, ...]) -> bool:
    text = headline.lower()
    return any(keyword in text for keyword in keywords)


def _classify_earnings_evidence(payload: object, *, trigger_date: str | None) -> _SourceEvidence:
    items = _event_items(payload, keys=('events', 'items'))
    best: _SourceEvidence | None = None
    for item in items:
        event_date = _format_date(item.get('date') or item.get('event_date') or item.get('reported_at'))
        if trigger_date is not None and _date_distance_days(event_date, trigger_date) not in (0, 1, 2):
            continue

        headline = str(item.get('headline') or item.get('title') or '')
        eps_surprise = _float_or_none(item.get('eps_surprise_pct') or item.get('eps_surprise'))
        revenue_surprise = _float_or_none(item.get('revenue_surprise_pct') or item.get('revenue_surprise'))

        count = 0
        notes: list[str] = []
        if _coerce_bool(item.get('confirmed') or item.get('reported') or item.get('is_confirmed')):
            count += 1
            notes.append('confirmed_earnings_event')
        if eps_surprise is not None and eps_surprise > 0.05:
            count += 1
            notes.append('positive_eps_surprise')
        if revenue_surprise is not None and revenue_surprise > 0.03:
            count += 1
            notes.append('positive_revenue_surprise')
        if headline and _headline_contains_keyword(headline, _EARNINGS_HEADLINE_KEYWORDS):
            count += 1
            notes.append('supportive_earnings_headline')
        if count < 2:
            continue

        confidence = min(0.95, 0.45 + 0.12 * count)
        summary = 'Confirmed earnings catalyst aligned with price action'
        candidate = _SourceEvidence('earnings', True, count, round(confidence, 2), summary, notes)
        if best is None or candidate.count > best.count or candidate.confidence > best.confidence:
            best = candidate

    if best is not None:
        return best
    return _SourceEvidence('earnings', False, 0, 0.0, 'No usable earnings catalyst evidence', [])


def _classify_news_evidence(payload: object, *, trigger_date: str | None) -> _SourceEvidence:
    items = _event_items(payload, keys=('items', 'events', 'headlines'))
    best: _SourceEvidence | None = None
    for item in items:
        event_date = _format_date(item.get('date') or item.get('published_at') or item.get('providerPublishTime'))
        if trigger_date is not None and _date_distance_days(event_date, trigger_date) not in (0, 1, 2):
            continue

        headline = str(item.get('headline') or item.get('title') or '')
        source = str(item.get('source') or item.get('publisher') or '')
        if not headline or not _headline_contains_keyword(headline, _NEWS_CATALYST_KEYWORDS):
            continue

        count = 1
        notes = ['catalyst_headline_match']
        if _headline_contains_keyword(headline, ('agreement', 'contract', 'deal', 'distribution', 'order', 'partnership', 'wins', 'secures')):
            count += 1
            notes.append('hard_catalyst_keyword')
        if any(source_name in source.lower() for source_name in _STRONG_NEWS_SOURCES):
            count += 1
            notes.append('credible_source')

        confidence = min(0.9, 0.4 + 0.14 * count)
        summary = 'Confirmed news catalyst aligned with price action'
        candidate = _SourceEvidence('news', True, count, round(confidence, 2), summary, notes)
        if best is None or candidate.count > best.count or candidate.confidence > best.confidence:
            best = candidate

    if best is not None:
        return best
    return _SourceEvidence('news', False, 0, 0.0, 'No usable news catalyst evidence', [])


def classify_event_catalyst(
    frame: pd.DataFrame,
    *,
    earnings_payload: object | None = None,
    news_payload: object | None = None,
) -> CatalystEvidence:
    price_state = _detect_price_pattern(frame)
    trigger_date = price_state.trigger_date or _format_date(frame.iloc[-1].get('Date')) if not frame.empty else None
    earnings = _classify_earnings_evidence(earnings_payload, trigger_date=trigger_date)
    news = _classify_news_evidence(news_payload, trigger_date=trigger_date)

    detected_sources = [source for source in (earnings, news) if source.matched]
    if len(detected_sources) >= 2:
        confidence = round(min(0.95, (earnings.confidence + news.confidence) / 2.0 + 0.05), 2)
        return CatalystEvidence(
            catalyst_type='mixed',
            event_detected=True,
            price_pattern_triggered=price_state.triggered,
            catalyst_confidence=confidence,
            catalyst_evidence_count=earnings.count + news.count,
            catalyst_summary='Mixed catalyst evidence from earnings and news',
            trigger_date=price_state.trigger_date,
            price_pattern=price_state.pattern,
            breakout_level=price_state.breakout_level,
            stop_reference=price_state.stop_reference,
            evidence_notes=earnings.notes + news.notes,
        )

    if earnings.matched:
        return CatalystEvidence(
            catalyst_type='earnings',
            event_detected=True,
            price_pattern_triggered=price_state.triggered,
            catalyst_confidence=earnings.confidence,
            catalyst_evidence_count=earnings.count,
            catalyst_summary=earnings.summary,
            trigger_date=price_state.trigger_date,
            price_pattern=price_state.pattern,
            breakout_level=price_state.breakout_level,
            stop_reference=price_state.stop_reference,
            evidence_notes=earnings.notes,
        )

    if news.matched:
        return CatalystEvidence(
            catalyst_type='news',
            event_detected=True,
            price_pattern_triggered=price_state.triggered,
            catalyst_confidence=news.confidence,
            catalyst_evidence_count=news.count,
            catalyst_summary=news.summary,
            trigger_date=price_state.trigger_date,
            price_pattern=price_state.pattern,
            breakout_level=price_state.breakout_level,
            stop_reference=price_state.stop_reference,
            evidence_notes=news.notes,
        )

    return CatalystEvidence(
        catalyst_type='unknown',
        event_detected=False,
        price_pattern_triggered=price_state.triggered,
        catalyst_confidence=0.0,
        catalyst_evidence_count=0,
        catalyst_summary='No usable catalyst evidence aligned with the price move',
        trigger_date=price_state.trigger_date,
        price_pattern=price_state.pattern,
        breakout_level=price_state.breakout_level,
        stop_reference=price_state.stop_reference,
        evidence_notes=[],
    )
