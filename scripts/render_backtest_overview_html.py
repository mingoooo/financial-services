#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PRICE_DIR = Path('/Users/huangsm43/Documents/mingo/code/backtest/data/equity/usa/daily')


def load_bars(symbol: str, start: datetime, end: datetime) -> list[dict]:
    path = PRICE_DIR / f'{symbol.lower()}.zip'
    if not path.exists():
        return []
    with zipfile.ZipFile(path) as zf:
        inner = f'{symbol.lower()}.csv'
        if inner not in zf.namelist():
            inner = zf.namelist()[0]
        with zf.open(inner) as handle:
            out = []
            for line in io.TextIOWrapper(handle, encoding='utf-8'):
                parts = line.strip().split(',')
                if len(parts) < 6:
                    continue
                dt = datetime.strptime(parts[0], '%Y%m%d %H:%M')
                if not (start <= dt <= end):
                    continue
                out.append({
                    'date': dt.strftime('%Y-%m-%d'),
                    'open': int(parts[1]) / 10000.0,
                    'high': int(parts[2]) / 10000.0,
                    'low': int(parts[3]) / 10000.0,
                    'close': int(parts[4]) / 10000.0,
                    'volume': float(parts[5]),
                })
            return out


def moving_average(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= window:
            running -= values[i - window]
        if i + 1 >= window:
            out.append(round(running / window, 4))
        else:
            out.append(None)
    return out


def build_symbol_block(symbol: str, trades: list[dict]) -> dict | None:
    start = min(datetime.strptime(t['entry_date'], '%Y-%m-%d') for t in trades) - timedelta(days=220)
    end = max(datetime.strptime(t['exit_date'], '%Y-%m-%d') for t in trades) + timedelta(days=20)
    bars = load_bars(symbol, start, end)
    if not bars:
        return None
    dates = [bar['date'] for bar in bars]
    closes = [bar['close'] for bar in bars]
    sma_map = {f'SMA{window}': moving_average(closes, window) for window in [10, 20, 50, 100, 200]}
    markers = []
    for trade in trades:
        if trade['entry_date'] in dates:
            markers.append({'name': 'Entry', 'coord': [trade['entry_date'], trade['entry_price']], 'value': f"买入\n{trade['entry_date']}\n{trade['entry_price']:.2f}", 'itemStyle': {'color': '#16a34a'}})
        if trade['exit_date'] in dates:
            markers.append({'name': 'Exit', 'coord': [trade['exit_date'], trade['exit_price']], 'value': f"卖出\n{trade['exit_date']}\n{trade['exit_price']:.2f}\n{trade['exit_reason']}", 'itemStyle': {'color': '#dc2626'}})
    return {
        'symbol': symbol,
        'dates': dates,
        'ohlc': [[bar['open'], bar['close'], bar['low'], bar['high']] for bar in bars],
        'volumes': [bar['volume'] for bar in bars],
        'markers': markers,
        'trades': trades,
        'sma': sma_map,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Render unified overview HTML for multiple backtest result JSONs.')
    parser.add_argument('--result-json', action='append', required=True)
    parser.add_argument('--output-html', required=True)
    args = parser.parse_args()

    mode_payloads = []
    for path_str in args.result_json:
        path = Path(path_str)
        data = json.loads(path.read_text(encoding='utf-8'))
        mode = data.get('universe_mode', path.stem)
        trades_by_symbol: dict[str, list[dict]] = defaultdict(list)
        for trade in data.get('trades', []):
            trades_by_symbol[trade['symbol']].append(trade)
        symbol_blocks = []
        for symbol, trades in sorted(trades_by_symbol.items()):
            block = build_symbol_block(symbol, trades)
            if block:
                symbol_blocks.append(block)
        mode_payloads.append({
            'mode': mode,
            'summary': {
                'mode': mode,
                'start': data['start'],
                'end': data['end'],
                'final_equity': data['final_equity'],
                'total_return_pct': data['total_return_pct'],
                'max_drawdown_pct': data['max_drawdown_pct'],
                'win_rate_pct': data['win_rate_pct'],
                'executed_trade_count': data['executed_trade_count'],
                'profit_factor': data.get('profit_factor', 0),
            },
            'symbols': symbol_blocks,
        })

    payload_json = json.dumps(mode_payloads, ensure_ascii=False)
    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Backtest Overview</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #0b1020; color: #e5e7eb; }}
    .wrap {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    .tabs {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
    .tab {{ background: #1e293b; color: #e2e8f0; border: 0; padding: 10px 14px; border-radius: 999px; cursor: pointer; }}
    .tab.active {{ background: #2563eb; }}
    .summary {{ display: grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap: 12px; margin-bottom: 24px; }}
    .card {{ background: #121a2b; border-radius: 12px; padding: 16px; }}
    .label {{ font-size: 12px; color: #94a3b8; margin-bottom: 8px; }}
    .value {{ font-size: 24px; font-weight: 700; }}
    .mode-section {{ display: none; }}
    .mode-section.active {{ display: block; }}
    .chart-card {{ background: #121a2b; border-radius: 12px; padding: 16px; margin-bottom: 24px; }}
    .chart {{ height: 560px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
    th, td {{ padding: 8px; border-bottom: 1px solid #243046; text-align: left; }}
    h1, h2 {{ margin: 0 0 16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>回测总览</h1>
    <div class="tabs" id="tabs"></div>
    <div id="content"></div>
  </div>
  <script>
    const payload = {payload_json};
    const tabs = document.getElementById('tabs');
    const content = document.getElementById('content');

    function renderMode(modePayload, active) {{
      const summary = modePayload.summary;
      const section = document.createElement('div');
      section.className = 'mode-section' + (active ? ' active' : '');
      section.id = `section-${{summary.mode}}`;
      section.innerHTML = `
        <div class="summary">
          <div class="card"><div class="label">模式</div><div class="value">${{summary.mode}}</div></div>
          <div class="card"><div class="label">总收益</div><div class="value">${{summary.total_return_pct}}%</div></div>
          <div class="card"><div class="label">最终权益</div><div class="value">${{summary.final_equity}}</div></div>
          <div class="card"><div class="label">最大回撤</div><div class="value">${{summary.max_drawdown_pct}}%</div></div>
          <div class="card"><div class="label">胜率</div><div class="value">${{summary.win_rate_pct}}%</div></div>
          <div class="card"><div class="label">成交笔数</div><div class="value">${{summary.executed_trade_count}}</div></div>
        </div>`;
      modePayload.symbols.forEach((block, idx) => {{
        const card = document.createElement('div');
        card.className = 'chart-card';
        const rows = block.trades.map(t => `<tr><td>${{t.entry_date}}</td><td>${{t.exit_date}}</td><td>${{t.entry_price.toFixed(2)}}</td><td>${{t.exit_price.toFixed(2)}}</td><td>${{t.return_pct.toFixed(2)}}%</td><td>${{t.exit_reason}}</td></tr>`).join('');
        card.innerHTML = `<h2>${{block.symbol}}</h2><div id="chart-${{summary.mode}}-${{idx}}" class="chart"></div><table><thead><tr><th>进场</th><th>离场</th><th>进场价</th><th>离场价</th><th>收益</th><th>原因</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        section.appendChild(card);
        setTimeout(() => {{
          const chart = echarts.init(document.getElementById(`chart-${{summary.mode}}-${{idx}}`));
          const series = [
            {{ name: 'K线', type: 'candlestick', data: block.ohlc, itemStyle: {{ color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' }}, markPoint: {{ symbol: 'pin', symbolSize: 42, label: {{ color: '#fff', formatter: '{{b}}' }}, data: block.markers }} }},
            {{ name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: block.volumes, itemStyle: {{ color: '#60a5fa' }} }},
          ];
          [['SMA10','#f59e0b'],['SMA20','#38bdf8'],['SMA50','#a78bfa'],['SMA100','#f472b6'],['SMA200','#34d399']].forEach(([name,color]) => {{
            series.push({{ name, type: 'line', data: block.sma[name], showSymbol: false, smooth: false, lineStyle: {{ width: 1.5, color }}, connectNulls: false }});
          }});
          chart.setOption({{
            animation: false,
            backgroundColor: '#121a2b',
            tooltip: {{ trigger: 'axis' }},
            legend: {{ data: ['K线','SMA10','SMA20','SMA50','SMA100','SMA200','成交量'], textStyle: {{ color: '#cbd5e1' }} }},
            axisPointer: {{ link: [{{ xAxisIndex: 'all' }}] }},
            grid: [{{ left: '8%', right: '8%', top: 50, height: '55%' }}, {{ left: '8%', right: '8%', top: '72%', height: '16%' }}],
            xAxis: [{{ type: 'category', data: block.dates, scale: true, boundaryGap: false, axisLine: {{ lineStyle: {{ color: '#64748b' }} }}, splitLine: {{ show: false }}, axisLabel: {{ color: '#94a3b8' }} }}, {{ type: 'category', gridIndex: 1, data: block.dates, scale: true, boundaryGap: false, axisLine: {{ lineStyle: {{ color: '#64748b' }} }}, splitLine: {{ show: false }}, axisLabel: {{ show: false }} }}],
            yAxis: [{{ scale: true, axisLine: {{ lineStyle: {{ color: '#64748b' }} }}, splitLine: {{ lineStyle: {{ color: '#243046' }} }}, axisLabel: {{ color: '#94a3b8' }} }}, {{ scale: true, gridIndex: 1, axisLine: {{ lineStyle: {{ color: '#64748b' }} }}, splitLine: {{ show: false }}, axisLabel: {{ color: '#94a3b8' }} }}],
            series,
          }});
        }}, 0);
      }});
      content.appendChild(section);
    }}

    function activate(mode) {{
      document.querySelectorAll('.tab').forEach(el => el.classList.toggle('active', el.dataset.mode === mode));
      document.querySelectorAll('.mode-section').forEach(el => el.classList.toggle('active', el.id === `section-${{mode}}`));
    }}

    payload.forEach((modePayload, idx) => {{
      const button = document.createElement('button');
      button.className = 'tab' + (idx === 0 ? ' active' : '');
      button.dataset.mode = modePayload.summary.mode;
      button.textContent = modePayload.summary.mode;
      button.onclick = () => activate(modePayload.summary.mode);
      tabs.appendChild(button);
      renderMode(modePayload, idx === 0);
    }});
  </script>
</body>
</html>'''

    Path(args.output_html).write_text(html, encoding='utf-8')
    print(args.output_html)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
