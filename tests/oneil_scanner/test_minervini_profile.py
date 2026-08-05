from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, ScannerConfig
from scripts.oneil_scanner.minervini import (
    DEFAULT_ALLOWED_FAMILIES,
    MINERVINI_RELAXED_PROFILE_SETTINGS,
    MINERVINI_STRICT_PROFILE_SETTINGS,
    allowed_detector_families,
    evaluate_minervini_trend_filters,
    is_minervini_profile,
)
from scripts.oneil_scanner.runner import RunnerDependencies, run_scan
from scripts.oneil_scanner.scoring import score_and_rank_candidates
from scripts.scan_oneil_setups import build_config, build_parser


def _daily_frame(length: int = 260, *, start: float = 100.0, step: float = 0.6) -> pd.DataFrame:
    dates = pd.date_range('2025-01-01', periods=length, freq='B')
    close = [start + (index * step) for index in range(length)]
    return pd.DataFrame(
        {
            'Date': dates,
            'Open': [value * 0.99 for value in close],
            'High': [value * 1.01 for value in close],
            'Low': [value * 0.98 for value in close],
            'Close': close,
            'Volume': [1_500_000] * length,
        }
    )


def _candidate(
    *,
    symbol: str = 'AAPL',
    pattern_family: str = 'vcp_breakout_family',
    pattern_type: str = 'vcp',
    trigger_date: str = '2026-07-16',
    rs_score: float = 95.0,
    distance_to_52w_high: float = 0.02,
    volume_confirmation: str = 'confirmed',
    quality_score: float = 88.0,
    setup_score: float = 86.0,
) -> PatternCandidate:
    return PatternCandidate(
        symbol=symbol,
        pattern_family=pattern_family,
        pattern_type=pattern_type,
        pattern_variant='test',
        trigger_date=trigger_date,
        breakout_level=100.0,
        entry_zone_low=100.0,
        entry_zone_high=105.0,
        stop_reference=95.0,
        trend_template_pass=True,
        rs_score=rs_score,
        distance_to_52w_high=distance_to_52w_high,
        volume_confirmation=volume_confirmation,
        catalyst_type='technical_breakout',
        catalyst_confidence=0.0,
        quality_score=quality_score,
        setup_score=setup_score,
        report_rank=None,
    )


def test_build_config_defaults_to_oneil_profile() -> None:
    config = build_config(build_parser().parse_args([]))

    assert config.strategy_profile == 'oneil'


def test_build_config_accepts_minervini_profile() -> None:
    config = build_config(build_parser().parse_args(['--strategy-profile', 'minervini_strict']))

    assert config.strategy_profile == 'minervini_strict'


def test_minervini_profile_helpers_expose_expected_defaults() -> None:
    assert is_minervini_profile('minervini_relaxed') is True
    assert is_minervini_profile('oneil') is False
    assert allowed_detector_families('minervini_relaxed') == DEFAULT_ALLOWED_FAMILIES
    assert MINERVINI_RELAXED_PROFILE_SETTINGS.rs_threshold < MINERVINI_STRICT_PROFILE_SETTINGS.rs_threshold


def test_evaluate_minervini_trend_filters_passes_strict_template() -> None:
    frame = _daily_frame()
    frame['SMA50'] = frame['Close'].rolling(50, min_periods=1).mean()
    frame['SMA150'] = frame['Close'].rolling(150, min_periods=1).mean()
    frame['SMA200'] = frame['Close'].rolling(200, min_periods=1).mean()
    frame['ClosePctFrom52WLow'] = 0.60
    frame['ClosePctFrom52WHigh'] = -0.05
    frame['RSProxy'] = 0.20

    result = evaluate_minervini_trend_filters(frame, strategy_profile='minervini_strict')

    assert result.passes is True
    assert result.trend_template_pass is True
    assert result.rs_pass is True
    assert result.check_status['close_above_sma50'] == 'pass'
    assert result.check_status['close_within_25pct_of_52w_high'] == 'pass'


def test_evaluate_minervini_trend_filters_fails_on_low_rs_proxy() -> None:
    frame = _daily_frame()
    frame['SMA50'] = frame['Close'].rolling(50, min_periods=1).mean()
    frame['SMA150'] = frame['Close'].rolling(150, min_periods=1).mean()
    frame['SMA200'] = frame['Close'].rolling(200, min_periods=1).mean()
    frame['ClosePctFrom52WLow'] = 0.60
    frame['ClosePctFrom52WHigh'] = -0.05
    frame['RSProxy'] = 0.01
    result = evaluate_minervini_trend_filters(frame, strategy_profile='minervini_strict')

    assert result.passes is False
    assert result.reasons == ['rs_proxy_below_threshold']
    assert result.check_status['rs_proxy'] == 'fail'


def test_run_scan_uses_minervini_profile_trend_path_and_allowed_families(monkeypatch, tmp_path) -> None:
    detector_calls: list[str] = []
    trend_calls: list[str] = []

    frame = _daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_preprocess(raw_frame, **_kwargs):
        enriched = raw_frame.copy()
        enriched['AvgDollarVolume20'] = 20_000_000.0
        enriched['RSProxy'] = 0.20
        enriched['ClosePctFrom52WHigh'] = -0.05
        enriched['SMA50'] = enriched['Close'] - 5
        enriched['SMA150'] = enriched['Close'] - 10
        enriched['SMA200'] = enriched['Close'] - 15
        enriched['ClosePctFrom52WLow'] = 0.60
        return enriched

    def make_detector(name: str):
        def _detector(_frame, **kwargs):
            detector_calls.append(name)
            trigger_date = {
                'vcp_breakout_family': '2026-07-16',
                'ibd_base_family': '2026-07-24',
            }[name]
            return [
                _candidate(
                    symbol=kwargs['symbol'],
                    pattern_family=name,
                    pattern_type='vcp' if name == 'vcp_breakout_family' else 'cup-with-handle',
                    trigger_date=trigger_date,
                )
            ]

        return _detector

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.add_shared_preprocessing', fake_preprocess)

    def fake_minervini_trend(frame, *, strategy_profile):
        trend_calls.append(strategy_profile)
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_minervini_trend_filters', fake_minervini_trend)
    monkeypatch.setattr(
        'scripts.oneil_scanner.runner.DETECTOR_REGISTRY',
        {
            'vcp_breakout_family': make_detector('vcp_breakout_family'),
            'ibd_base_family': make_detector('ibd_base_family'),
            'momentum_continuation_family': make_detector('momentum_continuation_family'),
            'event_driven_family': make_detector('event_driven_family'),
        },
    )

    summary = run_scan(
        ScannerConfig(
            universe='all-us',
            symbols=['AAPL'],
            cache_dir=str(tmp_path / 'cache'),
            out_dir=str(tmp_path / 'reports'),
            strategy_profile='minervini_strict',
        ),
        dependencies=RunnerDependencies(),
        write_reports=False,
    )

    assert trend_calls == ['minervini_strict']
    assert detector_calls == ['vcp_breakout_family', 'ibd_base_family']
    assert {candidate.pattern_family for candidate in summary.candidates} == DEFAULT_ALLOWED_FAMILIES
    assert summary.run_metadata.strategy_profile == 'minervini_strict'


def test_run_scan_keeps_oneil_family_set(monkeypatch, tmp_path) -> None:
    detector_calls: list[str] = []
    frame = _daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_preprocess(raw_frame, **_kwargs):
        enriched = raw_frame.copy()
        enriched['AvgDollarVolume20'] = 20_000_000.0
        return enriched

    def fake_trend_filters(_frame, *, min_rs_proxy=0.0):
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    def make_detector(name: str):
        def _detector(_frame, **kwargs):
            detector_calls.append(name)
            trigger_date = {
                'vcp_breakout_family': '2026-07-01',
                'ibd_base_family': '2026-07-09',
                'momentum_continuation_family': '2026-07-17',
                'event_driven_family': '2026-07-25',
            }[name]
            return [
                _candidate(
                    symbol=kwargs['symbol'],
                    pattern_family=name,
                    pattern_type='event-gap-breakout' if name == 'event_driven_family' else 'vcp',
                    trigger_date=trigger_date,
                )
            ]

        return _detector

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.add_shared_preprocessing', fake_preprocess)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_trend_filters', fake_trend_filters)
    monkeypatch.setattr(
        'scripts.oneil_scanner.runner.DETECTOR_REGISTRY',
        {
            'vcp_breakout_family': make_detector('vcp_breakout_family'),
            'ibd_base_family': make_detector('ibd_base_family'),
            'momentum_continuation_family': make_detector('momentum_continuation_family'),
            'event_driven_family': make_detector('event_driven_family'),
        },
    )

    summary = run_scan(
        ScannerConfig(
            universe='all-us',
            symbols=['AAPL'],
            cache_dir=str(tmp_path / 'cache'),
            out_dir=str(tmp_path / 'reports'),
        ),
        dependencies=RunnerDependencies(),
        write_reports=False,
    )

    assert detector_calls == [
        'vcp_breakout_family',
        'ibd_base_family',
        'momentum_continuation_family',
        'event_driven_family',
    ]
    assert len(summary.candidates) == 4
    assert summary.run_metadata.strategy_profile == 'oneil'


def test_minervini_ranking_prefers_tighter_high_rs_vcp_candidates() -> None:
    ranked = score_and_rank_candidates(
        [
            _candidate(symbol='AAPL', pattern_family='ibd_base_family', pattern_type='cup-with-handle', rs_score=92.0, distance_to_52w_high=0.05, volume_confirmation='watch', quality_score=90.0, setup_score=88.0),
            _candidate(symbol='NVDA', pattern_family='vcp_breakout_family', pattern_type='vcp', rs_score=98.0, distance_to_52w_high=0.01, volume_confirmation='confirmed', quality_score=89.0, setup_score=87.0),
        ],
        as_of='2026-07-16',
        strategy_profile='minervini_strict',
    )

    assert ranked[0].symbol == 'NVDA'
    assert ranked[0].report_rank == 1
