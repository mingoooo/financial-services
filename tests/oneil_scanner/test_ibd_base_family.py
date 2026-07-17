from __future__ import annotations

import importlib
import json
from pathlib import Path

import pandas as pd

from scripts.oneil_scanner.preprocess import add_shared_preprocessing


FIXTURE_PATH = Path('tests/fixtures/oneil_scanner/ibd_base_family_cases.json')


def _load_detector():
    try:
        module = importlib.import_module('scripts.oneil_scanner.detectors.ibd_base_family')
    except ModuleNotFoundError as exc:
        raise AssertionError('Task 5 detector module is missing') from exc
    return module


def _load_cases() -> dict[str, dict[str, list[list[float | int]]]]:
    return json.loads(FIXTURE_PATH.read_text())


def _piecewise_frame(case_name: str) -> pd.DataFrame:
    case = _load_cases()[case_name]
    segments = case['segments']

    closes: list[float] = []
    current = float(segments[0][0])
    for target, length in segments[1:]:
        step = (float(target) - current) / max(int(length), 1)
        for index in range(int(length)):
            closes.append(current + step * (index + 1))
        current = float(target)

    volumes: list[float] = []
    for length, value in case['volume_blocks']:
        volumes.extend([float(value)] * int(length))

    assert len(closes) == len(volumes)

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


def _detect(case_name: str, *, symbol: str = 'TEST'):
    module = _load_detector()
    enriched = add_shared_preprocessing(_piecewise_frame(case_name))
    return module.detect_ibd_base_family(enriched, symbol=symbol, trend_template_pass=True)


def _assert_candidate_contract(candidate, expected_type: str, expected_variant: str) -> None:
    assert candidate.pattern_family == 'ibd_base_family'
    assert candidate.pattern_type == expected_type
    assert candidate.pattern_variant == expected_variant
    assert candidate.breakout_level is not None
    assert candidate.entry_zone_low == candidate.breakout_level
    assert candidate.entry_zone_high is not None
    assert candidate.entry_zone_high > candidate.entry_zone_low
    assert candidate.stop_reference is not None
    assert candidate.volume_confirmation == 'confirmed'
    assert candidate.catalyst_type == 'technical_breakout'
    assert candidate.quality_score is not None
    assert candidate.setup_score is not None
    assert any(note.startswith('pivot=') for note in candidate.notes)
    assert any(note.startswith('base_depth_pct=') for note in candidate.notes)
    assert any(note.startswith('breakout_volume_ratio=') for note in candidate.notes)


def test_detector_returns_valid_cup_with_handle_candidate() -> None:
    candidates = _detect('valid_cup_with_handle')

    assert len(candidates) == 1
    candidate = candidates[0]
    _assert_candidate_contract(candidate, 'cup-with-handle', 'textbook')
    assert any(note == 'prior_uptrend=True' for note in candidate.notes)
    assert any(note.startswith('handle_depth_pct=') for note in candidate.notes)


def test_detector_returns_valid_flat_base_candidate() -> None:
    candidates = _detect('valid_flat_base')

    assert len(candidates) == 1
    candidate = candidates[0]
    _assert_candidate_contract(candidate, 'flat-base', 'tight')
    assert any(note.startswith('tightness_ratio=') for note in candidate.notes)
    assert any(note.startswith('extension_pct=') for note in candidate.notes)


def test_detector_returns_valid_double_bottom_candidate() -> None:
    candidates = _detect('valid_double_bottom')

    assert len(candidates) == 1
    candidate = candidates[0]
    _assert_candidate_contract(candidate, 'double-bottom', 'w-bottom')
    assert any(note.startswith('midpoint_peak=') for note in candidate.notes)
    assert any(note.startswith('second_low_vs_first_pct=') for note in candidate.notes)


def test_detector_rejects_structurally_invalid_near_misses() -> None:
    assert _detect('invalid_cup_no_prior_uptrend') == []
    assert _detect('invalid_flat_base_too_deep') == []
    assert _detect('invalid_double_bottom_bad_second_low') == []
