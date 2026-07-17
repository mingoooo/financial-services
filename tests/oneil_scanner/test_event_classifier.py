from __future__ import annotations

import importlib

import pandas as pd

from scripts.oneil_scanner.preprocess import add_shared_preprocessing


def _load_classifier_module():
    try:
        return importlib.import_module('scripts.oneil_scanner.event_classifier')
    except ModuleNotFoundError as exc:
        raise AssertionError('Task 7 event classifier module is missing') from exc



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



def _classify(frame: pd.DataFrame, **kwargs):
    module = _load_classifier_module()
    enriched = add_shared_preprocessing(frame)
    return module.classify_event_catalyst(enriched, **kwargs)



def test_classifier_detects_confirmed_earnings_gap_up() -> None:
    evidence = _classify(
        _gap_breakout_frame(),
        earnings_payload={
            'events': [
                {
                    'date': '2025-03-01',
                    'confirmed': True,
                    'eps_surprise_pct': 0.24,
                    'revenue_surprise_pct': 0.09,
                    'headline': 'Company beats and raises guidance',
                }
            ]
        },
    )

    assert evidence.catalyst_type == 'earnings'
    assert evidence.event_detected is True
    assert evidence.price_pattern_triggered is True
    assert evidence.catalyst_confidence >= 0.8
    assert evidence.catalyst_evidence_count >= 3
    assert 'earnings' in evidence.catalyst_summary.lower()



def test_classifier_detects_confirmed_news_gap_breakout() -> None:
    evidence = _classify(
        _gap_breakout_frame(),
        news_payload={
            'items': [
                {
                    'date': '2025-03-01',
                    'headline': 'Company wins multi-year hyperscaler partnership deal',
                    'source': 'Reuters',
                }
            ]
        },
    )

    assert evidence.catalyst_type == 'news'
    assert evidence.event_detected is True
    assert evidence.price_pattern_triggered is True
    assert evidence.catalyst_confidence >= 0.7
    assert evidence.catalyst_evidence_count >= 2
    assert 'news' in evidence.catalyst_summary.lower()



def test_classifier_reports_mixed_evidence_when_both_catalysts_exist() -> None:
    evidence = _classify(
        _gap_breakout_frame(),
        earnings_payload={
            'events': [
                {
                    'date': '2025-03-01',
                    'confirmed': True,
                    'eps_surprise_pct': 0.11,
                    'headline': 'Company posts earnings beat',
                }
            ]
        },
        news_payload={
            'items': [
                {
                    'date': '2025-03-01',
                    'headline': 'Company announces major enterprise expansion contract',
                    'source': 'Bloomberg',
                }
            ]
        },
    )

    assert evidence.catalyst_type == 'mixed'
    assert evidence.event_detected is True
    assert evidence.price_pattern_triggered is True
    assert 0.6 <= evidence.catalyst_confidence <= 0.95
    assert evidence.catalyst_evidence_count >= 4
    assert 'mixed' in evidence.catalyst_summary.lower()



def test_classifier_does_not_confirm_gap_without_usable_catalyst_evidence() -> None:
    evidence = _classify(
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

    assert evidence.catalyst_type == 'none'
    assert evidence.event_detected is False
    assert evidence.price_pattern_triggered is True
    assert evidence.catalyst_confidence == 0.0
    assert evidence.catalyst_evidence_count == 0
    assert 'no usable catalyst' in evidence.catalyst_summary.lower()
