from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from reversal_lib.models import Signal, TradeRecord


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_trade_csv(csv_dir: str | None, trades: list[TradeRecord]) -> None:
    if not csv_dir:
        return
    _write_csv(Path(csv_dir) / 'trades.csv', [asdict(item) for item in trades])


def write_signal_csv(csv_dir: str | None, signals: list[Signal]) -> None:
    if not csv_dir:
        return
    _write_csv(Path(csv_dir) / 'signals.csv', [asdict(item) for item in signals])


__all__ = ['write_trade_csv', 'write_signal_csv']
