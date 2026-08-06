from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import math
from typing import Any


STRATEGY_PROFILES = (
    'oneil',
    'minervini_relaxed',
    'minervini_strict',
    'qullamaggie',
)


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
    cache_dir: str = '.cache/oneil-scanner'
    period: str = '1y'
    interval: str = '1d'
    batch_size: int = 25
    timeout: int = 20
    retries: int = 2
    refresh_cache: bool = False
    min_price: float = 10.0
    min_avg_dollar_volume: float = 10_000_000.0
    min_rs_proxy: float = 0.05
    trigger_window_days: int = 5
    strategy_profile: str = 'oneil'

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
    strategy_profile: str = 'oneil'
    include_news: bool = False
    include_earnings: bool = False
    warnings: list[str] = field(default_factory=list)


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
    catalyst_evidence_count: int | None = None
    catalyst_summary: str | None = None
    secondary_signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    symbol_context: SymbolContext | None = None

    def __post_init__(self) -> None:
        if not self.catalyst_type:
            self.catalyst_type = 'unknown'
        if self.catalyst_confidence is None:
            self.catalyst_confidence = 0.0
        if self.catalyst_evidence_count is None:
            self.catalyst_evidence_count = 0 if self.catalyst_type == 'unknown' else 1
        if self.catalyst_summary is None:
            self.catalyst_summary = _default_catalyst_summary(self.catalyst_type)

    def setup_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for note in self.notes:
            if '=' not in note:
                continue
            key, raw_value = note.split('=', 1)
            key = key.strip()
            if not key:
                continue
            metadata[key] = _coerce_setup_metadata_value(raw_value.strip())
        return metadata

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        setup_metadata = self.setup_metadata()
        if setup_metadata:
            payload['setup_metadata'] = setup_metadata
        return payload


def _coerce_setup_metadata_value(value: str) -> Any:
    if value == '':
        return ''
    lowered = value.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    if value.lstrip('-').isdigit():
        return int(value)
    try:
        parsed = float(value)
    except ValueError:
        return value
    if math.isnan(parsed) or math.isinf(parsed):
        return value
    return parsed


def _default_catalyst_summary(catalyst_type: str) -> str:
    if catalyst_type == 'technical_breakout':
        return 'Technical breakout without separate event catalyst requirement'
    if catalyst_type == 'unknown':
        return 'No usable catalyst evidence aligned with the price move'
    label = catalyst_type.replace('_', ' ')
    return f'{label.capitalize()} catalyst'


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
        strategy_profile: str = 'oneil',
        warnings: list[str] | None = None,
    ) -> 'ScanRunSummary':
        return cls(
            run_metadata=RunMetadata(
                run_timestamp=run_timestamp,
                as_of=as_of,
                report_name=report_name,
                out_dir=out_dir,
                strategy_profile=strategy_profile,
                include_news=include_news,
                include_earnings=include_earnings,
                warnings=list(warnings or []),
            ),
            universe=universe,
            symbols=symbols or [],
            limit=limit,
            grouped_candidate_summaries=[],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            'run_metadata': asdict(self.run_metadata),
            'universe': self.universe,
            'symbols': list(self.symbols),
            'limit': self.limit,
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'grouped_candidate_summaries': [group.to_dict() for group in self.grouped_candidate_summaries],
        }
        payload['run_timestamp'] = self.run_metadata.run_timestamp
        payload['as_of'] = self.run_metadata.as_of
        payload['report_name'] = self.run_metadata.report_name
        payload['out_dir'] = self.run_metadata.out_dir
        payload['strategy_profile'] = self.run_metadata.strategy_profile
        payload['include_news'] = self.run_metadata.include_news
        payload['include_earnings'] = self.run_metadata.include_earnings
        payload['warnings'] = list(self.run_metadata.warnings)
        payload['candidate_count'] = len(self.candidates)
        return payload
