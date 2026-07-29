#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
from datetime import datetime, timezone
import json
import random
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from http.cookiejar import CookieJar
import urllib.parse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from finvizfinance.screener.overview import Overview
from reversal_lib.models import Candle, PrefilterMeta, ScanResult, UniverseRequest
from reversal_lib.pipeline.scan_pipeline import run_scan
from reversal_lib.presets import apply_strategy_preset, describe_strategy_preset, load_strategy_spec

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d&includePrePost=false&events=div%2Csplits"
WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ_LIST = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LIST = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
USER_AGENT = "Mozilla/5.0 (compatible; bullish-reversal-scanner/1.0)"
TIMEOUT = 20
CACHE_DIR = Path(".cache/bullish-reversal-scanner")
DEFAULT_SYMBOLS_FILE = Path("scripts/high_liquidity_us_symbols.txt")
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


def fetch_finviz_prefilter(args: argparse.Namespace) -> list[PrefilterMeta]:
    cache_key = f"finviz_{args.universe}_{int(args.include_etfs)}_{int(args.min_market_cap)}_{int(args.min_price)}_{int(args.min_avg_volume)}"
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
    if not args.include_etfs:
        filters["Industry"] = "Stocks only (ex-Funds)"

    filters["Exchange"] = "Any"
    log(f"starting Finviz prefilter with filters={filters}")
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


def fetch_candles(symbol: str) -> list[Candle]:
    cached = load_cache("ohlcv", symbol, 60 * 30)
    if cached:
        return [Candle(**item) for item in cached]
    data = fetch_json(API_URL.format(symbol=symbol))
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
    save_cache("ohlcv", symbol, [asdict(c) for c in candles])
    return candles


def is_small_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    body = abs(candle.close - candle.open)
    return rng > 0 and body / rng <= 0.35


def is_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    body_top = max(candle.open, candle.close)
    body_bottom = min(candle.open, candle.close)
    lower_shadow = body_bottom - candle.low
    upper_shadow = candle.high - body_top
    body = body_top - body_bottom
    return lower_shadow >= body * 2 and upper_shadow <= body * 0.5 and body_top >= candle.low + rng * 0.6


def is_inverted_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    body_top = max(candle.open, candle.close)
    body_bottom = min(candle.open, candle.close)
    lower_shadow = body_bottom - candle.low
    upper_shadow = candle.high - body_top
    body = body_top - body_bottom
    return upper_shadow >= body * 2 and lower_shadow <= body * 0.5 and body_bottom <= candle.low + rng * 0.4


def real_body(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def body_top(candle: Candle) -> float:
    return max(candle.open, candle.close)


def body_bottom(candle: Candle) -> float:
    return min(candle.open, candle.close)


def is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def is_long_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng >= 0.55


def is_doji(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng <= 0.1


def is_bullish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bearish(prev_candle)
        and is_bullish(candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and body_top(candle) >= body_top(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_piercing_pattern(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bearish(first)
        and is_long_body(first)
        and is_bullish(second)
        and second.open < first.low + (first.high - first.low) * 0.25
        and second.close > midpoint
        and second.close < first.open
    )


def is_morning_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bearish(first)
        and is_long_body(first)
        and small_second
        and is_bullish(third)
        and third.close > midpoint
    )


def is_shooting_star(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    upper_shadow = candle.high - body_top(candle)
    lower_shadow = body_bottom(candle) - candle.low
    return upper_shadow >= real_body(candle) * 2 and lower_shadow <= max(real_body(candle) * 0.5, rng * 0.1)


def is_hanging_man(candle: Candle) -> bool:
    return is_hammer(candle)


def is_bearish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bullish(prev_candle)
        and is_bearish(candle)
        and body_top(candle) >= body_top(prev_candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_dark_cloud_cover(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bullish(first)
        and is_long_body(first)
        and is_bearish(second)
        and second.open > first.high - (first.high - first.low) * 0.25
        and second.close < midpoint
        and second.close > first.open
    )


def is_evening_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bullish(first)
        and is_long_body(first)
        and small_second
        and is_bearish(third)
        and third.close < midpoint
    )


def is_bullish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bearish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bullish(second)
    )


def is_bearish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bullish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bearish(second)
    )


def has_prior_uptrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] > closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1]) >= 2


def detect_bearish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_shooting_star(candle):
        return "Shooting Star / 流星线", candle.high
    if is_hanging_man(candle):
        return "Hanging Man / 上吊线", candle.high
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bearish_engulfing(prev_candle, candle):
            return "Bearish Engulfing / 看跌吞没", max(prev_candle.high, candle.high)
        if is_dark_cloud_cover(prev_candle, candle):
            return "Dark Cloud Cover / 乌云盖顶", max(prev_candle.high, candle.high)
        if is_bearish_harami(prev_candle, candle):
            return "Bearish Harami / 看跌孕线", max(prev_candle.high, candle.high)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_evening_star(first, second, third):
            return "Evening Star / 黄昏星", max(first.high, second.high, third.high)
    return None, None


def detect_bullish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_hammer(candle):
        return "Hammer / 锤头线", candle.low
    if is_inverted_hammer(candle):
        return "Inverted Hammer / 倒锤头线", candle.low
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bullish_engulfing(prev_candle, candle):
            return "Bullish Engulfing / 看涨吞没", min(prev_candle.low, candle.low)
        if is_piercing_pattern(prev_candle, candle):
            return "Piercing Pattern / 刺透形态", min(prev_candle.low, candle.low)
        if is_bullish_harami(prev_candle, candle):
            return "Bullish Harami / 看涨孕线", min(prev_candle.low, candle.low)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_morning_star(first, second, third):
            return "Morning Star / 启明星", min(first.low, second.low, third.low)
    return None, None


def has_prior_downtrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] < closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] < closes[i - 1]) >= 2


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_signal_score(pattern_strength: str | None, confirm_volume: float, avg_volume_20: float, market_cap: float | None, avg_dollar_volume_20: float) -> tuple[float, str]:
    strength_points = {"strong": 40.0, "medium": 28.0, "standard": 20.0}.get(pattern_strength or "standard", 20.0)
    volume_ratio = (confirm_volume / avg_volume_20) if avg_volume_20 > 0 else 1.0
    if volume_ratio >= 2.0:
        volume_points = 25.0
    elif volume_ratio >= 1.5:
        volume_points = 20.0
    elif volume_ratio >= 1.1:
        volume_points = 14.0
    elif volume_ratio >= 1.0:
        volume_points = 10.0
    else:
        volume_points = 4.0

    if market_cap is None:
        market_cap_points = 6.0
    elif market_cap >= 200_000_000_000:
        market_cap_points = 18.0
    elif market_cap >= 10_000_000_000:
        market_cap_points = 14.0
    elif market_cap >= 2_000_000_000:
        market_cap_points = 10.0
    else:
        market_cap_points = 6.0

    if avg_dollar_volume_20 >= 500_000_000:
        liquidity_points = 17.0
    elif avg_dollar_volume_20 >= 100_000_000:
        liquidity_points = 13.0
    elif avg_dollar_volume_20 >= 25_000_000:
        liquidity_points = 9.0
    else:
        liquidity_points = 5.0

    score = clamp_score(strength_points + volume_points + market_cap_points + liquidity_points)
    detail = f"strength={strength_points:.0f}, volume={volume_points:.0f}, mcap={market_cap_points:.0f}, liquidity={liquidity_points:.0f}"
    return score, detail


def pattern_strength_label(pattern: str, side: str) -> str:
    strong = {
        "Bullish Engulfing / 看涨吞没",
        "Bearish Engulfing / 看跌吞没",
        "Morning Star / 启明星",
        "Evening Star / 黄昏星",
        "Dark Cloud Cover / 乌云盖顶",
        "Piercing Pattern / 刺透形态",
    }
    medium = {
        "Hammer / 锤头线",
        "Inverted Hammer / 倒锤头线",
        "Shooting Star / 流星线",
        "Hanging Man / 上吊线",
        "Bullish Harami / 看涨孕线",
        "Bearish Harami / 看跌孕线",
    }
    if pattern in strong:
        return "strong"
    if pattern in medium:
        return "medium"
    return "standard"


def bullish_confirmation_reason(pattern: str) -> str:
    mapping = {
        "Hammer / 锤头线": "确认日收盘站上候选实体上沿",
        "Inverted Hammer / 倒锤头线": "确认日收盘站上候选实体上沿",
        "Bullish Engulfing / 看涨吞没": "确认日收盘突破候选K线高点",
        "Bullish Harami / 看涨孕线": "确认日收盘突破候选K线高点",
        "Piercing Pattern / 刺透形态": "确认日继续上破候选高点与前阴线关键位",
        "Morning Star / 启明星": "确认日继续强化三K线底部反转",
    }
    return mapping.get(pattern, "确认日满足看涨确认条件")


def bearish_confirmation_reason(pattern: str) -> str:
    mapping = {
        "Shooting Star / 流星线": "确认日收盘跌破候选实体下沿",
        "Hanging Man / 上吊线": "确认日收盘跌破候选实体下沿",
        "Bearish Engulfing / 看跌吞没": "确认日收盘跌破候选K线低点",
        "Bearish Harami / 看跌孕线": "确认日收盘跌破候选K线低点",
        "Dark Cloud Cover / 乌云盖顶": "确认日继续下破候选低点并强化顶部反转",
        "Evening Star / 黄昏星": "确认日继续强化三K线顶部反转",
    }
    return mapping.get(pattern, "确认日满足看跌确认条件")


def bullish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {"Hammer / 锤头线", "Inverted Hammer / 倒锤头线"}:
        return confirm.close > body_top(candidate)
    if pattern in {"Bullish Engulfing / 看涨吞没", "Bullish Harami / 看涨孕线"}:
        return confirm.close > candidate.high
    if pattern == "Piercing Pattern / 刺透形态":
        prev_candle = candles[idx - 1]
        return confirm.close > max(candidate.high, body_top(prev_candle))
    if pattern == "Morning Star / 启明星":
        first = candles[idx - 2]
        return confirm.close > max(candidate.high, body_top(first))
    return confirm.close > body_top(candidate)


def bearish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {"Shooting Star / 流星线", "Hanging Man / 上吊线"}:
        return confirm.close < body_bottom(candidate)
    if pattern in {"Bearish Engulfing / 看跌吞没", "Bearish Harami / 看跌孕线"}:
        return confirm.close < candidate.low
    if pattern == "Dark Cloud Cover / 乌云盖顶":
        prev_candle = candles[idx - 1]
        return confirm.close < min(candidate.low, body_bottom(prev_candle))
    if pattern == "Evening Star / 黄昏星":
        first = candles[idx - 2]
        return confirm.close < min(candidate.low, body_bottom(first))
    return confirm.close < body_bottom(candidate)


def scan_symbol(symbol: str, require_confirm_volume: bool, confirm_volume_multiplier: float = 1.0, market_cap: float | None = None, side: str = "both") -> ScanResult | None:
    candles = fetch_candles(symbol)
    if len(candles) < 25:
        return None
    for idx in range(len(candles) - 2, 3, -1):
        candidate = candles[idx]
        confirm = candles[idx + 1]
        avg_vol20 = statistics.mean(c.volume for c in candles[max(0, idx - 19):idx + 1])
        avg_dollar_volume_20 = statistics.mean(c.close * c.volume for c in candles[max(0, idx - 19):idx + 1])
        scan_sides = [side] if side in {"bullish", "bearish"} else ["bullish", "bearish"]
        for current_side in scan_sides:
            if current_side == "bullish":
                pattern, stop_anchor = detect_bullish_pattern(candles, idx)
                if not pattern or stop_anchor is None:
                    continue
                if not bullish_confirmation_ok(pattern, candles, idx, confirm):
                    continue
                if require_confirm_volume and confirm.volume < avg_vol20 * confirm_volume_multiplier:
                    continue
                risk = confirm.close - stop_anchor
                if risk <= 0:
                    continue
                score, score_detail = compute_signal_score(pattern_strength_label(pattern, current_side), round(confirm.volume, 0), round(avg_vol20, 0), market_cap, round(avg_dollar_volume_20, 0))
                return ScanResult(
                    symbol=symbol,
                    pattern=pattern,
                    candidate_date=time.strftime("%Y-%m-%d", time.gmtime(candidate.ts)),
                    confirm_date=time.strftime("%Y-%m-%d", time.gmtime(confirm.ts)),
                    confirm_close=round(confirm.close, 2),
                    stop_loss=round(stop_anchor, 2),
                    first_target=round(confirm.close + risk, 2),
                    second_target=round(confirm.close + risk * 2, 2),
                    confirm_volume=round(confirm.volume, 0),
                    avg_volume_20=round(avg_vol20, 0),
                    avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                    market_cap=market_cap,
                    confidence="confirmed",
                    pattern_strength=pattern_strength_label(pattern, current_side),
                    confirmation_reason=bullish_confirmation_reason(pattern),
                    score=score,
                    score_detail=score_detail,
                )
            else:
                if not has_prior_uptrend(candles, idx):
                    continue
                pattern, stop_anchor = detect_bearish_pattern(candles, idx)
                if not pattern or stop_anchor is None:
                    continue
                if not bearish_confirmation_ok(pattern, candles, idx, confirm):
                    continue
                if require_confirm_volume and confirm.volume < avg_vol20 * confirm_volume_multiplier:
                    continue
                risk = stop_anchor - confirm.close
                if risk <= 0:
                    continue
                score, score_detail = compute_signal_score(pattern_strength_label(pattern, current_side), round(confirm.volume, 0), round(avg_vol20, 0), market_cap, round(avg_dollar_volume_20, 0))
                return ScanResult(
                    symbol=symbol,
                    pattern=pattern,
                    candidate_date=time.strftime("%Y-%m-%d", time.gmtime(candidate.ts)),
                    confirm_date=time.strftime("%Y-%m-%d", time.gmtime(confirm.ts)),
                    confirm_close=round(confirm.close, 2),
                    stop_loss=round(stop_anchor, 2),
                    first_target=round(confirm.close - risk, 2),
                    second_target=round(confirm.close - risk * 2, 2),
                    confirm_volume=round(confirm.volume, 0),
                    avg_volume_20=round(avg_vol20, 0),
                    avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                    market_cap=market_cap,
                    confidence="confirmed",
                    pattern_strength=pattern_strength_label(pattern, current_side),
                    confirmation_reason=bearish_confirmation_reason(pattern),
                    score=score,
                    score_detail=score_detail,
                )
    return None


def is_transient_scan_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in {403, 408, 409, 425, 429, 500, 502, 503, 504}
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, RuntimeError):
        return True
    return False


def scan_symbol_with_retries(symbol: str, require_confirm_volume: bool, confirm_volume_multiplier: float = 1.0, market_cap: float | None = None, retries: int = 3, side: str = "bullish") -> ScanResult | None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return scan_symbol(symbol, require_confirm_volume, confirm_volume_multiplier, market_cap, side)
        except (URLError, HTTPError, KeyError, IndexError, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            if not is_transient_scan_error(exc):
                break
            backoff = min(1.5 * (2 ** (attempt - 1)), 8.0) + random.uniform(0.0, 0.35)
            log(f"retry {attempt}/{retries-1} for {symbol} after transient error: {exc}; sleeping {backoff:.2f}s")
            time.sleep(backoff)
    if last_exc is not None:
        raise last_exc
    return None


def is_recent_confirm_date(confirm_date: str, max_age_days: int) -> bool:
    if max_age_days <= 0:
        return True
    confirm_dt = datetime.strptime(confirm_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_days = (now.date() - confirm_dt.date()).days
    return 0 <= age_days <= max_age_days


def format_market_cap(value: float | None) -> str:
    if value is None:
        return "-"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value:.0f}"


def simple_moving_average(candles: list[Candle], period: int) -> list[float | None]:
    values: list[float | None] = []
    closes = [c.close for c in candles]
    for idx in range(len(closes)):
        if idx + 1 < period:
            values.append(None)
        else:
            window = closes[idx - period + 1:idx + 1]
            values.append(sum(window) / period)
    return values


def detect_support_resistance_levels(candles: list[Candle], lookback: int = 50) -> tuple[list[float], list[float]]:
    window = candles[-lookback:] if len(candles) > lookback else candles
    if len(window) < 7:
        return [], []
    highs: list[float] = []
    lows: list[float] = []
    for i in range(2, len(window) - 2):
        c = window[i]
        left = window[i-2:i]
        right = window[i+1:i+3]
        if c.high >= max(x.high for x in left + right):
            highs.append(c.high)
        if c.low <= min(x.low for x in left + right):
            lows.append(c.low)

    def dedupe(levels: list[float]) -> list[float]:
        picked: list[float] = []
        for level in sorted(levels):
            if not picked or abs(level - picked[-1]) / max(abs(level), 1.0) > 0.015:
                picked.append(level)
        return picked

    current = window[-1].close
    supports = [lvl for lvl in dedupe(lows) if lvl < current]
    resistances = [lvl for lvl in dedupe(highs) if lvl > current]
    supports = sorted(supports, key=lambda x: abs(current - x))[:2]
    resistances = sorted(resistances, key=lambda x: abs(current - x))[:2]
    return supports, resistances


def build_price_chart_svg(symbol: str, candidate_date: str, confirm_date: str, stop_loss: float | None = None, first_target: float | None = None, second_target: float | None = None, pattern: str | None = None, confirmation_reason: str | None = None, score: float | None = None) -> str:
    candles = fetch_candles(symbol)[-80:]
    if not candles:
        return ""
    width = 980
    height = 420
    pad_left = 56
    pad_right = 128
    pad_top = 20
    pad_bottom = 28
    gap = 18
    volume_height = 92
    plot_width = width - pad_left - pad_right
    price_height = height - pad_top - pad_bottom - volume_height - gap
    volume_top = pad_top + price_height + gap
    volume_bottom = height - pad_bottom

    lows = [c.low for c in candles]
    highs = [c.high for c in candles]
    volumes = [c.volume for c in candles]
    sma_periods = [10, 20, 50, 200]
    sma_colors = {10: "#f59e0b", 20: "#38bdf8", 50: "#a78bfa", 200: "#f472b6"}
    full_candles = fetch_candles(symbol)
    sma_series_full = {period: simple_moving_average(full_candles, period) for period in sma_periods}
    offset = len(full_candles) - len(candles)
    sma_series = {period: series[offset:] for period, series in sma_series_full.items()}
    sma_levels = [value for series in sma_series.values() for value in series if value is not None]
    sma_latest = {period: next((v for v in reversed(series) if v is not None), None) for period, series in sma_series_full.items()}
    supports, resistances = detect_support_resistance_levels(candles)
    overlay_levels = [level for level in [stop_loss, first_target, second_target] if level is not None]
    extra_levels = supports + resistances + overlay_levels + sma_levels
    min_price = min(lows + extra_levels) if extra_levels else min(lows)
    max_price = max(highs + extra_levels) if extra_levels else max(highs)
    price_padding = max((max_price - min_price) * 0.04, max_price * 0.005)
    min_price -= price_padding
    max_price += price_padding
    price_range = max(max_price - min_price, 1e-6)
    max_volume = max(volumes) if volumes else 1

    def y_price(price: float) -> float:
        return pad_top + (max_price - price) / price_range * price_height

    def y_volume(volume: float) -> float:
        return volume_top + (1 - (volume / max(max_volume, 1))) * volume_height

    step = plot_width / max(len(candles), 1)
    candle_width = max(4, min(11, step * 0.72))
    half = candle_width / 2
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append('<rect x="0" y="0" width="100%" height="100%" fill="#0b1020"/>')
    parts.append(f'<rect x="{pad_left}" y="{pad_top}" width="{plot_width}" height="{price_height}" fill="#0f172a" rx="8"/>')
    parts.append(f'<rect x="{pad_left}" y="{volume_top}" width="{plot_width}" height="{volume_height}" fill="#0f172a" rx="8"/>')
    parts.append(f'<rect x="{width-120}" y="{pad_top}" width="104" height="{price_height}" fill="#0b1020" rx="8"/>')

    for level in range(5):
        gy = pad_top + price_height * level / 4
        price_label = max_price - price_range * level / 4
        parts.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width-pad_right}" y2="{gy:.1f}" stroke="#22314b" stroke-width="1"/>')
        parts.append(f'<text x="10" y="{gy+4:.1f}" fill="#94a3b8" font-size="11">{price_label:.2f}</text>')

    sr_specs = []
    for idx, level in enumerate(sorted(supports, reverse=True), start=1):
        sr_specs.append((f"S{idx}", level, "#22c55e"))
    for idx, level in enumerate(sorted(resistances), start=1):
        sr_specs.append((f"R{idx}", level, "#f87171"))
    for label, level, color in sr_specs:
        sy = y_price(level)
        parts.append(f'<line x1="{pad_left}" y1="{sy:.1f}" x2="{width-pad_right}" y2="{sy:.1f}" stroke="{color}" stroke-dasharray="6 4" stroke-width="1.2" opacity="0.9"/>')

    trade_specs = []
    if stop_loss is not None:
        trade_specs.append(("Stop", stop_loss, "#f59e0b"))
    if first_target is not None:
        trade_specs.append(("T1", first_target, "#38bdf8"))
    if second_target is not None:
        trade_specs.append(("T2", second_target, "#a78bfa"))
    for label, level, color in trade_specs:
        ty = y_price(level)
        parts.append(f'<line x1="{pad_left}" y1="{ty:.1f}" x2="{width-pad_right}" y2="{ty:.1f}" stroke="{color}" stroke-dasharray="3 3" stroke-width="1.1" opacity="0.95"/>')

    for level in range(3):
        gy = volume_top + volume_height * level / 2
        vol_label = max_volume * (1 - level / 2)
        parts.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width-pad_right}" y2="{gy:.1f}" stroke="#1f2b40" stroke-width="1"/>')
        parts.append(f'<text x="10" y="{gy+4:.1f}" fill="#64748b" font-size="10">{int(vol_label):,}</text>')

    sma_label_specs = []
    for period in sma_periods:
        series = sma_series[period]
        points = []
        last_visible_value = None
        for i, value in enumerate(series):
            if value is None:
                continue
            x = pad_left + step * i + step / 2
            points.append(f"{x:.1f},{y_price(value):.1f}")
            last_visible_value = value
        if len(points) >= 2:
            parts.append(f'<polyline fill="none" stroke="{sma_colors[period]}" stroke-width="1.4" points="{" ".join(points)}" opacity="0.95"/>')
        latest = sma_latest.get(period)
        if latest is not None:
            sma_label_specs.append((period, latest, y_price(last_visible_value if last_visible_value is not None else latest), sma_colors[period]))

    sma_label_specs.sort(key=lambda item: item[2])
    adjusted_specs = []
    min_gap = 18.0
    last_y = None
    for period, latest, base_y, color in sma_label_specs:
        y_pos = base_y
        if last_y is not None and y_pos - last_y < min_gap:
            y_pos = last_y + min_gap
        y_pos = min(max(y_pos, pad_top + 10), pad_top + price_height - 10)
        adjusted_specs.append((period, latest, y_pos, color))
        last_y = y_pos

    last_price = candles[-1].close
    current_specs = [("Last", last_price, y_price(last_price), "#e5eefc")]

    resistance_specs = [(label, level, y_price(level), color) for label, level, color in sr_specs if label.startswith("R")]
    support_specs = [(label, level, y_price(level), color) for label, level, color in sr_specs if label.startswith("S")]
    trade_label_specs = [(label, level, y_price(level), color) for label, level, color in trade_specs]
    sma_label_specs_sidebar = [(f"SMA{period}", latest, y_pos, color) for period, latest, y_pos, color in adjusted_specs]

    resistance_specs.sort(key=lambda item: item[1], reverse=True)
    support_specs.sort(key=lambda item: item[1], reverse=True)
    sma_label_specs_sidebar.sort(key=lambda item: item[1], reverse=True)
    trade_label_specs.sort(key=lambda item: item[1], reverse=True)

    right_label_specs = resistance_specs + sma_label_specs_sidebar + current_specs + support_specs + trade_label_specs

    right_label_specs.sort(key=lambda item: item[2])
    packed_specs = []
    min_gap = 18.0
    last_y = None
    for label, level, base_y, color in right_label_specs:
        y_pos = base_y
        if last_y is not None and y_pos - last_y < min_gap:
            y_pos = last_y + min_gap
        y_pos = min(max(y_pos, pad_top + 10), pad_top + price_height - 10)
        packed_specs.append((label, level, y_pos, color))
        last_y = y_pos

    for label, level, y_pos, color in packed_specs:
        box_x = width - 116
        text = f"{label} {level:.2f}"
        parts.append(f'<rect x="{box_x}" y="{y_pos-8:.1f}" width="106" height="16" rx="8" fill="#0b1020" stroke="{color}" stroke-width="1"/>')
        parts.append(f'<text x="{box_x+53}" y="{y_pos+3:.1f}" fill="{color}" font-size="10" text-anchor="middle">{text}</text>')

    cand = candidate_date
    conf = confirm_date
    for i, candle in enumerate(candles):
        x = pad_left + step * i + step / 2
        up = candle.close >= candle.open
        body_color = '#22c55e' if up else '#ef4444'
        wick_color = '#cbd5e1'
        body_top = y_price(max(candle.open, candle.close))
        body_bottom = y_price(min(candle.open, candle.close))
        body_height = max(1.8, body_bottom - body_top)
        wick_top = y_price(candle.high)
        wick_bottom = y_price(candle.low)
        body_x = x - half
        vol_y = y_volume(candle.volume)
        vol_h = max(1.0, volume_bottom - vol_y)
        day = time.strftime("%Y-%m-%d", time.gmtime(candle.ts))

        if day == cand:
            parts.append(f'<rect x="{x-step/2:.1f}" y="{pad_top}" width="{step:.1f}" height="{price_height}" fill="#f59e0b22"/>')
            parts.append(f'<rect x="{x-step/2:.1f}" y="{volume_top}" width="{step:.1f}" height="{volume_height}" fill="#f59e0b18"/>')
        elif day == conf:
            parts.append(f'<rect x="{x-step/2:.1f}" y="{pad_top}" width="{step:.1f}" height="{price_height}" fill="#60a5fa22"/>')
            parts.append(f'<rect x="{x-step/2:.1f}" y="{volume_top}" width="{step:.1f}" height="{volume_height}" fill="#60a5fa18"/>')

        parts.append(f'<line x1="{x:.1f}" y1="{wick_top:.1f}" x2="{x:.1f}" y2="{wick_bottom:.1f}" stroke="{wick_color}" stroke-width="1.2"/>')
        if up:
            parts.append(f'<rect x="{body_x:.1f}" y="{body_top:.1f}" width="{candle_width:.1f}" height="{body_height:.1f}" fill="#0b1020" stroke="{body_color}" stroke-width="1.4" rx="1"/>')
        else:
            parts.append(f'<rect x="{body_x:.1f}" y="{body_top:.1f}" width="{candle_width:.1f}" height="{body_height:.1f}" fill="{body_color}" stroke="{body_color}" stroke-width="1.2" rx="1"/>')
        parts.append(f'<rect x="{body_x:.1f}" y="{vol_y:.1f}" width="{candle_width:.1f}" height="{vol_h:.1f}" fill="{body_color}" opacity="0.72" rx="1"/>')

    axis_y = pad_top + price_height
    parts.append(f'<line x1="{pad_left}" y1="{axis_y:.1f}" x2="{width-pad_right}" y2="{axis_y:.1f}" stroke="#334155" stroke-width="1.1"/>')
    parts.append(f'<line x1="{pad_left}" y1="{volume_bottom:.1f}" x2="{width-pad_right}" y2="{volume_bottom:.1f}" stroke="#334155" stroke-width="1.1"/>')

    label_positions = [0, len(candles)//3, (2*len(candles))//3, len(candles)-1]
    used = set()
    for pos in label_positions:
        if pos < 0 or pos >= len(candles) or pos in used:
            continue
        used.add(pos)
        candle = candles[pos]
        x = pad_left + step * pos + step / 2
        label = time.strftime("%m-%d", time.gmtime(candle.ts))
        parts.append(f'<text x="{x:.1f}" y="{height-8}" fill="#94a3b8" font-size="10" text-anchor="middle">{label}</text>')

    parts.append('</svg>')
    return ''.join(parts)


def format_table(results: list[ScanResult]) -> str:
    if not results:
        return "No confirmed reversal signals found."
    headers = ["Symbol", "Pattern", "Strength", "Score", "Candidate", "Confirm", "MktCap", "Close", "Stop", "T1", "T2", "ConfVol", "AvgVol20", "Avg$Vol20"]
    rows = [[r.symbol, r.pattern, r.pattern_strength or '-', f"{(r.score or 0):.0f}", r.candidate_date, r.confirm_date, format_market_cap(r.market_cap), f"{r.confirm_close:.2f}", f"{r.stop_loss:.2f}", f"{r.first_target:.2f}", f"{r.second_target:.2f}", f"{int(r.confirm_volume)}", f"{int(r.avg_volume_20)}", f"{int(r.avg_dollar_volume_20)}"] for r in results]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    def fmt(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
    sep = "-+-".join("-" * w for w in widths)
    return "\n".join([fmt(headers), sep, *[fmt(row) for row in rows]])


def render_html_report(results: list[ScanResult], output_path: str, args: argparse.Namespace) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for result in results:
        result.chart_svg = build_price_chart_svg(result.symbol, result.candidate_date, result.confirm_date, result.stop_loss, result.first_target, result.second_target, result.pattern, result.confirmation_reason, result.score)
    rows = []
    mobile_rows = []
    for r in results:
        rows.append(f"""<tr>
<td data-label="Symbol"><a href="#chart-{html.escape(r.symbol)}">{html.escape(r.symbol)}</a></td>
<td data-label="Pattern">{html.escape(r.pattern)}</td>
<td data-label="Strength">{html.escape(r.pattern_strength or "-")}</td>
<td data-label="Score">{(r.score or 0):.0f}</td>
<td data-label="Candidate">{html.escape(r.candidate_date)}</td>
<td data-label="Confirm">{html.escape(r.confirm_date)}</td>
<td data-label="MktCap">{html.escape(format_market_cap(r.market_cap))}</td>
<td data-label="Close">{r.confirm_close:.2f}</td>
<td data-label="Stop">{r.stop_loss:.2f}</td>
<td data-label="T1">{r.first_target:.2f}</td>
<td data-label="T2">{r.second_target:.2f}</td>
<td data-label="ConfVol">{int(r.confirm_volume)}</td>
<td data-label="AvgVol20">{int(r.avg_volume_20)}</td>
<td data-label="Avg$Vol20">{int(r.avg_dollar_volume_20)}</td>
</tr>""")
        mobile_rows.append(f"""<tr>
<td class="symbol-col"><a class="mobile-link" href="#chart-{html.escape(r.symbol)}">{html.escape(r.symbol)}</a></td>
<td class="signal-col">{html.escape(r.pattern)}<span class="mobile-sub">{html.escape(format_market_cap(r.market_cap))} · <span class="mobile-badge">{html.escape((r.side or '-').upper())}</span><span class="mobile-badge">S {(r.score or 0):.0f}</span></span></td>
<td class="risk-col"><div class="mobile-risk">Stop {r.stop_loss:.2f}</div><div class="mobile-risk">T1 {r.first_target:.2f}</div><div class="mobile-risk">T2 {r.second_target:.2f}</div></td>
</tr>""")
    chart_blocks = []
    for r in results:
        chart_blocks.append(f"""<section class="card" id="chart-{html.escape(r.symbol)}">
<h3>{html.escape(r.symbol)} <span>{html.escape(r.pattern)}</span></h3>
<div class="meta">确认日 {html.escape(r.confirm_date)} · 市值 {html.escape(format_market_cap(r.market_cap))} · 强度 {html.escape(r.pattern_strength or "-")} · 评分 {(r.score or 0):.0f}</div>
<div class="meta">确认原因：{html.escape(r.confirmation_reason or "-")}</div>
<div class="meta">评分明细：{html.escape(r.score_detail or "-")}</div>
<div class="meta">S/R：S1/S2/R1/R2 自动识别；交易位：Stop/T1/T2；均线数值显示在图右侧</div>
<div class="chart"><div class="chart-wrap">{r.chart_svg or ''}</div></div>
</section>""")
    preset_label = args.preset or 'custom'
    pages_label = 'main preset' if preset_label == 'main' else f'{preset_label} preset'
    preset_description = describe_strategy_preset(args.preset)
    title = f"反转扫描报告（{pages_label} / {len(results)}）"
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{color-scheme:dark;}}
*{{box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:16px;line-height:1.45;}}
.page{{max-width:1400px;margin:0 auto;}}
h1{{margin:0 0 8px;font-size:clamp(24px,4vw,32px);}}
p.sub{{margin:0 0 20px;color:#94a3b8;font-size:14px;}}
.card{{background:#111827;border:1px solid #243041;border-radius:14px;padding:16px;margin:16px 0;box-shadow:0 8px 24px rgba(0,0,0,.18);}}
.mobile-summary{{display:none;overflow:hidden;}}
.mobile-list{{width:100%;overflow:hidden;border:1px solid #243041;border-radius:12px;background:#0b1220;}}
.mobile-table{{width:100%;border-collapse:collapse;table-layout:fixed;}}
.mobile-table th,.mobile-table td{{padding:7px 6px;border-bottom:1px solid #243041;font-size:12px;text-align:left;vertical-align:top;}}
.mobile-table th{{background:#172033;color:#cbd5e1;font-weight:600;}}
.mobile-table tbody tr:last-child td{{border-bottom:none;}}
.mobile-table .symbol-col{{width:64px;position:sticky;left:0;background:#0b1220;z-index:2;box-shadow:6px 0 10px rgba(2,6,23,.35);}}
.mobile-table thead .symbol-col{{background:#172033;z-index:3;}}
.mobile-table .signal-col{{width:auto;}}
.mobile-table .risk-col{{width:96px;text-align:right;}}
.mobile-link{{color:#93c5fd;text-decoration:none;font-weight:700;display:inline-block;font-size:12px;}}
.mobile-sub{{display:block;color:#94a3b8;font-size:11px;line-height:1.35;margin-top:2px;}}
.mobile-badge{{display:inline-block;font-size:11px;color:#cbd5e1;background:#172033;border-radius:999px;padding:1px 6px;margin-left:4px;}}
.mobile-risk{{color:#cbd5e1;font-variant-numeric:tabular-nums;line-height:1.35;text-align:right;white-space:nowrap;}}
.table-card{{padding:0;overflow:hidden;}}
.table-wrap{{width:100%;overflow:auto;-webkit-overflow-scrolling:touch;}}
table{{width:100%;border-collapse:collapse;background:#111827;min-width:980px;}}
th,td{{padding:10px 12px;border-bottom:1px solid #243041;text-align:left;font-size:13px;vertical-align:top;}}
th{{background:#172033;color:#cbd5e1;position:sticky;top:0;z-index:1;}}
tr:hover td{{background:#0b1220;}}
h3{{margin:0 0 6px;font-size:18px;}}
h3 span{{font-size:13px;color:#93c5fd;font-weight:500;margin-left:8px;}}
.meta{{color:#94a3b8;font-size:12px;margin-bottom:8px;word-break:break-word;}}
.chart{{overflow:hidden;background:#0b1020;border-radius:10px;padding:8px;}}
.chart-wrap{{width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scroll-behavior:auto;}}
.chart svg{{display:block;max-width:none;height:auto;}}
a{{color:#93c5fd;text-decoration:none;}}
a:hover{{text-decoration:underline;}}
th:first-child, td:first-child{{position:sticky;left:0;z-index:2;background:#111827;box-shadow:6px 0 10px rgba(2,6,23,.35);border-right:1px solid #243041;}}
th:first-child{{z-index:4;background:#172033;}}
th{{box-shadow:0 1px 0 #243041;}}
tr:hover td:first-child{{background:#0b1220;}}
@media (max-width: 900px){{
  body{{padding:12px;}}
  .card{{padding:14px;}}
  table{{min-width:820px;}}
}}
@media (max-width: 680px){{
  .mobile-summary{{display:block;}}
  .table-card{{display:none !important;}}
  .chart{{padding:6px;}}
  .mobile-list{{overflow-x:auto;-webkit-overflow-scrolling:touch;}}
  .mobile-table{{min-width:100%;}}
}}
</style>
</head>
<body>
<div class="page">
<h1>{html.escape(pages_label)}：最近{args.recent_confirm_days}日已确认{("双向" if args.side == "both" else ("看涨" if args.side == "bullish" else "看跌"))}反转信号</h1>
<p class="sub">preset 优先驱动，按评分、市值与流动性排序；GitHub Pages 默认展示主策略结果</p>
<section class="card">
<h3>运行摘要</h3>
<div class="meta">生成时间：{generated_at}</div>
<div class="meta">命中数量：{len(results)} · preset={html.escape(preset_label)} · 页面标签={html.escape(pages_label)} · universe={html.escape(args.universe)} · side={html.escape(args.side)} · include_etfs={args.include_etfs}</div>
<div class="meta">当前 HTML 报告已按 preset-first 方式展示，GitHub Action 默认也会跟随同名 preset 运行。</div>
<div class="meta">策略条件：min_price={args.min_price} · min_avg_volume={args.min_avg_volume} · min_last_volume={args.min_last_volume} · min_r_multiple={args.min_r_multiple} · require_confirm_volume={args.require_confirm_volume} · confirm_volume_multiplier={args.confirm_volume_multiplier} · require_fresh_sma_cross_up={args.require_fresh_sma_cross_up} · sma_cross_mode={html.escape(args.sma_cross_mode)} · require_standard_uptrend={args.require_standard_uptrend} · require_rsi_above={args.require_rsi_above} · require_macd_bullish={args.require_macd_bullish} · require_above_sma200={args.require_above_sma200} · entry_mode={html.escape(args.entry_mode)} · stop_mode={html.escape(args.stop_mode)} · target_mode={html.escape(args.target_mode)}</div>
<div class="meta">运行参数：recent_confirm_days={args.recent_confirm_days} · workers={args.workers} · scan_retries={args.scan_retries} · no_cache={args.no_cache}</div>
<div class="meta">输出文件：{html.escape(output_path)}</div>
</section>
<section class="card">
<h3>preset 策略说明</h3>
<div class="meta">{html.escape(preset_description)}</div>
</section>
<section class="card">
<h3>数据版本信息</h3>
<div class="meta">页面标签：{html.escape(pages_label)}</div>
<div class="meta">当前 JSON 元数据字段：preset / pages_label / preset_description / result_count / recent_confirm_days / universe / side / include_etfs / workers / scan_retries / no_cache</div>
<div class="meta">配套 JSON 文件：reports/reversal_signals.json</div>
<div class="meta">如需脚本消费结果，请优先读取 JSON 顶层的 meta 与 results 两个字段。</div>
</section>
<section class="card mobile-summary">
<h3>结果列表</h3>
<div class="mobile-list"><table class="mobile-table"><thead><tr><th class="symbol-col">代码</th><th class="signal-col">信号</th><th class="risk-col">交易计划</th></tr></thead><tbody>{''.join(mobile_rows)}</tbody></table></div>
</section>
<section class="card table-card">
<div class="table-wrap">
<table>
<thead><tr><th>Symbol</th><th>Pattern</th><th>Strength</th><th>Score</th><th>Candidate</th><th>Confirm</th><th>MktCap</th><th>Close</th><th>Stop</th><th>T1</th><th>T2</th><th>ConfVol</th><th>AvgVol20</th><th>Avg$Vol20</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
</section>
{''.join(chart_blocks) if chart_blocks else '<section class="card">当前条件下未发现已确认反转信号。</section>'}
<script>
(function(){{
  function scrollChartsToRight(){{
    document.querySelectorAll('.chart-wrap').forEach(function(el){{
      el.scrollLeft = el.scrollWidth;
    }});
  }}
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", scrollChartsToRight);
  }} else {{
    scrollChartsToRight();
  }}
  window.addEventListener("load", scrollChartsToRight);
}})();
</script>
</div>
</body>
</html>"""
    Path(output_path).write_text(doc, encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan for confirmed bullish reversal candlestick signals")
    parser.add_argument("--symbols", help="Comma-separated symbol list")
    parser.add_argument("--preset", choices=["main", "high_quality"])
    parser.add_argument("--universe", choices=["liquid", "sp500", "us"], default="sp500")
    parser.add_argument("--include-etfs", action="store_true", default=True, help="Include ETFs when using --universe us")
    parser.add_argument("--exclude-etfs", action="store_false", dest="include_etfs", help="Exclude ETFs when using --universe us")
    parser.add_argument("--etf-groups", default="core")
    parser.add_argument("--scan-mode", choices=["strategy", "raw"], default="strategy")
    parser.add_argument("--require-fresh-sma-cross-up", action="store_true", default=True)
    parser.add_argument("--sma-cross-mode", choices=["either", "20", "50"], default="either")
    parser.add_argument("--require-rsi-above", type=float, default=None)
    parser.add_argument("--require-macd-bullish", action="store_true", default=False)
    parser.add_argument("--min-last-volume", type=float, default=0, help="Minimum last-day volume required")
    parser.add_argument("--min-market-cap", type=float, default=2_000_000_000, help="Minimum market cap required for Finviz prefilter")
    parser.add_argument("--min-price", type=float, default=5, help="Minimum last price required")
    parser.add_argument("--min-avg-volume", type=float, default=300_000, help="Minimum average daily volume required")
    parser.add_argument("--top-dollar-volume", type=int, default=0, help="Keep only top N symbols by estimated dollar volume after metadata prefilter")
    parser.add_argument("--require-confirm-volume", action="store_true", default=True)
    parser.add_argument("--no-require-confirm-volume", action="store_false", dest="require_confirm_volume")
    parser.add_argument("--confirm-volume-multiplier", type=float, default=1.5, help="Require confirm volume to be at least N times AvgVol20")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--recent-confirm-days", type=int, default=2, help="Only keep signals whose confirmation date is within the last N calendar days")
    parser.add_argument("--html", dest="html_out", help="Write an HTML report with summary table and per-symbol daily charts")
    parser.add_argument("--side", choices=["both", "bullish", "bearish"], default="bullish", help="Scan bullish, bearish, or both confirmed reversal patterns")
    parser.add_argument("--entry-mode", choices=["confirm_close", "next_open"], default="confirm_close")
    parser.add_argument("--stop-mode", choices=["pattern_anchor", "confirm_low", "tighter_of_pattern_and_confirm_low"], default="pattern_anchor")
    parser.add_argument("--target-mode", choices=["nearest_resistance", "r_multiple"], default="nearest_resistance")
    parser.add_argument("--scan-retries", type=int, default=3, help="Retry transient per-symbol scan failures up to N total attempts")
    parser.add_argument("--no-cache", action="store_true", help="Disable all local cache reads and writes for this run")
    return parser.parse_args()


def _build_universe_request(args: argparse.Namespace) -> UniverseRequest:
    symbols = [item.strip().upper() for item in args.symbols.split(',')] if args.symbols else []
    return UniverseRequest(
        universe=args.universe,
        limit=args.limit or None,
        symbols=symbols,
        min_price=args.min_price,
        min_avg_volume=args.min_avg_volume,
        min_last_volume=args.min_last_volume,
        min_market_cap=args.min_market_cap,
        include_etfs=args.include_etfs,
        etf_groups=[item.strip() for item in args.etf_groups.split(',') if item.strip()],
    )


def _build_strategy_spec(args: argparse.Namespace):
    overrides = {
        'side': args.side,
        'min_r_multiple': args.min_r_multiple,
        'require_confirm_volume': args.require_confirm_volume,
        'confirm_volume_multiplier': args.confirm_volume_multiplier,
        'require_fresh_sma_cross_up': args.require_fresh_sma_cross_up,
        'sma_cross_mode': args.sma_cross_mode,
        'require_standard_uptrend': args.require_standard_uptrend,
        'require_macd_bullish': args.require_macd_bullish,
        'require_rsi_above': args.require_rsi_above,
        'require_above_sma200': args.require_above_sma200,
        'entry_mode': args.entry_mode,
        'stop_mode': args.stop_mode,
        'target_mode': args.target_mode,
        'indicator_config': {
            'require_trend_alignment': args.require_standard_uptrend,
            'require_location_alignment': False,
            'location_tolerance_ratio': 0.02,
            'allowed_patterns': None,
        },
    }
    return load_strategy_spec(args.preset, overrides)


def _candidate_to_scan_result(signal) -> ScanResult:
    return ScanResult(
        symbol=signal.hit.symbol,
        pattern=signal.hit.pattern,
        candidate_date=signal.hit.candidate_date,
        confirm_date=signal.hit.confirm_date,
        confirm_close=signal.confirm_close,
        stop_loss=signal.stop_loss,
        first_target=signal.first_target,
        second_target=signal.second_target,
        confirm_volume=signal.confirm_volume,
        avg_volume_20=signal.avg_volume_20,
        avg_dollar_volume_20=signal.avg_dollar_volume_20,
        market_cap=signal.market_cap,
        confidence='confirmed',
        pattern_strength=signal.hit.pattern_strength,
        confirmation_reason=signal.hit.confirmation_reason,
        score=signal.hit.score,
        score_detail=signal.hit.score_detail,
        side=signal.side,
    )


def main() -> int:
    global NO_CACHE
    started = time.time()
    args = parse_args()
    preset_options = apply_strategy_preset(vars(args), args.preset)
    for key, value in preset_options.items():
        setattr(args, key, value)
    NO_CACHE = args.no_cache

    universe_start = time.time()
    request = _build_universe_request(args)
    if args.symbols:
        symbols = [s for s in request.symbols if is_supported_symbol(s)]
        log(f"using explicit symbol list: {len(symbols)} symbol(s)")
    else:
        log(f"delegating scan pipeline for universe={args.universe}, include_etfs={args.include_etfs}")
    log(f"universe prep completed in {time.time() - universe_start:.1f}s")

    scan_start = time.time()
    scan_failures: list[str] = []
    spec = _build_strategy_spec(args)
    results = [_candidate_to_scan_result(signal) for signal in run_scan(spec, request, '5y')]

    results = [r for r in results if is_recent_confirm_date(r.confirm_date, args.recent_confirm_days)]
    results.sort(key=lambda r: ((r.score or 0), (r.market_cap or 0), r.avg_dollar_volume_20), reverse=True)
    if args.html_out:
        render_html_report(results, args.html_out, args)
        print(f"HTML report written to {args.html_out}")
    else:
        print(format_table(results))
    log(f"ohlcv scan completed in {time.time() - scan_start:.1f}s")
    log(f"total elapsed {time.time() - started:.1f}s")
    if scan_failures:
        print(f"\nWarnings: {len(scan_failures)} symbol(s) failed to scan.", file=sys.stderr)
        for msg in scan_failures[:10]:
            print(f"- {msg}", file=sys.stderr)
    if args.json_out:
        preset_label = args.preset or 'custom'
        pages_label = 'main preset' if preset_label == 'main' else f'{preset_label} preset'
        payload = {
            'meta': {
                'preset': preset_label,
                'pages_label': pages_label,
                'preset_description': describe_strategy_preset(args.preset),
                'recent_confirm_days': args.recent_confirm_days,
                'universe': args.universe,
                'side': args.side,
                'include_etfs': args.include_etfs,
                'workers': args.workers,
                'scan_retries': args.scan_retries,
                'no_cache': args.no_cache,
                'result_count': len(results),
            },
            'results': [asdict(r) for r in results],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
