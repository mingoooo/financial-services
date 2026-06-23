from .models import BacktestSummary, Signal, TradeRecord
from .reporting.csv_report import write_signal_csv as _write_signal_csv
from .reporting.csv_report import write_trade_csv as _write_trade_csv
from .reporting.html_report import write_html_report as _write_html_report
from .reporting.json_report import write_json_summary as _write_json_summary


def write_json_summary(path: str | None, summary: BacktestSummary, grouped: dict | None = None, params: dict | None = None) -> None:
    _write_json_summary(path, summary, grouped=grouped, params=params)


def write_trade_csv(csv_dir: str | None, trades: list[TradeRecord]) -> None:
    _write_trade_csv(csv_dir, trades)


def write_signal_csv(csv_dir: str | None, signals: list[Signal]) -> None:
    _write_signal_csv(csv_dir, signals)


def write_html_report(path: str | None, summary: BacktestSummary, trades: list[TradeRecord]) -> None:
    _write_html_report(path, summary, trades)
