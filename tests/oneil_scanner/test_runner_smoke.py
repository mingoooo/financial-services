from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.scan_oneil_setups import build_parser


def test_scan_oneil_module_import_smoke() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.universe == 'all-us'
    assert args.report_name == 'oneil-setups'


def test_scan_oneil_cli_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / 'reports'
    result = subprocess.run(
        [
            sys.executable,
            'scripts/scan_oneil_setups.py',
            '--universe',
            'all-us',
            '--symbols',
            'AAPL,MSFT',
            '--limit',
            '10',
            '--as-of',
            '2026-07-16',
            '--include-news',
            '--include-earnings',
            '--report-name',
            'smoke-run',
            '--out-dir',
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout.strip())

    assert payload['universe'] == 'all-us'
    assert payload['symbols'] == ['AAPL', 'MSFT']
    assert payload['candidate_count'] == 0
    assert payload['include_news'] is True
    assert payload['include_earnings'] is True
    assert (out_dir / 'smoke-run.json').exists()
    assert (out_dir / 'smoke-run.csv').exists()
    assert (out_dir / 'smoke-run.html').exists()
