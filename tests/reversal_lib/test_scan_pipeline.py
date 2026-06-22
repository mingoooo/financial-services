from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.domain.requests import UniverseRequest
from reversal_lib.pipeline import scan_pipeline
from reversal_lib.presets import apply_strategy_preset
from reversal_lib.strategy.spec import StrategySpec

FIXTURE_DIR = ROOT / 'tests' / 'fixtures' / 'reversal'


def _load_candles(name: str) -> list[Candle]:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding='utf-8'))
    return [Candle(**item) for item in payload]


def _preset_spec(preset: str) -> StrategySpec:
    base = {
        'side': 'bullish',
        'require_confirm_volume': True,
        'confirm_volume_multiplier': 1.5,
        'min_r_multiple': 1.5,
        'require_trend_alignment': False,
        'require_location_alignment': False,
        'location_tolerance_ratio': 0.02,
        'allowed_patterns': None,
        'require_fresh_sma_cross_up': False,
        'sma_cross_mode': 'either',
        'require_macd_bullish': False,
        'require_rsi_above': None,
        'require_above_sma200': False,
        'entry_mode': 'confirm_close',
        'stop_mode': 'confirm_low',
        'target_mode': 'nearest_resistance',
    }
    options = apply_strategy_preset(base, preset)
    return StrategySpec(
        side=options['side'],
        min_r_multiple=options['min_r_multiple'],
        require_confirm_volume=options['require_confirm_volume'],
        confirm_volume_multiplier=options['confirm_volume_multiplier'],
        require_fresh_sma_cross_up=options['require_fresh_sma_cross_up'],
        sma_cross_mode=options['sma_cross_mode'],
        require_standard_uptrend=options['require_trend_alignment'],
        require_macd_bullish=options['require_macd_bullish'],
        require_rsi_above=options['require_rsi_above'],
        require_above_sma200=options['require_above_sma200'],
        entry_mode=options['entry_mode'],
        stop_mode=options['stop_mode'],
        target_mode=options['target_mode'],
        indicator_config={
            'require_trend_alignment': options['require_trend_alignment'],
            'require_location_alignment': options['require_location_alignment'],
            'location_tolerance_ratio': options['location_tolerance_ratio'],
            'allowed_patterns': None,
        },
    )


def _scan_fixture(fixture_name: str, symbol: str, preset: str):
    candles = _load_candles(fixture_name)
    spec = _preset_spec(preset)
    original_fetch = scan_pipeline.fetch_candles
    original_resolve = scan_pipeline.resolve_prefiltered_universe
    scan_pipeline.fetch_candles = lambda requested_symbol, range_str='5y': candles if requested_symbol == symbol else []
    scan_pipeline.resolve_prefiltered_universe = lambda request, range_str='5y': [type('Meta', (), {'symbol': symbol, 'market_cap': None})()]
    try:
        return scan_pipeline.run_scan(spec, UniverseRequest(universe='us', symbols=[symbol]), '5y')
    finally:
        scan_pipeline.fetch_candles = original_fetch
        scan_pipeline.resolve_prefiltered_universe = original_resolve


def test_bullish_fixture_produces_expected_main_signals() -> None:
    signals = _scan_fixture('aapl_bullish_fixture.json', 'META', 'main')
    assert len(signals) == 2
    assert [signal.hit.confirm_date for signal in signals] == ['2021-10-28', '2023-07-27']


def test_no_signal_fixture_produces_zero_signals() -> None:
    main_signals = _scan_fixture('no_signal_fixture.json', 'AAPL', 'main')
    high_quality_signals = _scan_fixture('no_signal_fixture.json', 'AAPL', 'high_quality')
    assert len(main_signals) == 0
    assert len(high_quality_signals) == 0


@pytest.mark.parametrize(
    ('fixture_name', 'symbol', 'preset', 'expected_count', 'expected_dates'),
    [
        ('main_preset_fixture.json', 'META', 'main', 2, ['2021-10-28', '2023-07-27']),
        ('high_quality_fixture.json', 'APLE', 'high_quality', 1, ['2024-06-11']),
    ],
)
def test_preset_fixtures_lock_expected_signal_counts(
    fixture_name: str,
    symbol: str,
    preset: str,
    expected_count: int,
    expected_dates: list[str],
) -> None:
    signals = _scan_fixture(fixture_name, symbol, preset)
    assert len(signals) == expected_count
    assert [signal.hit.confirm_date for signal in signals] == expected_dates
