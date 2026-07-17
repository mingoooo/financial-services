from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .models import BreakoutSignal, VcpDetectionResult


@dataclass
class SwingPoint:
    index: int
    kind: str
    price: float
    date: str | None = None


@dataclass
class SwingLeg:
    start: SwingPoint
    end: SwingPoint
    direction: str
    move_pct: float
    duration: int
    avg_volume: float


def _compute_atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = frame['Close'].shift(1)
    tr = pd.concat(
        [
            frame['High'] - frame['Low'],
            (frame['High'] - prev_close).abs(),
            (frame['Low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window, min_periods=window).mean()


def segment_swings(
    frame: pd.DataFrame,
    min_bars_between_swings: int = 5,
    pct_reversal: float = 0.06,
    atr_multiplier: float = 1.5,
) -> list[SwingPoint]:
    if len(frame) < 30:
        return []

    atr = _compute_atr(frame).bfill().fillna(0)
    closes = frame['Close'].reset_index(drop=True)
    dates = pd.to_datetime(frame['Date']).dt.strftime('%Y-%m-%d').tolist() if 'Date' in frame.columns else [None] * len(frame)

    pivots: list[SwingPoint] = [SwingPoint(0, 'low', float(closes.iloc[0]), dates[0])]
    trend: str | None = None
    last_pivot_idx = 0
    candidate_idx = 0
    candidate_price = float(closes.iloc[0])

    for idx in range(1, len(closes)):
        price = float(closes.iloc[idx])
        atr_ratio = float(atr.iloc[idx] / price) if price > 0 else 0.0
        reversal_threshold = max(pct_reversal, atr_multiplier * atr_ratio)

        if trend is None:
            if price >= candidate_price * (1 + reversal_threshold):
                trend = 'up'
                pivots[0] = SwingPoint(last_pivot_idx, 'low', float(closes.iloc[last_pivot_idx]), dates[last_pivot_idx])
                candidate_idx = idx
                candidate_price = price
            elif price <= candidate_price * (1 - reversal_threshold):
                trend = 'down'
                pivots[0] = SwingPoint(last_pivot_idx, 'high', float(closes.iloc[last_pivot_idx]), dates[last_pivot_idx])
                candidate_idx = idx
                candidate_price = price
            elif price < candidate_price:
                candidate_idx = idx
                candidate_price = price
            continue

        if trend == 'up':
            if price >= candidate_price:
                candidate_idx = idx
                candidate_price = price
            elif (candidate_price - price) / candidate_price >= reversal_threshold and (candidate_idx - pivots[-1].index) >= min_bars_between_swings:
                pivots.append(SwingPoint(candidate_idx, 'high', candidate_price, dates[candidate_idx]))
                trend = 'down'
                last_pivot_idx = candidate_idx
                candidate_idx = idx
                candidate_price = price
        else:
            if price <= candidate_price:
                candidate_idx = idx
                candidate_price = price
            elif (price - candidate_price) / max(candidate_price, 1e-9) >= reversal_threshold and (candidate_idx - pivots[-1].index) >= min_bars_between_swings:
                pivots.append(SwingPoint(candidate_idx, 'low', candidate_price, dates[candidate_idx]))
                trend = 'up'
                last_pivot_idx = candidate_idx
                candidate_idx = idx
                candidate_price = price

    if trend == 'up' and candidate_idx != pivots[-1].index:
        pivots.append(SwingPoint(candidate_idx, 'high', candidate_price, dates[candidate_idx]))
    elif trend == 'down' and candidate_idx != pivots[-1].index:
        pivots.append(SwingPoint(candidate_idx, 'low', candidate_price, dates[candidate_idx]))

    deduped: list[SwingPoint] = []
    for pivot in pivots:
        if deduped and pivot.kind == deduped[-1].kind:
            if (pivot.kind == 'high' and pivot.price >= deduped[-1].price) or (pivot.kind == 'low' and pivot.price <= deduped[-1].price):
                deduped[-1] = pivot
            continue
        deduped.append(pivot)
    return deduped


def build_swing_legs(frame: pd.DataFrame, swings: list[SwingPoint]) -> list[SwingLeg]:
    legs: list[SwingLeg] = []
    for start, end in zip(swings, swings[1:]):
        direction = 'up' if end.price >= start.price else 'down'
        move_pct = end.price / max(start.price, 1e-9) - 1.0
        window = frame.iloc[start.index : end.index + 1]
        avg_volume = float(window['Volume'].mean()) if not window.empty else 0.0
        legs.append(
            SwingLeg(
                start=start,
                end=end,
                direction=direction,
                move_pct=move_pct,
                duration=max(1, end.index - start.index),
                avg_volume=avg_volume,
            )
        )
    return legs


def evaluate_prior_uptrend(frame: pd.DataFrame, swings: list[SwingPoint]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if len(swings) < 4:
        return False, ['not-enough-swings']
    highs = [s for s in swings if s.kind == 'high']
    lows = [s for s in swings if s.kind == 'low']
    if len(highs) < 2 or len(lows) < 2:
        return False, ['missing-swing-structure']

    latest_high = highs[-1]
    prior_lows = [low for low in lows if low.index < latest_high.index]
    if not prior_lows:
        return False, ['no-base-left-boundary']
    anchor_low = prior_lows[-1]
    lookback_swings = [s for s in swings if s.index <= anchor_low.index]
    if len(lookback_swings) < 2:
        return False, ['no-pre-base-structure']

    pre_base_low = min((s for s in lookback_swings if s.kind == 'low'), key=lambda s: s.price, default=None)
    if pre_base_low is None:
        return False, ['no-pre-base-low']
    advance_pct = anchor_low.price / max(pre_base_low.price, 1e-9) - 1.0
    if advance_pct < 0.25:
        reasons.append('advance-too-small')

    recent_highs = highs[-3:]
    recent_lows = lows[-3:]
    higher_highs = len(recent_highs) >= 2 and all(a.price < b.price for a, b in zip(recent_highs, recent_highs[1:]))
    higher_lows = len(recent_lows) >= 2 and all(a.price < b.price for a, b in zip(recent_lows, recent_lows[1:]))
    if not higher_highs:
        reasons.append('no-higher-highs')
    if not higher_lows:
        reasons.append('no-higher-lows')

    if len(frame) >= 200:
        latest = frame.iloc[-1]
        if not bool(latest['SMA50'] > latest['SMA150'] or latest['SMA50'] > frame['SMA50'].iloc[-20]):
            reasons.append('weak-moving-average-structure')

    return len(reasons) == 0, reasons


def evaluate_vcp_from_swings(
    frame: pd.DataFrame,
    swings: list[SwingPoint],
    legs: list[SwingLeg],
    max_base_depth: float,
) -> VcpDetectionResult:
    if len(swings) < 5 or len(legs) < 4:
        return VcpDetectionResult(False, False, defects=['insufficient-swings'])

    prior_uptrend, prior_reasons = evaluate_prior_uptrend(frame, swings)
    recent_legs = legs[-6:]
    down_legs = [leg for leg in recent_legs if leg.direction == 'down']
    if len(down_legs) < 2:
        return VcpDetectionResult(False, prior_uptrend, defects=['not-enough-down-legs'] + prior_reasons)

    contraction_depths = [abs(leg.move_pct) for leg in down_legs[-4:]]
    shrinking_pairs = sum(1 for a, b in zip(contraction_depths, contraction_depths[1:]) if a >= b or abs(a - b) <= 0.02)
    shrinking = shrinking_pairs >= max(1, len(contraction_depths) - 2)
    duration_non_worsening = sum(1 for a, b in zip(down_legs[-4:], down_legs[-3:]) if a.duration >= b.duration or abs(a.move_pct) >= abs(b.move_pct)) >= max(1, len(down_legs[-4:]) - 2) if len(down_legs) >= 2 else False
    volume_dry_up = sum(1 for a, b in zip(down_legs[-4:], down_legs[-3:]) if a.avg_volume >= b.avg_volume or abs(a.avg_volume - b.avg_volume) / max(a.avg_volume, 1e-9) <= 0.10) >= max(1, len(down_legs[-4:]) - 2) if len(down_legs) >= 2 else False
    first_down_volume = down_legs[-4:].pop(0).avg_volume if len(down_legs[-4:]) >= 1 else 0.0
    last_down_volume = down_legs[-1].avg_volume if down_legs else 0.0
    volume_dry_up_quality = max(0.0, 1.0 - last_down_volume / max(first_down_volume, 1e-9)) if first_down_volume > 0 else None

    high_swings = [s for s in swings[-6:] if s.kind == 'high']
    if high_swings and high_swings[-1].index == len(frame) - 1 and len(high_swings) >= 2:
        high_swings = high_swings[:-1]
    pivot = max(high_swings, key=lambda s: s.price, default=None)
    if pivot is None:
        return VcpDetectionResult(False, prior_uptrend, defects=['missing-pivot'] + prior_reasons)

    base_start_idx = min(leg.start.index for leg in down_legs[-4:])
    base_window = frame.iloc[base_start_idx : pivot.index + 1]
    base_high = float(base_window['High'].max())
    base_low = float(base_window['Low'].min())
    base_depth = (base_high - base_low) / max(base_high, 1e-9)
    pivot_level = float(frame.iloc[pivot.index]['High'])
    latest_close = float(frame.iloc[-1]['Close'])
    distance_to_pivot = latest_close / max(pivot_level, 1e-9) - 1.0
    breakout_confirmation, breakout_volume_ratio, breakout_date = _compute_breakout_confirmation(frame, pivot_level)
    final_15 = frame.tail(15)
    final_tightness = ((float(final_15['High'].max()) - float(final_15['Low'].min())) / max(latest_close, 1e-9)) <= 0.10

    defects: list[str] = list(prior_reasons)
    if not prior_uptrend:
        defects.append('no-prior-uptrend')
    if base_depth > max_base_depth:
        defects.append('base-too-deep')
    if not shrinking:
        defects.append('contractions-not-shrinking')
    if not duration_non_worsening:
        defects.append('leg-duration-worsening')
    if not volume_dry_up:
        defects.append('volume-not-drying-up')
    if not final_tightness:
        defects.append('late-stage-not-tight')
    if distance_to_pivot > 0.08:
        defects.append('too-extended-from-pivot')

    detected = prior_uptrend and shrinking and final_tightness and base_depth <= max_base_depth and len(down_legs[-4:]) >= 2
    return VcpDetectionResult(
        detected=detected,
        prior_uptrend=prior_uptrend,
        contraction_count=len(contraction_depths),
        contraction_depths=[round(value, 4) for value in contraction_depths],
        base_depth_pct=round(base_depth, 4),
        pivot_price=round(pivot_level, 4),
        distance_to_pivot_pct=round(distance_to_pivot, 4),
        final_tightness=final_tightness,
        volume_dry_up=volume_dry_up,
        volume_dry_up_quality=round(volume_dry_up_quality, 4) if volume_dry_up_quality is not None else None,
        breakout_confirmation=breakout_confirmation,
        breakout_volume_ratio=round(breakout_volume_ratio, 4) if breakout_volume_ratio is not None else None,
        breakout_date=breakout_date,
        defects=defects,
        notes=[f'swings={len(swings)}', f'down_legs={len(down_legs)}'],
    )


def detect_vcp(frame: pd.DataFrame, max_base_depth: float = 0.35) -> VcpDetectionResult:
    if len(frame) < 120:
        return VcpDetectionResult(False, False, defects=['insufficient-history'])
    recent = frame.tail(160).reset_index(drop=True)
    swings = segment_swings(recent)
    if len(swings) < 5:
        swings = segment_swings(recent, min_bars_between_swings=3, pct_reversal=0.04, atr_multiplier=0.75)
    legs = build_swing_legs(recent, swings)
    return evaluate_vcp_from_swings(recent, swings, legs, max_base_depth=max_base_depth)


def _compute_breakout_confirmation(frame: pd.DataFrame, pivot_price: float | None) -> tuple[bool, float | None, str | None]:
    if frame.empty or pivot_price is None:
        return False, None, None
    latest = frame.iloc[-1]
    latest_close = float(latest['Close'])
    latest_high = float(latest['High'])
    volume_window = frame['Volume'].iloc[-21:-1] if len(frame) > 21 else frame['Volume'].iloc[:-1]
    average_volume = float(volume_window.mean()) if not volume_window.empty else float(frame['Volume'].iloc[-1])
    breakout_volume_ratio = float(latest['Volume']) / max(average_volume, 1e-9)
    breakout_confirmation = latest_close >= pivot_price * 0.998 and latest_high >= pivot_price and breakout_volume_ratio >= 1.2
    breakout_date = pd.to_datetime(latest.get('Date')).strftime('%Y-%m-%d') if 'Date' in frame.columns else None
    return breakout_confirmation, breakout_volume_ratio, breakout_date


def detect_52_week_high_breakout(frame: pd.DataFrame) -> BreakoutSignal:
    if len(frame) < 120:
        return BreakoutSignal(pattern_type='52-week-high-breakout', pattern_variant='new-high', detected=False, notes=['insufficient-history'])

    latest = frame.iloc[-1]
    prior_high = float(frame['High'].shift(1).rolling(252, min_periods=20).max().iloc[-1])
    if pd.isna(prior_high):
        return BreakoutSignal(pattern_type='52-week-high-breakout', pattern_variant='new-high', detected=False, notes=['missing-52w-high'])
    breakout_confirmation, breakout_volume_ratio, breakout_date = _compute_breakout_confirmation(frame, prior_high)
    recent_volume = frame['Volume'].tail(10).mean()
    base_volume = frame['Volume'].tail(50).head(40).mean() if len(frame) >= 50 else frame['Volume'].mean()
    volume_dry_up_quality = max(0.0, 1.0 - float(recent_volume) / max(float(base_volume), 1e-9)) if base_volume else None
    distance_to_pivot = float(latest['Close']) / max(prior_high, 1e-9) - 1.0
    detected = breakout_confirmation and distance_to_pivot <= 0.08
    return BreakoutSignal(
        pattern_type='52-week-high-breakout',
        pattern_variant='new-high',
        detected=detected,
        pivot_price=round(prior_high, 4),
        trigger_date=breakout_date,
        distance_to_pivot_pct=round(distance_to_pivot, 4),
        breakout_confirmation=breakout_confirmation,
        breakout_volume_ratio=round(breakout_volume_ratio, 4) if breakout_volume_ratio is not None else None,
        volume_dry_up_quality=round(volume_dry_up_quality, 4) if volume_dry_up_quality is not None else None,
        notes=['lookback=252'],
    )


def detect_platform_breakout(frame: pd.DataFrame, *, lookback: int = 30, max_depth: float = 0.15) -> BreakoutSignal:
    if len(frame) < lookback + 30:
        return BreakoutSignal(pattern_type='platform-breakout', pattern_variant='consolidation', detected=False, notes=['insufficient-history'])

    platform = frame.iloc[-(lookback + 1):-1]
    if platform.empty:
        return BreakoutSignal(pattern_type='platform-breakout', pattern_variant='consolidation', detected=False, notes=['empty-platform'])
    pivot_price = float(platform['High'].max())
    support_level = float(platform['Low'].min())
    base_depth_pct = (pivot_price - support_level) / max(pivot_price, 1e-9)
    breakout_confirmation, breakout_volume_ratio, breakout_date = _compute_breakout_confirmation(frame, pivot_price)
    recent_volume = float(platform.tail(10)['Volume'].mean())
    early_volume = float(platform.head(max(10, len(platform) // 2))['Volume'].mean())
    volume_dry_up_quality = max(0.0, 1.0 - recent_volume / max(early_volume, 1e-9)) if early_volume else None
    latest_close = float(frame.iloc[-1]['Close'])
    distance_to_pivot = latest_close / max(pivot_price, 1e-9) - 1.0
    detected = base_depth_pct <= max_depth and breakout_confirmation and distance_to_pivot <= 0.08
    return BreakoutSignal(
        pattern_type='platform-breakout',
        pattern_variant='consolidation',
        detected=detected,
        pivot_price=round(pivot_price, 4),
        trigger_date=breakout_date,
        distance_to_pivot_pct=round(distance_to_pivot, 4),
        breakout_confirmation=breakout_confirmation,
        breakout_volume_ratio=round(breakout_volume_ratio, 4) if breakout_volume_ratio is not None else None,
        volume_dry_up_quality=round(volume_dry_up_quality, 4) if volume_dry_up_quality is not None else None,
        base_depth_pct=round(base_depth_pct, 4),
        support_level=round(support_level, 4),
        notes=[f'lookback={lookback}'],
    )
