from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from .cache import load_cache, save_cache
from .market_data import fetch_candles, log
from .universe import fetch_sp500_symbols, load_etf_universe, resolve_symbols
from ..models import PrefilterMeta, UniverseRequest

FINVIZ_PAGE_WORKERS = 3


def finviz_market_cap_filter(min_market_cap: float) -> str | None:
    if min_market_cap <= 0:
        return None
    if min_market_cap >= 10_000_000_000:
        return 'mega'
    if min_market_cap >= 2_000_000_000:
        return 'large'
    if min_market_cap >= 300_000_000:
        return 'mid'
    if min_market_cap >= 50_000_000:
        return 'small'
    return None


def finviz_avg_volume_filter(min_avg_volume: float) -> str | None:
    if min_avg_volume >= 2_000_000:
        return 'o2000'
    if min_avg_volume >= 1_000_000:
        return 'o1000'
    if min_avg_volume >= 750_000:
        return 'o750'
    if min_avg_volume >= 500_000:
        return 'o500'
    if min_avg_volume >= 200_000:
        return 'o200'
    return None


def finviz_price_filter(min_price: float) -> str | None:
    if min_price >= 50:
        return 'o50'
    if min_price >= 20:
        return 'o20'
    if min_price >= 10:
        return 'o10'
    if min_price >= 5:
        return 'o5'
    if min_price >= 1:
        return 'o1'
    return None


def _make_finviz_overview(filters: dict[str, str]):
    import finvizfinance.screener.overview as overview_mod

    screener = overview_mod.Overview()
    screener.set_filter(filters_dict=filters)
    return screener


def _fetch_finviz_page(task: tuple[dict[str, str], int]):
    filters, offset = task
    screener = _make_finviz_overview(filters)
    return screener.screener_view(limit=20, verbose=0, start=offset)


def _fetch_finviz_overview_df(filters: dict[str, str]):
    tasks = [(filters, offset) for offset in range(1, 81, 20)]
    with ThreadPoolExecutor(max_workers=FINVIZ_PAGE_WORKERS) as executor:
        pages = list(executor.map(_fetch_finviz_page, tasks))
    import pandas as pd

    return pd.concat([page for page in pages if page is not None], ignore_index=True) if pages else pd.DataFrame()


def _fetch_finviz_prefilter(args, extra_filters: dict[str, str] | None = None, cache_suffix: str = 'stocks') -> list[PrefilterMeta]:
    filters = {'Country': 'USA'}
    market_cap_filter = finviz_market_cap_filter(args.min_market_cap)
    avg_volume_filter = finviz_avg_volume_filter(args.min_avg_volume)
    price_filter = finviz_price_filter(args.min_price)
    if market_cap_filter:
        filters['Market Cap.'] = market_cap_filter
    if avg_volume_filter:
        filters['Average Volume'] = avg_volume_filter
    if price_filter:
        filters['Price'] = price_filter
    if extra_filters:
        filters.update(extra_filters)
    cache_key = f"{cache_suffix}_{args.min_market_cap}_{args.min_avg_volume}_{args.min_price}"
    cached = load_cache('prefilter', cache_key, 60 * 60 * 6)
    if cached:
        return [PrefilterMeta(**item) for item in cached]
    log(f'starting Finviz prefilter({cache_suffix}) with filters={filters}')
    df = _fetch_finviz_overview_df(filters)
    metas = [
        PrefilterMeta(
            symbol=row['Ticker'],
            name=row.get('Company'),
            price=row.get('Price'),
            volume=row.get('Volume'),
            average_volume=row.get('Average Volume'),
            market_cap=row.get('Market Cap'),
        )
        for _, row in df.iterrows()
    ]
    save_cache('prefilter', cache_key, [asdict(m) for m in metas])
    return metas


def fetch_finviz_stock_prefilter(args) -> list[PrefilterMeta]:
    return _fetch_finviz_prefilter(args, extra_filters={'Industry': 'Stocks only (ex-Funds)'}, cache_suffix='stocks')


def fetch_finviz_etf_prefilter(args) -> list[PrefilterMeta]:
    return _fetch_finviz_prefilter(args, extra_filters={'Industry': 'Exchange Traded Fund'}, cache_suffix='etf')


def fetch_finviz_prefilter(args: argparse.Namespace) -> list[PrefilterMeta]:
    return fetch_finviz_stock_prefilter(args)


def _is_probable_etf(meta: PrefilterMeta) -> bool:
    return bool(meta.name and 'ETF' in meta.name.upper())


def filter_prefilter_metas(metas: list[PrefilterMeta], min_last_volume: float = 50_000, top_dollar_volume: int = 0, limit: int = 0) -> list[PrefilterMeta]:
    filtered = [meta for meta in metas if (meta.volume or 0) >= min_last_volume]
    if top_dollar_volume > 0:
        filtered.sort(key=lambda item: (item.price or 0) * (item.volume or 0), reverse=True)
        filtered = filtered[:top_dollar_volume]
    if limit > 0:
        filtered = filtered[:limit]
    return filtered


def resolve_etf_symbols(min_price: float = 1.0, min_last_volume: float = 50_000, groups: list[str] | None = None, range_str: str = '5y') -> list[PrefilterMeta]:
    symbols = load_etf_universe(groups)
    metas: list[PrefilterMeta] = []
    for symbol in symbols:
        candles = fetch_candles(symbol, range_str=range_str)
        if not candles:
            continue
        last = candles[-1]
        if last.close < min_price or last.volume < min_last_volume:
            continue
        metas.append(PrefilterMeta(symbol=symbol, name=None, price=last.close, volume=last.volume, average_volume=None, market_cap=None))
    return metas


def fallback_prefilter_from_default_symbols(args, universe: str, include_etfs: bool, range_str: str, etf_groups: list[str] | None = None) -> list[PrefilterMeta]:
    metas: list[PrefilterMeta] = []
    explicit_symbols = ','.join(args.symbols) if getattr(args, 'symbols', None) else None
    for symbol in resolve_symbols(universe, symbols=explicit_symbols, include_etfs=False):
        candles = fetch_candles(symbol, range_str=range_str)
        if not candles:
            continue
        last = candles[-1]
        if last.close < args.min_price or last.volume < args.min_last_volume:
            continue
        metas.append(PrefilterMeta(symbol=symbol, name=None, price=last.close, volume=last.volume, average_volume=None, market_cap=None))
    if include_etfs and universe != 'sp500':
        seen = {item.symbol for item in metas}
        etf_prefilter = resolve_etf_symbols(min_price=args.min_price, min_last_volume=args.min_last_volume, groups=etf_groups, range_str=range_str)
        metas.extend(item for item in etf_prefilter if item.symbol not in seen)
    return filter_prefilter_metas(metas, min_last_volume=args.min_last_volume, top_dollar_volume=0, limit=0)


def resolve_prefiltered_symbols(universe: str, symbols: str | None = None, include_etfs: bool = True, min_market_cap: float = 2_000_000_000, min_price: float = 1.0, min_avg_volume: float = 750_000, min_last_volume: float = 50_000, top_dollar_volume: int = 0, limit: int = 0, etf_groups: list[str] | None = None, range_str: str = '5y') -> list[PrefilterMeta]:
    request = UniverseRequest(universe=universe, limit=limit or None, symbols=[item.strip().upper() for item in symbols.split(',')] if symbols else [])
    return resolve_prefiltered_universe(
        request,
        include_etfs=include_etfs,
        min_market_cap=min_market_cap,
        min_price=min_price,
        min_avg_volume=min_avg_volume,
        min_last_volume=min_last_volume,
        top_dollar_volume=top_dollar_volume,
        etf_groups=etf_groups,
        range_str=range_str,
    )


def resolve_prefiltered_universe(
    request: UniverseRequest,
    *,
    include_etfs: bool = True,
    min_market_cap: float = 2_000_000_000,
    min_price: float = 1.0,
    min_avg_volume: float = 750_000,
    min_last_volume: float = 50_000,
    top_dollar_volume: int = 0,
    etf_groups: list[str] | None = None,
    range_str: str = '5y',
) -> list[PrefilterMeta]:
    if request.symbols:
        return [PrefilterMeta(symbol=symbol, name=None, price=None, volume=None, average_volume=None, market_cap=None) for symbol in request.symbols]
    args = argparse.Namespace(
        universe=request.universe,
        symbols=request.symbols,
        min_market_cap=min_market_cap,
        min_price=min_price,
        min_avg_volume=min_avg_volume,
        min_last_volume=min_last_volume,
    )
    if request.universe == 'liquid':
        return fallback_prefilter_from_default_symbols(args, universe=request.universe, include_etfs=include_etfs, range_str=range_str, etf_groups=etf_groups)
    if request.universe in {'us', 'sp500'}:
        try:
            stock_prefilter = fetch_finviz_stock_prefilter(args)
            if request.universe == 'sp500':
                sp500_set = set(fetch_sp500_symbols())
                stock_prefilter = [item for item in stock_prefilter if item.symbol in sp500_set]
            merged = list(stock_prefilter)
            if include_etfs and request.universe != 'sp500':
                seen = {item.symbol for item in merged}
                etf_prefilter = resolve_etf_symbols(min_price=min_price, min_last_volume=min_last_volume, groups=etf_groups, range_str=range_str)
                merged.extend(item for item in etf_prefilter if item.symbol not in seen)
            return filter_prefilter_metas(merged, min_last_volume=min_last_volume, top_dollar_volume=top_dollar_volume, limit=request.limit or 0)
        except Exception:
            fallback = fallback_prefilter_from_default_symbols(args, universe=request.universe, include_etfs=include_etfs, range_str=range_str, etf_groups=etf_groups)
            return filter_prefilter_metas(fallback, min_last_volume=min_last_volume, top_dollar_volume=top_dollar_volume, limit=request.limit or 0)
    return fallback_prefilter_from_default_symbols(args, universe=request.universe, include_etfs=include_etfs, range_str=range_str, etf_groups=etf_groups)
