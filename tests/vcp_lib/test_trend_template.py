from __future__ import annotations

import pandas as pd

from scripts.vcp_lib.indicators import add_core_indicators
from scripts.vcp_lib.trend_template import evaluate_trend_template


def test_trend_template_pass_case() -> None:
    closes = pd.Series([float(i) for i in range(1, 260)])
    frame = pd.DataFrame({
        'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
        'Open': closes,
        'High': closes * 1.01,
        'Low': closes * 0.99,
        'Close': closes,
        'Volume': [1_000_000] * len(closes),
    })
    enriched = add_core_indicators(frame)
    result = evaluate_trend_template(enriched)
    assert result.passes is True


def test_trend_template_reports_failed_checks() -> None:
    closes = pd.Series([300.0 - 0.8 * i for i in range(260)])
    frame = pd.DataFrame({
        'Date': pd.date_range('2025-01-01', periods=len(closes), freq='D'),
        'Open': closes,
        'High': closes * 1.01,
        'Low': closes * 0.99,
        'Close': closes,
        'Volume': [1_000_000] * len(closes),
    })

    enriched = add_core_indicators(frame)
    result = evaluate_trend_template(enriched)

    assert result.passes is False
    assert 'price_above_sma150' in result.reasons
    assert 'close_to_52w_high' in result.reasons
