from __future__ import annotations

from pathlib import Path

from scripts.vcp_lib.models import ScanSummary, UniverseSnapshot
from scripts.vcp_lib.report import write_html


def test_write_html_smoke(tmp_path: Path) -> None:
    summary = ScanSummary(
        run_timestamp='2026-07-16T12:00:00',
        data_source_mode='yahoo-only',
        universe=UniverseSnapshot(requested_universe='all-us', data_source_mode='yahoo-only'),
    )
    output = tmp_path / 'report.html'
    write_html(str(output), summary)
    assert output.exists()
    assert 'VCP 扫描报告' in output.read_text(encoding='utf-8')
