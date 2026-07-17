from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from functools import cmp_to_key

from .models import PatternCandidate

DEFAULT_FAMILY_PRIORITY: dict[str, int] = {
    'event_driven_family': 4,
    'ibd_base_family': 3,
    'vcp_breakout_family': 2,
    'momentum_continuation_family': 1,
}

_FAMILY_QUALITY_BONUS: dict[str, float] = {
    'event_driven_family': 3.0,
    'ibd_base_family': 2.0,
    'vcp_breakout_family': 1.0,
    'momentum_continuation_family': 0.0,
}

_DEFAULT_QUALITY_BASELINE: dict[str, float] = {
    'event_driven_family': 89.0,
    'ibd_base_family': 87.0,
    'vcp_breakout_family': 85.0,
    'momentum_continuation_family': 84.0,
}

_VOLUME_QUALITY_BONUS: dict[str, float] = {
    'confirmed': 1.0,
    'watch': 0.5,
    'dry-up': 0.0,
}

_VOLUME_SETUP_BONUS: dict[str, float] = {
    'confirmed': 3.0,
    'watch': 1.0,
    'dry-up': -2.0,
}

_QUALITY_CLOSE_THRESHOLD = 1.0


def _clamp(value: float, *, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 2)


def _normalize_confidence(value: float | None) -> float:
    if value is None:
        return 0.0
    if value <= 1.0:
        return _clamp(value * 100.0)
    return _clamp(value)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return datetime.strptime(raw, '%Y-%m-%d').date()


def _recency_bonus(trigger_date: str | None, *, as_of: str | None) -> float:
    as_of_date = _parse_date(as_of)
    candidate_date = _parse_date(trigger_date)
    if as_of_date is None or candidate_date is None:
        return 0.0
    days_old = (as_of_date - candidate_date).days
    if days_old <= 1:
        return 4.0
    if days_old <= 3:
        return 2.5
    if days_old <= 5:
        return 1.0
    if days_old <= 7:
        return 0.0
    return -2.0


def _proximity_bonus(distance_to_52w_high: float | None) -> float:
    if distance_to_52w_high is None:
        return 0.0
    if distance_to_52w_high <= 0.02:
        return 3.0
    if distance_to_52w_high <= 0.05:
        return 1.5
    if distance_to_52w_high <= 0.08:
        return 0.0
    return -3.0


def _rs_bonus(rs_score: float | None) -> float:
    if rs_score is None:
        return 0.0
    if rs_score >= 95.0:
        return 2.0
    if rs_score >= 90.0:
        return 1.0
    if rs_score >= 80.0:
        return 0.0
    return -1.5


def _catalyst_setup_bonus(candidate: PatternCandidate) -> float:
    if candidate.catalyst_type in {'unknown', 'technical_breakout'}:
        return 0.0
    return round(_normalize_confidence(candidate.catalyst_confidence) * 0.025, 2)


def _raw_quality(candidate: PatternCandidate) -> float:
    if candidate.quality_score is not None:
        return candidate.quality_score
    return _DEFAULT_QUALITY_BASELINE.get(candidate.pattern_family, 85.0)


def _raw_setup(candidate: PatternCandidate, *, normalized_quality: float) -> float:
    if candidate.setup_score is not None:
        return candidate.setup_score
    return normalized_quality


def normalize_candidate(candidate: PatternCandidate, *, as_of: str | None = None) -> PatternCandidate:
    confidence = _normalize_confidence(candidate.catalyst_confidence)
    quality_score = _raw_quality(candidate)
    quality_score += _FAMILY_QUALITY_BONUS.get(candidate.pattern_family, 0.0)
    quality_score += _VOLUME_QUALITY_BONUS.get(candidate.volume_confirmation, 0.0)
    if candidate.pattern_family == 'event_driven_family':
        quality_score += round(confidence * 0.04, 2)
    quality_score = _clamp(quality_score)

    baseline_setup = (_raw_setup(candidate, normalized_quality=quality_score) + quality_score) / 2.0
    setup_score = baseline_setup
    setup_score += _VOLUME_SETUP_BONUS.get(candidate.volume_confirmation, 0.0)
    setup_score += _proximity_bonus(candidate.distance_to_52w_high)
    setup_score += _recency_bonus(candidate.trigger_date, as_of=as_of)
    setup_score += _catalyst_setup_bonus(candidate)
    setup_score += _rs_bonus(candidate.rs_score)
    setup_score = _clamp(setup_score)

    return replace(candidate, quality_score=quality_score, setup_score=setup_score)


def _report_sort_score(candidate: PatternCandidate) -> float:
    quality = candidate.quality_score or 0.0
    setup = candidate.setup_score or 0.0
    confidence = _normalize_confidence(candidate.catalyst_confidence)
    rs_score = candidate.rs_score or 0.0
    return round((quality * 0.35) + (setup * 0.45) + (confidence * 0.15) + (rs_score * 0.05), 4)


def _compare_primary_candidates(
    left: PatternCandidate,
    right: PatternCandidate,
    *,
    as_of: str | None,
    family_priority: Mapping[str, int],
) -> int:
    left_quality = left.quality_score or 0.0
    right_quality = right.quality_score or 0.0
    if abs(left_quality - right_quality) > _QUALITY_CLOSE_THRESHOLD:
        return -1 if left_quality > right_quality else 1

    left_priority = family_priority.get(left.pattern_family, 0)
    right_priority = family_priority.get(right.pattern_family, 0)
    if left_priority != right_priority:
        return -1 if left_priority > right_priority else 1

    left_confidence = _normalize_confidence(left.catalyst_confidence)
    right_confidence = _normalize_confidence(right.catalyst_confidence)
    if left_confidence != right_confidence:
        return -1 if left_confidence > right_confidence else 1

    left_recency = _recency_bonus(left.trigger_date, as_of=as_of)
    right_recency = _recency_bonus(right.trigger_date, as_of=as_of)
    if left_recency != right_recency:
        return -1 if left_recency > right_recency else 1

    left_setup = left.setup_score or 0.0
    right_setup = right.setup_score or 0.0
    if left_setup != right_setup:
        return -1 if left_setup > right_setup else 1

    left_report = _report_sort_score(left)
    right_report = _report_sort_score(right)
    if left_report != right_report:
        return -1 if left_report > right_report else 1

    return -1 if left.pattern_type < right.pattern_type else 1


def _secondary_signal_label(primary: PatternCandidate, overlap: PatternCandidate) -> str:
    if overlap.pattern_type != primary.pattern_type:
        return overlap.pattern_type
    return overlap.pattern_family


def _group_overlapping_candidates(
    candidates: list[PatternCandidate],
    *,
    trigger_window_days: int,
) -> list[list[PatternCandidate]]:
    grouped: list[list[PatternCandidate]] = []
    by_symbol: dict[str, list[PatternCandidate]] = {}
    for candidate in sorted(candidates, key=lambda item: (item.symbol, item.trigger_date or '', item.pattern_family, item.pattern_type)):
        by_symbol.setdefault(candidate.symbol, []).append(candidate)

    for symbol_candidates in by_symbol.values():
        windows: list[list[PatternCandidate]] = []
        for candidate in symbol_candidates:
            candidate_date = _parse_date(candidate.trigger_date)
            placed = False
            for window in windows:
                window_dates = [_parse_date(item.trigger_date) for item in window]
                dated_items = [item for item in window_dates if item is not None]
                if candidate_date is None or not dated_items:
                    if candidate.trigger_date == window[0].trigger_date:
                        window.append(candidate)
                        placed = True
                        break
                    continue
                latest_date = max(dated_items)
                if abs((candidate_date - latest_date).days) <= trigger_window_days:
                    window.append(candidate)
                    placed = True
                    break
            if not placed:
                windows.append([candidate])
        grouped.extend(windows)

    return grouped


def score_and_rank_candidates(
    candidates: list[PatternCandidate],
    *,
    as_of: str | None = None,
    trigger_window_days: int = 5,
    family_priority: Mapping[str, int] | None = None,
) -> list[PatternCandidate]:
    priority_map = family_priority or DEFAULT_FAMILY_PRIORITY
    normalized = [normalize_candidate(candidate, as_of=as_of) for candidate in candidates]

    deduplicated: list[PatternCandidate] = []
    for group in _group_overlapping_candidates(normalized, trigger_window_days=trigger_window_days):
        if len(group) == 1:
            deduplicated.append(group[0])
            continue

        ordered = sorted(
            group,
            key=cmp_to_key(lambda left, right: _compare_primary_candidates(left, right, as_of=as_of, family_priority=priority_map)),
        )
        primary = ordered[0]
        secondary_signals = list(primary.secondary_signals)
        notes = list(primary.notes)
        for overlap in ordered[1:]:
            signal_label = _secondary_signal_label(primary, overlap)
            if signal_label not in secondary_signals:
                secondary_signals.append(signal_label)
            notes.append(f'overlap={overlap.pattern_family}:{overlap.pattern_type}')
        deduplicated.append(replace(primary, secondary_signals=secondary_signals, notes=notes))

    ranked = sorted(
        deduplicated,
        key=lambda item: (
            _report_sort_score(item),
            item.setup_score or 0.0,
            item.quality_score or 0.0,
            priority_map.get(item.pattern_family, 0),
            _normalize_confidence(item.catalyst_confidence),
        ),
        reverse=True,
    )
    return [replace(candidate, report_rank=index) for index, candidate in enumerate(ranked, start=1)]


__all__ = ['DEFAULT_FAMILY_PRIORITY', 'normalize_candidate', 'score_and_rank_candidates']
