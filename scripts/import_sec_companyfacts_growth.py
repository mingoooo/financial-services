from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

DEFAULT_OUT = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_sec_growth_fundamentals.csv')
TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
COMPANYFACTS_URL = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
DEFAULT_USER_AGENT = 'financial-services-sec-import/1.0 contact: local-research@example.com'

REVENUE_TAGS = [
    ('us-gaap', 'RevenueFromContractWithCustomerExcludingAssessedTax'),
    ('us-gaap', 'Revenues'),
    ('us-gaap', 'SalesRevenueNet'),
    ('us-gaap', 'SalesRevenueGoodsNet'),
    ('us-gaap', 'RevenueFromContractWithCustomerIncludingAssessedTax'),
]
NET_INCOME_TAGS = [
    ('us-gaap', 'NetIncomeLoss'),
    ('us-gaap', 'ProfitLoss'),
]
EPS_DILUTED_TAGS = [
    ('us-gaap', 'EarningsPerShareDiluted'),
    ('us-gaap', 'IncomeLossFromContinuingOperationsPerDilutedShare'),
]
EPS_BASIC_TAGS = [
    ('us-gaap', 'EarningsPerShareBasic'),
]
SHARES_DILUTED_TAGS = [
    ('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding'),
]
SHARES_BASIC_TAGS = [
    ('us-gaap', 'WeightedAverageNumberOfSharesOutstandingBasic'),
]
QUARTERS = {'Q1', 'Q2', 'Q3', 'Q4'}
ANNUAL_FORMS = {'10-K', '10-K/A', '20-F', '20-F/A'}
QUARTERLY_FORMS = {'10-Q', '10-Q/A', '6-K', '6-K/A'}


@dataclass
class RawRow:
    symbol: str
    report_date: str
    fiscal_period: str
    revenue: float
    revenue_yoy: float
    eps: float
    eps_yoy: float


def fetch_json(url: str, headers: dict[str, str]) -> dict | list:
    req = Request(url, headers=headers)
    with urlopen(req, timeout=90) as response:
        return json.load(response)


def load_symbols(path: Path | None, symbols_arg: str | None) -> list[str]:
    symbols: list[str] = []
    if path:
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                symbol = line.strip().upper()
                if symbol:
                    symbols.append(symbol)
    if symbols_arg:
        for item in symbols_arg.split(','):
            symbol = item.strip().upper()
            if symbol:
                symbols.append(symbol)
    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol not in seen:
            deduped.append(symbol)
            seen.add(symbol)
    return deduped


def fiscal_period_from_fp(fp: str | None) -> str:
    text = (fp or '').strip().upper()
    return text if text in QUARTERS else ''


def fiscal_period_from_frame(frame: str | None) -> str:
    text = (frame or '').strip().upper()
    match = re.search(r'Q([1-4])$', text)
    return f'Q{match.group(1)}' if match else ''


def duration_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return (datetime.strptime(end, '%Y-%m-%d') - datetime.strptime(start, '%Y-%m-%d')).days
    except Exception:
        return None


def quarter_length_ok(days: int | None) -> bool:
    return days is None or 70 <= days <= 110


def annual_or_ytd_length(days: int | None) -> bool:
    return days is not None and days > 110


def parse_fact_rows(units: dict) -> list[dict]:
    preferred_name = None
    for unit_name in ('USD/shares', 'USD / shares', 'USD', 'shares'):
        if unit_name in units:
            preferred_name = unit_name
            break
    if preferred_name is None and units:
        preferred_name = next(iter(units.keys()))
    if preferred_name is None:
        return []

    rows: list[dict] = []
    for item in units[preferred_name]:
        form = (item.get('form') or '').upper()
        if form not in QUARTERLY_FORMS | ANNUAL_FORMS:
            continue
        end = item.get('end')
        value = item.get('val')
        if not end or value in (None, ''):
            continue
        start = item.get('start')
        frame = (item.get('frame') or '').strip()
        fp = fiscal_period_from_frame(frame) or fiscal_period_from_fp(item.get('fp'))
        days = duration_days(start, end)
        rows.append(
            {
                'end': end,
                'start': start or '',
                'duration_days': days,
                'frame': frame,
                'fp': fp,
                'fy': item.get('fy'),
                'form': form,
                'filed': item.get('filed') or '',
                'value': float(value),
            }
        )
    rows.sort(key=lambda row: (row['end'], row['filed']))
    return rows


def choose_tag_rows(facts: dict, tag_options: list[tuple[str, str]]) -> list[dict]:
    for taxonomy, tag in tag_options:
        units = facts.get(taxonomy, {}).get(tag, {}).get('units', {})
        if not units:
            continue
        rows = parse_fact_rows(units)
        if rows:
            return rows
    return []


def build_single_quarter_map(rows: list[dict]) -> dict[tuple[str, str], dict]:
    direct: dict[tuple[str, str], dict] = {}
    cumulative: dict[str, dict[str, dict]] = {}

    for row in rows:
        fp = row['fp']
        if fp not in QUARTERS:
            continue
        key = (row['end'], fp)
        has_frame = bool(fiscal_period_from_frame(row['frame']))
        if quarter_length_ok(row['duration_days']) and (row['form'] in QUARTERLY_FORMS or has_frame):
            incumbent = direct.get(key)
            incumbent_has_frame = bool(fiscal_period_from_frame(incumbent['frame'])) if incumbent else False
            better = incumbent is None
            if incumbent is not None:
                better = (
                    (has_frame and not incumbent_has_frame)
                    or (has_frame == incumbent_has_frame and (row['filed'], row['form']) > (incumbent['filed'], incumbent['form']))
                )
            if better:
                direct[key] = row
        elif annual_or_ytd_length(row['duration_days']):
            cumulative.setdefault(row['end'], {})[fp] = row

    result = dict(direct)

    for end, fp_rows in cumulative.items():
        ordered = [fp_rows[q] for q in ('Q1', 'Q2', 'Q3', 'Q4') if q in fp_rows]
        if not ordered:
            continue
        q1 = fp_rows.get('Q1')
        if q1 and (end, 'Q1') not in result:
            result[(end, 'Q1')] = q1
        q2 = fp_rows.get('Q2')
        if q1 and q2 and (end, 'Q2') not in result:
            clone = dict(q2)
            clone['value'] = q2['value'] - q1['value']
            result[(end, 'Q2')] = clone
        q3 = fp_rows.get('Q3')
        if q2 and q3 and (end, 'Q3') not in result:
            clone = dict(q3)
            clone['value'] = q3['value'] - q2['value']
            result[(end, 'Q3')] = clone
        q4 = fp_rows.get('Q4') or fp_rows.get('FY')
        if q3 and q4 and (end, 'Q4') not in result:
            clone = dict(q4)
            clone['fp'] = 'Q4'
            clone['value'] = q4['value'] - q3['value']
            result[(end, 'Q4')] = clone

    return result


def yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return ((current - previous) / abs(previous)) * 100.0


def period_sort_key(end: str, fp: str) -> tuple[int, int, int, int]:
    dt = datetime.strptime(end, '%Y-%m-%d')
    return (dt.year, dt.month, dt.day, int(fp[1]))


def resolve_end_conflicts(rows_by_key: dict[tuple[str, str], dict[str, float | str | None]]) -> dict[tuple[str, str], dict[str, float | str | None]]:
    by_end: dict[str, list[tuple[str, str]]] = {}
    for key in rows_by_key:
        by_end.setdefault(key[0], []).append(key)

    resolved: dict[tuple[str, str], dict[str, float | str | None]] = {}
    last_quarter_num = None
    for end in sorted(by_end.keys()):
        keys = by_end[end]
        if len(keys) == 1:
            key = keys[0]
            resolved[key] = rows_by_key[key]
            last_quarter_num = int(key[1][1])
            continue
        keys_sorted = sorted(keys, key=lambda item: int(item[1][1]))
        chosen = None
        if last_quarter_num is not None:
            expected = 1 if last_quarter_num == 4 else last_quarter_num + 1
            for key in keys_sorted:
                if int(key[1][1]) == expected:
                    chosen = key
                    break
        if chosen is None:
            chosen = keys_sorted[-1]
        resolved[chosen] = rows_by_key[chosen]
        last_quarter_num = int(chosen[1][1])
    return resolved


def build_rows_for_symbol(symbol: str, companyfacts: dict) -> list[RawRow]:
    facts = companyfacts.get('facts', {})
    revenue_map = build_single_quarter_map(choose_tag_rows(facts, REVENUE_TAGS))
    net_income_map = build_single_quarter_map(choose_tag_rows(facts, NET_INCOME_TAGS))
    eps_diluted_map = build_single_quarter_map(choose_tag_rows(facts, EPS_DILUTED_TAGS))
    eps_basic_map = build_single_quarter_map(choose_tag_rows(facts, EPS_BASIC_TAGS))
    shares_diluted_map = build_single_quarter_map(choose_tag_rows(facts, SHARES_DILUTED_TAGS))
    shares_basic_map = build_single_quarter_map(choose_tag_rows(facts, SHARES_BASIC_TAGS))

    quarter_keys = sorted(set(revenue_map) | set(net_income_map) | set(eps_diluted_map) | set(eps_basic_map), key=lambda item: period_sort_key(item[0], item[1]))
    rows_by_key: dict[tuple[str, str], dict[str, float | str | None]] = {}

    for end, fp in quarter_keys:
        revenue_item = revenue_map.get((end, fp))
        revenue = revenue_item['value'] if revenue_item else None
        eps_item = eps_diluted_map.get((end, fp)) or eps_basic_map.get((end, fp))
        eps = eps_item['value'] if eps_item else None
        if eps is None:
            net_income_item = net_income_map.get((end, fp))
            shares_item = shares_diluted_map.get((end, fp)) or shares_basic_map.get((end, fp))
            if net_income_item and shares_item and shares_item['value'] not in (None, 0):
                eps = float(net_income_item['value']) / float(shares_item['value'])
        rows_by_key[(end, fp)] = {
            'report_date': end,
            'fiscal_period': fp,
            'revenue': None if revenue is None else float(revenue),
            'eps': None if eps is None else float(eps),
        }

    rows_by_key = resolve_end_conflicts(rows_by_key)

    output: list[RawRow] = []
    sorted_keys = sorted(rows_by_key, key=lambda item: period_sort_key(item[0], item[1]))
    for end, fp in sorted_keys:
        current = rows_by_key[(end, fp)]
        previous = None
        end_dt = datetime.strptime(end, '%Y-%m-%d')
        for candidate_end, candidate_fp in sorted_keys:
            if candidate_fp != fp or candidate_end == end:
                continue
            candidate_dt = datetime.strptime(candidate_end, '%Y-%m-%d')
            delta = abs((end_dt - candidate_dt).days)
            if 360 <= delta <= 370:
                previous = rows_by_key[(candidate_end, candidate_fp)]
                break
        revenue = current['revenue']
        eps = current['eps']
        revenue_yoy = yoy(revenue if isinstance(revenue, float) else None, previous['revenue'] if previous else None)
        eps_yoy = yoy(eps if isinstance(eps, float) else None, previous['eps'] if previous else None)
        if revenue is None or eps is None or revenue_yoy is None or eps_yoy is None:
            continue
        output.append(
            RawRow(
                symbol=symbol,
                report_date=str(current['report_date']),
                fiscal_period=str(current['fiscal_period']),
                revenue=float(revenue),
                revenue_yoy=revenue_yoy,
                eps=float(eps),
                eps_yoy=eps_yoy,
            )
        )
    return output


def load_ticker_mapping(headers: dict[str, str]) -> dict[str, str]:
    payload = fetch_json(TICKERS_URL, headers)
    mapping: dict[str, str] = {}
    if isinstance(payload, dict):
        for _, row in payload.items():
            ticker = str(row.get('ticker', '')).upper()
            cik = str(row.get('cik_str', '')).zfill(10)
            if ticker and cik:
                mapping[ticker] = cik
    return mapping


def write_rows(rows: Iterable[RawRow], out_path: Path) -> int:
    fieldnames = ['symbol', 'report_date', 'fiscal_period', 'revenue', 'revenue_yoy', 'eps', 'eps_yoy']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    'symbol': row.symbol,
                    'report_date': row.report_date,
                    'fiscal_period': row.fiscal_period,
                    'revenue': f'{row.revenue:.6f}',
                    'revenue_yoy': f'{row.revenue_yoy:.6f}',
                    'eps': f'{row.eps:.6f}',
                    'eps_yoy': f'{row.eps_yoy:.6f}',
                }
            )
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description='Import quarterly growth fundamentals from SEC Company Facts into raw CSV shape used by local pipeline.')
    parser.add_argument('--symbols', help='Comma-separated symbols')
    parser.add_argument('--symbols-file', help='One symbol per line')
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    parser.add_argument('--sleep-seconds', type=float, default=0.2)
    parser.add_argument('--user-agent', default=DEFAULT_USER_AGENT, help='SEC requests should identify the client and contact')
    args = parser.parse_args()

    symbols = load_symbols(Path(args.symbols_file).expanduser().resolve() if args.symbols_file else None, args.symbols)
    if not symbols:
        print('no symbols provided', file=sys.stderr)
        return 2

    headers = {'accept': 'application/json', 'user-agent': args.user_agent}
    ticker_map = load_ticker_mapping(headers)
    all_rows: list[RawRow] = []
    failures: list[str] = []

    for index, symbol in enumerate(symbols, start=1):
        cik = ticker_map.get(symbol)
        if not cik:
            failures.append(symbol)
            print(f'[{index}/{len(symbols)}] {symbol}: missing CIK mapping', file=sys.stderr)
            continue
        try:
            companyfacts = fetch_json(COMPANYFACTS_URL.format(cik=cik), headers)
            rows = build_rows_for_symbol(symbol, companyfacts)
            all_rows.extend(rows)
            print(f'[{index}/{len(symbols)}] {symbol}: cik={cik} rows={len(rows)}')
        except Exception as exc:
            failures.append(symbol)
            print(f'[{index}/{len(symbols)}] {symbol}: failed {exc}', file=sys.stderr)
        time.sleep(args.sleep_seconds)

    out_path = Path(args.output).expanduser().resolve()
    count = write_rows(all_rows, out_path)
    print(f'wrote raw rows={count} symbols={len(symbols)} failures={len(failures)} output={out_path}')
    if failures:
        print('failed symbols: ' + ','.join(failures), file=sys.stderr)
    return 0 if count > 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
