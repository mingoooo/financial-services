from __future__ import annotations

import pytest

from scripts.oneil_scanner import ScannerBacktestSignal, candidate_to_signal, collapse_candidates_for_day
from scripts.oneil_scanner.models import PatternCandidate


def _candidate(
    *,
    symbol: str = 'AAPL',
    pattern_family: str = 'ibd_base_family',
    pattern_type: str = 'cup-with-handle',
    pattern_variant: str = 'standard',
    trigger_date: str = '2026-07-17',
    breakout_level: float = 215.5,
    stop_reference: float = 205.0,
    quality_score: float | None = 92.0,
    setup_score: float | None = 96.0,
    rs_score: float | None = 98.0,
) -> PatternCandidate:
    return PatternCandidate(
        symbol=symbol,
        pattern_family=pattern_family,
        pattern_type=pattern_type,
        pattern_variant=pattern_variant,
        trigger_date=trigger_date,
        breakout_level=breakout_level,
        entry_zone_low=breakout_level,
        entry_zone_high=breakout_level * 1.05,
        stop_reference=stop_reference,
        trend_template_pass=True,
        rs_score=rs_score,
        distance_to_52w_high=0.02,
        volume_confirmation='confirmed',
        catalyst_type='technical_breakout',
        catalyst_confidence=0.75,
        quality_score=quality_score,
        setup_score=setup_score,
        report_rank=None,
        secondary_signals=[],
        notes=[],
    )


def test_candidate_to_signal_converts_one_supported_candidate() -> None:
    candidate = _candidate()

    signal = candidate_to_signal(candidate)

    assert isinstance(signal, ScannerBacktestSignal)
    assert signal.symbol == 'AAPL'
    assert signal.trigger_date == '2026-07-17'
    assert signal.entry_date == '2026-07-18'
    assert signal.entry_price_ref == 215.5
    assert signal.breakout_level == 215.5
    assert signal.stop_reference == 205.0
    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == []
    assert signal.ranking_score == pytest.approx(95.2)


def test_collapse_candidates_for_day_merges_secondary_patterns() -> None:
    cup_hit = _candidate(pattern_type='cup-with-handle', pattern_variant='standard', setup_score=96.0, quality_score=92.0)
    flat_base_hit = _candidate(pattern_type='flat-base', pattern_variant='tight', setup_score=88.0, quality_score=90.0)

    signal = collapse_candidates_for_day([cup_hit, flat_base_hit])

    assert signal.symbol == 'AAPL'
    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == ['ibd_base_family:flat-base:tight']


def test_collapse_candidates_for_day_uses_ranking_score_to_choose_primary() -> None:
    lower_quality_better_setup = _candidate(
        pattern_type='cup-with-handle',
        pattern_variant='standard',
        quality_score=90.0,
        setup_score=97.0,
        rs_score=98.0,
    )
    higher_quality_weaker_setup = _candidate(
        pattern_type='flat-base',
        pattern_variant='tight',
        quality_score=94.0,
        setup_score=86.0,
        rs_score=88.0,
    )

    signal = collapse_candidates_for_day([higher_quality_weaker_setup, lower_quality_better_setup])

    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == ['ibd_base_family:flat-base:tight']
    assert signal.ranking_score == pytest.approx(95.1)


@pytest.mark.parametrize('unsupported_family', ['event_driven_family', 'momentum_continuation_family'])
def test_candidate_to_signal_rejects_unsupported_v1_families(unsupported_family: str) -> None:
    candidate = _candidate(pattern_family=unsupported_family, pattern_type='unsupported-pattern')

    with pytest.raises(ValueError, match='unsupported'):
        candidate_to_signal(candidate)


def test_candidate_to_signal_renormalizes_ranking_when_rs_missing() -> None:
    candidate = _candidate(rs_score=None, setup_score=80.0, quality_score=90.0)

    signal = candidate_to_signal(candidate)

    assert signal.ranking_score == pytest.approx(83.75)
