from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.domain.requests import UniverseRequest
from reversal_lib.pipeline import backtest_pipeline
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


def _run_fixture(fixture_name: str, symbol: str, preset: str):
    candles = _load_candles(fixture_name)
    spec = _preset_spec(preset)
    original_fetch = backtest_pipeline.fetch_candles
    original_run_scan = backtest_pipeline.run_scan
    from reversal_lib.pipeline.scan_pipeline import scan_candles
    backtest_pipeline.fetch_candles = lambda requested_symbol, range_str='5y': candles if requested_symbol == symbol else []
    backtest_pipeline.run_scan = lambda current_spec, request, range_str: scan_candles(candles, symbol=symbol, market_cap=None, spec=current_spec)
    try:
        result = backtest_pipeline.run_backtest(spec, UniverseRequest(universe='us', symbols=[symbol]), '5y')
    finally:
        backtest_pipeline.fetch_candles = original_fetch
        backtest_pipeline.run_scan = original_run_scan
    return result.signals, result.trades, result.summary


def test_main_fixture_backtest_summary_is_locked() -> None:
    signals, trades, summary = _run_fixture('main_preset_fixture.json', 'META', 'main')
    assert len(signals) == 2
    assert len(trades) == 2
    assert summary.total_trades == 2
    assert summary.win_rate == 100.0
    assert summary.average_return_pct == 3.6092
    assert summary.total_pnl == 7297.7603
    assert summary.sharpe_ratio == 1.8503


def test_high_quality_fixture_backtest_summary_is_locked() -> None:
    signals, trades, summary = _run_fixture('high_quality_fixture.json', 'APLE', 'high_quality')
    assert len(signals) == 1
    assert len(trades) == 1
    assert summary.total_trades == 1
    assert summary.win_rate == 100.0
    assert summary.average_return_pct == 2.095
    assert summary.total_pnl == 2094.9013
    assert trades[0].confirm_date == '2024-06-11'
    assert trades[0].exit_reason == 'eod'
