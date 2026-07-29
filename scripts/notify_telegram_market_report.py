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


def _build_links(*pairs: tuple[str, str | None]) -> list[str]:
    return [f'{label}: {value}' for label, value in pairs if value]


def _extract_oneil_summary(report_path: Path) -> dict[str, Any]:
    payload = _load_json(report_path)
    run_metadata = payload.get('run_metadata', {})
    candidates = payload.get('candidates') or []
    candidate_count = payload.get('candidate_count')
    if candidate_count is None:
        candidate_count = len(candidates)
    return {
        'report_name': run_metadata.get('report_name') or payload.get('report_name') or report_path.stem,
        'run_timestamp': run_metadata.get('run_timestamp') or payload.get('run_timestamp') or 'unknown',
        'universe': payload.get('universe') or 'unknown',
        'candidates': candidates,
        'candidate_count': candidate_count,
        'warnings': run_metadata.get('warnings') or payload.get('warnings') or [],
    }


def _build_premarket_message(
    report_path: Path,
    pages_url: str | None,
    run_label: str,
    *,
    hub_url: str | None = None,
    alt_pages_url: str | None = None,
) -> str:
    title = _read_markdown_title(report_path)
    lines = [
        '📈 盘前报告已生成',
        f'发送时点: {run_label}',
        f'标题: {title}',
    ]
    lines.extend(
        _build_links(
            ('导航页', hub_url),
            ('中文报告', pages_url),
            ('English report', alt_pages_url),
        )
    )
    return '\n'.join(lines)


def _build_oneil_message(
    report_path: Path,
    pages_url: str | None,
    run_label: str,
    *,
    hub_url: str | None = None,
) -> str:
    summary = _extract_oneil_summary(report_path)
    lines = [
        "🚀 O'Neil 扫描已完成",
        f'发送时点: {run_label}',
        f"报告: {summary['report_name']}",
        f"运行时间: {summary['run_timestamp']}",
        f"股票池: {summary['universe']}",
        f"候选数量: {summary['candidate_count']}",
    ]

    candidates = summary['candidates']
    if candidates:
        lines.append('前几条候选:')
        for candidate in candidates[:5]:
            lines.append(_format_oneil_candidate(candidate))
    else:
        lines.append('当前没有命中候选。')

    warnings = summary['warnings']
    if warnings:
        lines.append(f'注意事项: {warnings[0]}')

    lines.extend(
        _build_links(
            ('导航页', hub_url),
            ('扫描报告', pages_url),
        )
    )
    return '\n'.join(lines)


def _build_full_message(
    *,
    premarket_report_path: Path,
    oneil_report_path: Path,
    run_label: str,
    hub_url: str | None,
    premarket_pages_url: str | None,
    premarket_alt_pages_url: str | None,
    oneil_pages_url: str | None,
) -> str:
    premarket_title = _read_markdown_title(premarket_report_path)
    oneil = _extract_oneil_summary(oneil_report_path)
    lines = [
        '📬 市场扫描汇总已生成',
        f'发送时点: {run_label}',
        f'盘前标题: {premarket_title}',
        f"O'Neil 股票池: {oneil['universe']}",
        f"O'Neil 候选数量: {oneil['candidate_count']}",
    ]

    candidates = oneil['candidates']
    if candidates:
        lines.append("O'Neil 前几条候选:")
        for candidate in candidates[:3]:
            lines.append(_format_oneil_candidate(candidate))

    warnings = oneil['warnings']
    if warnings:
        lines.append(f'注意事项: {warnings[0]}')

    lines.extend(
        _build_links(
            ('导航页', hub_url),
            ('盘前中文', premarket_pages_url),
            ('盘前英文', premarket_alt_pages_url),
            ("O'Neil 报告", oneil_pages_url),
        )
    )
    return '\n'.join(lines)


def build_message(
    *,
    family: str,
    report_path: str | None,
    pages_url: str | None,
    run_label: str,
    hub_url: str | None = None,
    alt_pages_url: str | None = None,
    premarket_report_path: str | None = None,
    oneil_report_path: str | None = None,
    premarket_pages_url: str | None = None,
    premarket_alt_pages_url: str | None = None,
    oneil_pages_url: str | None = None,
) -> str:
    if family == 'premarket':
        if not report_path:
            raise ValueError('report_path is required for premarket notifications')
        return _build_premarket_message(
            Path(report_path),
            pages_url,
            run_label,
            hub_url=hub_url,
            alt_pages_url=alt_pages_url,
        )
    if family == 'oneil':
        if not report_path:
            raise ValueError('report_path is required for oneil notifications')
        return _build_oneil_message(
            Path(report_path),
            pages_url,
            run_label,
            hub_url=hub_url,
        )
    if family == 'full':
        if not premarket_report_path or not oneil_report_path:
            raise ValueError('premarket_report_path and oneil_report_path are required for full notifications')
        return _build_full_message(
            premarket_report_path=Path(premarket_report_path),
            oneil_report_path=Path(oneil_report_path),
            run_label=run_label,
            hub_url=hub_url,
            premarket_pages_url=premarket_pages_url,
            premarket_alt_pages_url=premarket_alt_pages_url,
            oneil_pages_url=oneil_pages_url,
        )
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
    parser.add_argument('--family', required=True, choices=['premarket', 'oneil', 'full'])
    parser.add_argument('--report-path')
    parser.add_argument('--pages-url')
    parser.add_argument('--alt-pages-url')
    parser.add_argument('--hub-url')
    parser.add_argument('--premarket-report-path')
    parser.add_argument('--oneil-report-path')
    parser.add_argument('--premarket-pages-url')
    parser.add_argument('--premarket-alt-pages-url')
    parser.add_argument('--oneil-pages-url')
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
            hub_url=args.hub_url,
            alt_pages_url=args.alt_pages_url,
            premarket_report_path=args.premarket_report_path,
            oneil_report_path=args.oneil_report_path,
            premarket_pages_url=args.premarket_pages_url,
            premarket_alt_pages_url=args.premarket_alt_pages_url,
            oneil_pages_url=args.oneil_pages_url,
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
