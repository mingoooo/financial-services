#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from vcp_lib.charts import render_candidate_chart_html
from vcp_lib.config import ScanConfig
from vcp_lib.data_sources import load_price_history, resolve_candidates
from vcp_lib.indicators import add_core_indicators
from vcp_lib.models import ScanSummary, UniverseSnapshot
from vcp_lib.report import write_csv, write_html, write_json
from vcp_lib.scoring import score_candidate
from vcp_lib.trend_template import evaluate_trend_template
from vcp_lib.vcp_detector import detect_vcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Scan U.S. stocks for Minervini-style VCP setups.')
    parser.add_argument('--universe', default='all-us')
    parser.add_argument('--data-source', default='finviz+yahoo')
    parser.add_argument('--min-price', type=float, default=10.0)
    parser.add_argument('--min-dollar-volume', type=float, default=10_000_000.0)
    parser.add_argument('--max-candidates', type=int, default=400)
    parser.add_argument('--history-days', type=int, default=420)
    parser.add_argument('--require-trend-template', action='store_true')
    parser.add_argument('--max-base-depth', type=float, default=0.35)
    parser.add_argument('--output-html', default='reports/vcp_scan.html')
    parser.add_argument('--json-out')
    parser.add_argument('--csv-out')
    parser.add_argument('--cache-dir', default='.cache/vcp')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    return parser


def parse_args() -> ScanConfig:
    args = build_parser().parse_args()
    return ScanConfig(
        universe=args.universe,
        data_source=args.data_source,
        min_price=args.min_price,
        min_dollar_volume=args.min_dollar_volume,
        max_candidates=args.max_candidates,
        history_days=args.history_days,
        require_trend_template=args.require_trend_template,
        max_base_depth=args.max_base_depth,
        output_html=args.output_html,
        json_out=args.json_out,
        csv_out=args.csv_out,
        cache_dir=args.cache_dir,
        verbose=args.verbose,
    )


def run_scan(config: ScanConfig) -> ScanSummary:
    provider_result = resolve_candidates(config)
    summary = ScanSummary(
        run_timestamp=datetime.now().isoformat(timespec='seconds'),
        data_source_mode=provider_result.mode_used,
        universe=UniverseSnapshot(
            requested_universe=config.universe,
            data_source_mode=provider_result.mode_used,
            symbols_considered=len(provider_result.candidates),
            symbols_prefiltered=len(provider_result.candidates),
            finviz_fallback_used=provider_result.mode_used == 'yahoo-only' and config.data_source != 'yahoo',
            provider_warnings=provider_result.warnings,
            prefilter_rules=provider_result.rules_applied,
            downstream_filter_counts={
                '历史长度不足': 0,
                '价格低于阈值': 0,
                '成交额低于阈值': 0,
                '趋势模板过滤': 0,
                '最终 Reject': 0,
            },
        ),
    )
    scan_candidates = provider_result.candidates[: config.max_candidates]
    for raw_candidate in scan_candidates:
        summary.total_symbols_attempted += 1
        try:
            frame = load_price_history(raw_candidate.symbol, config)
        except Exception as exc:
            reason = str(exc)
            if reason.startswith('IGNORABLE:'):
                summary.failed_symbols.append({'symbol': raw_candidate.symbol, 'reason': reason.replace('IGNORABLE:', '', 1)})
                continue
            summary.failed_symbols.append({'symbol': raw_candidate.symbol, 'reason': reason})
            continue
        if len(frame) < 200:
            summary.insufficient_data_symbols.append(raw_candidate.symbol)
            summary.universe.downstream_filter_counts['历史长度不足'] += 1
            continue
        raw_candidate.last_price = raw_candidate.last_price or float(frame['Close'].iloc[-1])
        raw_candidate.average_volume = float(frame['Volume'].tail(20).mean())
        raw_candidate.average_dollar_volume = float((frame['Close'] * frame['Volume']).tail(20).mean())
        if raw_candidate.last_price < config.min_price:
            summary.universe.downstream_filter_counts['价格低于阈值'] += 1
            continue
        if raw_candidate.average_dollar_volume < config.min_dollar_volume:
            summary.universe.downstream_filter_counts['成交额低于阈值'] += 1
            continue
        enriched = add_core_indicators(frame)
        trend = evaluate_trend_template(enriched)
        if config.require_trend_template and not trend.passes:
            summary.universe.downstream_filter_counts['趋势模板过滤'] += 1
            continue
        vcp = detect_vcp(enriched, max_base_depth=config.max_base_depth)
        scored = score_candidate(raw_candidate, trend, vcp)
        if scored.setup_tier in {'Textbook VCP', 'Near-VCP'}:
            scored.chart_html = render_candidate_chart_html(enriched, scored)
        if scored.grade != 'Reject':
            summary.final_candidates.append(scored)
        else:
            summary.universe.downstream_filter_counts['最终 Reject'] += 1
        summary.successful_histories += 1
    summary.final_candidates.sort(key=lambda item: item.overall_score, reverse=True)
    return summary


def main() -> int:
    config = parse_args()
    import sys
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        summary = ScanSummary(
            run_timestamp=datetime.now().isoformat(timespec='seconds'),
            data_source_mode=config.data_source,
            universe=UniverseSnapshot(requested_universe=config.universe, data_source_mode=config.data_source),
        )
    else:
        summary = run_scan(config)
    write_html(config.output_html, summary)
    write_json(config.json_out, summary)
    write_csv(config.csv_out, summary)
    print(json.dumps(summary.to_dict(), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
