from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_OUT = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_simfin_growth_fundamentals.csv')
SIMFIN_BASE = 'https://prod.simfin.com/api/v3/companies/statements/compact'


@dataclass
class RawRow:
    symbol: str
    report_date: str
    fiscal_period: str
    revenue: float
    revenue_yoy: float
    eps: float
    eps_yoy: float


def fetch_json(url: str, headers: dict[str, str]) -> list | dict:
    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as resp:
        return __import__('json').load(resp)


def load_symbols(path: Path | None, symbols_arg: str | None) -> list[str]:
    symbols: list[str] = []
    if path:
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                s = line.strip().upper()
                if s:
                    symbols.append(s)
    if symbols_arg:
        for item in symbols_arg.split(','):
            s = item.strip().upper()
            if s:
                symbols.append(s)
    deduped: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        if s not in seen:
            deduped.append(s)
            seen.add(s)
    return deduped


def yoy(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev in (None, 0):
        return None
    return ((curr - prev) / abs(prev)) * 100.0


def parse_period(value: str | None) -> str:
    if not value:
        return ''
    text = value.strip().upper()
    if text in {'Q1', 'Q2', 'Q3', 'Q4'}:
        return text
    return text


def compact_url(api_key: str, statement: str, ticker: str) -> str:
    qs = urlencode({
        'statement': statement,
        'ticker': ticker,
        'period': 'quarterly',
        'api-key': api_key,
    })
    return f'{SIMFIN_BASE}?{qs}'


def extract_rows(symbol: str, income_payload: list) -> list[RawRow]:
    if not income_payload:
        return []
    item = income_payload[0]
    columns = item.get('columns', [])
    data = item.get('data', [])
    idx = {name: i for i, name in enumerate(columns)}
    required = ['Fiscal Period', 'Date', 'Revenue', 'Net Income']
    if any(name not in idx for name in required):
        return []

    quarterly: list[dict] = []
    for row in data:
        fiscal_period = parse_period(row[idx['Fiscal Period']])
        if fiscal_period not in {'Q1', 'Q2', 'Q3', 'Q4'}:
            continue
        revenue = row[idx['Revenue']]
        net_income = row[idx['Net Income']]
        shares = None
        for share_col in ('Shares (Diluted)', 'Shares (Basic)', 'Weighted Average Shares Diluted', 'Weighted Average Shares Basic'):
            if share_col in idx:
                shares = row[idx[share_col]]
                if shares not in (None, 0):
                    break
        eps = None
        if shares not in (None, 0) and net_income is not None:
            eps = float(net_income) / float(shares)
        quarterly.append({
            'report_date': row[idx['Date']],
            'fiscal_period': fiscal_period,
            'revenue': None if revenue is None else float(revenue),
            'eps': eps,
        })

    quarterly.sort(key=lambda r: r['report_date'])
    by_key = {(r['report_date'][:4], r['fiscal_period']): r for r in quarterly}
    output: list[RawRow] = []
    for r in quarterly:
        year = int(r['report_date'][:4])
        prev = by_key.get((str(year - 1), r['fiscal_period']))
        revenue_yoy = yoy(r['revenue'], None if prev is None else prev['revenue'])
        eps_yoy = yoy(r['eps'], None if prev is None else prev['eps'])
        if r['revenue'] is None or r['eps'] is None or revenue_yoy is None or eps_yoy is None:
            continue
        output.append(RawRow(symbol=symbol, report_date=r['report_date'], fiscal_period=r['fiscal_period'], revenue=r['revenue'], revenue_yoy=revenue_yoy, eps=r['eps'], eps_yoy=eps_yoy))
    return output


def write_rows(rows: Iterable[RawRow], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['symbol', 'report_date', 'fiscal_period', 'revenue', 'revenue_yoy', 'eps', 'eps_yoy']
    count = 0
    with out_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                'symbol': row.symbol,
                'report_date': row.report_date,
                'fiscal_period': row.fiscal_period,
                'revenue': f'{row.revenue:.6f}',
                'revenue_yoy': f'{row.revenue_yoy:.6f}',
                'eps': f'{row.eps:.6f}',
                'eps_yoy': f'{row.eps_yoy:.6f}',
            })
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description='Import quarterly growth fundamentals from SimFin into raw CSV shape used by local pipeline.')
    parser.add_argument('--api-key', default=os.getenv('SIMFIN_API_KEY', 'free'))
    parser.add_argument('--symbols', help='Comma-separated symbols')
    parser.add_argument('--symbols-file', help='One symbol per line')
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    parser.add_argument('--sleep-seconds', type=float, default=0.2)
    args = parser.parse_args()

    symbols = load_symbols(Path(args.symbols_file).expanduser().resolve() if args.symbols_file else None, args.symbols)
    if not symbols:
        print('no symbols provided', file=sys.stderr)
        return 2

    headers = {
        'accept': 'application/json',
        'user-agent': 'financial-services-simfin-import/1.0',
    }

    all_rows: list[RawRow] = []
    failures: list[str] = []
    for i, symbol in enumerate(symbols, start=1):
        try:
            url = compact_url(args.api_key, 'income', symbol)
            payload = fetch_json(url, headers)
            rows = extract_rows(symbol, payload)
            all_rows.extend(rows)
            print(f'[{i}/{len(symbols)}] {symbol}: rows={len(rows)}')
        except Exception as exc:
            failures.append(symbol)
            print(f'[{i}/{len(symbols)}] {symbol}: failed {exc}', file=sys.stderr)
        time.sleep(args.sleep_seconds)

    out_path = Path(args.output).expanduser().resolve()
    count = write_rows(all_rows, out_path)
    print(f'wrote raw rows={count} symbols={len(symbols)} failures={len(failures)} output={out_path}')
    if failures:
        print('failed symbols: ' + ','.join(failures), file=sys.stderr)
    return 0 if count > 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
