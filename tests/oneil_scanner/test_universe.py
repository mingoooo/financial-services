from __future__ import annotations

from pathlib import Path

from scripts.oneil_scanner.runner import RunnerDependencies, run_scan
from scripts.oneil_scanner.universe import fetch_all_us_symbols, resolve_universe_symbols
from scripts.scan_oneil_setups import build_config, build_parser
from scripts.vcp_lib.data_sources import write_json_cache


NASDAQ_LISTED_SAMPLE = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust, Series 1|Q|N|N|100|Y|N
BRK.B|Berkshire Hathaway Inc. Class B|Q|N|N|100|N|N
TESTX|Some Test Security|Q|Y|N|100|N|N
NSHR|NextShares Example|Q|N|N|100|N|Y
WARR|Example Warrant Shares|Q|N|N|100|N|N
File Creation Time: 07272026
"""

OTHER_LISTED_SAMPLE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
MSFT|Microsoft Corporation Common Stock|N|MSFT|N|100|N|MSFT
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
RDS/A|Royal Dutch Shell plc ADR|N|RDS/A|N|100|N|RDS/A
ABC.WS|Abc Warrant Security|A|ABC.WS|N|100|N|ABC.WS
OTCM|Example OTC Security|U|OTCM|N|100|N|OTCM
File Creation Time: 07272026
"""


def _text_fetcher(url: str, *, timeout: int = 30) -> str:
    if 'nasdaqlisted' in url:
        return NASDAQ_LISTED_SAMPLE
    if 'otherlisted' in url:
        return OTHER_LISTED_SAMPLE
    raise AssertionError(f'unexpected url: {url} timeout={timeout}')


def test_fetch_all_us_symbols_filters_etfs_tests_and_non_common_stock_hints() -> None:
    symbols = fetch_all_us_symbols(text_fetcher=_text_fetcher)

    assert 'AAPL' in symbols
    assert 'BRK-B' in symbols
    assert 'MSFT' in symbols
    assert 'RDS-A' in symbols
    assert 'QQQ' not in symbols
    assert 'TESTX' not in symbols
    assert 'NSHR' not in symbols
    assert 'ABC-WS' not in symbols
    assert 'WARR' not in symbols
    assert 'OTCM' not in symbols


def test_fetch_all_us_symbols_uses_official_listed_sources_not_fixed_pool() -> None:
    symbols = fetch_all_us_symbols(text_fetcher=_text_fetcher)

    assert symbols == ['AAPL', 'BRK-B', 'MSFT', 'RDS-A']


def test_run_scan_uses_universe_resolver_when_symbols_are_not_provided(tmp_path: Path) -> None:
    config = build_config(
        build_parser().parse_args(
            [
                '--universe',
                'all-us',
                '--limit',
                '2',
                '--report-name',
                'all-us-smoke',
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
            universe_resolver=lambda _config: ['AAPL', 'MSFT', 'NVDA'],
            download_fn=lambda *_args, **_kwargs: None,
            history_loader=lambda *_args, **_kwargs: None,
        ),
    )

    assert summary.symbols == ['AAPL', 'MSFT']
    assert summary.candidates == []


def test_resolve_universe_symbols_uses_cache_after_first_fetch(tmp_path: Path) -> None:
    first = resolve_universe_symbols('all-us', cache_dir=tmp_path, text_fetcher=_text_fetcher)
    second = resolve_universe_symbols(
        'all-us',
        cache_dir=tmp_path,
        text_fetcher=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('cache miss')),
    )

    assert first == second
    assert (tmp_path / 'universe' / 'all-us.json').exists()


def test_resolve_universe_symbols_refreshes_stale_cache(tmp_path: Path) -> None:
    target = tmp_path / 'universe' / 'all-us.json'
    write_json_cache(
        target,
        {
            'universe': 'all-us',
            'symbol_count': 1,
            'symbols': ['STALE'],
            'fetched_at': '2026-07-01',
        },
    )

    refreshed = resolve_universe_symbols('all-us', cache_dir=tmp_path, text_fetcher=_text_fetcher)

    assert refreshed == ['AAPL', 'BRK-B', 'MSFT', 'RDS-A']
