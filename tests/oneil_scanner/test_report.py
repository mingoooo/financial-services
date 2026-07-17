from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.oneil_scanner.models import ScanSummary, SetupCandidate
from scripts.oneil_scanner.report import write_csv, write_html, write_json


def _summary() -> ScanSummary:
    return ScanSummary(
        run_timestamp='2026-07-17T10:00:00',
        universe='all-us',
        symbols=['AAPL'],
        limit=10,
        as_of='2026-07-16',
        include_news=False,
        include_earnings=False,
        report_name='daily-oneil',
        out_dir='reports/oneil',
        candidates=[
            SetupCandidate(
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
        ],
    )


def test_report_writers_emit_json_csv_and_html(tmp_path: Path) -> None:
    summary = _summary()
    json_path = tmp_path / 'daily-oneil.json'
    csv_path = tmp_path / 'daily-oneil.csv'
    html_path = tmp_path / 'daily-oneil.html'

    write_json(json_path, summary)
    write_csv(csv_path, summary)
    write_html(html_path, summary)

    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert payload['candidate_count'] == 1
    assert payload['candidates'][0]['pattern_type'] == 'vcp'

    with csv_path.open(newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]['symbol'] == 'AAPL'
    assert rows[0]['report_rank'] == '1'
    assert rows[0]['secondary_signals'] == 'tight closes'

    html = html_path.read_text(encoding='utf-8')
    assert 'O&#39;Neil Setup Scanner Report' in html or "O'Neil Setup Scanner Report" in html
    assert 'AAPL' in html


def test_report_writers_create_parent_directories(tmp_path: Path) -> None:
    summary = ScanSummary.empty(
        run_timestamp='2026-07-17T10:00:00',
        universe='all-us',
        report_name='empty',
        out_dir=str(tmp_path / 'nested' / 'reports'),
    )
    json_path = tmp_path / 'nested' / 'reports' / 'empty.json'

    write_json(json_path, summary)

    assert json_path.exists()
