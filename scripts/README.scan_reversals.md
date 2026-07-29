# Reversal Scanner Archive

> [!WARNING]
> **ARCHIVED WORKFLOW**
> `scripts/scan_reversals.py` is no longer part of the current local research stack. It is retained only for research reproducibility, historical comparison, and reference against older reversal studies.

## Status

Reversal scanning is not an active research path in this repository anymore.

For current work, use:

- `scripts/scan_oneil_setups.py` for the O'Neil / breakout family.
- `scripts/backtest_oneil_unified.py` for O'Neil backtests.
- `scan.py`, `scripts/build_premarket_report.py`, and `render_report.py` for the premarket event-driven report chain.

Keep this document only when you need to understand or reproduce prior reversal outputs.

## Scope

`scripts/scan_reversals.py` remains in-tree as archival support for deprecated reversal research. New users should start with the O'Neil or premarket paths listed above rather than building on the reversal scanner.

## Archival reference

The examples below are preserved strictly as historical reference for past reversal experiments.

### Historical example: default run

```bash
python3 scripts/scan_reversals.py
```

### Historical example: bearish side

```bash
python3 scripts/scan_reversals.py --side bearish
```

### Historical example: custom universe

```bash
python3 scripts/scan_reversals.py --universe sp500
```

### Historical example: explicit symbols

```bash
python3 scripts/scan_reversals.py --symbols AAPL,NVDA,SPY,TSLA
```

### Historical example: HTML output

```bash
python3 scripts/scan_reversals.py --html /tmp/reversal_report.html
```

### Historical example: disable cache

```bash
python3 scripts/scan_reversals.py --no-cache
```

## Notes for historical reproduction

- Expect behavior, outputs, and surrounding automation references in older notes to reflect the deprecated reversal stack.
- Do not treat this scanner as the default entrypoint for new research.
- If you need a maintained scanner today, use the active O'Neil or premarket documentation instead.
