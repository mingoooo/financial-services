#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict

from reversal_lib.backtest import build_summary, run_backtesting_py
from reversal_lib.data import fetch_candles, resolve_prefiltered_symbols
from reversal_lib.report import write_html_report, write_json_summary, write_signal_csv, write_trade_csv
from reversal_lib.presets import apply_strategy_preset
from reversal_lib.signals import generate_signals


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回测反转形态策略")
    parser.add_argument("--symbols")
    parser.add_argument("--preset", choices=["main", "high_quality"])
    parser.add_argument("--require-rsi-above", type=float)
    parser.add_argument("--require-above-sma200", action="store_true")
    parser.add_argument("--require-macd-bullish", action="store_true")
    parser.add_argument("--range", default="5y")
    parser.add_argument("--universe", choices=["us", "sp500", "liquid"], default="sp500")
    parser.add_argument("--side", choices=["both", "bullish", "bearish"], default="both")
    parser.add_argument("--html")
    parser.add_argument("--json")
    parser.add_argument("--csv-dir")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--top-dollar-volume", type=int, default=0)
    parser.add_argument("--min-last-volume", type=float, default=50000)
    parser.add_argument("--min-avg-volume", type=float, default=750000)
    parser.add_argument("--min-price", type=float, default=1.0)
    parser.add_argument("--min-market-cap", type=float, default=2000000000)
    parser.add_argument("--exclude-etfs", dest="include_etfs", action="store_false")
    parser.add_argument("--etf-groups", default="core,theme,manual_exceptions")
    parser.add_argument("--include-etfs", action="store_true", default=True)
    parser.add_argument("--require-confirm-volume", action="store_true", default=True)
    parser.add_argument("--no-require-confirm-volume", dest="require_confirm_volume", action="store_false")
    parser.add_argument("--min-r-multiple", type=float, default=2.0)
    parser.add_argument("--require-trend-alignment", action="store_true")
    parser.add_argument("--require-location-alignment", action="store_true")
    parser.add_argument("--location-tolerance-ratio", type=float, default=0.02)
    parser.add_argument("--allowed-patterns")
    parser.add_argument("--require-fresh-sma-cross-up", action="store_true")
    parser.add_argument("--sma-cross-mode", choices=["either", "20", "50"], default="either")
    return parser.parse_args()


def _summarize_group(items):
    wins = [item for item in items if item.pnl > 0]
    losses = [item for item in items if item.pnl < 0]
    gross_profit = sum(item.pnl for item in wins)
    gross_loss = abs(sum(item.pnl for item in losses))
    returns = [item.return_pct for item in items]
    returns_sorted = sorted(returns)
    median = returns_sorted[len(returns_sorted)//2] if returns_sorted else 0.0
    return {
        "count": len(items),
        "win_rate_pct": round(len(wins) / len(items) * 100.0, 4) if items else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "median_return_pct": round(median, 4) if returns else 0.0,
        "total_pnl": round(sum(item.pnl for item in items), 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else 0.0,
    }


def group_metrics(trades):
    by_pattern = defaultdict(list)
    by_side = defaultdict(list)
    for trade in trades:
        by_pattern[trade.pattern].append(trade)
        by_side[trade.side].append(trade)
    return {
        "by_pattern": {key: _summarize_group(value) for key, value in sorted(by_pattern.items())},
        "by_side": {key: _summarize_group(value) for key, value in sorted(by_side.items())},
    }


def main() -> int:
    args = parse_args()
    preset_options = apply_strategy_preset(vars(args), args.preset)
    for key, value in preset_options.items():
        setattr(args, key, value)
    allowed_patterns = {item.strip() for item in args.allowed_patterns.split("|") if item.strip()} if args.allowed_patterns else None
    etf_groups = [item.strip() for item in args.etf_groups.split(',') if item.strip()] if args.etf_groups else None
    prefiltered = resolve_prefiltered_symbols(args.universe, symbols=args.symbols, include_etfs=args.include_etfs, min_market_cap=args.min_market_cap, min_price=args.min_price, min_avg_volume=args.min_avg_volume, min_last_volume=args.min_last_volume, top_dollar_volume=args.top_dollar_volume, limit=args.max_symbols or 0, etf_groups=etf_groups, range_str=args.range)
    symbols = [item.symbol for item in prefiltered]
    all_signals = []
    all_trades = []
    all_stats = []
    failed = 0
    processed = 0
    for symbol in symbols:
        try:
            candles = fetch_candles(symbol, range_str=args.range)
            if len(candles) < 30:
                continue
            dates = [__import__('time').strftime('%Y-%m-%d', __import__('time').gmtime(c.ts)) for c in candles]
            opens = [c.open for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            closes = [c.close for c in candles]
            signals = generate_signals(candles, symbol=symbol, side=args.side, require_confirm_volume=args.require_confirm_volume, min_r_multiple=args.min_r_multiple, require_trend_alignment=args.require_trend_alignment, require_location_alignment=args.require_location_alignment, location_tolerance_ratio=args.location_tolerance_ratio, allowed_patterns=allowed_patterns, require_fresh_sma_cross_up=args.require_fresh_sma_cross_up, sma_cross_mode=args.sma_cross_mode, require_macd_bullish=args.require_macd_bullish, require_rsi_above=args.require_rsi_above, require_above_sma200=args.require_above_sma200)
            trades, stats = run_backtesting_py(signals, dates, opens, highs, lows, closes)
            all_signals.extend(signals)
            all_trades.extend(trades)
            all_stats.append(stats)
            processed += 1
        except Exception:
            failed += 1
    summary = build_summary(all_trades, symbols_total=len(symbols), symbols_processed=processed, symbols_failed=failed, stats_list=all_stats)
    grouped = group_metrics(all_trades)
    write_json_summary(args.json, summary, grouped=grouped, params=vars(args))
    write_trade_csv(args.csv_dir, all_trades)
    write_signal_csv(args.csv_dir, all_signals)
    write_html_report(args.html, summary, all_trades)
    print(f"处理完成: 成功={processed} 失败={failed} 交易数={summary.total_trades} 胜率={summary.win_rate:.2f}% 盈亏={summary.total_pnl:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
