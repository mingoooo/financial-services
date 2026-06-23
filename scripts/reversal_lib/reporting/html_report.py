from __future__ import annotations

from pathlib import Path

from reversal_lib.models import BacktestSummary, TradeRecord


def build_html_report(summary: BacktestSummary, trades: list[TradeRecord]) -> str:
    avg_return = summary.average_return_pct if summary.total_trades else 0.0
    rows = ''.join(
        f"<tr><td>{t.symbol}</td><td>{t.side}</td><td>{t.pattern}</td><td>{t.entry_date}</td><td>{t.exit_date}</td><td>{t.entry_price:.2f}</td><td>{t.exit_price:.2f}</td><td>{t.pnl:.2f}</td><td>{t.return_pct:.2f}%</td><td>{t.exit_reason}</td></tr>"
        for t in trades[:200]
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Backtest Report</title></head><body>"
        "<h1>Backtest Report</h1>"
        f"<p>Total trades: {summary.total_trades}</p>"
        f"<p>Win rate: {summary.win_rate:.2f}%</p>"
        f"<p>Average return: {avg_return:.2f}%</p>"
        f"<p>Total PnL: {summary.total_pnl:.2f}</p>"
        f"<p>Max drawdown: {summary.max_drawdown_pct:.2f}%</p>"
        f"<p>Profit factor: {summary.profit_factor:.2f}</p>"
        "<table><thead><tr><th>Symbol</th><th>Side</th><th>Pattern</th><th>Entry Date</th><th>Exit Date</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Return</th><th>Reason</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></body></html>"
    )


def write_html_report(path: str | None, summary: BacktestSummary, trades: list[TradeRecord]) -> None:
    if not path:
        return
    Path(path).write_text(build_html_report(summary, trades), encoding='utf-8')


__all__ = ['build_html_report', 'write_html_report']
