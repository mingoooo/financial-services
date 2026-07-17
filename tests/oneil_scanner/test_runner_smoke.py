from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.scan_oneil_setups import build_parser


def _batch_frame(symbols: list[str]) -> pd.DataFrame:
    index = pd.to_datetime(['2026-07-14', '2026-07-15'])
    columns = pd.MultiIndex.from_product(
        [symbols, ['Open', 'High', 'Low', 'Close', 'Volume']],
        names=['Ticker', 'Field'],
    )
    rows: list[list[float]] = []
    for offset in range(len(index)):
        row: list[float] = []
        for symbol_idx, _symbol in enumerate(symbols, start=1):
            base = 100.0 * symbol_idx + offset
            row.extend([base, base + 2.0, base - 1.0, base + 1.0, 1_000_000.0 + offset])
        rows.append(row)
    return pd.DataFrame(rows, index=index, columns=columns)


def _single_symbol_frame(symbol: str) -> pd.DataFrame:
    batch = _batch_frame([symbol])
    return pd.DataFrame({field: batch[(symbol, field)] for field in ['Open', 'High', 'Low', 'Close', 'Volume']}, index=batch.index)


def test_scan_oneil_module_import_smoke() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.universe == 'all-us'
    assert args.report_name == 'oneil-setups'


def test_scan_oneil_cli_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / 'reports'
    result = subprocess.run(
        [
            sys.executable,
            'scripts/scan_oneil_setups.py',
            '--universe',
            'all-us',
            '--symbols',
            'AAPL,MSFT',
            '--limit',
            '10',
            '--as-of',
            '2026-07-16',
            '--include-news',
            '--include-earnings',
            '--report-name',
            'smoke-run',
            '--out-dir',
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout.strip())

    assert payload['universe'] == 'all-us'
    assert payload['symbols'] == ['AAPL', 'MSFT']
    assert payload['candidate_count'] == 0
    assert payload['include_news'] is True
    assert payload['include_earnings'] is True
    assert (out_dir / 'smoke-run.json').exists()
    assert (out_dir / 'smoke-run.csv').exists()
    assert (out_dir / 'smoke-run.html').exists()


def test_daily_loader_batches_and_normalizes_frames(tmp_path: Path) -> None:
    from scripts.oneil_scanner.data import load_daily_ohlcv

    calls: list[list[str]] = []

    def fake_download(symbols: list[str], **_kwargs: object) -> pd.DataFrame:
        calls.append(symbols)
        return _batch_frame(symbols)

    result = load_daily_ohlcv(
        ['AAPL', 'MSFT', 'NVDA'],
        cache_dir=tmp_path,
        batch_size=2,
        download_fn=fake_download,
    )

    assert calls == [['AAPL', 'MSFT'], ['NVDA']]
    assert sorted(result.frames) == ['AAPL', 'MSFT', 'NVDA']
    assert list(result.frames['AAPL'].columns) == ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    assert result.statuses['AAPL'].status == 'ok'
    assert result.statuses['MSFT'].rows == 2
    assert result.warnings == []


def test_daily_loader_uses_cache_before_refetching(tmp_path: Path) -> None:
    from scripts.oneil_scanner.data import load_daily_ohlcv

    live_calls: list[list[str]] = []

    def fake_download(symbols: list[str], **_kwargs: object) -> pd.DataFrame:
        live_calls.append(symbols)
        return _batch_frame(symbols)

    first = load_daily_ohlcv(['AAPL'], cache_dir=tmp_path, download_fn=fake_download)
    second = load_daily_ohlcv(
        ['AAPL'],
        cache_dir=tmp_path,
        download_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('cache miss')),
    )

    assert live_calls == [['AAPL']]
    assert first.statuses['AAPL'].source == 'live'
    assert second.statuses['AAPL'].source == 'cache'
    assert second.frames['AAPL'].equals(first.frames['AAPL'])


def test_daily_loader_handles_timeouts_without_aborting(tmp_path: Path) -> None:
    from scripts.oneil_scanner.data import load_daily_ohlcv

    result = load_daily_ohlcv(
        ['AAPL'],
        cache_dir=tmp_path,
        retries=1,
        download_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError('request timed out')),
        history_loader=lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError('request timed out')),
    )

    assert result.frames == {}
    assert result.statuses['AAPL'].status == 'timeout'
    assert any('timeout' in warning.lower() for warning in result.warnings)


def test_daily_loader_keeps_partial_symbol_failures_local(tmp_path: Path) -> None:
    from scripts.oneil_scanner.data import load_daily_ohlcv

    def fake_download(symbols: list[str], **_kwargs: object) -> pd.DataFrame:
        assert symbols == ['AAPL', 'MSFT']
        return _batch_frame(['AAPL'])

    def fake_history(symbol: str, **_kwargs: object) -> pd.DataFrame:
        if symbol == 'MSFT':
            raise RuntimeError('No price data found')
        return _single_symbol_frame(symbol)

    result = load_daily_ohlcv(
        ['AAPL', 'MSFT'],
        cache_dir=tmp_path,
        retries=1,
        download_fn=fake_download,
        history_loader=fake_history,
    )

    assert 'AAPL' in result.frames
    assert 'MSFT' not in result.frames
    assert result.statuses['AAPL'].status == 'ok'
    assert result.statuses['MSFT'].status == 'error'
    assert any('partial' in warning.lower() for warning in result.warnings)


def test_event_fetch_warnings_propagate_to_run_metadata(tmp_path: Path) -> None:
    from scripts.oneil_scanner.data import fetch_event_payload

    sparse_payload, sparse_meta = fetch_event_payload(
        'news:AAPL',
        fetcher=lambda: [],
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
    )
    timeout_payload, timeout_meta = fetch_event_payload(
        'earnings:AAPL',
        fetcher=lambda: (_ for _ in ()).throw(TimeoutError('request timed out')),
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        retries=0,
    )
    rate_limit_payload, rate_limit_meta = fetch_event_payload(
        'news:MSFT',
        fetcher=lambda: (_ for _ in ()).throw(RuntimeError('429 too many requests')),
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        retries=0,
    )

    assert sparse_payload == []
    assert any('sparse event data' in warning.lower() for warning in sparse_meta['run_metadata']['warnings'])
    assert timeout_payload is None
    assert any('timeout' in warning.lower() for warning in timeout_meta['run_metadata']['warnings'])
    assert rate_limit_payload is None
    assert any('rate-limit' in warning.lower() for warning in rate_limit_meta['run_metadata']['warnings'])
