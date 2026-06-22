from __future__ import annotations

from reversal_lib.patterns_layer.bearish import (
    detect_bearish_pattern,
    detect_bearish_pattern_hit,
    has_prior_uptrend,
    is_bearish_engulfing,
    is_bearish_harami,
    is_dark_cloud_cover,
    is_evening_star,
    is_hanging_man,
    is_shooting_star,
)
from reversal_lib.patterns_layer.bullish import (
    body_bottom,
    body_top,
    detect_bullish_pattern,
    detect_bullish_pattern_hit,
    has_prior_downtrend,
    is_bearish,
    is_bullish,
    is_bullish_engulfing,
    is_bullish_harami,
    is_doji,
    is_hammer,
    is_inverted_hammer,
    is_long_body,
    is_morning_star,
    is_piercing_pattern,
    is_small_body,
    real_body,
)
from reversal_lib.patterns_layer.levels import (
    detect_support_resistance_levels,
    detect_support_resistance_levels_from_window,
    find_resistance_levels,
    find_support_levels,
)
from reversal_lib.patterns_layer.scoring import (
    bearish_confirmation_ok,
    bearish_confirmation_reason,
    bullish_confirmation_ok,
    bullish_confirmation_reason,
    clamp_score,
    compute_signal_score,
    pattern_strength_label,
)
