---
name: minervini-sepa-trading
description: Apply Mark Minervini's SEPA-style growth-stock trading process for liquid equities. Combines trend-template screening, volatility contraction pattern (VCP) recognition, earnings-and-sales confirmation, precise breakout entries, progressive position sizing, and highly disciplined sell rules. Use when evaluating whether a stock is truly price-ready, grading a breakout setup, planning entry/stop/add levels, reviewing post-earnings leadership, or translating Minervini-style momentum rules into an actionable trade plan. Triggers on "Minervini", "SEPA", "VCP", "trend template", "volatility contraction", "stage 2 uptrend", "price-ready", "buy pivot", "sell into strength", or "how would Mark Minervini trade this?".
---

# Minervini SEPA Trading

Use this skill to turn Minervini-style discretionary momentum ideas into a repeatable decision process. Focus on asymmetry: buy only when the stock is fundamentally strong, technically compressed, and operating in a supportive market regime; then risk little if wrong and press only when proven right.

## Core Process

Follow this sequence strictly:
1. Assess the overall market.
2. Screen for leadership and liquidity.
3. Check whether the stock passes the trend template.
4. Confirm the stock is price-ready, not merely fundamentally sound.
5. Identify the setup type, preferably a VCP or similarly tight consolidation.
6. Define the exact entry trigger, stop, and initial size.
7. Add only after the trade works.
8. Manage exits with hard defensive rules and opportunistic offensive sells.

If any upstream step fails, do not force the trade. Explain what is missing.

## Inputs To Gather

Collect or infer:
- Ticker and company
- Trading horizon: swing, position, intermediate trend
- Market context: confirmed uptrend, under pressure, correction, or range
- Position risk budget: max loss per trade, max position size, portfolio heat
- Liquidity constraints: average daily dollar volume, slippage tolerance
- Whether earnings are upcoming, just reported, or not a catalyst
- Whether the user wants classic Minervini execution or a looser momentum interpretation

If the user provides no constraints, assume liquid U.S. common stocks, intermediate-term swing/position trading, and risk-first execution.

## Market First

Do not evaluate single-name longs in isolation.

Classify the tape before discussing setup quality:
- **Supportive market**: breakouts are following through, leadership is expanding, indexes are above key moving averages.
- **Mixed market**: only take A/A+ setups, reduce size, and expect more failures.
- **Hostile market**: avoid forcing longs, preserve capital, and focus on watchlists.

Default principle: even elite setups underperform in weak market conditions.

## Leadership Screen

Prefer stocks with:
- Strong recent earnings and sales growth, ideally accelerating
- Positive price reactions to earnings or guidance
- Relative strength near highs versus the broad market
- Industry-group leadership rather than second-tier peers
- Sufficient liquidity for clean execution
- Institutional demand visible in price/volume behavior

Disqualify or downgrade stocks that are:
- Illiquid, highly erratic, or excessively news-driven
- Far below prior highs with no repair evidence
- Showing repeated breakout failures
- Fundamentally improving but technically not ready

## Trend Template

A stock is generally eligible only when most of the following are true:
- Price is above the 150-day and 200-day moving averages.
- The 150-day moving average is above the 200-day moving average.
- The 200-day moving average is rising or no longer declining materially.
- Price is above the 50-day moving average.
- Price is within reach of 52-week highs rather than deeply discounted.
- Relative strength is strong and preferably improving into new-high territory.

Treat the template as a gate, not a guarantee. Passing the template means the stock is in the right neighborhood; it still needs a valid setup.

For a concise checklist and grading rubric, read `references/trend-template.md`.

## Price-Ready Versus Fundamentally Sound

A recurring Minervini distinction is that a company may be good while the stock is not yet buyable.

Call a stock **price-ready** only when:
- Prior advance exists, proving sponsorship can move the name
- Base depth is reasonable for the context
- Volatility is contracting rather than expanding
- Pullbacks show diminishing selling pressure
- Tight closes appear near the pivot area
- Breakout timing aligns with market conditions

Avoid recommendations that rely only on valuation, story, or raw fundamentals.

## Setup Taxonomy

Name the setup explicitly before giving a buy point.

Preferred setup families:
- **VCP**: successive contractions in both price spread and turnover; best when the final contraction is very tight near resistance.
- **Tight consolidation / shelf**: short, orderly pause after an advance with volume drying up.
- **Power play / high-tight-flag variant**: explosive move followed by shallow digestion; use stricter selectivity because many traders misclassify weak patterns as power plays.
- **Post-earnings continuation**: strong gap or thrust that holds and tightens instead of failing.
- **Secondary entry**: re-breakout or tight pullback after an earlier successful move.

For detailed pattern language, read `references/setup-patterns.md`.

## Entry Rules

Always specify:
- Exact trigger level or trigger condition
- What volume confirmation should look like
- What would invalidate the setup immediately
- Whether the stock is still buyable or already extended

Default entry principles:
- Buy as the stock proves itself through resistance; do not anticipate without evidence.
- Prefer entries as close as possible to the pivot to keep risk tight.
- Do not chase obvious extension unless the user explicitly accepts momentum-gap tactics.
- Require tighter confirmation when the market is mixed.

## Stops And Position Sizing

Build size from risk, not conviction.

For each trade, provide:
- Entry
- Stop
- Risk per share
- Initial position size from the user’s risk budget
- Maximum planned total size if the trade proves itself

Default principles:
- Keep initial risk small enough that a normal stop-out is emotionally and financially trivial.
- Use smaller size for looser patterns, thinner liquidity, earnings-adjacent entries, or weak market conditions.
- If the appropriate stop is too far away, pass on the trade or reduce size materially.

## Add Rules

Add only after confirmation.

Good adds occur when:
- The initial entry is profitable
- The stock forms another tight area above cost
- Volume and relative strength remain supportive
- The general market still confirms risk-on behavior

Bad adds occur when:
- The stock is below cost
- You are averaging down
- The setup is getting looser
- The market backdrop has deteriorated

Default principle: never add to a loser.

## Sell Rules

Separate defensive exits from offensive profit management.

### Defensive sells
- Honor the stop without negotiation.
- Exit failed breakouts quickly.
- Reduce or exit when heavy-volume reversals show clear distribution.
- Tighten posture when the market regime weakens and leadership starts failing.

### Offensive sells
- Trim or sell into strength when a stock becomes climactic, extremely extended, or shows exhaustion after a fast move.
- Use partial profits when that reduces emotional pressure while preserving upside participation.
- Exit when trend character changes meaningfully after a substantial run.

When in doubt, prefer smaller losses, faster feedback, and capital preservation.

## Post-Trade Review

After a trade, review:
- Did the stock truly fit the trend template?
- Was the setup actually tight, or did you label a loose pattern as VCP?
- Did volume confirm at the right moments?
- Did you buy at the pivot, before it, or too extended above it?
- Did you size correctly relative to stop distance and market regime?
- Did you violate a sell rule, average down, or let a small loss become large?

Use post-analysis to refine execution quality, not to rationalize broken discipline.

## Output Format

When recommending a trade, structure the answer with:
- Market regime assessment
- Leadership verdict
- Trend-template pass/fail summary
- Setup classification
- Exact entry / stop / add / trim plan
- Main failure risks
- Final verdict: buy now, watch, wait for confirmation, or avoid

If data are incomplete, say what is missing and what would change the decision.

## References

Read only what is needed:
- `references/trend-template.md` for the screening checklist and pass/fail heuristics
- `references/setup-patterns.md` for VCP, power-play, and breakout pattern language
- `references/sell-rules.md` for defensive and offensive exit playbooks
- `references/book-notes.md` for condensed synthesis from the two Minervini books
