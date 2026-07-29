from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

DEFAULT_SYMBOLS = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/sp500_symbols.txt')
DEFAULT_OUT = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_sec_growth_fundamentals_sp500.csv')
DEFAULT_LOG = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/sec_sp500_singlepass_log.csv')
IMPORTER = Path(__file__).with_name('import_sec_companyfacts_growth.py')
FIELDNAMES = ['symbol', 'report_date', 'fiscal_period', 'revenue', 'revenue_yoy', 'eps', 'eps_yoy']
LOG_FIELDS = ['symbol', 'status', 'rows_appended', 'detail']


def read_symbols(path: Path) -> list[str]:
    return [line.strip().upper() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def read_logged(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding='utf-8', newline='') as handle:
        for row in csv.DictReader(handle):
            out[row['symbol']] = row['status']
    return out


def append_rows(target: Path, source: Path) -> int:
    with source.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return 0
    exists = target.exists()
    with target.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def append_log(path: Path, symbol: str, status: str, rows_appended: int, detail: str) -> None:
    exists = path.exists()
    with path.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({'symbol': symbol, 'status': status, 'rows_appended': rows_appended, 'detail': detail})


def main() -> int:
    parser = argparse.ArgumentParser(description='Single-symbol SEC SP500 importer with resume support.')
    parser.add_argument('--symbols-file', default=str(DEFAULT_SYMBOLS))
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    parser.add_argument('--log-file', default=str(DEFAULT_LOG))
    parser.add_argument('--sleep-seconds', type=float, default=0.01)
    parser.add_argument('--timeout-seconds', type=int, default=90)
    parser.add_argument('--user-agent', default='huangsm43 research local-test contact@example.com')
    args = parser.parse_args()

    symbols = read_symbols(Path(args.symbols_file).expanduser().resolve())
    output = Path(args.output).expanduser().resolve()
    log_file = Path(args.log_file).expanduser().resolve()
    logged = read_logged(log_file)
    remaining = [symbol for symbol in symbols if symbol not in logged]
    print(f'total={len(symbols)} done={len(logged)} remaining={len(remaining)}')

    temp = output.with_name(output.stem + '.single.csv')
    for idx, symbol in enumerate(remaining, start=1):
        if temp.exists():
            temp.unlink()
        cmd = [
            sys.executable,
            str(IMPORTER),
            '--symbols', symbol,
            '--output', str(temp),
            '--sleep-seconds', str(args.sleep_seconds),
            '--user-agent', args.user_agent,
        ]
        status = 'success'
        rows = 0
        detail = ''
        print(f'[{idx}/{len(remaining)}] {symbol}')
        try:
            subprocess.run(cmd, check=True, timeout=args.timeout_seconds)
            rows = append_rows(output, temp) if temp.exists() else 0
            if rows == 0:
                status = 'empty'
                detail = 'no rows'
        except subprocess.TimeoutExpired:
            status = 'timeout'
            detail = 'timeout'
        except subprocess.CalledProcessError as exc:
            status = 'error'
            detail = f'exit={exc.returncode}'
        append_log(log_file, symbol, status, rows, detail)
        if temp.exists():
            temp.unlink()
    print(f'finished output={output} log={log_file}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
