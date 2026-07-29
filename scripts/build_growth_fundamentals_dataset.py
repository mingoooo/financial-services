from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_OUT = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.csv')
DEFAULT_META = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.metadata.json')


@dataclass
class FundamentalRow:
    symbol: str
    report_date: str
    fiscal_period: str
    revenue: float
    revenue_yoy: float
    eps: float
    eps_yoy: float
    revenue_accel: float
    eps_accel: float
    source: str
    updated_at: str


FIELDNAMES = [field.name for field in FundamentalRow.__dataclass_fields__.values()]


def load_raw_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def parse_float(value: str | None) -> float | None:
    if value is None or value == '':
        return None
    return float(value)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace('.', '-')


def build_dataset(raw_rows: list[dict[str, str]], source_name: str) -> list[FundamentalRow]:
    rows_by_symbol: dict[str, list[dict[str, str]]] = {}
    for raw in raw_rows:
        symbol = normalize_symbol(raw['symbol'])
        rows_by_symbol.setdefault(symbol, []).append(raw)

    output: list[FundamentalRow] = []
    updated_at = datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    for symbol, rows in rows_by_symbol.items():
        ordered = sorted(rows, key=lambda row: row['report_date'])
        prior_revenue_yoy: float | None = None
        prior_eps_yoy: float | None = None
        for row in ordered:
            revenue = parse_float(row.get('revenue'))
            revenue_yoy = parse_float(row.get('revenue_yoy'))
            eps = parse_float(row.get('eps'))
            eps_yoy = parse_float(row.get('eps_yoy'))
            if None in (revenue, revenue_yoy, eps, eps_yoy):
                continue
            revenue_accel = 0.0 if prior_revenue_yoy is None else revenue_yoy - prior_revenue_yoy
            eps_accel = 0.0 if prior_eps_yoy is None else eps_yoy - prior_eps_yoy
            output.append(
                FundamentalRow(
                    symbol=symbol,
                    report_date=row['report_date'],
                    fiscal_period=row.get('fiscal_period', ''),
                    revenue=revenue,
                    revenue_yoy=revenue_yoy,
                    eps=eps,
                    eps_yoy=eps_yoy,
                    revenue_accel=revenue_accel,
                    eps_accel=eps_accel,
                    source=source_name,
                    updated_at=updated_at,
                )
            )
            prior_revenue_yoy = revenue_yoy
            prior_eps_yoy = eps_yoy

    return output


def write_dataset(rows: Iterable[FundamentalRow], out_path: Path, meta_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    with out_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    metadata = {
        'path': str(out_path),
        'row_count': len(rows),
        'updated_at': datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'schema': FIELDNAMES,
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Build standardized quarterly growth fundamentals dataset from a raw CSV source.')
    parser.add_argument('--input', required=True, help='Raw CSV with at least symbol, report_date, fiscal_period, revenue, revenue_yoy, eps, eps_yoy')
    parser.add_argument('--source-name', default='user-supplied')
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    parser.add_argument('--metadata', default=str(DEFAULT_META))
    args = parser.parse_args()

    raw_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    meta_path = Path(args.metadata).expanduser().resolve()

    raw_rows = load_raw_rows(raw_path)
    dataset = build_dataset(raw_rows, args.source_name)
    write_dataset(dataset, out_path, meta_path)
    print(f'wrote dataset rows={len(dataset)} path={out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
