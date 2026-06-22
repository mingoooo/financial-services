from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.presets import apply_strategy_preset, load_strategy_spec
from reversal_lib.strategy.spec import StrategySpec


def test_main_preset_maps_to_explicit_strategy_spec_fields() -> None:
    spec = load_strategy_spec('main', overrides={})

    assert isinstance(spec, StrategySpec)
    assert spec.side == 'bullish'
    assert spec.min_r_multiple == 1.5
    assert spec.require_confirm_volume is True
    assert spec.confirm_volume_multiplier == 1.5
    assert spec.require_fresh_sma_cross_up is False
    assert spec.sma_cross_mode == 'either'
    assert spec.require_standard_uptrend is True
    assert spec.require_macd_bullish is False
    assert spec.require_rsi_above is None
    assert spec.require_above_sma200 is False
    assert spec.entry_mode == 'confirm_close'
    assert spec.stop_mode == 'confirm_low'
    assert spec.target_mode == 'nearest_resistance'
    assert spec.indicator_config == {}


def test_high_quality_preset_maps_to_explicit_strategy_spec_fields() -> None:
    spec = load_strategy_spec('high_quality', overrides={})

    assert isinstance(spec, StrategySpec)
    assert spec.side == 'bullish'
    assert spec.min_r_multiple == 1.5
    assert spec.require_confirm_volume is True
    assert spec.confirm_volume_multiplier == 1.5
    assert spec.require_standard_uptrend is True
    assert spec.require_macd_bullish is True
    assert spec.entry_mode == 'confirm_close'
    assert spec.stop_mode == 'confirm_low'
    assert spec.target_mode == 'nearest_resistance'


def test_loader_applies_explicit_overrides_without_mutating_preset_defaults() -> None:
    base = load_strategy_spec('main', overrides={})
    overridden = load_strategy_spec('main', overrides={
        'require_macd_bullish': True,
        'entry_mode': 'next_open',
        'indicator_config': {'location_tolerance_ratio': 0.03},
    })

    assert overridden.require_macd_bullish is True
    assert overridden.entry_mode == 'next_open'
    assert overridden.indicator_config == {'location_tolerance_ratio': 0.03}

    assert base.require_macd_bullish is False
    assert base.entry_mode == 'confirm_close'
    assert base.indicator_config == {}


def test_loader_bridges_legacy_indicator_override_keys() -> None:
    spec = load_strategy_spec('main', overrides={
        'require_trend_alignment': True,
        'require_location_alignment': True,
        'location_tolerance_ratio': 0.03,
        'allowed_patterns': ['hammer', 'engulfing'],
    })

    assert spec.indicator_config == {
        'require_trend_alignment': True,
        'require_location_alignment': True,
        'location_tolerance_ratio': 0.03,
        'allowed_patterns': ['hammer', 'engulfing'],
    }


def test_apply_strategy_preset_delegates_current_options_through_strategy_spec() -> None:
    options = {
        'side': 'bearish',
        'min_r_multiple': 2.0,
        'require_macd_bullish': True,
        'entry_mode': 'next_open',
        'indicator_config': {'location_tolerance_ratio': 0.05},
        'require_trend_alignment': True,
        'require_location_alignment': True,
        'location_tolerance_ratio': 0.03,
        'allowed_patterns': ['hammer'],
        'universe': 'custom',
        'include_etfs': False,
    }

    merged = apply_strategy_preset(options, 'main')

    assert merged['side'] == 'bearish'
    assert merged['min_r_multiple'] == 2.0
    assert merged['require_macd_bullish'] is True
    assert merged['entry_mode'] == 'next_open'
    assert merged['require_trend_alignment'] is True
    assert merged['require_location_alignment'] is True
    assert merged['location_tolerance_ratio'] == 0.03
    assert merged['allowed_patterns'] == ['hammer']
    assert merged['universe'] == 'sp500'
    assert merged['include_etfs'] is True


def test_apply_strategy_preset_merges_indicator_config_with_legacy_indicator_overrides() -> None:
    merged = apply_strategy_preset({
        'indicator_config': {'location_tolerance_ratio': 0.05, 'allowed_patterns': ['inside_bar']},
        'require_location_alignment': True,
    }, 'main')

    assert merged['require_location_alignment'] is True
    assert merged['location_tolerance_ratio'] == 0.05
    assert merged['allowed_patterns'] == ['inside_bar']
