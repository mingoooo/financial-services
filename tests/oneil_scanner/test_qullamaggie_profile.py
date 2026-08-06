from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.oneil_scanner.models import PatternCandidate, ScannerConfig
from scripts.oneil_scanner.qullamaggie import (
    DEFAULT_ALLOWED_FAMILIES,
    allowed_detector_families_for_qullamaggie,
    evaluate_qullamaggie_leader_prefilter,
    is_qullamaggie_profile,
    resolve_qullamaggie_entry_trigger,
)
from scripts.oneil_scanner.runner import RunnerDependencies, run_scan
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


def _compounding_daily_frame(length: int = 260, *, start: float = 100.0, daily_return: float = 0.012) -> pd.DataFrame:
    close = [start * ((1.0 + daily_return) ** index) for index in range(length)]
    return pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=length, freq='B'),
            'Open': [value * 0.99 for value in close],
            'High': [value * 1.01 for value in close],
            'Low': [value * 0.98 for value in close],
            'Close': close,
            'Volume': [1_500_000] * length,
        }
    )


def _candidate(*, breakout_level: float | None = 104.5) -> PatternCandidate:
    return PatternCandidate(
        symbol='AAPL',
        pattern_family='momentum_continuation_family',
        pattern_type='inside-day',
        pattern_variant='test',
        trigger_date='2026-07-16',
        breakout_level=breakout_level,
        entry_zone_low=103.0,
        entry_zone_high=106.0,
        stop_reference=99.0,
        trend_template_pass=True,
        rs_score=95.0,
        distance_to_52w_high=0.01,
        volume_confirmation='confirmed',
        catalyst_type='technical_breakout',
        catalyst_confidence=0.0,
        quality_score=88.0,
        setup_score=86.0,
        report_rank=None,
    )


def test_qullamaggie_config_default_profile_remains_oneil() -> None:
    config = build_config(build_parser().parse_args([]))

    assert config.strategy_profile == 'oneil'



def test_qullamaggie_config_parser_accepts_profile_option() -> None:
    args = build_parser().parse_args(['--strategy-profile', 'qullamaggie'])

    assert args.strategy_profile == 'qullamaggie'



def test_qullamaggie_config_build_sets_scanner_profile() -> None:
    config = build_config(build_parser().parse_args(['--strategy-profile', 'qullamaggie']))

    assert isinstance(config, ScannerConfig)
    assert config.strategy_profile == 'qullamaggie'



def test_qullamaggie_helper_identifies_profile_name() -> None:
    assert is_qullamaggie_profile('qullamaggie') is True
    assert is_qullamaggie_profile('oneil') is False



def test_qullamaggie_helper_leader_prefilter_passes_for_strong_multi_horizon_momentum() -> None:
    result = evaluate_qullamaggie_leader_prefilter(
        strength_1m=0.35,
        strength_3m=0.60,
        strength_6m=0.90,
    )

    assert result.passes is True
    assert result.reasons == []
    assert result.metrics == {
        'strength_1m': 0.35,
        'strength_3m': 0.60,
        'strength_6m': 0.90,
    }



def test_qullamaggie_helper_leader_prefilter_fails_when_short_term_strength_breaks() -> None:
    result = evaluate_qullamaggie_leader_prefilter(
        strength_1m=0.10,
        strength_3m=0.60,
        strength_6m=0.90,
    )

    assert result.passes is False
    assert result.reasons == ['strength_1m_below_threshold']


def test_run_scan_oneil_leader_prefilter_does_not_invoke_qullamaggie_prefilter(monkeypatch, tmp_path) -> None:
    prefilter_calls: list[tuple[float | None, float | None, float | None]] = []
    detector_calls: list[str] = []
    frame = _daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_preprocess(raw_frame, **_kwargs):
        enriched = raw_frame.copy()
        enriched['AvgDollarVolume20'] = 20_000_000.0
        enriched['strength_1m'] = 0.35
        enriched['strength_3m'] = 0.60
        enriched['strength_6m'] = 0.90
        return enriched

    def fake_trend_filters(_frame, *, min_rs_proxy=0.0):
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    def fake_eligibility(_frame, **_kwargs):
        return SimpleNamespace(passes=True)

    def fake_leader_prefilter(*, strength_1m, strength_3m, strength_6m, strategy_profile='qullamaggie'):
        prefilter_calls.append((strength_1m, strength_3m, strength_6m))
        return SimpleNamespace(passes=True, reasons=[], metrics={})

    def fake_detector(_frame, **kwargs):
        detector_calls.append(kwargs['symbol'])
        return [_candidate()]

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.add_shared_preprocessing', fake_preprocess)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_trend_filters', fake_trend_filters)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_eligibility', fake_eligibility)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_qullamaggie_leader_prefilter', fake_leader_prefilter)
    monkeypatch.setattr('scripts.oneil_scanner.runner.DETECTOR_REGISTRY', {'momentum_continuation_family': fake_detector})

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

    assert prefilter_calls == []
    assert detector_calls == ['AAPL']
    assert len(summary.candidates) == 1


def test_run_scan_qullamaggie_leader_prefilter_runs_before_detectors(monkeypatch, tmp_path) -> None:
    call_order: list[tuple[str, float | None, float | None, float | None] | str] = []
    frame = _daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_preprocess(raw_frame, **_kwargs):
        enriched = raw_frame.copy()
        enriched['AvgDollarVolume20'] = 20_000_000.0
        enriched['strength_1m'] = 0.35
        enriched['strength_3m'] = 0.60
        enriched['strength_6m'] = 0.90
        return enriched

    def fake_trend_filters(_frame, *, min_rs_proxy=0.0):
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    def fake_eligibility(_frame, **_kwargs):
        return SimpleNamespace(passes=True)

    def fake_leader_prefilter(*, strength_1m, strength_3m, strength_6m, strategy_profile='qullamaggie'):
        call_order.append(('leader_prefilter', strength_1m, strength_3m, strength_6m))
        return SimpleNamespace(passes=True, reasons=[], metrics={})

    def fake_detector(_frame, **_kwargs):
        call_order.append('detector')
        return [_candidate()]

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.add_shared_preprocessing', fake_preprocess)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_trend_filters', fake_trend_filters)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_eligibility', fake_eligibility)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_qullamaggie_leader_prefilter', fake_leader_prefilter)
    monkeypatch.setattr('scripts.oneil_scanner.runner.DETECTOR_REGISTRY', {'momentum_continuation_family': fake_detector})

    run_scan(
        ScannerConfig(
            universe='all-us',
            symbols=['AAPL'],
            cache_dir=str(tmp_path / 'cache'),
            out_dir=str(tmp_path / 'reports'),
            strategy_profile='qullamaggie',
        ),
        dependencies=RunnerDependencies(),
        write_reports=False,
    )

    assert call_order == [('leader_prefilter', 0.35, 0.60, 0.90), 'detector']


def test_run_scan_qullamaggie_leader_prefilter_blocks_detector_calls_when_symbol_fails(monkeypatch, tmp_path) -> None:
    prefilter_calls: list[tuple[float | None, float | None, float | None]] = []
    detector_calls: list[str] = []
    frame = _daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_preprocess(raw_frame, **_kwargs):
        enriched = raw_frame.copy()
        enriched['AvgDollarVolume20'] = 20_000_000.0
        enriched['strength_1m'] = 0.10
        enriched['strength_3m'] = 0.60
        enriched['strength_6m'] = 0.90
        return enriched

    def fake_trend_filters(_frame, *, min_rs_proxy=0.0):
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    def fake_eligibility(_frame, **_kwargs):
        return SimpleNamespace(passes=True)

    def fake_leader_prefilter(*, strength_1m, strength_3m, strength_6m, strategy_profile='qullamaggie'):
        prefilter_calls.append((strength_1m, strength_3m, strength_6m))
        return SimpleNamespace(passes=False, reasons=['strength_1m_below_threshold'], metrics={})

    def fake_detector(_frame, **kwargs):
        detector_calls.append(kwargs['symbol'])
        return [_candidate()]

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.add_shared_preprocessing', fake_preprocess)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_trend_filters', fake_trend_filters)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_eligibility', fake_eligibility)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_qullamaggie_leader_prefilter', fake_leader_prefilter)
    monkeypatch.setattr('scripts.oneil_scanner.runner.DETECTOR_REGISTRY', {'momentum_continuation_family': fake_detector})

    summary = run_scan(
        ScannerConfig(
            universe='all-us',
            symbols=['AAPL'],
            cache_dir=str(tmp_path / 'cache'),
            out_dir=str(tmp_path / 'reports'),
            strategy_profile='qullamaggie',
        ),
        dependencies=RunnerDependencies(),
        write_reports=False,
    )

    assert prefilter_calls == [(0.10, 0.60, 0.90)]
    assert detector_calls == []
    assert summary.candidates == []


def test_run_scan_qullamaggie_leader_prefilter_uses_real_preprocessing_strength_metrics(monkeypatch, tmp_path) -> None:
    prefilter_calls: list[tuple[float | None, float | None, float | None]] = []
    detector_calls: list[str] = []
    frame = _compounding_daily_frame()

    def fake_load_daily_ohlcv(symbols, **_kwargs):
        return SimpleNamespace(frames={symbol: frame for symbol in symbols}, warnings=[], metadata={'run_metadata': {'window_key': 'latest_1y_1d'}})

    def fake_trend_filters(_frame, *, min_rs_proxy=0.0):
        return SimpleNamespace(passes=True, trend_template_pass=True, rs_pass=True)

    def fake_eligibility(_frame, **_kwargs):
        return SimpleNamespace(passes=True)

    def fake_leader_prefilter(*, strength_1m, strength_3m, strength_6m, strategy_profile='qullamaggie'):
        prefilter_calls.append((strength_1m, strength_3m, strength_6m))
        return SimpleNamespace(passes=True, reasons=[], metrics={})

    def fake_detector(_frame, **kwargs):
        detector_calls.append(kwargs['symbol'])
        return [_candidate()]

    monkeypatch.setattr('scripts.oneil_scanner.runner.load_daily_ohlcv', fake_load_daily_ohlcv)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_trend_filters', fake_trend_filters)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_eligibility', fake_eligibility)
    monkeypatch.setattr('scripts.oneil_scanner.runner.evaluate_qullamaggie_leader_prefilter', fake_leader_prefilter)
    monkeypatch.setattr('scripts.oneil_scanner.runner.DETECTOR_REGISTRY', {'momentum_continuation_family': fake_detector})

    summary = run_scan(
        ScannerConfig(
            universe='all-us',
            symbols=['AAPL'],
            cache_dir=str(tmp_path / 'cache'),
            out_dir=str(tmp_path / 'reports'),
            strategy_profile='qullamaggie',
        ),
        dependencies=RunnerDependencies(),
        write_reports=False,
    )

    assert len(prefilter_calls) == 1
    strength_1m, strength_3m, strength_6m = prefilter_calls[0]
    assert strength_1m == pytest.approx(frame['Close'].iloc[-1] / frame['Close'].iloc[-22] - 1.0)
    assert strength_3m == pytest.approx(frame['Close'].iloc[-1] / frame['Close'].iloc[-64] - 1.0)
    assert strength_6m == pytest.approx(frame['Close'].iloc[-1] / frame['Close'].iloc[-127] - 1.0)
    assert detector_calls == ['AAPL']
    assert len(summary.candidates) == 1



def test_qullamaggie_helper_allowed_family_filter_is_limited_to_v1_set() -> None:
    assert allowed_detector_families_for_qullamaggie('qullamaggie') == DEFAULT_ALLOWED_FAMILIES
    assert allowed_detector_families_for_qullamaggie('oneil') is None
    assert DEFAULT_ALLOWED_FAMILIES == {'qullamaggie_breakout_family', 'qullamaggie_ep_family'}



def test_qullamaggie_helper_entry_trigger_falls_back_without_orh_metadata() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_low': 101.0},
    )

    assert resolved == {
        'entry_trigger': 'breakout_level',
        'entry_label': 'Breakout level',
        'entry_price_reference': 104.5,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': None,
    }


def test_qullamaggie_helper_entry_trigger_prefers_orh_when_present() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_high': 105.25, 'orh_low': 101.0, 'orh_window_minutes': 30},
    )

    assert resolved == {
        'entry_trigger': 'orh_breakout',
        'entry_label': 'ORH 30m high',
        'entry_price_reference': 105.25,
        'orh_high': 105.25,
        'orh_low': 101.0,
        'orh_window_minutes': 30,
    }


def test_qullamaggie_helper_entry_trigger_uses_entry_zone_low_when_breakout_level_missing() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=None),
        execution_metadata={'orh_low': 101.0},
    )

    assert resolved == {
        'entry_trigger': 'entry_zone_low',
        'entry_label': 'Entry zone low',
        'entry_price_reference': 103.0,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': None,
    }


def test_qullamaggie_helper_ignores_nan_orh_high_and_falls_back() -> None:
    resolved = resolve_qullamaggie_entry_trigger(
        _candidate(breakout_level=104.5),
        execution_metadata={'orh_high': float('nan'), 'orh_low': 101.0, 'orh_window_minutes': 30},
    )

    assert resolved == {
        'entry_trigger': 'breakout_level',
        'entry_label': 'Breakout level',
        'entry_price_reference': 104.5,
        'orh_high': None,
        'orh_low': 101.0,
        'orh_window_minutes': 30,
    }
