from __future__ import annotations

import pandas as pd

from .indicators import sma200_rising
from .models import TrendTemplateResult


def build_trend_template_checks(frame: pd.DataFrame) -> dict[str, bool]:
    latest = frame.iloc[-1]
    return {
        'price_above_sma150': bool(latest['Close'] > latest['SMA150']),
        'price_above_sma200': bool(latest['Close'] > latest['SMA200']),
        'sma150_above_sma200': bool(latest['SMA150'] > latest['SMA200']),
        'sma200_rising': sma200_rising(frame),
        'price_above_sma50': bool(latest['Close'] > latest['SMA50']),
        'close_to_52w_high': bool(latest['ClosePctFrom52WHigh'] >= -0.15),
    }


def evaluate_trend_template(frame: pd.DataFrame) -> TrendTemplateResult:
    if len(frame) < 200:
        return TrendTemplateResult(False, reasons=['Not enough history for trend template'])
    latest = frame.iloc[-1]
    checks = build_trend_template_checks(frame)
    reasons: list[str] = []
    borderline: list[str] = []
    for key, passed in checks.items():
        if not passed:
            reasons.append(key)
    if checks['close_to_52w_high'] and latest['ClosePctFrom52WHigh'] < -0.05:
        borderline.append('Price is near highs but not especially tight to 52-week high')
    passes = sum(int(value) for value in checks.values()) >= 5 and checks['sma150_above_sma200']
    return TrendTemplateResult(passes=passes, checks=checks, reasons=reasons, borderline_notes=borderline)
