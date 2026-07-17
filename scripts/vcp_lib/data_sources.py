from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from .config import ScanConfig
from .models import RawCandidate

USER_AGENT = 'Mozilla/5.0 (compatible; vcp-scanner/1.0)'
_HEADERS = {'User-Agent': USER_AGENT}
_REQUEST_TIMEOUT = 30


@dataclass
class ProviderFetchResult:
    candidates: list[RawCandidate]
    mode_used: str
    warnings: list[str]
    rules_applied: list[str]


_DEFECTIVE_SUFFIXES = ('W', 'R', 'P')


def _cache_path(cache_dir: Path, namespace: str, key: str) -> Path:
    safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', key)
    return cache_dir / namespace / f'{safe}.json'


def cache_path(cache_dir: Path, namespace: str, key: str) -> Path:
    return _cache_path(cache_dir, namespace, key)


def _load_json_cache(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None


def load_json_cache(path: Path) -> dict | list | None:
    return _load_json_cache(path)


def _write_json_cache(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def write_json_cache(path: Path, payload: dict | list) -> None:
    _write_json_cache(path, payload)


def _fetch_text_with_retries(url: str, *, attempts: int = 3, sleep_base: float = 1.5) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(sleep_base * (attempt + 1) + random.uniform(0.0, 0.5))
    raise RuntimeError(f'fetch failed for {url}: {last_error}')


def _parse_finviz_symbols(html: str) -> list[RawCandidate]:
    soup = BeautifulSoup(html, 'html.parser')
    candidates: list[RawCandidate] = []
    seen: set[str] = set()
    for link in soup.find_all('a', href=re.compile(r'^stock\?t=')):
        href = link.get('href', '')
        match = re.search(r'[?&]t=([A-Z.\-]{1,10})', href)
        if not match:
            continue
        symbol = match.group(1).upper()
        text = link.get_text(' ', strip=True)
        if not text or text != symbol or symbol in seen:
            continue
        seen.add(symbol)
        row = link.find_parent('tr')
        text_cells = [cell.get_text(' ', strip=True) for cell in row.find_all('td')] if row else []
        last_price = None
        try:
            for cell in reversed(text_cells):
                value = float(cell.replace(',', '').replace('%', ''))
                if value > 0:
                    last_price = value
                    break
        except ValueError:
            pass
        candidates.append(RawCandidate(symbol=symbol, last_price=last_price, source_tags=['finviz']))
    return candidates


def fetch_finviz_candidates(config: ScanConfig) -> ProviderFetchResult:
    cache_dir = config.cache_dir_path()
    rules = [
        '股票池来源：Finviz 美国股票筛选结果',
        '市场：美国',
        '资产：普通股票优先（Finviz: sec_stocksonly）',
        f'价格 > {int(config.min_price)} 美元',
        '站上 50 日均线',
        '站上 200 日均线',
        '距离 52 周高点 0%–10%',
        '平均成交量 > 50 万股',
    ]
    query = {
        'v': '111',
        'f': ','.join([
            'geo_usa',
            'sec_stocksonly',
            f'sh_price_o{int(config.min_price)}',
            'ta_sma50_pa',
            'ta_sma200_pa',
            'ta_highlow52w_b0to10h',
            'sh_avgvol_o500',
        ]),
    }
    all_candidates: list[RawCandidate] = []
    seen: set[str] = set()
    starts = [1, 21, 41, 61, 81, 101]
    for start in starts:
        page_query = dict(query)
        page_query['r'] = str(start)
        url = f"https://finviz.com/screener.ashx?{urlencode(page_query)}"
        cache_path = _cache_path(cache_dir, 'finviz', f"screen_{page_query['f']}_{start}")
        html = None
        cached = _load_json_cache(cache_path)
        if isinstance(cached, dict) and 'html' in cached:
            html = cached['html']
        if html is None:
            html = _fetch_text_with_retries(url)
            _write_json_cache(cache_path, {'html': html})
        page_candidates = _parse_finviz_symbols(html)
        if not page_candidates:
            break
        added = 0
        for candidate in page_candidates:
            if candidate.symbol in seen:
                continue
            seen.add(candidate.symbol)
            all_candidates.append(candidate)
            added += 1
        if added == 0:
            break
        time.sleep(0.6 + random.uniform(0.0, 0.3))
    if not all_candidates:
        raise RuntimeError('Finviz returned no candidates')
    return ProviderFetchResult(candidates=all_candidates, mode_used='finviz+yahoo', warnings=[], rules_applied=rules)


def _fetch_nasdaq_stock_list(config: ScanConfig) -> list[str]:
    cache_path = _cache_path(config.cache_dir_path(), 'universe', 'nasdaq_stocks')
    cached = _load_json_cache(cache_path)
    if isinstance(cached, dict) and 'symbols' in cached:
        return list(cached['symbols'])

    urls = [
        'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
        'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',
    ]
    symbols: list[str] = []
    for url in urls:
        text = _fetch_text_with_retries(url)
        lines = text.splitlines()
        for line in lines[1:]:
            if not line or line.startswith('File Creation Time'):
                continue
            parts = line.split('|')
            symbol = parts[0].strip().upper()
            if not symbol or not re.fullmatch(r'[A-Z.\-]{1,10}', symbol):
                continue
            if symbol.endswith(_DEFECTIVE_SUFFIXES):
                continue
            if symbol not in symbols:
                symbols.append(symbol)
    _write_json_cache(cache_path, {'symbols': symbols})
    return symbols


def _frame_to_serializable_records(frame: pd.DataFrame) -> dict:
    records: list[dict] = []
    if isinstance(frame.columns, pd.MultiIndex):
        columns = ['symbol', 'field', 'value', 'date']
        for dt, row in frame.iterrows():
            dt_str = str(dt)
            for symbol, field in frame.columns:
                value = row[(symbol, field)]
                if pd.isna(value):
                    continue
                records.append({'date': dt_str, 'symbol': symbol, 'field': field, 'value': float(value)})
        return {'kind': 'multi', 'records': records, 'columns': columns}
    simple = frame.copy()
    simple.index = simple.index.astype(str)
    return {'kind': 'simple', 'records': simple.reset_index().to_dict(orient='records')}


def frame_to_serializable_records(frame: pd.DataFrame) -> dict:
    return _frame_to_serializable_records(frame)


def _serializable_records_to_frame(payload: dict) -> pd.DataFrame | None:
    kind = payload.get('kind')
    if kind == 'simple':
        records = payload.get('records', [])
        if not records:
            return None
        frame = pd.DataFrame(records)
        if 'index' in frame.columns:
            frame = frame.rename(columns={'index': 'Date'})
        if 'Date' in frame.columns:
            frame = frame.set_index('Date')
        frame.index = pd.to_datetime(frame.index)
        return frame
    if kind == 'multi':
        records = payload.get('records', [])
        if not records:
            return None
        long_df = pd.DataFrame(records)
        wide = long_df.pivot_table(index='date', columns=['symbol', 'field'], values='value', aggfunc='first')
        wide.index = pd.to_datetime(wide.index)
        wide = wide.sort_index(axis=1)
        return wide
    return None


def serializable_records_to_frame(payload: dict) -> pd.DataFrame | None:
    return _serializable_records_to_frame(payload)


def load_yfinance_history(symbol: str, **kwargs) -> pd.DataFrame:
    return yf.Ticker(symbol).history(**kwargs)


def normalize_daily_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])

    normalized = frame.copy() if 'Date' in frame.columns else frame.reset_index()
    if 'Date' not in normalized.columns:
        first_column = normalized.columns[0]
        if str(first_column).lower() != 'date':
            normalized = normalized.rename(columns={first_column: 'Date'})
    normalized = normalized.rename(columns=str.title)
    expected = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    available = [column for column in expected if column in normalized.columns]
    normalized = normalized[available].copy()
    if 'Date' in normalized.columns:
        normalized['Date'] = pd.to_datetime(normalized['Date'])
    required = [column for column in ['Open', 'High', 'Low', 'Close', 'Volume'] if column in normalized.columns]
    if required:
        normalized = normalized.dropna(subset=required)
    return normalized.reset_index(drop=True)


def _download_batch_with_cache(symbols: list[str], config: ScanConfig, batch_idx: int) -> pd.DataFrame | None:
    cache_path = _cache_path(config.cache_dir_path(), 'yahoo_prefilter', f'batch_{batch_idx}_{len(symbols)}')
    cached = _load_json_cache(cache_path)
    if isinstance(cached, dict):
        restored = _serializable_records_to_frame(cached)
        if restored is not None and not restored.empty:
            return restored

    last_error: Exception | None = None
    for attempt in range(4):
        try:
            data = yf.download(
                tickers=' '.join(symbols),
                period='1mo',
                interval='1d',
                auto_adjust=False,
                group_by='ticker',
                threads=False,
                progress=False,
                timeout=20,
            )
            if data is None or data.empty:
                return None
            _write_json_cache(cache_path, _frame_to_serializable_records(data))
            return data
        except Exception as exc:
            last_error = exc
            time.sleep((attempt + 1) * 2.0 + random.uniform(0.0, 0.5))
    return None


def _build_high_liquidity_candidates(config: ScanConfig) -> list[RawCandidate]:
    universe_symbols = _fetch_nasdaq_stock_list(config)
    probe_symbols = universe_symbols
    candidates: list[RawCandidate] = []
    batch_size = 120
    for batch_idx, start in enumerate(range(0, len(probe_symbols), batch_size)):
        batch = probe_symbols[start:start + batch_size]
        data = _download_batch_with_cache(batch, config, batch_idx)
        if data is None or data.empty:
            continue
        for symbol in batch:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if symbol not in data.columns.get_level_values(0):
                        continue
                    symbol_df = data[symbol].dropna()
                else:
                    symbol_df = data.dropna()
                if symbol_df is None or symbol_df.empty or len(symbol_df) < 10:
                    continue
                close = float(symbol_df['Close'].iloc[-1])
                avg_dollar_volume = float((symbol_df['Close'] * symbol_df['Volume']).tail(20).mean())
                sma50 = float(symbol_df['Close'].rolling(50, min_periods=20).mean().iloc[-1])
                sma200_series = symbol_df['Close'].rolling(200, min_periods=40).mean()
                sma200 = float(sma200_series.iloc[-1]) if not sma200_series.dropna().empty else None
                high_lookback = float(symbol_df['High'].max())
                near_high = close / max(high_lookback, 1e-9) - 1.0
                if close < config.min_price:
                    continue
                if avg_dollar_volume < config.min_dollar_volume:
                    continue
                if close < sma50:
                    continue
                if sma200 is not None and close < sma200:
                    continue
                if near_high < -0.15:
                    continue
                candidates.append(
                    RawCandidate(
                        symbol=symbol,
                        last_price=close,
                        average_volume=float(symbol_df['Volume'].tail(20).mean()),
                        average_dollar_volume=avg_dollar_volume,
                        source_tags=['market-wide-high-liquidity'],
                    )
                )
            except Exception:
                continue
        time.sleep(0.8 + random.uniform(0.0, 0.4))
    return candidates


def fetch_yahoo_universe_candidates(config: ScanConfig) -> ProviderFetchResult:
    candidates = _build_high_liquidity_candidates(config)
    rules = [
        '股票池来源：NASDAQ Trader 提供的美股上市代码表（nasdaqlisted + otherlisted）',
        '先获取全市场可交易股票代码，再做 leader-style 规则化预筛',
        f'价格定义：最新收盘价 > {int(config.min_price)} 美元',
        f'高流动性定义：近 20 日平均成交额 > {int(config.min_dollar_volume):,} 美元',
        '强趋势定义：最新收盘价 > SMA50',
        '强趋势定义：若可计算，则最新收盘价 > SMA200',
        '近高点定义：距离近阶段高点不超过 15%',
        '预筛通过后，再进入趋势模板与 VCP 结构评分',
    ]
    return ProviderFetchResult(
        candidates=candidates,
        mode_used='yahoo-only',
        warnings=['Finviz unavailable; fallback universe is rules-based market-wide U.S. equity list'],
        rules_applied=rules,
    )


def resolve_candidates(config: ScanConfig) -> ProviderFetchResult:
    if config.data_source == 'yahoo':
        return fetch_yahoo_universe_candidates(config)
    try:
        return fetch_finviz_candidates(config)
    except Exception as exc:
        fallback = fetch_yahoo_universe_candidates(config)
        fallback.warnings.append(f'Finviz prefilter failed: {exc}')
        return fallback


def load_price_history(symbol: str, config: ScanConfig) -> pd.DataFrame:
    cache_dir = config.cache_dir_path()
    cache_path = _cache_path(cache_dir, 'yahoo_history', f'{symbol}_{config.history_days}')
    cached = _load_json_cache(cache_path)
    if isinstance(cached, list) and cached:
        frame = pd.DataFrame(cached)
        frame['Date'] = pd.to_datetime(frame['Date'])
        return frame

    def _is_ignorable_error(message: str) -> bool:
        msg = message.lower()
        return ('possibly delisted' in msg) or ('no price data found' in msg) or ('no yahoo history' in msg) or ('empty cleaned yahoo history' in msg)

    for attempt in range(5):
        try:
            hist = load_yfinance_history(symbol, period=f'{max(1, config.history_days)}d', interval='1d', auto_adjust=False, timeout=12)
            if hist is None or hist.empty:
                raise RuntimeError(f'No Yahoo history for {symbol}')
            frame = normalize_daily_ohlcv_frame(hist)
            if frame.empty:
                raise RuntimeError(f'Empty cleaned Yahoo history for {symbol}')
            payload = frame.assign(Date=frame['Date'].dt.strftime('%Y-%m-%d')).to_dict(orient='records')
            _write_json_cache(cache_path, payload)
            return frame
        except Exception as exc:
            message = str(exc)
            if _is_ignorable_error(message):
                raise RuntimeError(f'IGNORABLE:{message}')
            if attempt == 4:
                raise RuntimeError(f'RETRY_EXHAUSTED:{message}')
            time.sleep((2 ** attempt) + random.uniform(0.0, 0.25))
