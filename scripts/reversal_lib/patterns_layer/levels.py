from __future__ import annotations

from reversal_lib.models import Candle


def find_support_levels(candles: list[Candle], idx: int, window: int = 3, tolerance_ratio: float = 0.005) -> list[float]:
    start = max(0, idx - 60)
    lows: list[float] = []
    for pivot in range(start + window, idx - window + 1):
        price = candles[pivot].low
        if all(price <= candles[pivot + offset].low for offset in range(-window, window + 1) if offset != 0):
            if not any(abs(price - existing) / existing <= tolerance_ratio for existing in lows if existing != 0):
                lows.append(price)
    return sorted(lows)


def find_resistance_levels(candles: list[Candle], idx: int, window: int = 3, tolerance_ratio: float = 0.005) -> list[float]:
    start = max(0, idx - 60)
    highs: list[float] = []
    for pivot in range(start + window, idx - window + 1):
        price = candles[pivot].high
        if all(price >= candles[pivot + offset].high for offset in range(-window, window + 1) if offset != 0):
            if not any(abs(price - existing) / existing <= tolerance_ratio for existing in highs if existing != 0):
                highs.append(price)
    return sorted(highs)


def detect_support_resistance_levels(candles: list[Candle], lookback: int = 50) -> tuple[list[float], list[float]]:
    window = candles[-lookback:] if len(candles) > lookback else candles
    if len(window) < 7:
        return [], []
    highs: list[float] = []
    lows: list[float] = []
    for i in range(2, len(window) - 2):
        c = window[i]
        left = window[i - 2:i]
        right = window[i + 1:i + 3]
        if c.high >= max(x.high for x in left + right):
            highs.append(c.high)
        if c.low <= min(x.low for x in left + right):
            lows.append(c.low)

    def dedupe(levels: list[float]) -> list[float]:
        picked: list[float] = []
        for level in sorted(levels):
            if not picked or abs(level - picked[-1]) / max(abs(level), 1.0) > 0.015:
                picked.append(level)
        return picked

    current = window[-1].close
    supports = [lvl for lvl in dedupe(lows) if lvl < current]
    resistances = [lvl for lvl in dedupe(highs) if lvl > current]
    supports = sorted(supports, key=lambda x: abs(current - x))[:2]
    resistances = sorted(resistances, key=lambda x: abs(current - x))[:2]
    return supports, resistances


def detect_support_resistance_levels_from_window(candles: list[Candle], lookback: int = 50) -> tuple[list[float], list[float]]:
    return detect_support_resistance_levels(candles, lookback=lookback)
