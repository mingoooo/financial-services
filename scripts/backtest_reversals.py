#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import time

import yaml

from reversal_lib.report import write_html_report, write_json_summary, write_signal_csv, write_trade_csv
from reversal_lib.presets import apply_strategy_preset
from reversal_lib.models import UniverseRequest
from reversal_lib.pipeline.backtest_pipeline import run_backtest
from reversal_lib.strategy.spec import StrategySpec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回测反转形态策略")
    parser.add_argument("--config")
    parser.add_argument("--config-preset")
    parser.add_argument("--symbols")
    parser.add_argument("--preset", choices=["main", "high_quality"])
    parser.add_argument("--entry-mode", choices=["next_open", "confirm_close"], default="confirm_close")
    parser.add_argument("--stop-mode", choices=["pattern_anchor", "confirm_low", "tighter_of_pattern_and_confirm_low"], default="confirm_low")
    parser.add_argument("--target-mode", choices=["nearest_resistance", "r_multiple"], default="nearest_resistance")
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
    parser.add_argument("--min-last-volume", type=float, default=0)
    parser.add_argument("--min-avg-volume", type=float, default=300000)
    parser.add_argument("--min-price", type=float, default=5.0)
    parser.add_argument("--min-market-cap", type=float, default=2000000000)
    parser.add_argument("--exclude-etfs", dest="include_etfs", action="store_false")
    parser.add_argument("--etf-groups", default="core,theme,manual_exceptions")
    parser.add_argument("--include-etfs", action="store_true", default=True)
    parser.add_argument("--require-confirm-volume", action="store_true", default=True)
    parser.add_argument("--no-require-confirm-volume", dest="require_confirm_volume", action="store_false")
    parser.add_argument("--confirm-volume-multiplier", type=float, default=1.5)
    parser.add_argument("--min-r-multiple", type=float, default=1.5)
    parser.add_argument("--require-trend-alignment", action="store_true")
    parser.add_argument("--require-location-alignment", action="store_true")
    parser.add_argument("--location-tolerance-ratio", type=float, default=0.02)
    parser.add_argument("--allowed-patterns")
    parser.add_argument("--require-fresh-sma-cross-up", action="store_true")
    parser.add_argument("--sma-cross-mode", choices=["either", "20", "50"], default="either")
    parser.add_argument("--workers", type=int)
    return parser.parse_args()




def _build_strategy_spec(args: argparse.Namespace, allowed_patterns: set[str] | None) -> StrategySpec:
    return StrategySpec(
        side=args.side,
        min_r_multiple=args.min_r_multiple,
        require_confirm_volume=args.require_confirm_volume,
        confirm_volume_multiplier=args.confirm_volume_multiplier,
        require_fresh_sma_cross_up=args.require_fresh_sma_cross_up,
        sma_cross_mode=args.sma_cross_mode,
        require_standard_uptrend=args.require_trend_alignment,
        require_macd_bullish=args.require_macd_bullish,
        require_rsi_above=args.require_rsi_above,
        require_above_sma200=args.require_above_sma200,
        entry_mode=args.entry_mode,
        stop_mode=args.stop_mode,
        target_mode=args.target_mode,
        indicator_config={
            "require_trend_alignment": args.require_trend_alignment,
            "require_location_alignment": args.require_location_alignment,
            "location_tolerance_ratio": args.location_tolerance_ratio,
            "allowed_patterns": sorted(allowed_patterns) if allowed_patterns is not None else None,
        },
    )

def load_config_overrides(path_str: str | None, preset_name: str | None) -> dict:
    if not path_str:
        return {}
    payload = yaml.safe_load(Path(path_str).read_text(encoding='utf-8')) or {}
    defaults = dict(payload.get('defaults') or {})
    presets = payload.get('presets') or {}
    selected = dict(presets.get(preset_name, {})) if preset_name else {}
    defaults.update(selected)
    return defaults


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
    started_at = time.perf_counter()
    args = parse_args()
    config_options = load_config_overrides(args.config, args.config_preset)
    for key, value in config_options.items():
        if getattr(args, key, None) in (None, False):
            setattr(args, key, value)
    preset_options = apply_strategy_preset(vars(args), args.preset)
    for key, value in preset_options.items():
        setattr(args, key, value)
    allowed_patterns = {item.strip() for item in args.allowed_patterns.split("|") if item.strip()} if args.allowed_patterns else None
    request = UniverseRequest(universe=args.universe, limit=args.max_symbols or None, symbols=[item.strip().upper() for item in args.symbols.split(',')] if args.symbols else [])
    spec = _build_strategy_spec(args, allowed_patterns)
    processing_started_at = time.perf_counter()
    result = run_backtest(spec, request, args.range)
    processing_elapsed = time.perf_counter() - processing_started_at

    grouped = group_metrics(result.trades)
    write_json_summary(args.json, result.summary, grouped=grouped, params=vars(args))
    write_trade_csv(args.csv_dir, result.trades)
    write_signal_csv(args.csv_dir, result.signals)
    write_html_report(args.html, result.summary, result.trades)
    total_elapsed = time.perf_counter() - started_at
    print(f"处理完成: 成功={result.summary.symbols_processed} 失败={result.summary.symbols_failed} 交易数={result.summary.total_trades} 胜率={result.summary.win_rate:.2f}% 盈亏={result.summary.total_pnl:.2f}")
    print(f"benchmark: symbols={result.summary.symbols_total} core_processing_sec={processing_elapsed:.3f} total_sec={total_elapsed:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
