from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from .models import Candle, PrefilterMeta

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d&includePrePost=false&events=div%2Csplits"
WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ_LIST = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LIST = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
USER_AGENT = "Mozilla/5.0 (compatible; bullish-reversal-scanner/1.0)"
TIMEOUT = 20
CACHE_DIR = Path(".cache/bullish-reversal-scanner")
DEFAULT_SYMBOLS_FILE = Path("scripts/high_liquidity_us_symbols.txt")
ETF_UNIVERSE_FILE = Path("scripts/etf_universe.json")
BAD_SUFFIXES = ("-W", "-U", "-R", "-RT", "WS", "WT")
NO_CACHE = False
YAHOO_COOKIE_JAR = CookieJar()
YAHOO_OPENER = build_opener(HTTPCookieProcessor(YAHOO_COOKIE_JAR))

def log(message: str) -> None:
    print(f"[scan] {message}", file=sys.stderr)



def cache_path(kind: str, key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{kind}_{key.replace('/', '_')}.json"



def load_cache(kind: str, key: str, max_age_seconds: int):
    if NO_CACHE:
        return None
    path = cache_path(kind, key)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None



def save_cache(kind: str, key: str, payload) -> None:
    if NO_CACHE:
        return
    cache_path(kind, key).write_text(json.dumps(payload), encoding="utf-8")



def warm_yahoo_session() -> None:
    warm_url = "https://finance.yahoo.com/quote/AAPL"
    req = Request(warm_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    })
    with YAHOO_OPENER.open(req, timeout=TIMEOUT) as resp:
        resp.read(256)



def fetch_json(url: str) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://finance.yahoo.com/",
        "Origin": "https://finance.yahoo.com",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    req = Request(url, headers=headers)
    try:
        with YAHOO_OPENER.open(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403:
            warm_yahoo_session()
            req_retry = Request(url, headers=headers)
            with YAHOO_OPENER.open(req_retry, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise



def fetch_default_symbols() -> list[str]:
    if DEFAULT_SYMBOLS_FILE.exists():
        return [line.strip().upper() for line in DEFAULT_SYMBOLS_FILE.read_text().splitlines() if line.strip()]
    return []



def fetch_sp500_symbols() -> list[str]:
    cached = load_cache("universe", "sp500", 60 * 60 * 12)
    if cached:
        return cached
    req = Request(WIKI_SP500, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    import re
    match = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', html, flags=re.S | re.I)
    if not match:
        raise RuntimeError("Could not find S&P 500 constituents table")
    rows = re.findall(r'<tr>(.*?)</tr>', match.group(1), flags=re.S | re.I)
    symbols: list[str] = []
    for row in rows[1:]:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, flags=re.S | re.I)
        if not cells:
            continue
        raw = re.sub(r'<.*?>', '', cells[0])
        symbol = raw.strip().replace('.', '-')
        if symbol:
            symbols.append(symbol)
    save_cache("universe", "sp500", symbols)
    return symbols



def fetch_us_symbols(include_etfs: bool = True) -> list[str]:
    cache_key = f"us_{'with_etf' if include_etfs else 'no_etf'}"
    cached = load_cache("universe", cache_key, 60 * 60 * 12)
    if cached:
        return cached
    symbols: set[str] = set()
    req = Request(NASDAQ_LIST, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol = parts[0].strip().replace('.', '-')
        is_etf = parts[6].strip().upper() == "Y"
        if not symbol or "$" in symbol or symbol == "Symbol":
            continue
        if is_etf and not include_etfs:
            continue
        symbols.add(symbol)
    req = Request(OTHER_LIST, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    for line in lines[1:]:
        if not line or line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol = parts[0].strip().replace('.', '-')
        if not symbol or "$" in symbol or symbol == "ACT Symbol":
            continue
        is_etf = parts[6].strip().upper() == "Y"
        if is_etf and not include_etfs:
            continue
        symbols.add(symbol)
    result = sorted(symbols)
    save_cache("universe", cache_key, result)
    return result



def is_supported_symbol(symbol: str) -> bool:
    if not symbol or symbol.endswith(BAD_SUFFIXES):
        return False
    if any(ch in symbol for ch in ["^", "/", "="]):
        return False
    return True



def finviz_market_cap_filter(min_market_cap: float) -> str | None:
    if min_market_cap >= 200_000_000_000:
        return "+Mega (over $200bln)"
    if min_market_cap >= 10_000_000_000:
        return "+Large (over $10bln)"
    if min_market_cap >= 2_000_000_000:
        return "+Mid (over $2bln)"
    if min_market_cap >= 300_000_000:
        return "+Small (over $300mln)"
    return None



def finviz_avg_volume_filter(min_avg_volume: float) -> str | None:
    if min_avg_volume >= 10_000_000:
        return "Over 10M"
    if min_avg_volume >= 5_000_000:
        return "Over 5M"
    if min_avg_volume >= 2_000_000:
        return "Over 2M"
    if min_avg_volume >= 1_000_000:
        return "Over 1M"
    if min_avg_volume >= 750_000:
        return "Over 750K"
    if min_avg_volume >= 500_000:
        return "Over 500K"
    return None



def finviz_price_filter(min_price: float) -> str | None:
    if min_price >= 50:
        return "Over $50"
    if min_price >= 20:
        return "Over $20"
    if min_price >= 10:
        return "Over $10"
    if min_price >= 5:
        return "Over $5"
    if min_price >= 1:
        return "Over $1"
    return None



def _fetch_finviz_prefilter(args, extra_filters: dict[str, str] | None = None, cache_suffix: str = 'stocks') -> list[PrefilterMeta]:
    from finvizfinance.screener.overview import Overview

    cache_key = f"finviz_{cache_suffix}_{args.universe}_{int(args.include_etfs)}_{int(args.min_market_cap)}_{int(args.min_price)}_{int(args.min_avg_volume)}"
    cached = load_cache("prefilter", cache_key, 60 * 60 * 6)
    if cached:
        return [PrefilterMeta(**item) for item in cached]

    filters: dict[str, str] = {}
    market_cap_filter = finviz_market_cap_filter(args.min_market_cap)
    avg_volume_filter = finviz_avg_volume_filter(args.min_avg_volume)
    price_filter = finviz_price_filter(args.min_price)
    if market_cap_filter:
        filters["Market Cap."] = market_cap_filter
    if avg_volume_filter:
        filters["Average Volume"] = avg_volume_filter
    if price_filter:
        filters["Price"] = price_filter
    if extra_filters:
        filters.update(extra_filters)

    filters["Exchange"] = "Any"
    log(f"starting Finviz prefilter({cache_suffix}) with filters={filters}")
    overview = Overview()
    if filters:
        overview.set_filter(filters_dict=filters)
    df = overview.screener_view()
    metas: list[PrefilterMeta] = []
    seen: set[str] = set()
    for row in df.to_dict(orient="records"):
        symbol = str(row.get("Ticker") or "").upper().replace('.', '-')
        if not is_supported_symbol(symbol) or symbol in seen:
            continue
        price = float(row.get("Price")) if row.get("Price") is not None else None
        volume = float(row.get("Volume")) if row.get("Volume") is not None else None
        market_cap = float(row.get("Market Cap")) if row.get("Market Cap") is not None else None
        meta = PrefilterMeta(
            symbol=symbol,
            name=row.get("Company"),
            price=price,
            volume=volume,
            average_volume=volume,
            market_cap=market_cap,
        )
        if meta.volume is not None and meta.volume < args.min_last_volume:
            continue
        seen.add(symbol)
        metas.append(meta)
    save_cache("prefilter", cache_key, [asdict(m) for m in metas])
    return metas


def fetch_finviz_stock_prefilter(args) -> list[PrefilterMeta]:
    return _fetch_finviz_prefilter(args, extra_filters={"Industry": "Stocks only (ex-Funds)"}, cache_suffix='stocks')


def fetch_finviz_etf_prefilter(args) -> list[PrefilterMeta]:
    return _fetch_finviz_prefilter(args, extra_filters={"Industry": "Exchange Traded Fund"}, cache_suffix='etf')


def fetch_finviz_prefilter(args: argparse.Namespace) -> list[PrefilterMeta]:
    return fetch_finviz_stock_prefilter(args)


def fetch_candles(symbol: str, max_age_seconds: int | None = None, range_str: str = "5y") -> list[Candle]:
    cache_key = f"{symbol}_{range_str}"
    if max_age_seconds is None:
        cached = load_cache("ohlcv", cache_key, 10**12)
    else:
        cached = load_cache("ohlcv", cache_key, max_age_seconds)
    if cached:
        return [Candle(**item) for item in cached]
    data = fetch_json(API_URL.format(symbol=symbol, range=range_str))
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    candles: list[Candle] = []
    for idx, ts in enumerate(timestamps):
        o = quote["open"][idx]
        h = quote["high"][idx]
        l = quote["low"][idx]
        c = quote["close"][idx]
        v = quote["volume"][idx]
        if None in (o, h, l, c, v):
            continue
        candles.append(Candle(ts=ts, open=float(o), high=float(h), low=float(l), close=float(c), volume=float(v)))
    save_cache("ohlcv", cache_key, [asdict(c) for c in candles])
    return candles



def resolve_symbols(universe: str, symbols: str | None = None, include_etfs: bool = True) -> list[str]:
    if symbols:
        return [item.strip().upper() for item in symbols.split(',') if item.strip()]
    if universe == "sp500":
        return fetch_sp500_symbols()
    if universe == "liquid":
        return fetch_default_symbols()
    return fetch_us_symbols(include_etfs=include_etfs)


def load_etf_universe(groups: list[str] | None = None) -> list[str]:
    if not ETF_UNIVERSE_FILE.exists():
        return []
    payload = json.loads(ETF_UNIVERSE_FILE.read_text())
    selected_groups = groups or ['core', 'theme', 'manual_exceptions']
    symbols: list[str] = []
    seen: set[str] = set()
    for group in selected_groups:
        for symbol in payload.get(group, []):
            normalized = str(symbol).strip().upper()
            if normalized and normalized not in seen:
                seen.add(normalized)
                symbols.append(normalized)
    return symbols


def resolve_etf_symbols(min_price: float = 1.0, min_last_volume: float = 50_000, groups: list[str] | None = None, range_str: str = '5y') -> list[PrefilterMeta]:
    symbols = load_etf_universe(groups)
    metas: list[PrefilterMeta] = []
    for symbol in symbols:
        try:
            candles = fetch_candles(symbol, range_str=range_str)
        except Exception:
            continue
        if not candles:
            continue
        last = candles[-1]
        avg_volume = sum(c.volume for c in candles[-20:]) / min(len(candles), 20)
        if last.close < min_price or last.volume < min_last_volume:
            continue
        metas.append(PrefilterMeta(
            symbol=symbol,
            name=symbol,
            price=last.close,
            volume=last.volume,
            average_volume=avg_volume,
            market_cap=None,
        ))
    return metas


def _is_probable_etf(meta: PrefilterMeta) -> bool:
    symbol = (meta.symbol or '').upper()
    name = (meta.name or '').lower()

    explicit_symbol_allowlist = {
        'SPY', 'QQQ', 'GLD', 'DIA', 'IWM', 'IVV', 'VOO', 'VTI', 'VEA', 'VWO', 'XLK', 'XLF', 'XLE', 'XLV',
        'TLT', 'IEF', 'HYG', 'LQD', 'SLV', 'USO', 'XBI', 'SMH', 'SOXX', 'ARKK', 'KWEB', 'EEM', 'EWJ',
        'GDX', 'GDXJ', 'XLP', 'XLY', 'XLI', 'XLB', 'XLU', 'XLC', 'VNQ', 'IYR', 'DBC', 'UUP', 'FXI',
    }
    if symbol in explicit_symbol_allowlist:
        return True

    include_keywords = [
        ' etf', ' etn', ' exchange traded fund', ' index fund', ' closed-end fund', ' exchange-traded fund',
        'ishares', ' spdr', 'vanguard', 'invesco', 'direxion', 'xtrackers', 'proshares', 'global x',
        ' pimco ', 'nuveen ', 'sprott ', 'etf trust', 'commodity trust', 'income fund', 'opportunities fund',
    ]
    exclude_keywords = [
        'realty trust', 'property trust', 'mortgage trust', 'hotel trust', 'healthcare trust', 'storage trust',
        'industrial realty trust', 'residential trust', 'office trust', 'holdings inc', 'group inc', 'therapeutics',
        'technologies', 'energy inc', 'resources inc', 'bank corp', 'financial inc', 'pharma', 'biosciences',
    ]
    if any(keyword in name for keyword in exclude_keywords):
        return False
    return any(keyword in name for keyword in include_keywords)


def filter_prefilter_metas(metas: list[PrefilterMeta], min_last_volume: float = 50_000, top_dollar_volume: int = 0, limit: int = 0) -> list[PrefilterMeta]:
    filtered = [meta for meta in metas if meta.volume is None or meta.volume >= min_last_volume]
    if top_dollar_volume:
        filtered.sort(key=lambda item: ((item.price or 0.0) * (item.volume or 0.0)), reverse=True)
        filtered = filtered[:top_dollar_volume]
    elif limit:
        filtered = filtered[:limit]
    return filtered


def resolve_prefiltered_symbols(universe: str, symbols: str | None = None, include_etfs: bool = True, min_market_cap: float = 2_000_000_000, min_price: float = 1.0, min_avg_volume: float = 750_000, min_last_volume: float = 50_000, top_dollar_volume: int = 0, limit: int = 0, etf_groups: list[str] | None = None, range_str: str = '5y') -> list[PrefilterMeta]:
    if symbols:
        return [PrefilterMeta(symbol=item.strip().upper(), name=None, price=None, volume=None, average_volume=None, market_cap=None) for item in symbols.split(',') if item.strip()]

    class Args:
        pass

    args = Args()
    args.universe = universe
    args.include_etfs = include_etfs
    args.min_market_cap = min_market_cap
    args.min_price = min_price
    args.min_avg_volume = min_avg_volume
    args.min_last_volume = min_last_volume

    if universe == 'liquid':
        return [PrefilterMeta(symbol=s, name=None, price=None, volume=None, average_volume=None, market_cap=None) for s in fetch_default_symbols() if is_supported_symbol(s)]

    if universe in {'us', 'sp500'}:
        stock_prefilter = fetch_finviz_stock_prefilter(args)
        if universe == 'sp500':
            sp500_set = set(fetch_sp500_symbols())
            stock_prefilter = [item for item in stock_prefilter if item.symbol in sp500_set]
        merged = list(stock_prefilter)
        if include_etfs:
            etf_prefilter = resolve_etf_symbols(min_price=min_price, min_last_volume=min_last_volume, groups=etf_groups, range_str=range_str)
            seen = {item.symbol for item in merged}
            merged.extend(item for item in etf_prefilter if item.symbol not in seen)
        return filter_prefilter_metas(merged, min_last_volume=min_last_volume, top_dollar_volume=top_dollar_volume, limit=limit)

    return []
