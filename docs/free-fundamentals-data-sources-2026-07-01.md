# Free Fundamentals Data Sources for LEAN / Local O'Neil Pipeline

Date: 2026-07-01

## Executive Summary

For a **free, practical, and production-leaning** fundamentals pipeline for US equities:

1. **SEC EDGAR Company Facts** should be treated as the core durable free source.
2. **SimFin** is still attractive for fast standardization, but in our validation it currently requires a valid API key and is not a zero-friction anonymous source.
3. **Alpha Vantage / FMP free tiers** are useful as convenience APIs, not ideal as the primary historical fundamentals backbone.

## Recommended Source Ranking

### 1) SEC EDGAR Company Facts — Best long-term free source

Pros:
- Official primary source from the SEC.
- Free public JSON APIs.
- Includes company facts / XBRL disclosures that can support revenue, net income, diluted EPS, and shares outstanding derivations.
- Suitable for building a reproducible internal pipeline with no third-party pricing dependency.

Cons:
- Requires normalization of tags across issuers.
- Some metrics need fallback tag logic.
- Engineering effort is higher than turnkey vendor feeds.

Best use:
- Core source of truth.
- Validation layer for any third-party standardized feed.

## 2) SimFin — Best MVP standardization path if API key available

Pros:
- Easier standardized schema for quarterly statements.
- Faster path to a usable cross-sectional dataset.
- Good fit for bootstrapping O'Neil-style quarterly growth screens.

Cons:
- Current API access is not anonymous in our test path.
- Operational dependency on external vendor policy.

Current validation status:
- Our importer implementation works structurally, but a live request returned HTTP 401 without a valid key on 2026-07-01.

Best use:
- Fast importer when an API key is available.
- Supplemental standardized layer above SEC raw facts.

## 3) Alpha Vantage / FMP free tier — Good for prototyping, weaker for primary pipeline

Pros:
- Easy REST usage.
- Fast to test.

Cons:
- Free quotas / throttling.
- Weaker breadth and historical robustness for a full SP500 quarterly pipeline.
- More policy risk as a long-term backbone.

Best use:
- Spot fills.
- Small-universe experiments.
- Debugging / cross-checks.

## Recommended Architecture

### Phase 1
- Use local price data for LEAN backtests.
- Build fundamentals candidate universe externally.
- Feed candidate CSV into C# LEAN algorithm.

### Phase 2
- Ingest **SEC Company Facts** into a raw quarterly facts layer.
- Standardize into:
  - `symbol`
  - `report_date`
  - `fiscal_period`
  - `revenue`
  - `revenue_yoy`
  - `eps`
  - `eps_yoy`
- Reuse existing builders:
  - `scripts/build_growth_fundamentals_dataset.py`
  - `scripts/build_oneil_candidate_list.py`

### Phase 3
- Optionally add SimFin as a convenience source when a valid key is available.
- Use SEC to validate or backfill discrepancies.

## Implementation Status in This Repo

Implemented:
- `scripts/build_growth_fundamentals_dataset.py`
- `scripts/build_oneil_candidate_list.py`
- `scripts/import_simfin_growth_fundamentals.py`
- `lean/FUNDAMENTALS_PIPELINE.md`

Pending next best implementation:
- `scripts/import_sec_companyfacts_growth.py`

## Practical Recommendation

If the goal is **free + stable +可落地**, the next implementation should be:
- build a **SEC Company Facts importer** first;
- keep SimFin importer as an optional accelerator when a key is available.
