from __future__ import annotations

import csv
import json
import math
from collections import OrderedDict
from html import escape
from pathlib import Path

import pandas as pd

try:
    from jinja2 import Template
except ModuleNotFoundError as exc:
    if exc.name != 'jinja2':
        raise
    Template = None

from .config import ScannerConfig
from .data import build_scan_window_key
from .models import GroupedCandidateSummary, PatternCandidate, ScanRunSummary
from scripts.vcp_lib.data_sources import cache_path, load_json_cache, normalize_daily_ohlcv_frame, serializable_records_to_frame

CSV_COLUMNS = [
    'symbol',
    'pattern_family',
    'pattern_type',
    'pattern_variant',
    'trigger_date',
    'breakout_level',
    'entry_zone_low',
    'entry_zone_high',
    'stop_reference',
    'trend_template_pass',
    'rs_score',
    'distance_to_52w_high',
    'volume_confirmation',
    'catalyst_type',
    'catalyst_confidence',
    'catalyst_evidence_count',
    'catalyst_summary',
    'quality_score',
    'setup_score',
    'report_rank',
    'secondary_signals',
    'notes',
]

REPORT_SECTIONS: tuple[tuple[str, str, str, str | None], ...] = (
    ('top_setups', 'Top Setups', '重点候选', None),
    ('event_driven_setups', 'Event-Driven Setups', '事件驱动形态', 'event_driven_family'),
    ('ibd_base_setups', 'IBD Base Setups', 'IBD 底部形态', 'ibd_base_family'),
    ('vcp_breakout_setups', 'VCP/Breakout Setups', 'VCP / 突破形态', 'vcp_breakout_family'),
    ('momentum_continuation_setups', 'Momentum Continuation Setups', '动量延续形态', 'momentum_continuation_family'),
)

_PATTERN_TYPE_ZH = {
    'event-follow-through': '事件跟涨延续',
    'earnings-gap-breakout': '财报跳空突破',
    'news-gap-breakout': '新闻跳空突破',
    'event-gap-breakout': '事件跳空突破',
    'cup-with-handle': '杯柄形态',
    'flat-base': '平底整理',
    'double-bottom': '双底形态',
    'vcp': 'VCP 波动收缩形态',
    'platform-breakout': '平台突破',
    '52-week-high-breakout': '52 周新高突破',
    'high-tight-flag': '高 tight flag',
    'continuation-breakout': '延续突破',
}

_FAMILY_ZH = {
    'event_driven_family': '事件驱动',
    'ibd_base_family': 'IBD 底部',
    'vcp_breakout_family': 'VCP / 突破',
    'momentum_continuation_family': '动量延续',
}

_CATALYST_TYPE_ZH = {
    'technical_breakout': '技术突破',
    'earnings': '财报催化',
    'news': '新闻催化',
    'mixed': '混合催化',
    'unknown': '未知催化',
}

_VOLUME_CONFIRMATION_ZH = {
    'confirmed': '放量确认',
    'watch': '待观察',
    'dry-up': '缩量',
}

_COLUMN_LABELS = {
    'report_rank': ('Rank', '排名'),
    'symbol': ('Symbol', '代码'),
    'chart': ('Chart', '图表'),
    'pattern_type': ('Pattern', '形态'),
    'trigger_date': ('Trigger Date', '触发日期'),
    'setup_score': ('Setup Score', '形态分'),
    'quality_score': ('Quality Score', '质量分'),
    'volume_confirmation': ('Volume', '量能'),
    'catalyst_type': ('Catalyst', '催化'),
    'explanation': ('Explanation', '说明'),
}


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _unique_symbols(candidates: list[PatternCandidate]) -> list[str]:
    return list(OrderedDict.fromkeys(candidate.symbol for candidate in candidates))


def _section_candidates(candidates: list[PatternCandidate], *, top_limit: int = 10) -> OrderedDict[str, list[PatternCandidate]]:
    sections: OrderedDict[str, list[PatternCandidate]] = OrderedDict()
    for section_key, _label_en, _label_zh, family in REPORT_SECTIONS:
        if family is None:
            sections[section_key] = candidates[:top_limit]
            continue
        sections[section_key] = [candidate for candidate in candidates if candidate.pattern_family == family]
    return sections


def build_grouped_candidate_summaries(candidates: list[PatternCandidate], *, top_limit: int = 10) -> list[GroupedCandidateSummary]:
    sections = _section_candidates(candidates, top_limit=top_limit)
    grouped: list[GroupedCandidateSummary] = []
    for section_key, label_en, _label_zh, family in REPORT_SECTIONS:
        section_candidates = sections[section_key]
        candidate_count = len(candidates) if family is None else len(section_candidates)
        grouped.append(
            GroupedCandidateSummary(
                group_key=section_key,
                label=label_en,
                candidate_count=candidate_count,
                symbols=_unique_symbols(section_candidates),
            )
        )
    return grouped


def _translate_pattern_type(pattern_type: str) -> str:
    return _PATTERN_TYPE_ZH.get(pattern_type, pattern_type)


def _translate_catalyst_type(catalyst_type: str) -> str:
    return _CATALYST_TYPE_ZH.get(catalyst_type, catalyst_type)


def _translate_volume_confirmation(volume_confirmation: str) -> str:
    return _VOLUME_CONFIRMATION_ZH.get(volume_confirmation, volume_confirmation)


def _candidate_explanation(candidate: PatternCandidate) -> str:
    setup_metadata = candidate.setup_metadata()
    parts = [
        f"{candidate.pattern_type} on {candidate.trigger_date or 'latest bar'}",
        f"quality {candidate.quality_score or 0:.1f}",
        f"setup {candidate.setup_score or 0:.1f}",
        f"volume {candidate.volume_confirmation}",
    ]
    if candidate.rs_score is not None:
        parts.append(f"RS {candidate.rs_score:.1f}")
    if candidate.distance_to_52w_high is not None:
        parts.append(f"{candidate.distance_to_52w_high:.1%} from 52-week high")
    if candidate.catalyst_type not in {'unknown', 'technical_breakout'}:
        parts.append(f"catalyst {candidate.catalyst_type}: {candidate.catalyst_summary or ''}")
    elif candidate.catalyst_summary:
        parts.append(candidate.catalyst_summary)
    parts.extend(_qullamaggie_explanation_bits(candidate, setup_metadata=setup_metadata))
    return '; '.join(parts)


def _candidate_explanation_zh(candidate: PatternCandidate) -> str:
    setup_metadata = candidate.setup_metadata()
    parts = [
        f"{_translate_pattern_type(candidate.pattern_type)}，触发日 {candidate.trigger_date or '最新一根 K 线'}",
        f"质量分 {candidate.quality_score or 0:.1f}",
        f"形态分 {candidate.setup_score or 0:.1f}",
        f"量能状态：{_translate_volume_confirmation(candidate.volume_confirmation)}",
    ]
    if candidate.rs_score is not None:
        parts.append(f"RS {candidate.rs_score:.1f}")
    if candidate.distance_to_52w_high is not None:
        parts.append(f"距离 52 周高点 {candidate.distance_to_52w_high:.1%}")
    if candidate.catalyst_type not in {'unknown', 'technical_breakout'}:
        parts.append(f"催化：{_translate_catalyst_type(candidate.catalyst_type)}；{candidate.catalyst_summary or ''}")
    elif candidate.catalyst_summary:
        parts.append(candidate.catalyst_summary.replace('Technical breakout without separate event catalyst requirement', '技术突破，无需额外事件催化').replace('No usable catalyst evidence aligned with the price move', '未发现与价格动作匹配的有效催化'))
    parts.extend(_qullamaggie_explanation_bits_zh(candidate, setup_metadata=setup_metadata))
    return '；'.join(parts)


def _qullamaggie_explanation_bits(candidate: PatternCandidate, *, setup_metadata: dict[str, object]) -> list[str]:
    if not candidate.pattern_family.startswith('qullamaggie_'):
        return []
    parts: list[str] = []
    if candidate.pattern_family == 'qullamaggie_ep_family':
        gap_pct = setup_metadata.get('gap_pct')
        if isinstance(gap_pct, (int, float)):
            parts.append(f'gap {float(gap_pct):.1%}')
        opening_drive = setup_metadata.get('opening_drive_volume_ratio')
        if isinstance(opening_drive, (int, float)):
            parts.append(f'opening drive {float(opening_drive):.1f}x')
        entry_trigger_type = setup_metadata.get('entry_trigger_type')
        if entry_trigger_type:
            parts.append(f'entry {entry_trigger_type}')
        or_window = setup_metadata.get('or_window_used')
        if isinstance(or_window, (int, float)):
            parts.append(f'OR window {int(or_window)}m')
        stop_type = setup_metadata.get('stop_type')
        if stop_type:
            parts.append(f'stop {stop_type}')
        return parts

    prior_runup = setup_metadata.get('prior_runup_pct')
    if isinstance(prior_runup, (int, float)):
        parts.append(f'prior run-up {float(prior_runup):.1%}')
    base_length = setup_metadata.get('base_length_bars')
    if isinstance(base_length, (int, float)):
        parts.append(f'base {int(base_length)} bars')
    base_depth = setup_metadata.get('base_depth_pct')
    if isinstance(base_depth, (int, float)):
        parts.append(f'base depth {float(base_depth):.1%}')
    tightness = setup_metadata.get('range_tightness_score')
    if isinstance(tightness, (int, float)):
        parts.append(f'tightness {float(tightness):.2f}')
    breakout_volume = setup_metadata.get('breakout_volume_ratio')
    if isinstance(breakout_volume, (int, float)):
        parts.append(f'breakout volume {float(breakout_volume):.1f}x')
    return parts


def _qullamaggie_explanation_bits_zh(candidate: PatternCandidate, *, setup_metadata: dict[str, object]) -> list[str]:
    if not candidate.pattern_family.startswith('qullamaggie_'):
        return []
    parts: list[str] = []
    if candidate.pattern_family == 'qullamaggie_ep_family':
        gap_pct = setup_metadata.get('gap_pct')
        if isinstance(gap_pct, (int, float)):
            parts.append(f'跳空幅度 {float(gap_pct):.1%}')
        opening_drive = setup_metadata.get('opening_drive_volume_ratio')
        if isinstance(opening_drive, (int, float)):
            parts.append(f'开盘驱动量比 {float(opening_drive):.1f} 倍')
        entry_trigger_type = setup_metadata.get('entry_trigger_type')
        if entry_trigger_type:
            parts.append(f'入场触发 {entry_trigger_type}')
        or_window = setup_metadata.get('or_window_used')
        if isinstance(or_window, (int, float)):
            parts.append(f'开盘区间 {int(or_window)} 分钟')
        stop_type = setup_metadata.get('stop_type')
        if stop_type:
            parts.append(f'止损类型 {stop_type}')
        return parts

    prior_runup = setup_metadata.get('prior_runup_pct')
    if isinstance(prior_runup, (int, float)):
        parts.append(f'前期涨幅 {float(prior_runup):.1%}')
    base_length = setup_metadata.get('base_length_bars')
    if isinstance(base_length, (int, float)):
        parts.append(f'平台长度 {int(base_length)} 根')
    base_depth = setup_metadata.get('base_depth_pct')
    if isinstance(base_depth, (int, float)):
        parts.append(f'平台深度 {float(base_depth):.1%}')
    tightness = setup_metadata.get('range_tightness_score')
    if isinstance(tightness, (int, float)):
        parts.append(f'收紧度 {float(tightness):.2f}')
    breakout_volume = setup_metadata.get('breakout_volume_ratio')
    if isinstance(breakout_volume, (int, float)):
        parts.append(f'突破量比 {float(breakout_volume):.1f} 倍')
    return parts


def _row_for_candidate(candidate: PatternCandidate) -> dict[str, object]:
    row = candidate.to_dict()
    row['secondary_signals'] = ', '.join(row['secondary_signals'])
    row['notes'] = ', '.join(row['notes'])
    row['explanation'] = _candidate_explanation(candidate)
    row['explanation_zh'] = _candidate_explanation_zh(candidate)
    row['pattern_type_zh'] = _translate_pattern_type(candidate.pattern_type)
    row['catalyst_type_zh'] = _translate_catalyst_type(candidate.catalyst_type)
    row['volume_confirmation_zh'] = _translate_volume_confirmation(candidate.volume_confirmation)
    return row


def _language_span(english: str, chinese: str) -> str:
    return f'<span class="lang lang-en">{escape(english)}</span><span class="lang lang-zh">{escape(chinese)}</span>'


def _restore_cached_frame(payload: dict | list | None):
    if not isinstance(payload, dict):
        return None
    frame_payload = payload.get('frame') if isinstance(payload.get('frame'), dict) else payload
    restored = serializable_records_to_frame(frame_payload)
    if restored is None or restored.empty:
        return None
    return normalize_daily_ohlcv_frame(restored)


def _load_chart_frames(config: ScannerConfig | None, summary: ScanRunSummary) -> dict[str, object]:
    if config is None:
        return {}
    window_key = build_scan_window_key(as_of=summary.run_metadata.as_of, period=config.period, interval=config.interval)
    frames: dict[str, object] = {}
    for symbol in _unique_symbols(summary.candidates):
        target = cache_path(Path(config.cache_dir), f'oneil_scanner/ohlcv/{window_key}', symbol)
        frame = _restore_cached_frame(load_json_cache(target))
        if frame is not None and not frame.empty:
            frames[symbol] = frame
    return frames


def _scaled(value: float, lower: float, upper: float, span: float) -> float:
    if math.isclose(upper, lower):
        return span / 2.0
    return (value - lower) / (upper - lower) * span


def _render_candidate_chart(candidate: PatternCandidate, frame) -> str:
    if frame is None or getattr(frame, 'empty', True):
        return '<div class="chart-fallback">' + _language_span('No chart data', '暂无图表数据') + '</div>'

    recent = frame.tail(60).copy()
    if recent.empty:
        return '<div class="chart-fallback">' + _language_span('No chart data', '暂无图表数据') + '</div>'

    chart_frame = frame.copy()
    chart_frame['MA20'] = chart_frame['Close'].rolling(20, min_periods=1).mean()
    chart_frame['MA50'] = chart_frame['Close'].rolling(50, min_periods=1).mean()
    chart_frame['MA200'] = chart_frame['Close'].rolling(200, min_periods=1).mean()
    recent = chart_frame.tail(60).copy()

    width = 240
    height = 150
    margin_left = 8
    margin_right = 8
    margin_top = 8
    margin_bottom = 8
    price_height = 96
    volume_gap = 6
    volume_height = 28
    usable_width = width - margin_left - margin_right
    price_width = max(usable_width, 1)
    candle_step = price_width / max(len(recent), 1)
    candle_width = max(2.0, min(6.0, candle_step * 0.65))

    highs = recent['High'].astype(float)
    lows = recent['Low'].astype(float)
    price_min = float(lows.min())
    price_max = float(highs.max())
    price_pad = max((price_max - price_min) * 0.05, price_max * 0.01, 0.5)
    price_min -= price_pad
    price_max += price_pad
    volume_max = max(float(recent['Volume'].astype(float).max()), 1.0)

    svg_parts: list[str] = [
        f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(candidate.symbol)} chart">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" rx="8" ry="8"/>',
        f'<line x1="{margin_left}" y1="{margin_top + price_height}" x2="{width - margin_right}" y2="{margin_top + price_height}" stroke="#d0d7de" stroke-width="1"/>',
    ]

    ma_specs = [
        ('MA20', '#7c3aed'),
        ('MA50', '#ea580c'),
        ('MA200', '#0891b2'),
    ]
    for ma_name, color in ma_specs:
        points: list[str] = []
        for index, (_, row) in enumerate(recent.iterrows()):
            ma_value = row.get(ma_name)
            if ma_value is None or pd.isna(ma_value):
                continue
            center_x = margin_left + index * candle_step + candle_step / 2.0
            ma_y = margin_top + (price_height - _scaled(float(ma_value), price_min, price_max, price_height))
            points.append(f'{center_x:.2f},{ma_y:.2f}')
        if len(points) >= 2:
            svg_parts.append(
                f'<polyline class="ma-line {ma_name.lower()}" fill="none" stroke="{color}" stroke-width="1.4" points="{" ".join(points)}"/>'
            )

    breakout_level = candidate.breakout_level
    if breakout_level is not None:
        breakout_y = margin_top + (price_height - _scaled(float(breakout_level), price_min, price_max, price_height))
        svg_parts.append(
            f'<line x1="{margin_left}" y1="{breakout_y:.2f}" x2="{width - margin_right}" y2="{breakout_y:.2f}" stroke="#2563eb" stroke-width="1" stroke-dasharray="4 3"/>'
        )

    volume_top = margin_top + price_height + volume_gap
    for index, (_, row) in enumerate(recent.iterrows()):
        open_price = float(row['Open'])
        high_price = float(row['High'])
        low_price = float(row['Low'])
        close_price = float(row['Close'])
        volume = float(row['Volume'])
        center_x = margin_left + index * candle_step + candle_step / 2.0
        high_y = margin_top + (price_height - _scaled(high_price, price_min, price_max, price_height))
        low_y = margin_top + (price_height - _scaled(low_price, price_min, price_max, price_height))
        open_y = margin_top + (price_height - _scaled(open_price, price_min, price_max, price_height))
        close_y = margin_top + (price_height - _scaled(close_price, price_min, price_max, price_height))
        body_top = min(open_y, close_y)
        body_height = max(abs(close_y - open_y), 1.2)
        color = '#16a34a' if close_price >= open_price else '#dc2626'
        volume_scaled = volume / volume_max * volume_height
        volume_y = volume_top + (volume_height - volume_scaled)
        svg_parts.append(f'<line x1="{center_x:.2f}" y1="{high_y:.2f}" x2="{center_x:.2f}" y2="{low_y:.2f}" stroke="{color}" stroke-width="1"/>')
        svg_parts.append(f'<rect x="{center_x - candle_width / 2.0:.2f}" y="{body_top:.2f}" width="{candle_width:.2f}" height="{body_height:.2f}" fill="{color}" rx="1" ry="1"/>')
        svg_parts.append(f'<rect x="{center_x - candle_width / 2.0:.2f}" y="{volume_y:.2f}" width="{candle_width:.2f}" height="{max(volume_scaled, 1.0):.2f}" fill="{color}" opacity="0.35" rx="1" ry="1"/>')

    latest_close = float(recent.iloc[-1]['Close'])
    latest_volume = float(recent.iloc[-1]['Volume']) / 1_000_000.0
    svg_parts.append(f'<text x="{margin_left}" y="12" font-size="10" fill="#111827">{escape(candidate.symbol)}</text>')
    svg_parts.append(f'<text x="{width - margin_right}" y="12" font-size="10" text-anchor="end" fill="#111827">{latest_close:.2f}</text>')
    svg_parts.append('<text x="8" y="146" font-size="9" fill="#7c3aed">MA20</text>')
    svg_parts.append('<text x="44" y="146" font-size="9" fill="#ea580c">MA50</text>')
    svg_parts.append('<text x="82" y="146" font-size="9" fill="#0891b2">MA200</text>')
    svg_parts.append(f'<text x="{width - margin_right}" y="{height - 2}" font-size="10" text-anchor="end" fill="#6b7280">Vol {latest_volume:.1f}M</text>')
    svg_parts.append('</svg>')
    return ''.join(svg_parts)


def _render_candidate_table(candidates: list[PatternCandidate], *, chart_frames: dict[str, object] | None = None) -> str:
    if not candidates:
        return (
            '<p class="muted">'
            '<span class="lang lang-en">No candidates in this section.</span>'
            '<span class="lang lang-zh">该分组暂无候选。</span>'
            '</p>'
        )

    columns = ['report_rank', 'symbol', 'chart', 'pattern_type', 'trigger_date', 'setup_score', 'quality_score', 'volume_confirmation', 'catalyst_type', 'explanation']
    header_cells = ''.join(
        f'<th>{_language_span(*_COLUMN_LABELS[column])}</th>'
        for column in columns
    )

    rows: list[str] = []
    for candidate in candidates:
        row = _row_for_candidate(candidate)
        cells: list[str] = []
        for column in columns:
            if column == 'chart':
                value = _render_candidate_chart(candidate, (chart_frames or {}).get(candidate.symbol))
            elif column == 'pattern_type':
                value = _language_span(str(row['pattern_type']), str(row['pattern_type_zh']))
            elif column == 'volume_confirmation':
                value = _language_span(str(row['volume_confirmation']), str(row['volume_confirmation_zh']))
            elif column == 'catalyst_type':
                value = _language_span(str(row['catalyst_type']), str(row['catalyst_type_zh']))
            elif column == 'explanation':
                value = _language_span(str(row['explanation']), str(row['explanation_zh']))
            else:
                raw = '' if row.get(column) is None else str(row.get(column))
                value = escape(raw)
            cells.append(f'<td>{value}</td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')
    return f'<table><thead><tr>{header_cells}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _render_html(summary: ScanRunSummary, *, config: ScannerConfig | None = None) -> str:
    section_map = {group.group_key: group for group in summary.grouped_candidate_summaries}
    section_candidates = _section_candidates(summary.candidates)
    chart_frames = _load_chart_frames(config, summary)

    sections_html: list[str] = []
    for section_key, label_en, label_zh, _family in REPORT_SECTIONS:
        group = section_map.get(section_key)
        count = group.candidate_count if group is not None else len(section_candidates[section_key])
        symbols = ', '.join(group.symbols) if group is not None and group.symbols else 'None'
        symbols_zh = ', '.join(group.symbols) if group is not None and group.symbols else '无'
        sections_html.append(
            '<section>'
            f'<h2>{_language_span(f"{label_en} ({count})", f"{label_zh} ({count})")}</h2>'
            f'<p class="muted">{_language_span(f"Symbols: {symbols}", f"股票代码：{symbols_zh}")}</p>'
            f'{_render_candidate_table(section_candidates[section_key], chart_frames=chart_frames)}'
            '</section>'
        )

    warnings_html = ''
    if summary.run_metadata.warnings:
        warning_items = ''.join(
            f'<li>{_language_span(warning, warning)}</li>'
            for warning in summary.run_metadata.warnings
        )
        warnings_html = (
            '<section>'
            '<details class="warnings-panel">'
            f'<summary>{_language_span("Warnings", "警告")}</summary>'
            f'<ul>{warning_items}</ul>'
            '</details>'
            '</section>'
        )

    return (
        '<!doctype html>'
        '<html>'
        '<head>'
        '  <meta charset="utf-8">'
        '  <title>Setup Scanner Report</title>'
        '  <style>'
        '    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #222; }'
        '    table { border-collapse: collapse; width: 100%; margin: 16px 0 28px; }'
        '    th, td { border: 1px solid #ddd; padding: 8px; font-size: 13px; text-align: left; vertical-align: top; }'
        '    th { background: #f5f5f5; }'
        '    .muted { color: #666; }'
        '    section { margin-top: 28px; }'
        '    .toolbar { display: flex; gap: 8px; margin: 16px 0 24px; }'
        '    .chart-svg { display: block; width: 240px; height: 150px; }'
        '    .chart-fallback { min-width: 180px; color: #666; font-size: 12px; }'
        '    .lang-toggle { border: 1px solid #ccc; background: #fff; padding: 6px 12px; border-radius: 6px; cursor: pointer; }'
        '    .lang-toggle.active { background: #222; color: #fff; border-color: #222; }'
        '    .warnings-panel { border: 1px solid #ddd; border-radius: 8px; background: #fafafa; padding: 10px 12px; }'
        '    .warnings-panel summary { cursor: pointer; font-weight: 600; }'
        '    .warnings-panel ul { margin: 10px 0 0 18px; padding: 0; }'
        '    html[data-lang="en"] .lang-zh { display: none; }'
        '    html[data-lang="zh"] .lang-en { display: none; }'
        '    @media (max-width: 1100px) { .chart-svg { width: 180px; height: 112px; } }'
        '  </style>'
        '  <script>'
        '    function setLanguage(lang) {'
        '      document.documentElement.setAttribute("data-lang", lang);'
        '      for (const button of document.querySelectorAll(".lang-toggle")) {'
        '        button.classList.toggle("active", button.dataset.lang === lang);'
        '      }'
        '    }'
        '    document.addEventListener("DOMContentLoaded", function () { setLanguage("en"); });'
        '  </script>'
        '</head>'
        '<body>'
        f'  <h1>{_language_span("Setup Scanner Report", "形态扫描报告")}</h1>'
        '  <div class="toolbar">'
        '    <button class="lang-toggle active" data-lang="en" onclick="setLanguage(\'en\')">English</button>'
        '    <button class="lang-toggle" data-lang="zh" onclick="setLanguage(\'zh\')">中文</button>'
        '  </div>'
        f'  <p class="muted">{_language_span(f"Report: {summary.run_metadata.report_name} | Universe: {summary.universe} | As of: {summary.run_metadata.as_of or "latest"}", f"报告名：{summary.run_metadata.report_name} | 股票池：{summary.universe} | 截至：{summary.run_metadata.as_of or "最新"}")}</p>'
        f'  <p class="muted">{_language_span(f"Strategy profile: {summary.run_metadata.strategy_profile}", f"策略画像：{summary.run_metadata.strategy_profile}")}</p>'
        f'  <p class="muted">{_language_span(f"Candidates: {len(summary.candidates)}", f"候选数量：{len(summary.candidates)}")}</p>'
        f'{warnings_html}'
        f'{"".join(sections_html)}'
        '</body>'
        '</html>'
    )


def write_json(path: str | Path, summary: ScanRunSummary) -> None:
    output = Path(path)
    _ensure_parent(output)
    output.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')


def write_csv(path: str | Path, summary: ScanRunSummary) -> None:
    output = Path(path)
    _ensure_parent(output)
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for candidate in summary.candidates:
            row = _row_for_candidate(candidate)
            writer.writerow({column: row.get(column) for column in CSV_COLUMNS})


def write_html(path: str | Path, summary: ScanRunSummary, config: ScannerConfig | None = None) -> None:
    output = Path(path)
    _ensure_parent(output)
    output.write_text(_render_html(summary, config=config), encoding='utf-8')


def write_report_bundle(config: ScannerConfig, summary: ScanRunSummary) -> dict[str, Path]:
    paths = {
        'json': config.report_path('json'),
        'csv': config.report_path('csv'),
        'html': config.report_path('html'),
    }
    write_json(paths['json'], summary)
    write_csv(paths['csv'], summary)
    write_html(paths['html'], summary, config=config)
    return paths


__all__ = [
    'CSV_COLUMNS',
    'REPORT_SECTIONS',
    'Template',
    'build_grouped_candidate_summaries',
    'write_csv',
    'write_html',
    'write_json',
    'write_report_bundle',
]
