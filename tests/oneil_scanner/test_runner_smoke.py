from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.oneil_scanner.data import _serialize_frame, build_scan_window_key, fetch_event_payload, load_daily_ohlcv
from scripts.oneil_scanner import runner as runner_module
from scripts.oneil_scanner.runner import RunnerDependencies, run_scan
from scripts.scan_oneil_setups import build_config, build_parser
from scripts.vcp_lib.data_sources import cache_path, write_json_cache
from tests.oneil_scanner.test_momentum_continuation_family import _high_tight_flag_frame
from tests.oneil_scanner.test_vcp_breakout_family import _platform_breakout_frame, _textbook_vcp_frame


FIELDS = ['Open', 'High', 'Low', 'Close', 'Volume']


def _single_symbol_frame(symbol: str) -> pd.DataFrame:
    index = pd.to_datetime(['2026-07-14', '2026-07-15'])
    return pd.DataFrame(
        {
            'Date': index,
            'Open': [100.0, 101.0],
            'High': [102.0, 103.0],
            'Low': [99.0, 100.0],
            'Close': [101.0, 102.0],
            'Volume': [1_000_000.0, 1_100_000.0],
        }
    )


def _batch_frame(symbols: list[str]) -> pd.DataFrame:
    frames = {symbol: _single_symbol_frame(symbol).set_index('Date')[FIELDS] for symbol in symbols}
    return pd.concat(frames, axis=1)


def _multi_symbol_download_factory(frames_by_symbol: dict[str, pd.DataFrame]):
    def fake_download(symbols: list[str], **_kwargs: object) -> pd.DataFrame:
        frames = {symbol: frames_by_symbol[symbol].set_index('Date')[FIELDS] for symbol in symbols}
        return pd.concat(frames, axis=1)

    return fake_download


def _long_event_overlap_frame() -> pd.DataFrame:
    closes = [60.0 + 0.22 * index for index in range(255)]
    frame = pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
            'Open': [price * 0.998 for price in closes],
            'High': [price * 1.012 for price in closes],
            'Low': [price * 0.99 for price in closes],
            'Close': closes,
            'Volume': [2_200_000.0] * len(closes),
        }
    )
    frame.loc[frame.index[-1], ['Open', 'High', 'Low', 'Close', 'Volume']] = [
        121.5,
        131.5,
        120.8,
        130.2,
        5_400_000.0,
    ]
    return frame


def _end_to_end_frames() -> dict[str, pd.DataFrame]:
    return {
        'SHOP': _long_event_overlap_frame(),
        'VCP': _platform_breakout_frame(),
        'IBD': _textbook_vcp_frame(breakout=False),
        'MOMO': _high_tight_flag_frame(),
    }


def test_scan_oneil_module_import_smoke() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.universe == 'all-us'
    assert args.report_name == 'oneil-setups'
    assert args.cache_dir == '.cache/oneil-scanner'


def test_scan_oneil_cli_smoke_uses_canonical_cache_backed_runner(tmp_path: Path) -> None:
    cache_dir = tmp_path / 'cache'
    out_dir = tmp_path / 'reports'
    frame = _long_event_overlap_frame()

    load_daily_ohlcv(
        ['SHOP'],
        cache_dir=cache_dir,
        as_of='2026-07-16',
        download_fn=_multi_symbol_download_factory({'SHOP': frame}),
    )
    fetch_event_payload(
        'news:SHOP',
        fetcher=lambda: {
            'items': [
                {
                    'date': frame.iloc[-1]['Date'].strftime('%Y-%m-%d'),
                    'headline': 'Company secures major platform distribution agreement',
                    'source': 'Reuters',
                }
            ]
        },
        cache_dir=cache_dir,
        window_key='2026-07-16_1y_1d',
    )

    result = subprocess.run(
        [
            sys.executable,
            'scripts/scan_oneil_setups.py',
            '--universe',
            'all-us',
            '--symbols',
            'SHOP',
            '--limit',
            '10',
            '--as-of',
            '2026-07-16',
            '--include-news',
            '--report-name',
            'smoke-run',
            '--out-dir',
            str(out_dir),
            '--cache-dir',
            str(cache_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout.strip())

    assert payload['universe'] == 'all-us'
    assert payload['symbols'] == ['SHOP']
    assert payload['candidate_count'] == 1
    assert payload['candidates'][0]['pattern_family'] == 'event_driven_family'
    assert (out_dir / 'smoke-run.json').exists()
    assert (out_dir / 'smoke-run.csv').exists()
    assert (out_dir / 'smoke-run.html').exists()


def test_run_scan_end_to_end_runs_all_families_dedups_and_writes_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frames = _end_to_end_frames()
    monkeypatch.setattr(
        runner_module,
        'evaluate_trend_filters',
        lambda *_args, **_kwargs: SimpleNamespace(passes=True, trend_template_pass=True),
    )
    config = build_config(
        build_parser().parse_args(
            [
                '--universe',
                'all-us',
                '--symbols',
                'SHOP,VCP,IBD,MOMO',
                '--limit',
                '10',
                '--as-of',
                '2026-07-16',
                '--include-news',
                '--report-name',
                'e2e-run',
                '--out-dir',
                str(tmp_path / 'reports'),
                '--cache-dir',
                str(tmp_path / 'cache'),
            ]
        )
    )
    summary = run_scan(
        config,
        dependencies=RunnerDependencies(
            download_fn=_multi_symbol_download_factory(frames),
            news_fetcher=lambda symbol: {
                'items': [
                    {
                        'date': frames[symbol].iloc[-1]['Date'].strftime('%Y-%m-%d'),
                        'headline': 'Company secures major platform distribution agreement',
                        'source': 'Reuters',
                    }
                ]
            }
            if symbol == 'SHOP'
            else {'items': []},
        ),
    )

    assert summary.symbols == ['SHOP', 'VCP', 'IBD', 'MOMO']
    assert len(summary.candidates) == 4
    assert {candidate.pattern_family for candidate in summary.candidates} == {
        'event_driven_family',
        'ibd_base_family',
        'vcp_breakout_family',
        'momentum_continuation_family',
    }

    shop_candidate = next(candidate for candidate in summary.candidates if candidate.symbol == 'SHOP')
    ibd_candidate = next(candidate for candidate in summary.candidates if candidate.symbol == 'IBD')
    assert shop_candidate.pattern_family == 'event_driven_family'
    assert 'vcp' in ibd_candidate.secondary_signals
    assert shop_candidate.symbol_context is not None
    assert shop_candidate.symbol_context.symbol == 'SHOP'

    grouped = {group.group_key: group for group in summary.grouped_candidate_summaries}
    assert grouped['top_setups'].candidate_count == 4
    assert grouped['event_driven_setups'].candidate_count == 1
    assert grouped['ibd_base_setups'].candidate_count == 1
    assert grouped['vcp_breakout_setups'].candidate_count == 1
    assert grouped['momentum_continuation_setups'].candidate_count == 1

    assert (tmp_path / 'reports' / 'e2e-run.json').exists()
    assert (tmp_path / 'reports' / 'e2e-run.csv').exists()
    assert (tmp_path / 'reports' / 'e2e-run.html').exists()


def test_daily_loader_batches_and_normalizes_frames(tmp_path: Path) -> None:
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


def test_daily_loader_incrementally_refreshes_stale_cached_history(tmp_path: Path) -> None:
    cache_file = cache_path(tmp_path, 'oneil_scanner/ohlcv/' + build_scan_window_key(as_of=None, period='1y', interval='1d'), 'AAPL')
    stale = _single_symbol_frame('AAPL')
    write_json_cache(
        cache_file,
        {
            **_serialize_frame(stale),
            'fetched_at': '2026-07-15',
            'last_date': '2026-07-15',
        },
    )

    batch_calls: list[dict[str, object]] = []

    def fake_download(symbols: list[str], **kwargs: object) -> pd.DataFrame:
        batch_calls.append({'symbols': symbols, **kwargs})
        assert symbols == ['AAPL']
        assert kwargs['start'] == '2026-07-10'
        assert kwargs.get('end') is None
        return pd.concat(
            {
                'AAPL': pd.DataFrame(
                    {
                        'Open': [101.0, 102.0],
                        'High': [103.0, 104.0],
                        'Low': [100.0, 101.0],
                        'Close': [102.0, 103.0],
                        'Volume': [1_100_000.0, 1_200_000.0],
                    },
                    index=pd.to_datetime(['2026-07-15', '2026-07-16']),
                )
            },
            axis=1,
        )

    result = load_daily_ohlcv(
        ['AAPL'],
        cache_dir=tmp_path,
        download_fn=fake_download,
    )

    assert len(batch_calls) == 1
    assert result.statuses['AAPL'].source == 'cache+live'
    assert list(result.frames['AAPL']['Date'].dt.strftime('%Y-%m-%d')) == ['2026-07-14', '2026-07-15', '2026-07-16']


def test_daily_loader_refresh_flag_bypasses_same_day_cache(tmp_path: Path) -> None:
    live_calls: list[list[str]] = []

    def fake_download(symbols: list[str], **_kwargs: object) -> pd.DataFrame:
        live_calls.append(symbols)
        return _batch_frame(symbols)

    load_daily_ohlcv(['AAPL'], cache_dir=tmp_path, download_fn=fake_download)
    refreshed = load_daily_ohlcv(['AAPL'], cache_dir=tmp_path, refresh=True, download_fn=fake_download)

    assert live_calls == [['AAPL'], ['AAPL']]
    assert refreshed.statuses['AAPL'].source == 'cache+live'


def test_daily_loader_handles_timeouts_without_aborting(tmp_path: Path) -> None:
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


def test_event_fetch_preserves_cached_warnings_on_cache_hit_and_fallback(tmp_path: Path) -> None:
    warnings: list[str] = []
    initial_payload, initial_meta = fetch_event_payload(
        'news:NVDA',
        fetcher=lambda: [],
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        warnings=warnings,
    )
    cached_payload, cached_meta = fetch_event_payload(
        'news:NVDA',
        fetcher=lambda: ['should not be used'],
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        warnings=warnings,
    )
    fallback_payload, fallback_meta = fetch_event_payload(
        'news:NVDA',
        fetcher=lambda: (_ for _ in ()).throw(RuntimeError('429 too many requests')),
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        retries=0,
        refresh=True,
        warnings=warnings,
    )

    assert initial_payload == []
    assert any('sparse event data' in warning.lower() for warning in initial_meta['run_metadata']['warnings'])
    assert cached_payload == []
    assert any('sparse event data' in warning.lower() for warning in cached_meta['run_metadata']['warnings'])
    assert fallback_payload == []
    assert any('sparse event data' in warning.lower() for warning in fallback_meta['run_metadata']['warnings'])
    assert any('rate-limit' in warning.lower() for warning in fallback_meta['run_metadata']['warnings'])
    assert any('sparse event data' in warning.lower() for warning in warnings)
    assert any('rate-limit' in warning.lower() for warning in warnings)


def test_event_fetch_rehydrates_cached_warnings_into_fresh_accumulator(tmp_path: Path) -> None:
    fetch_event_payload(
        'news:SHOP',
        fetcher=lambda: [],
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
    )

    fresh_warnings: list[str] = []
    cached_payload, cached_meta = fetch_event_payload(
        'news:SHOP',
        fetcher=lambda: ['unused'],
        cache_dir=tmp_path,
        window_key='2026-07-16_1y_1d',
        warnings=fresh_warnings,
    )

    assert cached_payload == []
    assert any('sparse event data' in warning.lower() for warning in cached_meta['run_metadata']['warnings'])
    assert any('sparse event data' in warning.lower() for warning in fresh_warnings)


def test_event_fetch_refreshes_stale_latest_cache(tmp_path: Path) -> None:
    cache_file = cache_path(tmp_path, 'oneil_scanner/events/latest_1y_1d', 'news_AAPL')
    write_json_cache(
        cache_file,
        {
            'fetched_at': '2026-07-01T08:00:00+00:00',
            'payload': {'items': [{'headline': 'stale'}]},
            'warnings': [],
        },
    )

    payload, meta = fetch_event_payload(
        'news:AAPL',
        fetcher=lambda: {'items': [{'headline': 'fresh'}]},
        cache_dir=tmp_path,
        window_key='latest_1y_1d',
    )

    assert payload == {'items': [{'headline': 'fresh'}]}
    assert meta['source'] == 'live'
