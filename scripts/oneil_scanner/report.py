from __future__ import annotations

import csv
import json
from pathlib import Path

try:
    from jinja2 import Template
except ModuleNotFoundError as exc:
    if exc.name != 'jinja2':
        raise
    Template = None

from .config import ScannerConfig
from .models import ScanRunSummary

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
    'quality_score',
    'setup_score',
    'report_rank',
    'secondary_signals',
    'notes',
]

_HTML_TEMPLATE_SOURCE = (
    """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>O'Neil Setup Scanner Report</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #222; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 13px; text-align: left; vertical-align: top; }
    th { background: #f5f5f5; }
    .muted { color: #666; }
  </style>
</head>
<body>
  <h1>O'Neil Setup Scanner Report</h1>
  <p class="muted">Report: {{ summary.run_metadata.report_name }} | Universe: {{ summary.universe }} | As of: {{ summary.run_metadata.as_of or 'latest' }}</p>
  <p class="muted">Candidates: {{ summary.candidates | length }}</p>
  <p class="muted">Groups: {% for group in summary.grouped_candidate_summaries %}{{ group.label }} ({{ group.candidate_count }}){% if not loop.last %}; {% endif %}{% else %}None{% endfor %}</p>
  <table>
    <thead>
      <tr>
      {% for column in columns %}
        <th>{{ column }}</th>
      {% endfor %}
      </tr>
    </thead>
    <tbody>
    {% for candidate in candidates %}
      <tr>
      {% for column in columns %}
        {% set value = candidate[column] %}
        <td>{% if value is iterable and value is not string %}{{ value | join(', ') }}{% elif value is none %}{% else %}{{ value }}{% endif %}</td>
      {% endfor %}
      </tr>
    {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""
)


def _missing_html_dependency() -> ModuleNotFoundError:
    return ModuleNotFoundError('jinja2 is required for HTML report generation')


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


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
            row = candidate.to_dict()
            row['secondary_signals'] = ', '.join(row['secondary_signals'])
            row['notes'] = ', '.join(row['notes'])
            writer.writerow({column: row.get(column) for column in CSV_COLUMNS})


def write_html(path: str | Path, summary: ScanRunSummary) -> None:
    if Template is None:
        raise _missing_html_dependency()
    output = Path(path)
    _ensure_parent(output)
    rows = [candidate.to_dict() for candidate in summary.candidates]
    output.write_text(Template(_HTML_TEMPLATE_SOURCE).render(summary=summary, columns=CSV_COLUMNS, candidates=rows), encoding='utf-8')


def write_report_bundle(config: ScannerConfig, summary: ScanRunSummary) -> dict[str, Path]:
    paths = {
        'json': config.report_path('json'),
        'csv': config.report_path('csv'),
        'html': config.report_path('html'),
    }
    write_json(paths['json'], summary)
    write_csv(paths['csv'], summary)
    write_html(paths['html'], summary)
    return paths
