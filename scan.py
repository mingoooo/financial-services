import json
import math
import re
import time
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests
import yfinance as yf

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
CACHE_PATH = Path(".ff_calendar_cache.json")
CAL_TTL_SECONDS = 4 * 60 * 60
PACKET_PATH = Path("packet.json")

MARKET_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Dow": "^DJI",
    "Nasdaq": "^IXIC",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
    "US 10Y": "^TNX",
    "US 3M": "^IRX",
    "WTI Oil": "CL=F",
    "Dollar (DXY)": "DX-Y.NYB",
}

UNIVERSE = [
    "NVDA", "AMD", "AVGO", "SMCI", "MRVL", "TSLA", "AAPL", "MSFT", "META", "AMZN",
    "GOOGL", "NFLX", "DELL", "SNOW", "PLTR", "COIN", "MSTR", "SOFI", "RIVN", "NIO",
    "MARA", "RIOT", "BA", "DIS", "JPM", "BAC", "XOM", "CVX", "HOOD", "UBER",
    "CRWD", "PANW", "CELH", "LULU", "NKE", "CAVA", "DKNG", "ARM", "INTC", "MU",
]

RSS_FEEDS = {
    "MarketWatch Top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "MarketWatch RealTime": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Google News Markets": "https://news.google.com/rss/search?q=markets%20OR%20earnings%20when%3A1d&hl=en-US&gl=US&ceid=US:en",
}

PRIMARY_PUBLISHERS = [
    "Bloomberg", "Reuters", "CNBC", "MarketWatch", "Barron's", "Yahoo Finance", "WSJ",
    "Wall Street Journal", "Financial Times", "The Information", "Investor's Business Daily",
]

NAME_STOP = {
    "the", "inc", "corp", "corporation", "holdings", "holding", "technologies", "technology",
    "group", "digital", "applied", "advanced", "strategy", "motors", "energy", "platforms",
    "systems", "solutions", "international", "global", "brands", "resources", "financial",
    "health", "bio", "biotech", "pharma", "pharmaceuticals", "media", "software", "networks",
    "communications", "industries", "labs", "limited", "company", "companies", "enterprise",
    "enterprises", "capital", "materials", "therapeutics", "devices", "medical", "foods",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}


def log(msg):
    print(msg, flush=True)


def safe_float(value):
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def strip_html(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def iso_now():
    return datetime.now(UTC).isoformat()


def fetch_json(url, timeout=20):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        return None, str(exc)


def get_history(symbol, **kwargs):
    try:
        return yf.Ticker(symbol).history(**kwargs)
    except Exception as exc:
        log(f"history failed for {symbol}: {exc}")
        return None


def get_fast_info(symbol):
    try:
        ticker = yf.Ticker(symbol)
        fast = dict(ticker.fast_info or {})
        info = ticker.info or {}
        return ticker, fast, info
    except Exception as exc:
        log(f"fast_info failed for {symbol}: {exc}")
        return None, {}, {}


def current_extended_price(ticker_obj, fast, info, symbol):
    try:
        hist = ticker_obj.history(period="2d", interval="1m", auto_adjust=False, prepost=True)
        if hist is not None and not hist.empty:
            close_series = hist["Close"].dropna()
            if not close_series.empty:
                return safe_float(close_series.iloc[-1])
    except Exception as exc:
        log(f"extended minute price failed for {symbol}: {exc}")
    for value in [
        info.get("preMarketPrice"),
        info.get("postMarketPrice"),
        fast.get("lastPrice"),
        fast.get("regularMarketPrice"),
        info.get("regularMarketPrice"),
    ]:
        number = safe_float(value)
        if number is not None:
            return number
    return None


def previous_close_from_daily(ticker_obj, symbol):
    try:
        hist = ticker_obj.history(period="7d", interval="1d", auto_adjust=False, prepost=False)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna().tolist()
        if not closes:
            return None
        return safe_float(closes[-1])
    except Exception as exc:
        log(f"previous close failed for {symbol}: {exc}")
        return None


def last_two_daily_closes(symbol):
    hist = get_history(symbol, period="7d", interval="1d", auto_adjust=False, prepost=False)
    if hist is None or hist.empty or len(hist) < 2:
        return None, None
    closes = hist["Close"].dropna().tolist()
    if len(closes) < 2:
        return None, None
    return safe_float(closes[-1]), safe_float(closes[-2])


def build_market_snapshot():
    out = []
    for name, symbol in MARKET_SYMBOLS.items():
        log(f"market snapshot: {name} {symbol}")
        ticker, fast, info = get_fast_info(symbol)
        prev_close = previous_close_from_daily(ticker, symbol) if ticker is not None else None
        last = current_extended_price(ticker, fast, info, symbol) if ticker is not None else None
        if last is None or prev_close is None:
            daily_last, daily_prev = last_two_daily_closes(symbol)
            last = last if last is not None else daily_last
            prev_close = prev_close if prev_close is not None else daily_prev
        change_pct = None
        if last is not None and prev_close not in (None, 0):
            change_pct = (last / prev_close - 1) * 100
        out.append({
            "name": name,
            "symbol": symbol,
            "last": last,
            "prev_close": prev_close,
            "change_pct": change_pct,
        })
    return out


def run_predefined_screener(name):
    try:
        screen = yf.screen(name)
        quotes = screen.get("quotes", []) if isinstance(screen, dict) else []
        return quotes, None
    except Exception as exc:
        return [], str(exc)


def candidate_from_quote(quote, source):
    symbol = quote.get("symbol") or quote.get("ticker")
    if not symbol:
        return None
    price = safe_float(quote.get("preMarketPrice") or quote.get("postMarketPrice") or quote.get("regularMarketPrice"))
    prev_close = safe_float(quote.get("regularMarketPreviousClose") or quote.get("regularMarketPreviousCloseRaw"))
    gap_pct = safe_float(quote.get("regularMarketChangePercent"))
    market_cap = safe_float(quote.get("marketCap"))
    volume = safe_float(quote.get("regularMarketVolume") or quote.get("volume"))
    name = quote.get("shortName") or quote.get("longName") or quote.get("displayName")
    return {
        "ticker": symbol.upper(),
        "company_name": name,
        "price": price,
        "prev_close": prev_close,
        "gap_pct": gap_pct,
        "market_cap": market_cap,
        "volume": volume,
        "candidate_source": source,
    }


def fallback_candidates():
    results = []
    for symbol in UNIVERSE:
        log(f"fallback candidate: {symbol}")
        try:
            ticker, fast, info = get_fast_info(symbol)
            if ticker is None:
                continue
            current_price = current_extended_price(ticker, fast, info, symbol)
            prev_close = previous_close_from_daily(ticker, symbol)
            gap_pct = (current_price / prev_close - 1) * 100 if current_price is not None and prev_close not in (None, 0) else None
            results.append({
                "ticker": symbol,
                "company_name": info.get("shortName") or info.get("longName") or symbol,
                "price": current_price,
                "prev_close": prev_close,
                "gap_pct": gap_pct,
                "market_cap": safe_float(fast.get("marketCap") or info.get("marketCap")),
                "volume": safe_float(fast.get("lastVolume") or info.get("volume")),
                "candidate_source": "fallback_universe",
            })
        except Exception as exc:
            log(f"fallback failed for {symbol}: {exc}")
    return results


def build_live_top_movers():
    by_symbol = {}
    source_used = []
    for screener in ["day_gainers", "most_actives"]:
        log(f"screener: {screener}")
        quotes, err = run_predefined_screener(screener)
        if err:
            log(f"screener failed {screener}: {err}")
        for quote in quotes:
            item = candidate_from_quote(quote, f"yfinance_{screener}")
            if item:
                by_symbol[item["ticker"]] = item
        if quotes:
            source_used.append(screener)
    if len(by_symbol) < 5:
        log("live screener thin, using fallback universe")
        for item in fallback_candidates():
            by_symbol[item["ticker"]] = item
        candidate_source = "fallback_universe" if not source_used else f"yfinance_{'+'.join(source_used)}+fallback_universe"
    else:
        candidate_source = f"yfinance_{'+'.join(source_used)}" if source_used else "yfinance_unknown"
    movers = [
        item for item in by_symbol.values()
        if item.get("price") is not None and item.get("gap_pct") is not None
    ]
    movers.sort(key=lambda x: abs(x.get("gap_pct") or 0), reverse=True)
    filtered = [m for m in movers if abs(m.get("gap_pct") or 0) >= 4 and (m.get("price") or 0) >= 3][:12]
    return candidate_source, filtered


def should_drop_news(title):
    low = (title or "").lower()
    if "price prediction" in low:
        return True
    if re.search(r"20\d{2}\s*[-/]\s*20\d{2}", title or ""):
        return True
    return False


def parse_feed(label, url):
    items = []
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            title = (entry.get("title") or "").strip()
            if not title or should_drop_news(title):
                continue
            items.append({
                "source": label,
                "publisher": entry.get("source", {}).get("title") or label,
                "title": title,
                "summary": strip_html(entry.get("summary") or entry.get("description") or ""),
                "link": entry.get("link"),
                "published": entry.get("published") or entry.get("updated"),
            })
    except Exception as exc:
        log(f"feed failed {label}: {exc}")
    return items


def build_market_news():
    all_items = []
    for label, url in RSS_FEEDS.items():
        log(f"rss: {label}")
        all_items.extend(parse_feed(label, url))
    deduped = {}
    for item in all_items:
        key = (item.get("title") or "", item.get("link") or "")
        deduped[key] = item
    items = list(deduped.values())
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    return items[:20]


def load_calendar_cache():
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return None


def save_calendar_cache(raw):
    try:
        CACHE_PATH.write_text(json.dumps({"fetched_at": iso_now(), "raw": raw}, indent=2))
    except Exception as exc:
        log(f"cache write failed: {exc}")


def parse_ff_time(date_str, time_str):
    for fmt in ["%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p"]:
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=ET)
        except Exception:
            pass
    return None


def fetch_econ_calendar():
    today_et = datetime.now(ET).date()
    tomorrow_et = today_et + timedelta(days=1)
    result = {
        "source": "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "filter": {"country": "USD", "impact": "High", "dates": [str(today_et), str(tomorrow_et)]},
        "today_date": str(today_et),
        "tomorrow_date": str(tomorrow_et),
        "today": [],
        "tomorrow": [],
        "notes": [],
    }
    raw = None
    cache = load_calendar_cache()
    use_cache = False
    if cache:
        fetched_at = cache.get("fetched_at")
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(fetched_at)
            if age.total_seconds() < CAL_TTL_SECONDS:
                raw = cache.get("raw")
                use_cache = True
                result["notes"].append("using cached weekly feed within 4h ttl")
        except Exception:
            pass
    if raw is None:
        raw, err = fetch_json(result["source"], timeout=20)
        if raw is not None:
            save_calendar_cache(raw)
        else:
            result["notes"].append(f"live fetch failed: {err}")
            if cache and cache.get("raw") is not None:
                raw = cache.get("raw")
                use_cache = True
                result["notes"].append("fell back to cached weekly feed")
    if raw is None:
        result["notes"].append("calendar unavailable, returning empty results")
        return result
    if use_cache:
        result["notes"].append("feed may be stale")
    try:
        for event in raw:
            if event.get("country") != "USD" or event.get("impact") != "High":
                continue
            dt = parse_ff_time(str(event.get("date", "")), str(event.get("time", "")))
            if dt is None:
                continue
            item = {
                "time_et": dt.strftime("%Y-%m-%d %I:%M %p ET"),
                "title": event.get("title"),
                "forecast": event.get("forecast"),
                "previous": event.get("previous"),
            }
            if dt.date() == today_et:
                result["today"].append(item)
            elif dt.date() == tomorrow_et:
                result["tomorrow"].append(item)
        result["today"].sort(key=lambda x: x["time_et"])
        result["tomorrow"].sort(key=lambda x: x["time_et"])
    except Exception as exc:
        result["today"] = []
        result["tomorrow"] = []
        result["notes"].append(f"calendar parse error: {exc}")
    return result


def distinctive_tokens(company_name):
    raw = re.findall(r"[A-Za-z][A-Za-z&.'-]+", company_name or "")
    tokens = []
    for token in raw:
        clean = token.lower().strip(".'")
        # Only distinctive 4+ letter name tokens can match on company name alone, because generic words like
        # Applied, Digital, Holdings, Technologies, Strategy, Energy, and Motors cross-match unrelated companies.
        if len(clean) < 4 or clean in NAME_STOP:
            continue
        tokens.append(clean)
    return sorted(set(tokens), key=len, reverse=True)


def title_matches_ticker_or_name(text, ticker, company_name):
    text = text or ""
    if re.search(rf"\b{re.escape(ticker)}\b", text, flags=re.IGNORECASE):
        return True
    for token in distinctive_tokens(company_name):
        if re.search(rf"\b{re.escape(token)}\b", text, flags=re.IGNORECASE):
            return True
    return False


def publisher_rank(item):
    hay = " ".join([item.get("publisher") or "", item.get("source") or "", item.get("title") or ""])
    for idx, pub in enumerate(PRIMARY_PUBLISHERS):
        if pub.lower() in hay.lower():
            return idx
    return len(PRIMARY_PUBLISHERS)


def safe_get_news(ticker_obj, symbol):
    try:
        return ticker_obj.news or []
    except Exception as exc:
        log(f"news failed for {symbol}: {exc}")
        return []


def extract_catalysts(symbol, company_name, ticker_news, market_news):
    candidates = []
    for item in ticker_news:
        title = item.get("title") or ""
        if not title_matches_ticker_or_name(title, symbol, company_name):
            continue
        candidates.append({
            "publisher": item.get("publisher") or item.get("providerPublishTime") or "",
            "source": "yfinance_news",
            "title": title,
            "link": item.get("link") or item.get("canonicalUrl", {}).get("url"),
        })
    for item in market_news:
        title = item.get("title") or ""
        if not title_matches_ticker_or_name(title, symbol, company_name):
            continue
        candidates.append({
            "publisher": item.get("publisher") or item.get("source") or "",
            "source": item.get("source") or "rss",
            "title": title,
            "link": item.get("link"),
        })
    seen = set()
    unique = []
    for item in candidates:
        key = (item.get("title"), item.get("link"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda x: (publisher_rank(x), x.get("title") or ""))
    return {
        "catalyst_found": bool(unique),
        "catalyst_headlines": unique[:6],
    }


def intraday_levels(symbol):
    hist = get_history(symbol, period="1d", interval="5m", auto_adjust=False, prepost=True)
    if hist is None or hist.empty:
        return {}
    try:
        idx = hist.index
        if getattr(idx, "tz", None) is None:
            idx = idx.tz_localize(UTC).tz_convert(ET)
        else:
            idx = idx.tz_convert(ET)
        work = hist.copy()
        work.index = idx
        pre = work.between_time("04:00", "09:29")
        total_pv = (work["Close"] * work["Volume"]).fillna(0).cumsum()
        total_v = work["Volume"].fillna(0).cumsum().replace(0, math.nan)
        vwap_series = total_pv / total_v
        return {
            "current_extended_price": safe_float(work["Close"].dropna().iloc[-1]) if not work["Close"].dropna().empty else None,
            "vwap": safe_float(vwap_series.dropna().iloc[-1]) if not vwap_series.dropna().empty else None,
            "hod": safe_float(work["High"].max()),
            "lod": safe_float(work["Low"].min()),
            "premarket_high": safe_float(pre["High"].max()) if not pre.empty else None,
            "premarket_volume": safe_float(pre["Volume"].sum()) if not pre.empty else None,
        }
    except Exception as exc:
        log(f"intraday levels failed for {symbol}: {exc}")
        return {}


def daily_metrics(symbol):
    hist = get_history(symbol, period="1y", interval="1d", auto_adjust=False, prepost=False)
    if hist is None or hist.empty:
        return {}
    try:
        work = hist.copy().dropna(subset=["Close"])
        if len(work) >= 2:
            work_no_today = work.iloc[:-1]
            today_bar = work.iloc[-1]
        else:
            work_no_today = work
            today_bar = None
        avg20 = safe_float(work_no_today["Volume"].tail(20).mean()) if not work_no_today.empty else None
        sma200 = safe_float(work_no_today["Close"].tail(200).mean()) if len(work_no_today) >= 1 else None
        prior = work_no_today.iloc[-1] if not work_no_today.empty else None
        return {
            "sma_200": sma200,
            "prior_day_high": safe_float(prior["High"]) if prior is not None else None,
            "prior_close": safe_float(prior["Close"]) if prior is not None else None,
            "today_open": safe_float(today_bar["Open"]) if today_bar is not None else None,
            "avg_volume_20d": avg20,
            "today_volume": safe_float(today_bar["Volume"]) if today_bar is not None else None,
        }
    except Exception as exc:
        log(f"daily metrics failed for {symbol}: {exc}")
        return {}


def next_earnings_date(ticker_obj, symbol):
    try:
        dates = ticker_obj.calendar
        if hasattr(dates, "index") and len(dates.index) > 0:
            try:
                values = list(dates.iloc[:, 0].dropna().astype(str))
                return values[0] if values else None
            except Exception:
                pass
    except Exception as exc:
        log(f"earnings calendar failed for {symbol}: {exc}")
    try:
        ed = ticker_obj.get_earnings_dates(limit=4)
        if ed is not None and not ed.empty:
            first = ed.index[0]
            return str(first)
    except Exception as exc:
        log(f"earnings dates failed for {symbol}: {exc}")
    return None


def enrich_gapper(base, market_news):
    symbol = base["ticker"]
    log(f"enrich: {symbol}")
    out = dict(base)
    try:
        ticker, fast, info = get_fast_info(symbol)
        if ticker is None:
            return out
        out["company_name"] = out.get("company_name") or info.get("shortName") or info.get("longName") or symbol
        intra = intraday_levels(symbol)
        daily = daily_metrics(symbol)
        out.update(intra)
        out.update(daily)
        today_volume = out.get("today_volume")
        avg20 = out.get("avg_volume_20d")
        # yfinance often reports about 0 premarket volume, so true premarket RVOL needs a premarket feed like Alpaca.
        # Full-day relative volume is the keyless stand-in here.
        out["rvol"] = (today_volume / avg20) if today_volume is not None and avg20 not in (None, 0) else None
        ticker_news = safe_get_news(ticker, symbol)
        out.update(extract_catalysts(symbol, out.get("company_name"), ticker_news, market_news))
        out["next_earnings_date"] = next_earnings_date(ticker, symbol)
        out["market_cap"] = out.get("market_cap") or safe_float(fast.get("marketCap") or info.get("marketCap"))
        out["price"] = out.get("current_extended_price") or out.get("price") or current_extended_price(ticker, fast, info, symbol)
        out["prev_close"] = out.get("prev_close") or out.get("prior_close")
        if out.get("gap_pct") is None and out.get("price") is not None and out.get("prev_close") not in (None, 0):
            out["gap_pct"] = (out["price"] / out["prev_close"] - 1) * 100
        gap = out.get("gap_pct")
        price = out.get("price")
        mcap = out.get("market_cap")
        prior_high = out.get("prior_day_high")
        open_price = out.get("today_open")
        sma200 = out.get("sma_200")
        rvol = out.get("rvol")
        catalyst_found = bool(out.get("catalyst_found"))
        out["day_eligible"] = bool(
            gap is not None and gap > 3 and
            price is not None and price > 3 and
            mcap is not None and mcap > 1_000_000_000 and
            rvol is not None and rvol > 1.5 and
            prior_high is not None and price > prior_high
        )
        out["swing_eligible"] = bool(
            gap is not None and gap >= 8 and
            price is not None and price > 3 and
            open_price is not None and prior_high is not None and open_price > prior_high and
            sma200 is not None and open_price > sma200 and
            mcap is not None and mcap >= 800_000_000 and
            catalyst_found
        )
    except Exception as exc:
        log(f"enrich failed for {symbol}: {exc}")
    return out


def build_criteria_text():
    return {
        "day_trading_watchlist": "Trend Join Long: gap > 3%, price > $3, market cap > $1B, RVOL > 1.5, and price above prior-day high. Intraday execution is handled later, not here.",
        "swing_watchlist": "Swing setup: gap >= 8%, price > $3, open above prior-day high, open above 200-day SMA, market cap >= $800M, and a real catalyst exists. Entry and exit management are not decided here.",
    }


def build_scan_params():
    return {
        "market_snapshot_symbols": MARKET_SYMBOLS,
        "screeners": ["day_gainers", "most_actives"],
        "fallback_universe": UNIVERSE,
        "gap_filter": {"abs_gap_pct_min": 4, "price_min": 3, "top_n": 12},
        "rss_feeds": RSS_FEEDS,
        "econ_calendar": {"country": "USD", "impact": "High", "ttl_hours": 4},
    }


def build_gaps_to_fill():
    return [
        "Market-wide earnings coverage is only partial because this packet uses free RSS and ticker-level news.",
        "Intraday levels depend on yfinance intraday bars and can be missing or delayed.",
        "Premarket RVOL is approximated with full-day relative volume because keyless yfinance premarket volume is unreliable.",
    ]


def main():
    log("starting premarket scan")
    packet = {
        "generated_at": iso_now(),
        "candidate_source": None,
        "trading_day_note": "Raw premarket packet only. No analysis, no conviction, no watchlist bucketing.",
        "scan_params": build_scan_params(),
        "criteria": build_criteria_text(),
        "market_snapshot": [],
        "econ_calendar": {},
        "gappers": [],
        "market_news": [],
        "gaps_to_fill": build_gaps_to_fill(),
    }
    packet["market_snapshot"] = build_market_snapshot()
    packet["market_news"] = build_market_news()
    packet["econ_calendar"] = fetch_econ_calendar()
    candidate_source, gappers = build_live_top_movers()
    packet["candidate_source"] = candidate_source
    enriched = []
    for gapper in gappers:
        enriched.append(enrich_gapper(gapper, packet["market_news"]))
        time.sleep(0.2)
    packet["gappers"] = enriched
    PACKET_PATH.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
    log(f"wrote {PACKET_PATH}")


if __name__ == "__main__":
    main()
