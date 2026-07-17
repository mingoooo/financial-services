from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScannerConfig:
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


@dataclass
class RunMetadata:
    run_timestamp: str
    as_of: str | None = None
    report_name: str = 'oneil-setups'
    out_dir: str = 'reports/oneil'
    include_news: bool = False
    include_earnings: bool = False


@dataclass
class SymbolContext:
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    source_tags: list[str] = field(default_factory=list)


@dataclass
class PatternCandidate:
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
    symbol_context: SymbolContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroupedCandidateSummary:
    group_key: str
    label: str
    candidate_count: int = 0
    symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanRunSummary:
    run_metadata: RunMetadata
    universe: str
    symbols: list[str] = field(default_factory=list)
    limit: int | None = None
    candidates: list[PatternCandidate] = field(default_factory=list)
    grouped_candidate_summaries: list[GroupedCandidateSummary] = field(default_factory=list)

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
    ) -> 'ScanRunSummary':
        return cls(
            run_metadata=RunMetadata(
                run_timestamp=run_timestamp,
                as_of=as_of,
                report_name=report_name,
                out_dir=out_dir,
                include_news=include_news,
                include_earnings=include_earnings,
            ),
            universe=universe,
            symbols=symbols or [],
            limit=limit,
            grouped_candidate_summaries=[],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['run_timestamp'] = self.run_metadata.run_timestamp
        payload['as_of'] = self.run_metadata.as_of
        payload['report_name'] = self.run_metadata.report_name
        payload['out_dir'] = self.run_metadata.out_dir
        payload['include_news'] = self.run_metadata.include_news
        payload['include_earnings'] = self.run_metadata.include_earnings
        payload['candidate_count'] = len(self.candidates)
        return payload


ScanConfig = ScannerConfig
SetupCandidate = PatternCandidate
ScanSummary = ScanRunSummary
