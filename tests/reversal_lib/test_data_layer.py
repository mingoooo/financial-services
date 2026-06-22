from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.data import resolve_prefiltered_symbols
from reversal_lib.data.prefilter import filter_prefilter_metas, resolve_prefiltered_universe
from reversal_lib.models import PrefilterMeta, UniverseRequest


def test_filter_prefilter_metas_applies_volume_sort_and_limit() -> None:
    metas = [
        PrefilterMeta(symbol='AAA', name=None, price=10, volume=100_000, average_volume=None, market_cap=None),
        PrefilterMeta(symbol='BBB', name=None, price=30, volume=90_000, average_volume=None, market_cap=None),
        PrefilterMeta(symbol='CCC', name=None, price=5, volume=10_000, average_volume=None, market_cap=None),
    ]
    filtered = filter_prefilter_metas(metas, min_last_volume=50_000, top_dollar_volume=1)
    assert [item.symbol for item in filtered] == ['BBB']


def test_resolve_prefiltered_symbols_uses_universe_request_symbol_override() -> None:
    result = resolve_prefiltered_symbols('sp500', symbols='aapl, msft', include_etfs=False)
    assert [item.symbol for item in result] == ['AAPL', 'MSFT']


def test_resolve_prefiltered_universe_symbol_override_returns_minimal_metas() -> None:
    request = UniverseRequest(universe='us', symbols=['SPY', 'QQQ'])
    result = resolve_prefiltered_universe(request)
    assert [(item.symbol, item.price, item.volume) for item in result] == [('SPY', None, None), ('QQQ', None, None)]
