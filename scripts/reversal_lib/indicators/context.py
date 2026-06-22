from __future__ import annotations

from dataclasses import dataclass

from reversal_lib.domain.models import IndicatorContext
from reversal_lib.models import Candle
from reversal_lib.patterns import detect_support_resistance_levels_from_window
from reversal_lib.strategy_filters import (
    macd_context_series,
    rolling_mean_series,
    rolling_sma_series,
    rsi_series,
    sma_cross_context_series,
    trend_context_series,
)


@dataclass(frozen=True)
class ComputedIndicatorContext:
    indicator_context: IndicatorContext
    avg_volume_20: float | None
    avg_dollar_volume_20: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    confirm_volume_ratio: float | None
    confirm_volume_ok: bool


@dataclass(frozen=True)
class IndicatorContextInputs:
    avg_vol20_series: list[float | None]
    avg_dollar_volume_20_series: list[float | None]
    trend_series: list[str | None]
    sma_cross_series: list[str]
    macd_series: list[str]
    rsi_values: list[float | None]
    sma200_series: list[float | None]


def prepare_indicator_context_inputs(candles: list[Candle]) -> IndicatorContextInputs:
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    dollar_volumes = [c.close * c.volume for c in candles]
    return IndicatorContextInputs(
        avg_vol20_series=rolling_mean_series(volumes, 20),
        avg_dollar_volume_20_series=rolling_mean_series(dollar_volumes, 20),
        trend_series=trend_context_series(closes),
        sma_cross_series=sma_cross_context_series(closes),
        macd_series=macd_context_series(closes),
        rsi_values=rsi_series(closes),
        sma200_series=rolling_sma_series(closes, 200),
    )


def _is_near_level(price: float, level: float | None, tolerance_ratio: float = 0.02) -> bool:
    if level is None or price <= 0:
        return False
    return abs(price - level) / price <= tolerance_ratio


def _location_context(
    confirm_close: float,
    nearest_support: float | None,
    nearest_resistance: float | None,
    tolerance_ratio: float = 0.02,
) -> str:
    near_support = _is_near_level(confirm_close, nearest_support, tolerance_ratio)
    near_resistance = _is_near_level(confirm_close, nearest_resistance, tolerance_ratio)
    if near_support and not near_resistance:
        return 'near_support'
    if near_resistance and not near_support:
        return 'near_resistance'
    if near_support and near_resistance:
        return 'near_both'
    return 'neutral'


def build_indicator_context(
    candles: list[Candle],
    candidate_index: int,
    confirm_close: float,
    location_tolerance_ratio: float = 0.02,
    confirm_volume: float | None = None,
    confirm_volume_multiplier: float = 1.0,
    inputs: IndicatorContextInputs | None = None,
) -> ComputedIndicatorContext:
    prepared = inputs or prepare_indicator_context_inputs(candles)

    confirm_index = candidate_index + 1
    sr_window = candles[max(0, confirm_index + 1 - 50):confirm_index + 1]
    supports, resistances = detect_support_resistance_levels_from_window(sr_window)
    nearest_support = max(supports) if supports else None
    nearest_resistance = min(resistances) if resistances else None
    avg_volume_20 = prepared.avg_vol20_series[candidate_index]
    actual_confirm_volume = confirm_volume if confirm_volume is not None else candles[confirm_index].volume
    volume_ratio = (actual_confirm_volume / avg_volume_20) if avg_volume_20 else None
    sma200 = prepared.sma200_series[confirm_index]

    return ComputedIndicatorContext(
        indicator_context=IndicatorContext(
            trend_context=prepared.trend_series[candidate_index],
            location_context=_location_context(confirm_close, nearest_support, nearest_resistance, location_tolerance_ratio),
            sma_cross_context=prepared.sma_cross_series[confirm_index],
            rsi_value=round(prepared.rsi_values[confirm_index], 4) if prepared.rsi_values[confirm_index] is not None else None,
            above_sma200=sma200 is not None and confirm_close > sma200,
            macd_context=prepared.macd_series[confirm_index],
        ),
        avg_volume_20=avg_volume_20,
        avg_dollar_volume_20=prepared.avg_dollar_volume_20_series[candidate_index],
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        confirm_volume_ratio=round(volume_ratio, 4) if volume_ratio is not None else None,
        confirm_volume_ok=bool(avg_volume_20) and actual_confirm_volume >= avg_volume_20 * confirm_volume_multiplier,
    )
