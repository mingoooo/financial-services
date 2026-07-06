from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def fmt_num(x, digits=2):
    return 'n/a' if x is None else f"{x:.{digits}f}"


def fmt_pct(x):
    if x is None:
        return 'n/a'
    if abs(x) < 0.005:
        return 'flat'
    if 0 < abs(x) < 0.01:
        sign = '+' if x > 0 else '-'
        return f"{sign}<0.01%"
    return f"{x:+.2f}%"


def fmt_market_cap(x):
    if x is None:
        return 'n/a'
    abs_x = abs(x)
    if abs_x >= 1_000_000_000_000:
        return f"${x / 1_000_000_000_000:.2f}T"
    if abs_x >= 1_000_000_000:
        return f"${x / 1_000_000_000:.2f}B"
    if abs_x >= 1_000_000:
        return f"${x / 1_000_000:.2f}M"
    return f"${x:,.0f}"


def catalyst_line(g):
    heads = g.get('catalyst_headlines') or []
    return heads[0]['title'] if heads else 'No clean catalyst headline found'


def levels_line(g):
    parts = []
    if g.get('premarket_high') is not None:
        parts.append(f"PMH {fmt_num(g.get('premarket_high'))}")
    if g.get('premarket_low') is not None:
        parts.append(f"PML {fmt_num(g.get('premarket_low'))}")
    if g.get('prior_day_high') is not None:
        parts.append(f"PDH {fmt_num(g.get('prior_day_high'))}")
    elif g.get('hod') is not None:
        parts.append(f"HOD {fmt_num(g.get('hod'))}")
    if g.get('prior_day_low') is not None:
        parts.append(f"PDL {fmt_num(g.get('prior_day_low'))}")
    elif g.get('lod') is not None:
        parts.append(f"LOD {fmt_num(g.get('lod'))}")
    return ' | '.join(parts) if parts else 'live levels unavailable'


def levels_cell(g):
    return levels_line(g).replace(' | ', ' · ')


def day_plan_line(g):
    if g.get('premarket_high') is not None:
        return f"Only interested if price reclaims and holds above PMH {fmt_num(g.get('premarket_high'))}. Do not chase failed moves."
    return "Wait for a clean break and hold above the key premarket trigger. Do not chase failed moves."


def codex_check_line(g):
    checks = []
    if not g.get('catalyst_found'):
        checks.append('catalyst not confirmed')
    if g.get('rvol') is None:
        checks.append('RVOL unavailable')
    if g.get('price') is not None and g.get('prior_day_high') is not None and g.get('price') <= g.get('prior_day_high'):
        checks.append('still below prior high')
    return '; '.join(checks) if checks else 'hard rules passed'


def conviction_badge(g):
    if g.get('day_eligible') and g.get('catalyst_found'):
        return '🟢 HIGH'
    if g.get('day_eligible') or g.get('swing_eligible'):
        return '🟡 MED'
    return '🔴 LOW/skip'


def trend_context(g):
    parts = []
    price = g.get('price')
    sma = g.get('sma_200')
    if price is not None and sma is not None:
        parts.append('above 200d SMA' if price > sma else 'below 200d SMA')
    if g.get('prior_day_high') is not None:
        parts.append(f"prior high {fmt_num(g.get('prior_day_high'))}")
    if g.get('rvol') is not None:
        parts.append(f"RVOL {fmt_num(g.get('rvol'))}")
    return ', '.join(parts) if parts else 'trend context limited'


def build_report(packet: dict) -> str:
    now_et = datetime.now(ZoneInfo('America/New_York'))
    date_line = now_et.strftime('%Y-%m-%d %I:%M %p ET')
    market_snapshot = packet.get('market_snapshot', [])
    econ = packet.get('econ_calendar', {})
    gappers = packet.get('gappers', [])
    snapshot_map = {item['name']: item for item in market_snapshot if item.get('name')}

    summary_tape = []
    for key in ['S&P 500', 'Nasdaq', 'VIX', 'US 10Y', 'Dollar (DXY)']:
        item = snapshot_map.get(key)
        if item:
            summary_tape.append(f"{key} {fmt_pct(item.get('change_pct'))}")
    summary_tape_line = '; '.join(summary_tape) if summary_tape else 'broad tape snapshot is patchy'

    day_rows = []
    for g in gappers:
        if g.get('day_eligible'):
            day_rows.append(
                f"| {g.get('ticker','')} | {catalyst_line(g)} | {levels_line(g)} | {day_plan_line(g)} | {codex_check_line(g)} | {conviction_badge(g)} |"
                .replace(levels_line(g), levels_cell(g), 1)
            )
    if not day_rows:
        day_rows.append('| None | No clean day setup passed the hard rules in this packet | n/a | Stand aside and wait for cleaner confirmation | Packet only. | 🔴 LOW/skip |')

    swing_rows = []
    for g in gappers:
        if g.get('swing_eligible'):
            swing_rows.append(f"| {g.get('ticker','')} | {catalyst_line(g)} | {trend_context(g)} | Starter idea only. Swing entries and exits are still not finalized. | Packet only. | 🟡 MED |")
    if not swing_rows:
        swing_rows.append('| None | No swing name passed the hard rules in this packet | context limited | No starter idea today from the hard screen | Packet only. | 🔴 LOW/skip |')

    pre_gappers = []
    for g in gappers:
        pre_gappers.append(
            f"### {g.get('ticker','')} | {g.get('company_name') or 'Company unknown'}\n"
            f"- Full catalyst headline: {catalyst_line(g)}\n"
            f"- Price: {fmt_num(g.get('price'))} | Gap: {fmt_pct(g.get('gap_pct'))} | Market cap: {fmt_market_cap(g.get('market_cap'))}\n"
            f"- Live levels: {levels_line(g)}\n"
            f"- Flags: day_eligible={g.get('day_eligible')} | swing_eligible={g.get('swing_eligible')} | catalyst_found={g.get('catalyst_found')}\n"
        )

    market_trends = [
        f"- Tape backdrop: {summary_tape_line}.",
        f"- Candidate source: {packet.get('candidate_source') or 'unknown'}.",
        f"- Hard-screened gappers in packet: {len(gappers)}.",
        "- This is still raw data first. Quality judgment is limited because no separate view files were supplied.",
    ]

    tech_signals = [
        "- Trend Join names need a clean push through premarket high and then a fresh high of day.",
        "- If a gapper cannot stay above prior-day high, the setup gets a lot less interesting fast.",
        "- RVOL here is a keyless stand-in based on full-day relative volume, not a true premarket feed.",
    ]

    rates_bits = []
    for key in ['US 10Y', 'US 3M', 'Dollar (DXY)']:
        item = snapshot_map.get(key)
        if item:
            rates_bits.append(f"{key} {fmt_pct(item.get('change_pct'))}")
    rates_line = '; '.join(rates_bits) if rates_bits else 'rates snapshot unavailable'

    if econ.get('today'):
        econ_today_lines = [f"- {e.get('time_et')}: {e.get('title')} | Forecast: {e.get('forecast') or 'n/a'} | Previous: {e.get('previous') or 'n/a'}" for e in econ.get('today', [])]
    elif econ.get('notes') and any('unavailable' in n.lower() for n in econ.get('notes', [])):
        econ_today_lines = ["- Econ feed unavailable.", f"- Rates snapshot: {rates_line}."]
    else:
        econ_today_lines = ["- Light data day on the calendar.", f"- Rates snapshot: {rates_line}."]
    if econ_today_lines[-1] != f"- Rates snapshot: {rates_line}.":
        econ_today_lines.append(f"- Rates snapshot: {rates_line}.")

    coming = []
    if econ.get('tomorrow'):
        for e in econ.get('tomorrow', []):
            coming.append(f"- {e.get('time_et')}: {e.get('title')}")
    else:
        coming.append('- No high-impact USD event listed for tomorrow in the cached/live feed.')
    notable_earnings = [f"{g.get('ticker')}: {g.get('next_earnings_date')}" for g in gappers if g.get('next_earnings_date')]
    if notable_earnings:
        coming.append(f"- Notable earnings dates seen in gappers: {', '.join(notable_earnings[:8])}")
    else:
        coming.append('- Notable earnings dates from gappers were limited or unavailable.')

    skips = []
    failed_day = [g['ticker'] for g in gappers if not g.get('day_eligible')]
    failed_swing = [g['ticker'] for g in gappers if not g.get('swing_eligible')]
    missing_cat = [g['ticker'] for g in gappers if not g.get('catalyst_found')]
    if failed_day:
        skips.append(f"- Failed day screen: {', '.join(failed_day[:8])}. Usually missing RVOL, prior-high reclaim, or clean structure.")
    if failed_swing:
        skips.append(f"- Failed swing screen: {', '.join(failed_swing[:8])}. Usually missing real catalyst, 200d context, or valid open rules.")
    if missing_cat:
        skips.append(f"- Weak catalyst match: {', '.join(missing_cat[:8])}. The headline match filter stayed strict on purpose.")
    if not skips:
        skips.append('- No obvious trap list was generated from the current packet.')

    return f'''# 🧠 AI PREMARKET REPORT — Humbled Trader

### {date_line} · Claude + Codex (GPT-5.5), independent passes

### Watchlists built by the rules: Day = Trend Join Long · Swing = gap-up + real catalyst

> Disclaimer: deterministic criteria decide membership, both AIs judge quality later, price, gap, and live levels here use extended-hours data when available, intraday RVOL here has a keyless caveat, and none of this is financial advice.

## Summary

- Tape backdrop: {summary_tape_line}.
- The catch we are watching: big gap names are there, but clean catalyst matching is still thin on some names.
- Two-brain verdict: packet-based editor draft only. No separate Claude or Codex view files were provided.

## 📊 Pre-Market Gappers

{chr(10).join(pre_gappers)}
## ☀️ Day Trading Watchlist

| Ticker | Catalyst | Levels (live) | Plan (Trend Join) | 🤖 Codex | Conv. |
|---|---|---|---|---|---|
{chr(10).join(day_rows)}

## 📈 Notable Swing Watchlist

| Ticker | Catalyst (headline) | Trend context | Idea | 🤖 Codex | Conv. |
|---|---|---|---|---|---|
{chr(10).join(swing_rows)}

## 📉 Market Trends of the Day

{chr(10).join(market_trends)}

## 📊 Technical Signals for Today

{chr(10).join(tech_signals)}

## 💰 Economic Data, Rates & the Fed

{chr(10).join(econ_today_lines)}

## 📅 Coming Up

{chr(10).join(coming)}

## 🚫 Skips & Traps

{chr(10).join(skips)}

---

## 🤖 Where the two brains landed

- Agreement: unavailable because no separate Claude or Codex view files were provided.
- Rules vs discretion: no separate discretion layer was provided, so this report sticks to deterministic packet facts only.
- Claude's sharp catch the other missed: unavailable.
- Codex's sharp catch the other missed: unavailable.
- trade where they agree; where they disagree, stand down or size down; never average.
'''


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: python scripts/build_premarket_report.py <packet.json> <REPORT.md>', file=sys.stderr)
        return 2
    packet = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    report = build_report(packet)
    Path(sys.argv[2]).write_text(report, encoding='utf-8')
    print(sys.argv[2])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
