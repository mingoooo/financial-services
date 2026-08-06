#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.oneil_scanner.config import ScannerConfig
    from scripts.oneil_scanner.models import STRATEGY_PROFILES
    from scripts.oneil_scanner.runner import run_scan
else:
    from .oneil_scanner.config import ScannerConfig
    from .oneil_scanner.models import STRATEGY_PROFILES
    from .oneil_scanner.runner import run_scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan for O'Neil-style stock setups.")
    parser.add_argument('--universe', default='all-us')
    parser.add_argument('--symbols')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--as-of')
    parser.add_argument('--include-news', action='store_true')
    parser.add_argument('--include-earnings', action='store_true')
    parser.add_argument('--report-name', default='oneil-setups')
    parser.add_argument('--out-dir', default='reports/oneil')
    parser.add_argument('--cache-dir', default='.cache/oneil-scanner')
    parser.add_argument('--period', default='1y')
    parser.add_argument('--interval', default='1d')
    parser.add_argument('--refresh-cache', action='store_true')
    parser.add_argument(
        '--strategy-profile',
        default='oneil',
        choices=STRATEGY_PROFILES,
        help='Strategy profile to run inside the unified scanner.',
    )
    return parser


def parse_symbols(raw_symbols: str | None) -> list[str]:
    if not raw_symbols:
        return []
    return [symbol.strip().upper() for symbol in raw_symbols.split(',') if symbol.strip()]


def build_config(args: argparse.Namespace) -> ScannerConfig:
    return ScannerConfig(
        universe=args.universe,
        symbols=parse_symbols(args.symbols),
        limit=args.limit,
        as_of=args.as_of,
        include_news=args.include_news,
        include_earnings=args.include_earnings,
        report_name=args.report_name,
        out_dir=args.out_dir,
        cache_dir=args.cache_dir,
        period=args.period,
        interval=args.interval,
        refresh_cache=args.refresh_cache,
        strategy_profile=args.strategy_profile,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = build_config(args)
    summary = run_scan(config)
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
