from __future__ import annotations

import pandas as pd
import pytest

from scripts.vcp_lib.indicators import add_core_indicators
from scripts.vcp_lib.vcp_detector import (
    build_swing_legs,
    detect_52_week_high_breakout,
    detect_vcp,
    evaluate_prior_uptrend,
    segment_swings,
)


def _piecewise_frame(*segments: tuple[float, int], volumes: list[float] | None = None) -> pd.DataFrame:
    closes: list[float] = []
    current = segments[0][0]
    for target, length in segments[1:]:
        step = (target - current) / max(length, 1)
        for index in range(length):
            closes.append(current + step * (index + 1))
        current = target
    if volumes is None:
        volumes = [2_000_000.0] * len(closes)
    frame = pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
            'Open': [price * 0.998 for price in closes],
            'High': [price * 1.01 for price in closes],
            'Low': [price * 0.99 for price in closes],
            'Close': closes,
            'Volume': volumes,
        }
    )
    return frame


def _textbook_vcp_frame(*, breakout: bool) -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (100.0, 180),
        (84.0, 14),
        (98.0, 12),
        (89.0, 10),
        (99.0, 10),
        (93.0, 8),
        (99.5, 8),
        (96.0, 6),
        ((101.5 if breakout else 99.2), 6),
    )
    volumes = [2_400_000.0] * 180 + [2_000_000.0] * 14 + [1_700_000.0] * 12 + [1_500_000.0] * 10 + [1_300_000.0] * 10 + [1_100_000.0] * 8 + [950_000.0] * 8 + [825_000.0] * 6 + [2_800_000.0] * 6
    frame['Volume'] = volumes[: len(frame)]
    return frame


def _defective_vcp_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (100.0, 150),
        (84.0, 10),
        (97.0, 8),
        (88.0, 12),
        (99.0, 8),
        (92.5, 15),
        (111.0, 6),
    )
    volumes = [2_200_000.0] * 150 + [1_800_000.0] * 10 + [1_950_000.0] * 8 + [2_050_000.0] * 12 + [2_150_000.0] * 8 + [2_250_000.0] * 15 + [3_000_000.0] * 6
    frame['Volume'] = volumes[: len(frame)]
    return frame


def _short_context_high_breakout_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (90.0, 150),
        (96.0, 20),
        (93.0, 12),
        (99.0, 15),
        (97.0, 10),
        (103.0, 5),
    )
    frame['Volume'] = [1_600_000.0] * (len(frame) - 5) + [3_200_000.0] * 5
    return frame


def test_detect_vcp_insufficient_history() -> None:
    frame = pd.DataFrame({'Close': [10.0] * 50, 'High': [10.2] * 50, 'Low': [9.8] * 50, 'Volume': [1000] * 50})
    result = detect_vcp(frame)
    assert result.detected is False
    assert 'insufficient-history' in result.defects


def test_segment_swings_returns_turning_points() -> None:
    closes = [
        10, 11, 12, 13, 14, 15, 14, 13, 12, 13, 14, 15, 16, 17, 16, 15, 14,
        15, 16, 17, 18, 17, 16, 15, 16, 17, 18, 19, 18, 17, 16, 17, 18, 19, 20, 19, 18, 17, 18, 19, 20
    ]
    frame = pd.DataFrame({
        'Date': pd.date_range('2026-01-01', periods=len(closes), freq='D'),
        'Open': closes,
        'High': [c * 1.01 for c in closes],
        'Low': [c * 0.99 for c in closes],
        'Close': closes,
        'Volume': [1000 - i * 5 for i in range(len(closes))],
    })
    swings = segment_swings(frame, min_bars_between_swings=2, pct_reversal=0.04, atr_multiplier=0.2)
    assert len(swings) >= 4
    legs = build_swing_legs(frame, swings)
    assert len(legs) >= 3


def test_prior_uptrend_detects_constructive_structure() -> None:
    closes = [
        50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80,
        78, 76, 74, 76, 78, 80, 82, 84, 83, 81, 79, 81, 83, 85, 84, 82, 81, 82, 83, 84, 85, 86,
    ]
    frame = pd.DataFrame({
        'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
        'Open': closes,
        'High': [c * 1.01 for c in closes],
        'Low': [c * 0.99 for c in closes],
        'Close': closes,
        'Volume': [2_000_000] * len(closes),
    })
    enriched = add_core_indicators(frame)
    swings = segment_swings(enriched, min_bars_between_swings=2, pct_reversal=0.04, atr_multiplier=0.2)
    ok, reasons = evaluate_prior_uptrend(enriched, swings)
    assert ok or reasons


def test_detect_vcp_reports_adapter_friendly_evidence() -> None:
    enriched = add_core_indicators(_textbook_vcp_frame(breakout=False))

    result = detect_vcp(enriched)

    assert result.detected is True
    assert len(result.contraction_depths) >= 3
    assert result.contraction_depths == sorted(result.contraction_depths, reverse=True)
    assert result.pivot_price == pytest.approx(100.495, rel=1e-3)
    assert result.distance_to_pivot_pct == pytest.approx(-0.0129, rel=1e-1)
    assert result.volume_dry_up is True
    assert result.volume_dry_up_quality is not None
    assert result.breakout_confirmation is False


def test_detect_vcp_flags_breakout_confirmation_when_price_clears_pivot_on_volume() -> None:
    enriched = add_core_indicators(_textbook_vcp_frame(breakout=True))

    result = detect_vcp(enriched)

    assert result.detected is True
    assert result.breakout_confirmation is True
    assert result.breakout_volume_ratio is not None
    assert result.breakout_volume_ratio > 1.2


def test_detect_vcp_rejects_extended_non_dry_structure() -> None:
    enriched = add_core_indicators(_defective_vcp_frame())

    result = detect_vcp(enriched)

    assert result.detected is False
    assert 'volume-not-drying-up' in result.defects
    assert 'leg-duration-worsening' in result.defects
    assert 'too-extended-from-pivot' in result.defects


def test_detect_52_week_high_breakout_requires_true_252_day_context() -> None:
    enriched = add_core_indicators(_short_context_high_breakout_frame())

    result = detect_52_week_high_breakout(enriched)

    assert result.detected is False
    assert 'insufficient-252-day-context' in result.notes
