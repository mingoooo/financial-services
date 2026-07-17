from __future__ import annotations

import pandas as pd

from scripts.vcp_lib.indicators import (
    add_52_week_indicators,
    add_gap_and_breakout_indicators,
    add_liquidity_indicators,
    add_moving_average_indicators,
    add_range_indicators,
    add_relative_strength_proxy,
)


def add_shared_preprocessing(
    frame: pd.DataFrame,
    *,
    benchmark: pd.DataFrame | pd.Series | None = None,
) -> pd.DataFrame:
    enriched = frame.copy()
    enriched = add_moving_average_indicators(enriched)
    enriched = add_52_week_indicators(enriched)
    enriched = add_range_indicators(enriched)
    enriched = add_liquidity_indicators(enriched)
    enriched = add_gap_and_breakout_indicators(enriched)
    enriched = add_relative_strength_proxy(enriched, benchmark=benchmark)
    return enriched
