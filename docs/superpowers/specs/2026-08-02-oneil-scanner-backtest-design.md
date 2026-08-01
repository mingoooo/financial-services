# O'Neil Scanner Pattern Backtest Design

Date: 2026-08-02

## Goal

Replace the current handcrafted breakout entry logic in `scripts/backtest_oneil_unified.py` with entry signals generated directly from the live O'Neil scanner pattern detectors.

The new backtest should answer a different question from the current workflow:

- current workflow: which names in a predefined universe break out best?
- new workflow: which scanner-detected O'Neil patterns across the full market perform best when traded with the existing O'Neil portfolio/risk engine?

## Decisions Confirmed

- Reuse scanner detectors directly rather than approximating them in backtest code.
- Use scanner patterns as the signal source for backtest entries.
- Use next-trading-day open execution after a pattern is confirmed on the trigger day's close.
- Include all primary technical base/breakout patterns in the first version:
  - `vcp`
  - `platform-breakout`
  - `52-week-high-breakout`
  - `cup-with-handle`
  - `flat-base`
  - `double-bottom`
- Allow one trade per symbol per day, but keep multi-pattern attribution on that single trade.
- Scan the full market rather than reusing the old static/dynamic candidate universes.
- Build caching into the scanner-backed backtest flow from the first implementation.

## Non-Goals for V1

- No event-driven pattern trading rules in V1 (`event-gap-breakout` stays out).
- No dedicated `high-tight-flag` trading path in V1.
- No change to the existing exit/risk model in V1.
- No intraday execution model.
- No attempt to optimize for maximum throughput before correctness is established.

## High-Level Architecture

Keep the existing unified backtest runner as the canonical engine, but replace the signal generator.

### Existing engine to preserve

`scripts/backtest_oneil_unified.py` continues to own:

- portfolio cash accounting
- open-position tracking
- max positions / max new positions per day
- risk sizing
- stop handling
- trailing stop logic
- `SPY` market filter
- equity curve construction
- result JSON generation

### New signal path

Add a scanner-to-backtest adapter layer:

- `scripts/oneil_scanner/backtest_adapter.py`

Responsibilities:

- prepare per-symbol historical frames for detector consumption
- run the selected scanner detector families on a day-specific frame snapshot
- normalize hits into a backtest-ready signal model
- deduplicate same-symbol same-day entries into a single tradeable signal
- retain secondary pattern attribution metadata

This keeps the boundary clean:

- scanner decides **what pattern exists**
- backtest engine decides **how to trade it**

## Components

### 1. Detector-backed signal adapter

Add a lightweight signal dataclass for the backtest engine, for example:

- `symbol`
- `trigger_date`
- `entry_date`
- `entry_price_ref`
- `initial_stop_price`
- `primary_pattern_family`
- `primary_pattern_type`
- `primary_pattern_variant`
- `secondary_patterns`
- `setup_score`
- `quality_score`
- `rs_score`
- `ranking_score`

The adapter should accept raw `PatternCandidate` outputs from scanner families and convert them into a single signal for a symbol/day.

### 2. Historical detector execution

For each trading day `T`:

- build the market universe for that day from available local price files
- for each symbol, slice data through `T` only
- run scanner detectors against that historical slice
- only accept candidates whose `trigger_date == T`
- convert accepted candidates into backtest signals

This ensures no future leakage.

### 3. Signal cache

Cache historical scanner results on disk so repeated backtests do not rescan the entire market.

Recommended cache layout:

- `.cache/oneil-backtest-scanner-signals/<date>.jsonl`

Each cached record should include at least:

- `date`
- `symbol`
- `primary_pattern_family`
- `primary_pattern_type`
- `primary_pattern_variant`
- `secondary_patterns`
- `breakout_level`
- `stop_reference`
- `setup_score`
- `quality_score`
- `rs_score`
- `ranking_score`

Behavior:

- if cache exists for a day, load it
- if cache is missing, scan and write it
- if user requests refresh, overwrite day cache

### 4. Backtest engine integration

In `scripts/backtest_oneil_unified.py`:

- replace the current `daily_candidates` + `build_entry_signal(...)` path with cached scanner signals
- keep the current execution engine structure intact
- buy at next-day open for signals triggered on the previous close

The engine still handles exits and capital allocation exactly as it does today.

## Shape Coverage in V1

### Included

- `vcp_breakout_family`
  - `vcp`
  - `platform-breakout`
  - `52-week-high-breakout`
- `ibd_base_family`
  - `cup-with-handle`
  - `flat-base`
  - `double-bottom`

### Excluded

- `event_driven_family`
- `momentum_continuation_family` high-tight-flag handling as a tradeable strategy

Reason:

The included shapes all map naturally to breakout-level + stop-reference semantics. The excluded families likely need separate execution assumptions.

## Entry Semantics

### Trigger

A signal is valid only if the scanner detector marks the pattern as triggered on date `T` using data available through the close of `T`.

### Fill rule

Trade entry is executed on the next available trading day `T+1` at the open.

### Entry price reference

The scanner's `breakout_level` is still stored for attribution/reporting, but actual fill uses next-day open.

### Initial stop

Priority order:

1. `PatternCandidate.stop_reference`
2. fallback to existing backtest logic if a detector does not provide a usable stop

## Multi-Pattern Attribution

If the same symbol on the same day is matched by multiple patterns:

- open only one trade
- assign one primary pattern
- preserve additional matches as secondary labels

### Primary pattern selection

Use scanner ranking order as the source of truth.

### Secondary storage

Store all non-primary hits as:

- `secondary_patterns`: list of `family:type[:variant]`

### Reporting rule

- PnL is attributed once, to the primary pattern only
- secondary patterns are counted in a separate overlap/attribution table only

This avoids double-counting returns while preserving scanner richness.

## Ranking

The backtest needs a cross-symbol ranking score for days with more signals than capacity.

Recommended V1 ranking:

- primary sort: scanner-derived `ranking_score`
- fallback sort: `setup_score`, `quality_score`, `rs_score`

Suggested formula:

- `ranking_score = 0.50 * setup_score + 0.30 * quality_score + 0.20 * normalized_rs_score`

This can remain configurable later, but the first version should keep one stable formula.

## Universe Definition

V1 should scan the full local US equity universe available in the LEAN-style daily price store.

Expected behavior:

- derive the active symbol set from local price files
- exclude `SPY` from tradable candidates but retain it for market filtering
- optionally add a basic liquidity guard before detector execution to control runtime

Recommended prefilter before running detectors:

- minimum history length required by detector family
- minimum average dollar volume
- valid OHLCV data only

This is not a return-model filter; it is only a runtime and data-quality guard.

## Exit Rules

V1 keeps existing exit logic unchanged:

- gap stop
- intraday stop
- breakeven promotion after +10%
- trailing stop using ATR
- two consecutive closes below `SMA20`

Reason:

This isolates the experiment to entry-signal substitution.

## Data Flow

### Daily workflow

1. Determine the historical trading calendar from local bars.
2. For each day `T`:
   - load scanner signal cache for `T` if present
   - otherwise scan the full market using data through close `T`
   - write signal cache for `T`
3. On trading day `T+1` open:
   - execute signals triggered on `T`
4. Manage open positions using existing exit engine.
5. Save trades with pattern attribution.

## CLI Changes

Extend `scripts/backtest_oneil_unified.py` rather than creating a new permanent entrypoint.

Recommended additions:

- `--signal-source {legacy,scanner}`
- `--pattern-families vcp_breakout_family,ibd_base_family`
- `--pattern-types ...` (optional subset filter)
- `--scanner-cache-dir <path>`
- `--refresh-scanner-cache`
- `--min-dollar-volume <value>`

Suggested default for the new mode:

- `--signal-source scanner`

once the implementation is stable.

## Output / Reporting Changes

Add pattern-aware fields to each trade record:

- `trigger_date`
- `primary_pattern_family`
- `primary_pattern_type`
- `primary_pattern_variant`
- `secondary_patterns`
- `breakout_level`
- `stop_reference`

Add summary tables to the overview HTML:

- trades by `primary_pattern_type`
- win rate by `primary_pattern_type`
- average return by `primary_pattern_type`
- total PnL by `primary_pattern_type`
- most common secondary overlaps

V1 can be table-only. No extra visualization is required initially.

## Error Handling

V1 should prefer resilience over hard failure.

Rules:

- if one symbol scan fails, record a warning and continue
- if one detector family fails for a symbol/day, continue with other families when safe
- if a day cache is corrupt, delete/rebuild that day only
- if a signal lacks a valid stop, skip that signal unless fallback logic can produce one safely
- if next-day bar is missing, drop the trade and record a warning

Warnings should be included in result JSON metadata.

## Testing Strategy

### Unit tests

Add focused tests for:

- `PatternCandidate -> backtest signal` conversion
- same-symbol same-day multi-pattern collapse into one trade signal
- next-day-open fill semantics
- stop fallback behavior
- cache read/write round-trip

### Integration tests

Add a small fixture-driven backtest test that:

- uses a tiny symbol universe
- exercises at least one `vcp_breakout_family` signal
- exercises at least one `ibd_base_family` signal
- verifies resulting trades include pattern attribution metadata

### Regression tests

Preserve the existing legacy signal path behind `--signal-source legacy` until scanner mode is trusted.

This gives a known baseline and reduces migration risk.

## Migration Plan

### Phase 1

- add scanner adapter
- add day cache
- add scanner signal source behind flag
- preserve legacy mode

### Phase 2

- add pattern attribution to reports
- add pattern summary tables

### Phase 3

- evaluate whether event-driven and high-tight-flag should become separate backtest modes

## Alternatives Considered

### Alternative 1: keep handcrafted backtest rules and only rename them to scanner patterns

Rejected because it creates long-term drift between scanner and backtest semantics.

### Alternative 2: precompute historical signals in a totally separate pipeline first

Useful later, but not ideal as the first implementation because it splits the rollout into two systems too early.

### Alternative 3: replace exits as well as entries in the same change

Rejected for V1 because it would make performance attribution much harder.

## Recommendation

Implement scanner-backed backtest mode inside the existing unified runner with:

- full-market scanning
- daily signal caching
- next-day-open execution
- single trade per symbol/day
- multi-pattern attribution metadata
- unchanged risk/exit engine

This is the narrowest path that still fully satisfies the product goal: using real scanner patterns as the backtest signal source.
