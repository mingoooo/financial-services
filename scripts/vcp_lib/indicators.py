from __future__ import annotations

import pandas as pd


TRADING_DAYS_PER_YEAR = 252
DEFAULT_AVERAGE_WINDOW = 20
DEFAULT_RS_LOOKBACK = 63


def add_moving_average_indicators(
    frame: pd.DataFrame,
    *,
    price_column: str = 'Close',
    windows: tuple[int, ...] = (10, 20, 50, 150, 200),
) -> pd.DataFrame:
    enriched = frame.copy()
    for window in windows:
        enriched[f'SMA{window}'] = enriched[price_column].rolling(window).mean()
    return enriched


def add_52_week_indicators(
    frame: pd.DataFrame,
    *,
    high_column: str = 'High',
    low_column: str = 'Low',
    close_column: str = 'Close',
    window: int = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    enriched = frame.copy()
    high_52_week = enriched[high_column].rolling(window, min_periods=20).max()
    low_52_week = enriched[low_column].rolling(window, min_periods=20).min()
    close = enriched[close_column].replace(0, pd.NA)
    enriched['High52Week'] = high_52_week
    enriched['Low52Week'] = low_52_week
    enriched['ClosePctFrom52WHigh'] = close / high_52_week - 1.0
    enriched['ClosePctFrom52WLow'] = close / low_52_week - 1.0
    return enriched


def add_range_indicators(
    frame: pd.DataFrame,
    *,
    high_column: str = 'High',
    low_column: str = 'Low',
    close_column: str = 'Close',
    atr_window: int = DEFAULT_AVERAGE_WINDOW,
) -> pd.DataFrame:
    enriched = frame.copy()
    prev_close = enriched[close_column].shift(1)
    high_low = enriched[high_column] - enriched[low_column]
    high_prev_close = (enriched[high_column] - prev_close).abs()
    low_prev_close = (enriched[low_column] - prev_close).abs()

    enriched['PrevClose'] = prev_close
    enriched['TrueRange'] = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    close = enriched[close_column].replace(0, pd.NA)
    enriched['ATR20'] = enriched['TrueRange'].rolling(atr_window).mean()
    enriched['RangePct'] = high_low / close
    enriched['RangePct20'] = enriched['RangePct'].rolling(atr_window).mean()
    return enriched


def add_liquidity_indicators(
    frame: pd.DataFrame,
    *,
    close_column: str = 'Close',
    volume_column: str = 'Volume',
    window: int = DEFAULT_AVERAGE_WINDOW,
) -> pd.DataFrame:
    enriched = frame.copy()
    avg_volume = enriched[volume_column].rolling(window).mean()
    avg_dollar_volume = (enriched[close_column] * enriched[volume_column]).rolling(window).mean()
    enriched['AvgVolume20'] = avg_volume
    enriched['AverageVolume'] = avg_volume
    enriched['DollarVolume20'] = avg_dollar_volume
    enriched['AvgDollarVolume20'] = avg_dollar_volume
    enriched['AverageDollarVolume'] = avg_dollar_volume
    return enriched


def add_gap_and_breakout_indicators(
    frame: pd.DataFrame,
    *,
    open_column: str = 'Open',
    close_column: str = 'Close',
    volume_column: str = 'Volume',
    window: int = DEFAULT_AVERAGE_WINDOW,
) -> pd.DataFrame:
    enriched = frame.copy()
    prev_close = enriched[close_column].shift(1).replace(0, pd.NA)
    enriched['GapPct'] = enriched[open_column] / prev_close - 1.0
    average_volume = enriched.get('AvgVolume20')
    if average_volume is None:
        average_volume = enriched[volume_column].rolling(window).mean()
    enriched['BreakoutVolumeRatio'] = enriched[volume_column] / average_volume.replace(0, pd.NA)
    return enriched


def add_relative_strength_proxy(
    frame: pd.DataFrame,
    *,
    benchmark: pd.DataFrame | pd.Series | None = None,
    close_column: str = 'Close',
    lookback: int = DEFAULT_RS_LOOKBACK,
) -> pd.DataFrame:
    enriched = frame.copy()
    stock_return = enriched[close_column] / enriched[close_column].shift(lookback) - 1.0
    if benchmark is None:
        enriched['RSProxy'] = stock_return
        return enriched

    benchmark_close = benchmark[close_column] if isinstance(benchmark, pd.DataFrame) else benchmark
    aligned_benchmark = benchmark_close.reindex(enriched.index)
    if aligned_benchmark.isna().all() and len(benchmark_close) == len(enriched):
        aligned_benchmark = pd.Series(benchmark_close.to_numpy(), index=enriched.index)
    benchmark_return = aligned_benchmark / aligned_benchmark.shift(lookback) - 1.0
    enriched['RSProxy'] = stock_return - benchmark_return
    return enriched


def add_core_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = add_moving_average_indicators(frame, windows=(50, 150, 200))
    enriched = add_liquidity_indicators(enriched)
    enriched = add_range_indicators(enriched)
    enriched = add_52_week_indicators(enriched)
    return enriched


def sma200_rising(frame: pd.DataFrame, lookback: int = 20) -> bool:
    series = frame['SMA200'].dropna()
    if len(series) < lookback + 1:
        return False
    recent = series.iloc[-1]
    old = series.iloc[-(lookback + 1)]
    return bool(recent >= old)
