#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.oneil_scanner.backtest_adapter import ScannerBacktestSignal, load_or_build_day_signals

PRICE_DIR = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/equity/usa/daily')
STATIC_CANDIDATE_FILE = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/oneil_candidates_latest.csv')
FUNDAMENTALS_DATASET = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.csv')
SCANNER_CACHE_DIR = Path('.cache/oneil-backtest-scanner-signals')
INITIAL_CAPITAL = 100000.0
MAX_POSITIONS = 8
MAX_NEW_POSITIONS_PER_DAY = 2
RISK_PER_TRADE = 0.01
MAX_ALLOC_PCT = 0.15
MAX_GROUP_POSITIONS = 1
MIN_BREAKOUT_STRENGTH_PCT = 1.5
MIN_VOLUME_RATIO = 1.2
MAX_GAP_PCT = 12.0
BREAKEVEN_TRIGGER_PCT = 10.0
SPY_ENTRY_FILTER = True
TRAILING_ATR_MULTIPLIER = 2.5
SLIPPAGE_BPS = 5.0
COMMISSION_PER_TRADE = 1.0
ENTRY_LAG_DAYS_GROWTH = 45
ENTRY_LAG_DAYS_BALANCED = 60
TOP_DYNAMIC_CANDIDATES_GROWTH = 30
TOP_DYNAMIC_CANDIDATES_BALANCED = 40
MIN_RS_PERCENTILE_GROWTH = 75.0
MIN_RS_PERCENTILE_BALANCED = 60.0
MAX_REPORT_AGE_DAYS = 140
MIN_AVG_DOLLAR_VOLUME = 20_000_000.0
GROUPS = {
    'semis': {'AMD', 'AVGO', 'ADI', 'MRVL', 'MU', 'NVDA', 'LRCX', 'MPWR', 'COHR'},
    'software': {'CRWD', 'DDOG', 'PLTR', 'FTNT', 'APP', 'FICO'},
    'infra_ai': {'VRT', 'SMCI', 'DELL', 'HPE'},
}


@dataclass
class FundamentalPoint:
    symbol: str
    report_date: datetime
    revenue_yoy: float
    eps_yoy: float
    revenue_accel: float
    eps_accel: float


@dataclass
class PortfolioTrade:
    symbol: str
    trigger_date: str | None
    entry_date: str
    entry_price: float
    stop_price: float
    exit_date: str
    exit_price: float
    shares: float
    allocated_capital: float
    pnl: float
    return_pct: float
    breakout_strength_pct: float
    volume_ratio: float
    exit_reason: str
    universe_score: float
    primary_pattern_family: str | None = None
    primary_pattern_type: str | None = None
    primary_pattern_variant: str | None = None
    secondary_patterns: list[str] = field(default_factory=list)
    breakout_level: float | None = None
    stop_reference: float | None = None


def symbol_group(symbol: str) -> str:
    for group, names in GROUPS.items():
        if symbol in names:
            return group
    return 'other'


def load_bars(symbol: str, start: datetime, end: datetime) -> list[dict]:
    path = PRICE_DIR / f'{symbol.lower()}.zip'
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as zf:
        inner = f'{symbol.lower()}.csv'
        if inner not in zf.namelist():
            inner = zf.namelist()[0]
        with zf.open(inner) as handle:
            out = []
            for line in io.TextIOWrapper(handle, encoding='utf-8'):
                parts = line.strip().split(',')
                if len(parts) < 6:
                    continue
                dt = datetime.strptime(parts[0], '%Y%m%d %H:%M')
                if not (start <= dt <= end):
                    continue
                out.append({
                    'date': dt,
                    'open': int(parts[1]) / 10000.0,
                    'high': int(parts[2]) / 10000.0,
                    'low': int(parts[3]) / 10000.0,
                    'close': int(parts[4]) / 10000.0,
                    'volume': float(parts[5]),
                })
            return out


def sma(values: list[float], n: int, idx: int) -> float | None:
    if idx + 1 < n:
        return None
    return sum(values[idx - n + 1: idx + 1]) / n


def atr(bars: list[dict], n: int, idx: int) -> float | None:
    if idx < 1 or idx + 1 < n:
        return None
    values = []
    for i in range(idx - n + 1, idx + 1):
        high = bars[i]['high']
        low = bars[i]['low']
        prev_close = bars[i - 1]['close'] if i > 0 else bars[i]['close']
        values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(values) / len(values)


def apply_slippage(price: float, side: str) -> float:
    factor = 1 + SLIPPAGE_BPS / 10000.0
    return price * factor if side == 'buy' else price / factor


def build_spy_entry_filter(start: datetime, end: datetime) -> dict[str, bool]:
    bars = load_bars('SPY', datetime(2019, 1, 1), end)
    closes = [bar['close'] for bar in bars]
    allowed: dict[str, bool] = {}
    for i, bar in enumerate(bars):
        if not (start <= bar['date'] <= end):
            continue
        s50 = sma(closes, 50, i)
        allowed[bar['date'].strftime('%Y-%m-%d')] = bool(s50 is not None and bar['close'] > s50)
    return allowed


def load_static_daily_candidates(path: Path, start: datetime, end: datetime) -> dict[str, dict[str, float]]:
    symbols = [row['symbol'] for row in csv.DictReader(path.open(encoding='utf-8')) if row['included'].lower() == 'true']
    out = {}
    day = start
    while day <= end:
        out[day.strftime('%Y-%m-%d')] = {symbol: 1.0 for symbol in symbols}
        day += timedelta(days=1)
    return out


def load_fundamentals(path: Path) -> dict[str, list[FundamentalPoint]]:
    out: dict[str, list[FundamentalPoint]] = {}
    with path.open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            point = FundamentalPoint(
                symbol=row['symbol'],
                report_date=datetime.strptime(row['report_date'], '%Y-%m-%d'),
                revenue_yoy=float(row['revenue_yoy']),
                eps_yoy=float(row['eps_yoy']),
                revenue_accel=float(row['revenue_accel']),
                eps_accel=float(row['eps_accel']),
            )
            out.setdefault(point.symbol, []).append(point)
    for symbol in out:
        out[symbol].sort(key=lambda item: item.report_date)
    return out


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def average_dollar_volume(bars: list[dict], day: datetime, window: int = 50) -> float | None:
    eligible = [bar for bar in bars if bar['date'] <= day]
    if len(eligible) < window:
        return None
    sample = eligible[-window:]
    return sum(bar['close'] * bar['volume'] for bar in sample) / window


def structure_score(bars: list[dict], day: datetime) -> float | None:
    eligible = [bar for bar in bars if bar['date'] <= day]
    if len(eligible) < 200:
        return None
    closes = [bar['close'] for bar in eligible]
    current = eligible[-1]['close']
    s200 = sum(closes[-200:]) / 200
    s50 = sum(closes[-50:]) / 50
    if s200 <= 0 or s50 <= 0:
        return None
    dist_200 = current / s200 - 1
    dist_50 = current / s50 - 1
    score = 0.0
    score += 1.0 - clamp(abs(dist_200 - 0.08) / 0.20, 0.0, 1.0)
    score += 1.0 - clamp(abs(dist_50 - 0.03) / 0.15, 0.0, 1.0)
    return score / 2.0


def relative_strength_raw(bars: list[dict], benchmark_bars: list[dict], day: datetime) -> float | None:
    eligible = [bar for bar in bars if bar['date'] <= day]
    bench = [bar for bar in benchmark_bars if bar['date'] <= day]
    if len(eligible) < 127 or len(bench) < 127:
        return None
    close_now = eligible[-1]['close']
    close_63 = eligible[-64]['close']
    close_126 = eligible[-127]['close']
    bench_now = bench[-1]['close']
    bench_63 = bench[-64]['close']
    bench_126 = bench[-127]['close']
    if min(close_63, close_126, bench_63, bench_126) <= 0:
        return None
    ret_3m = close_now / close_63 - 1
    ret_6m = close_now / close_126 - 1
    bench_ret_3m = bench_now / bench_63 - 1
    bench_ret_6m = bench_now / bench_126 - 1
    excess_3m = ret_3m - bench_ret_3m
    excess_6m = ret_6m - bench_ret_6m
    return excess_6m * 0.65 + excess_3m * 0.35


def percentile_rank(value: float, sorted_values: list[float]) -> float:
    if not sorted_values:
        return 0.0
    count = sum(1 for item in sorted_values if item <= value)
    if len(sorted_values) == 1:
        return 100.0
    return (count - 1) / (len(sorted_values) - 1) * 100.0


def inflection_score(points: list[FundamentalPoint]) -> float:
    if len(points) < 3:
        return 0.0
    latest = points[-1]
    prior = points[-2]
    older = points[-3]
    score = 0.0
    score += 1.0 if latest.eps_yoy > prior.eps_yoy > older.eps_yoy else 0.0
    score += 1.0 if latest.revenue_yoy > prior.revenue_yoy > older.revenue_yoy else 0.0
    score += 1.0 if latest.eps_accel > 0 and prior.eps_accel > 0 else 0.0
    score += 1.0 if latest.revenue_accel > 0 and prior.revenue_accel > 0 else 0.0
    return score / 4.0


def score_components(points: list[FundamentalPoint]) -> dict[str, float]:
    latest = points[-1]
    recent2 = points[-2:] if len(points) >= 2 else points
    recent3 = points[-3:] if len(points) >= 3 else points
    growth = 0.0
    growth += clamp(latest.revenue_yoy / 40.0, 0.0, 1.0)
    growth += clamp(latest.eps_yoy / 60.0, 0.0, 1.0)
    growth += 1.0 if len(recent2) == 2 and all(point.eps_yoy > 20 for point in recent2) else 0.0
    growth += 1.0 if len(recent2) == 2 and all(point.revenue_yoy > 15 for point in recent2) else 0.0
    growth_score = growth / 4.0
    quality = 0.0
    quality += 1.0 if latest.eps_accel > 0 else 0.0
    quality += 1.0 if latest.revenue_accel > 0 else 0.0
    quality += 1.0 if latest.eps_yoy > latest.revenue_yoy else 0.0
    if len(recent3) >= 2:
        eps_vals = [point.eps_yoy for point in recent3]
        rev_vals = [point.revenue_yoy for point in recent3]
        eps_span = max(eps_vals) - min(eps_vals)
        rev_span = max(rev_vals) - min(rev_vals)
        quality += 1.0 - clamp((eps_span + rev_span) / 120.0, 0.0, 1.0)
    quality_score = quality / 4.0
    return {'growth': growth_score, 'quality': quality_score, 'inflection': inflection_score(points)}


def build_dynamic_daily_candidates(dataset: Path, bars_by_symbol: dict[str, list[dict]], start: datetime, end: datetime, mode: str) -> dict[str, dict[str, float]]:
    fundamentals = load_fundamentals(dataset)
    if mode == 'dynamic-growth':
        entry_lag_days = ENTRY_LAG_DAYS_GROWTH
        top_candidates = TOP_DYNAMIC_CANDIDATES_GROWTH
        min_rs_percentile = MIN_RS_PERCENTILE_GROWTH
    else:
        entry_lag_days = ENTRY_LAG_DAYS_BALANCED
        top_candidates = TOP_DYNAMIC_CANDIDATES_BALANCED
        min_rs_percentile = MIN_RS_PERCENTILE_BALANCED
    out: dict[str, dict[str, float]] = {}
    current = start
    while current <= end:
        as_of = current - timedelta(days=entry_lag_days)
        scored: list[tuple[str, dict[str, float], float, float, float]] = []
        for symbol, points in fundamentals.items():
            eligible = [point for point in points if point.report_date <= as_of]
            if not eligible:
                continue
            latest = eligible[-1]
            report_age_days = (current - latest.report_date).days
            if report_age_days > MAX_REPORT_AGE_DAYS:
                continue
            bars = bars_by_symbol.get(symbol, [])
            rs = relative_strength_raw(bars, bars_by_symbol.get('SPY', []), current)
            liquidity = average_dollar_volume(bars, current)
            structure = structure_score(bars, current)
            if rs is None or liquidity is None or structure is None:
                continue
            if liquidity < MIN_AVG_DOLLAR_VOLUME:
                continue
            parts = score_components(eligible)
            parts['freshness_days'] = report_age_days
            scored.append((symbol, parts, rs, liquidity, structure))
        rs_values = sorted(item[2] for item in scored)
        ranked = []
        for symbol, parts, rs, liquidity, structure in scored:
            rs_pct = percentile_rank(rs, rs_values)
            if rs_pct < min_rs_percentile:
                continue
            rs_score = rs_pct / 100.0
            liquidity_score = clamp(math.log10(liquidity / MIN_AVG_DOLLAR_VOLUME + 1.0), 0.0, 1.0)
            freshness_score = 1.0 - clamp(parts['freshness_days'] / MAX_REPORT_AGE_DAYS, 0.0, 1.0)
            if mode == 'dynamic-growth':
                universe_score = parts['growth'] * 0.35 + parts['quality'] * 0.20 + parts['inflection'] * 0.14 + rs_score * 0.23 + liquidity_score * 0.05 + freshness_score * 0.03
            else:
                universe_score = parts['growth'] * 0.34 + parts['quality'] * 0.20 + parts['inflection'] * 0.16 + rs_score * 0.20 + liquidity_score * 0.05 + freshness_score * 0.05
            ranked.append((symbol, universe_score, rs_pct))
        ranked.sort(key=lambda item: (item[1], item[2], item[0]), reverse=True)
        out[current.strftime('%Y-%m-%d')] = {symbol: score for symbol, score, _pct in ranked[:top_candidates]}
        current += timedelta(days=1)
    return out


def rank_signals(signals: list[dict], universe_mode: str, bars_by_symbol: dict[str, list[dict]], day: str) -> list[dict]:
    if universe_mode == 'dynamic-balanced':
        for item in signals:
            bars = bars_by_symbol[item['symbol']]
            idx = next(i for i, bar in enumerate(bars) if bar['date'].strftime('%Y-%m-%d') == day)
            window_252 = bars[max(0, idx - 251):idx + 1]
            high_52w = max(bar['high'] for bar in window_252) if window_252 else item['entry_price']
            dist_high = item['entry_price'] / high_52w if high_52w > 0 else 0.0
            technical_score = 0.0
            if 0.90 <= dist_high <= 1.00:
                technical_score += 0.5
            if item['breakout_strength_pct'] >= 2.0:
                technical_score += 0.3
            if item['volume_ratio'] >= 1.5:
                technical_score += 0.2
            item['technical_score'] = technical_score
        return sorted(signals, key=lambda item: (item.get('technical_score', 0.0), item['universe_score'], item['volume_ratio'], item['breakout_strength_pct']), reverse=True)
    return sorted(signals, key=lambda item: (item['universe_score'], item['volume_ratio'], item['breakout_strength_pct']), reverse=True)




def build_bars_by_symbol(symbols: list[str], start: datetime, end: datetime) -> dict[str, list[dict]]:
    return {symbol: load_bars(symbol, start, end) for symbol in symbols}


def discover_price_zip_symbols(price_dir: Path = PRICE_DIR) -> list[str]:
    symbols: list[str] = []
    for path in sorted(price_dir.glob('*.zip')):
        symbol = path.stem.upper()
        if symbol == 'SPY':
            continue
        symbols.append(symbol)
    return symbols


def discover_scanner_symbols(price_dir: Path = PRICE_DIR) -> list[str]:
    return discover_price_zip_symbols(price_dir)


def bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            'Date': [bar['date'] for bar in bars],
            'Open': [bar['open'] for bar in bars],
            'High': [bar['high'] for bar in bars],
            'Low': [bar['low'] for bar in bars],
            'Close': [bar['close'] for bar in bars],
            'Volume': [bar['volume'] for bar in bars],
        }
    )


def build_raw_frames_by_symbol(bars_by_symbol: dict[str, list[dict]]) -> dict[str, pd.DataFrame]:
    return {symbol: bars_to_frame(bars) for symbol, bars in bars_by_symbol.items() if bars}


def _find_bar_index(bars: list[dict], day: str) -> int | None:
    return next((i for i, bar in enumerate(bars) if bar['date'].strftime('%Y-%m-%d') == day), None)


def _legacy_stop_fallback(bars: list[dict], trigger_idx: int) -> float | None:
    if trigger_idx is None or trigger_idx < 20:
        return None
    atr14 = atr(bars, 14, trigger_idx)
    if atr14 is None:
        return None
    recent = bars[trigger_idx - 20:trigger_idx]
    if len(recent) < 20:
        return None
    recent_low = min(item['low'] for item in recent)
    trigger_close = bars[trigger_idx]['close']
    return max(recent_low, trigger_close - atr14 * 1.8)


def build_scanner_entry_signal(
    scanner_signal: ScannerBacktestSignal,
    *,
    bars_by_symbol: dict[str, list[dict]],
    entry_day: str,
    warnings: list[str],
) -> dict | None:
    bars = bars_by_symbol.get(scanner_signal.symbol, [])
    trigger_idx = _find_bar_index(bars, scanner_signal.trigger_date or '') if scanner_signal.trigger_date else None
    entry_idx = _find_bar_index(bars, entry_day)
    if trigger_idx is None:
        warnings.append(f'Missing trigger bar for {scanner_signal.symbol} on {scanner_signal.trigger_date}; skipping signal.')
        return None
    if entry_idx is None:
        warnings.append(f'Missing next-day entry bar for {scanner_signal.symbol} on {entry_day}; skipping signal.')
        return None

    trigger_bar = bars[trigger_idx]
    entry_bar = bars[entry_idx]
    initial_stop_price = scanner_signal.stop_reference
    if initial_stop_price is None:
        initial_stop_price = _legacy_stop_fallback(bars, trigger_idx)
    if initial_stop_price is None or initial_stop_price <= 0:
        warnings.append(f'Unable to derive safe stop for {scanner_signal.symbol} on {scanner_signal.trigger_date}; skipping signal.')
        return None

    lookback = bars[max(0, trigger_idx - 20):trigger_idx]
    avg_vol20 = sum(bar['volume'] for bar in lookback) / len(lookback) if lookback else 0.0
    volume_ratio = trigger_bar['volume'] / avg_vol20 if avg_vol20 > 0 else 0.0
    breakout_level = scanner_signal.breakout_level or scanner_signal.entry_price_ref or 0.0
    breakout_strength = (trigger_bar['close'] / breakout_level - 1.0) * 100.0 if breakout_level > 0 else 0.0
    return {
        'symbol': scanner_signal.symbol,
        'trigger_date': scanner_signal.trigger_date,
        'entry_price': apply_slippage(entry_bar['open'], 'buy'),
        'initial_stop_price': initial_stop_price,
        'breakout_strength_pct': breakout_strength,
        'volume_ratio': volume_ratio,
        'universe_score': scanner_signal.ranking_score or 0.0,
        'ranking_score': scanner_signal.ranking_score or 0.0,
        'setup_score': scanner_signal.setup_score or 0.0,
        'quality_score': scanner_signal.quality_score or 0.0,
        'rs_score': scanner_signal.normalized_rs_score or 0.0,
        'primary_pattern_family': scanner_signal.primary_pattern_family,
        'primary_pattern_type': scanner_signal.primary_pattern_type,
        'primary_pattern_variant': scanner_signal.primary_pattern_variant,
        'secondary_patterns': list(scanner_signal.secondary_patterns),
        'breakout_level': scanner_signal.breakout_level,
        'stop_reference': scanner_signal.stop_reference,
    }


def rank_scanner_signals(signals: list[dict]) -> list[dict]:
    return sorted(
        signals,
        key=lambda item: (
            item.get('ranking_score', 0.0),
            item.get('setup_score', 0.0),
            item.get('quality_score', 0.0),
            item.get('rs_score', 0.0),
        ),
        reverse=True,
    )



def build_group_counts(positions: dict[str, dict]) -> dict[str, int]:
    group_counts: dict[str, int] = {}
    for position in positions.values():
        group = symbol_group(position['symbol'])
        group_counts[group] = group_counts.get(group, 0) + 1
    return group_counts



def mark_to_market_equity(cash: float, positions: dict[str, dict], bars_by_symbol: dict[str, list[dict]], day: str) -> float:
    equity = cash
    for symbol, position in positions.items():
        bars = bars_by_symbol[symbol]
        idx = next((i for i, bar in enumerate(bars) if bar['date'].strftime('%Y-%m-%d') == day), None)
        if idx is not None:
            equity += position['shares'] * bars[idx]['close']
    return equity



def load_daily_candidates(universe_mode: str, static_candidate_file: Path, fundamentals_dataset: Path, bars_by_symbol: dict[str, list[dict]], start: datetime, end: datetime) -> dict[str, dict[str, float]]:
    if universe_mode == 'static':
        return load_static_daily_candidates(static_candidate_file, start, end)
    return build_dynamic_daily_candidates(fundamentals_dataset, bars_by_symbol, start, end, mode=universe_mode)



def build_entry_signal(symbol: str, universe_score: float, bars_by_symbol: dict[str, list[dict]], day: str) -> dict | None:
    bars = bars_by_symbol[symbol]
    idx = next((i for i, bar in enumerate(bars) if bar['date'].strftime('%Y-%m-%d') == day), None)
    if idx is None or idx < 200:
        return None
    closes = [bar['close'] for bar in bars]
    volumes = [bar['volume'] for bar in bars]
    bar = bars[idx]
    s200 = sma(closes, 200, idx)
    atr14 = atr(bars, 14, idx)
    if s200 is None or atr14 is None or not (bar['close'] > s200):
        return None
    recent = bars[idx - 20:idx]
    if len(recent) < 20:
        return None
    pivot = max(item['high'] for item in recent)
    recent_low = min(item['low'] for item in recent)
    avg_vol20 = sum(volumes[idx - 20:idx]) / 20
    breakout_strength = (bar['close'] / pivot - 1) * 100 if pivot > 0 else 0.0
    volume_ratio = bar['volume'] / avg_vol20 if avg_vol20 > 0 else 0.0
    prev_close = bars[idx - 1]['close']
    gap_pct = abs(bar['open'] / prev_close - 1) * 100 if prev_close > 0 else 0.0
    if not (bar['close'] >= pivot and bar['volume'] >= avg_vol20 and bar['close'] > bar['open'] and breakout_strength >= MIN_BREAKOUT_STRENGTH_PCT and volume_ratio >= MIN_VOLUME_RATIO and gap_pct <= MAX_GAP_PCT):
        return None
    return {
        'symbol': symbol,
        'entry_price': apply_slippage(bar['close'], 'buy'),
        'initial_stop_price': max(recent_low, bar['close'] - atr14 * 1.8),
        'breakout_strength_pct': breakout_strength,
        'volume_ratio': volume_ratio,
        'universe_score': universe_score,
    }

def run_backtest(
    start: datetime,
    end: datetime,
    universe_mode: str,
    static_candidate_file: Path,
    fundamentals_dataset: Path,
    *,
    signal_source: str = 'legacy',
    scanner_cache_dir: Path = SCANNER_CACHE_DIR,
    refresh_scanner_cache: bool = False,
    pattern_families: list[str] | None = None,
    pattern_types: list[str] | None = None,
    min_dollar_volume: float = MIN_AVG_DOLLAR_VOLUME,
) -> dict:
    warmup_start = start - timedelta(days=260)
    scanner_warnings: list[str] = []
    scanner_signal_symbols_seen: set[str] = set()
    raw_frames_by_symbol: dict[str, pd.DataFrame] = {}
    benchmark_frame: pd.DataFrame | None = None

    if signal_source == 'scanner':
        tradable_symbols = [symbol for symbol in discover_scanner_symbols() if symbol != 'SPY']
        all_symbols = sorted(set(tradable_symbols) | {'SPY'})
        bars_by_symbol = build_bars_by_symbol(all_symbols, warmup_start, end)
        raw_frames_by_symbol = build_raw_frames_by_symbol({symbol: bars_by_symbol[symbol] for symbol in tradable_symbols if symbol in bars_by_symbol})
        benchmark_frame = bars_to_frame(bars_by_symbol['SPY']) if bars_by_symbol.get('SPY') else None
        daily_candidates: dict[str, dict[str, float]] = {}
    elif universe_mode == 'static':
        bars_by_symbol = {}
        daily_candidates = load_daily_candidates(universe_mode, static_candidate_file, fundamentals_dataset, bars_by_symbol, start, end)
        all_symbols = sorted({symbol for day_map in daily_candidates.values() for symbol in day_map} | {'SPY'})
    else:
        fundamentals = load_fundamentals(fundamentals_dataset)
        all_symbols = sorted(set(fundamentals.keys()) | {'SPY'})
        bars_by_symbol = build_bars_by_symbol(all_symbols, warmup_start, end)
        daily_candidates = load_daily_candidates(universe_mode, static_candidate_file, fundamentals_dataset, bars_by_symbol, start, end)
        all_symbols = sorted({symbol for day_map in daily_candidates.values() for symbol in day_map} | {'SPY'})
    if signal_source != 'scanner':
        bars_by_symbol = build_bars_by_symbol(all_symbols, warmup_start, end)
    spy_filter = build_spy_entry_filter(start, end) if SPY_ENTRY_FILTER else {}

    trading_days = sorted({bar['date'].strftime('%Y-%m-%d') for symbol in all_symbols if symbol != 'SPY' for bar in bars_by_symbol[symbol] if start <= bar['date'] <= end})
    cash = INITIAL_CAPITAL
    positions: dict[str, dict] = {}
    trades: list[PortfolioTrade] = []
    equity_curve: list[dict] = []
    monthly_pnl: dict[str, float] = {}
    signal_trade_count = 0

    for day_index, day in enumerate(trading_days):
        group_counts = build_group_counts(positions)

        exits = []
        for symbol, position in list(positions.items()):
            bars = bars_by_symbol[symbol]
            idx = next((i for i, bar in enumerate(bars) if bar['date'].strftime('%Y-%m-%d') == day), None)
            if idx is None:
                continue
            closes = [bar['close'] for bar in bars]
            bar = bars[idx]
            s20 = sma(closes, 20, idx)
            atr14 = atr(bars, 14, idx)
            if s20 is None or atr14 is None:
                continue
            position['highest_close'] = max(position['highest_close'], bar['close'])
            if position['highest_close'] >= position['entry_price'] * (1 + BREAKEVEN_TRIGGER_PCT / 100):
                position['stop_price'] = max(position['stop_price'], position['entry_price'])
            position['stop_price'] = max(position['stop_price'], position['highest_close'] - atr14 * TRAILING_ATR_MULTIPLIER)
            if bar['close'] < s20:
                position['below_sma20'] += 1
            else:
                position['below_sma20'] = 0
            exit_price = None
            exit_reason = None
            if bar['open'] < position['stop_price']:
                exit_price = apply_slippage(bar['open'], 'sell')
                exit_reason = 'gap_stop'
            elif bar['low'] <= position['stop_price']:
                exit_price = apply_slippage(position['stop_price'], 'sell')
                exit_reason = 'stop'
            elif position['below_sma20'] >= 2:
                exit_price = apply_slippage(bar['close'], 'sell')
                exit_reason = 'lost_sma20'
            if exit_price is not None:
                proceeds = position['shares'] * exit_price - COMMISSION_PER_TRADE
                cash += proceeds
                pnl = proceeds - position['cost_basis']
                trades.append(
                    PortfolioTrade(
                        symbol=symbol,
                        trigger_date=position.get('trigger_date'),
                        entry_date=position['entry_date'],
                        entry_price=position['entry_price'],
                        stop_price=position['initial_stop_price'],
                        exit_date=day,
                        exit_price=exit_price,
                        shares=position['shares'],
                        allocated_capital=position['cost_basis'],
                        pnl=pnl,
                        return_pct=(proceeds / position['cost_basis'] - 1) * 100,
                        breakout_strength_pct=position['breakout_strength_pct'],
                        volume_ratio=position['volume_ratio'],
                        exit_reason=exit_reason,
                        universe_score=position['universe_score'],
                        primary_pattern_family=position.get('primary_pattern_family'),
                        primary_pattern_type=position.get('primary_pattern_type'),
                        primary_pattern_variant=position.get('primary_pattern_variant'),
                        secondary_patterns=list(position.get('secondary_patterns', [])),
                        breakout_level=position.get('breakout_level'),
                        stop_reference=position.get('stop_reference'),
                    )
                )
                monthly_pnl[day[:7]] = monthly_pnl.get(day[:7], 0.0) + pnl
                exits.append(symbol)
        for symbol in exits:
            positions.pop(symbol, None)

        mark_to_market = mark_to_market_equity(cash, positions, bars_by_symbol, day)
        equity_curve.append({'date': day, 'equity': mark_to_market})

        if SPY_ENTRY_FILTER and not spy_filter.get(day, False):
            continue
        if len(positions) >= MAX_POSITIONS:
            continue

        signals = []
        if signal_source == 'scanner':
            if day_index > 0:
                trigger_day = trading_days[day_index - 1]
                day_cache = load_or_build_day_signals(
                    cache_dir=scanner_cache_dir,
                    day=trigger_day,
                    frames_by_symbol=raw_frames_by_symbol,
                    refresh=refresh_scanner_cache,
                    detector_families=pattern_families,
                    pattern_types=pattern_types,
                    min_avg_dollar_volume=min_dollar_volume,
                    benchmark_frame=benchmark_frame,
                )
                scanner_warnings.extend(day_cache.warnings)
                for scanner_signal in day_cache.signals:
                    scanner_signal_symbols_seen.add(scanner_signal.symbol)
                    if scanner_signal.symbol in positions or scanner_signal.symbol == 'SPY':
                        continue
                    group = symbol_group(scanner_signal.symbol)
                    if group_counts.get(group, 0) >= MAX_GROUP_POSITIONS:
                        continue
                    signal = build_scanner_entry_signal(
                        scanner_signal,
                        bars_by_symbol=bars_by_symbol,
                        entry_day=day,
                        warnings=scanner_warnings,
                    )
                    if signal is not None:
                        signal_trade_count += 1
                        signals.append(signal)
                signals = rank_scanner_signals(signals)
        else:
            todays_candidates = daily_candidates.get(day, {})
            for symbol, universe_score in todays_candidates.items():
                if symbol in positions or symbol == 'SPY':
                    continue
                group = symbol_group(symbol)
                if group_counts.get(group, 0) >= MAX_GROUP_POSITIONS:
                    continue
                signal = build_entry_signal(symbol, universe_score, bars_by_symbol, day)
                if signal is not None:
                    signal_trade_count += 1
                    signals.append(signal)
            signals = rank_signals(signals, universe_mode, bars_by_symbol, day)

        opened_today = 0
        for signal in signals:
            if opened_today >= MAX_NEW_POSITIONS_PER_DAY or len(positions) >= MAX_POSITIONS:
                break
            group = symbol_group(signal['symbol'])
            if group_counts.get(group, 0) >= MAX_GROUP_POSITIONS:
                continue
            risk_per_share = signal['entry_price'] - signal['initial_stop_price']
            if risk_per_share <= 0:
                continue
            risk_budget = mark_to_market * RISK_PER_TRADE
            shares_by_risk = risk_budget / risk_per_share
            shares_by_alloc = (mark_to_market * MAX_ALLOC_PCT) / signal['entry_price']
            shares = min(shares_by_risk, shares_by_alloc)
            gross_cost = shares * signal['entry_price']
            total_cost = gross_cost + COMMISSION_PER_TRADE
            if total_cost > cash:
                shares = max(0.0, (cash - COMMISSION_PER_TRADE) / signal['entry_price'])
                gross_cost = shares * signal['entry_price']
                total_cost = gross_cost + COMMISSION_PER_TRADE
            if shares <= 0 or total_cost > cash:
                continue
            cash -= total_cost
            positions[signal['symbol']] = {
                'symbol': signal['symbol'],
                'trigger_date': signal.get('trigger_date'),
                'entry_date': day,
                'entry_price': signal['entry_price'],
                'initial_stop_price': signal['initial_stop_price'],
                'stop_price': signal['initial_stop_price'],
                'shares': shares,
                'cost_basis': total_cost,
                'highest_close': signal['entry_price'],
                'below_sma20': 0,
                'breakout_strength_pct': signal['breakout_strength_pct'],
                'volume_ratio': signal['volume_ratio'],
                'universe_score': signal['universe_score'],
                'primary_pattern_family': signal.get('primary_pattern_family'),
                'primary_pattern_type': signal.get('primary_pattern_type'),
                'primary_pattern_variant': signal.get('primary_pattern_variant'),
                'secondary_patterns': list(signal.get('secondary_patterns', [])),
                'breakout_level': signal.get('breakout_level'),
                'stop_reference': signal.get('stop_reference'),
            }
            group_counts[group] = group_counts.get(group, 0) + 1
            opened_today += 1

    for symbol, position in list(positions.items()):
        bars = bars_by_symbol[symbol]
        last = next(bar for bar in reversed(bars) if bar['date'] <= end)
        exit_price = apply_slippage(last['close'], 'sell')
        proceeds = position['shares'] * exit_price - COMMISSION_PER_TRADE
        cash += proceeds
        pnl = proceeds - position['cost_basis']
        trades.append(
            PortfolioTrade(
                symbol=symbol,
                trigger_date=position.get('trigger_date'),
                entry_date=position['entry_date'],
                entry_price=position['entry_price'],
                stop_price=position['initial_stop_price'],
                exit_date=last['date'].strftime('%Y-%m-%d'),
                exit_price=exit_price,
                shares=position['shares'],
                allocated_capital=position['cost_basis'],
                pnl=pnl,
                return_pct=(proceeds / position['cost_basis'] - 1) * 100,
                breakout_strength_pct=position['breakout_strength_pct'],
                volume_ratio=position['volume_ratio'],
                exit_reason='eod',
                universe_score=position['universe_score'],
                primary_pattern_family=position.get('primary_pattern_family'),
                primary_pattern_type=position.get('primary_pattern_type'),
                primary_pattern_variant=position.get('primary_pattern_variant'),
                secondary_patterns=list(position.get('secondary_patterns', [])),
                breakout_level=position.get('breakout_level'),
                stop_reference=position.get('stop_reference'),
            )
        )
        monthly_pnl[last['date'].strftime('%Y-%m')] = monthly_pnl.get(last['date'].strftime('%Y-%m'), 0.0) + pnl

    final_equity = cash
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    for point in equity_curve:
        peak = max(peak, point['equity'])
        max_dd = max(max_dd, (peak - point['equity']) / peak if peak > 0 else 0.0)
    wins = [trade for trade in trades if trade.pnl > 0]
    avg_return = sum(trade.return_pct for trade in trades) / len(trades) if trades else 0.0
    gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
    gross_loss = abs(sum(trade.pnl for trade in trades if trade.pnl < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    years = max((end - start).days / 365.25, 1e-9)
    annualized = ((final_equity / INITIAL_CAPITAL) ** (1 / years) - 1) * 100 if final_equity > 0 else 0.0
    candidate_count = len(scanner_signal_symbols_seen) if signal_source == 'scanner' else len({symbol for day_map in daily_candidates.values() for symbol in day_map})
    warnings = list(dict.fromkeys(scanner_warnings))
    return {
        'signal_source': signal_source,
        'universe_mode': universe_mode,
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
        'candidate_count': candidate_count,
        'scanned_universe_count': len(raw_frames_by_symbol) if signal_source == 'scanner' else None,
        'signal_trade_count': signal_trade_count,
        'executed_trade_count': len(trades),
        'win_rate_pct': round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        'average_trade_return_pct': round(avg_return, 4),
        'initial_capital': INITIAL_CAPITAL,
        'final_equity': round(final_equity, 2),
        'total_return_pct': round((final_equity / INITIAL_CAPITAL - 1) * 100, 2),
        'annualized_return_pct': round(annualized, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'profit_factor': round(profit_factor, 3) if trades else 0.0,
        'monthly_pnl': monthly_pnl,
        'equity_curve': equity_curve,
        'warnings': warnings,
        'trades': [asdict(trade) for trade in trades],
    }


def _parse_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(',') if item.strip()]
    return items or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Unified event-driven backtest for ONeil-style strategy with static, dynamic-growth, or dynamic-balanced universe modes.')
    parser.add_argument('--start', default='2025-06-30')
    parser.add_argument('--end', default='2026-06-29')
    parser.add_argument('--universe-mode', choices=['static', 'dynamic-growth', 'dynamic-balanced'], default='static')
    parser.add_argument('--signal-source', choices=['legacy', 'scanner'], default='legacy')
    parser.add_argument('--candidate-file', default=str(STATIC_CANDIDATE_FILE))
    parser.add_argument('--fundamentals-dataset', default=str(FUNDAMENTALS_DATASET))
    parser.add_argument('--scanner-cache-dir', default=str(SCANNER_CACHE_DIR))
    parser.add_argument('--refresh-scanner-cache', action='store_true')
    parser.add_argument('--pattern-families')
    parser.add_argument('--pattern-types')
    parser.add_argument('--min-dollar-volume', type=float, default=MIN_AVG_DOLLAR_VOLUME)
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)
    result = run_backtest(
        start=datetime.strptime(args.start, '%Y-%m-%d'),
        end=datetime.strptime(args.end, '%Y-%m-%d'),
        universe_mode=args.universe_mode,
        static_candidate_file=Path(args.candidate_file),
        fundamentals_dataset=Path(args.fundamentals_dataset),
        signal_source=args.signal_source,
        scanner_cache_dir=Path(args.scanner_cache_dir),
        refresh_scanner_cache=args.refresh_scanner_cache,
        pattern_families=_parse_csv_list(args.pattern_families),
        pattern_types=_parse_csv_list(args.pattern_types),
        min_dollar_volume=args.min_dollar_volume,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
