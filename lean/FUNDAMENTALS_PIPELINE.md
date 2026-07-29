# Fundamentals Pipeline

## Overview

This pipeline builds a local quarterly fundamentals dataset and derives a simplified O'Neil candidate universe snapshot for LEAN backtests.

## Files

- Dataset builder: `scripts/build_growth_fundamentals_dataset.py`
- Candidate builder: `scripts/build_oneil_candidate_list.py`
- Standardized dataset: `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/us_growth_quarterly.csv`
- Latest candidate universe: `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/oneil_candidates_latest.csv`
- Historical snapshots: `/Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/snapshots/`

## Raw Input Schema

Required raw CSV columns:
- `symbol`
- `report_date`
- `fiscal_period`
- `revenue`
- `revenue_yoy`
- `eps`
- `eps_yoy`

## Build Dataset

```bash
python3 scripts/build_growth_fundamentals_dataset.py \
  --input /path/to/raw_growth_fundamentals.csv \
  --source-name my-source
```

## Build Candidate Snapshot

```bash
python3 scripts/build_oneil_candidate_list.py \
  --as-of-date 2026-06-30
```

## Screening Rules

Candidate inclusion requires:
- `revenue_yoy > 20`
- `eps_yoy > 25`
- `revenue_accel > 0` or `eps_accel > 0`

## Intended LEAN Integration

LEAN should read `oneil_candidates_latest.csv` or a dated snapshot and restrict technical breakout evaluation to `included=true` symbols.


## Free Data Sources

### Recommended practical path

1. **SimFin**: easiest free standardized quarterly fundamentals source for MVP import.
2. **SEC EDGAR Company Facts**: best free primary-source fallback / validator, but requires more normalization.
3. **Alpha Vantage / FMP free tiers**: useful for prototyping or spot fills, but free quotas and coverage constraints make them weaker as the primary pipeline source.

### SimFin importer

Raw importer:
- `scripts/import_simfin_growth_fundamentals.py`

Example:

```bash
python3 scripts/import_simfin_growth_fundamentals.py   --symbols AAPL,NVDA,PLTR,MSFT   --output /Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_simfin_growth_fundamentals.csv

python3 scripts/build_growth_fundamentals_dataset.py   --input /Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_simfin_growth_fundamentals.csv   --source-name simfin

python3 scripts/build_oneil_candidate_list.py   --as-of-date 2026-06-30
```

Notes:
- SimFin importer currently uses quarterly income statement data.
- `revenue_yoy` is computed from same fiscal quarter one year earlier.
- `eps` is approximated as `net_income / diluted_shares` when available, then `eps_yoy` is computed the same way.
- For broader coverage and better accounting controls, add SEC validation as phase 2.


## SEC importer

Free primary-source importer:
- `scripts/import_sec_companyfacts_growth.py`

Example:

```bash
python3 scripts/import_sec_companyfacts_growth.py   --symbols AAPL,NVDA,PLTR,MSFT   --user-agent 'your-name research your-email@example.com'

python3 scripts/build_growth_fundamentals_dataset.py   --input /Users/huangsm43/Documents/mingo/code/backtest/data/custom/fundamentals/raw_sec_growth_fundamentals.csv   --source-name sec-companyfacts

python3 scripts/build_oneil_candidate_list.py   --as-of-date 2026-06-30
```

Notes:
- SEC requests should send a descriptive `User-Agent` with contact info.
- Current importer is an MVP focused on quarterly revenue and EPS growth extraction.
- It already works for symbols like `PLTR`, `MSFT`, and partially `NVDA` in live validation.
- Some issuers such as `AAPL` still need additional period-normalization logic because SEC facts may mix cumulative and single-quarter disclosures across `fp` and `frame` fields.
