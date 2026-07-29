#!/usr/bin/env python3
from __future__ import annotations

import argparse
from textwrap import dedent
import sys


DEPRECATION_MESSAGE = dedent(
    """
    `scripts/scan_reversals.py` is archived and no longer runs the active reversal scanner.

    Use one of these current entrypoints instead:
    - `scripts/scan_oneil_setups.py`
    - `scan.py`
    - archived reversal README files: `scripts/README.scan_reversals.md` and `scripts/README.backtest_reversals.md`

    No scan, report generation, or output files were produced.
    """
).strip()


def _parse_deprecation_args(argv: list[str] | None = None) -> None:
    """Best-effort consume representative legacy flags without exiting."""

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--symbols")
    parser.add_argument("--preset")
    parser.add_argument("--universe")
    parser.add_argument("--json")
    parser.add_argument("--html")
    parser.add_argument("--include-etfs", action="store_true")
    parser.add_argument("--exclude-etfs", action="store_true")
    parser.add_argument("--etf-groups")
    parser.add_argument("--scan-mode")
    parser.add_argument("--require-fresh-sma-cross-up", action="store_true")
    parser.add_argument("--sma-cross-mode")
    parser.add_argument("--require-rsi-above")
    parser.add_argument("--require-macd-bullish", action="store_true")
    parser.add_argument("--min-last-volume")
    parser.add_argument("--min-market-cap")
    parser.add_argument("--min-price")
    parser.add_argument("--min-avg-volume")
    parser.add_argument("--top-dollar-volume")
    parser.add_argument("--require-confirm-volume", action="store_true")
    parser.add_argument("--no-require-confirm-volume", action="store_true")
    parser.add_argument("--confirm-volume-multiplier")
    parser.add_argument("--limit")
    parser.add_argument("--workers")
    parser.add_argument("--recent-confirm-days")
    parser.add_argument("--side")
    parser.add_argument("--entry-mode")
    parser.add_argument("--stop-mode")
    parser.add_argument("--target-mode")
    parser.add_argument("--scan-retries")
    parser.add_argument("--no-cache", action="store_true")
    try:
        parser.parse_known_args(argv)
    except argparse.ArgumentError:
        pass
    except SystemExit:
        pass


def main(argv: list[str] | None = None) -> int:
    _parse_deprecation_args(argv)
    print(DEPRECATION_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
