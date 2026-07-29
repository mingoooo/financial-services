from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

DEFAULT_SYMBOLS = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/sp500_symbols.txt')
DEFAULT_OUT = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_sec_growth_fundamentals_sp500.csv')
DEFAULT_LOG = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/sec_sp500_batch_log.csv')
IMPORTER = Path(__file__).with_name('import_sec_companyfacts_growth.py')
FIELDNAMES = ['symbol', 'report_date', 'fiscal_period', 'revenue', 'revenue_yoy', 'eps', 'eps_yoy']
LOG_FIELDS = ['batch_index', 'first_symbol', 'last_symbol', 'batch_size', 'status', 'rows_appended', 'detail']


def read_symbols(path: Path) -> list[str]:
    return [line.strip().upper() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def read_existing_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding='utf-8', newline='') as handle:
        return {row['symbol'] for row in csv.DictReader(handle)}


def read_logged_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            if row['status'] != 'success':
                continue
            first_symbol = row['first_symbol']
            last_symbol = row['last_symbol']
            detail = row['detail']
            if detail.startswith('symbols='):
                for symbol in detail.removeprefix('symbols=').split('|'):
                    if symbol:
                        done.add(symbol)
            else:
                done.add(first_symbol)
                done.add(last_symbol)
    return done


def append_rows(target: Path, source: Path) -> int:
    with source.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    exists = target.exists()
    with target.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def append_log(path: Path, row: dict[str, str | int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description='Batch SEC Company Facts import for SP500 universe with resume support.')
    parser.add_argument('--symbols-file', default=str(DEFAULT_SYMBOLS))
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    parser.add_argument('--log-file', default=str(DEFAULT_LOG))
    parser.add_argument('--batch-size', type=int, default=25)
    parser.add_argument('--sleep-seconds', type=float, default=0.03)
    parser.add_argument('--timeout-seconds', type=int, default=240)
    parser.add_argument('--user-agent', default='huangsm43 research local-test contact@example.com')
    parser.add_argument('--reset', action='store_true')
    args = parser.parse_args()

    symbols_path = Path(args.symbols_file).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    log_path = Path(args.log_file).expanduser().resolve()
    if args.reset:
        if output_path.exists():
            output_path.unlink()
        if log_path.exists():
            log_path.unlink()

    symbols = read_symbols(symbols_path)
    done = read_existing_symbols(output_path) | read_logged_symbols(log_path)
    remaining = [symbol for symbol in symbols if symbol not in done]
    print(f'total={len(symbols)} done={len(done)} remaining={len(remaining)} output={output_path}')

    temp = output_path.with_name(output_path.stem + '.batch.csv')
    imported_symbols = 0
    imported_rows = 0
    failed_batches = 0

    for idx, batch in enumerate(chunked(remaining, args.batch_size), start=1):
        if temp.exists():
            temp.unlink()
        detail_symbols = '|'.join(batch)
        cmd = [
            sys.executable,
            str(IMPORTER),
            '--symbols',
            ','.join(batch),
            '--output',
            str(temp),
            '--sleep-seconds',
            str(args.sleep_seconds),
            '--user-agent',
            args.user_agent,
        ]
        print(f'[batch {idx}] symbols={len(batch)} first={batch[0]} last={batch[-1]}')
        status = 'success'
        rows = 0
        detail = f'symbols={detail_symbols}'
        try:
            subprocess.run(cmd, check=True, timeout=args.timeout_seconds)
            rows = append_rows(output_path, temp)
            imported_symbols += len(batch)
            imported_rows += rows
            print(f'[batch {idx}] appended_rows={rows} total_imported_symbols={imported_symbols}')
        except subprocess.TimeoutExpired:
            status = 'timeout'
            failed_batches += 1
            detail = f'timeout symbols={detail_symbols}'
            print(f'[batch {idx}] timeout after {args.timeout_seconds}s', file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            status = 'error'
            failed_batches += 1
            detail = f'exit={exc.returncode} symbols={detail_symbols}'
            print(f'[batch {idx}] failed exit={exc.returncode}', file=sys.stderr)
        finally:
            append_log(
                log_path,
                {
                    'batch_index': idx,
                    'first_symbol': batch[0],
                    'last_symbol': batch[-1],
                    'batch_size': len(batch),
                    'status': status,
                    'rows_appended': rows,
                    'detail': detail,
                },
            )
            if temp.exists():
                temp.unlink()

    print(f'finished imported_symbols={imported_symbols} imported_rows={imported_rows} failed_batches={failed_batches} output={output_path} log={log_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
