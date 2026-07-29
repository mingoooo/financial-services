from __future__ import annotations

import csv
import json
from pathlib import Path

from jinja2 import Template

from .models import ScanSummary

DEFECT_TRANSLATIONS = {
    'advance-too-small': '前置上涨幅度不足',
    'no-higher-highs': '未形成更高高点',
    'no-higher-lows': '未形成更高低点',
    'weak-moving-average-structure': '均线结构偏弱',
    'contractions-not-shrinking': '收缩幅度未明显递减',
    'leg-duration-worsening': '回撤持续时间未改善',
    'volume-not-drying-up': '回撤阶段量能未明显萎缩',
    'late-stage-not-tight': '末段整理不够紧',
    'insufficient-swings': '可识别的 swing 结构不足',
    'no-prior-uptrend': '缺少可信的前置上涨',
    'base-too-deep': '底座过深',
    'too-extended-from-pivot': '距离 Pivot 过远，已偏扩展',
    'missing-pivot': '未识别到有效 Pivot',
    'not-enough-down-legs': '回撤腿数量不足',
}

_HTML_TEMPLATE = Template("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>VCP 扫描报告</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; margin: 24px; color: #222; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 13px; vertical-align: top; }
    th { background: #f5f5f5; }
    .grade-A-plus { color: #0a7a2f; font-weight: 700; }
    .grade-A { color: #2f7d32; font-weight: 700; }
    .grade-B { color: #8a6d1d; }
    .grade-Watch { color: #9c6b00; }
    .grade-Reject { color: #999; }
    .muted { color: #666; }
    .section { margin: 24px 0; }
    .card { border: 1px solid #e5e5e5; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fff; }
    .summary-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }
    .summary-grid .card { margin: 0; }
    details { border: 1px solid #e5e5e5; border-radius: 8px; background: #fafafa; padding: 10px 12px; margin: 12px 0; }
    summary { cursor: pointer; font-weight: 600; }
    .pill { display: inline-block; border-radius: 999px; padding: 2px 8px; background: #f1f3f5; font-size: 12px; margin-right: 6px; }
    .chart-wrap { margin-top: 12px; }
    .toolbar { margin: 12px 0 20px; }
    .toolbar button { padding: 8px 12px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
  </style>
  <script>
    function toggleAllCharts(expand) {
      document.querySelectorAll('details.chart-details').forEach((el) => { el.open = expand; });
    }
  </script>
</head>
<body>
  <h1>VCP 扫描报告</h1>
  <p>运行时间：{{ summary.run_timestamp }}</p>
  <p>数据模式：{{ summary.data_source_mode }}</p>

  <div class="summary-grid">
    <div class="card"><strong>股票池规模</strong><br>{{ summary.universe.symbols_considered }}</div>
    <div class="card"><strong>预筛后数量</strong><br>{{ summary.universe.symbols_prefiltered }}</div>
    <div class="card"><strong>成功加载历史</strong><br>{{ summary.successful_histories }}</div>
    <div class="card"><strong>下载失败</strong><br>{{ summary.failed_symbols|length }}</div>
    <div class="card"><strong>数据不足</strong><br>{{ summary.insufficient_data_symbols|length }}</div>
    <div class="card"><strong>最终候选</strong><br>{{ summary.final_candidates|length }}</div>
  </div>

  <details>
    <summary>点此展开：当前扫描器使用的规则</summary>
    <div class="section">
      <p><span class="pill">预筛规则</span>{% for rule in summary.universe.prefilter_rules %}{{ rule }}{% if not loop.last %}；{% endif %}{% endfor %}</p>
      <p><span class="pill">趋势模板</span>优先通过 `SMA50 / SMA150 / SMA200` 关系、接近 52 周高点、长期均线方向来判断股票是否处在 Minervini 风格的可选区间。</p>
      <p><span class="pill">Swing 分段</span>使用 ATR 感知的反转阈值与最小时间间隔，避免把日常噪音误判成多个收缩腿。</p>
      <p><span class="pill">Prior Uptrend</span>要求底座左侧存在一定幅度的上涨，并尽量具备更高高点 / 更高低点或改善中的均线结构。</p>
      <p><span class="pill">VCP 检测</span>检查最近 2–4 条回撤腿的深度、持续时间、量能是否总体改善，并要求后段足够紧、价格不要离 pivot 太远。</p>
      <p><span class="pill">瑕疵翻译</span>
        {% for key, value in defect_translations.items() %}
          {{ key }} = {{ value }}{% if not loop.last %}；{% endif %}
        {% endfor %}
      </p>
    </div>
  </details>

  <div class="toolbar">
    <button onclick="toggleAllCharts(true)">全部展开K线图</button>
    <button onclick="toggleAllCharts(false)">全部收起K线图</button>
  </div>

  {% set textbook = summary.final_candidates | selectattr('setup_tier', 'equalto', 'Textbook VCP') | list %}
  {% set near = summary.final_candidates | selectattr('setup_tier', 'equalto', 'Near-VCP') | list %}
  {% set watch = summary.final_candidates | selectattr('setup_tier', 'equalto', '观察名单') | list %}

  {% macro result_table(title, rows) -%}
    <div class="section">
      <h2>{{ title }}（{{ rows|length }}）</h2>
      <table>
        <thead>
          <tr>
            <th>代码</th><th>层级</th><th>复核优先级</th><th>等级</th><th>总分</th><th>现价</th><th>距 Pivot</th><th>收缩次数</th><th>底座深度</th><th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {% for candidate in rows %}
          {% set grade_class = 'grade-A-plus' if candidate.grade == 'A+' else 'grade-' ~ candidate.grade %}
          <tr>
            <td><a href="#{{ candidate.symbol }}">{{ candidate.symbol }}</a></td>
            <td>{{ candidate.setup_tier }}</td>
            <td>{{ candidate.review_priority }}</td>
            <td class="{{ grade_class }}">{{ candidate.grade }}</td>
            <td>{{ '%.2f'|format(candidate.overall_score) }}</td>
            <td>{{ '%.2f'|format(candidate.last_price) if candidate.last_price is not none else '' }}</td>
            <td>{{ '%.2f%%'|format(candidate.vcp.distance_to_pivot_pct * 100) if candidate.vcp.distance_to_pivot_pct is not none else '' }}</td>
            <td>{{ candidate.vcp.contraction_count }}</td>
            <td>{{ '%.2f%%'|format(candidate.vcp.base_depth_pct * 100) if candidate.vcp.base_depth_pct is not none else '' }}</td>
            <td>{% for item in candidate.explanation[:3] %}{{ defect_translations.get(item, item) }}{% if not loop.last %}；{% endif %}{% endfor %}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {%- endmacro %}

  {{ result_table('Textbook VCP', textbook) }}
  {{ result_table('Near-VCP', near) }}
  {{ result_table('观察名单', watch) }}

  <div class="section">
    <h2>个股详情</h2>
    {% for candidate in summary.final_candidates %}
    <section id="{{ candidate.symbol }}" class="card">
      <h3>{{ candidate.symbol }} — {{ candidate.setup_tier }} — {{ candidate.review_priority }} — {{ candidate.grade }} — {{ '%.2f'|format(candidate.overall_score) }}</h3>
      <p class="muted">{% for item in candidate.explanation %}{{ defect_translations.get(item, item) }}{% if not loop.last %}；{% endif %}{% endfor %}</p>
      <p>趋势模板：{{ '通过' if candidate.trend_template.passes else '不通过' }}</p>
      <p>Pivot：{{ candidate.vcp.pivot_price }} ｜ 距离：{{ '%.2f%%'|format(candidate.vcp.distance_to_pivot_pct * 100) if candidate.vcp.distance_to_pivot_pct is not none else '无' }}</p>
      {% if candidate.chart_html %}
      <details class="chart-details">
        <summary>点击展开 {{ candidate.symbol }} K线图与标注</summary>
        <div class="chart-wrap">{{ candidate.chart_html | safe }}</div>
      </details>
      {% endif %}
    </section>
    {% endfor %}
  </div>
</body>
</html>
""")


def write_json(path: str | None, summary: ScanSummary) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')


def write_csv(path: str | None, summary: ScanSummary) -> None:
    if not path:
        return
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['symbol', 'setup_tier', 'grade', 'score', 'price', 'pivot_distance_pct', 'contraction_count', 'base_depth_pct'])
        for candidate in summary.final_candidates:
            writer.writerow([
                candidate.symbol,
                candidate.setup_tier,
                candidate.grade,
                candidate.overall_score,
                candidate.last_price,
                candidate.vcp.distance_to_pivot_pct,
                candidate.vcp.contraction_count,
                candidate.vcp.base_depth_pct,
            ])


def write_html(path: str, summary: ScanSummary) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_HTML_TEMPLATE.render(summary=summary, defect_translations=DEFECT_TRANSLATIONS), encoding='utf-8')
