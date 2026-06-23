from __future__ import annotations

import json
from pathlib import Path

from reversal_lib.backtest import summary_to_dict
from reversal_lib.models import BacktestSummary


def build_json_summary_payload(summary: BacktestSummary, grouped: dict | None = None, params: dict | None = None) -> dict:
    payload = summary_to_dict(summary)
    if grouped is not None:
        payload['grouped'] = grouped
    if params is not None:
        payload['params'] = params
    return payload


def write_json_summary(path: str | None, summary: BacktestSummary, grouped: dict | None = None, params: dict | None = None) -> None:
    if not path:
        return
    payload = build_json_summary_payload(summary, grouped=grouped, params=params)
    Path(path).write_text(json.dumps(payload, indent=2), encoding='utf-8')


__all__ = ['build_json_summary_payload', 'write_json_summary']
