from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from scripts.vcp_lib import trend_template as vcp_trend_template
from scripts.vcp_lib.models import TrendTemplateResult

DEFAULT_REQUIRED_BARS_BY_FAMILY: dict[str, int] = {
    'trend_template': 200,
    'vcp_breakout_family': 200,
    'ibd_base_family': 200,
    'momentum_continuation_family': 120,
    'event_driven_family': 60,
}

NON_TARGET_TYPE_HINTS = {
    'etf',
    'fund',
    'mutual fund',
    'closed-end fund',
    'trust',
    'adr',
    'warrant',
    'unit',
    'right',
    'preferred',
    'preferred stock',
}

NON_TARGET_NAME_HINTS = (
    ' etf',
    ' fund',
    ' trust',
    ' adr',
    ' warrant',
    ' units',
    ' rights',
    ' preferred',
)


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


def _latest_value(frame: pd.DataFrame, column: str) -> Any:
    if frame.empty or column not in frame.columns:
        return None
    return frame.iloc[-1][column]


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _normalize_instrument_hint(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    return str(value).strip().lower()


def _detect_non_target_instrument(frame: pd.DataFrame) -> str | None:
    instrument_hints = [
        _normalize_instrument_hint(_latest_value(frame, 'InstrumentType')),
        _normalize_instrument_hint(_latest_value(frame, 'QuoteType')),
        _normalize_instrument_hint(_latest_value(frame, 'SecurityType')),
    ]
    for hint in instrument_hints:
        if hint in NON_TARGET_TYPE_HINTS:
            return f'non_target_instrument:{hint.replace(" ", "_")}'

    boolean_hints = {
        'IsETF': 'non_target_instrument:etf',
        'IsFund': 'non_target_instrument:fund',
        'IsADR': 'non_target_instrument:adr',
    }
    for column, reason in boolean_hints.items():
        value = _latest_value(frame, column)
        if value is not None and not pd.isna(value) and bool(value):
            return reason

    company_name = _normalize_instrument_hint(_latest_value(frame, 'CompanyName'))
    for hint in NON_TARGET_NAME_HINTS:
        if hint in company_name:
            return f'non_target_instrument:{hint.strip().replace(" ", "_")}'
    return None


def required_bars_for_detector_family(
    detector_family: str | None,
    *,
    required_bars_by_family: dict[str, int] | None = None,
    fallback_min_history: int = 200,
) -> int:
    if not detector_family:
        return fallback_min_history
    mapping = required_bars_by_family or DEFAULT_REQUIRED_BARS_BY_FAMILY
    return int(mapping.get(detector_family, fallback_min_history))


def adapt_trend_template_result(
    frame: pd.DataFrame,
    *,
    trend_template: TrendTemplateResult,
    min_rs_proxy: float = 0.0,
) -> TrendFilterResult:
    latest = frame.iloc[-1] if not frame.empty else pd.Series(dtype='float64')
    rs_score = _float_or_none(latest.get('RSProxy'))
    close_pct_from_high = _float_or_none(latest.get('ClosePctFrom52WHigh'))
    distance_to_52w_high = abs(close_pct_from_high) if close_pct_from_high is not None else None
    rs_pass = rs_score is not None and rs_score >= min_rs_proxy

    reasons: list[str] = []
    if not trend_template.passes:
        reasons.append('trend_template')
    if not rs_pass:
        reasons.append('rs_proxy_below_threshold')

    check_status = {key: ('pass' if passed else 'fail') for key, passed in trend_template.checks.items()}
    check_status['rs_proxy'] = 'pass' if rs_pass else 'fail'

    return TrendFilterResult(
        passes=trend_template.passes and rs_pass,
        trend_template_pass=trend_template.passes,
        rs_pass=rs_pass,
        reasons=reasons,
        failed_checks=list(trend_template.reasons),
        check_status=check_status,
        distance_to_52w_high=distance_to_52w_high,
        rs_score=rs_score,
        trend_template=trend_template,
    )


def evaluate_eligibility(
    frame: pd.DataFrame,
    *,
    detector_family: str | None = None,
    min_history: int = 200,
    min_price: float = 10.0,
    min_avg_dollar_volume: float = 10_000_000.0,
    required_bars_by_family: dict[str, int] | None = None,
) -> EligibilityFilterResult:
    if frame.empty:
        return EligibilityFilterResult(False, reasons=['empty_history'])

    latest = frame.iloc[-1]
    reasons: list[str] = []
    required_bars = required_bars_for_detector_family(
        detector_family,
        required_bars_by_family=required_bars_by_family,
        fallback_min_history=min_history,
    )
    avg_dollar_volume_value = latest.get('AvgDollarVolume20')
    if avg_dollar_volume_value is None or pd.isna(avg_dollar_volume_value):
        avg_dollar_volume_value = latest.get('DollarVolume20')
    metrics = {
        'history_length': len(frame),
        'detector_family': detector_family,
        'required_bars': required_bars,
        'close': _float_or_none(latest.get('Close')),
        'avg_dollar_volume_20': _float_or_none(avg_dollar_volume_value),
    }

    if len(frame) < min_history:
        reasons.append('insufficient_history')
    if len(frame) < required_bars:
        family_name = detector_family or 'detector'
        reasons.append(f'insufficient_bars_for_{family_name}')
    latest_close = metrics['close']
    if latest_close is None or latest_close < min_price:
        reasons.append('price_below_threshold')
    latest_avg_dollar_volume = metrics['avg_dollar_volume_20']
    if latest_avg_dollar_volume is None or latest_avg_dollar_volume < min_avg_dollar_volume:
        reasons.append('avg_dollar_volume_below_threshold')
    non_target_reason = _detect_non_target_instrument(frame)
    if non_target_reason is not None:
        reasons.append(non_target_reason)

    return EligibilityFilterResult(passes=not reasons, reasons=reasons, metrics=metrics)


def evaluate_trend_filters(frame: pd.DataFrame, *, min_rs_proxy: float = 0.0) -> TrendFilterResult:
    trend_template = vcp_trend_template.evaluate_trend_template(frame)
    return adapt_trend_template_result(frame, trend_template=trend_template, min_rs_proxy=min_rs_proxy)
