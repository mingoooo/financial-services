from __future__ import annotations

import time

from reversal_lib.backtest import build_summary, run_backtesting_py
from reversal_lib.data.market_data import fetch_candles
from reversal_lib.domain.models import BacktestResult, SignalCandidate
from reversal_lib.domain.requests import UniverseRequest
from reversal_lib.models import Candle, Signal
from reversal_lib.pipeline.scan_pipeline import run_scan
from reversal_lib.strategy.spec import StrategySpec
from reversal_lib.strategy.trade_plan import build_trade_plan


def _to_legacy_signal(signal: SignalCandidate, candles: list[Candle], spec: StrategySpec) -> Signal:
    dates = [time.strftime('%Y-%m-%d', time.gmtime(c.ts)) for c in candles]
    plan = build_trade_plan(signal, candles, stop_mode=spec.stop_mode, target_mode=spec.target_mode)
    context = signal.indicator_context
    return Signal(
        symbol=signal.hit.symbol,
        side=signal.side,
        pattern=signal.hit.pattern,
        candidate_index=signal.hit.candidate_index,
        confirm_index=signal.hit.confirm_index or signal.hit.candidate_index + 1,
        candidate_date=signal.hit.candidate_date,
        confirm_date=signal.hit.confirm_date or dates[signal.hit.candidate_index + 1],
        confirm_close=round(signal.confirm_close, 2),
        planned_entry_price=round(signal.planned_entry_price if signal.entry_mode == 'confirm_close' else plan.entry_price, 2),
        entry_mode=signal.entry_mode,
        stop_loss=round(plan.stop_loss, 2),
        first_target=round(signal.first_target, 2),
        second_target=round(signal.second_target, 2),
        confirm_volume=round(signal.confirm_volume, 0),
        avg_volume_20=round(signal.avg_volume_20, 0),
        avg_dollar_volume_20=round(signal.avg_dollar_volume_20, 0),
        market_cap=signal.market_cap,
        pattern_strength=signal.hit.pattern_strength,
        confirmation_reason=signal.hit.confirmation_reason,
        score=signal.hit.score,
        score_detail=signal.hit.score_detail,
        structural_r_multiple=signal.structural_r_multiple,
        trend_context=context.trend_context if context else None,
        location_context=context.location_context if context else None,
        sma_cross_context=context.sma_cross_context if context else None,
        rsi_value=context.rsi_value if context else None,
        above_sma200=context.above_sma200 if context else None,
        macd_context=context.macd_context if context else None,
        candlestick_quality=signal.candlestick_quality,
        candlestick_notes=signal.candlestick_notes,
    )


def run_backtest(spec: StrategySpec, universe_request: UniverseRequest, range_str: str) -> BacktestResult:
    signal_candidates = run_scan(spec, universe_request, range_str)
    requested_symbols_total = len(universe_request.symbols) if universe_request.symbols else 0
    by_symbol: dict[str, list[SignalCandidate]] = {}
    for signal in signal_candidates:
        by_symbol.setdefault(signal.hit.symbol, []).append(signal)

    legacy_signals: list[Signal] = []
    trade_plans = []
    trades = []
    stats_list = []
    failed = 0
    processed = 0

    for symbol, symbol_signals in by_symbol.items():
        candles = fetch_candles(symbol, range_str=range_str)
        if len(candles) < 30:
            failed += 1
            continue
        dates = [time.strftime('%Y-%m-%d', time.gmtime(c.ts)) for c in candles]
        opens = [c.open for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        symbol_legacy: list[Signal] = []
        for signal in symbol_signals:
            trade_plans.append(build_trade_plan(signal, candles, stop_mode=spec.stop_mode, target_mode=spec.target_mode))
            symbol_legacy.append(_to_legacy_signal(signal, candles, spec))
        symbol_trades, stats = run_backtesting_py(symbol_legacy, dates, opens, highs, lows, closes, entry_mode=spec.entry_mode)
        legacy_signals.extend(symbol_legacy)
        trades.extend(symbol_trades)
        if stats is not None:
            stats_list.append(stats)
        processed += 1

    symbols_total = max(len(by_symbol), requested_symbols_total)
    summary = build_summary(trades, symbols_total=symbols_total, symbols_processed=processed, symbols_failed=failed, stats_list=stats_list)
    return BacktestResult(signals=legacy_signals, trade_plans=trade_plans, trades=trades, summary=summary)


__all__ = ['run_backtest']
