from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SetupCandidate:
    symbol: str
    pattern_family: str
    pattern_type: str
    pattern_variant: str
    trigger_date: str | None
    breakout_level: float | None
    entry_zone_low: float | None
    entry_zone_high: float | None
    stop_reference: float | None
    trend_template_pass: bool
    rs_score: float | None
    distance_to_52w_high: float | None
    volume_confirmation: str
    catalyst_type: str
    catalyst_confidence: float | None
    quality_score: float | None
    setup_score: float | None
    report_rank: int | None
    secondary_signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanSummary:
    run_timestamp: str
    universe: str
    symbols: list[str] = field(default_factory=list)
    limit: int | None = None
    as_of: str | None = None
    include_news: bool = False
    include_earnings: bool = False
    report_name: str = 'oneil-setups'
    out_dir: str = 'reports/oneil'
    candidates: list[SetupCandidate] = field(default_factory=list)

    @classmethod
    def empty(
        cls,
        *,
        run_timestamp: str,
        universe: str,
        report_name: str,
        out_dir: str,
        symbols: list[str] | None = None,
        limit: int | None = None,
        as_of: str | None = None,
        include_news: bool = False,
        include_earnings: bool = False,
    ) -> 'ScanSummary':
        return cls(
            run_timestamp=run_timestamp,
            universe=universe,
            symbols=symbols or [],
            limit=limit,
            as_of=as_of,
            include_news=include_news,
            include_earnings=include_earnings,
            report_name=report_name,
            out_dir=out_dir,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['candidate_count'] = len(self.candidates)
        return payload
