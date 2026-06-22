from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PrefilterMeta:
    symbol: str
    name: str | None
    price: float | None
    volume: float | None
    average_volume: float | None
    market_cap: float | None


@dataclass
class ScanResult:
    symbol: str
    pattern: str
    candidate_date: str
    confirm_date: str
    confirm_close: float
    stop_loss: float
    first_target: float
    second_target: float
    confirm_volume: float
    avg_volume_20: float
    avg_dollar_volume_20: float
    market_cap: float | None
    confidence: str
    pattern_strength: str | None = None
    confirmation_reason: str | None = None
    score: float | None = None
    score_detail: str | None = None
    side: str | None = None
    chart_svg: str | None = None


@dataclass
class Signal:
    symbol: str
    side: str
    pattern: str
    candidate_index: int
    confirm_index: int
    candidate_date: str
    confirm_date: str
    confirm_close: float
    planned_entry_price: float
    entry_mode: str
    stop_loss: float
    first_target: float
    second_target: float
    confirm_volume: float
    avg_volume_20: float
    avg_dollar_volume_20: float
    market_cap: float | None
    pattern_strength: str | None
    confirmation_reason: str | None
    score: float | None
    score_detail: str | None
    structural_r_multiple: float | None = None
    trend_context: str | None = None
    location_context: str | None = None
    sma_cross_context: str | None = None
    rsi_value: float | None = None
    above_sma200: bool | None = None
    macd_context: str | None = None


@dataclass
class TradeRecord:
    symbol: str
    side: str
    pattern: str
    candidate_date: str
    confirm_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    stop_loss: float
    target_price: float
    exit_reason: str
    pnl: float
    return_pct: float
    score: float | None = None


@dataclass
class BacktestSummary:
    symbols_total: int
    symbols_processed: int
    symbols_failed: int
    total_trades: int
    win_rate: float
    average_return_pct: float
    median_return_pct: float
    total_pnl: float
    max_drawdown_pct: float
    profit_factor: float


from reversal_lib.domain.models import (  # noqa: E402
    BacktestResult,
    IndicatorContext,
    PatternHit,
    SignalCandidate,
    TradePlan,
)
from reversal_lib.domain.requests import (  # noqa: E402
    SymbolBatchRequest,
    UniverseRequest,
)

__all__ = [
    "BacktestResult",
    "BacktestSummary",
    "Candle",
    "IndicatorContext",
    "PatternHit",
    "PrefilterMeta",
    "ScanResult",
    "Signal",
    "SignalCandidate",
    "SymbolBatchRequest",
    "TradePlan",
    "TradeRecord",
    "UniverseRequest",
]
