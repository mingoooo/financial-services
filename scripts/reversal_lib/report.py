from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import summary_to_dict
from .models import BacktestSummary, Signal, TradeRecord


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
    rows = ''.join(
        f"<tr><td>{t.symbol}</td><td>{t.side}</td><td>{t.pattern}</td><td>{t.entry_date}</td><td>{t.exit_date}</td><td>{t.entry_price:.2f}</td><td>{t.exit_price:.2f}</td><td>{t.pnl:.2f}</td><td>{t.return_pct:.2f}%</td><td>{t.exit_reason}</td></tr>"
        for t in trades[:200]
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>反转形态回测</title>
<style>body{{font-family:sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #334155;padding:8px}}th{{background:#1e293b}}</style>
</head><body>
<h1>反转形态回测汇总</h1>
<p>总交易数: {summary.total_trades} · 胜率: {summary.win_rate:.2f}% · 总盈亏: {summary.total_pnl:.2f} · 最大回撤: {summary.max_drawdown_pct:.2f}%</p>
<table><thead><tr><th>代码</th><th>方向</th><th>形态</th><th>入场日</th><th>出场日</th><th>入场价</th><th>出场价</th><th>盈亏</th><th>收益率</th><th>出场原因</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    Path(path).write_text(html, encoding="utf-8")
