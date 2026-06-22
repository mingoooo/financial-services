from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from reversal_lib.domain.models import PatternHit, SignalCandidate
from reversal_lib.indicators.context import build_indicator_context, prepare_indicator_context_inputs
from reversal_lib.models import Candle
from reversal_lib.patterns import detect_bearish_pattern, detect_bullish_pattern, detect_support_resistance_levels_from_window
from reversal_lib.presets import load_strategy_spec
from reversal_lib.signals import generate_signals
from reversal_lib.strategy.rules import evaluate_signal
from reversal_lib.strategy.trade_plan import build_trade_plan

FIXTURE_DIR = ROOT / 'tests' / 'fixtures' / 'reversal'


def _load_candles(name: str) -> list[Candle]:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding='utf-8'))
    return [Candle(**item) for item in payload]


def _staged_generate(candles: list[Candle], symbol: str, preset: str):
    spec = load_strategy_spec(preset, overrides={})
    prepared = prepare_indicator_context_inputs(candles)
    staged: list[tuple[str, str, str, float, float]] = []
    for idx in range(20, len(candles) - 2):
        candidate = candles[idx]
        confirm = candles[idx + 1]
        sr_window = candles[max(0, idx + 2 - 50):idx + 2]
        supports, resistances = detect_support_resistance_levels_from_window(sr_window)
        for side, detector in [('bullish', detect_bullish_pattern), ('bearish', detect_bearish_pattern)]:
            if spec.side != 'both' and spec.side != side:
                continue
            pattern, stop_anchor = detector(candles, idx)
            if not pattern or stop_anchor is None:
                continue
            confirmed = confirm.close > max(candidate.open, candidate.close) if side == 'bullish' else confirm.close < min(candidate.open, candidate.close)
            if not confirmed:
                continue
            context = build_indicator_context(
                candles,
                idx,
                confirm.close,
                spec.indicator_config.get('location_tolerance_ratio', 0.02),
                confirm.volume,
                spec.confirm_volume_multiplier,
                prepared,
            )
            avg_vol20 = context.avg_volume_20
            avg_dollar_volume_20 = context.avg_dollar_volume_20
            if avg_vol20 is None or avg_dollar_volume_20 is None:
                continue
            signal = SignalCandidate(
                hit=PatternHit(symbol=symbol, pattern=pattern, candidate_index=idx, candidate_date='x', confirm_index=idx + 1, confirm_date='y'),
                side=side,
                confirm_close=confirm.close,
                planned_entry_price=confirm.close if spec.entry_mode == 'confirm_close' else candles[idx + 2].open,
                stop_loss=stop_anchor,
                first_target=(min(resistances) if resistances else confirm.close) if side == 'bullish' else (max(supports) if supports else confirm.close),
                second_target=(resistances[1] if len(resistances) > 1 else confirm.close) if side == 'bullish' else (supports[-2] if len(supports) > 1 else confirm.close),
                confirm_volume=confirm.volume,
                avg_volume_20=avg_vol20,
                avg_dollar_volume_20=avg_dollar_volume_20,
                entry_mode=spec.entry_mode,
            )
            accepted, enriched = evaluate_signal(signal, context, spec)
            if not accepted:
                continue
            plan = build_trade_plan(enriched, candles, stop_mode=spec.stop_mode, target_mode=spec.target_mode)
            staged.append((side, pattern, plan.entry_date, round(plan.stop_loss, 2), round(plan.target_price, 2)))
    return staged


def test_generate_signals_matches_staged_rule_evaluation_for_main_fixture() -> None:
    candles = _load_candles('main_preset_fixture.json')
    legacy = generate_signals(
        candles,
        symbol='META',
        side='bullish',
        require_confirm_volume=True,
        confirm_volume_multiplier=1.5,
        min_r_multiple=1.5,
        require_trend_alignment=False,
        require_location_alignment=False,
        location_tolerance_ratio=0.02,
        allowed_patterns=None,
        require_fresh_sma_cross_up=False,
        sma_cross_mode='either',
        require_macd_bullish=False,
        require_rsi_above=None,
        require_above_sma200=False,
        entry_mode='confirm_close',
        stop_mode='confirm_low',
        target_mode='nearest_resistance',
    )
    staged = _staged_generate(candles, 'META', 'main')
    assert [(s.side, s.pattern, s.confirm_date, s.stop_loss, s.first_target) for s in legacy] == staged
