from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UniverseRequest:
    universe: str
    limit: int | None = None
    as_of_date: str | None = None
    symbols: list[str] = field(default_factory=list)
    min_price: float | None = None
    min_avg_volume: float | None = None
    min_last_volume: float | None = None
    min_market_cap: float | None = None
    include_etfs: bool | None = None
    etf_groups: list[str] = field(default_factory=list)


@dataclass
class SymbolBatchRequest:
    symbols: list[str]
    as_of_date: str | None = None
