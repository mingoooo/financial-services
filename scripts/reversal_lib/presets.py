from __future__ import annotations

from reversal_lib.strategy.spec import StrategySpec, normalize_indicator_config


_PRESET_SPECS: dict[str, dict] = {
    'main': {
        'side': 'bullish',
        'min_r_multiple': 1.5,
        'require_confirm_volume': True,
        'confirm_volume_multiplier': 1.5,
        'require_fresh_sma_cross_up': False,
        'sma_cross_mode': 'either',
        'require_standard_uptrend': True,
        'require_macd_bullish': False,
        'require_rsi_above': None,
        'require_above_sma200': False,
        'entry_mode': 'confirm_close',
        'stop_mode': 'confirm_low',
        'target_mode': 'nearest_resistance',
        'indicator_config': {},
    },
    'high_quality': {
        'side': 'bullish',
        'min_r_multiple': 1.5,
        'require_confirm_volume': True,
        'confirm_volume_multiplier': 1.5,
        'require_fresh_sma_cross_up': False,
        'sma_cross_mode': 'either',
        'require_standard_uptrend': True,
        'require_macd_bullish': True,
        'require_rsi_above': None,
        'require_above_sma200': False,
        'entry_mode': 'confirm_close',
        'stop_mode': 'confirm_low',
        'target_mode': 'nearest_resistance',
        'indicator_config': {},
    },
}


def describe_strategy_preset(preset: str | None) -> str:
    normalized = (preset or '').strip().lower()
    if normalized == 'main':
        return '主策略：sp500 + core ETF，仅做 bullish，要求确认量能至少为 20 日均量的 1.5 倍、至少 1.5R 到最近阻力位、股价高于 5 美元、且满足 close > SMA20 > SMA50 的标准上升趋势；默认按确认日收盘价入场、止损设在确认日最低点、止盈默认看最近阻力位。'
    if normalized == 'high_quality':
        return '高质量版：在主策略基础上，额外要求 MACD 处于 bullish / cross_up 状态，以减少交易数换取更高信号质量；默认按确认日收盘价入场。'
    return '自定义参数：当前运行使用了非预设或部分覆盖后的参数组合，请结合页面中的实际参数摘要理解结果。'


def load_strategy_spec(preset: str | None, overrides: dict) -> StrategySpec:
    normalized = (preset or '').strip().lower()
    base = dict(_PRESET_SPECS.get(normalized, {}))
    base['indicator_config'] = dict(base.get('indicator_config', {}))

    merged = dict(base)
    for key, value in dict(overrides).items():
        if key == 'indicator_config':
            merged['indicator_config'] = normalize_indicator_config(value)
        elif key in StrategySpec.__dataclass_fields__:
            merged[key] = value

    merged['indicator_config'] = normalize_indicator_config(merged.get('indicator_config'))
    return StrategySpec(**merged)


def apply_strategy_preset(options: dict, preset: str | None) -> dict:
    if not preset:
        return options

    spec = load_strategy_spec(preset, overrides={})
    merged = dict(options)
    merged.update(spec.to_legacy_options())

    normalized = preset.strip().lower()
    if normalized in {'main', 'high_quality'}:
        merged.update({
            'universe': 'sp500',
            'include_etfs': True,
            'etf_groups': 'core',
            'min_price': 5.0,
            'min_avg_volume': 300_000,
            'min_last_volume': 0,
        })
    return merged
