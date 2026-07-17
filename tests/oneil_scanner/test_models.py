from __future__ import annotations

from scripts.oneil_scanner.models import ScanSummary, SetupCandidate


REQUIRED_FIELDS = {
    'pattern_family',
    'pattern_type',
    'pattern_variant',
    'trigger_date',
    'breakout_level',
    'entry_zone_low',
    'entry_zone_high',
    'stop_reference',
    'trend_template_pass',
    'rs_score',
    'distance_to_52w_high',
    'volume_confirmation',
    'catalyst_type',
    'catalyst_confidence',
    'quality_score',
    'setup_score',
    'report_rank',
    'secondary_signals',
    'notes',
}


def test_setup_candidate_serializes_required_contract_fields() -> None:
    candidate = SetupCandidate(
        symbol='AAPL',
        pattern_family='base',
        pattern_type='vcp',
        pattern_variant='early',
        trigger_date='2026-07-16',
        breakout_level=215.5,
        entry_zone_low=215.5,
        entry_zone_high=219.81,
        stop_reference=207.0,
        trend_template_pass=True,
        rs_score=92.5,
        distance_to_52w_high=0.03,
        volume_confirmation='pending',
        catalyst_type='none',
        catalyst_confidence=0.0,
        quality_score=81.0,
        setup_score=79.0,
        report_rank=1,
        secondary_signals=['tight closes'],
        notes=['scaffold'],
    )

    payload = candidate.to_dict()

    assert REQUIRED_FIELDS.issubset(payload.keys())
    assert payload['symbol'] == 'AAPL'
    assert payload['secondary_signals'] == ['tight closes']
    assert payload['notes'] == ['scaffold']


def test_scan_summary_to_dict_keeps_candidates_and_counts() -> None:
    summary = ScanSummary.empty(
        run_timestamp='2026-07-17T10:00:00',
        universe='all-us',
        report_name='daily-oneil',
        out_dir='reports/oneil',
        as_of='2026-07-16',
    )

    payload = summary.to_dict()

    assert payload['report_name'] == 'daily-oneil'
    assert payload['candidate_count'] == 0
    assert payload['candidates'] == []
