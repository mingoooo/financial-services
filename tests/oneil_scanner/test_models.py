from __future__ import annotations

from scripts.oneil_scanner.models import (
    GroupedCandidateSummary,
    PatternCandidate,
    RunMetadata,
    ScanRunSummary,
    ScannerConfig,
    SymbolContext,
)


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
    'catalyst_evidence_count',
    'catalyst_summary',
    'quality_score',
    'setup_score',
    'report_rank',
    'secondary_signals',
    'notes',
}


def test_scanner_config_exposes_task1_cli_fields() -> None:
    config = ScannerConfig()

    assert config.universe == 'all-us'
    assert config.symbols == []
    assert config.limit == 100
    assert config.as_of is None
    assert config.include_news is False
    assert config.include_earnings is False
    assert config.report_name == 'oneil-setups'


def test_symbol_context_serializes_expected_fields() -> None:
    context = SymbolContext(
        symbol='AAPL',
        company_name='Apple Inc.',
        sector='Technology',
        industry='Consumer Electronics',
        exchange='NASDAQ',
        source_tags=['manual'],
    )

    assert context.symbol == 'AAPL'
    assert context.source_tags == ['manual']


def test_pattern_candidate_serializes_required_contract_fields() -> None:
    candidate = PatternCandidate(
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
        catalyst_type='unknown',
        catalyst_confidence=0.0,
        catalyst_evidence_count=0,
        catalyst_summary='No usable catalyst evidence aligned with the price move',
        quality_score=81.0,
        setup_score=79.0,
        report_rank=1,
        secondary_signals=['tight closes'],
        notes=['scaffold'],
        symbol_context=SymbolContext(symbol='AAPL'),
    )

    payload = candidate.to_dict()

    assert REQUIRED_FIELDS.issubset(payload.keys())
    assert payload['symbol'] == 'AAPL'
    assert payload['secondary_signals'] == ['tight closes']
    assert payload['notes'] == ['scaffold']
    assert payload['symbol_context']['symbol'] == 'AAPL'


def test_scan_run_summary_includes_grouped_candidate_support() -> None:
    summary = ScanRunSummary(
        run_metadata=RunMetadata(
            run_timestamp='2026-07-17T10:00:00',
            as_of='2026-07-16',
            report_name='daily-oneil',
            out_dir='reports/oneil',
        ),
        universe='all-us',
        grouped_candidate_summaries=[
            GroupedCandidateSummary(
                group_key='base:vcp',
                label='Base / VCP',
                candidate_count=0,
                symbols=[],
            )
        ],
    )

    payload = summary.to_dict()

    assert payload['report_name'] == 'daily-oneil'
    assert payload['candidate_count'] == 0
    assert payload['grouped_candidate_summaries'][0]['group_key'] == 'base:vcp'
    assert payload['candidates'] == []
