from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.domain.models import IndicatorContext, PatternHit, SignalCandidate
from reversal_lib.indicators.context import build_indicator_context, prepare_indicator_context_inputs
from reversal_lib.models import Candle
from reversal_lib.presets import apply_strategy_preset, load_strategy_spec
from reversal_lib.strategy.rules import evaluate_signal
from reversal_lib.strategy.spec import StrategySpec
from reversal_lib.strategy.trade_plan import build_trade_plan

FIXTURE_DIR = ROOT / 'tests' / 'fixtures' / 'reversal'


def _load_candles(name: str) -> list[Candle]:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding='utf-8'))
    return [Candle(**item) for item in payload]


def _candidate_from_fixture() -> tuple[list[Candle], SignalCandidate]:
    candles = _load_candles('main_preset_fixture.json')
    candidate_index = 91
    confirm_index = candidate_index + 1
    confirm = candles[confirm_index]
    hit = PatternHit(
        symbol='META',
        pattern='Inverted Hammer / 倒锤头线',
        candidate_index=candidate_index,
        candidate_date='2021-10-28',
        confirm_index=confirm_index,
        confirm_date='2021-10-29',
    )
    signal = SignalCandidate(
        hit=hit,
        side='bullish',
        confirm_close=confirm.close,
        planned_entry_price=confirm.close,
        stop_loss=307.7,
        first_target=330.21,
        second_target=335.85,
        confirm_volume=confirm.volume,
        avg_volume_20=sum(c.volume for c in candles[candidate_index - 19:candidate_index + 1]) / 20,
        avg_dollar_volume_20=sum(c.close * c.volume for c in candles[candidate_index - 19:candidate_index + 1]) / 20,
        entry_mode='confirm_close',
        market_cap=1_000_000_000,
    )
    return candles, signal


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


def test_build_indicator_context_computes_expected_fields_from_fixture() -> None:
    candles, signal = _candidate_from_fixture()
    prepared = prepare_indicator_context_inputs(candles)
    context = build_indicator_context(candles, signal.hit.candidate_index, signal.confirm_close, inputs=prepared)
    assert context.indicator_context.trend_context == 'bearish'
    assert context.indicator_context.location_context == 'neutral'
    assert context.indicator_context.sma_cross_context == 'none'
    assert context.indicator_context.macd_context == 'bearish'
    assert context.indicator_context.above_sma200 is False
    assert context.indicator_context.rsi_value == 41.182


def test_evaluate_signal_accepts_and_rejects_based_on_strategy_spec() -> None:
    candles, signal = _candidate_from_fixture()
    prepared = prepare_indicator_context_inputs(candles)
    context = build_indicator_context(candles, signal.hit.candidate_index, signal.confirm_close, inputs=prepared)
    accepted, enriched = evaluate_signal(signal, context, load_strategy_spec('main', overrides={}))
    assert accepted is True
    assert isinstance(enriched.indicator_context, IndicatorContext)
    assert enriched.indicator_context.trend_context == 'bearish'

    rejected, _ = evaluate_signal(signal, context, load_strategy_spec('main', overrides={'allowed_patterns': ['hammer']}))
    assert rejected is False

    rejected_by_macd, _ = evaluate_signal(signal, context, load_strategy_spec('high_quality', overrides={}))
    assert rejected_by_macd is False


def test_build_trade_plan_derives_expected_entry_stop_target_fields() -> None:
    candles, signal = _candidate_from_fixture()
    plan = build_trade_plan(signal, candles, stop_mode='confirm_low', target_mode='nearest_resistance')
    assert plan.entry_date == '2021-10-29'
    assert plan.entry_price == 316.92
    assert plan.stop_loss == 308.11
    assert plan.target_price == 330.21
    assert plan.signal.structural_r_multiple == 1.5085
