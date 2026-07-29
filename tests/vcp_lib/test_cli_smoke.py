from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_scan_vcp_cli_smoke(tmp_path: Path) -> None:
    json_out = tmp_path / 'summary.json'
    result = subprocess.run(
        ['/Users/huangsm43/Documents/mingo/code/financial-services/.venv/bin/python', 'scripts/scan_vcp_stocks.py', '--dry-run', '--json-out', str(json_out)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout.strip())
    assert payload['data_source_mode'] == 'finviz+yahoo'
    assert json_out.exists()
