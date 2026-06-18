from __future__ import annotations

from .models import Candle


def is_small_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    body = abs(candle.close - candle.open)
    return rng > 0 and body / rng <= 0.35


def is_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    top = max(candle.open, candle.close)
    bottom = min(candle.open, candle.close)
    lower_shadow = bottom - candle.low
    upper_shadow = candle.high - top
    body = top - bottom
    return lower_shadow >= body * 2 and upper_shadow <= body * 0.5 and top >= candle.low + rng * 0.6


def is_inverted_hammer(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    top = max(candle.open, candle.close)
    bottom = min(candle.open, candle.close)
    lower_shadow = bottom - candle.low
    upper_shadow = candle.high - top
    body = top - bottom
    return upper_shadow >= body * 2 and lower_shadow <= body * 0.5 and bottom <= candle.low + rng * 0.4


def real_body(candle: Candle) -> float:
    return abs(candle.close - candle.open)


def body_top(candle: Candle) -> float:
    return max(candle.open, candle.close)


def body_bottom(candle: Candle) -> float:
    return min(candle.open, candle.close)


def is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def is_long_body(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng >= 0.55


def is_doji(candle: Candle) -> bool:
    rng = candle.high - candle.low
    return rng > 0 and real_body(candle) / rng <= 0.1


def is_bullish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bearish(prev_candle)
        and is_bullish(candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and body_top(candle) >= body_top(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_piercing_pattern(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bearish(first)
        and is_long_body(first)
        and is_bullish(second)
        and second.open < first.low + (first.high - first.low) * 0.25
        and second.close > midpoint
        and second.close < first.open
    )


def is_morning_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bearish(first)
        and is_long_body(first)
        and small_second
        and is_bullish(third)
        and third.close > midpoint
    )


def is_shooting_star(candle: Candle) -> bool:
    rng = candle.high - candle.low
    if rng <= 0 or not is_small_body(candle):
        return False
    upper_shadow = candle.high - body_top(candle)
    lower_shadow = body_bottom(candle) - candle.low
    return upper_shadow >= real_body(candle) * 2 and lower_shadow <= max(real_body(candle) * 0.5, rng * 0.1)


def is_hanging_man(candle: Candle) -> bool:
    return is_hammer(candle)


def is_bearish_engulfing(prev_candle: Candle, candle: Candle) -> bool:
    return (
        is_bullish(prev_candle)
        and is_bearish(candle)
        and body_top(candle) >= body_top(prev_candle)
        and body_bottom(candle) <= body_bottom(prev_candle)
        and real_body(candle) > real_body(prev_candle) * 0.9
    )


def is_dark_cloud_cover(first: Candle, second: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    return (
        is_bullish(first)
        and is_long_body(first)
        and is_bearish(second)
        and second.open > first.high - (first.high - first.low) * 0.25
        and second.close < midpoint
        and second.close > first.open
    )


def is_evening_star(first: Candle, second: Candle, third: Candle) -> bool:
    midpoint = (first.open + first.close) / 2
    small_second = real_body(second) <= max(real_body(first) * 0.5, (second.high - second.low) * 0.35)
    return (
        is_bullish(first)
        and is_long_body(first)
        and small_second
        and is_bearish(third)
        and third.close < midpoint
    )


def is_bullish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bearish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bullish(second)
    )


def is_bearish_harami(first: Candle, second: Candle) -> bool:
    return (
        is_bullish(first)
        and is_long_body(first)
        and real_body(second) <= real_body(first) * 0.6
        and body_bottom(second) >= body_bottom(first)
        and body_top(second) <= body_top(first)
        and is_bearish(second)
    )


def has_prior_uptrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] > closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1]) >= 2


def detect_bearish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_shooting_star(candle):
        return "Shooting Star / 流星线", candle.high
    if is_hanging_man(candle):
        return "Hanging Man / 上吊线", candle.high
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bearish_engulfing(prev_candle, candle):
            return "Bearish Engulfing / 看跌吞没", max(prev_candle.high, candle.high)
        if is_dark_cloud_cover(prev_candle, candle):
            return "Dark Cloud Cover / 乌云盖顶", max(prev_candle.high, candle.high)
        if is_bearish_harami(prev_candle, candle):
            return "Bearish Harami / 看跌孕线", max(prev_candle.high, candle.high)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_evening_star(first, second, third):
            return "Evening Star / 黄昏星", max(first.high, second.high, third.high)
    return None, None


def detect_bullish_pattern(candles: list[Candle], idx: int) -> tuple[str | None, float | None]:
    candle = candles[idx]
    if is_hammer(candle):
        return "Hammer / 锤头线", candle.low
    if is_inverted_hammer(candle):
        return "Inverted Hammer / 倒锤头线", candle.low
    if idx >= 1:
        prev_candle = candles[idx - 1]
        if is_bullish_engulfing(prev_candle, candle):
            return "Bullish Engulfing / 看涨吞没", min(prev_candle.low, candle.low)
        if is_piercing_pattern(prev_candle, candle):
            return "Piercing Pattern / 刺透形态", min(prev_candle.low, candle.low)
        if is_bullish_harami(prev_candle, candle):
            return "Bullish Harami / 看涨孕线", min(prev_candle.low, candle.low)
    if idx >= 2:
        first = candles[idx - 2]
        second = candles[idx - 1]
        third = candles[idx]
        if is_morning_star(first, second, third):
            return "Morning Star / 启明星", min(first.low, second.low, third.low)
    return None, None


def has_prior_downtrend(candles: list[Candle], idx: int) -> bool:
    if idx < 4:
        return False
    closes = [c.close for c in candles[idx - 4:idx]]
    return closes[-1] < closes[0] and sum(1 for i in range(1, len(closes)) if closes[i] < closes[i - 1]) >= 2


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_signal_score(pattern_strength: str | None, confirm_volume: float, avg_volume_20: float, market_cap: float | None, avg_dollar_volume_20: float) -> tuple[float, str]:
    strength_points = {"strong": 40.0, "medium": 28.0, "standard": 20.0}.get(pattern_strength or "standard", 20.0)
    volume_ratio = (confirm_volume / avg_volume_20) if avg_volume_20 > 0 else 1.0
    if volume_ratio >= 2.0:
        volume_points = 25.0
    elif volume_ratio >= 1.5:
        volume_points = 20.0
    elif volume_ratio >= 1.1:
        volume_points = 14.0
    elif volume_ratio >= 1.0:
        volume_points = 10.0
    else:
        volume_points = 4.0

    if market_cap is None:
        market_cap_points = 6.0
    elif market_cap >= 200_000_000_000:
        market_cap_points = 18.0
    elif market_cap >= 10_000_000_000:
        market_cap_points = 14.0
    elif market_cap >= 2_000_000_000:
        market_cap_points = 10.0
    else:
        market_cap_points = 6.0

    if avg_dollar_volume_20 >= 500_000_000:
        liquidity_points = 17.0
    elif avg_dollar_volume_20 >= 100_000_000:
        liquidity_points = 13.0
    elif avg_dollar_volume_20 >= 25_000_000:
        liquidity_points = 9.0
    else:
        liquidity_points = 5.0

    score = clamp_score(strength_points + volume_points + market_cap_points + liquidity_points)
    detail = f"strength={strength_points:.0f}, volume={volume_points:.0f}, mcap={market_cap_points:.0f}, liquidity={liquidity_points:.0f}"
    return score, detail


def pattern_strength_label(pattern: str, side: str) -> str:
    strong = {
        "Bullish Engulfing / 看涨吞没",
        "Bearish Engulfing / 看跌吞没",
        "Morning Star / 启明星",
        "Evening Star / 黄昏星",
        "Dark Cloud Cover / 乌云盖顶",
        "Piercing Pattern / 刺透形态",
    }
    medium = {
        "Hammer / 锤头线",
        "Inverted Hammer / 倒锤头线",
        "Shooting Star / 流星线",
        "Hanging Man / 上吊线",
        "Bullish Harami / 看涨孕线",
        "Bearish Harami / 看跌孕线",
    }
    if pattern in strong:
        return "strong"
    if pattern in medium:
        return "medium"
    return "standard"


def bullish_confirmation_reason(pattern: str) -> str:
    mapping = {
        "Hammer / 锤头线": "确认日收盘站上候选实体上沿",
        "Inverted Hammer / 倒锤头线": "确认日收盘站上候选实体上沿",
        "Bullish Engulfing / 看涨吞没": "确认日收盘突破候选K线高点",
        "Bullish Harami / 看涨孕线": "确认日收盘突破候选K线高点",
        "Piercing Pattern / 刺透形态": "确认日继续上破候选高点与前阴线关键位",
        "Morning Star / 启明星": "确认日继续强化三K线底部反转",
    }
    return mapping.get(pattern, "确认日满足看涨确认条件")


def bearish_confirmation_reason(pattern: str) -> str:
    mapping = {
        "Shooting Star / 流星线": "确认日收盘跌破候选实体下沿",
        "Hanging Man / 上吊线": "确认日收盘跌破候选实体下沿",
        "Bearish Engulfing / 看跌吞没": "确认日收盘跌破候选K线低点",
        "Bearish Harami / 看跌孕线": "确认日收盘跌破候选K线低点",
        "Dark Cloud Cover / 乌云盖顶": "确认日继续下破候选低点并强化顶部反转",
        "Evening Star / 黄昏星": "确认日继续强化三K线顶部反转",
    }
    return mapping.get(pattern, "确认日满足看跌确认条件")


def bullish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {"Hammer / 锤头线", "Inverted Hammer / 倒锤头线"}:
        return confirm.close > body_top(candidate)
    if pattern in {"Bullish Engulfing / 看涨吞没", "Bullish Harami / 看涨孕线"}:
        return confirm.close > candidate.high
    if pattern == "Piercing Pattern / 刺透形态":
        prev_candle = candles[idx - 1]
        return confirm.close > max(candidate.high, body_top(prev_candle))
    if pattern == "Morning Star / 启明星":
        first = candles[idx - 2]
        return confirm.close > max(candidate.high, body_top(first))
    return confirm.close > body_top(candidate)


def bearish_confirmation_ok(pattern: str, candles: list[Candle], idx: int, confirm: Candle) -> bool:
    candidate = candles[idx]
    if pattern in {"Shooting Star / 流星线", "Hanging Man / 上吊线"}:
        return confirm.close < body_bottom(candidate)
    if pattern in {"Bearish Engulfing / 看跌吞没", "Bearish Harami / 看跌孕线"}:
        return confirm.close < candidate.low
    if pattern == "Dark Cloud Cover / 乌云盖顶":
        prev_candle = candles[idx - 1]
        return confirm.close < min(candidate.low, body_bottom(prev_candle))
    if pattern == "Evening Star / 黄昏星":
        first = candles[idx - 2]
        return confirm.close < min(candidate.low, body_bottom(first))
    return confirm.close < body_bottom(candidate)


def scan_symbol(symbol: str, require_confirm_volume: bool, market_cap: float | None = None, side: str = "both") -> ScanResult | None:
    candles = fetch_candles(symbol)
    if len(candles) < 25:
        return None
    for idx in range(len(candles) - 2, 3, -1):
        candidate = candles[idx]
        confirm = candles[idx + 1]
        avg_vol20 = statistics.mean(c.volume for c in candles[max(0, idx - 19):idx + 1])
        avg_dollar_volume_20 = statistics.mean(c.close * c.volume for c in candles[max(0, idx - 19):idx + 1])
        scan_sides = [side] if side in {"bullish", "bearish"} else ["bullish", "bearish"]
        for current_side in scan_sides:
            if current_side == "bullish":
                if not has_prior_downtrend(candles, idx):
                    continue
                pattern, stop_anchor = detect_bullish_pattern(candles, idx)
                if not pattern or stop_anchor is None:
                    continue
                if not bullish_confirmation_ok(pattern, candles, idx, confirm):
                    continue
                if require_confirm_volume and confirm.volume < avg_vol20:
                    continue
                risk = confirm.close - stop_anchor
                if risk <= 0:
                    continue
                score, score_detail = compute_signal_score(pattern_strength_label(pattern, current_side), round(confirm.volume, 0), round(avg_vol20, 0), market_cap, round(avg_dollar_volume_20, 0))
                return ScanResult(
                    symbol=symbol,
                    pattern=pattern,
                    candidate_date=time.strftime("%Y-%m-%d", time.gmtime(candidate.ts)),
                    confirm_date=time.strftime("%Y-%m-%d", time.gmtime(confirm.ts)),
                    confirm_close=round(confirm.close, 2),
                    stop_loss=round(stop_anchor, 2),
                    first_target=round(confirm.close + risk, 2),
                    second_target=round(confirm.close + risk * 2, 2),
                    confirm_volume=round(confirm.volume, 0),
                    avg_volume_20=round(avg_vol20, 0),
                    avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                    market_cap=market_cap,
                    confidence="confirmed",
                    pattern_strength=pattern_strength_label(pattern, current_side),
                    confirmation_reason=bullish_confirmation_reason(pattern),
                    score=score,
                    score_detail=score_detail,
                )
            else:
                if not has_prior_uptrend(candles, idx):
                    continue
                pattern, stop_anchor = detect_bearish_pattern(candles, idx)
                if not pattern or stop_anchor is None:
                    continue
                if not bearish_confirmation_ok(pattern, candles, idx, confirm):
                    continue
                if require_confirm_volume and confirm.volume < avg_vol20:
                    continue
                risk = stop_anchor - confirm.close
                if risk <= 0:
                    continue
                score, score_detail = compute_signal_score(pattern_strength_label(pattern, current_side), round(confirm.volume, 0), round(avg_vol20, 0), market_cap, round(avg_dollar_volume_20, 0))
                return ScanResult(
                    symbol=symbol,
                    pattern=pattern,
                    candidate_date=time.strftime("%Y-%m-%d", time.gmtime(candidate.ts)),
                    confirm_date=time.strftime("%Y-%m-%d", time.gmtime(confirm.ts)),
                    confirm_close=round(confirm.close, 2),
                    stop_loss=round(stop_anchor, 2),
                    first_target=round(confirm.close - risk, 2),
                    second_target=round(confirm.close - risk * 2, 2),
                    confirm_volume=round(confirm.volume, 0),
                    avg_volume_20=round(avg_vol20, 0),
                    avg_dollar_volume_20=round(avg_dollar_volume_20, 0),
                    market_cap=market_cap,
                    confidence="confirmed",
                    pattern_strength=pattern_strength_label(pattern, current_side),
                    confirmation_reason=bearish_confirmation_reason(pattern),
                    score=score,
                    score_detail=score_detail,
                )
    return None


def is_transient_scan_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in {403, 408, 409, 425, 429, 500, 502, 503, 504}
    if isinstance(exc, URLError):
        return True
    if isinstance(exc, RuntimeError):
        return True
    return False


def scan_symbol_with_retries(symbol: str, require_confirm_volume: bool, market_cap: float | None = None, retries: int = 3, side: str = "bullish") -> ScanResult | None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return scan_symbol(symbol, require_confirm_volume, market_cap, side)
        except (URLError, HTTPError, KeyError, IndexError, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            if not is_transient_scan_error(exc):
                break
            backoff = min(1.5 * (2 ** (attempt - 1)), 8.0) + random.uniform(0.0, 0.35)
            log(f"retry {attempt}/{retries-1} for {symbol} after transient error: {exc}; sleeping {backoff:.2f}s")
            time.sleep(backoff)
    if last_exc is not None:
        raise last_exc
    return None


def is_recent_confirm_date(confirm_date: str, max_age_days: int) -> bool:
    if max_age_days <= 0:
        return True
    confirm_dt = datetime.strptime(confirm_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_days = (now.date() - confirm_dt.date()).days
    return 0 <= age_days <= max_age_days


def format_market_cap(value: float | None) -> str:
    if value is None:
        return "-"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value:.0f}"


def simple_moving_average(candles: list[Candle], period: int) -> list[float | None]:
    values: list[float | None] = []
    closes = [c.close for c in candles]
    for idx in range(len(closes)):
        if idx + 1 < period:
            values.append(None)
        else:
            window = closes[idx - period + 1:idx + 1]
            values.append(sum(window) / period)
    return values


def detect_support_resistance_levels(candles: list[Candle], lookback: int = 50) -> tuple[list[float], list[float]]:
    window = candles[-lookback:] if len(candles) > lookback else candles
    if len(window) < 7:
        return [], []
    highs: list[float] = []
    lows: list[float] = []
    for i in range(2, len(window) - 2):
        c = window[i]
        left = window[i-2:i]
        right = window[i+1:i+3]
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


