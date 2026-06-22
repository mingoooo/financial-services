from __future__ import annotations

import re
from urllib.error import HTTPError

from .cache import load_cache, save_cache
from .market_data import fetch_json
from pathlib import Path

WIKI_SP500 = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
NASDAQ_LIST = 'https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt'
OTHER_LIST = 'https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt'
DEFAULT_SYMBOLS_FILE = Path('scripts/high_liquidity_us_symbols.txt')
ETF_UNIVERSE_FILE = Path('scripts/etf_universe.json')
SP500_FALLBACK_FILE = Path('scripts/sp500_symbols.txt')
BAD_SUFFIXES = ('-W', '-U', '-R', '-RT', 'WS', 'WT')


def fetch_default_symbols() -> list[str]:
    return [line.strip().upper() for line in DEFAULT_SYMBOLS_FILE.read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')]


def fetch_sp500_symbols() -> list[str]:
    cached = load_cache('sp500', 'symbols', 60 * 60 * 24)
    if cached:
        return cached
    try:
        html = fetch_json(WIKI_SP500)
    except Exception:
        if SP500_FALLBACK_FILE.exists():
            return [line.strip().upper() for line in SP500_FALLBACK_FILE.read_text(encoding='utf-8').splitlines() if line.strip()]
        raise
    # compatibility with legacy fetch_json behavior isn't needed here; support raw string fallback
    if isinstance(html, dict):
        raise RuntimeError('Unexpected JSON response for SP500 source')
    matches = re.findall(r'<td>([A-Z.]+)</td>', html)
    symbols = [symbol.replace('.', '-') for symbol in matches]
    if symbols:
        save_cache('sp500', 'symbols', symbols)
        return symbols
    if SP500_FALLBACK_FILE.exists():
        return [line.strip().upper() for line in SP500_FALLBACK_FILE.read_text(encoding='utf-8').splitlines() if line.strip()]
    raise RuntimeError('Unable to resolve S&P 500 symbols')


def is_supported_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    if any(upper.endswith(suffix) for suffix in BAD_SUFFIXES):
        return False
    return upper.isascii() and upper.replace('-', '').isalpha()


def fetch_us_symbols(include_etfs: bool = True) -> list[str]:
    cache_key = f'us_symbols_{int(include_etfs)}'
    cached = load_cache('universe', cache_key, 60 * 60 * 24)
    if cached:
        return cached
    symbols: list[str] = []
    seen: set[str] = set()
    for url in (NASDAQ_LIST, OTHER_LIST):
        try:
            payload = fetch_json(url)
        except HTTPError:
            continue
        if isinstance(payload, dict):
            raise RuntimeError('Unexpected JSON response for Nasdaq symbol source')
        lines = str(payload).splitlines()
        for line in lines[1:]:
            if 'File Creation Time' in line:
                continue
            parts = line.split('|')
            if len(parts) < 2:
                continue
            symbol = parts[0].strip().upper()
            if not symbol or not is_supported_symbol(symbol):
                continue
            if not include_etfs:
                etf_flag = parts[5].strip().upper() if len(parts) > 5 else 'N'
                if etf_flag == 'Y':
                    continue
            if symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        symbols = fetch_default_symbols()
    save_cache('universe', cache_key, symbols)
    return symbols


def load_etf_universe(groups: list[str] | None = None) -> list[str]:
    payload = fetch_json(str(ETF_UNIVERSE_FILE)) if False else None
    data = __import__('json').loads(ETF_UNIVERSE_FILE.read_text(encoding='utf-8'))
    normalized = {group.lower() for group in groups or []}
    symbols: list[str] = []
    seen: set[str] = set()
    for item in data:
        item_groups = {group.lower() for group in item.get('groups', [])}
        if normalized and not (normalized & item_groups):
            continue
        symbol = str(item.get('symbol', '')).upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def resolve_symbols(universe: str, symbols: str | None = None, include_etfs: bool = True) -> list[str]:
    if symbols:
        return [item.strip().upper() for item in symbols.split(',') if item.strip()]
    if universe == 'sp500':
        return fetch_sp500_symbols()
    if universe == 'liquid':
        return fetch_default_symbols()
    return fetch_us_symbols(include_etfs=include_etfs)
