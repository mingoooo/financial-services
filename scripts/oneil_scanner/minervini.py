from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.oneil_scanner.filters import TrendFilterResult, adapt_trend_template_result
from scripts.vcp_lib.models import TrendTemplateResult

ONEIL_PROFILE = 'oneil'
MINERVINI_RELAXED_PROFILE = 'minervini_relaxed'
MINERVINI_STRICT_PROFILE = 'minervini_strict'
DEFAULT_ALLOWED_FAMILIES: set[str] = {'vcp_breakout_family', 'ibd_base_family'}


@dataclass(frozen=True)
class MinerviniProfileSettings:
    name: str
    rs_threshold: float
    max_distance_to_high: float = 0.25
    min_above_52w_low: float = 0.30
    sma200_lookback_days: int = 30


PROFILE_SETTINGS: dict[str, MinerviniProfileSettings] = {
    MINERVINI_RELAXED_PROFILE: MinerviniProfileSettings(name=MINERVINI_RELAXED_PROFILE, rs_threshold=0.05),
    MINERVINI_STRICT_PROFILE: MinerviniProfileSettings(name=MINERVINI_STRICT_PROFILE, rs_threshold=0.10),
}

MINERVINI_RELAXED_PROFILE_SETTINGS = PROFILE_SETTINGS[MINERVINI_RELAXED_PROFILE]
MINERVINI_STRICT_PROFILE_SETTINGS = PROFILE_SETTINGS[MINERVINI_STRICT_PROFILE]


def is_minervini_profile(strategy_profile: str) -> bool:
    return strategy_profile in PROFILE_SETTINGS


def get_profile_settings(strategy_profile: str) -> MinerviniProfileSettings:
    return PROFILE_SETTINGS[strategy_profile]


def allowed_detector_families(strategy_profile: str) -> set[str] | None:
    if is_minervini_profile(strategy_profile):
        return set(DEFAULT_ALLOWED_FAMILIES)
    return None


def _bool_value(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(value)


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _evaluate_minervini_trend_template(frame: pd.DataFrame, *, settings: MinerviniProfileSettings) -> TrendTemplateResult:
    if len(frame) < 200:
        return TrendTemplateResult(False, reasons=['Not enough history for Minervini trend template'])

    latest = frame.iloc[-1]
    sma200_series = frame['SMA200'].dropna() if 'SMA200' in frame.columns else pd.Series(dtype='float64')
    sma200_lookback_value = None
    if len(sma200_series) > settings.sma200_lookback_days:
        sma200_lookback_value = _float_or_none(sma200_series.iloc[-(settings.sma200_lookback_days + 1)])

    close_pct_from_low = _float_or_none(latest.get('ClosePctFrom52WLow'))
    close_pct_from_high = _float_or_none(latest.get('ClosePctFrom52WHigh'))

    checks = {
        'close_above_sma50': _float_or_none(latest.get('Close')) is not None and _float_or_none(latest.get('SMA50')) is not None and bool(latest['Close'] > latest['SMA50']),
        'close_above_sma150': _float_or_none(latest.get('Close')) is not None and _float_or_none(latest.get('SMA150')) is not None and bool(latest['Close'] > latest['SMA150']),
        'close_above_sma200': _float_or_none(latest.get('Close')) is not None and _float_or_none(latest.get('SMA200')) is not None and bool(latest['Close'] > latest['SMA200']),
        'sma50_above_sma150': _float_or_none(latest.get('SMA50')) is not None and _float_or_none(latest.get('SMA150')) is not None and bool(latest['SMA50'] > latest['SMA150']),
        'sma150_above_sma200': _float_or_none(latest.get('SMA150')) is not None and _float_or_none(latest.get('SMA200')) is not None and bool(latest['SMA150'] > latest['SMA200']),
        'sma200_rising_30d': sma200_lookback_value is not None and _float_or_none(latest.get('SMA200')) is not None and bool(latest['SMA200'] > sma200_lookback_value),
        'close_above_52w_low_by_30pct': close_pct_from_low is not None and close_pct_from_low >= settings.min_above_52w_low,
        'close_within_25pct_of_52w_high': close_pct_from_high is not None and close_pct_from_high >= -settings.max_distance_to_high,
    }
    reasons = [key for key, passed in checks.items() if not passed]
    borderline_notes: list[str] = []
    if close_pct_from_high is not None and close_pct_from_high < -0.10 and checks['close_within_25pct_of_52w_high']:
        borderline_notes.append('Price remains in range but is not especially tight to the 52-week high')

    return TrendTemplateResult(
        passes=all(checks.values()),
        checks=checks,
        reasons=reasons,
        borderline_notes=borderline_notes,
    )


def evaluate_minervini_trend_filters(frame: pd.DataFrame, *, strategy_profile: str) -> TrendFilterResult:
    settings = get_profile_settings(strategy_profile)
    trend_template = _evaluate_minervini_trend_template(frame, settings=settings)
    return adapt_trend_template_result(frame, trend_template=trend_template, min_rs_proxy=settings.rs_threshold)


__all__ = [
    'DEFAULT_ALLOWED_FAMILIES',
    'MINERVINI_RELAXED_PROFILE',
    'MINERVINI_RELAXED_PROFILE_SETTINGS',
    'MINERVINI_STRICT_PROFILE',
    'MINERVINI_STRICT_PROFILE_SETTINGS',
    'ONEIL_PROFILE',
    'PROFILE_SETTINGS',
    'MinerviniProfileSettings',
    'allowed_detector_families',
    'evaluate_minervini_trend_filters',
    'get_profile_settings',
    'is_minervini_profile',
]
