from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.data.market_data import fetch_json  # noqa: E402
from reversal_lib.data.universe import fetch_sp500_symbols  # noqa: E402
from reversal_lib.models import Candle  # noqa: E402

DEFAULT_OUT_DIR = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/equity/usa/daily')
DEFAULT_PRELOAD_DAYS = 120
SCALE = 10000


def parse_utc_date(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)


def format_lean_row(ts: int, open_: float, high: float, low: float, close: float, volume: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return ','.join(
        [
            dt.strftime('%Y%m%d 00:00'),
            str(int(round(open_ * SCALE))),
            str(int(round(high * SCALE))),
            str(int(round(low * SCALE))),
            str(int(round(close * SCALE))),
            str(int(round(volume))),
        ]
    )


def parse_lean_row(row: str) -> tuple[int, str]:
    parts = row.strip().split(',')
    dt = datetime.strptime(parts[0], '%Y%m%d %H:%M').replace(tzinfo=timezone.utc)
    return int(dt.timestamp()), row.strip()


def read_existing_rows(zip_path: Path) -> dict[int, str]:
    if not zip_path.exists():
        return {}
    csv_name = f'{zip_path.stem}.csv'
    with zipfile.ZipFile(zip_path, 'r') as zf:
        try:
            payload = zf.read(csv_name).decode('utf-8')
        except KeyError:
            names = zf.namelist()
            payload = zf.read(names[0]).decode('utf-8')
    rows: dict[int, str] = {}
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        ts, raw = parse_lean_row(line)
        rows[ts] = raw
    return rows




def ensure_equity_auxiliary_files(symbol: str, out_dir: Path) -> None:
    equity_root = out_dir.parent
    map_dir = equity_root / 'map_files'
    factor_dir = equity_root / 'factor_files'
    map_dir.mkdir(parents=True, exist_ok=True)
    factor_dir.mkdir(parents=True, exist_ok=True)

    map_path = map_dir / f'{symbol.lower()}.csv'
    if not map_path.exists():
        map_path.write_text(f'19980101,{symbol.upper()}\n', encoding='utf-8')

    factor_path = factor_dir / f'{symbol.lower()}.csv'
    if not factor_path.exists():
        factor_path.write_text('19980101,1,1,1,1\n', encoding='utf-8')

def write_rows_to_zip(symbol: str, rows_by_ts: dict[int, str], out_dir: Path) -> int:
    if not rows_by_ts:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f'{symbol.lower()}.zip'
    csv_name = f'{symbol.lower()}.csv'
    payload = ('\n'.join(raw for _, raw in sorted(rows_by_ts.items())) + '\n').encode('utf-8')
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_name, payload)
    ensure_equity_auxiliary_files(symbol, out_dir)
    return len(rows_by_ts)


def merge_candles_into_existing(symbol: str, candles: list[Candle], out_dir: Path, min_ts: int, max_ts: int) -> tuple[int, int]:
    zip_path = out_dir / f'{symbol.lower()}.zip'
    rows_by_ts = read_existing_rows(zip_path)
    before_count = len(rows_by_ts)
    for candle in candles:
        if candle.ts < min_ts or candle.ts > max_ts:
            continue
        rows_by_ts[candle.ts] = format_lean_row(candle.ts, candle.open, candle.high, candle.low, candle.close, candle.volume)
    total_count = write_rows_to_zip(symbol, rows_by_ts, out_dir)
    return before_count, total_count


def fetch_true_sp500_symbols() -> list[str]:
    html = fetch_json('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    tables = pd.read_html(io.StringIO(html))
    for table in tables:
        cols = {str(col).strip(): col for col in table.columns}
        if 'Symbol' in cols:
            symbols = []
            for raw in table['Symbol'].astype(str).tolist():
                symbol = raw.strip().upper().replace('.', '-')
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
            if len(symbols) >= 500:
                return symbols
    raise RuntimeError('Failed to parse S&P 500 constituents from Wikipedia HTML')


def load_symbols(args_symbols: str | None, out_dir: Path | None = None) -> list[str]:
    if args_symbols:
        return [item.strip().upper() for item in args_symbols.split(',') if item.strip()]
    try:
        return fetch_true_sp500_symbols()
    except Exception as exc:
        print(f'[warn] wikipedia sp500 fetch failed: {exc}; trying local cache sources', file=sys.stderr)
        candidates: list[str] = []
        if out_dir is not None:
            metadata_path = out_dir.parent / 'yahoo_sp500_download_metadata.json'
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                    candidates.extend(metadata.get('symbols', {}).keys())
                except Exception:
                    pass
            if out_dir.exists():
                candidates.extend(path.stem.upper() for path in out_dir.glob('*.zip'))
        if candidates:
            deduped = []
            seen = set()
            for symbol in candidates:
                symbol = symbol.strip().upper().replace('.', '-')
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    deduped.append(symbol)
            return deduped
        print(f'[warn] local cache sources unavailable; falling back to existing remote local source', file=sys.stderr)
        symbols = fetch_sp500_symbols()
        return [item.strip().upper().replace('.', '-') for item in symbols if item.strip()]


def resolve_backtest_window(args: argparse.Namespace) -> tuple[datetime, datetime, str]:
    if args.lean_project:
        project_dir = Path(args.lean_project).expanduser().resolve()
        main_candidates = list(project_dir.glob('*.cs')) + list(project_dir.glob('*.py'))
        if not main_candidates:
            raise FileNotFoundError(f'No algorithm source found in project: {project_dir}')
        source = main_candidates[0].read_text(encoding='utf-8', errors='ignore')
        import re
        start_match = re.search(r'SetStartDate\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)', source)
        end_match = re.search(r'SetEndDate\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)', source)
        if not start_match or not end_match:
            raise RuntimeError(f'Could not parse SetStartDate/SetEndDate from {main_candidates[0]}')
        start_dt = datetime(int(start_match.group(1)), int(start_match.group(2)), int(start_match.group(3)), tzinfo=timezone.utc)
        end_dt = datetime(int(end_match.group(1)), int(end_match.group(2)), int(end_match.group(3)), tzinfo=timezone.utc)
        return start_dt, end_dt, f'lean-project:{project_dir.name}'

    if args.start_date and args.end_date:
        return parse_utc_date(args.start_date), parse_utc_date(args.end_date), 'explicit-dates'

    if args.start_date or args.end_date:
        raise ValueError('--start-date and --end-date must be provided together')

    end_dt = datetime.now(tz=timezone.utc)
    start_dt = end_dt - timedelta(days=int(round(args.years * 366)))
    return start_dt, end_dt, 'rolling-years'


def fetch_candles_for_window(symbol: str, start_dt: datetime, end_dt: datetime) -> list[Candle]:
    history = yf.Ticker(symbol).history(
        start=start_dt.strftime('%Y-%m-%d'),
        end=(end_dt + timedelta(days=1)).strftime('%Y-%m-%d'),
        interval='1d',
        auto_adjust=False,
    )
    candles: list[Candle] = []
    if history is None or history.empty:
        return candles
    for ts, row in history.iterrows():
        open_ = row.get('Open')
        high = row.get('High')
        low = row.get('Low')
        close = row.get('Close')
        volume = row.get('Volume')
        if None in (open_, high, low, close, volume):
            continue
        if any(value != value for value in (open_, high, low, close, volume)):
            continue
        candles.append(Candle(ts=int(ts.timestamp()), open=float(open_), high=float(high), low=float(low), close=float(close), volume=float(volume)))
    return candles


def load_metadata(path: Path) -> dict:
    if not path.exists():
        return {'symbols': {}}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {'symbols': {}}


def save_metadata(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Download Yahoo daily data and convert to LEAN daily zip format with reusable incremental cache.')
    parser.add_argument('--years', type=float, default=1.0, help='Fallback rolling window when explicit dates / LEAN project are not provided')
    parser.add_argument('--start-date', help='Backtest window start date, YYYY-MM-DD')
    parser.add_argument('--end-date', help='Backtest window end date, YYYY-MM-DD')
    parser.add_argument('--lean-project', help='LEAN project directory; auto-parses SetStartDate/SetEndDate from the algorithm source')
    parser.add_argument('--preload-days', type=int, default=DEFAULT_PRELOAD_DAYS, help='Extra calendar days to prepend before the backtest start for warmup indicators')
    parser.add_argument('--symbols', help='Comma separated symbols; default uses S&P 500 constituents')
    parser.add_argument('--limit', type=int, help='Limit number of symbols for testing')
    parser.add_argument('--out-dir', default=str(DEFAULT_OUT_DIR))
    parser.add_argument('--force-refresh', action='store_true', help='Ignore cache coverage and redownload requested symbols fully')
    args = parser.parse_args()

    backtest_start_dt, backtest_end_dt, window_source = resolve_backtest_window(args)
    download_start_dt = backtest_start_dt - timedelta(days=args.preload_days)
    download_end_dt = backtest_end_dt

    out_dir = Path(args.out_dir).expanduser().resolve()
    metadata_path = out_dir.parent / 'yahoo_sp500_download_metadata.json'
    report_path = out_dir.parent / 'yahoo_sp500_download_report.csv'
    metadata = load_metadata(metadata_path)
    metadata.setdefault('symbols', {})

    symbols = load_symbols(args.symbols, out_dir=out_dir)
    if args.limit:
        symbols = symbols[: args.limit]

    min_ts = int(download_start_dt.timestamp())
    max_ts = int((download_end_dt + timedelta(days=1) - timedelta(seconds=1)).timestamp())

    print(
        f'window_source={window_source} backtest_start={backtest_start_dt:%Y-%m-%d} '
        f'backtest_end={backtest_end_dt:%Y-%m-%d} download_start={download_start_dt:%Y-%m-%d} '
        f'download_end={download_end_dt:%Y-%m-%d} preload_days={args.preload_days} symbols={len(symbols)} force_refresh={args.force_refresh}',
        flush=True,
    )

    results: list[tuple[str, int, str]] = []
    for index, symbol in enumerate(symbols, start=1):
        symbol_meta = metadata['symbols'].get(symbol, {})
        existing_start = symbol_meta.get('download_start')
        existing_end = symbol_meta.get('download_end')
        covered = (
            not args.force_refresh
            and existing_start is not None
            and existing_end is not None
            and existing_start <= download_start_dt.strftime('%Y-%m-%d')
            and existing_end >= download_end_dt.strftime('%Y-%m-%d')
            and (out_dir / f'{symbol.lower()}.zip').exists()
        )
        if covered:
            rows_by_ts = read_existing_rows(out_dir / f'{symbol.lower()}.zip')
            count = sum(1 for ts in rows_by_ts if min_ts <= ts <= max_ts)
            print(f'[{index}/{len(symbols)}] {symbol}: cached ({count} rows)', flush=True)
            results.append((symbol, count, 'cached'))
            continue

        fetch_start_dt = download_start_dt
        fetch_end_dt = download_end_dt
        if not args.force_refresh and existing_start and existing_end:
            existing_start_dt = parse_utc_date(existing_start)
            existing_end_dt = parse_utc_date(existing_end)
            if existing_start_dt <= download_start_dt <= existing_end_dt and existing_end_dt < download_end_dt:
                fetch_start_dt = existing_end_dt + timedelta(days=1)
            elif download_start_dt < existing_start_dt <= download_end_dt and download_end_dt <= existing_end_dt:
                fetch_end_dt = existing_start_dt - timedelta(days=1)
            elif existing_start_dt <= download_start_dt and existing_end_dt >= download_end_dt:
                fetch_start_dt = download_end_dt
                fetch_end_dt = download_start_dt

        try:
            candles = []
            if fetch_start_dt <= fetch_end_dt:
                candles = fetch_candles_for_window(symbol, fetch_start_dt, fetch_end_dt)
            before_count, total_count = merge_candles_into_existing(symbol, candles, out_dir, min_ts, max_ts)
            status = 'ok' if total_count else 'empty'
            delta = total_count - before_count
            print(f'[{index}/{len(symbols)}] {symbol}: {status} (total={total_count}, added={delta})', flush=True)
            results.append((symbol, total_count, status))
            if total_count > 0:
                new_start = download_start_dt.strftime('%Y-%m-%d')
                new_end = download_end_dt.strftime('%Y-%m-%d')
                if existing_start and not args.force_refresh:
                    new_start = min(existing_start, new_start)
                if existing_end and not args.force_refresh:
                    new_end = max(existing_end, new_end)
                metadata['symbols'][symbol] = {
                    'download_start': new_start,
                    'download_end': new_end,
                    'rows': total_count,
                    'updated_at': datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                }
        except Exception as exc:
            print(f'[{index}/{len(symbols)}] {symbol}: error ({exc})', file=sys.stderr, flush=True)
            results.append((symbol, 0, f'error: {exc}'))

    metadata.update(
        {
            'window_source': window_source,
            'backtest_start': backtest_start_dt.strftime('%Y-%m-%d'),
            'backtest_end': backtest_end_dt.strftime('%Y-%m-%d'),
            'download_start': download_start_dt.strftime('%Y-%m-%d'),
            'download_end': download_end_dt.strftime('%Y-%m-%d'),
            'preload_days': args.preload_days,
            'symbol_count': len(symbols),
            'out_dir': str(out_dir),
            'updated_at': datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
    )
    save_metadata(metadata_path, metadata)

    with report_path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['symbol', 'rows', 'status'])
        writer.writerows(results)

    ok_count = sum(1 for _, rows, status in results if status in {'ok', 'cached'} and rows > 0)
    print(f'completed: {ok_count}/{len(results)} symbols ready; report={report_path} metadata={metadata_path}')
    return 0 if ok_count else 1


if __name__ == '__main__':
    raise SystemExit(main())
