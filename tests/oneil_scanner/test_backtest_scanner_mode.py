from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import scripts.backtest_oneil_unified as bt
from scripts.oneil_scanner.backtest_adapter import DaySignalCache, ScannerBacktestSignal


def _make_bars(symbol: str, periods: int = 220) -> list[dict]:
    dates = list(__import__('pandas').date_range('2025-01-01', periods=periods, freq='B'))
    bars: list[dict] = []
    for index, ts in enumerate(dates):
        base = 100.0 + index * 0.5
        bars.append(
            {
                'date': ts.to_pydatetime(),
                'open': base,
                'high': base + 1.2,
                'low': base - 1.5,
                'close': base + 0.6,
                'volume': 2_000_000.0 + index * 1000,
            }
        )
    return bars


@pytest.fixture
def scanner_fixture() -> dict[str, object]:
    aapl = _make_bars('AAPL')
    spy = _make_bars('SPY')
    start = aapl[-2]['date']
    end = aapl[-1]['date']
    return {
        'bars_by_symbol': {'AAPL': aapl, 'SPY': spy},
        'trigger_day': aapl[-2]['date'].strftime('%Y-%m-%d'),
        'entry_day': aapl[-1]['date'].strftime('%Y-%m-%d'),
        'start': start,
        'end': end,
    }


def test_main_accepts_scanner_cli_flags(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    captured: dict[str, object] = {}

    def fake_run_backtest(*args: object, **kwargs: object) -> dict:
        captured.update(kwargs)
        return {
            'signal_source': kwargs['signal_source'],
            'universe_mode': kwargs['universe_mode'],
            'start': '2026-01-01',
            'end': '2026-01-02',
            'candidate_count': 0,
            'signal_trade_count': 0,
            'executed_trade_count': 0,
            'win_rate_pct': 0.0,
            'average_trade_return_pct': 0.0,
            'initial_capital': 100000.0,
            'final_equity': 100000.0,
            'total_return_pct': 0.0,
            'annualized_return_pct': 0.0,
            'max_drawdown_pct': 0.0,
            'profit_factor': 0.0,
            'monthly_pnl': {},
            'equity_curve': [],
            'warnings': [],
            'trades': [],
        }

    monkeypatch.setattr(bt, 'run_backtest', fake_run_backtest)

    exit_code = bt.main(
        [
            '--signal-source',
            'scanner',
            '--scanner-cache-dir',
            '/tmp/scanner-cache',
            '--refresh-scanner-cache',
            '--pattern-families',
            'vcp_breakout_family,ibd_base_family',
            '--pattern-types',
            'vcp,cup-with-handle',
            '--min-dollar-volume',
            '1234567',
        ]
    )

    assert exit_code == 0
    assert captured['signal_source'] == 'scanner'
    assert captured['scanner_cache_dir'] == Path('/tmp/scanner-cache')
    assert captured['refresh_scanner_cache'] is True
    assert captured['pattern_families'] == ['vcp_breakout_family', 'ibd_base_family']
    assert captured['pattern_types'] == ['vcp', 'cup-with-handle']
    assert captured['min_dollar_volume'] == pytest.approx(1234567.0)
    assert 'scanner' in capsys.readouterr().out


def test_run_backtest_legacy_preserves_candidate_loader_path(monkeypatch: pytest.MonkeyPatch, scanner_fixture: dict[str, object]) -> None:
    load_calls: list[str] = []

    def fake_load_daily_candidates(*args: object, **kwargs: object) -> dict[str, dict[str, float]]:
        load_calls.append('called')
        return {scanner_fixture['trigger_day']: {'AAPL': 1.0}, scanner_fixture['entry_day']: {}}

    monkeypatch.setattr(bt, 'load_daily_candidates', fake_load_daily_candidates)
    monkeypatch.setattr(bt, 'build_bars_by_symbol', lambda *args, **kwargs: scanner_fixture['bars_by_symbol'])
    monkeypatch.setattr(bt, 'build_spy_entry_filter', lambda *args, **kwargs: {scanner_fixture['trigger_day']: True, scanner_fixture['entry_day']: True})

    result = bt.run_backtest(
        start=scanner_fixture['start'],
        end=scanner_fixture['end'],
        universe_mode='static',
        static_candidate_file=Path('unused.csv'),
        fundamentals_dataset=Path('unused.csv'),
        signal_source='legacy',
    )

    assert load_calls == ['called']
    assert result['signal_source'] == 'legacy'


def test_run_backtest_scanner_uses_adapter_signals_and_skips_candidate_loader(
    monkeypatch: pytest.MonkeyPatch,
    scanner_fixture: dict[str, object],
) -> None:
    bars_by_symbol = scanner_fixture['bars_by_symbol']
    trigger_day = scanner_fixture['trigger_day']
    entry_day = scanner_fixture['entry_day']

    monkeypatch.setattr(bt, 'discover_scanner_symbols', lambda *args, **kwargs: ['AAPL'])
    monkeypatch.setattr(bt, 'build_bars_by_symbol', lambda *args, **kwargs: bars_by_symbol)
    monkeypatch.setattr(bt, 'build_spy_entry_filter', lambda *args, **kwargs: {trigger_day: True, entry_day: True})
    monkeypatch.setattr(bt, 'load_daily_candidates', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('legacy path should not run')))

    signal = ScannerBacktestSignal(
        symbol='AAPL',
        trigger_date=trigger_day,
        entry_date=entry_day,
        entry_price_ref=150.0,
        breakout_level=150.0,
        stop_reference=145.0,
        primary_pattern_family='ibd_base_family',
        primary_pattern_type='cup-with-handle',
        primary_pattern_variant='standard',
        secondary_patterns=('vcp_breakout_family:vcp:textbook',),
        ranking_score=97.0,
        quality_score=92.0,
        setup_score=95.0,
        rs_score=98.0,
        normalized_rs_score=98.0,
    )
    monkeypatch.setattr(
        bt,
        'load_or_build_day_signals',
        lambda **kwargs: DaySignalCache(date=trigger_day, signals=(signal,), warnings=('scanner family warning',)),
    )

    result = bt.run_backtest(
        start=scanner_fixture['start'],
        end=scanner_fixture['end'],
        universe_mode='static',
        static_candidate_file=Path('unused.csv'),
        fundamentals_dataset=Path('unused.csv'),
        signal_source='scanner',
        scanner_cache_dir=Path('/tmp/scanner-cache'),
    )

    assert result['signal_source'] == 'scanner'
    assert result['executed_trade_count'] == 1
    assert result['warnings'] == ['scanner family warning']
    trade = result['trades'][0]
    assert trade['trigger_date'] == trigger_day
    assert trade['entry_date'] == entry_day
    assert trade['primary_pattern_family'] == 'ibd_base_family'
    assert trade['primary_pattern_type'] == 'cup-with-handle'
    assert trade['secondary_patterns'] == ['vcp_breakout_family:vcp:textbook']


def test_scanner_entry_uses_next_day_open_and_fallback_stop(
    monkeypatch: pytest.MonkeyPatch,
    scanner_fixture: dict[str, object],
) -> None:
    bars_by_symbol = scanner_fixture['bars_by_symbol']
    trigger_day = scanner_fixture['trigger_day']
    entry_day = scanner_fixture['entry_day']
    expected_entry_open = bars_by_symbol['AAPL'][-1]['open']

    monkeypatch.setattr(bt, 'discover_scanner_symbols', lambda *args, **kwargs: ['AAPL'])
    monkeypatch.setattr(bt, 'build_bars_by_symbol', lambda *args, **kwargs: bars_by_symbol)
    monkeypatch.setattr(bt, 'build_spy_entry_filter', lambda *args, **kwargs: {trigger_day: True, entry_day: True})
    monkeypatch.setattr(
        bt,
        'load_or_build_day_signals',
        lambda **kwargs: DaySignalCache(
            date=trigger_day,
            signals=(
                ScannerBacktestSignal(
                    symbol='AAPL',
                    trigger_date=trigger_day,
                    entry_date=entry_day,
                    entry_price_ref=150.0,
                    breakout_level=150.0,
                    stop_reference=None,
                    primary_pattern_family='vcp_breakout_family',
                    primary_pattern_type='vcp',
                    primary_pattern_variant='textbook',
                    secondary_patterns=(),
                    ranking_score=90.0,
                    quality_score=90.0,
                    setup_score=91.0,
                    rs_score=88.0,
                    normalized_rs_score=88.0,
                ),
            ),
            warnings=('symbol detector warning',),
        ),
    )

    result = bt.run_backtest(
        start=scanner_fixture['start'],
        end=scanner_fixture['end'],
        universe_mode='static',
        static_candidate_file=Path('unused.csv'),
        fundamentals_dataset=Path('unused.csv'),
        signal_source='scanner',
    )

    trade = result['trades'][0]
    assert trade['entry_price'] == pytest.approx(bt.apply_slippage(expected_entry_open, 'buy'))
    assert trade['stop_price'] > 0
    assert 'symbol detector warning' in result['warnings']


def test_scanner_skips_signal_when_next_day_bar_missing(monkeypatch: pytest.MonkeyPatch, scanner_fixture: dict[str, object]) -> None:
    aapl = scanner_fixture['bars_by_symbol']['AAPL'][:-1]
    msft = _make_bars('MSFT')
    spy = scanner_fixture['bars_by_symbol']['SPY']
    trigger_day = scanner_fixture['trigger_day']
    entry_day = scanner_fixture['entry_day']

    monkeypatch.setattr(bt, 'discover_scanner_symbols', lambda *args, **kwargs: ['AAPL', 'MSFT'])
    monkeypatch.setattr(bt, 'build_bars_by_symbol', lambda *args, **kwargs: {'AAPL': aapl, 'MSFT': msft, 'SPY': spy})
    monkeypatch.setattr(bt, 'build_spy_entry_filter', lambda *args, **kwargs: {trigger_day: True, entry_day: True})
    monkeypatch.setattr(
        bt,
        'load_or_build_day_signals',
        lambda **kwargs: DaySignalCache(
            date=trigger_day,
            signals=(
                ScannerBacktestSignal(
                    symbol='AAPL',
                    trigger_date=trigger_day,
                    entry_date=entry_day,
                    entry_price_ref=150.0,
                    breakout_level=150.0,
                    stop_reference=145.0,
                    primary_pattern_family='ibd_base_family',
                    primary_pattern_type='flat-base',
                    primary_pattern_variant='tight',
                    secondary_patterns=(),
                    ranking_score=80.0,
                    quality_score=80.0,
                    setup_score=81.0,
                    rs_score=82.0,
                    normalized_rs_score=82.0,
                ),
            ),
            warnings=(),
        ),
    )

    result = bt.run_backtest(
        start=scanner_fixture['start'],
        end=scanner_fixture['end'],
        universe_mode='static',
        static_candidate_file=Path('unused.csv'),
        fundamentals_dataset=Path('unused.csv'),
        signal_source='scanner',
    )

    assert result['executed_trade_count'] == 0
    assert any('Missing next-day entry bar' in warning for warning in result['warnings'])
