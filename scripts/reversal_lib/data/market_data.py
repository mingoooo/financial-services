from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from .cache import load_cache, save_cache
from ..models import Candle

API_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d&includePrePost=false&events=div%2Csplits'
USER_AGENT = 'Mozilla/5.0 (compatible; bullish-reversal-scanner/1.0)'
TIMEOUT = 20
YAHOO_COOKIE_JAR = CookieJar()
YAHOO_OPENER = build_opener(HTTPCookieProcessor(YAHOO_COOKIE_JAR))


def log(message: str) -> None:
    print(f'[scan] {message}', file=sys.stderr)


def warm_yahoo_session() -> None:
    warm_url = 'https://finance.yahoo.com/quote/SPY/history'
    request = Request(warm_url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
    try:
        with YAHOO_OPENER.open(request, timeout=TIMEOUT) as response:
            response.read(1)
    except Exception:
        return


def fetch_json(url: str):
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8'})
    opener = YAHOO_OPENER if 'finance.yahoo.com' in url or 'query1.finance.yahoo.com' in url else None
    with (opener.open(request, timeout=TIMEOUT) if opener else urlopen(request, timeout=TIMEOUT)) as response:
        payload = response.read().decode('utf-8')
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def fetch_candles(symbol: str, max_age_seconds: int | None = None, range_str: str = '5y') -> list[Candle]:
    cache_age = max_age_seconds if max_age_seconds is not None else 60 * 60 * 24
    cache_key = f'{symbol}_{range_str}'
    cached = load_cache('candles', cache_key, cache_age)
    if cached:
        return [Candle(**item) for item in cached]

    warm_yahoo_session()
    url = API_URL.format(symbol=symbol, range=range_str)
    payload = fetch_json(url)
    result = payload['chart']['result'][0]
    timestamps = result.get('timestamp') or []
    quote = result['indicators']['quote'][0]
    candles: list[Candle] = []
    for idx, ts in enumerate(timestamps):
        open_ = quote['open'][idx]
        high = quote['high'][idx]
        low = quote['low'][idx]
        close = quote['close'][idx]
        volume = quote['volume'][idx]
        if None in (open_, high, low, close, volume):
            continue
        candles.append(Candle(ts=ts, open=open_, high=high, low=low, close=close, volume=volume))
    save_cache('candles', cache_key, [asdict(candle) for candle in candles])
    return candles
