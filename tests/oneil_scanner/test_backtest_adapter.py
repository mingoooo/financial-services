from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.oneil_scanner import ScannerBacktestSignal, candidate_to_signal, collapse_candidates_for_day
from scripts.oneil_scanner import backtest_adapter as adapter
from scripts.oneil_scanner.models import PatternCandidate


def _candidate(
    *,
    symbol: str = 'AAPL',
    pattern_family: str = 'ibd_base_family',
    pattern_type: str = 'cup-with-handle',
    pattern_variant: str = 'standard',
    trigger_date: str = '2026-07-17',
    breakout_level: float = 215.5,
    stop_reference: float = 205.0,
    quality_score: float | None = 92.0,
    setup_score: float | None = 96.0,
    rs_score: float | None = 98.0,
) -> PatternCandidate:
    return PatternCandidate(
        symbol=symbol,
        pattern_family=pattern_family,
        pattern_type=pattern_type,
        pattern_variant=pattern_variant,
        trigger_date=trigger_date,
        breakout_level=breakout_level,
        entry_zone_low=breakout_level,
        entry_zone_high=breakout_level * 1.05,
        stop_reference=stop_reference,
        trend_template_pass=True,
        rs_score=rs_score,
        distance_to_52w_high=0.02,
        volume_confirmation='confirmed',
        catalyst_type='technical_breakout',
        catalyst_confidence=0.75,
        quality_score=quality_score,
        setup_score=setup_score,
        report_rank=None,
        secondary_signals=[],
        notes=[],
    )


def test_candidate_to_signal_converts_one_supported_candidate() -> None:
    candidate = _candidate()

    signal = candidate_to_signal(candidate)

    assert isinstance(signal, ScannerBacktestSignal)
    assert signal.symbol == 'AAPL'
    assert signal.trigger_date == '2026-07-17'
    assert signal.entry_date == '2026-07-20'
    assert signal.entry_price_ref == 215.5
    assert signal.breakout_level == 215.5
    assert signal.stop_reference == 205.0
    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == ()
    assert signal.ranking_score == pytest.approx(95.2)


def test_collapse_candidates_for_day_merges_secondary_patterns() -> None:
    cup_hit = _candidate(pattern_type='cup-with-handle', pattern_variant='standard', setup_score=96.0, quality_score=92.0)
    flat_base_hit = _candidate(pattern_type='flat-base', pattern_variant='tight', setup_score=88.0, quality_score=90.0)

    signal = collapse_candidates_for_day([cup_hit, flat_base_hit])

    assert signal.symbol == 'AAPL'
    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == ('ibd_base_family:flat-base:tight',)


def test_collapse_candidates_for_day_uses_ranking_score_to_choose_primary() -> None:
    lower_quality_better_setup = _candidate(
        pattern_type='cup-with-handle',
        pattern_variant='standard',
        quality_score=90.0,
        setup_score=97.0,
        rs_score=98.0,
    )
    higher_quality_weaker_setup = _candidate(
        pattern_type='flat-base',
        pattern_variant='tight',
        quality_score=94.0,
        setup_score=86.0,
        rs_score=88.0,
    )

    signal = collapse_candidates_for_day([higher_quality_weaker_setup, lower_quality_better_setup])

    assert signal.primary_pattern_type == 'cup-with-handle'
    assert signal.secondary_patterns == ('ibd_base_family:flat-base:tight',)
    assert signal.ranking_score == pytest.approx(95.1)


@pytest.mark.parametrize('unsupported_family', ['event_driven_family', 'momentum_continuation_family'])
def test_candidate_to_signal_rejects_unsupported_v1_families(unsupported_family: str) -> None:
    candidate = _candidate(pattern_family=unsupported_family, pattern_type='unsupported-pattern')

    with pytest.raises(ValueError, match='unsupported'):
        candidate_to_signal(candidate)


@pytest.mark.parametrize(
    ('pattern_family', 'pattern_type'),
    [
        ('ibd_base_family', 'cup-with-handel'),
        ('vcp_breakout_family', 'pivot-breakout'),
    ],
)
def test_candidate_to_signal_rejects_unknown_v1_pattern_types(pattern_family: str, pattern_type: str) -> None:
    candidate = _candidate(pattern_family=pattern_family, pattern_type=pattern_type)

    with pytest.raises(ValueError, match='pattern_type'):
        candidate_to_signal(candidate)


def test_candidate_to_signal_uses_next_business_day_placeholder() -> None:
    friday_candidate = _candidate(trigger_date='2026-07-17')
    monday_candidate = _candidate(trigger_date='2026-07-20')

    friday_signal = candidate_to_signal(friday_candidate)
    monday_signal = candidate_to_signal(monday_candidate)

    assert friday_signal.entry_date == '2026-07-20'
    assert monday_signal.entry_date == '2026-07-21'


def test_candidate_to_signal_renormalizes_ranking_when_rs_missing() -> None:
    candidate = _candidate(rs_score=None, setup_score=80.0, quality_score=90.0)

    signal = candidate_to_signal(candidate)

    assert signal.ranking_score == pytest.approx(83.75)


def _bars(symbol: str, days: int = 220, *, start: str = '2025-01-01') -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=days, freq='B')
    close = pd.Series([100.0 + index * 0.5 for index in range(days)])
    return pd.DataFrame(
        {
            'Date': dates,
            'Open': close - 0.4,
            'High': close + 0.8,
            'Low': close - 1.0,
            'Close': close,
            'Volume': [2_000_000.0] * days,
            'AvgDollarVolume20': [25_000_000.0] * days,
            'AvgVolume20': [1_500_000.0] * days,
            'BreakoutVolumeRatio': [1.3] * days,
            'RSProxy': [95.0] * days,
            'ClosePctFrom52WHigh': [-0.01] * days,
            'CompanyName': [f'{symbol} Inc.'] * days,
            'Exchange': ['NASDAQ'] * days,
        }
    )


def test_day_cache_round_trip(tmp_path: Path) -> None:
    day = '2026-07-17'
    signal = candidate_to_signal(_candidate(trigger_date=day))

    cache_path = adapter.write_cached_day_signals(tmp_path, day, [signal], warnings=['cached warning'])
    cached = adapter.load_cached_day_signals(tmp_path, day)

    assert cache_path == tmp_path / '2026-07-17.json'
    assert cached.date == day
    assert cached.signals == (signal,)
    assert cached.warnings == ('cached warning',)


def test_corrupt_cache_rebuilds_day_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target_day = '2026-07-17'
    other_day = '2026-07-18'
    adapter.day_cache_path(tmp_path, target_day).parent.mkdir(parents=True, exist_ok=True)
    adapter.day_cache_path(tmp_path, target_day).write_text('{not valid json', encoding='utf-8')
    adapter.write_cached_day_signals(tmp_path, other_day, [candidate_to_signal(_candidate(trigger_date=other_day))])

    monkeypatch.setattr(adapter, 'evaluate_eligibility', lambda *args, **kwargs: SimpleNamespace(passes=True))

    built_calls: list[str] = []

    def detector(frame: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        built_calls.append(symbol)
        return [_candidate(symbol=symbol, trigger_date=target_day)]

    result = adapter.load_or_build_day_signals(
        cache_dir=tmp_path,
        day=target_day,
        frames_by_symbol={'AAPL': _bars('AAPL')},
        detector_registry={'ibd_base_family': detector},
        preprocess_frame=lambda frame, **kwargs: frame,
        trend_filter_fn=lambda frame: SimpleNamespace(passes=True, trend_template_pass=True),
    )

    assert built_calls == ['AAPL']
    assert result.date == target_day
    assert result.signals[0].symbol == 'AAPL'
    assert any('Corrupt scanner cache' in warning for warning in result.warnings)
    assert adapter.load_cached_day_signals(tmp_path, other_day).signals[0].trigger_date == other_day


def test_historical_scan_uses_bars_through_trigger_day_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = '2025-08-01'
    frame = _bars('AAPL', days=260, start='2025-01-01')
    seen_last_dates: list[str] = []
    monkeypatch.setattr(adapter, 'evaluate_eligibility', lambda *args, **kwargs: SimpleNamespace(passes=True))

    def detector(snapshot: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        seen_last_dates.append(snapshot.iloc[-1]['Date'].strftime('%Y-%m-%d'))
        return [_candidate(symbol=symbol, trigger_date=day)]

    result = adapter.load_or_build_day_signals(
        cache_dir=tmp_path,
        day=day,
        frames_by_symbol={'AAPL': frame},
        refresh=True,
        detector_registry={'ibd_base_family': detector},
        preprocess_frame=lambda snapshot, **kwargs: snapshot,
        trend_filter_fn=lambda snapshot: SimpleNamespace(passes=True, trend_template_pass=True),
    )

    assert seen_last_dates == [day]
    assert result.signals[0].trigger_date == day


def test_historical_scan_returns_only_hits_triggered_on_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = '2025-08-01'
    monkeypatch.setattr(adapter, 'evaluate_eligibility', lambda *args, **kwargs: SimpleNamespace(passes=True))

    def detector(frame: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        return [
            _candidate(symbol=symbol, trigger_date='2025-07-31', pattern_type='flat-base', setup_score=91.0),
            _candidate(symbol=symbol, trigger_date=day, pattern_type='cup-with-handle', setup_score=96.0),
        ]

    result = adapter.load_or_build_day_signals(
        cache_dir=tmp_path,
        day=day,
        frames_by_symbol={'AAPL': _bars('AAPL')},
        refresh=True,
        detector_registry={'ibd_base_family': detector},
        preprocess_frame=lambda frame, **kwargs: frame,
        trend_filter_fn=lambda frame: SimpleNamespace(passes=True, trend_template_pass=True),
    )

    assert len(result.signals) == 1
    assert result.signals[0].trigger_date == day
    assert result.signals[0].primary_pattern_type == 'cup-with-handle'


def test_symbol_level_failure_does_not_abort_whole_day_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = '2025-08-01'
    monkeypatch.setattr(adapter, 'evaluate_eligibility', lambda *args, **kwargs: SimpleNamespace(passes=True))

    def preprocess(frame: pd.DataFrame, **kwargs: object) -> pd.DataFrame:
        if frame.iloc[-1]['CompanyName'].startswith('BROKEN'):
            raise RuntimeError('bad frame')
        return frame

    def detector(frame: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        return [_candidate(symbol=symbol, trigger_date=day)]

    frames = {
        'AAPL': _bars('AAPL'),
        'BROKEN': _bars('BROKEN').assign(CompanyName='BROKEN Inc.'),
    }

    result = adapter.load_or_build_day_signals(
        cache_dir=tmp_path,
        day=day,
        frames_by_symbol=frames,
        refresh=True,
        detector_registry={'ibd_base_family': detector},
        preprocess_frame=preprocess,
        trend_filter_fn=lambda frame: SimpleNamespace(passes=True, trend_template_pass=True),
    )

    assert [signal.symbol for signal in result.signals] == ['AAPL']
    assert any('BROKEN scan failed' in warning for warning in result.warnings)


def test_family_level_failure_does_not_abort_other_families_for_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = '2025-08-01'
    monkeypatch.setattr(adapter, 'evaluate_eligibility', lambda *args, **kwargs: SimpleNamespace(passes=True))

    def broken_detector(frame: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        raise RuntimeError('detector boom')

    def working_detector(frame: pd.DataFrame, *, symbol: str, **kwargs: object) -> list[PatternCandidate]:
        return [_candidate(symbol=symbol, trigger_date=day, pattern_family='vcp_breakout_family', pattern_type='vcp')]

    result = adapter.load_or_build_day_signals(
        cache_dir=tmp_path,
        day=day,
        frames_by_symbol={'AAPL': _bars('AAPL')},
        refresh=True,
        detector_registry={
            'ibd_base_family': broken_detector,
            'vcp_breakout_family': working_detector,
        },
        preprocess_frame=lambda frame, **kwargs: frame,
        trend_filter_fn=lambda frame: SimpleNamespace(passes=True, trend_template_pass=True),
    )

    assert len(result.signals) == 1
    assert result.signals[0].primary_pattern_family == 'vcp_breakout_family'
    assert any('ibd_base_family detector failed' in warning for warning in result.warnings)
