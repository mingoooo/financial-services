from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import summary_to_dict
from .models import BacktestSummary, Signal, TradeRecord
from .presets import describe_strategy_preset


def write_json_summary(path: str | None, summary: BacktestSummary, grouped: dict | None = None, params: dict | None = None) -> None:
    if not path:
        return
    payload = summary_to_dict(summary)
    if grouped is not None:
        payload["grouped"] = grouped
    if params is not None:
        payload["params"] = params
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_trade_csv(csv_dir: str | None, trades: list[TradeRecord]) -> None:
    if not csv_dir:
        return
    _write_csv(Path(csv_dir) / "trades.csv", [asdict(item) for item in trades])


def write_signal_csv(csv_dir: str | None, signals: list[Signal]) -> None:
    if not csv_dir:
        return
    _write_csv(Path(csv_dir) / "signals.csv", [asdict(item) for item in signals])


def write_html_report(path: str | None, summary: BacktestSummary, trades: list[TradeRecord]) -> None:
    if not path:
        return
    avg_return = summary.avg_return_pct if summary.total_trades else 0.0
    preset_description = describe_strategy_preset('main')
    rows = ''.join(
        f"<tr><td>{t.symbol}</td><td>{t.side}</td><td>{t.pattern}</td><td>{t.entry_date}</td><td>{t.exit_date}</td><td>{t.entry_price:.2f}</td><td>{t.exit_price:.2f}</td><td>{t.pnl:.2f}</td><td>{t.return_pct:.2f}%</td><td>{t.exit_reason}</td></tr>"
        for t in trades[:200]
    )
    html = f"""<!doctype html>
<html lang='zh-CN'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>反转形态回测报告</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px;line-height:1.5;}}
.page{{max-width:1280px;margin:0 auto;}}
.card{{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:18px 20px;margin:0 0 18px;}}
.meta{{color:#94a3b8;font-size:14px;margin:6px 0;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:12px;}}
.metric{{background:#0b1220;border:1px solid #243041;border-radius:12px;padding:12px;}}
.metric .label{{color:#94a3b8;font-size:12px;}}
.metric .value{{font-size:22px;font-weight:700;margin-top:4px;}}
table{{width:100%;border-collapse:collapse;background:#111827;}}
td,th{{border:1px solid #334155;padding:8px 10px;font-size:13px;}}
th{{background:#1e293b;}}
h1,h2{{margin:0 0 8px;}}
</style>
</head>
<body>
<div class='page'>
<h1>反转形态回测报告</h1>
<section class='card'>
<h2>策略摘要</h2>
<div class='meta'>当前回测报告已与扫描脚本共享同一套策略过滤层，并以 preset 为主要驱动方式。</div>
<div class='meta'>建议优先使用 `main` 或 `high_quality` preset，避免在多处手工维护分散参数。</div>
<div class='meta'>{preset_description}</div>
<div class='meta'>当前默认回测入场方式：确认日收盘价入场（`confirm_close`）。</div>
</section>
<section class='card'>
<h2>回测汇总</h2>
<div class='grid'>
<div class='metric'><div class='label'>总交易数</div><div class='value'>{summary.total_trades}</div></div>
<div class='metric'><div class='label'>胜率</div><div class='value'>{summary.win_rate:.2f}%</div></div>
<div class='metric'><div class='label'>平均单笔收益率</div><div class='value'>{avg_return:.2f}%</div></div>
<div class='metric'><div class='label'>总盈亏</div><div class='value'>{summary.total_pnl:.2f}</div></div>
<div class='metric'><div class='label'>最大回撤</div><div class='value'>{summary.max_drawdown_pct:.2f}%</div></div>
<div class='metric'><div class='label'>Profit Factor</div><div class='value'>{summary.profit_factor:.2f}</div></div>
</div>
</section>
<section class='card'>
<h2>交易明细（最多展示前 200 笔）</h2>
<table><thead><tr><th>代码</th><th>方向</th><th>形态</th><th>入场日</th><th>出场日</th><th>入场价</th><th>出场价</th><th>盈亏</th><th>收益率</th><th>出场原因</th></tr></thead><tbody>{rows}</tbody></table>
</section>
</div>
</body>
</html>"""
    Path(path).write_text(html, encoding="utf-8")
