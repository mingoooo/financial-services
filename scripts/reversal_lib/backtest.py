from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import math
import statistics

import pandas as pd
from backtesting import Backtest, Strategy

from .models import BacktestSummary, Signal, TradeRecord


class ReversalSignalStrategy(Strategy):
    signals: list[Signal] = []
    signal_index_by_bar: dict[int, Signal] = {}

    def init(self) -> None:
        self._consumed_confirm_indexes: set[int] = set()

    def next(self) -> None:
        current_bar = len(self.data) - 1
        signal = self.signal_index_by_bar.get(current_bar)
        if signal is None:
            return
        if current_bar in self._consumed_confirm_indexes:
            return
        if self.position:
            return
        entry_price = float(signal.planned_entry_price)
        if signal.side == 'bullish':
            risk = entry_price - signal.stop_loss
            if risk <= 0:
                self._consumed_confirm_indexes.add(current_bar)
                return
            target_price = entry_price + risk * 2
            if not (signal.stop_loss < entry_price < target_price):
                self._consumed_confirm_indexes.add(current_bar)
                return
            self.buy(sl=signal.stop_loss, tp=target_price)
        else:
            risk = signal.stop_loss - entry_price
            if risk <= 0:
                self._consumed_confirm_indexes.add(current_bar)
                return
            target_price = entry_price - risk * 2
            if not (target_price < entry_price < signal.stop_loss):
                self._consumed_confirm_indexes.add(current_bar)
                return
            self.sell(sl=signal.stop_loss, tp=target_price)
        self._consumed_confirm_indexes.add(current_bar)


def _build_frame(dates: list[str], opens: list[float], highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    frame = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes,
    }, index=pd.to_datetime(dates))
    frame['Volume'] = 0.0
    return frame


def run_backtesting_py(signals: list[Signal], dates: list[str], opens: list[float], highs: list[float], lows: list[float], closes: list[float], entry_mode: str = 'next_open') -> tuple[list[TradeRecord], dict]:
    if not dates:
        return [], {}
    frame = _build_frame(dates, opens, highs, lows, closes)
    by_date = {value: idx for idx, value in enumerate(dates)}
    signal_map: dict[int, Signal] = {}
    for signal in signals:
        confirm_idx = by_date.get(signal.confirm_date)
        if confirm_idx is None:
            continue
        entry_idx = confirm_idx if entry_mode == 'confirm_close' else confirm_idx + 1
        if entry_idx < len(dates):
            signal_map[entry_idx] = signal
    ReversalSignalStrategy.signals = signals
    ReversalSignalStrategy.signal_index_by_bar = signal_map
    trade_on_close = entry_mode == 'confirm_close'
    backtest = Backtest(frame, ReversalSignalStrategy, cash=100000, commission=0.0, exclusive_orders=True, trade_on_close=trade_on_close, finalize_trades=True)
    stats = backtest.run()
    trades_df = stats.get('_trades')
    trades: list[TradeRecord] = []
    if trades_df is None or trades_df.empty:
        return trades, dict(stats)

    pending_by_date: dict[str, list[Signal]] = {}
    for signal in signals:
        entry_idx = by_date.get(signal.confirm_date)
        if entry_idx is None:
            continue
        effective_entry_idx = entry_idx if entry_mode == 'confirm_close' else entry_idx + 1
        if effective_entry_idx >= len(dates):
            continue
        pending_by_date.setdefault(dates[effective_entry_idx], []).append(signal)

    def pop_matching_signal(entry_date: str, side: str) -> Signal | None:
        candidates = pending_by_date.get(entry_date, [])
        for idx, signal in enumerate(candidates):
            if signal.side == side:
                return candidates.pop(idx)
        return None

    for _, row in trades_df.iterrows():
        entry_bar = int(row['EntryBar'])
        exit_bar = int(row['ExitBar'])
        side = 'bullish' if float(row['Size']) > 0 else 'bearish'
        entry_time = row['EntryTime']
        entry_date = entry_time.strftime('%Y-%m-%d') if hasattr(entry_time, 'strftime') else str(entry_time)
        signal = pop_matching_signal(entry_date, side)
        if signal is None:
            continue
        target_price = round(float(row['TP']), 4)
        exit_price = round(float(row['ExitPrice']), 4)
        exit_reason = 'eod'
        if abs(exit_price - signal.stop_loss) < 1e-4:
            exit_reason = 'stop_loss'
        elif abs(exit_price - target_price) < 1e-4:
            exit_reason = 'target'
        trades.append(TradeRecord(
            symbol=signal.symbol,
            side=side,
            pattern=signal.pattern,
            candidate_date=signal.candidate_date,
            confirm_date=signal.confirm_date,
            entry_date=dates[entry_bar],
            exit_date=dates[exit_bar],
            entry_price=round(float(row['EntryPrice']), 4),
            exit_price=exit_price,
            stop_loss=signal.stop_loss,
            target_price=target_price,
            exit_reason=exit_reason,
            pnl=round(float(row['PnL']), 4),
            return_pct=round(float(row['ReturnPct']) * 100.0, 4),
            score=signal.score,
        ))
    return trades, dict(stats)


def candles_to_ohlcv(candles) -> tuple[list[str], list[float], list[float], list[float], list[float]]:
    dates = [datetime.utcfromtimestamp(c.ts).strftime('%Y-%m-%d') for c in candles]
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    return dates, opens, highs, lows, closes


def run_symbol_backtest(signals: list[Signal], candles, *, entry_mode: str = 'next_open') -> tuple[list[TradeRecord], dict]:
    dates, opens, highs, lows, closes = candles_to_ohlcv(candles)
    return run_backtesting_py(signals, dates, opens, highs, lows, closes, entry_mode=entry_mode)


def calculate_trade_sharpe_ratio(return_pcts: list[float], risk_free_rate: float = 0.0) -> float:
    if len(return_pcts) < 2:
        return 0.0
    excess_returns = [value - risk_free_rate for value in return_pcts]
    try:
        stdev = statistics.stdev(excess_returns)
    except statistics.StatisticsError:
        return 0.0
    if stdev == 0:
        return 0.0
    mean = statistics.fmean(excess_returns)
    return round((mean / stdev) * math.sqrt(len(excess_returns)), 4)


def build_summary(trades: list[TradeRecord], symbols_total: int, symbols_processed: int, symbols_failed: int, stats_list: list[dict] | None = None) -> BacktestSummary:
    returns = [trade.return_pct for trade in trades]
    wins = [trade for trade in trades if trade.pnl > 0]
    losses = [trade for trade in trades if trade.pnl < 0]
    gross_profit = sum(trade.pnl for trade in wins)
    gross_loss = abs(sum(trade.pnl for trade in losses))
    max_drawdown = 0.0
    if stats_list:
        drawdowns = []
        for stats in stats_list:
            value = stats.get('Max. Drawdown [%]')
            if value is not None:
                drawdowns.append(abs(float(value)))
        if drawdowns:
            max_drawdown = max(drawdowns)
    returns_sorted = sorted(returns)
    median = returns_sorted[len(returns_sorted)//2] if returns_sorted else 0.0
    return BacktestSummary(
        symbols_total=symbols_total,
        symbols_processed=symbols_processed,
        symbols_failed=symbols_failed,
        total_trades=len(trades),
        win_rate=round((len(wins) / len(trades) * 100.0), 4) if trades else 0.0,
        average_return_pct=round(sum(returns) / len(returns), 4) if returns else 0.0,
        median_return_pct=round(median, 4) if returns else 0.0,
        total_pnl=round(sum(trade.pnl for trade in trades), 4),
        max_drawdown_pct=round(max_drawdown, 4),
        profit_factor=round((gross_profit / gross_loss), 4) if gross_loss else 0.0,
    )


def summary_to_dict(summary: BacktestSummary) -> dict:
    payload = asdict(summary)
    payload['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return payload


__all__ = [
    'ReversalSignalStrategy',
    'run_backtesting_py',
    'candles_to_ohlcv',
    'run_symbol_backtest',
    'calculate_trade_sharpe_ratio',
    'build_summary',
    'summary_to_dict',
]
