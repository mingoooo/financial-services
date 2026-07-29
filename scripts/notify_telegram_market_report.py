from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError


def _read_markdown_title(path: Path) -> str:
    title = 'AI 盘前报告'
    if not path.exists():
        return title
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            return line[2:].strip() or title
    return title


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _format_oneil_candidate(candidate: dict[str, Any]) -> str:
    symbol = str(candidate.get('symbol') or '?').upper()
    pattern = candidate.get('pattern_variant') or candidate.get('pattern_type') or candidate.get('pattern_family') or 'setup'
    trigger_date = candidate.get('trigger_date') or 'n/a'
    setup_score = candidate.get('setup_score')
    score_suffix = '' if setup_score is None else f' | Score {setup_score}'
    return f'- {symbol} {pattern} | Trigger {trigger_date}{score_suffix}'


def _build_premarket_message(report_path: Path, pages_url: str | None, run_label: str) -> str:
    title = _read_markdown_title(report_path)
    lines = [
        title,
        f'发送时点: {run_label}',
        '盘前报告已生成。',
    ]
    if pages_url:
        lines.append(f'报告页面: {pages_url}')
    return '\n'.join(lines)


def _build_oneil_message(report_path: Path, pages_url: str | None, run_label: str) -> str:
    payload = _load_json(report_path)
    run_metadata = payload.get('run_metadata', {})
    report_name = run_metadata.get('report_name') or payload.get('report_name') or report_path.stem
    run_timestamp = run_metadata.get('run_timestamp') or payload.get('run_timestamp') or 'unknown'
    universe = payload.get('universe') or 'unknown'
    candidates = payload.get('candidates') or []
    candidate_count = payload.get('candidate_count')
    if candidate_count is None:
        candidate_count = len(candidates)

    lines = [
        "O'Neil 实时扫描",
        f'发送时点: {run_label}',
        f'报告: {report_name}',
        f'运行时间: {run_timestamp}',
        f'股票池: {universe}',
        f'候选数量: {candidate_count}',
    ]

    if candidates:
        lines.append('前几条候选:')
        for candidate in candidates[:5]:
            lines.append(_format_oneil_candidate(candidate))
    else:
        lines.append('当前没有命中候选。')

    warnings = run_metadata.get('warnings') or payload.get('warnings') or []
    if warnings:
        lines.append(f'注意事项: {warnings[0]}')

    if pages_url:
        lines.append(f'报告页面: {pages_url}')
    return '\n'.join(lines)


def build_message(*, family: str, report_path: str, pages_url: str | None, run_label: str) -> str:
    path = Path(report_path)
    if family == 'premarket':
        return _build_premarket_message(path, pages_url, run_label)
    if family == 'oneil':
        return _build_oneil_message(path, pages_url, run_label)
    raise ValueError(f'Unsupported report family: {family}')


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
    except HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='ignore') if exc.fp else ''
        raise RuntimeError(f'Telegram HTTPError {exc.code}: {error_body or exc.reason}') from exc
    except URLError as exc:
        raise RuntimeError(f'Telegram URLError: {exc.reason}') from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Telegram sendMessage returned non-JSON body: {body}') from exc
    if not payload.get('ok'):
        raise RuntimeError(f'Telegram sendMessage failed: {body}')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Send Telegram notifications for market report families.')
    parser.add_argument('--family', required=True, choices=['premarket', 'oneil'])
    parser.add_argument('--report-path', required=True)
    parser.add_argument('--pages-url')
    parser.add_argument('--run-label', default='scheduled run')
    parser.add_argument('--dry-run', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        message = build_message(
            family=args.family,
            report_path=args.report_path,
            pages_url=args.pages_url,
            run_label=args.run_label,
        )
    except Exception as exc:
        print(f'Failed to build Telegram notification: {exc}', file=sys.stderr)
        return 1

    if args.dry_run:
        print(message)
        return 0

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        print('TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing, skip notification.', file=sys.stderr)
        return 0

    try:
        _send_telegram(bot_token, chat_id, message)
    except Exception as exc:
        print(f'Telegram notification failed: {exc}', file=sys.stderr)
        return 1

    print('Telegram notification sent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
