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
        module = importlib.import_module('scripts.oneil_scanner.detectors.momentum_continuation_family')
    except ModuleNotFoundError as exc:
        raise AssertionError('Task 6 detector module is missing') from exc
    return module


def _detect(frame: pd.DataFrame, *, symbol: str = 'TEST'):
    module = _load_detector()
    enriched = add_shared_preprocessing(frame)
    return module.detect_momentum_continuation_family(enriched, symbol=symbol, trend_template_pass=True)


def _high_tight_flag_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (50.0, 0),
        (100.0, 35),
        (92.0, 6),
        (97.0, 6),
        (95.5, 4),
        (101.5, 3),
    )
    frame['Volume'] = [2_400_000.0] * 35 + [1_300_000.0] * 16 + [3_600_000.0] * 3
    return frame


def _continuation_breakout_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (72.0, 55),
        (66.0, 8),
        (70.0, 8),
        (67.5, 6),
        (73.2, 4),
    )
    frame['Volume'] = [2_100_000.0] * 55 + [1_500_000.0] * 22 + [3_000_000.0] * 4
    return frame


def _overextended_high_tight_flag_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (50.0, 0),
        (100.0, 35),
        (92.0, 6),
        (97.0, 6),
        (95.5, 4),
        (112.0, 3),
    )
    frame['Volume'] = [2_400_000.0] * 35 + [1_300_000.0] * 16 + [3_700_000.0] * 3
    return frame


def _failed_continuation_frame() -> pd.DataFrame:
    frame = _piecewise_frame(
        (40.0, 0),
        (72.0, 55),
        (66.0, 8),
        (70.0, 8),
        (67.5, 6),
        (70.8, 4),
    )
    frame['Volume'] = [2_100_000.0] * 55 + [1_500_000.0] * 22 + [1_700_000.0] * 4
    return frame


def test_detector_returns_valid_high_tight_flag_candidate() -> None:
    candidates = _detect(_high_tight_flag_frame())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_family == 'momentum_continuation_family'
    assert candidate.pattern_type == 'high-tight-flag'
    assert candidate.pattern_variant == 'textbook'
    assert candidate.breakout_level is not None
    assert candidate.entry_zone_low == candidate.breakout_level
    assert candidate.entry_zone_high is not None
    assert candidate.entry_zone_high > candidate.entry_zone_low
    assert candidate.stop_reference is not None
    assert candidate.volume_confirmation == 'confirmed'
    assert candidate.catalyst_type == 'technical_breakout'
    assert candidate.quality_score is not None
    assert candidate.setup_score is not None
    assert any(note.startswith('prior_advance_pct=') for note in candidate.notes)
    assert any(note.startswith('flag_depth_pct=') for note in candidate.notes)
    assert any(note.startswith('breakout_volume_ratio=') for note in candidate.notes)



def test_detector_returns_valid_continuation_breakout_candidate() -> None:
    candidates = _detect(_continuation_breakout_frame())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_family == 'momentum_continuation_family'
    assert candidate.pattern_type == 'continuation-breakout'
    assert candidate.pattern_variant == 'momentum'
    assert candidate.breakout_level is not None
    assert candidate.volume_confirmation == 'confirmed'
    assert candidate.stop_reference is not None
    assert any(note.startswith('prior_advance_pct=') for note in candidate.notes)
    assert any(note.startswith('consolidation_depth_pct=') for note in candidate.notes)
    assert any(note.startswith('extension_pct=') for note in candidate.notes)



def test_detector_rejects_overextended_and_failed_continuations() -> None:
    assert _detect(_overextended_high_tight_flag_frame()) == []
    assert _detect(_failed_continuation_frame()) == []
