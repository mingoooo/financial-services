# O'Neil Unified Scanner Design

## Summary

Build a new unified O'Neil-style stock scanner and report pipeline for US equities that reuses the repository's existing `yfinance` and `vcp_lib` foundations, while expanding coverage beyond VCP to include breakout, IBD base, momentum continuation, and event-driven setups.

The first version should be complete enough to scan and report all requested setup families in one pass, with a strict and consistent standard for candidate structure, scoring, de-duplication, catalyst tagging, and HTML/CSV/JSON output.

## Goals

- Add a unified scanner for US equities using the existing repository data flow where practical.
- Reuse current `scripts/vcp_lib/` capabilities rather than replacing them.
- Cover the following setup types in one report:
  - `VCP`
  - `52-week high breakout`
  - `platform/consolidation breakout`
  - `high tight flag`
  - `trend template + RS`
  - `earnings/news event-driven breakout`
  - `cup-with-handle`
  - `flat base`
  - `double bottom`
- Produce one unified report with shared ranking, shared candidate schema, and shared explanation fields.
- Classify catalysts as `earnings`, `news`, `mixed`, or `unknown`.
- Keep the design compatible with future integration into the O'Neil research/backtest workflow.

## Non-Goals

- Do not implement multi-market support in the first version.
- Do not make `IBKR` or any non-current data source a required dependency.
- Do not couple the new scanner directly into `scripts/backtest_oneil_unified.py` yet.
- Do not attempt intraday, minute-bar, or real-time streaming detection in the first version.
- Do not aim for perfect institutional-grade event data coverage in v1.
- Do not replace the existing VCP scan entrypoint unless later migration becomes clearly beneficial.

## Context

The repository already contains several useful building blocks:

- `scripts/vcp_lib/`
  - Existing VCP-oriented modules for data loading, trend template logic, scoring, charts, and reporting.
- `scripts/scan_vcp_stocks.py`
  - Existing VCP scan entrypoint.
- `scan.py`
  - Existing `yfinance`, RSS/news, and market metadata gathering patterns.
- `scripts/backtest_oneil_unified.py`
  - Canonical O'Neil-style backtest entrypoint for this repo.
- `WATCHLIST_CRITERIA.md`
  - Existing rule source pattern that prefers strict scanner rules before subjective analysis.

The new scanner should align with these patterns instead of introducing a disconnected one-off workflow.

## Alternatives Considered

### Approach A: Expand `vcp_lib` into the entire multi-pattern framework

This would maximize reuse but would force `vcp_lib` to evolve from a focused VCP library into a much broader multi-pattern engine. That increases coupling and makes the current VCP code harder to reason about.

### Approach B: Keep `vcp_lib` focused and add a new `oneil_scanner` orchestration layer

This approach preserves the current VCP boundary while adding a new top-level scanner framework that calls multiple pattern-family detectors, including VCP. It introduces one more layer, but it provides cleaner ownership and lower migration risk.

### Approach C: Build the scanner directly around `backtest_oneil_unified.py`

This would align tightly with the later research flow, but it would make the first version harder to ship as a clean standalone scanner-plus-report product.

## Recommended Approach

Use **Approach B**.

Keep `scripts/vcp_lib/` as a reusable library for VCP and shared O'Neil-style primitives, then add a new scanner package that orchestrates:

- shared data loading
- shared preprocessing
- shared filtering
- multiple detector families
- unified candidate merging
- unified scoring
- unified report generation

This keeps the current VCP implementation stable while creating the right boundary for broader setup coverage.

## Proposed Structure

Add a new package:

- `scripts/oneil_scanner/`
  - `__init__.py`
  - `models.py`
  - `config.py`
  - `data.py`
  - `preprocess.py`
  - `filters.py`
  - `event_classifier.py`
  - `scoring.py`
  - `report.py`
  - `runner.py`
  - `detectors/`
    - `__init__.py`
    - `vcp_breakout_family.py`
    - `ibd_base_family.py`
    - `momentum_continuation_family.py`
    - `event_driven_family.py`

Add a new entrypoint:

- `scripts/scan_oneil_setups.py`

Keep existing modules in place:

- `scripts/vcp_lib/` remains the home of reusable VCP/trend-template functionality.
- `scripts/scan_vcp_stocks.py` remains available for focused VCP-only work.

## Architecture

### Top-Level Flow

The new scanner should work as a staged batch pipeline:

1. Build the target universe.
2. Load daily OHLCV and metadata.
3. Compute shared technical fields.
4. Load earnings/news evidence.
5. Build a standardized symbol context.
6. Run detector families.
7. Merge and de-duplicate candidates.
8. Score and rank candidates.
9. Render HTML/CSV/JSON outputs.

### Separation of Responsibilities

- `data.py`
  - Fetches raw market data, metadata, and event inputs.
- `preprocess.py`
  - Computes shared technical features once.
- `filters.py`
  - Applies global pre-filters and trend-template style filters.
- `detectors/*`
  - Detect setup-family-specific geometry or trigger conditions.
- `event_classifier.py`
  - Assigns catalyst evidence and catalyst labels.
- `scoring.py`
  - Converts detector outputs into comparable quality and setup scores.
- `report.py`
  - Builds final JSON/CSV/HTML outputs.
- `runner.py`
  - Orchestrates the full scan.

This keeps detector code focused on pattern logic, while shared concerns live in one place.

## Data Sources

### Primary Market Data

Use the repository's existing `yfinance` flow as the default daily data source.

First-version expectations:

- Market: US equities only.
- Primary timeframe: daily bars.
- History window: roughly 1-2 years per symbol, enough to support trend-template, 52-week levels, bases, and prior-uptrend checks.

### Derived Technical Fields

Shared preprocessing should compute at least:

- `SMA10`, `SMA20`, `SMA50`, `SMA150`, `SMA200`
- 52-week high and low
- ATR or ATR-like range metric
- average volume and average dollar volume
- gap percent
- breakout volume ratio
- distance to 52-week high
- RS proxy / relative strength score

These should be computed once per symbol and reused by all detector families.

### Metadata

Use the repository's existing metadata access patterns where practical, including `fast_info` / `info` fields when available.

Useful fields include:

- market cap
- sector / industry
- price
- average dollar volume
- float / shares when available

The design should treat metadata as helpful but partially optional, since `yfinance` fields can be incomplete.

### Event Data

Event data should be pulled from existing repository-compatible sources, not invented independently by each detector.

Required event classes:

- earnings events
- news events

The first version should support both price action and catalyst evidence. Event-driven setups should not be classified as earnings/news setups on price action alone.

### Catalyst Labels

Candidates should expose:

- `catalyst_type = earnings`
- `catalyst_type = news`
- `catalyst_type = mixed`
- `catalyst_type = unknown`

And also distinguish between:

- `event_detected`
- `price_pattern_triggered`

This prevents ordinary gap behavior from being mislabeled as a confirmed earnings or news setup.

## Universe and Pre-Filters

The first version targets US equities and should follow a staged filtering model.

### Global Eligibility Filters

These should eliminate symbols that are obviously unsuitable before detector logic runs:

- non-empty OHLCV history
- price above minimum threshold
- liquidity above minimum threshold
- enough bars for the relevant detector family
- exclusion of obvious non-target instruments when identifiable

### Trend-Template Layer

`trend template + RS` should not be a standalone final detector. Instead, it should act as both:

- a global quality filter
- a shared scoring input

Candidate records should expose:

- `trend_template_pass`
- `rs_score`
- `distance_to_52w_high`
- optional `stage2_like_pass`

This lets the scanner use trend quality consistently across all pattern families.

## Detector Families

### 1. `vcp_breakout_family`

Covers:

- `VCP`
- `platform/consolidation breakout`
- `52-week high breakout`

Shared logic themes:

- strong prior trend
- proximity to highs
- contraction / tightening
- volume contraction before breakout
- volume confirmation on breakout

This family should reuse as much of `vcp_lib` as practical.

### 2. `ibd_base_family`

Covers:

- `cup-with-handle`
- `flat base`
- `double bottom`

Shared logic themes:

- valid base width and depth
- pivot identification
- handle or midpoint validation where relevant
- breakout confirmation above pivot
- base quality scoring

### 3. `momentum_continuation_family`

Covers:

- `high tight flag`
- strong continuation breakout setups

Shared logic themes:

- steep prior advance
- short and shallow consolidation
- resumed upward expansion
- relative volume and extension checks

### 4. `event_driven_family`

Covers:

- `earnings gap up`
- `news gap breakout`
- `follow-through after catalyst`

Shared logic themes:

- catalyst evidence
- meaningful gap / trigger day behavior
- no immediate full failure
- follow-through in subsequent bars

This family should have the strictest catalyst classification requirements because it is the least defensible if reduced to OHLCV alone.

## Unified Candidate Model

Define one standard candidate structure, for example via `PatternCandidate`.

Every candidate should include at least:

- `symbol`
- `pattern_family`
- `pattern_type`
- `pattern_variant`
- `trigger_date`
- `breakout_level`
- `current_price`
- `entry_zone_low`
- `entry_zone_high`
- `stop_reference`
- `trend_template_pass`
- `rs_score`
- `distance_to_52w_high`
- `volume_confirmation`
- `catalyst_type`
- `catalyst_summary`
- `quality_score`
- `setup_score`
- `report_rank`
- `secondary_signals`
- `notes`

Detector-specific fields can still exist, but the report layer should depend on the shared schema rather than detector internals.

## De-Duplication and Primary Setup Selection

The same symbol may trigger multiple setup families in the same trigger window.

The scanner should therefore:

- keep one `primary` setup per symbol per trigger window
- preserve other triggered setups as `secondary_signals`

Selection order should consider:

1. `quality_score`
2. family priority
3. catalyst confidence
4. timing / recency

Suggested family priority when scores are otherwise close:

1. `event_driven_family`
2. `ibd_base_family`
3. `vcp_breakout_family`
4. `momentum_continuation_family`

This should remain configurable rather than hard-coded forever.

## Scoring

Use two main score layers, not one monolithic score.

### `quality_score`

Measures structural quality of the setup itself.

Examples by family:

- VCP: contraction quality, volume dry-up, pivot clarity
- cup-with-handle: cup depth, handle position, handle shape, rim quality
- double bottom: symmetry, neckline quality, breakout quality
- high tight flag: prior advance, flag shallowness, re-expansion quality
- event-driven: gap quality, hold behavior, follow-through, event evidence strength

### `setup_score`

Measures actionability.

Examples:

- liquidity
- distance from pivot / breakout level
- recency of trigger
- volume confirmation
- catalyst clarity
- extension risk

### Final Rank

Use a derived `report_rank` based on weighted inputs such as:

- `quality_score`
- `setup_score`
- catalyst confidence
- RS strength

The goal is a consistent report sort order without losing family-specific nuance.

## Report Outputs

The scanner should write to `reports/` and follow the repository's current output style.

### Default Files

- `reports/oneil_scan_latest.json`
- `reports/oneil_scan_latest.csv`
- `reports/oneil_scan_latest.html`

If a custom report name is passed, produce named variants in the same directory.

### JSON

Should contain:

- run metadata
- config
- universe metadata
- grouped summaries
- all candidates with full shared schema

### CSV

Should contain a flattened candidate table suitable for manual review.

Priority columns:

- symbol
- primary pattern
- secondary signals
- catalyst type
- quality score
- setup score
- report rank
- trigger date
- breakout level
- RS score
- trend-template pass

### HTML

The HTML report is the main human-facing artifact.

Recommended structure:

- summary header
- top ranked setups
- event-driven setups
- IBD base setups
- VCP / breakout setups
- momentum continuation setups
- optional low-quality or rejected summary section

Each row or card should include a short explanation line, for example:

- `Cup-with-handle breakout near pivot, RS strong, earnings catalyst confirmed`
- `VCP-style contraction near 52-week highs, no confirmed catalyst`
- `High tight flag continuation after earnings gap-up with follow-through`

## CLI

Add a new entrypoint:

- `scripts/scan_oneil_setups.py`

Recommended first-version arguments:

- `--universe`
- `--symbols`
- `--limit`
- `--as-of`
- `--include-news`
- `--include-earnings`
- `--report-name`
- `--out-dir`

This is enough to support practical use without over-designing the interface.

## Error Handling

The scanner should degrade safely.

- Missing OHLCV for one symbol should not abort the whole run.
- Missing metadata should reduce richness, not necessarily block detection.
- Missing event evidence should prevent strict event-family classification, not crash the scanner.
- Each symbol should record status metadata such as skipped / failed / insufficient_data where useful.

The report should expose enough run metadata to explain reduced coverage.

## Testing and Validation

Testing should start with targeted unit and fixture coverage around the new package.

### Unit Coverage

Add focused tests for:

- candidate schema creation
- trend-template / RS shared filters
- de-duplication rules
- catalyst classification behavior
- report ranking logic

### Detector Coverage

Use small deterministic fixtures to test representative setup cases for:

- VCP-like contraction
- 52-week high breakout
- cup-with-handle
- flat base
- double bottom
- high tight flag
- event-driven gap classification

### Report Coverage

Add tests that verify:

- JSON/CSV/HTML outputs are created
- candidate grouping works as expected
- top-ranked candidates appear in stable order for known fixture input

## Rollout Strategy

Implementation should proceed in a way that keeps the system internally coherent even if some family logic requires tuning.

Recommended implementation order:

1. shared candidate model, config, and runner
2. shared data + preprocessing + trend-template/RS layer
3. initial report scaffolding
4. VCP/breakout family integration using `vcp_lib`
5. IBD base family
6. momentum continuation family
7. event-driven family
8. de-duplication and unified ranking refinement
9. final HTML explanation polish

## Risks

### Event Data Quality

Catalyst classification will be the noisiest area in v1. This is acceptable if the scanner is explicit about evidence strength and avoids overclaiming.

### Pattern Overlap

Many requested patterns overlap structurally. Without a strong de-duplication layer, the report will become noisy and repetitive.

### Incomplete `yfinance` Metadata

Some metadata fields may be missing or inconsistent. The design should avoid making them hard blockers unless necessary.

### Scope Pressure

This is intentionally broad for a first version. The design therefore relies on strong shared abstractions to prevent the implementation from fragmenting.

## Acceptance Criteria

The design is successful when the repository can support a scanner that:

- runs against US equities using the existing data foundation
- detects all requested setup families in one end-to-end pass
- outputs one unified JSON/CSV/HTML report
- uses one shared candidate schema
- de-duplicates overlapping pattern hits into primary + secondary signals
- classifies catalyst type using both price behavior and event evidence
- preserves `vcp_lib` as a reusable focused library instead of collapsing all logic into it

## Future Integration

After the scanner is stable, the natural next step is to connect it to the canonical O'Neil research workflow.

Most likely future path:

- keep `scripts/scan_oneil_setups.py` as the scanning/reporting entrypoint
- allow `scripts/backtest_oneil_unified.py` to consume scanner outputs or scanner config in a later phase

That future integration should happen only after the scanning layer is stable enough to act as a reliable upstream candidate generator.
