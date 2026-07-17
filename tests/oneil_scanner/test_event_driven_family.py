from __future__ import annotations

import importlib

import pandas as pd

from scripts.oneil_scanner.preprocess import add_shared_preprocessing



def _load_detector_module():
    try:
        return importlib.import_module('scripts.oneil_scanner.detectors.event_driven_family')
    except ModuleNotFoundError as exc:
        raise AssertionError('Task 7 event-driven family detector module is missing') from exc



def _base_frame(*, periods: int = 60, start: float = 40.0, step: float = 0.18, volume: float = 1_000_000.0) -> pd.DataFrame:
    closes = [start + step * index for index in range(periods)]
    return pd.DataFrame(
        {
            'Date': pd.date_range('2025-01-01', periods=periods, freq='D'),
            'Open': [price * 0.998 for price in closes],
            'High': [price * 1.01 for price in closes],
            'Low': [price * 0.99 for price in closes],
            'Close': closes,
            'Volume': [volume] * periods,
        }
    )



def _gap_breakout_frame() -> pd.DataFrame:
    frame = _base_frame()
    frame.loc[frame.index[-1], ['Open', 'High', 'Low', 'Close', 'Volume']] = [
        54.6,
        58.8,
        54.0,
        58.1,
        3_600_000.0,
    ]
    return frame



def _follow_through_frame() -> pd.DataFrame:
    frame = _base_frame()
    frame.loc[frame.index[-3], ['Open', 'High', 'Low', 'Close', 'Volume']] = [
        54.4,
        58.5,
        53.8,
        57.2,
        3_400_000.0,
    ]
    frame.loc[frame.index[-2], ['Open', 'High', 'Low', 'Close', 'Volume']] = [
        57.4,
        59.1,
        56.6,
        58.4,
        1_700_000.0,
    ]
    frame.loc[frame.index[-1], ['Open', 'High', 'Low', 'Close', 'Volume']] = [
        58.3,
        60.1,
        57.7,
        59.1,
        1_500_000.0,
    ]
    return frame



def _detect(frame: pd.DataFrame, **kwargs):
    module = _load_detector_module()
    enriched = add_shared_preprocessing(frame)
    return module.detect_event_driven_family(enriched, symbol='TEST', trend_template_pass=True, **kwargs)



def test_detector_requires_event_evidence_for_event_driven_family() -> None:
    candidates = _detect(
        _gap_breakout_frame(),
        news_payload={
            'items': [
                {
                    'date': '2025-03-01',
                    'headline': 'Market wrap: indexes rise into close',
                    'source': 'Blog',
                }
            ]
        },
    )

    assert candidates == []



def test_detector_returns_follow_through_candidate_after_catalyst_holds() -> None:
    candidates = _detect(
        _follow_through_frame(),
        news_payload={
            'items': [
                {
                    'date': '2025-02-27',
                    'headline': 'Company secures major platform distribution agreement',
                    'source': 'Reuters',
                }
            ]
        },
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.pattern_family == 'event_driven_family'
    assert candidate.pattern_type == 'event-follow-through'
    assert candidate.pattern_variant == 'news'
    assert candidate.catalyst_type == 'news'
    assert candidate.catalyst_confidence is not None and candidate.catalyst_confidence >= 0.7
    assert candidate.catalyst_evidence_count is not None and candidate.catalyst_evidence_count >= 2
    assert candidate.catalyst_summary is not None and 'news catalyst' in candidate.catalyst_summary.lower()
    assert any(note.startswith('catalyst_summary=') for note in candidate.notes)
    assert any(note == 'price_pattern=follow-through' for note in candidate.notes)
