from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from scripts.oneil_scanner.config import ScannerConfig
from scripts.oneil_scanner.data import build_scan_window_key
from scripts.oneil_scanner.models import PatternCandidate, RunMetadata, ScanRunSummary
from scripts.oneil_scanner.report import build_grouped_candidate_summaries, write_csv, write_html, write_json
from scripts.vcp_lib.data_sources import cache_path, frame_to_serializable_records, write_json_cache


def _candidate(
    *,
    symbol: str,
    family: str,
    pattern_type: str,
    rank: int,
    catalyst_type: str = 'technical_breakout',
) -> PatternCandidate:
    return PatternCandidate(
        symbol=symbol,
        pattern_family=family,
        pattern_type=pattern_type,
        pattern_variant='test',
        trigger_date='2026-07-16',
        breakout_level=215.5,
        entry_zone_low=215.5,
        entry_zone_high=219.81,
        stop_reference=207.0,
        trend_template_pass=True,
        rs_score=92.5,
        distance_to_52w_high=0.03,
        volume_confirmation='confirmed',
        catalyst_type=catalyst_type,
        catalyst_confidence=0.8 if catalyst_type not in {'technical_breakout', 'unknown'} else 0.0,
        catalyst_evidence_count=2 if catalyst_type not in {'technical_breakout', 'unknown'} else 1,
        catalyst_summary='Confirmed catalyst aligned with price action' if catalyst_type not in {'technical_breakout', 'unknown'} else None,
        quality_score=81.0 + rank,
        setup_score=79.0 + rank,
        report_rank=rank,
        secondary_signals=['tight closes'],
        notes=['scaffold'],
    )


def _summary() -> ScanRunSummary:
    candidates = [
        _candidate(symbol='EVNT', family='event_driven_family', pattern_type='event-follow-through', rank=1, catalyst_type='earnings'),
        _candidate(symbol='IBD', family='ibd_base_family', pattern_type='cup-with-handle', rank=2),
        _candidate(symbol='VCP', family='vcp_breakout_family', pattern_type='vcp', rank=3),
        _candidate(symbol='MOMO', family='momentum_continuation_family', pattern_type='high-tight-flag', rank=4),
    ]
    return ScanRunSummary(
        run_metadata=RunMetadata(
            run_timestamp='2026-07-17T10:00:00',
            as_of='2026-07-16',
            report_name='daily-oneil',
            out_dir='reports/oneil',
            warnings=['Sparse event data for news:VCP; continuing without enrichment.'],
        ),
        universe='all-us',
        symbols=['EVNT', 'IBD', 'VCP', 'MOMO'],
        limit=10,
        candidates=candidates,
        grouped_candidate_summaries=build_grouped_candidate_summaries(candidates),
    )


def _chart_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            'Date': pd.date_range('2026-05-01', periods=80, freq='D'),
            'Open': [100 + index * 0.4 for index in range(80)],
            'High': [101 + index * 0.4 for index in range(80)],
            'Low': [99 + index * 0.4 for index in range(80)],
            'Close': [100.5 + index * 0.4 for index in range(80)],
            'Volume': [1_000_000 + index * 12_500 for index in range(80)],
        }
    )


def _write_cached_frame(cache_dir: Path, symbol: str, *, as_of: str) -> None:
    frame = _chart_frame().copy()
    payload = frame.set_index('Date')
    window_key = build_scan_window_key(as_of=as_of, period='1y', interval='1d')
    write_json_cache(
        cache_path(cache_dir, f'oneil_scanner/ohlcv/{window_key}', symbol),
        {
            'frame': frame_to_serializable_records(payload),
            'fetched_at': as_of,
            'last_date': as_of,
        },
    )


def test_report_writers_emit_json_csv_and_html(tmp_path: Path) -> None:
    summary = _summary()
    config = ScannerConfig(as_of='2026-07-16', cache_dir=str(tmp_path / 'cache'))
    json_path = tmp_path / 'daily-oneil.json'
    csv_path = tmp_path / 'daily-oneil.csv'
    html_path = tmp_path / 'daily-oneil.html'

    for symbol in summary.symbols:
        _write_cached_frame(Path(config.cache_dir), symbol, as_of='2026-07-16')

    write_json(json_path, summary)
    write_csv(csv_path, summary)
    write_html(html_path, summary, config=config)

    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert payload['candidate_count'] == 4
    assert payload['candidates'][0]['pattern_type'] == 'event-follow-through'
    assert payload['grouped_candidate_summaries'][0]['label'] == 'Top Setups'
    assert {group['group_key'] for group in payload['grouped_candidate_summaries']} == {
        'top_setups',
        'event_driven_setups',
        'ibd_base_setups',
        'vcp_breakout_setups',
        'momentum_continuation_setups',
    }

    with csv_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]['symbol'] == 'EVNT'
    assert rows[0]['report_rank'] == '1'
    assert rows[0]['secondary_signals'] == 'tight closes'
    assert rows[0]['catalyst_type'] == 'earnings'

    html = html_path.read_text(encoding='utf-8')
    assert 'Setup Scanner Report' in html
    assert 'Strategy profile: oneil' in html
    assert '形态扫描报告' in html
    assert 'English' in html
    assert '中文' in html
    assert 'setLanguage(' in html
    assert 'Top Setups (4)' in html
    assert '重点候选 (4)' in html
    assert 'Event-Driven Setups (1)' in html
    assert '事件驱动形态 (1)' in html
    assert 'IBD Base Setups (1)' in html
    assert 'IBD 底部形态 (1)' in html
    assert 'VCP/Breakout Setups (1)' in html
    assert 'VCP / 突破形态 (1)' in html
    assert 'Momentum Continuation Setups (1)' in html
    assert '动量延续形态 (1)' in html
    assert 'quality 82.0' in html
    assert '质量分 82.0' in html
    assert 'Chart' in html
    assert '图表' in html
    assert 'chart-svg' in html
    assert '<svg class="chart-svg"' in html
    assert 'MA20' in html
    assert 'MA50' in html
    assert 'MA200' in html
    assert 'class="ma-line ma20"' in html
    assert 'Warnings' in html
    assert '警告' in html


def test_report_writers_create_parent_directories(tmp_path: Path) -> None:
    summary = ScanRunSummary.empty(
        run_timestamp='2026-07-17T10:00:00',
        universe='all-us',
        report_name='empty',
        out_dir=str(tmp_path / 'nested' / 'reports'),
    )
    summary.grouped_candidate_summaries = build_grouped_candidate_summaries(summary.candidates)
    json_path = tmp_path / 'nested' / 'reports' / 'empty.json'

    write_json(json_path, summary)

    assert json_path.exists()
