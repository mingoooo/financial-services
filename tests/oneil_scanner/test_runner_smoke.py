from __future__ import annotations

import json
import subprocess
from pathlib import Path


PYTHON = '/Users/huangsm43/Documents/mingo/code/financial-services/.venv/bin/python'


def test_scan_oneil_cli_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / 'reports'
    result = subprocess.run(
        [
            PYTHON,
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
