from __future__ import annotations

import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError


def _build_message(report_path: str, pages_url: str | None, run_label: str) -> str:
    path = Path(report_path)
    title = "AI 盘前报告"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    lines = [
        f"{title}",
        f"发送时点: {run_label}",
        "盘前报告已生成。",
    ]
    if pages_url:
        lines.append(f"报告页面: {pages_url}")
    return "\n".join(lines)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        raise RuntimeError(f"Telegram HTTPError {exc.code}: {error_body or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Telegram URLError: {exc.reason}") from exc
    if '"ok":true' not in body:
        raise RuntimeError(f"Telegram sendMessage failed: {body}")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/notify_telegram_premarket.py <report-path> [pages-url] [run-label]", file=sys.stderr)
        return 2
    report_path = sys.argv[1]
    pages_url = sys.argv[2] if len(sys.argv) > 2 else None
    run_label = sys.argv[3] if len(sys.argv) > 3 else "scheduled run"
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing, skip notification.", file=sys.stderr)
        return 0
    message = _build_message(report_path, pages_url, run_label)
    try:
        _send_telegram(bot_token, chat_id, message)
    except Exception as exc:
        print(f"Telegram notification failed: {exc}", file=sys.stderr)
        return 1
    print("Telegram notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
