from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from scripts.vcp_lib.models import TrendTemplateResult
from scripts.vcp_lib.trend_template import evaluate_trend_template


@dataclass
class EligibilityFilterResult:
    passes: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrendFilterResult:
    passes: bool
    trend_template_pass: bool
    rs_pass: bool
    reasons: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    check_status: dict[str, str] = field(default_factory=dict)
    distance_to_52w_high: float | None = None
    rs_score: float | None = None
    trend_template: TrendTemplateResult | None = None



def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)



def evaluate_eligibility(
    frame: pd.DataFrame,
    *,
    min_history: int = 200,
    min_price: float = 10.0,
    min_avg_dollar_volume: float = 10_000_000.0,
) -> EligibilityFilterResult:
    if frame.empty:
        return EligibilityFilterResult(False, reasons=['empty_history'])

    latest = frame.iloc[-1]
    reasons: list[str] = []
    avg_dollar_volume_value = latest.get('AvgDollarVolume20')
    if avg_dollar_volume_value is None or pd.isna(avg_dollar_volume_value):
        avg_dollar_volume_value = latest.get('DollarVolume20')
    metrics = {
        'history_length': len(frame),
        'close': _float_or_none(latest.get('Close')),
        'avg_dollar_volume_20': _float_or_none(avg_dollar_volume_value),
    }

    if len(frame) < min_history:
        reasons.append('insufficient_history')
    latest_close = metrics['close']
    if latest_close is None or latest_close < min_price:
        reasons.append('price_below_threshold')
    latest_avg_dollar_volume = metrics['avg_dollar_volume_20']
    if latest_avg_dollar_volume is None or latest_avg_dollar_volume < min_avg_dollar_volume:
        reasons.append('avg_dollar_volume_below_threshold')

    return EligibilityFilterResult(passes=not reasons, reasons=reasons, metrics=metrics)



def evaluate_trend_filters(frame: pd.DataFrame, *, min_rs_proxy: float = 0.0) -> TrendFilterResult:
    trend_template = evaluate_trend_template(frame)
    latest = frame.iloc[-1] if not frame.empty else pd.Series(dtype='float64')
    rs_score = _float_or_none(latest.get('RSProxy'))
    distance_to_52w_high = None
    close_pct_from_high = _float_or_none(latest.get('ClosePctFrom52WHigh'))
    if close_pct_from_high is not None:
        distance_to_52w_high = abs(close_pct_from_high)

    rs_pass = rs_score is not None and rs_score >= min_rs_proxy
    reasons = list(trend_template.reasons)
    gate_reasons: list[str] = []
    if not trend_template.passes:
        gate_reasons.append('trend_template')
    if not rs_pass:
        gate_reasons.append('rs_proxy_below_threshold')

    check_status = {key: ('pass' if passed else 'fail') for key, passed in trend_template.checks.items()}
    check_status['rs_proxy'] = 'pass' if rs_pass else 'fail'

    return TrendFilterResult(
        passes=trend_template.passes and rs_pass,
        trend_template_pass=trend_template.passes,
        rs_pass=rs_pass,
        reasons=gate_reasons,
        failed_checks=reasons,
        check_status=check_status,
        distance_to_52w_high=distance_to_52w_high,
        rs_score=rs_score,
        trend_template=trend_template,
    )
