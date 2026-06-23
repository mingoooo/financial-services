#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'scripts' / 'reversal_experiments.yaml'
REPORT_ROOT = ROOT / 'reports' / 'reversal-experiments'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='批量运行 reversal 参数实验')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--experiments', help='逗号分隔，只运行指定实验名')
    parser.add_argument('--output-dir')
    parser.add_argument('--range')
    parser.add_argument('--entry-mode', choices=['next_open', 'confirm_close'])
    parser.add_argument('--symbols')
    parser.add_argument('--max-symbols', type=int)
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--resume', action='store_true')
    return parser.parse_args()


def load_config(path_str: str) -> dict:
    return yaml.safe_load(Path(path_str).read_text(encoding='utf-8')) or {}


def merge_dicts(*parts: dict) -> dict:
    merged: dict = {}
    for part in parts:
        if not part:
            continue
        merged.update(part)
    return merged


def _expand_grid(item: dict) -> list[dict]:
    grid = item.get('grid') or {}
    if not grid:
        return [item]
    expanded = [{}]
    for key, values in grid.items():
        next_rows = []
        for row in expanded:
            for value in values:
                candidate = dict(row)
                candidate[key] = value
                next_rows.append(candidate)
        expanded = next_rows
    rows = []
    for overrides in expanded:
        label = '__'.join(f"{key}={value}" for key, value in overrides.items())
        candidate = {k: v for k, v in item.items() if k != 'grid'}
        candidate['name'] = f"{item['name']}__{label}" if label else item['name']
        candidate.update(overrides)
        rows.append(candidate)
    return rows


def build_experiments(payload: dict, selected_names: set[str] | None) -> list[dict]:
    defaults = payload.get('defaults') or {}
    presets = payload.get('presets') or {}
    experiments = []
    for item in payload.get('experiments') or []:
        expanded_rows = _expand_grid(item)
        if selected_names and item.get('name') in selected_names:
            for expanded in expanded_rows:
                name = expanded['name']
                preset_values = presets.get(expanded.get('use'), {}) if expanded.get('use') else {}
                final = merge_dicts(defaults, preset_values, {k: v for k, v in expanded.items() if k not in {'name', 'use'}})
                experiments.append({'name': name, 'params': final, 'use': expanded.get('use')})
            continue
        for expanded in expanded_rows:
            name = expanded['name']
            if selected_names and name not in selected_names:
                continue
            preset_values = presets.get(expanded.get('use'), {}) if expanded.get('use') else {}
            final = merge_dicts(defaults, preset_values, {k: v for k, v in expanded.items() if k not in {'name', 'use'}})
            experiments.append({'name': name, 'params': final, 'use': expanded.get('use')})
    return experiments


def apply_cli_overrides(params: dict, args: argparse.Namespace) -> dict:
    merged = dict(params)
    for key in ['range', 'entry_mode', 'symbols', 'max_symbols']:
        value = getattr(args, key)
        if value is not None:
            merged[key] = value
    return merged


def to_cli_args(params: dict, summary_json: Path, csv_dir: Path, html_path: Path) -> list[str]:
    args = [sys.executable, str(ROOT / 'scripts' / 'backtest_reversals.py'), '--json', str(summary_json), '--csv-dir', str(csv_dir), '--html', str(html_path)]
    bool_flags_true = {
        'include_etfs': '--include-etfs',
        'require_confirm_volume': '--require-confirm-volume',
        'require_trend_alignment': '--require-trend-alignment',
        'require_location_alignment': '--require-location-alignment',
        'require_fresh_sma_cross_up': '--require-fresh-sma-cross-up',
        'require_macd_bullish': '--require-macd-bullish',
        'require_above_sma200': '--require-above-sma200',
    }
    bool_flags_false = {
        'include_etfs': '--exclude-etfs',
        'require_confirm_volume': '--no-require-confirm-volume',
    }
    scalar_flags = {
        'preset': '--preset',
        'entry_mode': '--entry-mode',
        'require_rsi_above': '--require-rsi-above',
        'range': '--range',
        'universe': '--universe',
        'side': '--side',
        'max_symbols': '--max-symbols',
        'top_dollar_volume': '--top-dollar-volume',
        'min_last_volume': '--min-last-volume',
        'min_avg_volume': '--min-avg-volume',
        'min_price': '--min-price',
        'min_market_cap': '--min-market-cap',
        'etf_groups': '--etf-groups',
        'min_r_multiple': '--min-r-multiple',
        'location_tolerance_ratio': '--location-tolerance-ratio',
        'allowed_patterns': '--allowed-patterns',
        'sma_cross_mode': '--sma-cross-mode',
        'symbols': '--symbols',
    }
    preset_value = params.get('preset')
    explicit_keys = {
        'require_confirm_volume',
        'min_r_multiple',
        'require_fresh_sma_cross_up',
        'require_rsi_above',
        'require_macd_bullish',
        'universe',
        'include_etfs',
    }
    if preset_value is not None and not any(key in params for key in explicit_keys):
        args.extend(['--preset', str(preset_value)])
    for key, flag in scalar_flags.items():
        if key == 'preset':
            continue
        value = params.get(key)
        if value is not None:
            args.extend([flag, str(value)])
    for key, flag in bool_flags_true.items():
        if params.get(key) is True:
            args.append(flag)
    for key, flag in bool_flags_false.items():
        if key in params and params.get(key) is False:
            args.append(flag)
    return args


def write_leaderboard_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _to_bool_label(value) -> str:
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    return str(value)


def summarize_rows(rows: list[dict]) -> dict:
    count = len(rows)
    if count == 0:
        return {
            'count': 0,
            'avg_sharpe_ratio': 0.0,
            'avg_total_pnl': 0.0,
            'avg_total_trades': 0.0,
            'avg_win_rate': 0.0,
            'avg_max_drawdown_pct': 0.0,
        }
    return {
        'count': count,
        'avg_sharpe_ratio': round(sum(row['sharpe_ratio'] for row in rows) / count, 4),
        'avg_total_pnl': round(sum(row['total_pnl'] for row in rows) / count, 4),
        'avg_total_trades': round(sum(row['total_trades'] for row in rows) / count, 4),
        'avg_win_rate': round(sum(row['win_rate'] for row in rows) / count, 4),
        'avg_max_drawdown_pct': round(sum(row['max_drawdown_pct'] for row in rows) / count, 4),
    }


def write_marginal_effects(json_path: Path, csv_path: Path, rows: list[dict]) -> None:
    params_by_experiment = {row['experiment']: json.loads(row['param_summary']) for row in rows}
    tracked_keys = [
        'require_confirm_volume',
        'min_r_multiple',
        'require_fresh_sma_cross_up',
        'require_rsi_above',
        'require_macd_bullish',
        'universe',
    ]
    payload = {}
    csv_rows = []
    for key in tracked_keys:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            params = params_by_experiment[row['experiment']]
            value = params.get(key)
            label = _to_bool_label(value)
            buckets[label].append(row)
        payload[key] = {}
        for label, items in sorted(buckets.items(), key=lambda item: item[0]):
            summary = summarize_rows(items)
            payload[key][label] = summary
            csv_rows.append({'parameter': key, 'value': label, **summary})
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    write_leaderboard_csv(csv_path, csv_rows)


def write_filtered_leaderboard(path: Path, rows: list[dict], universe: str) -> None:
    subset = [row for row in rows if json.loads(row['param_summary']).get('universe') == universe]
    write_leaderboard_csv(path, subset)


def write_index_html(path: Path, rows: list[dict]) -> None:
    top = rows[:3]
    cards = ''.join(
        f"<div class='card'><div class='rank'>#{idx}</div><div class='name'>{row['experiment']}</div><div class='meta'>Sharpe {row['sharpe_ratio']:.2f} · PnL {row['total_pnl']:.2f} · MaxDD {row['max_drawdown_pct']:.2f}%</div><div class='meta'>Trades {row['total_trades']} · Win {row['win_rate']:.2f}% · PF {row['profit_factor']:.2f}</div></div>"
        for idx, row in enumerate(top, start=1)
    )
    table_rows = ''.join(
        f"<tr><td>{row['experiment']}</td><td>{row['base_preset']}</td><td>{row['total_trades']}</td><td>{row['win_rate']:.2f}%</td><td>{row['average_return_pct']:.2f}%</td><td>{row['median_return_pct']:.2f}%</td><td>{row['total_pnl']:.2f}</td><td>{row['max_drawdown_pct']:.2f}%</td><td>{row['profit_factor']:.2f}</td><td>{row['sharpe_ratio']:.2f}</td><td><code>{row['param_summary']}</code></td></tr>"
        for row in rows
    )
    html = f"""<!doctype html>
<html lang='zh-CN'>
<head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Reversal Experiments</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;line-height:1.5}}
.wrap{{max-width:1440px;margin:0 auto}}
.hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:18px 0 24px}}
.card{{background:#111827;border:1px solid #334155;border-radius:14px;padding:16px}}
.rank{{font-size:12px;color:#94a3b8}}
.name{{font-size:18px;font-weight:700;margin:4px 0 8px}}
.meta{{color:#cbd5e1;font-size:13px}}
.table-wrap{{overflow:auto;border:1px solid #334155;border-radius:12px}}
table{{width:100%;border-collapse:collapse;background:#111827}}
td,th{{border:1px solid #334155;padding:8px 10px;font-size:13px;vertical-align:top}}
th{{background:#1e293b;position:sticky;top:0;cursor:pointer;user-select:none}}
th.sort-asc::after{{content:' ▲';font-size:11px;color:#93c5fd}}
th.sort-desc::after{{content:' ▼';font-size:11px;color:#93c5fd}}
code{{white-space:pre-wrap;font-size:12px;color:#bfdbfe}}
.small{{color:#94a3b8;font-size:13px;margin-bottom:12px}}
</style>
<script>
function parseCellValue(text, type) {{
  const cleaned = text.replace(/[%,$,]/g, '').trim();
  if (type === 'number') {{
    const n = Number(cleaned);
    return Number.isNaN(n) ? -Infinity : n;
  }}
  return cleaned.toLowerCase();
}}
function makeSortable() {{
  const table = document.querySelector('table');
  const headers = table.querySelectorAll('th');
  const tbody = table.querySelector('tbody');
  headers.forEach((th, index) => {{
    th.addEventListener('click', () => {{
      const type = th.dataset.type || 'text';
      const current = th.classList.contains('sort-asc') ? 'asc' : th.classList.contains('sort-desc') ? 'desc' : 'none';
      headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      const next = current === 'asc' ? 'desc' : 'asc';
      th.classList.add(next === 'asc' ? 'sort-asc' : 'sort-desc');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {{
        const av = parseCellValue(a.children[index].innerText, type);
        const bv = parseCellValue(b.children[index].innerText, type);
        if (av < bv) return next === 'asc' ? -1 : 1;
        if (av > bv) return next === 'asc' ? 1 : -1;
        return 0;
      }});
      rows.forEach(row => tbody.appendChild(row));
    }});
  }});
}}
window.addEventListener('DOMContentLoaded', makeSortable);
</script>
</head><body><div class='wrap'><h1>Reversal Experiments Leaderboard</h1><div class='small'>默认按 Sharpe Ratio 降序排列；点击任意列表头可排序，同时展示 Trade 数、PnL、Max Drawdown，避免只看单一指标。</div><div class='hero'>{cards}</div><div class='table-wrap'><table><thead><tr><th data-type='text'>Experiment</th><th data-type='text'>Base</th><th data-type='number'>Trades</th><th data-type='number'>Win Rate</th><th data-type='number'>Avg Return</th><th data-type='number'>Median Return</th><th data-type='number'>Total PnL</th><th data-type='number'>MaxDD</th><th data-type='number'>PF</th><th data-type='number'>Sharpe</th><th data-type='text'>Params</th></tr></thead><tbody>{table_rows}</tbody></table></div></div></body></html>"""
    path.write_text(html, encoding='utf-8')


def main() -> int:
    args = parse_args()
    payload = load_config(args.config)
    selected = {item.strip() for item in args.experiments.split(',') if item.strip()} if args.experiments else None
    experiments = build_experiments(payload, selected)
    if not experiments:
        print('No experiments selected.', file=sys.stderr)
        return 1
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    out_root = Path(args.output_dir) if args.output_dir else REPORT_ROOT / run_id
    out_root.mkdir(parents=True, exist_ok=True)

    leaderboard: list[dict] = []
    for experiment in experiments:
        name = experiment['name']
        params = apply_cli_overrides(experiment['params'], args)
        exp_dir = out_root / name
        exp_dir.mkdir(parents=True, exist_ok=True)
        summary_json = exp_dir / 'summary.json'
        csv_dir = exp_dir / 'csv'
        html_path = exp_dir / 'report.html'
        if args.resume and summary_json.exists():
            print(f'[experiments] skip existing {name}', file=sys.stderr)
            summary = json.loads(summary_json.read_text(encoding='utf-8'))
            row = {
                'experiment': name,
                'base_preset': params.get('preset') or experiment.get('use') or '-',
                'total_trades': summary.get('total_trades', 0),
                'win_rate': summary.get('win_rate', 0.0),
                'average_return_pct': summary.get('average_return_pct', 0.0),
                'median_return_pct': summary.get('median_return_pct', 0.0),
                'total_pnl': summary.get('total_pnl', 0.0),
                'max_drawdown_pct': summary.get('max_drawdown_pct', 0.0),
                'profit_factor': summary.get('profit_factor', 0.0),
                'sharpe_ratio': summary.get('sharpe_ratio', 0.0),
                'param_summary': json.dumps(params, ensure_ascii=False, sort_keys=True),
            }
            leaderboard.append(row)
            continue
        cmd = to_cli_args(params, summary_json, csv_dir, html_path)
        print(f'[experiments] running {name}', file=sys.stderr)
        last_error = None
        for attempt in range(1, args.retries + 1):
            try:
                subprocess.run(cmd, cwd=ROOT, check=True)
                last_error = None
                break
            except subprocess.CalledProcessError as exc:
                last_error = exc
                print(f'[experiments] retry {attempt}/{args.retries} failed for {name}', file=sys.stderr)
        if last_error is not None:
            raise last_error
        summary = json.loads(summary_json.read_text(encoding='utf-8'))
        row = {
            'experiment': name,
            'base_preset': params.get('preset') or experiment.get('use') or '-',
            'total_trades': summary.get('total_trades', 0),
            'win_rate': summary.get('win_rate', 0.0),
            'average_return_pct': summary.get('average_return_pct', 0.0),
            'median_return_pct': summary.get('median_return_pct', 0.0),
            'total_pnl': summary.get('total_pnl', 0.0),
            'max_drawdown_pct': summary.get('max_drawdown_pct', 0.0),
            'profit_factor': summary.get('profit_factor', 0.0),
            'sharpe_ratio': summary.get('sharpe_ratio', 0.0),
            'param_summary': json.dumps(params, ensure_ascii=False, sort_keys=True),
        }
        leaderboard.append(row)

    leaderboard.sort(key=lambda item: (item['sharpe_ratio'], item['total_pnl']), reverse=True)
    (out_root / 'leaderboard.json').write_text(json.dumps(leaderboard, indent=2, ensure_ascii=False), encoding='utf-8')
    write_leaderboard_csv(out_root / 'leaderboard.csv', leaderboard)
    write_filtered_leaderboard(out_root / 'leaderboard_sp500.csv', leaderboard, 'sp500')
    write_filtered_leaderboard(out_root / 'leaderboard_us.csv', leaderboard, 'us')
    write_marginal_effects(out_root / 'marginal_effects.json', out_root / 'marginal_effects.csv', leaderboard)
    write_index_html(out_root / 'index.html', leaderboard)
    print(json.dumps({'output_dir': str(out_root), 'experiments': len(leaderboard)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
