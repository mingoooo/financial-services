#!/usr/bin/env python3
from __future__ import annotations

import argparse
from textwrap import dedent
import sys


DEPRECATION_MESSAGE = dedent(
    """
    `scripts/notify_telegram_premarket.py` is deprecated and no longer sends the active premarket notification.

    Use the consolidated notifier instead:
    - `scripts/notify_telegram_market_report.py --family premarket --report-path <REPORT.md>`
    - `scripts/notify_telegram_market_report.py --family oneil --report-path <live-full-latest.json>`

    No Telegram message was sent.
    """
).strip()


def _parse_deprecation_args(argv: list[str] | None = None) -> None:
    """Best-effort consume the legacy positional interface without exiting."""

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument('report_path', nargs='?')
    parser.add_argument('pages_url', nargs='?')
    parser.add_argument('run_label', nargs='?')
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


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
