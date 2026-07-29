from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanConfig:
    universe: str = 'all-us'
    data_source: str = 'finviz+yahoo'
    min_price: float = 10.0
    min_dollar_volume: float = 10_000_000.0
    max_candidates: int = 400
    history_days: int = 420
    require_trend_template: bool = False
    max_base_depth: float = 0.35
    output_html: str = 'reports/vcp_scan.html'
    json_out: str | None = None
    csv_out: str | None = None
    cache_dir: str = '.cache/vcp'
    verbose: bool = False

    def output_html_path(self) -> Path:
        return Path(self.output_html)

    def cache_dir_path(self) -> Path:
        return Path(self.cache_dir)
