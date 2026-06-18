from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _load_payload(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _build_message(payload: dict, pages_url: str | None) -> str:
    meta = payload.get('meta', {})
    results = payload.get('results', [])
    preset = meta.get('preset', 'unknown')
    result_count = meta.get('result_count', len(results))
    recent_days = meta.get('recent_confirm_days', '?')
    lines = [
        f'反转扫描通知',
        f'preset: {preset}',
        f'最近确认窗口: {recent_days} 天',
        f'命中数量: {result_count}',
    ]
    if results:
        lines.append('前几条信号:')
        for item in results[:5]:
            lines.append(
                f"- {item.get('symbol')} {item.get('pattern')} | Confirm {item.get('confirm_date')} | Stop {item.get('stop_loss')} | T1 {item.get('first_target')} | T2 {item.get('second_target')}"
            )
    else:
        lines.append('当前没有命中信号。')
    if pages_url:
        lines.append(f'报告页面: {pages_url}')
    return '\n'.join(lines)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8', errors='ignore')
    payload = json.loads(body)
    if not payload.get('ok'):
        raise RuntimeError(f'Telegram sendMessage failed: {body}')


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python scripts/notify_telegram_scan.py <json-path> [pages-url]', file=sys.stderr)
        return 2
    json_path = sys.argv[1]
    pages_url = sys.argv[2] if len(sys.argv) > 2 else None
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        print('TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing, skip notification.', file=sys.stderr)
        return 0
    payload = _load_payload(json_path)
    message = _build_message(payload, pages_url)
    _send_telegram(bot_token, chat_id, message)
    print('Telegram notification sent.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
