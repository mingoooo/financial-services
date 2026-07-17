from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.oneil_scanner.models import GroupedCandidateSummary, PatternCandidate, RunMetadata, ScanRunSummary
from scripts.oneil_scanner import report as report_module
from scripts.oneil_scanner.report import write_csv, write_html, write_json


def _summary() -> ScanRunSummary:
    return ScanRunSummary(
        run_metadata=RunMetadata(
            run_timestamp='2026-07-17T10:00:00',
            as_of='2026-07-16',
            report_name='daily-oneil',
            out_dir='reports/oneil',
            include_news=False,
            include_earnings=False,
        ),
        universe='all-us',
        symbols=['AAPL'],
        limit=10,
        candidates=[
            PatternCandidate(
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
            )
        ],
        grouped_candidate_summaries=[
            GroupedCandidateSummary(
                group_key='base:vcp',
                label='Base / VCP',
                candidate_count=1,
                symbols=['AAPL'],
            )
        ],
    )


def test_report_writers_emit_json_csv_and_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _summary()
    json_path = tmp_path / 'daily-oneil.json'
    csv_path = tmp_path / 'daily-oneil.csv'
    html_path = tmp_path / 'daily-oneil.html'

    using_fake_template = report_module.Template is None
    if report_module.Template is None:
        class _FakeTemplate:
            def __init__(self, _: str) -> None:
                pass

            def render(self, *, summary, columns, candidates):
                return f"{summary.candidates[0].symbol}|{columns}|{candidates[0]['catalyst_evidence_count']}|{candidates[0]['catalyst_summary']}"

        monkeypatch.setattr(report_module, 'Template', _FakeTemplate)

    write_json(json_path, summary)
    write_csv(csv_path, summary)
    write_html(html_path, summary)

    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert payload['candidate_count'] == 1
    assert payload['candidates'][0]['pattern_type'] == 'vcp'
    assert payload['grouped_candidate_summaries'][0]['label'] == 'Base / VCP'

    with csv_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]['symbol'] == 'AAPL'
    assert rows[0]['report_rank'] == '1'
    assert rows[0]['catalyst_evidence_count'] == '0'
    assert rows[0]['catalyst_summary'] == 'No usable catalyst evidence aligned with the price move'
    assert rows[0]['secondary_signals'] == 'tight closes'

    html = html_path.read_text(encoding='utf-8')
    assert 'AAPL' in html
    assert 'catalyst_evidence_count' in html
    assert 'No usable catalyst evidence aligned with the price move' in html
    if not using_fake_template:
        assert 'O&#39;Neil Setup Scanner Report' in html or "O'Neil Setup Scanner Report" in html
        assert 'Base / VCP (1)' in html


def test_report_writers_create_parent_directories(tmp_path: Path) -> None:
    summary = ScanRunSummary.empty(
        run_timestamp='2026-07-17T10:00:00',
        universe='all-us',
        report_name='empty',
        out_dir=str(tmp_path / 'nested' / 'reports'),
    )
    json_path = tmp_path / 'nested' / 'reports' / 'empty.json'

    write_json(json_path, summary)

    assert json_path.exists()
