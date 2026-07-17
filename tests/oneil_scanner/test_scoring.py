from __future__ import annotations

from scripts.oneil_scanner.models import PatternCandidate
from scripts.oneil_scanner.scoring import _compare_primary_candidates, normalize_candidate, score_and_rank_candidates


def _candidate(
    *,
    symbol: str = 'AAPL',
    pattern_family: str = 'vcp_breakout_family',
    pattern_type: str = 'vcp',
    trigger_date: str = '2026-07-17',
    quality_score: float = 88.0,
    setup_score: float = 84.0,
    report_rank: int | None = None,
    rs_score: float = 90.0,
    distance_to_52w_high: float = 0.02,
    volume_confirmation: str = 'watch',
    catalyst_type: str = 'technical_breakout',
    catalyst_confidence: float = 0.5,
) -> PatternCandidate:
    return PatternCandidate(
        symbol=symbol,
        pattern_family=pattern_family,
        pattern_type=pattern_type,
        pattern_variant='test',
        trigger_date=trigger_date,
        breakout_level=100.0,
        entry_zone_low=100.0,
        entry_zone_high=105.0,
        stop_reference=95.0,
        trend_template_pass=True,
        rs_score=rs_score,
        distance_to_52w_high=distance_to_52w_high,
        volume_confirmation=volume_confirmation,
        catalyst_type=catalyst_type,
        catalyst_confidence=catalyst_confidence,
        quality_score=quality_score,
        setup_score=setup_score,
        report_rank=report_rank,
        secondary_signals=[],
        notes=[],
    )


def test_normalize_candidate_applies_family_specific_quality_mapping() -> None:
    event_candidate = normalize_candidate(
        _candidate(pattern_family='event_driven_family', pattern_type='earnings-gap-up', catalyst_type='earnings', catalyst_confidence=0.9)
    )
    ibd_candidate = normalize_candidate(_candidate(pattern_family='ibd_base_family', pattern_type='cup-with-handle'))
    vcp_candidate = normalize_candidate(_candidate(pattern_family='vcp_breakout_family', pattern_type='vcp'))
    momentum_candidate = normalize_candidate(
        _candidate(pattern_family='momentum_continuation_family', pattern_type='high-tight-flag')
    )

    assert event_candidate.quality_score is not None
    assert ibd_candidate.quality_score is not None
    assert vcp_candidate.quality_score is not None
    assert momentum_candidate.quality_score is not None
    assert event_candidate.quality_score > ibd_candidate.quality_score > vcp_candidate.quality_score > momentum_candidate.quality_score
    assert 0.0 <= momentum_candidate.quality_score <= 100.0
    assert 0.0 <= event_candidate.quality_score <= 100.0


def test_normalize_candidate_maps_setup_score_from_actionability_inputs() -> None:
    actionable = normalize_candidate(
        _candidate(
            symbol='NVDA',
            trigger_date='2026-07-18',
            volume_confirmation='confirmed',
            catalyst_confidence=0.9,
            rs_score=97.0,
            distance_to_52w_high=0.01,
        ),
        as_of='2026-07-18',
    )
    stale = normalize_candidate(
        _candidate(
            symbol='NVDA',
            trigger_date='2026-07-08',
            volume_confirmation='dry-up',
            catalyst_confidence=0.1,
            rs_score=74.0,
            distance_to_52w_high=0.09,
        ),
        as_of='2026-07-18',
    )

    assert actionable.setup_score is not None
    assert stale.setup_score is not None
    assert actionable.setup_score > stale.setup_score
    assert actionable.setup_score > actionable.quality_score
    assert actionable.quality_score == 96.8
    assert actionable.setup_score == 100.0


def test_score_and_rank_candidates_orders_by_report_rank() -> None:
    ranked = score_and_rank_candidates(
        [
            _candidate(
                symbol='EVNT',
                pattern_family='event_driven_family',
                pattern_type='earnings-gap-up',
                quality_score=92.0,
                setup_score=89.0,
                volume_confirmation='confirmed',
                rs_score=96.0,
                catalyst_type='earnings',
                catalyst_confidence=0.95,
            ),
            _candidate(
                symbol='IBD',
                pattern_family='ibd_base_family',
                pattern_type='cup-with-handle',
                quality_score=90.0,
                setup_score=87.0,
                volume_confirmation='confirmed',
                rs_score=93.0,
                catalyst_confidence=0.55,
            ),
            _candidate(
                symbol='MOMO',
                pattern_family='momentum_continuation_family',
                pattern_type='high-tight-flag',
                quality_score=87.0,
                setup_score=82.0,
                volume_confirmation='watch',
                rs_score=88.0,
                catalyst_confidence=0.3,
            ),
        ],
        as_of='2026-07-18',
    )

    assert [candidate.symbol for candidate in ranked] == ['EVNT', 'IBD', 'MOMO']
    assert [candidate.report_rank for candidate in ranked] == [1, 2, 3]


def test_score_and_rank_candidates_selects_primary_and_preserves_secondary_signals() -> None:
    ranked = score_and_rank_candidates(
        [
            _candidate(
                symbol='SHOP',
                pattern_family='event_driven_family',
                pattern_type='earnings-gap-up',
                quality_score=91.0,
                setup_score=88.0,
                volume_confirmation='confirmed',
                catalyst_type='earnings',
                catalyst_confidence=0.95,
            ),
            _candidate(
                symbol='SHOP',
                pattern_family='vcp_breakout_family',
                pattern_type='vcp',
                quality_score=90.5,
                setup_score=87.5,
                volume_confirmation='confirmed',
                catalyst_confidence=0.4,
            ),
        ],
        as_of='2026-07-18',
    )

    assert len(ranked) == 1
    assert ranked[0].pattern_family == 'event_driven_family'
    assert 'vcp' in ranked[0].secondary_signals


def test_primary_selection_uses_family_priority_when_quality_scores_are_close() -> None:
    ranked = score_and_rank_candidates(
        [
            _candidate(
                symbol='TSLA',
                pattern_family='event_driven_family',
                pattern_type='news-gap-up',
                quality_score=90.0,
                setup_score=86.5,
                volume_confirmation='confirmed',
                catalyst_type='news',
                catalyst_confidence=0.8,
            ),
            _candidate(
                symbol='TSLA',
                pattern_family='vcp_breakout_family',
                pattern_type='vcp',
                quality_score=90.6,
                setup_score=86.5,
                volume_confirmation='confirmed',
                catalyst_confidence=0.3,
            ),
        ],
        as_of='2026-07-18',
    )

    assert len(ranked) == 1
    assert ranked[0].pattern_family == 'event_driven_family'


def test_grouping_does_not_chain_candidates_beyond_trigger_window() -> None:
    ranked = score_and_rank_candidates(
        [
            _candidate(symbol='AAPL', trigger_date='2026-07-01', pattern_family='vcp_breakout_family', pattern_type='vcp'),
            _candidate(symbol='AAPL', trigger_date='2026-07-05', pattern_family='vcp_breakout_family', pattern_type='platform-breakout'),
            _candidate(symbol='AAPL', trigger_date='2026-07-09', pattern_family='vcp_breakout_family', pattern_type='52-week-high-breakout'),
        ],
        as_of='2026-07-18',
        trigger_window_days=5,
    )

    assert len(ranked) == 2
    assert sorted(candidate.trigger_date for candidate in ranked) == ['2026-07-01', '2026-07-09']


def test_primary_comparator_returns_zero_on_exact_tie() -> None:
    left = normalize_candidate(_candidate(symbol='MSFT', pattern_type='vcp', trigger_date='2026-07-18'), as_of='2026-07-18')
    right = normalize_candidate(_candidate(symbol='MSFT', pattern_type='vcp', trigger_date='2026-07-18'), as_of='2026-07-18')

    assert _compare_primary_candidates(left, right, as_of='2026-07-18', family_priority={'vcp_breakout_family': 2}) == 0
