from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanConfig:
    universe: str = 'all-us'
    symbols: list[str] = field(default_factory=list)
    limit: int = 100
    as_of: str | None = None
    include_news: bool = False
    include_earnings: bool = False
    report_name: str = 'oneil-setups'
    out_dir: str = 'reports/oneil'

    def out_dir_path(self) -> Path:
        return Path(self.out_dir)

    def report_path(self, suffix: str) -> Path:
        return self.out_dir_path() / f'{self.report_name}.{suffix}'
