from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import PatternCandidate


SUPPORTED_V1_FAMILIES = frozenset({'ibd_base_family', 'vcp_breakout_family'})

_RANKING_WEIGHTS = {
    'setup_score': 0.50,
    'quality_score': 0.30,
    'normalized_rs_score': 0.20,
}


@dataclass(frozen=True)
class ScannerBacktestSignal:
    symbol: str
    trigger_date: str | None
    entry_date: str | None
    entry_price_ref: float | None
    breakout_level: float | None
    stop_reference: float | None
    primary_pattern_family: str
    primary_pattern_type: str
    primary_pattern_variant: str
    secondary_patterns: list[str]
    ranking_score: float | None
    quality_score: float | None
    setup_score: float | None
    rs_score: float | None
    normalized_rs_score: float | None


def candidate_to_signal(candidate: PatternCandidate) -> ScannerBacktestSignal:
    _validate_supported_candidate(candidate)

    normalized_rs_score = _normalize_rs_score(candidate.rs_score)
    ranking_score = _compute_ranking_score(
        setup_score=candidate.setup_score,
        quality_score=candidate.quality_score,
        normalized_rs_score=normalized_rs_score,
    )

    return ScannerBacktestSignal(
        symbol=candidate.symbol,
        trigger_date=candidate.trigger_date,
        entry_date=_next_trading_day_placeholder(candidate.trigger_date),
        entry_price_ref=candidate.breakout_level,
        breakout_level=candidate.breakout_level,
        stop_reference=candidate.stop_reference,
        primary_pattern_family=candidate.pattern_family,
        primary_pattern_type=candidate.pattern_type,
        primary_pattern_variant=candidate.pattern_variant,
        secondary_patterns=[],
        ranking_score=ranking_score,
        quality_score=_clamp_score(candidate.quality_score),
        setup_score=_clamp_score(candidate.setup_score),
        rs_score=candidate.rs_score,
        normalized_rs_score=normalized_rs_score,
    )


def collapse_candidates_for_day(candidates: list[PatternCandidate]) -> ScannerBacktestSignal:
    if not candidates:
        raise ValueError('collapse_candidates_for_day requires at least one candidate')

    symbols = {candidate.symbol for candidate in candidates}
    if len(symbols) != 1:
        raise ValueError('collapse_candidates_for_day requires candidates for exactly one symbol')

    trigger_dates = {candidate.trigger_date for candidate in candidates}
    if len(trigger_dates) != 1:
        raise ValueError('collapse_candidates_for_day requires candidates for exactly one trigger_date')

    ordered = sorted((candidate_to_signal(candidate) for candidate in candidates), key=_signal_order_key)
    primary = ordered[0]

    secondary_patterns: list[str] = []
    for overlap in ordered[1:]:
        label = _secondary_pattern_label(overlap)
        if label not in secondary_patterns:
            secondary_patterns.append(label)

    return ScannerBacktestSignal(
        symbol=primary.symbol,
        trigger_date=primary.trigger_date,
        entry_date=primary.entry_date,
        entry_price_ref=primary.entry_price_ref,
        breakout_level=primary.breakout_level,
        stop_reference=primary.stop_reference,
        primary_pattern_family=primary.primary_pattern_family,
        primary_pattern_type=primary.primary_pattern_type,
        primary_pattern_variant=primary.primary_pattern_variant,
        secondary_patterns=secondary_patterns,
        ranking_score=primary.ranking_score,
        quality_score=primary.quality_score,
        setup_score=primary.setup_score,
        rs_score=primary.rs_score,
        normalized_rs_score=primary.normalized_rs_score,
    )


def _validate_supported_candidate(candidate: PatternCandidate) -> None:
    if candidate.pattern_family not in SUPPORTED_V1_FAMILIES:
        raise ValueError(f'unsupported scanner family for V1 adapter: {candidate.pattern_family}')


def _secondary_pattern_label(signal: ScannerBacktestSignal) -> str:
    label = f'{signal.primary_pattern_family}:{signal.primary_pattern_type}'
    if signal.primary_pattern_variant:
        label = f'{label}:{signal.primary_pattern_variant}'
    return label


def _compute_ranking_score(
    *,
    setup_score: float | None,
    quality_score: float | None,
    normalized_rs_score: float | None,
) -> float | None:
    components = {
        'setup_score': _clamp_score(setup_score),
        'quality_score': _clamp_score(quality_score),
        'normalized_rs_score': _clamp_score(normalized_rs_score),
    }
    available_weights = sum(weight for name, weight in _RANKING_WEIGHTS.items() if components[name] is not None)
    if available_weights == 0:
        return None

    weighted_total = sum(_RANKING_WEIGHTS[name] * value for name, value in components.items() if value is not None)
    return round(weighted_total / available_weights, 4)


def _normalize_rs_score(rs_score: float | None) -> float | None:
    return _clamp_score(rs_score)


def _clamp_score(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, float(value)))


def _next_trading_day_placeholder(trigger_date: str | None) -> str | None:
    if not trigger_date:
        return None
    try:
        parsed = date.fromisoformat(trigger_date)
    except ValueError:
        return None
    return (parsed + timedelta(days=1)).isoformat()


def _signal_order_key(signal: ScannerBacktestSignal) -> tuple[float, float, float, float, str, str, str]:
    return (
        -_sort_score(signal.ranking_score),
        -_sort_score(signal.setup_score),
        -_sort_score(signal.quality_score),
        -_sort_score(signal.normalized_rs_score),
        signal.primary_pattern_family,
        signal.primary_pattern_type,
        signal.primary_pattern_variant,
    )


def _sort_score(value: float | None) -> float:
    if value is None:
        return float('-inf')
    return value


__all__ = ['SUPPORTED_V1_FAMILIES', 'ScannerBacktestSignal', 'candidate_to_signal', 'collapse_candidates_for_day']
