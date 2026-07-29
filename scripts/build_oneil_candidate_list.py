from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATASET = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.csv')
DEFAULT_LATEST = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/oneil_candidates_latest.csv')
DEFAULT_SNAPSHOTS = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/snapshots')


@dataclass
class CandidateRow:
    as_of_date: str
    symbol: str
    passes_revenue_growth: bool
    passes_eps_growth: bool
    passes_acceleration: bool
    candidate_score: int
    included: bool


FIELDNAMES = [field.name for field in CandidateRow.__dataclass_fields__.values()]


def parse_date(text: str) -> datetime:
    return datetime.strptime(text, '%Y-%m-%d')


def main() -> int:
    parser = argparse.ArgumentParser(description='Build O\'Neil-style fundamentals candidate universe snapshot from standardized dataset.')
    parser.add_argument('--dataset', default=str(DEFAULT_DATASET))
    parser.add_argument('--as-of-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--latest-output', default=str(DEFAULT_LATEST))
    parser.add_argument('--snapshots-dir', default=str(DEFAULT_SNAPSHOTS))
    args = parser.parse_args()

    dataset_path = Path(args.dataset).expanduser().resolve()
    latest_output = Path(args.latest_output).expanduser().resolve()
    snapshots_dir = Path(args.snapshots_dir).expanduser().resolve()
    as_of = parse_date(args.as_of_date)

    rows_by_symbol: dict[str, dict[str, str]] = {}
    with dataset_path.open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            report_date = parse_date(row['report_date'])
            if report_date > as_of:
                continue
            symbol = row['symbol']
            if symbol not in rows_by_symbol or parse_date(rows_by_symbol[symbol]['report_date']) < report_date:
                rows_by_symbol[symbol] = row

    candidates: list[CandidateRow] = []
    for symbol, row in sorted(rows_by_symbol.items()):
        revenue_yoy = float(row['revenue_yoy'])
        eps_yoy = float(row['eps_yoy'])
        revenue_accel = float(row['revenue_accel'])
        eps_accel = float(row['eps_accel'])

        passes_revenue_growth = revenue_yoy > 20
        passes_eps_growth = eps_yoy > 25
        passes_acceleration = revenue_accel > 0 or eps_accel > 0

        score = 0
        score += 1 if passes_revenue_growth else 0
        score += 1 if passes_eps_growth else 0
        score += 1 if passes_acceleration else 0
        score += 1 if revenue_yoy > 30 else 0
        score += 1 if eps_yoy > 40 else 0

        included = passes_revenue_growth and passes_eps_growth and passes_acceleration
        candidates.append(
            CandidateRow(
                as_of_date=args.as_of_date,
                symbol=symbol,
                passes_revenue_growth=passes_revenue_growth,
                passes_eps_growth=passes_eps_growth,
                passes_acceleration=passes_acceleration,
                candidate_score=score,
                included=included,
            )
        )

    latest_output.parent.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f'oneil_candidates_{args.as_of_date}.csv'

    for path in (latest_output, snapshot_path):
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in candidates:
                writer.writerow(asdict(row))

    included_count = sum(1 for row in candidates if row.included)
    print(f'wrote candidates total={len(candidates)} included={included_count} latest={latest_output} snapshot={snapshot_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
