from __future__ import annotations


def apply_strategy_preset(options: dict, preset: str | None) -> dict:
    if not preset:
        return options
    preset = preset.strip().lower()
    merged = dict(options)
    if preset == 'main':
        merged.update({
            'universe': 'sp500',
            'include_etfs': True,
            'etf_groups': 'core',
            'side': 'bullish',
            'min_r_multiple': 2.0,
            'require_confirm_volume': True,
            'require_fresh_sma_cross_up': True,
            'sma_cross_mode': 'either',
            'require_rsi_above': 50.0,
            'require_macd_bullish': False,
            'require_above_sma200': False,
        })
    elif preset == 'high_quality':
        merged.update({
            'universe': 'sp500',
            'include_etfs': True,
            'etf_groups': 'core',
            'side': 'bullish',
            'min_r_multiple': 2.0,
            'require_confirm_volume': True,
            'require_fresh_sma_cross_up': True,
            'sma_cross_mode': 'either',
            'require_rsi_above': 50.0,
            'require_macd_bullish': True,
            'require_above_sma200': False,
        })
    return merged
