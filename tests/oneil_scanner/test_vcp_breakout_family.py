from __future__ import annotations

import importlib

import pandas as pd

from scripts.oneil_scanner.preprocess import add_shared_preprocessing


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
    return pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
            'Open': [price * 0.998 for price in closes],
            'High': [price * 1.01 for price in closes],
            'Low': [price * 0.99 for price in closes],
            'Close': closes,
            'Volume': volumes,
        }
    )


def _load_detector():
    try:
        module = importlib.import_module('scripts.oneil_scanner.detectors.vcp_breakout_family')
    except ModuleNotFoundError as exc:
        raise AssertionError('Task 4 detector module is missing') from exc
    return module


def _detect(frame: pd.DataFrame, *, symbol: str = 'TEST'):
    module = _load_detector()
    enriched = add_shared_preprocessing(frame)
    return module.detect_vcp_breakout_family(enriched, symbol=symbol, trend_template_pass=True)


def _textbook_vcp_frame(*, breakout: bool) -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (100.0, 150),
        (84.0, 14),
        (98.0, 12),
        (89.0, 10),
        (99.0, 10),
        (93.0, 8),
        (99.5, 8),
        (96.0, 6),
        ((101.5 if breakout else 99.2), 6),
    )
    volumes = [2_400_000.0] * 150 + [2_000_000.0] * 14 + [1_700_000.0] * 12 + [1_500_000.0] * 10 + [1_300_000.0] * 10 + [1_100_000.0] * 8 + [950_000.0] * 8 + [825_000.0] * 6 + [2_800_000.0] * 6
    frame['Volume'] = volumes[: len(frame)]
    return frame


def _high_breakout_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (90.0, 180),
        (96.0, 20),
        (93.0, 12),
        (99.0, 15),
        (97.0, 10),
        (103.0, 5),
    )
    frame['Volume'] = [1_600_000.0] * (len(frame) - 5) + [3_200_000.0] * 5
    return frame


def _platform_breakout_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (30.0, 0),
        (86.0, 120),
        (74.0, 30),
        (80.0, 20),
        (74.0, 10),
        (79.0, 10),
        (75.5, 10),
        (81.5, 6),
    )
    frame['Volume'] = [1_900_000.0] * 120 + [1_700_000.0] * 30 + [1_550_000.0] * 20 + [1_450_000.0] * 30 + [3_100_000.0] * 6
    return frame


def test_family_detector_returns_textbook_vcp_candidate() -> None:
    candidates = _detect(_textbook_vcp_frame(breakout=False))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_family == 'vcp_breakout_family'
    assert candidate.pattern_type == 'vcp'
    assert candidate.pattern_variant == 'textbook'
    assert candidate.breakout_level is not None
    assert any('contraction_depths=' in note for note in candidate.notes)
    assert any('breakout_confirmation=False' in note for note in candidate.notes)


def test_family_detector_returns_52_week_high_breakout_candidate() -> None:
    candidates = _detect(_high_breakout_frame())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == '52-week-high-breakout'
    assert candidate.pattern_variant == 'new-high'
    assert candidate.volume_confirmation == 'confirmed'
    assert any('pivot=' in note for note in candidate.notes)
    assert any('breakout_confirmation=True' in note for note in candidate.notes)


def test_family_detector_returns_platform_breakout_candidate() -> None:
    candidates = _detect(_platform_breakout_frame())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == 'platform-breakout'
    assert candidate.pattern_variant == 'consolidation'
    assert candidate.entry_zone_high is not None
    assert any('volume_dry_up_quality=' in note for note in candidate.notes)


def test_family_detector_collapses_overlapping_hits_into_single_output() -> None:
    candidates = _detect(_textbook_vcp_frame(breakout=True))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_type == 'vcp'
    assert 'platform-breakout' in candidate.secondary_signals
    assert '52-week-high-breakout' in candidate.secondary_signals
