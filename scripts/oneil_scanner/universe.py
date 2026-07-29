from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.vcp_lib.data_sources import load_json_cache, write_json_cache

NASDAQ_LISTED_URL = 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt'
OTHER_LISTED_URL = 'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt'

_NON_COMMON_STOCK_HINTS = (
    ' warrant',
    ' rights',
    ' unit',
    ' units',
    ' preferred',
    ' depositary',
    ' etf',
    ' etn',
    ' fund',
    ' trust',
    ' notes',
    ' note',
    ' income shares',
    ' contingent value right',
)

_ALLOWED_OTHER_LISTED_EXCHANGES = {'A', 'N', 'P', 'V', 'Z'}
_MARKET_TZ = ZoneInfo('America/New_York')


def _cache_path(cache_dir: str | Path, universe_name: str) -> Path:
    return Path(cache_dir) / 'universe' / f'{universe_name}.json'


def _today_market_date() -> str:
    return datetime.now(_MARKET_TZ).date().isoformat()


def _cache_is_fresh(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    fetched_at = str(payload.get('fetched_at') or '').strip()
    return fetched_at == _today_market_date()


def _fetch_text(url: str, *, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode('utf-8', 'ignore')


def _normalize_symbol(symbol: str) -> str | None:
    normalized = str(symbol or '').strip().upper()
    if not normalized:
        return None
    if normalized in {'FILE CREATION TIME', 'SYMBOL'}:
        return None
    if '$' in normalized or '^' in normalized:
        return None
    normalized = normalized.replace('.', '-').replace('/', '-')
    if normalized.endswith('-WI') or normalized.endswith('-WS') or normalized.endswith('-RT'):
        return None
    if not any(char.isalpha() for char in normalized):
        return None
    return normalized


def _looks_non_common_stock(security_name: str) -> bool:
    text = str(security_name or '').lower()
    return any(hint in text for hint in _NON_COMMON_STOCK_HINTS)


def _parse_pipe_delimited(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text), delimiter='|'))
    if rows and any('file creation time' in str(value).lower() for value in rows[-1].values()):
        rows = rows[:-1]
    return [{str(key).strip(): str(value).strip() for key, value in row.items() if key is not None} for row in rows]


def _is_supported_other_listed_exchange(exchange: str) -> bool:
    return exchange.strip().upper() in _ALLOWED_OTHER_LISTED_EXCHANGES


def _symbols_from_nasdaq_listed(text: str) -> list[str]:
    symbols: list[str] = []
    for row in _parse_pipe_delimited(text):
        if row.get('Test Issue', '').upper() == 'Y':
            continue
        if row.get('ETF', '').upper() == 'Y':
            continue
        if row.get('NextShares', '').upper() == 'Y':
            continue
        if _looks_non_common_stock(row.get('Security Name', '')):
            continue
        symbol = _normalize_symbol(row.get('Symbol', ''))
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def _symbols_from_other_listed(text: str) -> list[str]:
    symbols: list[str] = []
    for row in _parse_pipe_delimited(text):
        if row.get('Test Issue', '').upper() == 'Y':
            continue
        if row.get('ETF', '').upper() == 'Y':
            continue
        if not _is_supported_other_listed_exchange(row.get('Exchange', '')):
            continue
        if _looks_non_common_stock(row.get('Security Name', '')):
            continue
        symbol = _normalize_symbol(row.get('ACT Symbol', ''))
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def fetch_all_us_symbols(*, timeout: int = 30, text_fetcher=None) -> list[str]:
    fetcher = text_fetcher or _fetch_text
    nasdaq_listed = _symbols_from_nasdaq_listed(fetcher(NASDAQ_LISTED_URL, timeout=timeout))
    other_listed = _symbols_from_other_listed(fetcher(OTHER_LISTED_URL, timeout=timeout))
    return sorted(set(nasdaq_listed + other_listed))


def resolve_universe_symbols(
    universe: str,
    *,
    cache_dir: str | Path,
    refresh: bool = False,
    timeout: int = 30,
    text_fetcher=None,
) -> list[str]:
    normalized_universe = universe.strip().lower()
    if normalized_universe != 'all-us':
        return []

    target = _cache_path(cache_dir, normalized_universe)
    if not refresh:
        cached = load_json_cache(target)
        if _cache_is_fresh(cached) and isinstance(cached.get('symbols'), list):
            return [str(symbol).upper() for symbol in cached['symbols'] if str(symbol).strip()]

    symbols = fetch_all_us_symbols(timeout=timeout, text_fetcher=text_fetcher)
    write_json_cache(
        target,
        {
            'universe': normalized_universe,
            'symbol_count': len(symbols),
            'symbols': symbols,
            'fetched_at': _today_market_date(),
            'source': 'nasdaqtrader',
        },
    )
    return symbols


__all__ = ['fetch_all_us_symbols', 'resolve_universe_symbols']
