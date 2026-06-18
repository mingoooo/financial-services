from __future__ import annotations


def describe_strategy_preset(preset: str | None) -> str:
    normalized = (preset or '').strip().lower()
    if normalized == 'main':
        return '主策略：sp500 + core ETF，仅做 bullish，要求确认量能、至少 2R 结构空间、刚站上 20SMA 或 50SMA，且 RSI(14) > 50。'
    if normalized == 'high_quality':
        return '高质量版：在主策略基础上，额外要求 MACD 处于 bullish / cross_up 状态，以减少交易数换取更高信号质量。'
    return '自定义参数：当前运行使用了非预设或部分覆盖后的参数组合，请结合页面中的实际参数摘要理解结果。'


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
