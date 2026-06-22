from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reversal_lib.models import BacktestSummary, Signal, TradeRecord


@dataclass
class PatternHit:
    symbol: str
    pattern: str
    candidate_index: int
    candidate_date: str
    confirm_index: int | None = None
    confirm_date: str | None = None
    pattern_strength: str | None = None
    confirmation_reason: str | None = None
    score: float | None = None
    score_detail: str | None = None


@dataclass
class IndicatorContext:
    trend_context: str | None = None
    location_context: str | None = None
    sma_cross_context: str | None = None
    rsi_value: float | None = None
    above_sma200: bool | None = None
    macd_context: str | None = None


@dataclass
class SignalCandidate:
    hit: PatternHit
    side: str
    confirm_close: float
    planned_entry_price: float
    stop_loss: float
    first_target: float
    second_target: float
    confirm_volume: float
    avg_volume_20: float
    avg_dollar_volume_20: float
    indicator_context: IndicatorContext | None = None
    entry_mode: str = "close"
    market_cap: float | None = None
    structural_r_multiple: float | None = None


@dataclass
class TradePlan:
    signal: SignalCandidate
    entry_date: str
    entry_price: float
    stop_loss: float
    target_price: float
    position_size: float | None = None
    notes: str | None = None


@dataclass
class BacktestResult:
    signals: list[SignalCandidate | Signal] = field(default_factory=list)
    trade_plans: list[TradePlan] = field(default_factory=list)
    trades: list[TradeRecord] = field(default_factory=list)
    summary: BacktestSummary | dict[str, Any] = field(default_factory=dict)
