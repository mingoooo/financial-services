from __future__ import annotations

import json
import os
import sys
from html import escape
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


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
def build_daily_chart_svg(ticker: str) -> str | None:
    try:
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period='1y', interval='1d', auto_adjust=False, prepost=False)
        if hist is None or hist.empty:
            return None
        chart = hist[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().copy()
        if chart.empty:
            return None
        chart['MA20'] = chart['Close'].rolling(20, min_periods=1).mean()
        chart['MA50'] = chart['Close'].rolling(50, min_periods=1).mean()
        chart['MA200'] = chart['Close'].rolling(200, min_periods=1).mean()
        recent = chart.tail(90).copy()
        if recent.empty:
            return None

        width = 760
        height = 360
        margin_left = 14
        margin_right = 14
        margin_top = 18
        margin_bottom = 16
        price_height = 236
        volume_gap = 12
        volume_height = 64
        usable_width = width - margin_left - margin_right
        candle_step = usable_width / max(len(recent), 1)
        candle_width = max(2.0, min(6.0, candle_step * 0.68))

        highs = recent['High'].astype(float)
        lows = recent['Low'].astype(float)
        price_min = float(lows.min())
        price_max = float(highs.max())
        price_pad = max((price_max - price_min) * 0.06, price_max * 0.01, 0.5)
        price_min -= price_pad
        price_max += price_pad
        volume_max = max(float(recent['Volume'].astype(float).max()), 1.0)

        def scaled(value: float, lower: float, upper: float, span: float) -> float:
            if abs(upper - lower) < 1e-9:
                return span / 2.0
            return (value - lower) / (upper - lower) * span

        svg_parts: list[str] = [
            '<div class="chart-card">',
            f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(ticker)} 1Y daily candlestick chart">',
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" rx="12" ry="12"/>',
            f'<line x1="{margin_left}" y1="{margin_top + price_height}" x2="{width - margin_right}" y2="{margin_top + price_height}" stroke="#d0d7de" stroke-width="1"/>',
        ]

        for step in range(4):
            grid_y = margin_top + step * (price_height / 3.0)
            svg_parts.append(
                f'<line x1="{margin_left}" y1="{grid_y:.2f}" x2="{width - margin_right}" y2="{grid_y:.2f}" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="3 4"/>'
            )

        ma_specs = [('MA20', '#7c3aed'), ('MA50', '#ea580c'), ('MA200', '#0891b2')]
        for ma_name, color in ma_specs:
            points: list[str] = []
            for index, (_, row) in enumerate(recent.iterrows()):
                ma_value = row.get(ma_name)
                if ma_value is None or pd.isna(ma_value):
                    continue
                center_x = margin_left + index * candle_step + candle_step / 2.0
                ma_y = margin_top + (price_height - scaled(float(ma_value), price_min, price_max, price_height))
                points.append(f'{center_x:.2f},{ma_y:.2f}')
            if len(points) >= 2:
                svg_parts.append(
                    f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{" ".join(points)}"/>'
                )

        try:
            ext = ticker_obj.history(period='2d', interval='1m', auto_adjust=False, prepost=True)
            ext_close = ext['Close'].dropna() if ext is not None and not ext.empty else pd.Series(dtype=float)
            if not ext_close.empty:
                latest_ext = float(ext_close.iloc[-1])
                latest_y = margin_top + (price_height - scaled(latest_ext, price_min, price_max, price_height))
                svg_parts.append(
                    f'<line x1="{margin_left}" y1="{latest_y:.2f}" x2="{width - margin_right}" y2="{latest_y:.2f}" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="5 4"/>'
                )
                svg_parts.append(
                    f'<text x="{width - margin_right - 4}" y="{max(latest_y - 4, margin_top + 10):.2f}" font-size="11" text-anchor="end" fill="#2563eb">Last {latest_ext:.2f}</text>'
                )
        except Exception:
            pass

        volume_top = margin_top + price_height + volume_gap
        label_indices = sorted({0, len(recent) // 3, (len(recent) * 2) // 3, len(recent) - 1})
        for index, (_, row) in enumerate(recent.iterrows()):
            open_price = float(row['Open'])
            high_price = float(row['High'])
            low_price = float(row['Low'])
            close_price = float(row['Close'])
            volume = float(row['Volume'])
            center_x = margin_left + index * candle_step + candle_step / 2.0
            high_y = margin_top + (price_height - scaled(high_price, price_min, price_max, price_height))
            low_y = margin_top + (price_height - scaled(low_price, price_min, price_max, price_height))
            open_y = margin_top + (price_height - scaled(open_price, price_min, price_max, price_height))
            close_y = margin_top + (price_height - scaled(close_price, price_min, price_max, price_height))
            body_top = min(open_y, close_y)
            body_height = max(abs(close_y - open_y), 1.4)
            color = '#16a34a' if close_price >= open_price else '#dc2626'
            volume_scaled = volume / volume_max * volume_height
            volume_y = volume_top + (volume_height - volume_scaled)
            svg_parts.append(f'<line x1="{center_x:.2f}" y1="{high_y:.2f}" x2="{center_x:.2f}" y2="{low_y:.2f}" stroke="{color}" stroke-width="1"/>')
            svg_parts.append(f'<rect x="{center_x - candle_width / 2.0:.2f}" y="{body_top:.2f}" width="{candle_width:.2f}" height="{body_height:.2f}" fill="{color}" rx="1" ry="1"/>')
            svg_parts.append(f'<rect x="{center_x - candle_width / 2.0:.2f}" y="{volume_y:.2f}" width="{candle_width:.2f}" height="{max(volume_scaled, 1.0):.2f}" fill="{color}" opacity="0.30" rx="1" ry="1"/>')
            if index in label_indices:
                label = pd.Timestamp(recent.index[index]).strftime('%Y-%m')
                svg_parts.append(f'<text x="{center_x:.2f}" y="{height - 2}" font-size="10" text-anchor="middle" fill="#6b7280">{label}</text>')

        latest_close = float(recent.iloc[-1]['Close'])
        latest_volume = float(recent.iloc[-1]['Volume']) / 1_000_000.0
        svg_parts.append(f'<text x="{margin_left}" y="14" font-size="12" fill="#111827">{escape(ticker)} · 1Y Daily</text>')
        svg_parts.append(f'<text x="{width - margin_right}" y="14" font-size="12" text-anchor="end" fill="#111827">{latest_close:.2f}</text>')
        svg_parts.append(f'<text x="{margin_left}" y="{margin_top + price_height + volume_gap - 2}" font-size="10" fill="#6b7280">Volume</text>')
        svg_parts.append(f'<text x="{width - margin_right}" y="{margin_top + price_height + volume_gap - 2}" font-size="10" text-anchor="end" fill="#6b7280">Vol {latest_volume:.1f}M</text>')
        svg_parts.append('<text x="14" y="348" font-size="10" fill="#7c3aed">MA20</text>')
        svg_parts.append('<text x="54" y="348" font-size="10" fill="#ea580c">MA50</text>')
        svg_parts.append('<text x="96" y="348" font-size="10" fill="#0891b2">MA200</text>')
        svg_parts.append('</svg>')
        svg_parts.append('</div>')
        return ''.join(svg_parts)
    except Exception:
        return None


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


def extended_volume_line(g):
    if g.get('premarket_volume') is not None:
        return f"PM Vol {fmt_num(g.get('premarket_volume'), 0)}"
    return 'extended-hours volume unavailable'


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
    warnings = packet.get('warnings', [])
    snapshot_map = {item['name']: item for item in market_snapshot if item.get('name')}

    summary_tape = []
    for key in ['S&P 500', 'Nasdaq', 'VIX', 'US 10Y', 'Dollar (DXY)']:
        item = snapshot_map.get(key)
        if item:
            summary_tape.append(f"{key} {fmt_pct(item.get('change_pct'))}")
    summary_tape_line = '; '.join(summary_tape) if summary_tape else 'broad tape snapshot is patchy'
    warning_lines = [f"- Warning: {w}" for w in warnings]

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
        ticker = g.get('ticker', '')
        chart_md = ''
        if ticker:
            chart_html = build_daily_chart_svg(ticker)
            if chart_html:
                chart_md = f"\n{chart_html}\n"
        pre_gappers.append(
            f"### {ticker} | {g.get('company_name') or 'Company unknown'}\n"
            f"- Full catalyst headline: {catalyst_line(g)}\n"
            f"- Price: {fmt_num(g.get('price'))} | Gap: {fmt_pct(g.get('gap_pct'))} | Market cap: {fmt_market_cap(g.get('market_cap'))}\n"
            f"- Live levels: {levels_line(g)}\n"
            f"- Extended-hours volume: {extended_volume_line(g)}\n"
            f"- Flags: day_eligible={g.get('day_eligible')} | swing_eligible={g.get('swing_eligible')} | catalyst_found={g.get('catalyst_found')}\n"
            f"{chart_md}"
        )

    market_trends = [
        f"- Tape backdrop: {summary_tape_line}.",
        f"- Candidate source: {packet.get('candidate_source') or 'unknown'}.",
        f"- Hard-screened gappers in packet: {len(gappers)}.",
        "- This is still raw data first. Quality judgment is limited because no separate view files were supplied.",
    ]

    tech_signals = [
        "- Overnight and premarket action are combined into one premarket view for simplicity.",
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

### {date_line} · Packet-based report generated by Codex

### Watchlists built by the rules: Day = Trend Join Long · Swing = gap-up + real catalyst

> Disclaimer: deterministic criteria decide membership, both AIs judge quality later, price, gap, and live levels here use extended-hours data when available, intraday RVOL here has a keyless caveat, and none of this is financial advice.

## Summary

- Tape backdrop: {summary_tape_line}.
- The catch we are watching: big gap names are there, but clean catalyst matching is still thin on some names.
- Report mode: packet-based editor draft only. No separate Claude or Codex analyst views were provided.

{'## ⚠️ Data Warnings\n\n' + chr(10).join(warning_lines) if warning_lines else ''}

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

## 🤖 Report Method

- This report is generated from the packet and rule-based transforms only.
- No separate Claude analyst memo or Codex analyst memo was provided for comparison.
- Where live data is incomplete, the report may degrade to fallback names or empty watchlists.
- Use the packet facts first; treat the commentary layer as formatting, not independent research.
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
