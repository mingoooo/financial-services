from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.domain.models import PatternHit
from reversal_lib.models import Candle
from reversal_lib.patterns_layer.bullish import detect_bullish_pattern_hit
from reversal_lib.patterns_layer.bearish import detect_bearish_pattern_hit
from reversal_lib.patterns_layer.levels import find_support_levels, find_resistance_levels
from reversal_lib.patterns_layer.scoring import compute_signal_score


def test_bullish_pattern_detection_returns_pattern_hit() -> None:
    candles = [
        Candle(ts=1, open=10.0, high=10.2, low=8.7, close=9.0, volume=1000),
        Candle(ts=2, open=8.95, high=10.1, low=8.9, close=10.0, volume=1200),
    ]

    hit = detect_bullish_pattern_hit(candles, 1, symbol='TEST', candidate_date='2024-01-02')

    assert isinstance(hit, PatternHit)
    assert hit.pattern == 'Bullish Engulfing / 看涨吞没'
    assert hit.candidate_index == 1
    assert hit.candidate_date == '2024-01-02'


def test_bearish_pattern_detection_returns_pattern_hit() -> None:
    candles = [
        Candle(ts=1, open=9.0, high=10.2, low=8.9, close=10.0, volume=1000),
        Candle(ts=2, open=10.05, high=10.1, low=8.8, close=9.0, volume=1200),
    ]

    hit = detect_bearish_pattern_hit(candles, 1, symbol='TEST', candidate_date='2024-01-02')

    assert isinstance(hit, PatternHit)
    assert hit.pattern == 'Bearish Engulfing / 看跌吞没'
    assert hit.candidate_index == 1
    assert hit.candidate_date == '2024-01-02'


def test_level_detection_is_deterministic_for_fixed_window() -> None:
    candles = [
        Candle(ts=1, open=10.0, high=10.5, low=9.8, close=10.2, volume=1000),
        Candle(ts=2, open=10.2, high=10.4, low=9.0, close=9.4, volume=1000),
        Candle(ts=3, open=9.4, high=10.1, low=9.3, close=10.0, volume=1000),
        Candle(ts=4, open=10.0, high=11.2, low=9.9, close=10.8, volume=1000),
        Candle(ts=5, open=10.8, high=10.9, low=9.5, close=9.8, volume=1000),
        Candle(ts=6, open=9.8, high=10.3, low=9.7, close=10.1, volume=1000),
        Candle(ts=7, open=10.1, high=11.0, low=10.0, close=10.9, volume=1000),
    ]

    supports_first = find_support_levels(candles, 6, window=2)
    supports_second = find_support_levels(candles, 6, window=2)
    resistances_first = find_resistance_levels(candles, 6, window=2)
    resistances_second = find_resistance_levels(candles, 6, window=2)

    assert supports_first == supports_second
    assert resistances_first == resistances_second


def test_structural_scoring_is_independent_from_strategy_acceptance() -> None:
    score, detail = compute_signal_score(
        pattern_strength='strong',
        confirm_volume=150.0,
        avg_volume_20=100.0,
        market_cap=5_000_000_000,
        avg_dollar_volume_20=200_000_000.0,
    )

    assert score == 84.0
    assert 'Pattern strength: 40.0' in detail
    assert 'Volume ratio: 20.0' in detail
