# Backtest Workflow

This repository includes a local research workflow for O'Neil-style equity backtests using local daily price data and local fundamentals snapshots.

## Main Entry Points

- Unified backtest runner:
  - `/Users/huangsm43/Documents/mingo/code/financial-services/scripts/backtest_oneil_unified.py`
- Unified overview HTML generator:
  - `/Users/huangsm43/Documents/mingo/code/financial-services/scripts/render_backtest_overview_html.py`

## Universe Modes

The unified backtest runner supports three universe modes:

- `static`
  - Uses `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/oneil_candidates_latest.csv`
  - Best current raw return in the repository workflow
- `dynamic-growth`
  - Rolling fundamentals-driven candidate universe
  - Growth-oriented dynamic ranking
- `dynamic-balanced`
  - Rolling fundamentals-driven candidate universe
  - More conservative technical reranking for lower drawdown

## Example Commands

### Static mode

```bash
python3 /Users/huangsm43/Documents/mingo/code/financial-services/scripts/backtest_oneil_unified.py \
  --start 2025-06-30 \
  --end 2026-06-29 \
  --universe-mode static \
  --json-out /tmp/oneil_mode_static.json
```

### Dynamic growth mode

```bash
python3 /Users/huangsm43/Documents/mingo/code/financial-services/scripts/backtest_oneil_unified.py \
  --start 2025-06-30 \
  --end 2026-06-29 \
  --universe-mode dynamic-growth \
  --json-out /tmp/oneil_mode_dynamic_growth.json
```

### Dynamic balanced mode

```bash
python3 /Users/huangsm43/Documents/mingo/code/financial-services/scripts/backtest_oneil_unified.py \
  --start 2025-06-30 \
  --end 2026-06-29 \
  --universe-mode dynamic-balanced \
  --json-out /tmp/oneil_mode_dynamic_balanced.json
```

## Generate Overview HTML

```bash
/Users/huangsm43/Documents/mingo/code/financial-services/.venv/bin/python \
  /Users/huangsm43/Documents/mingo/code/financial-services/scripts/render_backtest_overview_html.py \
  --result-json /tmp/oneil_mode_static.json \
  --result-json /tmp/oneil_mode_dynamic_growth.json \
  --result-json /tmp/oneil_mode_dynamic_balanced.json \
  --output-html /Users/huangsm43/Documents/mingo/code/financial-services/reports/oneil_backtest_overview.html
```

The overview HTML currently includes:

- Per-mode summary cards
- Candlestick charts
- Entry and exit markers
- Volume bars
- `SMA10`, `SMA20`, `SMA50`, `SMA100`, `SMA200`
- Per-symbol trade tables

## Data Dependencies

### Local price data

- Directory:
  - `/Users/huangsm43/Documents/mingo/code/backtest/data/equity/usa/daily`
- Format:
  - LEAN-style daily zip files converted from Yahoo data

### Static candidate file

- `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/oneil_candidates_latest.csv`

### Fundamentals dataset

- `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.csv`

## Current Strategy Assumptions

The unified backtester currently models:

- Event-driven daily portfolio simulation
- Real cash deduction on entry
- Concurrent positions
- `SPY` entry filter
- Daily stop handling with gap-aware stop logic
- Basic slippage and per-trade commission
- End-of-day mark-to-market equity curve

This is substantially more realistic than the earlier precomputed-trade portfolio approximation.

## Recommended Usage

- Use `static` when you want the strongest current strategy result
- Use `dynamic-growth` when you want the best current rolling fundamentals-based mode
- Use `dynamic-balanced` when you prefer lower drawdown over higher return

## Repository Check

Use the project virtualenv for repository checks:

```bash
/Users/huangsm43/Documents/mingo/code/financial-services/.venv/bin/python \
  /Users/huangsm43/Documents/mingo/code/financial-services/scripts/check.py
```

This is preferred over system `python3` because the virtualenv already includes `pyyaml`.

## Notes for Future Work

- Keep extending `backtest_oneil_unified.py` instead of creating one-off parallel backtest runners
- Keep HTML reporting consolidated in `render_backtest_overview_html.py`
- Prefer comparing strategy changes under the same event-driven engine and the same cost model


## Unified Runner Structure

The unified backtest runner is organized around a single event-driven portfolio engine plus small helper functions.

### Core Helpers

Current helper layout in `scripts/backtest_oneil_unified.py` includes:

- `build_bars_by_symbol(...)`
  - Loads local price history for a symbol set
- `build_group_counts(...)`
  - Counts active positions by risk bucket / theme bucket
- `mark_to_market_equity(...)`
  - Computes daily equity from cash plus open positions
- `load_daily_candidates(...)`
  - Dispatches to `static` or dynamic universe construction
- `build_entry_signal(...)`
  - Builds a single-day breakout entry signal for one symbol
- `rank_signals(...)`
  - Applies per-mode ranking rules before opening positions

### Backtest Engine Responsibilities

`run_backtest(...)` is the canonical event-driven engine and is responsible for:

- building the candidate universe for the chosen mode
- loading local market data
- applying the market entry filter
- updating open positions day by day
- executing exits before new entries
- sizing and opening new positions
- tracking daily equity and summary metrics

### Maintenance Rule

When modifying the unified runner:

- prefer extracting a tiny helper instead of rewriting large blocks
- after each structural refactor, rerun the `static`, `dynamic-growth`, and `dynamic-balanced` regression checks
- do not change strategy behavior during structure-only refactors


## Current Reference Baselines

Use the following 1-year results as the current regression reference for structure-only refactors of `scripts/backtest_oneil_unified.py`.

### `static`

- executed trades: `18`
- total return: `21.24%`
- max drawdown: `21.89%`
- profit factor: `4.258`

### `dynamic-growth`

- executed trades: `16`
- total return: `18.09%`
- max drawdown: `20.46%`
- profit factor: `5.314`

### `dynamic-balanced`

- executed trades: `16`
- total return: `12.56%`
- max drawdown: `14.38%`
- profit factor: `2.778`

When doing a structure-only refactor, these values should remain unchanged.
