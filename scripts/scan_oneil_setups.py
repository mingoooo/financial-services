#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC

from oneil_scanner.config import ScanConfig
from oneil_scanner.models import ScanSummary
from oneil_scanner.report import write_report_bundle


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
    return parser


def parse_symbols(raw_symbols: str | None) -> list[str]:
    if not raw_symbols:
        return []
    return [symbol.strip().upper() for symbol in raw_symbols.split(',') if symbol.strip()]


def build_config(args: argparse.Namespace) -> ScanConfig:
    return ScanConfig(
        universe=args.universe,
        symbols=parse_symbols(args.symbols),
        limit=args.limit,
        as_of=args.as_of,
        include_news=args.include_news,
        include_earnings=args.include_earnings,
        report_name=args.report_name,
        out_dir=args.out_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = build_config(args)
    summary = ScanSummary.empty(
        run_timestamp=datetime.now(UTC).isoformat(timespec='seconds'),
        universe=config.universe,
        symbols=config.symbols,
        limit=config.limit,
        as_of=config.as_of,
        include_news=config.include_news,
        include_earnings=config.include_earnings,
        report_name=config.report_name,
        out_dir=config.out_dir,
    )
    write_report_bundle(config, summary)
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
