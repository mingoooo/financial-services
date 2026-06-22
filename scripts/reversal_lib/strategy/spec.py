from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_ALLOWED_INDICATOR_CONFIG_KEYS = {
    'location_tolerance_ratio',
    'allowed_patterns',
    'require_trend_alignment',
    'require_location_alignment',
}


@dataclass(frozen=True)
class StrategySpec:
    side: str = 'bullish'
    min_r_multiple: float = 1.5
    require_confirm_volume: bool = True
    confirm_volume_multiplier: float = 1.5
    require_fresh_sma_cross_up: bool = False
    sma_cross_mode: str = 'either'
    require_standard_uptrend: bool = False
    require_macd_bullish: bool = False
    require_rsi_above: float | None = None
    require_above_sma200: bool = False
    entry_mode: str = 'confirm_close'
    stop_mode: str = 'confirm_low'
    target_mode: str = 'nearest_resistance'
    indicator_config: dict[str, Any] = field(default_factory=dict)

    def to_legacy_options(self) -> dict[str, Any]:
        indicator_config = dict(self.indicator_config)
        return {
            'side': self.side,
            'min_r_multiple': self.min_r_multiple,
            'require_confirm_volume': self.require_confirm_volume,
            'confirm_volume_multiplier': self.confirm_volume_multiplier,
            'require_fresh_sma_cross_up': self.require_fresh_sma_cross_up,
            'sma_cross_mode': self.sma_cross_mode,
            'require_standard_uptrend': self.require_standard_uptrend,
            'require_macd_bullish': self.require_macd_bullish,
            'require_rsi_above': self.require_rsi_above,
            'require_above_sma200': self.require_above_sma200,
            'entry_mode': self.entry_mode,
            'stop_mode': self.stop_mode,
            'target_mode': self.target_mode,
            'require_trend_alignment': indicator_config.get('require_trend_alignment', False),
            'require_location_alignment': indicator_config.get('require_location_alignment', False),
            'location_tolerance_ratio': indicator_config.get('location_tolerance_ratio', 0.02),
            'allowed_patterns': indicator_config.get('allowed_patterns'),
        }


def normalize_indicator_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {}
    unknown_keys = set(config) - _ALLOWED_INDICATOR_CONFIG_KEYS
    if unknown_keys:
        unknown = ', '.join(sorted(unknown_keys))
        raise ValueError(f'Unsupported indicator_config keys: {unknown}')
    return dict(config)
