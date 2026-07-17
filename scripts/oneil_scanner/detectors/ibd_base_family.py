from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.oneil_scanner.models import PatternCandidate, SymbolContext

FAMILY_NAME = 'ibd_base_family'
_PATTERN_PRIORITY = {
    'cup-with-handle': 3,
    'double-bottom': 2,
    'flat-base': 1,
}


@dataclass
class _BasePatternHit:
    pattern_type: str
    pattern_variant: str
    pivot_price: float
    stop_reference: float
    base_depth_pct: float
    breakout_volume_ratio: float | None
    distance_to_pivot_pct: float
    quality_score: float
    setup_score: float
    notes: list[str]


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).strftime('%Y-%m-%d')


def _breakout_volume_ratio(frame: pd.DataFrame) -> float | None:
    latest = frame.iloc[-1]
    volume_ratio = _float_or_none(latest.get('BreakoutVolumeRatio'))
    if volume_ratio is not None:
        return volume_ratio
    avg_volume = _float_or_none(latest.get('AvgVolume20'))
    if avg_volume in (None, 0.0):
        avg_volume = _float_or_none(frame['Volume'].tail(20).mean())
    latest_volume = _float_or_none(latest.get('Volume'))
    if avg_volume in (None, 0.0) or latest_volume is None:
        return None
    return latest_volume / avg_volume


def _volume_confirmation_label(volume_ratio: float | None) -> str:
    if volume_ratio is not None and volume_ratio >= 1.1:
        return 'confirmed'
    if volume_ratio is not None and volume_ratio >= 1.0:
        return 'watch'
    return 'dry-up'


def _has_prior_uptrend(
    frame: pd.DataFrame,
    *,
    base_start: int,
    anchor_price: float,
    lookback: int = 60,
    min_gain_pct: float = 0.25,
) -> bool:
    if base_start < lookback or anchor_price <= 0:
        return False
    reference_price = _float_or_none(frame.iloc[base_start - lookback]['Close'])
    if reference_price in (None, 0.0):
        return False
    return anchor_price / reference_price - 1.0 >= min_gain_pct


def _latest_breakout_checks(frame: pd.DataFrame, *, pivot_price: float, max_extension_pct: float = 0.05) -> tuple[bool, float, float | None]:
    latest_close = float(frame.iloc[-1]['Close'])
    distance_to_pivot_pct = latest_close / pivot_price - 1.0
    volume_ratio = _breakout_volume_ratio(frame)
    confirmed = latest_close > pivot_price and distance_to_pivot_pct <= max_extension_pct and (volume_ratio or 0.0) >= 1.1
    return confirmed, distance_to_pivot_pct, volume_ratio


def _build_candidate(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None,
    hit: _BasePatternHit,
) -> PatternCandidate:
    latest = frame.iloc[-1]
    return PatternCandidate(
        symbol=symbol,
        pattern_family=FAMILY_NAME,
        pattern_type=hit.pattern_type,
        pattern_variant=hit.pattern_variant,
        trigger_date=_format_date(latest.get('Date')),
        breakout_level=round(hit.pivot_price, 4),
        entry_zone_low=round(hit.pivot_price, 4),
        entry_zone_high=round(hit.pivot_price * 1.05, 4),
        stop_reference=round(hit.stop_reference, 4),
        trend_template_pass=trend_template_pass,
        rs_score=_float_or_none(latest.get('RSProxy')),
        distance_to_52w_high=abs(_float_or_none(latest.get('ClosePctFrom52WHigh')) or 0.0),
        volume_confirmation=_volume_confirmation_label(hit.breakout_volume_ratio),
        catalyst_type='technical_breakout',
        catalyst_confidence=0.9,
        quality_score=round(min(hit.quality_score, 99.0), 2),
        setup_score=round(min(hit.setup_score, 99.0), 2),
        report_rank=None,
        secondary_signals=[],
        notes=hit.notes,
        symbol_context=symbol_context,
    )


def _detect_cup_with_handle(frame: pd.DataFrame) -> _BasePatternHit | None:
    pre_breakout = frame.iloc[:-1]
    if len(pre_breakout) < 45:
        return None

    best_hit: _BasePatternHit | None = None
    max_width = min(75, len(pre_breakout))
    for width in range(35, max_width + 1):
        base_start = len(pre_breakout) - width
        window = pre_breakout.iloc[-width:].reset_index(drop=True)
        for handle_len in range(5, min(15, width // 2) + 1):
            cup_window = window.iloc[:-handle_len]
            handle_window = window.iloc[-handle_len:]
            if len(cup_window) < 25:
                continue

            trough_pos = int(cup_window['Low'].idxmin())
            if trough_pos < int(len(cup_window) * 0.2) or trough_pos > int(len(cup_window) * 0.7):
                continue
            if trough_pos < 5 or trough_pos >= len(cup_window) - 5:
                continue

            left_rim = float(cup_window.iloc[:trough_pos]['Close'].max())
            right_rim = float(cup_window.iloc[trough_pos + 1 :]['Close'].max())
            trough_low = float(cup_window.iloc[trough_pos]['Low'])
            cup_peak = max(left_rim, right_rim)
            base_depth_pct = 1.0 - trough_low / cup_peak
            if not 0.12 <= base_depth_pct <= 0.35:
                continue

            prior_uptrend = _has_prior_uptrend(frame, base_start=base_start, anchor_price=left_rim, min_gain_pct=0.25)
            if not prior_uptrend:
                continue
            if right_rim < left_rim * 0.93:
                continue
            secondary_lows = cup_window.iloc[trough_pos + 5 :]['Low']
            if not secondary_lows.empty and float(secondary_lows.min()) <= trough_low * 1.05:
                continue

            pivot_price = float(handle_window['Close'].max())
            handle_low = float(handle_window['Low'].min())
            handle_depth_pct = 1.0 - handle_low / pivot_price
            cup_midpoint = trough_low + (cup_peak - trough_low) / 2.0
            if handle_low < cup_midpoint or handle_depth_pct > 0.15:
                continue
            if float(handle_window.iloc[0]['Close']) < trough_low + (cup_peak - trough_low) * 0.55:
                continue

            confirmed, distance_to_pivot_pct, volume_ratio = _latest_breakout_checks(frame, pivot_price=pivot_price)
            if not confirmed:
                continue

            quality_score = 88.0 + min(6.0, (volume_ratio or 1.1) - 1.0) * 10.0
            setup_score = quality_score - abs(distance_to_pivot_pct) * 100.0
            hit = _BasePatternHit(
                pattern_type='cup-with-handle',
                pattern_variant='textbook',
                pivot_price=pivot_price,
                stop_reference=handle_low,
                base_depth_pct=base_depth_pct,
                breakout_volume_ratio=volume_ratio,
                distance_to_pivot_pct=distance_to_pivot_pct,
                quality_score=quality_score,
                setup_score=setup_score,
                notes=[
                    f'pivot={pivot_price:.4f}',
                    f'base_depth_pct={base_depth_pct:.4f}',
                    f'breakout_volume_ratio={(volume_ratio or 0.0):.4f}',
                    'prior_uptrend=True',
                    f'left_rim={left_rim:.4f}',
                    f'right_rim={right_rim:.4f}',
                    f'handle_depth_pct={handle_depth_pct:.4f}',
                ],
            )
            if best_hit is None or hit.setup_score > best_hit.setup_score:
                best_hit = hit
    return best_hit


def _detect_flat_base(frame: pd.DataFrame) -> _BasePatternHit | None:
    pre_breakout = frame.iloc[:-1]
    if len(pre_breakout) < 30:
        return None

    best_hit: _BasePatternHit | None = None
    max_width = min(40, len(pre_breakout))
    for width in range(25, max_width + 1):
        base_start = len(pre_breakout) - width
        window = pre_breakout.iloc[-width:]
        high_resistance = float(window['Close'].max())
        low_support = float(window['Low'].min())
        base_depth_pct = 1.0 - low_support / high_resistance
        if not 0.04 <= base_depth_pct <= 0.15:
            continue

        prior_uptrend = _has_prior_uptrend(frame, base_start=base_start, anchor_price=high_resistance, min_gain_pct=0.2)
        if not prior_uptrend:
            continue

        tightness_ratio = float(window['Close'].std(ddof=0) / window['Close'].mean())
        if tightness_ratio > 0.03:
            continue

        pivot_price = high_resistance * 1.001
        confirmed, distance_to_pivot_pct, volume_ratio = _latest_breakout_checks(
            frame,
            pivot_price=pivot_price,
            max_extension_pct=0.05,
        )
        if not confirmed:
            continue

        extension_pct = float(frame.iloc[-1]['Close']) / pivot_price - 1.0
        quality_score = 86.0 + (0.03 - tightness_ratio) * 100.0
        setup_score = quality_score - extension_pct * 100.0
        hit = _BasePatternHit(
            pattern_type='flat-base',
            pattern_variant='tight',
            pivot_price=pivot_price,
            stop_reference=low_support,
            base_depth_pct=base_depth_pct,
            breakout_volume_ratio=volume_ratio,
            distance_to_pivot_pct=distance_to_pivot_pct,
            quality_score=quality_score,
            setup_score=setup_score,
            notes=[
                f'pivot={pivot_price:.4f}',
                f'base_depth_pct={base_depth_pct:.4f}',
                f'breakout_volume_ratio={(volume_ratio or 0.0):.4f}',
                f'tightness_ratio={tightness_ratio:.4f}',
                f'extension_pct={extension_pct:.4f}',
                f'base_resistance={high_resistance:.4f}',
            ],
        )
        if best_hit is None or hit.setup_score > best_hit.setup_score:
            best_hit = hit
    return best_hit


def _detect_double_bottom(frame: pd.DataFrame) -> _BasePatternHit | None:
    pre_breakout = frame.iloc[:-1]
    if len(pre_breakout) < 40:
        return None

    best_hit: _BasePatternHit | None = None
    max_width = min(70, len(pre_breakout))
    for width in range(35, max_width + 1):
        base_start = len(pre_breakout) - width
        window = pre_breakout.iloc[-width:].reset_index(drop=True)
        first_half_end = int(width * 0.45)
        second_half_start = int(width * 0.45)
        if first_half_end < 8 or second_half_start >= width - 5:
            continue

        first_low_pos = int(window.iloc[:first_half_end]['Low'].idxmin())
        second_low_pos = int(window.iloc[second_half_start:]['Low'].idxmin())
        if second_low_pos <= first_low_pos + 5 or second_low_pos >= width - 4:
            continue

        first_low = float(window.iloc[first_low_pos]['Low'])
        second_low = float(window.iloc[second_low_pos]['Low'])
        middle_slice = window.iloc[first_low_pos + 3 : second_low_pos - 2]
        if middle_slice.empty:
            continue

        midpoint_peak = float(middle_slice['High'].max())
        base_depth_pct = 1.0 - min(first_low, second_low) / midpoint_peak
        if not 0.10 <= base_depth_pct <= 0.35:
            continue

        prior_uptrend = _has_prior_uptrend(frame, base_start=base_start, anchor_price=midpoint_peak, min_gain_pct=0.2)
        if not prior_uptrend:
            continue

        second_low_vs_first_pct = second_low / first_low - 1.0
        if second_low_vs_first_pct < -0.08 or second_low_vs_first_pct > 0.03:
            continue
        if midpoint_peak < max(first_low, second_low) * 1.12:
            continue

        confirmed, distance_to_pivot_pct, volume_ratio = _latest_breakout_checks(frame, pivot_price=midpoint_peak)
        if not confirmed:
            continue

        quality_score = 87.0 + min(6.0, (volume_ratio or 1.1) - 1.0) * 10.0
        setup_score = quality_score - abs(distance_to_pivot_pct) * 100.0
        hit = _BasePatternHit(
            pattern_type='double-bottom',
            pattern_variant='w-bottom',
            pivot_price=midpoint_peak,
            stop_reference=second_low,
            base_depth_pct=base_depth_pct,
            breakout_volume_ratio=volume_ratio,
            distance_to_pivot_pct=distance_to_pivot_pct,
            quality_score=quality_score,
            setup_score=setup_score,
            notes=[
                f'pivot={midpoint_peak:.4f}',
                f'base_depth_pct={base_depth_pct:.4f}',
                f'breakout_volume_ratio={(volume_ratio or 0.0):.4f}',
                f'midpoint_peak={midpoint_peak:.4f}',
                f'first_low={first_low:.4f}',
                f'second_low={second_low:.4f}',
                f'second_low_vs_first_pct={second_low_vs_first_pct:.4f}',
            ],
        )
        if best_hit is None or hit.setup_score > best_hit.setup_score:
            best_hit = hit
    return best_hit


def detect_ibd_base_family(
    frame: pd.DataFrame,
    *,
    symbol: str,
    trend_template_pass: bool,
    symbol_context: SymbolContext | None = None,
) -> list[PatternCandidate]:
    raw_hits = [
        _detect_cup_with_handle(frame),
        _detect_flat_base(frame),
        _detect_double_bottom(frame),
    ]
    hits = [hit for hit in raw_hits if hit is not None]
    if not hits:
        return []

    best_hit = sorted(
        hits,
        key=lambda item: (_PATTERN_PRIORITY.get(item.pattern_type, 0), item.setup_score, item.quality_score),
        reverse=True,
    )[0]
    return [_build_candidate(frame, symbol=symbol, trend_template_pass=trend_template_pass, symbol_context=symbol_context, hit=best_hit)]
