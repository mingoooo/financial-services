from __future__ import annotations

import time

from reversal_lib.domain.models import SignalCandidate, TradePlan
from reversal_lib.models import Candle
from reversal_lib.patterns import detect_support_resistance_levels_from_window


def build_trade_plan(
    signal: SignalCandidate,
    candles: list[Candle],
    *,
    stop_mode: str,
    target_mode: str,
) -> TradePlan:
    confirm_index = signal.hit.confirm_index
    assert confirm_index is not None
    entry_index = confirm_index + 1
    confirm = candles[confirm_index]
    entry_candle = candles[entry_index]
    sr_window = candles[max(0, confirm_index + 1 - 50):confirm_index + 1]
    supports, resistances = detect_support_resistance_levels_from_window(sr_window)

    entry_price = signal.confirm_close if signal.entry_mode == 'confirm_close' else entry_candle.open
    if signal.side == 'bullish':
        resolved_stop = max(signal.stop_loss, confirm.low) if stop_mode == 'tighter_of_pattern_and_confirm_low' else (confirm.low if stop_mode == 'confirm_low' else signal.stop_loss)
        risk = entry_price - resolved_stop
        structural_target = min(resistances) if resistances else None
        target_price = structural_target if (target_mode == 'nearest_resistance' and structural_target is not None) else (entry_price + risk)
        structural_r_multiple = ((structural_target - entry_price) / risk) if (structural_target is not None and risk > 0) else None
    else:
        resolved_stop = max(signal.stop_loss, confirm.high) if stop_mode == 'tighter_of_pattern_and_confirm_low' else (confirm.high if stop_mode == 'confirm_low' else signal.stop_loss)
        risk = resolved_stop - entry_price
        structural_target = max(supports) if supports else None
        target_price = structural_target if (target_mode == 'nearest_resistance' and structural_target is not None) else (entry_price - risk)
        structural_r_multiple = ((entry_price - structural_target) / risk) if (structural_target is not None and risk > 0) else None

    signal.structural_r_multiple = round(structural_r_multiple, 4) if structural_r_multiple is not None else None
    return TradePlan(
        signal=signal,
        entry_date=time.strftime('%Y-%m-%d', time.gmtime(entry_candle.ts)),
        entry_price=round(entry_price, 2),
        stop_loss=round(resolved_stop, 2),
        target_price=round(target_price, 2),
    )
