from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class UniverseSnapshot:
    requested_universe: str
    data_source_mode: str
    symbols_considered: int = 0
    symbols_prefiltered: int = 0
    finviz_fallback_used: bool = False
    provider_warnings: list[str] = field(default_factory=list)
    prefilter_rules: list[str] = field(default_factory=list)
    downstream_filter_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class RawCandidate:
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    last_price: float | None = None
    average_volume: float | None = None
    average_dollar_volume: float | None = None
    source_tags: list[str] = field(default_factory=list)


@dataclass
class TrendTemplateResult:
    passes: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    borderline_notes: list[str] = field(default_factory=list)


@dataclass
class VcpDetectionResult:
    detected: bool
    prior_uptrend: bool
    contraction_count: int = 0
    contraction_depths: list[float] = field(default_factory=list)
    base_depth_pct: float | None = None
    pivot_price: float | None = None
    distance_to_pivot_pct: float | None = None
    final_tightness: bool = False
    volume_dry_up: bool = False
    volume_dry_up_quality: float | None = None
    breakout_confirmation: bool = False
    breakout_volume_ratio: float | None = None
    breakout_date: str | None = None
    defects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class BreakoutSignal:
    pattern_type: str
    pattern_variant: str
    detected: bool
    pivot_price: float | None = None
    trigger_date: str | None = None
    distance_to_pivot_pct: float | None = None
    breakout_confirmation: bool = False
    breakout_volume_ratio: float | None = None
    volume_dry_up_quality: float | None = None
    contraction_depths: list[float] = field(default_factory=list)
    base_depth_pct: float | None = None
    support_level: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ScoredCandidate:
    symbol: str
    company_name: str | None
    sector: str | None
    industry: str | None
    last_price: float | None
    trend_template: TrendTemplateResult
    vcp: VcpDetectionResult
    component_scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    grade: str = "Reject"
    setup_tier: str = "Rejected"
    review_priority: str = "暂不优先"
    explanation: list[str] = field(default_factory=list)
    chart_html: str | None = None


@dataclass
class ScanSummary:
    run_timestamp: str
    data_source_mode: str
    universe: UniverseSnapshot
    total_symbols_attempted: int = 0
    successful_histories: int = 0
    failed_symbols: list[dict[str, str]] = field(default_factory=list)
    insufficient_data_symbols: list[str] = field(default_factory=list)
    final_candidates: list[ScoredCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
