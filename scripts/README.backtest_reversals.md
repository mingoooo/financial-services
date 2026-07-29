# Reversal Backtest Archive

> [!WARNING]
> **ARCHIVED STATUS**
> `scripts/backtest_reversals.py` is retained only as archival research support for the deprecated reversal stack.

## Status

This document exists only to support reproduction of older reversal studies.

For current research, use:

- `scripts/backtest_oneil_unified.py` for supported O'Neil backtests.
- `scripts/scan_oneil_setups.py` for O'Neil / breakout scanning.
- `scan.py`, `scripts/build_premarket_report.py`, and `render_report.py` for the premarket event-driven chain.

Do not use `scripts/backtest_reversals.py` as the mainline starting point for new work.

## Scope

`scripts/backtest_reversals.py` remains available for archival comparison against historical reversal results. It should not be treated as the recommended path for ongoing strategy development.

## Archival reference

The commands below are preserved only so older reversal research can be reproduced when necessary.

### Historical example: baseline backtest

```bash
python3 scripts/backtest_reversals.py \
  --range 5y \
  --json /tmp/reversal-baseline.json \
  --csv-dir /tmp/reversal-baseline-csv \
  --html /tmp/reversal-baseline.html
```

### Historical example: symbol subset

```bash
python3 scripts/backtest_reversals.py \
  --symbols AAPL,NVDA,TSLA \
  --range 2y \
  --json /tmp/reversal-subset.json
```

### Historical example: experiment runner

```bash
python3 scripts/run_reversal_experiments.py
python3 scripts/run_reversal_experiments.py --experiments archived_baseline,archived_relaxed
```

## Notes for historical reproduction

- Older reversal notes may describe parameters, presets, and outputs that were tuned for the deprecated reversal stack.
- Preserve those runs only when you need comparability with prior research artifacts.
- For maintained research paths, follow the O'Neil and premarket documentation instead.
